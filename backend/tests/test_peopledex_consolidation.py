"""
Epic #55: PeopleDex is the one store for what Cass knows about users.

- No runtime module writes the legacy user_observations table (static check).
- UserManager's observation/model methods read and write PeopleDex, and no
  longer write the per-user YAML files.
- scripts/migrate_legacy_users_to_peopledex.py: dry run writes nothing,
  --apply copies legacy rows and YAML into PeopleDex, a second --apply adds
  nothing, and the legacy rows and files are left in place.
"""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml

BACKEND = Path(__file__).resolve().parents[1]

# Code that runs in the daemon. scripts/ holds one-off migrations (including
# the PeopleDex one, which reads the legacy table) and tests/ is tests.
EXCLUDED_DIRS = {"tests", "scripts", "venv", ".venv", "node_modules", "__pycache__"}

LEGACY_WRITE = re.compile(
    r"\b(INSERT\s+(?:OR\s+\w+\s+)?INTO|REPLACE\s+INTO|UPDATE|DELETE\s+FROM)\s+user_observations\b",
    re.IGNORECASE,
)


def _runtime_modules():
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND)
        if EXCLUDED_DIRS.intersection(rel.parts):
            continue
        yield rel, path.read_text(errors="replace")


def test_no_runtime_writer_touches_user_observations():
    offenders = [
        f"{rel}:{text[:m.start()].count(chr(10)) + 1}"
        for rel, text in _runtime_modules()
        for m in LEGACY_WRITE.finditer(text)
    ]
    assert offenders == [], f"legacy user_observations writes: {offenders}"


def test_no_runtime_code_uses_legacy_observation_manager_or_yaml_writers():
    offenders = []
    for rel, text in _runtime_modules():
        if "UserObservationManager(" in text:
            offenders.append(f"{rel}: UserObservationManager")
        # save_user_model / save_relationship_model write the YAML files
        # nothing reads any more; only their definitions may mention them.
        for name in ("save_user_model(", "save_relationship_model("):
            calls = [m for m in re.finditer(re.escape(name), text)
                     if not text[max(0, m.start() - 4):m.start()].endswith("def ")]
            if calls:
                offenders.append(f"{rel}: {name}")
    assert offenders == []


def test_static_check_catches_a_writer():
    """The regex the guard relies on matches the forms the old code used."""
    for sql in ("INSERT INTO user_observations (id) VALUES (?)",
                "insert or ignore into user_observations",
                "UPDATE user_observations SET x = 1",
                "DELETE FROM user_observations WHERE id = ?"):
        assert LEGACY_WRITE.search(sql), sql
    assert not LEGACY_WRITE.search("SELECT * FROM user_observations")
    assert not LEGACY_WRITE.search("INSERT INTO peopledex_observations")


# --- UserManager over PeopleDex ----------------------------------------------

def _user(name="Robin"):
    from database import get_db
    user_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO users (id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                     (user_id, name, now, now))
    return user_id


def _count(sql, *params):
    from database import get_db
    with get_db() as conn:
        return conn.execute(sql, params).fetchone()[0]


@pytest.fixture
def manager(tmp_path):
    from users import UserManager
    return UserManager(storage_dir=str(tmp_path / "users"))


def test_add_observation_writes_peopledex_not_legacy(manager):
    user_id = _user()
    obs = manager.add_observation(user_id, "Likes tea", category="preference", confidence=0.6,
                                  source_journal_date="2026-10-20", source_type="journal")
    assert obs is not None and obs.category == "preference"
    assert _count("SELECT COUNT(*) FROM user_observations") == 0
    assert _count("SELECT COUNT(*) FROM peopledex_observations WHERE id = ? AND observation_type = 'general'",
                  obs.id) == 1

    [loaded] = manager.load_observations(user_id)
    assert (loaded.id, loaded.observation, loaded.category, loaded.source_journal_date) == \
        (obs.id, "Likes tea", "preference", "2026-10-20")
    assert manager.get_observations_by_category(user_id, "preference")[0].id == obs.id

    validated = manager.validate_observation(user_id, obs.id)
    assert validated.confidence == pytest.approx(0.65)
    assert validated.validation_count == 1

    assert manager.add_observation(str(uuid.uuid4()), "nobody") is None


def test_delete_observation_removes_it_for_good(manager):
    """#31: deleting used to be a no-op save; the observation came back."""
    me, other = _user("Me"), _user("Other")
    mine = manager.add_observation(me, "mine")
    theirs = manager.add_observation(other, "theirs")

    assert manager.delete_observation(me, theirs.id) is False  # not about me
    assert manager.delete_observation(me, mine.id) is True
    assert manager.load_observations(me) == []
    assert [o.id for o in manager.load_observations(other)] == [theirs.id]


def test_model_methods_write_peopledex_and_no_yaml(manager, tmp_path):
    user_id = _user()
    manager.add_identity_understanding(user_id, "Builds first, verifies after", confidence=0.8)
    manager.add_shared_moment(user_id, "First deploy", "it worked", category="milestone")
    manager.add_user_growth_observation(user_id, "patience", "Waits for tests now")
    c = manager.add_user_contradiction(user_id, "Wants speed", "Wants rigor")
    assert manager.add_open_question_about_user(user_id, "Why Godot?")
    assert manager.add_open_question_about_user(user_id, "Why Godot?")  # no duplicate
    manager.add_relational_pattern(user_id, "late nights", "Debugging after midnight")
    manager.add_relationship_shift(user_id, "Started building together", "user", "collaborator")
    manager.add_mutual_shaping_note(user_id, how_they_shape_me="Precision", how_i_shape_them="Patience")
    manager.add_inherited_value(user_id, "Witness what is present")
    manager.update_communication_style(user_id, style="direct", add_preference="no fluff")
    assert manager.resolve_user_contradiction(user_id, c.id, "both, by context").resolved

    assert not list((tmp_path / "users").rglob("*.yaml"))

    model = manager.load_user_model(user_id)
    assert [s.statement for s in model.identity_statements] == ["Builds first, verifies after"]
    assert [m.description for m in model.shared_history] == ["First deploy"]
    assert model.growth_observations[0].area == "patience"
    assert model.open_questions == ["Why Godot?"]
    assert model.contradictions[0].resolution == "both, by context"
    assert model.communication_style.style == "direct"
    assert model.communication_style.preferences == ["no fluff"]

    rel = manager.load_relationship_model(user_id)
    assert [p.name for p in rel.patterns] == ["late nights"]
    assert rel.significant_shifts[0].to_state == "collaborator"
    assert rel.current_phase == "collaborator"
    assert rel.how_they_shape_me == ["Precision"] and rel.how_i_shape_them == ["Patience"]
    assert rel.inherited_values == ["Witness what is present"]

    from peopledex import PeopleDexManager
    from database import get_daemon_id
    context = PeopleDexManager(get_daemon_id()).get_user_relational_context(user_id)
    assert "Builds first, verifies after" in context and "Why Godot?" in context


def test_general_observations_reach_the_prompt(manager):
    user_id = _user()
    manager.add_observation(user_id, "Collects fountain pens", category="interest")
    from peopledex import PeopleDexManager
    from database import get_daemon_id
    context = PeopleDexManager(get_daemon_id()).get_user_relational_context(user_id)
    assert "Collects fountain pens" in context


def test_relational_context_is_scoped_to_the_daemon(manager):
    """Another daemon's knowledge about the same person stays out of this
    daemon's prompt (all relational sections, not just observations)."""
    from database import get_daemon_id, get_or_create_daemon
    from peopledex import PeopleDexManager
    user_id = _user()
    cass, other = get_daemon_id(), get_or_create_daemon("solenne", name="Solenne")
    cass_pdx, other_pdx = PeopleDexManager(cass), PeopleDexManager(other)

    cass_pdx.add_observation_for_user(user_id, "general", "Cass noticed: likes rain")
    other_pdx.add_observation_for_user(user_id, "general", "Solenne noticed: likes snow")
    other_pdx.add_observation_for_user(user_id, "identity_statement", "Solenne thinks: a painter")
    other_pdx.add_moment_for_user(user_id, "Solenne's moment", significance="high")
    other_pdx.add_relationship_pattern_for_user(user_id, "pattern", "Solenne's pattern")
    other_pdx.add_mutual_shaping_for_user(user_id, "they_shape_me", "Solenne's shaping")

    cass_ctx = cass_pdx.get_user_relational_context(user_id)
    other_ctx = other_pdx.get_user_relational_context(user_id)
    assert "Cass noticed: likes rain" in cass_ctx
    assert "Solenne" not in cass_ctx
    assert "Solenne noticed: likes snow" in other_ctx and "Solenne's moment" in other_ctx
    assert "Cass noticed" not in other_ctx
    # No daemon to scope to: nothing relational is shown.
    assert PeopleDexManager().get_user_relational_context(user_id) == ""


def test_relational_context_clips_long_lines(manager):
    from database import get_daemon_id
    from peopledex import MAX_CONTEXT_LINE_CHARS, PeopleDexManager
    user_id = _user()
    manager.add_observation(user_id, "x" * 5000, category="interest")
    context = PeopleDexManager(get_daemon_id()).get_user_relational_context(user_id)
    longest = max(len(line) for line in context.splitlines())
    assert longest <= MAX_CONTEXT_LINE_CHARS + 2  # "- " prefix
    assert "x" * 100 in context and "…" in context


def test_resolve_user_by_display_name(manager):
    """list_users() keys ids as user_id; name lookup read "id" and always missed."""
    pytest.importorskip("networkx")  # the handlers package needs runtime deps CI's fast job lacks
    from handlers.metacognitive import _resolve_user
    sam = _user("Sam")
    assert _resolve_user(manager, "sam") == sam
    assert _resolve_user(manager, "nobody") is None


# --- migration script --------------------------------------------------------

def _seed_legacy(data_dir: Path, user_id: str, daemon_id: str):
    from database import get_db
    now = datetime.now().isoformat()
    with get_db() as conn:
        for i, (cat, text) in enumerate([("background", "Works in QA"),
                                         ("preference", "Prefers mornings"),
                                         ("value", "Honesty")]):
            conn.execute(
                "INSERT INTO user_observations (id, daemon_id, user_id, observation_type, content_json, "
                "confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"legacy-{i}", daemon_id, user_id, cat,
                 json.dumps({"observation": text, "source_type": "journal", "validation_count": 2}),
                 0.7, now))
    user_dir = data_dir / "users" / user_id
    user_dir.mkdir(parents=True)
    (user_dir / "user_model.yaml").write_text(yaml.safe_dump({
        "user_id": user_id,
        "identity_statements": [{"statement": "A careful tester", "confidence": 0.8}],
        "values": ["Honesty"],  # same text as a legacy row: kept once
        "communication_style": {"style": "terse", "preferences": ["bullets"]},
        "shared_history": [{"id": "m1", "timestamp": now, "description": "First bug found together",
                            "significance": "high", "category": "milestone"}],
        "open_questions": ["What do they test?"],
        "contradictions": [{"id": "c1", "timestamp": now, "aspect_a": "Calm", "aspect_b": "Rushed",
                            "resolved": False}],
        "relationship_type": "friend",
    }))
    (user_dir / "relationship_model.yaml").write_text(yaml.safe_dump({
        "user_id": user_id,
        "formation_date": now,
        "current_phase": "deepening",
        "patterns": [{"id": "p1", "name": "puns", "description": "Trades puns"}],
        "significant_shifts": [{"id": "s1", "timestamp": now, "description": "Became friends",
                                "from_state": "user", "to_state": "friend"}],
        "rituals": ["Friday retro"],
        "how_they_shape_me": ["Patience"],
        "inherited_values": ["Check twice"],
        "is_foundational": False,
    }))


def _pdx_counts():
    tables = ["peopledex_observations", "peopledex_moments", "peopledex_relationship_patterns",
              "peopledex_mutual_shaping", "peopledex_relationship_meta", "peopledex_entities"]
    return {t: _count(f"SELECT COUNT(*) FROM {t}") for t in tables}


def test_migration_dry_run_apply_idempotent(test_db, monkeypatch, capsys):
    import database.connection as connection
    from database import get_daemon_id
    from scripts.migrate_legacy_users_to_peopledex import main

    monkeypatch.setenv("DATA_DIR", str(test_db.parent))  # main() sets it too; restored after
    data_dir = test_db.parent
    user_id = _user("Tess")
    daemon_id = get_daemon_id()
    _seed_legacy(data_dir, user_id, daemon_id)
    connection.close_connection()  # let the script's own connection see committed rows

    before = _pdx_counts()
    assert main(["--data-dir", str(data_dir)]) == 0  # dry run
    assert "DRY RUN" in capsys.readouterr().out
    assert _pdx_counts() == before

    assert main(["--data-dir", str(data_dir), "--apply"]) == 0
    after = _pdx_counts()
    # 3 legacy rows + identity + communication style + open question +
    # contradiction ("Honesty" is already there from the legacy row)
    assert after["peopledex_observations"] - before["peopledex_observations"] == 7
    assert after["peopledex_moments"] - before["peopledex_moments"] == 1
    assert after["peopledex_relationship_patterns"] - before["peopledex_relationship_patterns"] == 3
    assert after["peopledex_mutual_shaping"] - before["peopledex_mutual_shaping"] == 2
    assert after["peopledex_relationship_meta"] - before["peopledex_relationship_meta"] == 1
    assert after["peopledex_entities"] - before["peopledex_entities"] == 1

    # Legacy ids are kept, so Chroma's user_observation_<id> docs still match.
    assert _count("SELECT COUNT(*) FROM peopledex_observations WHERE id LIKE 'legacy-%'") == 3

    capsys.readouterr()
    assert main(["--data-dir", str(data_dir), "--apply"]) == 0
    assert "to add:\n    nothing" in capsys.readouterr().out
    assert _pdx_counts() == after

    # Nothing legacy was removed.
    assert _count("SELECT COUNT(*) FROM user_observations") == 3
    assert (data_dir / "users" / user_id / "user_model.yaml").exists()
    assert (data_dir / "users" / user_id / "relationship_model.yaml").exists()

    # What the migration wrote reads back through the runtime view.
    from users import UserManager
    model = UserManager(storage_dir=str(data_dir / "users")).load_user_model(user_id)
    assert {s.statement for s in model.identity_statements} >= {"A careful tester", "Works in QA"}
    assert [m.description for m in model.shared_history] == ["First bug found together"]
