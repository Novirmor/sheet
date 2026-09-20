"""Session worker for external interpreters.

This module runs inside a user-selected Python interpreter, launched as
``<interpreter> external_bootstrap.py <code directory> <session id>``.
Commands arrive as UTF-8 JSON lines on stdin and worker messages leave as JSON
lines on stdout. The worker first redirects the raw stdout file descriptor to
stderr, so stray writes from user code or C extensions cannot corrupt the
protocol channel. It reuses the same validated session loop as the built-in
multiprocessing worker.
"""

from __future__ import annotations

import json
import os
import signal
import sys

MAX_LINE_BYTES = 8 * 1024 * 1024


class _SignalFlag:
    """Interrupt flag set by SIGINT; polled by the shared session trace loop."""

    def __init__(self) -> None:
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True

    def clear(self) -> None:
        self._set = False


INTERRUPT_FLAG = _SignalFlag()

if os.name == "posix":

    def _handle_sigint(_signum, _frame) -> None:
        INTERRUPT_FLAG.set()

    signal.signal(signal.SIGINT, _handle_sigint)


def main(session_id: str) -> int:
    from sheet.scripting import _run_session_loop

    protocol_fd = os.dup(1)
    os.dup2(2, 1)  # stray stdout writes are reported on stderr instead
    reader = sys.stdin  # text mode, UTF-8 from the launcher's -X utf8

    def get_command() -> object:
        line = reader.readline()
        if not line:
            return {"kind": "shutdown"}
        if len(line.encode("utf-8", "ignore")) > MAX_LINE_BYTES:
            raise SystemExit("session command exceeded the line-size limit")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return {"kind": "shutdown"}

    with os.fdopen(protocol_fd, "w", encoding="utf-8") as messages:

        def send_message(payload: dict[str, object]) -> None:
            messages.write(json.dumps(payload) + "\n")
            messages.flush()

        try:
            _run_session_loop(get_command, send_message, INTERRUPT_FLAG, session_id)
        except BrokenPipeError:
            return 1
    return 0
