"""Parent-side sessions that execute Python in a user-selected external interpreter.

Commands travel as UTF-8 JSON lines on the child's stdin; worker messages return
on an inherited pipe (``pass_fds``), so nothing the child prints can corrupt the
protocol. The child's real stdout is discarded and its stderr is drained and
surfaced when the process exits unexpectedly. Interruption sends SIGINT where
available and otherwise escalates to termination after a grace period, matching
the built-in session's contract.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

from sheet.scripting import (
    MAX_MESSAGE_BYTES,
    SessionCommand,
    SessionResult,
    SessionState,
    _command_payload,
    _inspection_from_payload,
    _output_from_payload,
    _result_from_payload,
    _validate_cells,
    _validate_payload_size,
    _validate_text,
)

if TYPE_CHECKING:
    from sheet.scripting import ScriptResult
    from sheet.workbook import Workbook

_STDERR_TAIL_LINES = 100
_EOF = "_eof"


def external_code_directory() -> Path:
    """Directory that makes ``import sheet`` work inside an external interpreter."""
    bundle = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle, str):
        return Path(bundle) / "src"
    return Path(__file__).resolve().parent.parent


def external_bootstrap_path() -> Path:
    return external_code_directory() / "sheet" / "external_bootstrap.py"


def external_launch_ready() -> bool:
    """True when this build ships the bootstrap an external interpreter executes."""
    return external_bootstrap_path().is_file()


class ExternalScriptSession:
    """A spawned, serial Python namespace in an external interpreter."""

    def __init__(self, interpreter: str | Path, *, interrupt_grace: float = 1.0) -> None:
        if interrupt_grace <= 0:
            raise ValueError("interrupt_grace must be positive")
        self._interpreter = Path(interpreter)
        self._interrupt_grace = interrupt_grace
        self._process: subprocess.Popen | None = None
        self._messages: queue.Queue[dict[str, object]] | None = None
        self._stdin_lock = threading.Lock()
        self._stderr_tail: list[str] = []
        self._eof_seen = False
        self._launch_error = ""
        self._current: SessionCommand | None = None
        self._deadline: float | None = None
        self._deadline_reason = ""
        self._exit_reported = False
        self._output_events = []
        self._inspections = []
        self.session_id = ""
        self.state = SessionState.STOPPED

    @property
    def running(self) -> bool:
        return self.state in {SessionState.RUNNING, SessionState.INTERRUPTING}

    @property
    def interpreter(self) -> Path:
        return self._interpreter

    def start(self) -> None:
        if self.state in {
            SessionState.STARTING,
            SessionState.IDLE,
            SessionState.RUNNING,
            SessionState.INTERRUPTING,
        }:
            return
        self.session_id = uuid.uuid4().hex
        self._current = None
        self._deadline = None
        self._exit_reported = False
        self._eof_seen = False
        self._launch_error = ""
        self._stderr_tail.clear()
        self._output_events.clear()
        self._inspections.clear()
        if not external_launch_ready():
            self.state = SessionState.FAILED
            self._launch_error = "This build does not package the external worker bootstrap."
            return
        read_fd, write_fd = os.pipe()
        messages: queue.Queue[dict[str, object]] = queue.Queue()
        try:
            self._process = subprocess.Popen(
                [
                    os.fspath(self._interpreter),
                    "-X",
                    "utf8",
                    os.fspath(external_bootstrap_path()),
                    os.fspath(external_code_directory()),
                    str(write_fd),
                    self.session_id,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                pass_fds=(write_fd,),
            )
        except OSError as error:
            os.close(read_fd)
            os.close(write_fd)
            self._launch_error = f"Could not start {self._interpreter}: {error}"
            self.state = SessionState.FAILED
            return
        os.close(write_fd)  # the parent keeps only the read end
        self._messages = messages
        threading.Thread(target=self._read_messages, args=(messages, read_fd), daemon=True).start()
        assert self._process.stderr is not None
        threading.Thread(
            target=self._drain_stderr, args=(self._process.stderr,), daemon=True
        ).start()
        self.state = SessionState.STARTING

    def run(
        self,
        source: str,
        workbook: Workbook,
        *,
        source_id: str,
        source_version: int,
        interactive: bool = False,
        script_path: str | None = None,
        timeout: float | None = None,
    ) -> str:
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.state == SessionState.STOPPED or self.state == SessionState.FAILED:
            self.start()
        if self.state not in {SessionState.STARTING, SessionState.IDLE} or self._process is None:
            raise RuntimeError("a session command is already running")
        validated_source = _validate_text(source, "source")
        cells = _validate_cells(dict(workbook.cells), workbook.rows, workbook.columns)
        _validate_payload_size(validated_source, cells)
        command = SessionCommand(
            validated_source,
            _validate_text(source_id, "source identity", limit=256),
            source_version,
            workbook.document_id,
            workbook.revision,
            uuid.uuid4().hex,
            self.session_id,
            cells,
            workbook.rows,
            workbook.columns,
            interactive,
            script_path,
        )
        self._send(_command_payload(command))
        self._current = command
        self._deadline = time.monotonic() + timeout if timeout is not None else None
        self._deadline_reason = "timeout"
        self.state = SessionState.RUNNING
        return command.run_id

    execute = run

    def inspect_variables(self) -> str:
        return self._inspect("variables")

    def inspect_variable_page(self, handle: str, start: int = 0) -> str:
        return self._inspect("variable_page", handle=handle, start=start)

    def _inspect(self, kind: str, **payload: object) -> str:
        if self.state != SessionState.IDLE or self._process is None:
            raise RuntimeError("the session must be idle to inspect variables")
        request_id = uuid.uuid4().hex
        self._send(
            {"kind": kind, "request_id": request_id, "session_id": self.session_id, **payload}
        )
        return request_id

    def take_output_events(self) -> list:
        events = self._output_events
        self._output_events = []
        return events

    def take_inspections(self) -> list:
        inspections = self._inspections
        self._inspections = []
        return inspections

    def interrupt(self) -> bool:
        if self.state != SessionState.RUNNING or self._process is None:
            return False
        if os.name == "posix":
            with suppress(OSError):
                self._process.send_signal(signal.SIGINT)
        self._deadline = time.monotonic() + self._interrupt_grace
        self._deadline_reason = "interrupt"
        self.state = SessionState.INTERRUPTING
        return True

    def restart(self) -> None:
        self.stop()
        self.start()

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._send({"kind": "shutdown", "session_id": self.session_id})
            with suppress(subprocess.TimeoutExpired):
                self._process.wait(timeout=0.5)
        self._dispose_process()
        self._current = None
        self._deadline = None
        self.state = SessionState.STOPPED

    def poll(self) -> SessionResult | None:
        completed: SessionResult | None = None
        messages = self._messages
        if messages is not None:
            while True:
                try:
                    payload = messages.get_nowait()
                except queue.Empty:
                    break
                kind = payload.get("kind") if isinstance(payload, dict) else None
                if kind == _EOF:
                    self._eof_seen = True
                    continue
                if kind == "ready":
                    if payload.get("session_id") == self.session_id and self._current is None:
                        self.state = SessionState.IDLE
                    continue
                if kind == "output":
                    with suppress(ValueError):
                        event = _output_from_payload(payload, self.session_id)
                        if event is not None:
                            self._output_events.append(event)
                    continue
                if kind == "inspection":
                    with suppress(ValueError):
                        self._inspections.append(_inspection_from_payload(payload, self.session_id))
                    continue
                try:
                    result = _result_from_payload(payload, self.session_id)
                except ValueError:
                    continue
                if self._current is None or result.run_id != self._current.run_id:
                    continue
                self._current = None
                self._deadline = None
                self.state = SessionState.IDLE
                completed = result
                continue
        if completed is not None:
            return completed
        if self.state == SessionState.FAILED and self._launch_error and not self._exit_reported:
            self._exit_reported = True
            return self._launch_failure_result()
        if self._deadline is not None and time.monotonic() >= self._deadline:
            return self._terminate_current(
                "External session timed out and was terminated; session variables were lost."
                if self._deadline_reason == "timeout"
                else (
                    "External session was terminated after the interrupt grace period; "
                    "session variables were lost."
                )
            )
        process = self._process
        exited = self._eof_seen or (process is not None and process.poll() is not None)
        if (
            exited
            and not self._exit_reported
            and self.state
            not in {
                SessionState.STOPPED,
                SessionState.FAILED,
            }
        ):
            if self.state == SessionState.INTERRUPTING:
                # The child died from the interrupt signal before replying; report
                # the interruption rather than an unexplained exit.
                return self._terminate_current(
                    "External session was terminated after the interrupt grace period; "
                    "session variables were lost."
                )
            self._exit_reported = True
            command = self._current
            self._current = None
            self._deadline = None
            self.state = SessionState.FAILED
            details = "".join(self._stderr_tail[-_STDERR_TAIL_LINES:]).strip()
            message = "External session process exited without returning a result."
            if details:
                message = f"{message}\n{details}"
            self._dispose_process()
            return SessionResult(
                message,
                {},
                command.rows if command else 1,
                command.columns if command else 1,
                True,
                command.document_id if command else "",
                command.snapshot_revision if command else 0,
                command.run_id if command else "",
                self.session_id,
                command.source_id if command else "",
                command.source_version if command else 0,
            )
        return None

    def _launch_failure_result(self) -> SessionResult:
        self.state = SessionState.FAILED
        return SessionResult(self._launch_error, {}, 1, 1, True, "", 0, "", self.session_id, "", 0)

    def _terminate_current(self, output: str) -> SessionResult | None:
        command = self._current
        if command is None:
            return None
        self._current = None
        self._deadline = None
        self.state = SessionState.FAILED
        self._dispose_process()
        return SessionResult(
            output,
            {},
            command.rows,
            command.columns,
            True,
            command.document_id,
            command.snapshot_revision,
            command.run_id,
            command.session_id,
            command.source_id,
            command.source_version,
            True,
        )

    def _send(self, payload: dict[str, object]) -> None:
        line = json.dumps(payload)
        if len(line.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError(f"message exceeds the {MAX_MESSAGE_BYTES}-byte limit")
        with self._stdin_lock:
            stdin = self._process.stdin if self._process is not None else None
            if stdin is None:
                return
            try:
                stdin.write(line.encode("utf-8") + b"\n")
                stdin.flush()
            except BrokenPipeError, OSError:
                pass  # an unexpected exit is reported through poll()

    def _read_messages(self, messages: queue.Queue[dict[str, object]], read_fd: int) -> None:
        try:
            with os.fdopen(read_fd, "r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        messages.put(payload)
        except OSError:
            pass
        finally:
            messages.put({"kind": _EOF})

    def _drain_stderr(self, stream) -> None:
        try:
            for line in stream:
                self._stderr_tail.append(line.decode("utf-8", "replace"))
                if len(self._stderr_tail) > 2 * _STDERR_TAIL_LINES:
                    del self._stderr_tail[:_STDERR_TAIL_LINES]
        except OSError, ValueError:
            pass

    def _dispose_process(self) -> None:
        process = self._process
        if process is not None:
            if process.poll() is None:
                process.terminate()
            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=0.5)
            if process.stdin is not None:
                with suppress(OSError, ValueError):
                    process.stdin.close()
        self._process = None
        self._messages = None


class ExternalScriptProcess:
    """One fresh-run script process in an external interpreter."""

    def __init__(
        self,
        interpreter: str | Path,
        source: str,
        workbook: Workbook,
        script_path: str | None = None,
        *,
        source_id: str = "script",
        source_version: int = 0,
    ) -> None:
        self.document_id = workbook.document_id
        self.snapshot_revision = workbook.revision
        self.run_id = uuid.uuid4().hex
        self._source = source
        self._workbook = workbook
        self._script_path = script_path
        self._source_id = source_id
        self._source_version = source_version
        self._session = ExternalScriptSession(interpreter)
        self._session_run_id = ""

    @property
    def running(self) -> bool:
        return self._session.running

    def start(self) -> None:
        self._session.start()
        self._session_run_id = self._session.run(
            self._source,
            self._workbook,
            source_id=self._source_id,
            source_version=self._source_version,
            script_path=self._script_path,
        )
        self.run_id = self._session_run_id

    def poll(self) -> ScriptResult | SessionResult | None:
        result = self._session.poll()
        if result is not None:
            self._session.stop()
            return result
        return None

    def stop(self) -> None:
        self._session.stop()
