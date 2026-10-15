"""
/testing/rollback/execute (card 07 "Rollback manager"): restore extracted the
snapshot inside the directory it was restoring, failed with ENOENT, and left
data/testing (or, for FULL, the whole data/ dir) renamed to *_backup_<ts>.

These use a throwaway DATA_DIR laid out like the real one.
"""
import os
from pathlib import Path

import pytest

from testing.rollback import RollbackManager, RollbackStatus, SnapshotType


@pytest.fixture
def data_dir(tmp_path):
    data = tmp_path / "data"
    (data / "testing").mkdir(parents=True)
    (data / "self").mkdir()
    (data / "conversations").mkdir()
    (data / "testing" / "baseline.json").write_text("v1")
    (data / "self" / "identity.json").write_text("v1")
    (data / "conversations" / "c1.json").write_text("v1")
    (data / "cass.db").write_text("db-v1")
    return data


def _manager(data_dir):
    # Same wiring as main_sdk: storage under DATA_DIR/testing
    return RollbackManager(storage_dir=data_dir / "testing", data_dir=data_dir)


def _change_everything(data_dir):
    (data_dir / "testing" / "baseline.json").write_text("v2")
    (data_dir / "self" / "identity.json").write_text("v2")
    (data_dir / "self" / "new.json").write_text("added after snapshot")
    (data_dir / "conversations" / "c1.json").write_text("v2")
    (data_dir / "cass.db").write_text("db-v2")


def _leftovers(data_dir):
    """Backup/staging dirs a restore must not leave behind."""
    names = [p.name for p in data_dir.parent.rglob("*")]
    return [n for n in names if "_backup_" in n or "_restore_" in n or "_failed_" in n]


def test_cognitive_rollback_round_trips(data_dir):
    manager = _manager(data_dir)
    snapshot = manager.create_snapshot("before", snapshot_type=SnapshotType.COGNITIVE)
    _change_everything(data_dir)

    op = manager.rollback(snapshot.id, reason="test")

    assert op.status in (RollbackStatus.COMPLETED, RollbackStatus.VERIFIED), op.error_message
    assert (data_dir / "testing" / "baseline.json").read_text() == "v1"
    assert (data_dir / "self" / "identity.json").read_text() == "v1"
    assert not (data_dir / "self" / "new.json").exists()
    # Not part of a COGNITIVE snapshot: untouched
    assert (data_dir / "conversations" / "c1.json").read_text() == "v2"
    assert (data_dir / "cass.db").read_text() == "db-v2"
    assert _leftovers(data_dir) == []
    # The rollback store survived: the operation and pre-rollback snapshot are recorded
    assert manager.get_operation(op.id).status == op.status
    assert manager.get_snapshot(op.from_snapshot_id) is not None


def test_full_rollback_round_trips(data_dir):
    manager = _manager(data_dir)
    snapshot = manager.create_snapshot("before", snapshot_type=SnapshotType.FULL)
    _change_everything(data_dir)

    op = manager.rollback(snapshot.id, reason="test", capture_current=False)

    assert op.status in (RollbackStatus.COMPLETED, RollbackStatus.VERIFIED), op.error_message
    assert data_dir.is_dir()
    assert (data_dir / "cass.db").read_text() == "db-v1"
    assert (data_dir / "conversations" / "c1.json").read_text() == "v1"
    assert (data_dir / "self" / "identity.json").read_text() == "v1"
    assert _leftovers(data_dir) == []
    assert manager.get_operation(op.id).status == op.status


# Restore renames, in order: testing -> backup, staged testing -> testing,
# live rollback store -> restored testing, self -> backup, staged self -> self.
@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5])
def test_failed_rollback_leaves_data_intact(data_dir, monkeypatch, fail_at):
    manager = _manager(data_dir)
    snapshot = manager.create_snapshot("before", snapshot_type=SnapshotType.COGNITIVE)
    _change_everything(data_dir)
    before = {p.relative_to(data_dir): p.read_text()
              for p in data_dir.rglob("*") if p.is_file() and "rollback" not in p.parts}

    # Fail at each step of the swap in turn.
    real_rename = os.rename
    calls = {"n": 0}

    def flaky_rename(src, dst):
        calls["n"] += 1
        if calls["n"] == fail_at:
            raise OSError("disk on fire")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky_rename)
    op = manager.rollback(snapshot.id, reason="test", capture_current=False)
    monkeypatch.setattr(os, "rename", real_rename)

    assert op.status == RollbackStatus.FAILED
    assert "disk on fire" in op.error_message
    after = {p.relative_to(data_dir): p.read_text()
             for p in data_dir.rglob("*") if p.is_file() and "rollback" not in p.parts}
    assert after == before
    assert _leftovers(data_dir) == []
    # Operation log (inside data/testing) still readable and records the failure
    assert manager.get_operation(op.id).status == RollbackStatus.FAILED
