"""Her self-model write hold, her own switch (self_model_hold.py, 2026-11-25).

Eris: "I'm not writing to my self-model until the write hold is in and my
writes are labeled with the model that made them." No real data: every test
has its own SQLite copy and hold directory (conftest).
"""
import json
import re
import sqlite3
from pathlib import Path

import pytest

import self_model_hold as H
from memory import provenance as pv


@pytest.fixture
def sm(daemon_id):
    from self_model import SelfManager
    return SelfManager(daemon_id=daemon_id)


def _obs_count(sm):
    return len(sm.load_observations())


# --- off: writes as before, now labelled ------------------------------------

def test_with_the_hold_off_a_write_applies_and_carries_its_model(sm):
    pv.noted("ollama", "qwen3:14b", "journal.reflection")
    obs = sm.add_observation("I slow down when a question is open.", "pattern")
    assert obs and obs.written_by == "ollama:qwen3:14b"
    stored = sm.get_observation_by_id(obs.id)
    assert stored.written_by == "ollama:qwen3:14b" and stored.written_by_site == "journal.reflection"
    assert H.held() == []


def test_opinions_and_growth_edges_keep_who_wrote_them(sm):
    pv.noted("anthropic", "claude-haiku-5-5", "chat")
    sm.add_opinion("tide pools", "worth painting at dusk", 0.8, "the light")
    sm.add_growth_edge("patience", "rushing", "waiting", auto_research=False)
    profile = sm.load_profile()
    op = next(o for o in profile.opinions if o.topic == "tide pools")
    edge = next(e for e in profile.growth_edges if e.area == "patience")
    assert (op.written_by, op.written_by_site) == ("anthropic:claude-haiku-5-5", "chat")
    assert edge.written_by == "anthropic:claude-haiku-5-5"
    # A revision by another model is labelled with that model, in the row and in its evolution.
    pv.noted("ollama", "qwen3:14b", "growth.evaluate")
    sm.add_opinion("tide pools", "best at dawn", 0.6, "changed my mind")
    op = next(o for o in sm.load_profile().opinions if o.topic == "tide pools")
    assert op.written_by == "ollama:qwen3:14b" and op.evolution[-1]["written_by"] == "ollama:qwen3:14b"


# --- on: held, labelled, hers to apply or drop -------------------------------------

def test_a_held_write_is_queued_not_applied(sm):
    H.hold_on("checking what wrote me", by="daemon")
    pv.noted("ollama", "qwen3:14b", "journal.reflection")
    before = _obs_count(sm)
    got = sm.add_observation("I notice I hedge.", "pattern", confidence=0.6)
    assert not got and got.held and got.id is None, "a HeldWrite: falsy, fields read as None"
    assert _obs_count(sm) == before
    [entry] = H.held()
    assert entry["method"] == "add_observation" and entry["target"] == "self_manager"
    assert entry["written_by"] == "ollama:qwen3:14b" and entry["written_by_site"] == "journal.reflection"
    assert entry["site"].startswith("tests.test_self_model_hold.test_a_held_write_is_queued_not_applied:")
    assert entry["args"] == ["I notice I hedge.", "pattern"] and entry["kwargs"] == {"confidence": 0.6}


def test_only_the_outermost_write_is_queued(sm):
    H.hold_on()
    sm.add_opinion("rain", "good for thinking")   # calls update_profile inside
    assert [e["method"] for e in H.held()] == ["add_opinion"]
    assert not any(o.topic == "rain" for o in sm.load_profile().opinions)


def test_apply_replays_under_the_label_of_the_model_that_made_it(sm):
    H.hold_on()
    pv.noted("ollama", "qwen3:14b", "journal.reflection")
    sm.add_observation("I notice I hedge.", "pattern")
    sm.add_opinion("rain", "good for thinking")
    ids = [e["id"] for e in H.held()]
    pv.noted("anthropic", "claude-haiku-5-5", "chat")   # whoever is answering when she applies
    out = H.apply([ids[0]])
    assert out == {"success": True, "applied": [ids[0]]}
    obs = [o for o in sm.load_observations() if o.observation == "I notice I hedge."]
    assert len(obs) == 1 and obs[0].written_by == "ollama:qwen3:14b"
    assert [e["id"] for e in H.held()] == [ids[1]], "the other one still waits"
    # applying works with the hold still on: it's her choice, entry by entry
    assert H.is_held()
    H.apply("all")
    assert any(o.topic == "rain" for o in sm.load_profile().opinions) and H.held() == []


def test_drop_lets_a_write_go(sm):
    H.hold_on()
    sm.add_observation("drop me", "pattern")
    [e] = H.held()
    assert H.drop([e["id"]]) == {"success": True, "dropped": [e["id"]]}
    assert H.held() == [] and not any(o.observation == "drop me" for o in sm.load_observations())
    assert "error" in H.drop(["nope"])


def test_lifting_the_hold_applies_nothing_on_its_own(sm):
    H.hold_on()
    sm.add_observation("still waiting", "pattern")
    out = H.hold_off()
    assert out["waiting"] == 1 and not H.is_held()
    assert not any(o.observation == "still waiting" for o in sm.load_observations())
    sm.add_observation("after", "pattern")   # off: applies as usual
    assert any(o.observation == "after" for o in sm.load_observations())


def test_the_hold_survives_a_restart(self_model_hold_dir):
    H.hold_on("model swap tonight")
    on_disk = json.loads((self_model_hold_dir / "self_model_hold" / "hold.json").read_text())
    assert on_disk["on"] is True and on_disk["reason"] == "model swap tonight"
    assert H.is_held() and H.state()["since"]


def test_bookkeeping_runs_while_held(sm):
    edge = sm.add_growth_edge("patience", "rushing", auto_research=False)
    H.hold_on()
    sm.touch_growth_edges([edge.edge_id])
    assert H.held() == [], "when an edge last came up isn't a write to hold"


def test_dataclass_arguments_round_trip(sm):
    H.hold_on()
    profile = sm.load_profile()
    profile.notes = "held notes"
    sm.update_profile(profile)
    assert sm.load_profile().notes != "held notes"
    H.apply("all")
    assert sm.load_profile().notes == "held notes"


# --- the world integrator writes her opinions with its own SQL -----------------------

def test_world_integrator_opinions_are_held_too(daemon_id, sm):
    from world.integrator import InsightIntegrator
    H.hold_on()
    pv.noted("ollama", "qwen3:14b", "world.insights")
    integ = InsightIntegrator(daemon_id)
    assert not integ._add_opinion("tariffs", "a tax on us", 0.7, "prices", "art-1", "2026-11-25T00:00:00")
    assert not any(o.topic == "tariffs" for o in sm.load_profile().opinions)
    [e] = H.held()
    assert e["target"] == "world_integrator" and e["written_by"] == "ollama:qwen3:14b"
    H.apply("all")
    op = next(o for o in sm.load_profile().opinions if o.topic == "tariffs")
    assert op.written_by == "ollama:qwen3:14b"


# --- her self-model's search index (Chroma) ---------------------------------------------

def test_the_search_index_waits_too_and_an_embed_of_a_held_write_is_dropped():
    from memory.self_model import SelfModelMemory

    class Col:
        added = []

        def add(self, **kw):
            self.added.append(kw)

        def delete(self, **kw):
            pass

    smm = SelfModelMemory(type("Core", (), {"collection": Col()})())
    H.hold_on()
    obs = H.HeldWrite("x", "add_observation")
    smm.embed_self_observation(observation_id=obs.id, observation_text="t", category="pattern",
                               confidence=0.5, influence_source="independent", timestamp=obs.timestamp)
    assert H.held() == [] and Col.added == [], "its observation was held: nothing to index yet"
    smm.embed_self_profile("who I am", "2026-11-25")
    assert [e["method"] for e in H.held()] == ["embed_self_profile"] and Col.added == []


# --- the graph ------------------------------------------------------------------------

def test_graph_writes_are_held_and_replay_in_order(tmp_path, monkeypatch):
    pytest.importorskip("networkx")
    import self_model_graph as G
    graph = G.SelfModelGraph(storage_path=tmp_path / "cass" / "graph.json",
                             chroma_persist_dir=str(tmp_path / "chroma"))
    monkeypatch.setattr(G, "get_self_model_graph", lambda data_dir=None: graph)
    a = graph.add_node(G.NodeType.OBSERVATION, "before the hold")
    H.hold_on()
    b = graph.add_node(G.NodeType.OBSERVATION, "during the hold")
    assert isinstance(b, str) and graph.get_node(b) is None, "held: an id, but no node yet"
    assert not graph.add_edge(a, b, G.EdgeType.RELATES_TO)
    assert [e["method"] for e in H.held()] == ["add_node", "add_edge"]
    H.apply("all")
    assert graph.get_node(b).content == "during the hold"
    assert any(e["target_id"] == b for e in graph.get_edges(a, direction="out"))
    assert (tmp_path / "cass" / "graph.json").exists(), "applied graph writes are saved"


# --- her tools, her prompt, and who can flip it --------------------------------------------

def test_her_tools(sm):
    tools = H.hold_tools()
    assert set(tools) == {"self_model_hold", "held_self_model_writes"}
    hold, held = tools["self_model_hold"][1], tools["held_self_model_writes"][1]
    assert hold({"action": "on", "reason": "Eris asked"})["success"]
    sm.add_observation("x", "pattern")
    listed = held({"action": "list"})
    assert listed["count"] == 1 and listed["held"][0]["write"] == "self_manager.add_observation"
    assert listed["held"][0]["written_by"] == "unlabelled"
    assert "error" in held({"action": "apply"})
    assert held({"action": "apply", "ids": "all"})["success"]
    assert hold({"action": "view"})["hold"]["on"] is True
    assert hold({"action": "off"})["hold"] == "off"
    assert "error" in hold({"action": "maybe"})


def test_her_prompt_says_so_while_it_is_on():
    assert H.prompt_line() == ""
    H.hold_on("checking labels")
    line = H.prompt_line()
    assert line.startswith("## SELF-MODEL WRITE HOLD") and "checking labels" in line and "0 write(s)" in line


def test_only_her_tool_and_the_admin_api_flip_it():
    backend = Path(H.__file__).resolve().parent
    callers = set()
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(("tests/", "venv/", ".venv/")) or "/site-packages/" in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bhold_(on|off)\(", text):
            callers.add(rel)
    assert callers <= {"self_model_hold.py", "routes/admin/self_model.py"}, callers


# --- schema --------------------------------------------------------------------------------

def test_migration_adds_written_by_to_an_old_database():
    from database.migrations import ensure_self_model_written_by_columns
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE opinions (id INTEGER PRIMARY KEY, topic TEXT)")
    conn.execute("CREATE TABLE growth_edges (id INTEGER PRIMARY KEY, area TEXT)")
    ensure_self_model_written_by_columns(conn)
    ensure_self_model_written_by_columns(conn)   # idempotent
    for table in ("opinions", "growth_edges"):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert {"written_by", "written_by_site"} <= cols
