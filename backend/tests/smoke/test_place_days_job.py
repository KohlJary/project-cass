"""
Smoke: one cycle of the place_days job (lever `job_place_days`) against the
fake LLM: a house channel's day becomes her line, and it reaches her lately block.
"""
from datetime import datetime

import places
from database import get_daemon_id, get_db


def test_place_days_job_runs_one_cycle(fake_llm, levers, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO conversations (id, daemon_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                     ("conv-g", get_daemon_id(), "Babelr: #general", now, now))
        conn.execute("INSERT INTO messages (conversation_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                     ("conv-g", "user", "[Babelr #general] @jaryk: crazy day, huh", now))
        conn.commit()
    places.register("babelr", "channel:g", kind="channel", visibility="house",
                    conversation_id="conv-g", label="#general")
    fake_llm.queue_text("a loud, good day in #general.")

    import asyncio
    from features import is_enabled
    from scheduler.handlers import place_days_handler
    with levers(job_place_days=True):
        assert is_enabled("job_place_days")
        result = asyncio.run(place_days_handler())
    assert result.success, result.message
    assert len(result.data["written"]) == 1

    from lately import build_lately
    assert "in #general: a loud, good day" in build_lately(get_daemon_id(), data_dir=tmp_path)
