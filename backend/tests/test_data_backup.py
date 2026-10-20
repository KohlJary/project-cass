"""
The daily backup script and its retention (data_backup.prune).
"""
from datetime import datetime, timedelta
from zipfile import ZipFile

import os
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

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
    db = sqlite3.connect(data / "cass.db")
    db.execute("CREATE TABLE t (v)")
    db.commit()
    db.close()
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


def test_prune_ignores_impossible_dates_and_directories(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for d in range(10):
        _touch_daily(out, datetime(2026, 10, 20) - timedelta(days=d))
    (out / "cass-2020-13-45-0430.zip").write_bytes(b"x")
    (out / "cass-2020-01-01-0430.zip").mkdir()
    data_backup.prune(out, keep_daily=2, keep_weekly=0)
    assert (out / "cass-2020-13-45-0430.zip").exists()
    assert (out / "cass-2020-01-01-0430.zip").is_dir()


def test_prune_refuses_to_keep_nothing(tmp_path):
    with pytest.raises(ValueError):
        data_backup.prune(tmp_path, keep_daily=0, keep_weekly=0)


def test_weekly_keepers_are_weeks_the_daily_ones_dont_cover(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    start = datetime(2026, 10, 21, 4, 30)  # a Wednesday
    for d in range(60):
        _touch_daily(out, start - timedelta(days=d))
    data_backup.prune(out, keep_daily=7, keep_weekly=4)
    days = sorted(datetime.strptime(p.name[5:15], "%Y-%m-%d") for p in out.iterdir())
    daily_weeks = {d.isocalendar()[:2] for d in days[-7:]}
    weekly_weeks = {d.isocalendar()[:2] for d in days[:-7]}
    assert len(weekly_weeks) == 4 and not (weekly_weeks & daily_weeks)


def test_symlink_in_data_dir_to_the_backup_folder_is_not_backed_up(script, tmp_path):
    backup, data = script
    out = tmp_path / "outs"
    out.mkdir()
    (data / "escape").symlink_to(out, target_is_directory=True)
    assert backup.main(["--out", str(out)]) == 0
    first = next(out.glob("cass-*.zip"))
    first.rename(out / "cass-2020-01-01-0000.zip")
    assert backup.main(["--out", str(out), "--keep-daily", "5"]) == 0
    newest = max(out.glob("cass-*.zip"), key=lambda p: p.name)
    with ZipFile(newest) as zf:
        assert not any(n.startswith("escape/") for n in zf.namelist())


def test_script_refuses_a_data_dir_without_her_database(script, tmp_path):
    backup, data = script
    (data / "cass.db").unlink()
    out = tmp_path / "out"
    assert backup.main(["--out", str(out)]) == 1
    assert not out.exists() or list(out.iterdir()) == []


def test_script_sweeps_stale_partials(script, tmp_path):
    backup, _ = script
    out = tmp_path / "out"
    out.mkdir()
    (out / "cass-2026-10-19-0430.zip.partial").write_bytes(b"half")
    assert backup.main(["--out", str(out)]) == 0
    assert list(out.glob("*.partial")) == []


def test_sigterm_mid_backup_leaves_no_partial(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    sqlite3.connect(data / "cass.db").execute("CREATE TABLE t (v)").connection.commit()
    with open(data / "big.bin", "wb") as f:
        f.write(os.urandom(400 * 1024 * 1024))
    out = tmp_path / "out"
    backend = Path(__file__).resolve().parent.parent
    env = dict(os.environ, DATA_DIR=str(data))
    proc = subprocess.Popen([sys.executable, "scripts/backup.py", "--out", str(out)], cwd=backend, env=env)
    deadline = time.time() + 30
    while not list(out.glob("*.partial")) if out.exists() else True:
        assert time.time() < deadline and proc.poll() is None, "backup never started writing"
        time.sleep(0.02)
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=30)
    assert proc.returncode != 0
    assert list(out.iterdir()) == []
