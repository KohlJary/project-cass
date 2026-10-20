"""
The daily backup script and its retention (data_backup.prune).
"""
from datetime import datetime, timedelta
from zipfile import ZipFile

import pytest

import data_backup


def _touch_daily(out, when):
    path = data_backup.daily_backup_path(out, when)
    path.write_bytes(b"zip")
    return path


def test_prune_keeps_seven_days_and_four_weeks(tmp_path):
    start = datetime(2026, 10, 20, 4, 30)
    for days_ago in range(60):
        _touch_daily(tmp_path, start - timedelta(days=days_ago))
    _touch_daily(tmp_path, start - timedelta(hours=2))  # a second one today
    (tmp_path / "data-snapshot-2026-10-16-0105.zip").write_bytes(b"manual")

    deleted = data_backup.prune(tmp_path, keep_daily=7, keep_weekly=4)

    kept = sorted(p.name for p in tmp_path.iterdir() if data_backup.DAILY_NAME.match(p.name))
    days = [n[5:15] for n in kept]
    assert len(set(days)) == len(days) == 11  # one per day: 7 daily + 4 weekly
    assert days[-7:] == [(start - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(6, -1, -1)]
    weeks = {datetime.strptime(d, "%Y-%m-%d").isocalendar()[:2] for d in days[:4]}
    assert len(weeks) == 4
    # Today's newest is the one kept, and the manual snapshot is never touched
    assert data_backup.daily_backup_path(tmp_path, start).name in kept
    assert (tmp_path / "data-snapshot-2026-10-16-0105.zip").exists()
    assert len(deleted) == 61 - 11


def test_prune_with_few_backups_keeps_all(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for d in range(3):
        _touch_daily(out, datetime(2026, 10, 20) - timedelta(days=d))
    assert data_backup.prune(out) == []
    assert len(list(out.iterdir())) == 3


@pytest.fixture
def script(tmp_path, monkeypatch):
    from scripts import backup

    data = tmp_path / "data"
    (data / "wiki").mkdir(parents=True)
    (data / "wiki" / "page.md").write_text("hello")
    monkeypatch.setattr(backup, "DATA_DIR", data)
    return backup, data


def test_backup_script_writes_a_daily_zip_and_prunes(script, tmp_path):
    backup, _ = script
    out = tmp_path / "backups"
    out.mkdir()
    old = _touch_daily(out, datetime(2020, 1, 1))
    for d in range(1, 12):
        _touch_daily(out, datetime(2020, 1, 1) + timedelta(days=d * 7))

    assert backup.main(["--out", str(out), "--keep-daily", "1", "--keep-weekly", "0"]) == 0

    zips = [p for p in out.iterdir() if data_backup.DAILY_NAME.match(p.name)]
    assert len(zips) == 1 and not old.exists()
    with ZipFile(zips[0]) as zf:
        assert "wiki/page.md" in zf.namelist()


def test_backup_script_refuses_a_target_inside_the_data_dir(script):
    backup, data = script
    with pytest.raises(SystemExit):
        backup.main(["--out", str(data / "backups")])


def test_backup_script_needs_a_target(script, monkeypatch):
    backup, _ = script
    monkeypatch.delenv("CASS_BACKUP_DIR", raising=False)
    with pytest.raises(SystemExit):
        backup.main([])
