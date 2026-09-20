"""Headless smoke checks for development and packaged builds.

The checks avoid Qt entirely so windowed packaged builds can run them without a
display or platform plugin; multiprocessing workers still exercise the frozen
spawn bootstrap. ``run_smoke_test`` returns an exit code: 0 means every check
passed.
"""

from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sheet import __version__
from sheet.python_environment import (
    EnvironmentInspection,
    app_runtime_inspection,
    inspect_interpreter,
)
from sheet.scripting import ScriptProcess, ScriptSession, SessionResult, SessionState
from sheet.workbook import Workbook

FRESH_SCRIPT = """import sys

print("fresh", sys.platform)
sheet.set("B1", sheet.get("A1") * 2)
total = sheet.get("A1") + sheet.get("B1")
"""

SESSION_SCRIPT = """import sys

print("session", sys.platform)
sheet.set("C1", value * 2)
total = value * 3
"""

POLL_INTERVAL = 0.05


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    ok: bool
    detail: str


def check_startup_report() -> tuple[bool, str]:
    frozen = bool(getattr(sys, "frozen", False))
    return True, f"Sheet {__version__}; frozen={frozen}; executable={sys.executable}"


def check_workbook_roundtrip(directory: Path) -> tuple[bool, str]:
    path = directory / "smoke-test.sheet"
    workbook = Workbook(path, recovery_enabled=False)
    workbook.set_cell(0, 0, "2")
    workbook.set_cell(1, 0, "3")
    workbook.set_cell(2, 0, "=SUM(A1:A2)")
    workbook.set_script("smoke", 'sheet.set("B1", 21)')
    workbook.save()
    workbook.close()

    reopened = Workbook(path, recovery_enabled=False)
    try:
        if reopened.value(2, 0) != 5:
            return False, f"formula evaluated to {reopened.value(2, 0)!r}"
        if reopened.scripts.get("smoke") != 'sheet.set("B1", 21)':
            return False, "stored script did not survive the roundtrip"
    finally:
        reopened.close()
    return True, "formulas, cells, and scripts survived a save/reopen roundtrip"


def check_fresh_script_process(timeout: float) -> tuple[bool, str]:
    workbook = Workbook(":memory:", recovery_enabled=False)
    workbook.set_cell(0, 0, "4")
    runner = ScriptProcess(FRESH_SCRIPT, workbook)
    runner.start()
    try:
        result = _poll_until(lambda: runner.poll(), timeout)
        if result is None:
            return False, f"no result within {timeout:.0f}s"
        if result.failed:
            return False, f"script failed: {result.output.strip()}"
        if result.changes != {(0, 1): "8"}:
            return False, f"unexpected cell changes: {result.changes}"
        if result.output != f"fresh {sys.platform}\n":
            return False, f"unexpected output: {result.output!r}"
        return True, "spawned one-shot worker ran and reported its changes"
    finally:
        runner.stop()
        workbook.close()


def check_persistent_session(timeout: float) -> tuple[bool, str]:
    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ScriptSession()
    try:
        session.run("value = 21", workbook, source_id="smoke", source_version=1)
        first = _poll_until(lambda: session.poll(), timeout)
        if first is None:
            return False, f"no first result within {timeout:.0f}s"
        if first.failed:
            return False, f"session command failed: {first.output.strip()}"

        session.run(SESSION_SCRIPT, workbook, source_id="smoke", source_version=2)
        second = _poll_session_result(session, timeout)
        if second is None:
            return False, f"no second result within {timeout:.0f}s"
        if isinstance(second, bool):
            return False, "session exited unexpectedly between commands"
        if second.failed:
            return False, f"second command failed: {second.output.strip()}"
        if second.changes != {(0, 2): "42"}:
            return False, f"unexpected cell changes: {second.changes}"

        session.inspect_variables()
        inspection = _poll_session_inspection(session, timeout)
        if inspection is None:
            return False, f"no variable snapshot within {timeout:.0f}s"
        if inspection.error:
            return False, f"variable snapshot failed: {inspection.error}"
        names = {variable.name for variable in inspection.variables}
        if "value" not in names or "total" not in names:
            return False, f"expected variables missing from snapshot: {sorted(names)}"
        return True, "persistent session kept variables and applied batched writes"
    finally:
        session.stop()
        workbook.close()


def check_app_runtime_environment() -> tuple[bool, str]:
    inspection = app_runtime_inspection()
    if not inspection.compatible:
        return False, inspection.error or "application runtime reported incompatible"
    packages = ", ".join(
        f"{name} {version or 'missing'}" for name, version in (inspection.packages or {}).items()
    )
    version = ".".join(str(part) for part in inspection.version)
    return True, f"application runtime: Python {version}; {packages}"


def check_external_launch_state() -> tuple[bool, str]:
    inspection = EnvironmentInspection(Path(sys.executable))
    if not inspection.external_launch_available:
        return False, "external worker launch must be available when the bootstrap is packaged"
    return True, "external worker launch is packaged and available"


def check_external_execution(interpreter: Path, timeout: float) -> tuple[bool, str]:
    from sheet.external_session import ExternalScriptSession

    workbook = Workbook(":memory:", recovery_enabled=False)
    session = ExternalScriptSession(interpreter)
    try:
        session.run(
            "value = 6\nsheet.set('A1', value * 7)",
            workbook,
            source_id="smoke",
            source_version=1,
        )
        result = _poll_until(lambda: session.poll(), timeout)
        if result is None:
            return False, f"no external result within {timeout:.0f}s"
        if result.failed:
            return False, f"external command failed: {result.output.strip()}"
        if result.changes != {(0, 0): "42"}:
            return False, f"unexpected changes: {result.changes}"
        return True, f"launched and executed a command with {interpreter}"
    finally:
        session.stop()
        workbook.close()


def _probe_check(inspection, interpreter: Path) -> tuple[bool, str]:
    """Verify the probe pipeline; an incompatible-but-probed interpreter is a valid state."""
    if not inspection.version:
        return False, inspection.error or "probe returned no Python version"
    version = ".".join(str(part) for part in inspection.version)
    missing = ", ".join(inspection.missing_packages) or "none"
    if inspection.compatible:
        state = "compatible"
    elif inspection.error:
        state = f"explicitly rejected: {inspection.error}"
    else:
        state = "probed; not compatible"
    return True, f"{interpreter}: Python {version}; missing packages: {missing}; {state}"


def _poll_until(poll, timeout: float):
    deadline = time.monotonic() + timeout
    result = None
    while result is None and time.monotonic() < deadline:
        result = poll()
        if result is None:
            time.sleep(POLL_INTERVAL)
    return result


def _poll_session_result(session: ScriptSession, timeout: float) -> SessionResult | bool | None:
    """Return the result, ``False`` for an unexpected exit, or ``None`` on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = session.poll()
        if result is not None:
            return result
        if session.state == SessionState.FAILED:
            return False
        time.sleep(POLL_INTERVAL)
    return None


def _poll_session_inspection(session: ScriptSession, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session.poll()
        inspections = session.take_inspections()
        if inspections:
            return inspections[-1]
        time.sleep(POLL_INTERVAL)
    return None


def run_smoke_test(interpreter: Path | None = None, *, timeout: float = 60.0, stream=None) -> int:
    """Run every smoke check; print progress when ``stream`` is given."""
    checks: list[tuple[str, tuple[bool, str]]] = [
        ("startup", check_startup_report()),
    ]
    with tempfile.TemporaryDirectory(prefix="sheet-smoke-") as temporary:
        checks.append(("workbook-roundtrip", check_workbook_roundtrip(Path(temporary))))
    checks.append(("fresh-script-process", check_fresh_script_process(timeout)))
    checks.append(("persistent-session", check_persistent_session(timeout)))
    checks.append(("app-runtime-environment", check_app_runtime_environment()))
    checks.append(("external-launch-state", check_external_launch_state()))
    if interpreter is not None:
        inspection = inspect_interpreter(interpreter, timeout=timeout)
        checks.append(
            (
                "external-interpreter-probe",
                _probe_check(inspection, interpreter),
            )
        )
        if inspection.compatible:
            checks.append(("external-execution", check_external_execution(interpreter, timeout)))

    results = [SmokeCheck(name, outcome[0], outcome[1]) for name, outcome in checks]
    if stream is not None:
        for check in results:
            line = f"{'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}"
            print(line, file=stream)
        failed = sum(1 for check in results if not check.ok)
        summary = f"{len(results) - failed} of {len(results)} smoke checks passed"
        print(summary, file=stream)
    return 0 if all(check.ok for check in results) else 1
