"""Safe inspection and optional setup helpers for user-managed Python environments."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_PYTHON_MINIMUM = (3, 14)
REQUIRED_PACKAGES = ("pandas", "plotly")
SETTINGS_KEY = "pythonEnvironment/interpreter"
DECLARATION_NAME = "sheet-requirements.txt"
PROBE_PROTOCOL = "sheet-environment-v1"

_PROBE = """import importlib.metadata as m, json, sys
packages = {}
for name in ('pandas', 'plotly'):
    try:
        packages[name] = m.version(name)
    except m.PackageNotFoundError:
        packages[name] = None
print(json.dumps({'protocol': 'sheet-environment-v1', 'executable': sys.executable,
                  'version': list(sys.version_info[:3]), 'packages': packages}))
"""


@dataclass(frozen=True, slots=True)
class EnvironmentInspection:
    path: Path
    executable: str = ""
    version: tuple[int, ...] = ()
    packages: Mapping[str, str | None] | None = None
    error: str = ""

    @property
    def missing_packages(self) -> tuple[str, ...]:
        return tuple(name for name in REQUIRED_PACKAGES if not (self.packages or {}).get(name))

    @property
    def compatible(self) -> bool:
        return (
            not self.error
            and self.version >= SUPPORTED_PYTHON_MINIMUM
            and not self.missing_packages
        )

    @property
    def external_launch_available(self) -> bool:
        """This build packages the bootstrap external interpreters execute."""
        return True


@dataclass(frozen=True, slots=True)
class DependencyDeclaration:
    path: Path
    content: str
    exists: bool


@dataclass(frozen=True, slots=True)
class UvOperation:
    commands: tuple[tuple[str, ...], ...]
    target: Path


@dataclass(frozen=True, slots=True)
class UvResult:
    succeeded: bool
    log: str


def inspect_interpreter(
    path: str | Path, *, timeout: float = 5, run: Callable[..., object] = subprocess.run
) -> EnvironmentInspection:
    """Probe an existing interpreter with fixed arguments and no shell."""
    interpreter = Path(path).expanduser()
    if not interpreter.is_file():
        return EnvironmentInspection(interpreter, error="Interpreter file does not exist.")
    try:
        completed = run(
            [os.fspath(interpreter), "-c", _PROBE],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return EnvironmentInspection(interpreter, error="Interpreter probe timed out.")
    except OSError as error:
        return EnvironmentInspection(interpreter, error=f"Could not start interpreter: {error}")
    if getattr(completed, "returncode", 1) != 0:
        message = (getattr(completed, "stderr", "") or "").strip()
        message = message or "interpreter exited unsuccessfully"
        return EnvironmentInspection(interpreter, error=f"Interpreter probe failed: {message}")
    try:
        payload = json.loads(getattr(completed, "stdout", ""))
        version = payload["version"]
        packages = payload["packages"]
        if (
            payload.get("protocol") != PROBE_PROTOCOL
            or not isinstance(payload.get("executable"), str)
            or not isinstance(version, list)
            or len(version) != 3
            or any(type(value) is not int for value in version)
            or not isinstance(packages, dict)
        ):
            raise ValueError
        package_versions = {
            name: value if isinstance(value, str) else None for name, value in packages.items()
        }
    except TypeError, ValueError, json.JSONDecodeError, KeyError:
        return EnvironmentInspection(
            interpreter, error="Interpreter returned an invalid Sheet probe."
        )
    inspection = EnvironmentInspection(
        interpreter, payload["executable"], tuple(version), package_versions
    )
    if inspection.version < SUPPORTED_PYTHON_MINIMUM:
        return EnvironmentInspection(
            interpreter,
            inspection.executable,
            inspection.version,
            inspection.packages,
            f"Python {SUPPORTED_PYTHON_MINIMUM[0]}.{SUPPORTED_PYTHON_MINIMUM[1]} "
            "or newer is required.",
        )
    if inspection.missing_packages:
        return EnvironmentInspection(
            interpreter,
            inspection.executable,
            inspection.version,
            inspection.packages,
            f"Missing required package(s): {', '.join(inspection.missing_packages)}.",
        )
    return inspection


def app_runtime_inspection() -> EnvironmentInspection:
    """Describe the runtime executing Sheet itself.

    A frozen application is not a Python interpreter, so probing its own
    executable as one would fail; report the bundled runtime directly instead
    of launching a subprocess.
    """
    if getattr(sys, "frozen", False):
        return _frozen_runtime_inspection()
    return inspect_interpreter(sys.executable)


def _frozen_runtime_inspection() -> EnvironmentInspection:
    packages: dict[str, str | None] = {}
    for name in REQUIRED_PACKAGES:
        try:
            packages[name] = getattr(__import__(name), "__version__", None)
        except ImportError:
            packages[name] = None
    return EnvironmentInspection(
        Path(sys.executable),
        executable=sys.executable,
        version=tuple(sys.version_info[:3]),
        packages=packages,
    )


def selected_interpreter(settings) -> Path | None:
    value = settings.value(SETTINGS_KEY, "")
    return Path(value) if isinstance(value, str) and value else None


def save_selected_interpreter(settings, path: Path) -> None:
    settings.setValue(SETTINGS_KEY, os.fspath(path))


def reset_selected_interpreter(settings) -> None:
    settings.remove(SETTINGS_KEY)


def dependency_declaration(
    directory: str | Path, packages: Mapping[str, str | None]
) -> DependencyDeclaration:
    project = Path(directory).expanduser()
    path = project / DECLARATION_NAME
    lines = [
        "# Managed by Sheet. This file is portable and contains only Sheet script dependencies.",
        "# Review and update it in your project; Sheet never installs it automatically.",
    ]
    for name in REQUIRED_PACKAGES:
        version = packages.get(name)
        if not version:
            raise ValueError(f"Cannot export a declaration without {name}.")
        lines.append(f"{name}=={version}")
    return DependencyDeclaration(path, "\n".join(lines) + "\n", path.exists())


def find_uv() -> Path | None:
    value = shutil.which("uv")
    return Path(value) if value else None


def uv_operation(
    uv: str | Path, directory: str | Path, declaration: DependencyDeclaration
) -> UvOperation:
    project = Path(directory).expanduser()
    target = project / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return UvOperation(
        (
            (os.fspath(uv), "venv", os.fspath(target)),
            (
                os.fspath(uv),
                "pip",
                "install",
                "--python",
                os.fspath(python),
                "-r",
                os.fspath(declaration.path),
            ),
        ),
        target,
    )


def command_preview(commands: Sequence[Sequence[str]]) -> str:
    """Represent argv losslessly rather than presenting a shell command."""
    return "\n".join(json.dumps(list(command)) for command in commands)


def run_uv_operation(
    operation: UvOperation, *, timeout: float = 120, run: Callable[..., object] = subprocess.run
) -> UvResult:
    logs: list[str] = []
    for command in operation.commands:
        try:
            completed = run(
                list(command), capture_output=True, text=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return UvResult(False, "\n".join([*logs, f"Timed out: {command_preview((command,))}"]))
        except OSError as error:
            return UvResult(False, "\n".join([*logs, f"Could not start uv: {error}"]))
        output = (
            (getattr(completed, "stdout", "") or "") + (getattr(completed, "stderr", "") or "")
        ).strip()
        logs.append(f"$ {command_preview((command,))}\n{output}".rstrip())
        if getattr(completed, "returncode", 1) != 0:
            return UvResult(False, "\n".join(logs))
    return UvResult(True, "\n".join(logs))
