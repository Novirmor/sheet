import os

from sheet.app import configure_display, main, parse_args


def test_default_document_is_untitled() -> None:
    assert parse_args([]).file is None


def test_version_does_not_start_the_gui(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == "Sheet 0.1.0\n"


def test_existing_qt_platform_is_not_overridden(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    configure_display()
    assert os.environ["QT_QPA_PLATFORM"] == "offscreen"
