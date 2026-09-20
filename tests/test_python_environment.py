import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from sheet.python_environment import (
    DECLARATION_NAME,
    app_runtime_inspection,
    command_preview,
    dependency_declaration,
    find_uv,
    inspect_interpreter,
    run_uv_operation,
    uv_operation,
)


def _probe(*, version=(3, 14, 0), packages=None):
    payload = {
        "protocol": "sheet-environment-v1",
        "executable": "/python",
        "version": list(version),
        "packages": packages or {"pandas": "2.2.3", "plotly": "6.0.1"},
    }
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_interpreter_probe_passes_a_spaced_path_as_one_argument(tmp_path: Path) -> None:
    interpreter = tmp_path / "Python With Spaces" / "python"
    interpreter.parent.mkdir()
    interpreter.touch()
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return _probe()

    inspection = inspect_interpreter(interpreter, run=run)

    assert inspection.compatible
    assert calls[0][0][:2] == [str(interpreter), "-c"]
    assert calls[0][1]["check"] is False
    assert calls[0][1]["timeout"] == 5


def test_interpreter_probe_reports_failures_before_selection(tmp_path: Path) -> None:
    interpreter = tmp_path / "python"
    interpreter.touch()

    inspection = inspect_interpreter(
        interpreter,
        run=lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="not usable"),
    )

    assert not inspection.compatible
    assert inspection.error == "Interpreter probe failed: not usable"


def test_interpreter_probe_rejects_missing_requirements_and_old_python(tmp_path: Path) -> None:
    interpreter = tmp_path / "python"
    interpreter.touch()

    missing = inspect_interpreter(
        interpreter,
        run=lambda *_args, **_kwargs: _probe(packages={"pandas": "2.2.3", "plotly": None}),
    )
    old = inspect_interpreter(interpreter, run=lambda *_args, **_kwargs: _probe(version=(3, 13, 9)))

    assert missing.error == "Missing required package(s): plotly."
    assert old.error == "Python 3.14 or newer is required."


def test_dependency_declaration_and_uv_commands_are_portable_with_spaced_paths(
    tmp_path: Path,
) -> None:
    project = tmp_path / "My Project"
    project.mkdir()
    declaration = dependency_declaration(project, {"pandas": "2.2.3", "plotly": "6.0.1"})
    operation = uv_operation(tmp_path / "uv binary", project, declaration)
    venv_python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    assert declaration.path.name == DECLARATION_NAME
    assert "pandas==2.2.3" in declaration.content
    assert operation.commands[0] == (str(tmp_path / "uv binary"), "venv", str(project / ".venv"))
    assert operation.commands[1][-1] == str(declaration.path)
    assert str(venv_python) in command_preview(operation.commands)


def test_uv_failure_and_absent_uv_are_safe(monkeypatch, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    declaration = dependency_declaration(project, {"pandas": "2.2.3", "plotly": "6.0.1"})
    operation = uv_operation("uv", project, declaration)
    calls = []

    def run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0 if len(calls) == 1 else 1, stdout="", stderr="offline")

    result = run_uv_operation(operation, run=run)
    monkeypatch.setattr("sheet.python_environment.shutil.which", lambda _name: None)

    assert not result.succeeded
    assert "offline" in result.log
    assert len(calls) == 2
    assert find_uv() is None


def test_frozen_runtime_is_reported_without_probing_the_executable(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("frozen builds must not probe their own executable")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("sheet.python_environment.inspect_interpreter", forbidden)

    inspection = app_runtime_inspection()

    assert inspection.compatible
    assert inspection.path == Path(sys.executable)
    assert inspection.version == tuple(sys.version_info[:3])
    assert inspection.packages
    assert all(inspection.packages.values())
