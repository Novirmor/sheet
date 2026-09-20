import sys
from pathlib import Path

from sheet.app import main
from sheet.smoke_test import run_smoke_test


def test_smoke_test_passes_with_an_external_probe_of_this_interpreter() -> None:
    assert run_smoke_test(interpreter=Path(sys.executable)) == 0


def test_smoke_test_fails_when_the_external_probe_fails(tmp_path: Path) -> None:
    assert run_smoke_test(interpreter=tmp_path / "missing-python") == 1


def test_cli_routes_the_smoke_test_before_any_gui(capsys) -> None:
    assert main(["--smoke-test"]) == 0

    reported = capsys.readouterr().out
    assert "PASS startup:" in reported
    assert "PASS persistent-session:" in reported
    assert "smoke checks passed" in reported
    assert "external-interpreter-probe" not in reported


def test_cli_smoke_test_accepts_an_external_interpreter(capsys) -> None:
    assert main(["--smoke-test", "--smoke-test-interpreter", sys.executable]) == 0

    assert "PASS external-interpreter-probe:" in capsys.readouterr().out
