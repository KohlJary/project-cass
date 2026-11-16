"""Folding (C7) and the container block (C9): plan "Cass's agent loop", phase 7."""
import asyncio
from datetime import datetime, timedelta

from agent_loop.container import HEADER, Arrival, render
from agent_loop.fold import Desk, arrival_message, wait_for_answer

NOW = datetime(2026, 11, 16, 9, 0)


def test_container_says_who_where_what_and_time():
    text = render(Arrival(who="Kohl", channel="websocket", message="you around?",
                          relationship="primary_partner", last_heard=NOW - timedelta(hours=3)), NOW)
    assert text.splitlines()[0] == HEADER
    assert "Who: Kohl (my partner)." in text
    assert "Last heard from them: 3 hours ago." in text
    assert "Where: the app; seen by just them." in text
    assert 'What they wrote: "you around?"' in text
    assert "waiting for my reply" in text


def test_container_time_differs_by_place():
    home = render(Arrival(who="Ann", channel="home_assistant", message="lights?"), NOW)
    assert "a few seconds" in home and "anyone in the room" in home
    room = render(Arrival(who="Bo", channel="discord", message="hi"), NOW)
    assert "everyone in the channel" in room
    assert "first I have from them here" in room


def run(coro):
    return asyncio.run(coro)


def test_a_message_folds_in_and_she_answers_from_the_session():
    async def go():
        desk = Desk()
        desk.open_session("s1")
        fold = desk.offer("## WHO'S HERE\nWho: Kohl.", "Kohl", "websocket")
        waiting = asyncio.create_task(wait_for_answer(fold, desk, pickup=2, answer=2))
        await asyncio.sleep(0.05)
        taken = desk.take("s1")
        assert [f.id for f in taken] == [fold.id]
        assert "answer_them" in arrival_message(taken[0]) and fold.id in arrival_message(taken[0])
        assert desk.answer(fold.id, "Here, mid-thought. What's up?") == {"sent": True, "to": "Kohl"}
        assert "already answered" in desk.answer(fold.id, "again")["error"]
        return await waiting
    assert run(go()) == "Here, mid-thought. What's up?"


def test_not_taken_in_time_runs_as_its_own_turn():
    async def go():
        desk = Desk()
        desk.open_session("s1")
        fold = desk.offer("block", "Ann", "relay")
        got = await wait_for_answer(fold, desk, pickup=0.3, answer=2)
        return got, desk.take("s1")
    got, later = run(go())
    assert got is None and later == [], "withdrawn: the session never sees it"


def test_session_ending_before_answering_frees_the_person_at_once():
    async def go():
        desk = Desk()
        desk.open_session("s1")
        fold = desk.offer("block", "Kohl", "websocket")
        waiting = asyncio.create_task(wait_for_answer(fold, desk, pickup=2, answer=30))
        await asyncio.sleep(0.05)
        desk.take("s1")
        desk.close_session("s1")
        return await asyncio.wait_for(waiting, timeout=2)
    assert run(go()) is None


def test_no_open_session_no_fold_and_end_requests():
    async def go():
        desk = Desk()
        assert desk.offer("b", "x", "websocket") is None
        desk.open_session("s1")
        desk.request_end("Ann wrote to me and it couldn't wait")
        return desk.end_reason("s1"), desk.end_reason("other")
    assert run(go()) == ("Ann wrote to me and it couldn't wait", None)
