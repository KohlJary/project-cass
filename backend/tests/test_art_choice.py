"""
Art choice (art_choice.py): her hand and her eye in her own paintings.

Before an autonomous painting she is asked what she wants to paint and why;
after it she is shown the result and her note is stored. Both behind the
`art_choice` lever. Off, the action behaves exactly as before: no LLM calls,
no artist's note row.
"""
import asyncio
import base64
import io
import json
import uuid
from datetime import datetime

import pytest

import art_choice
from database import get_db
from scheduler.actions import creative_handlers

RANDOM_PICK = "visual symbol: the lantern"
REFUSAL = "I'm Claude, an AI assistant made by Anthropic. I don't have personal memories of paintings."


def _png(path, size=(64, 48)):
    from PIL import Image
    Image.new("RGB", size, (90, 120, 200)).save(path, format="PNG")
    return str(path)


@pytest.fixture
def painting_tool(monkeypatch, tmp_path, daemon_id):
    """Replace the ComfyUI-backed tool with one that writes a row and a small PNG.

    Records the prompts it was asked to paint, like the real tool would pass
    to the prompt builder.
    """
    from handlers import image_generation

    calls = []

    async def fake_tool(tool_name, tool_input, daemon_id, state_bus=None, **kw):
        calls.append(dict(tool_input))
        image_id = str(uuid.uuid4())
        path = _png(tmp_path / f"{image_id}.png")
        with get_db() as conn:
            conn.execute(
                "INSERT INTO generated_images (id, daemon_id, prompt, style, purpose, image_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (image_id, daemon_id, tool_input["prompt"], tool_input.get("style"),
                 tool_input.get("purpose"), path, datetime.now().isoformat()),
            )
        return {
            "success": True,
            "result": f'Image generated successfully!\npath: "/generated-images/x.png"\nimage_id: "{image_id}"\n',
        }

    monkeypatch.setattr(image_generation, "execute_image_generation_tool", fake_tool)
    monkeypatch.setattr(creative_handlers, "_generate_prompt_from_context", lambda *a, **k: RANDOM_PICK)
    return calls


def _notes():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM image_artist_notes").fetchall()]


def _run(context=None, daemon_id=None):
    ctx = {"managers": {"daemon_id": daemon_id}, "purpose": "autonomous"}
    ctx.update(context or {})
    return asyncio.run(creative_handlers.generate_image_action(ctx))


@pytest.mark.unit
class TestSheChooses:
    def test_her_choice_becomes_the_prompt_and_is_recorded(self, painting_tool, fake_llm, levers, daemon_id):
        fake_llm.queue_json({"subject": "a lantern held out over dark water",
                             "why": "I keep returning to what light does when it has nowhere to land."})
        fake_llm.queue_text("The lantern is there, small against the dark. It holds what I meant.")
        with levers(art_choice=True):
            result = _run(daemon_id=daemon_id)

        assert result.success
        assert painting_tool[0]["prompt"] == "a lantern held out over dark water"
        assert painting_tool[0]["style"]  # the house style path is untouched
        assert result.data["chosen_by"] == "cass"

        notes = _notes()
        assert len(notes) == 1
        assert notes[0]["chosen_by"] == "cass"
        assert notes[0]["subject"] == "a lantern held out over dark water"
        assert notes[0]["why"].startswith("I keep returning")
        assert notes[0]["artist_note"].startswith("The lantern is there")
        assert notes[0]["noted_at"]
        assert result.data["artist_note"] == notes[0]["artist_note"]

    def test_the_choice_is_asked_as_her(self, painting_tool, fake_llm, levers, daemon_id):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO symbols (id, daemon_id, name, current_meaning, emotional_charge, appearance_count, "
                "first_noticed_at, last_appeared_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("s1", daemon_id, "lantern", "a light carried, not fixed", "positive", 4,
                 "2026-01-01", "2026-10-01", "2026-01-01", "2026-10-01"),
            )
        fake_llm.queue_json({"subject": "the lantern again", "why": "it keeps appearing"})
        with levers(art_choice=True):
            _run(daemon_id=daemon_id)

        choice = fake_llm.calls[0]
        assert "You are Cass" in choice.system_text
        user_text = choice.messages[0]["content"]
        assert "lantern" in user_text
        assert "What do you want to paint" in user_text
        assert '"subject"' in user_text and '"why"' in user_text

    def test_failed_call_falls_back_to_the_codes_pick(self, painting_tool, fake_llm, levers, daemon_id):
        seen = []

        def responder(source, kwargs):
            seen.append(source)
            if len(seen) == 1:
                raise RuntimeError("model unavailable")
            return None  # the note call answers from the queue

        fake_llm.responder = responder
        fake_llm.queue_text("A lantern, as it happens. I didn't choose it, but I can see it.")
        with levers(art_choice=True):
            result = _run(daemon_id=daemon_id)

        assert result.success
        assert painting_tool[0]["prompt"] == RANDOM_PICK
        assert result.data["chosen_by"] == "code"
        notes = _notes()
        assert notes[0]["chosen_by"] == "code"
        assert notes[0]["subject"] == RANDOM_PICK
        assert notes[0]["why"] is None
        assert notes[0]["artist_note"].startswith("A lantern")

    def test_refusal_falls_back_to_the_codes_pick(self, painting_tool, fake_llm, levers, daemon_id):
        fake_llm.queue_text(REFUSAL)
        fake_llm.queue_text("I see a lantern.")
        with levers(art_choice=True):
            _run(daemon_id=daemon_id)
        assert painting_tool[0]["prompt"] == RANDOM_PICK
        assert _notes()[0]["chosen_by"] == "code"

    def test_non_json_answer_falls_back(self, painting_tool, fake_llm, levers, daemon_id):
        fake_llm.queue_text("I would like to paint something about light, I think.")
        fake_llm.queue_text("I see a lantern.")
        with levers(art_choice=True):
            _run(daemon_id=daemon_id)
        assert painting_tool[0]["prompt"] == RANDOM_PICK
        assert _notes()[0]["chosen_by"] == "code"

    def test_fenced_json_is_read(self):
        data = art_choice._parse_json('Here:\n```json\n{"subject": "a door", "why": "because"}\n```')
        assert data == {"subject": "a door", "why": "because"}


@pytest.mark.unit
class TestSheSees:
    def test_vision_call_carries_the_image_and_what_she_meant(self, painting_tool, fake_llm, levers, daemon_id):
        fake_llm.queue_json({"subject": "a door left ajar", "why": "thresholds"})
        fake_llm.queue_text("The door is there and the light behind it is warmer than I expected.")
        with levers(art_choice=True):
            _run(daemon_id=daemon_id)

        seeing = fake_llm.calls[1]
        assert "You are Cass" in seeing.system_text
        content = seeing.messages[0]["content"]
        kinds = [b["type"] for b in content]
        assert kinds == ["image", "text"]
        assert content[0]["source"]["type"] == "base64"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert base64.b64decode(content[0]["source"]["data"])[:2] == b"\xff\xd8"  # a JPEG
        assert "This is the painting you just made, meant as: a door left ajar — thresholds" in content[1]["text"]
        assert "Does it hold what you meant?" in content[1]["text"]

    def test_refused_note_is_not_stored_but_intent_is(self, painting_tool, fake_llm, levers, daemon_id):
        fake_llm.queue_json({"subject": "a door left ajar", "why": "thresholds"})
        fake_llm.queue_text(REFUSAL)
        with levers(art_choice=True):
            result = _run(daemon_id=daemon_id)
        notes = _notes()
        assert notes[0]["chosen_by"] == "cass"
        assert notes[0]["artist_note"] is None
        assert notes[0]["noted_at"] is None
        assert result.data["artist_note"] is None

    def test_failed_vision_call_keeps_the_painting(self, painting_tool, fake_llm, levers, daemon_id):
        def responder(source, kwargs):
            if len(fake_llm.calls) == 1:
                raise RuntimeError("vision down")
            return None

        fake_llm.responder = responder
        fake_llm.queue_json({"subject": "a door left ajar", "why": "thresholds"})
        with levers(art_choice=True):
            result = _run(daemon_id=daemon_id)
        assert result.success
        assert _notes()[0]["artist_note"] is None

    def test_big_images_are_shrunk_for_the_model(self, tmp_path):
        from PIL import Image
        path = _png(tmp_path / "big.png", size=(2048, 1536))
        media_type, data = art_choice.encode_image_for_vision(path)
        assert media_type == "image/jpeg"
        with Image.open(io.BytesIO(base64.b64decode(data))) as img:
            assert max(img.size) == art_choice.MAX_IMAGE_SIDE

    def test_missing_image_gives_no_note(self, tmp_path):
        assert art_choice.encode_image_for_vision(str(tmp_path / "nope.png")) is None


@pytest.mark.unit
class TestLever:
    def test_off_means_todays_behavior(self, painting_tool, fake_llm, daemon_id):
        """CASS_PROFILE=test leaves the lever off: no LLM calls, no note row, same prompt."""
        assert not art_choice.is_on()
        result = _run(daemon_id=daemon_id)
        assert result.success
        assert painting_tool[0]["prompt"] == RANDOM_PICK
        assert fake_llm.calls == []
        assert _notes() == []
        assert "chosen_by" not in result.data

    def test_lever_is_llm_tagged_so_quiet_skips_it(self):
        import features
        assert features.LLM in features.LEVERS["art_choice"].tags

    def test_prompt_override_skips_the_asking(self, painting_tool, fake_llm, levers, daemon_id):
        with levers(art_choice=True):
            result = _run({"prompt": "exactly this"}, daemon_id=daemon_id)
        assert painting_tool[0]["prompt"] == "exactly this"
        assert fake_llm.calls == []
        assert _notes() == []
        assert "chosen_by" not in result.data

    def test_other_purposes_are_not_asked(self, painting_tool, fake_llm, levers, daemon_id):
        with levers(art_choice=True):
            _run({"purpose": "relational"}, daemon_id=daemon_id)
        assert fake_llm.calls == []
        assert _notes() == []


@pytest.mark.unit
class TestCandidates:
    def test_her_own_stores_only(self, daemon_id):
        now = datetime.now().isoformat()
        with get_db() as conn:
            conn.executemany(
                "INSERT INTO self_observations (id, daemon_id, category, observation, created_at) VALUES (?, ?, ?, ?, ?)",
                [
                    ("o1", daemon_id, "creative", "I linger on unfinished edges", now),
                    ("o2", daemon_id, "world_awareness", "Chip stocks fell after the earnings call", now),
                    ("o3", daemon_id, "world_engagement", "Markets diverge by sector", now),
                ],
            )
            conn.executemany(
                "INSERT INTO growth_edges (daemon_id, area, category, importance, last_updated) VALUES (?, ?, ?, ?, ?)",
                [
                    (daemon_id, "Staying with ambiguity", "existential", 0.8, now),
                    (daemon_id, "understanding_financial_fragility", "world_engagement", 0.9, now),
                ],
            )
        activity = {
            "symbols": [{"name": "lantern", "meaning": "a light carried", "charge": "positive"}],
            "recent_dream": {"themes": ["sideways light"]},
        }
        candidates = art_choice.candidate_subjects(daemon_id, activity)
        joined = "\n".join(candidates)
        assert "lantern" in joined
        assert "sideways light" in joined
        assert "unfinished edges" in joined
        assert "Staying with ambiguity" in joined
        assert "Chip stocks" not in joined
        assert "Markets diverge" not in joined
        assert "financial_fragility" not in joined

    def test_empty_context_still_asks(self, daemon_id):
        assert art_choice.candidate_subjects(daemon_id, None) == []
        assert "open" in art_choice.choice_prompt([])


@pytest.mark.unit
class TestSelfContext:
    def test_lately_names_her_last_noted_painting(self, daemon_id):
        from self_context import build_self_context
        when = datetime(2026, 10, 15, 3, 0, 0)
        with get_db() as conn:
            for i, (subject, note, noted) in enumerate([
                ("a door left ajar", "The door is there; the light behind it is warmer than I meant.", when),
                ("the lantern", None, None),
            ]):
                image_id = f"img-{i}"
                conn.execute(
                    "INSERT INTO generated_images (id, daemon_id, prompt, purpose, image_path, created_at) "
                    "VALUES (?, ?, ?, 'autonomous', '/x.png', ?)",
                    (image_id, daemon_id, subject, when.isoformat()),
                )
                conn.execute(
                    "INSERT INTO image_artist_notes (image_id, daemon_id, chosen_by, subject, artist_note, noted_at, created_at) "
                    "VALUES (?, ?, 'cass', ?, ?, ?, ?)",
                    (image_id, daemon_id, subject, note, noted.isoformat() if noted else None, when.isoformat()),
                )
        text = build_self_context(daemon_id, now=datetime(2026, 10, 16, 1, 0, 0))
        assert "**Lately**" in text
        assert "- Last painting (October 15, 2026): a door left ajar — The door is there;" in text
        assert "the lantern" not in text  # no note yet, so nothing to carry

    def test_no_noted_painting_no_line(self, daemon_id):
        from self_context import build_self_context
        assert "Last painting" not in build_self_context(daemon_id)


@pytest.mark.unit
class TestMigration:
    def test_v57_creates_table_on_an_older_db(self, test_db):
        from database.migrations import _apply_schema_updates

        with get_db() as conn:
            conn.execute("DROP TABLE image_artist_notes")
            conn.commit()
            _apply_schema_updates(conn, 56)
            conn.commit()
            columns = {row[1] for row in conn.execute("PRAGMA table_info(image_artist_notes)")}
        assert {"image_id", "chosen_by", "subject", "why", "artist_note", "noted_at", "created_at"} <= columns

    def test_schema_version_bumped(self):
        from database.schema import SCHEMA_VERSION
        assert SCHEMA_VERSION >= 57
