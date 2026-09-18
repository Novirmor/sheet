from sheet.workbook_storage import (
    discard_snapshot,
    read_recovery,
    user_recovery_directory,
    write_snapshot,
)


def test_recovery_directory_uses_platform_state_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert user_recovery_directory() == tmp_path / "Sheet" / "recovery"


def test_snapshot_round_trip_and_cleanup(tmp_path) -> None:
    path = tmp_path / "snapshot.sheet"
    write_snapshot(path, rows=2, columns=3, cells={(1, 2): "value"}, formats={}, scripts={})

    assert read_recovery(path) is not None
    discard_snapshot(path)
    assert not path.exists()
