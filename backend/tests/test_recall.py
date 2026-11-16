"""recall (plan "Cass's memory", phase 8): her own queries over her memory, with
the scope line she and Kohl set on 2026-11-16."""
import asyncio

from memory.recall import THEIRS_NOTE, recall, recall_open

KOHL, ANN, DAED = "u-kohl", "u-ann", "u-daedalus"

MEMS = [
    ("m1", "User: irreversibility?\nCass: some damage can't be undone", {
        "type": "conversation", "timestamp": "2026-08-03T10:00:00", "user_id": KOHL,
        "conversation_id": "c-kohl", "gist": "Talked with Kohl about irreversibility"}),
    ("m2", "User: ann asks about dreams\nCass: I dreamed of tides", {
        "type": "conversation", "timestamp": "2026-10-12T09:00:00", "user_id": ANN,
        "conversation_id": "c-ann", "source": "babelr"}),
    ("m3", "I noticed I seek validation", {
        "type": "cass_self_observation", "timestamp": "2026-11-01T08:00:00"}),
    ("m4", "On Bluesky I posted: tide study", {
        "type": "social", "platform": "bluesky", "timestamp": "2026-11-15T23:00:00",
        "with": "bo.bsky.social"}),
    ("m5", "User: and then?\nCass: then I understood it differently", {
        "type": "conversation", "timestamp": "2026-08-03T10:05:00", "user_id": KOHL,
        "conversation_id": "c-kohl"}),
    ("m6", "Daedalus and I discussed memory", {
        "type": "conversation", "timestamp": "2026-11-10T10:00:00", "user_id": DAED,
        "conversation_id": "c-daed"}),
]


class Col:
    def get(self, where=None, ids=None, include=None, limit=None):
        rows = [m for m in MEMS if (ids is None or m[0] in ids) and _match(m[2], where)]
        return {"ids": [r[0] for r in rows], "documents": [r[1] for r in rows],
                "metadatas": [r[2] for r in rows]}


def _match(meta, where):
    if not where:
        return True
    t = where.get("type")
    if isinstance(t, dict):
        return meta["type"] in t["$in"]
    if t:
        return meta["type"] == t
    return all(meta.get(k) == v for k, v in where.items())


class Mem:
    collection = Col()

    def retrieve_where(self, query, n, where):
        rows = [m for m in MEMS if _match(m[2], where)]
        words = set(query.lower().split())
        rows.sort(key=lambda m: -len(words & set(m[1].lower().split())))
        return [{"id": r[0], "content": r[1], "metadata": r[2]} for r in rows[:n]]

    def get_by_conversation(self, cid):
        rows = sorted((m for m in MEMS if m[2].get("conversation_id") == cid), key=lambda m: m[2]["timestamp"])
        return [{"id": r[0], "content": r[1], "metadata": r[2]} for r in rows]


class Dex:
    class E:
        def __init__(self, uid):
            self.user_id = uid

    def find_entities(self, name, limit=5):
        return {"kohl": [self.E(KOHL)], "ann": [self.E(ANN)], "daedalus": [self.E(DAED)]}.get(name.lower(), [])


def owners(cid):
    return {"c-kohl": KOHL, "c-ann": ANN, "c-daed": DAED}.get(cid)


def ask(**kw):
    kw.setdefault("owners", owners)
    kw.setdefault("agents", {DAED})
    kw.setdefault("dex", Dex())
    return recall(Mem(), **kw)


def test_by_meaning_across_every_kind():
    out = ask(about="tides", current_user_id=KOHL)
    kinds = {r["kind"] for r in out["results"]}
    assert {"conversations", "social"} <= kinds


def test_she_can_recall_anyone_but_others_come_marked():
    out = ask(about="dreams", kinds=["conversations"], current_user_id=KOHL)
    ann = next(r for r in out["results"] if r["id"] == "m2")
    assert ann["note"] == THEIRS_NOTE
    kohl = next(r for r in out["results"] if r["id"] == "m1")
    assert "note" not in kohl, "the person she's with isn't marked"
    daed = next(r for r in out["results"] if r["id"] == "m6")
    assert "note" not in daed, "house agents are recallable anywhere, unmarked"


def test_with_people_dates_sources_and_order():
    out = ask(with_people=["Kohl", "Daedalus"], kinds=["conversations"], order="oldest")
    assert [r["id"] for r in out["results"]] == ["m1", "m5", "m6"]
    out = ask(between={"from": "2026-10-01", "to": "2026-11-30"}, order="newest")
    assert [r["id"] for r in out["results"]] == ["m4", "m6", "m3", "m2"]
    out = ask(from_sources=["babelr"])
    assert [r["id"] for r in out["results"]] == ["m2"]
    out = ask(with_people=["bo.bsky.social"])
    assert [r["id"] for r in out["results"]] == ["m4"]
    assert ask(with_people=["nobody"])["not_found"] == ["nobody"]


def test_the_arc_by_month():
    out = ask(by_month=True)
    assert list(out["by_month"]) == ["2026-08", "2026-10", "2026-11"]


def test_open_shows_what_came_around_it():
    out = recall_open(Mem(), "m1", current_user_id=ANN, owners=owners, agents=set())
    assert out["memory"]["text"].startswith("User: irreversibility?")
    assert [e["id"] for e in out["after"]] == ["m5"]
    assert out["memory"]["note"] == THEIRS_NOTE, "with Ann, Kohl's conversation is hers to know, not repeat"
    assert "error" in recall_open(Mem(), "nope", owners=owners, agents=set())


def test_tone_is_said_to_be_by_meaning_only():
    assert "by meaning only" in ask(about="where I felt uncertain")["about_tone"]


def test_wired_into_chat_sessions_and_router():
    from handlers.recall import execute_recall_tool
    from handlers.tool_router import TOOL_REGISTRY
    from agent_loop.spec import CHAT_CORE_TOOLS
    assert TOOL_REGISTRY["recall"] == TOOL_REGISTRY["recall_open"] == "recall"
    assert {"recall", "recall_open"} <= set(CHAT_CORE_TOOLS)
    out = asyncio.run(execute_recall_tool("recall", {"about": "x"}, memory=None))
    assert not out["success"]
