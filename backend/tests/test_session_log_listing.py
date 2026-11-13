"""A session log saved with a null summary or start time is still listed
(found by the phase 6 comparison: 'NoneType' object is not subscriptable)."""
import json

import pytest


def test_logs_with_null_fields_are_listed(tmp_path):
    pytest.importorskip("anthropic")
    from session import GenericSessionRunner
    runner = GenericSessionRunner(data_dir=tmp_path, model="m")
    day = runner.logs_dir / "reflection" / "2026-11-13"
    day.mkdir(parents=True)
    (day / "a.json").write_text(json.dumps({"session_id": "a", "session_type": "reflection",
                                            "started_at": "2026-11-13T10:00:00", "summary": None}))
    (day / "b.json").write_text(json.dumps({"session_id": "b", "session_type": "reflection",
                                            "started_at": None, "summary": "short"}))
    logs = runner.list_session_logs(limit=10)
    assert {l["session_id"] for l in logs} == {"a", "b"}
    assert next(l for l in logs if l["session_id"] == "a")["summary"] == ""
