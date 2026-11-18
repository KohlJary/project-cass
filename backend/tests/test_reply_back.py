"""Reply back to where a session came from (agent_loop/reply_back.py): every
channel routes to its own sender, and the reply doesn't count as a step."""
import asyncio

from agent_loop import reply_back as RB


def test_every_channel_routes_to_its_sender():
    sent = []

    async def router(tool, inp):
        sent.append((tool, inp))
        return {"ok": True}
    cases = {
        "babelr_dm": ("@kohl", ("babelr_dm", {"person": "kohl", "content": "heard it"})),
        "babelr_channel": ("#general", ("babelr_post", {"channel": "general", "content": "heard it"})),
        "bluesky_dm": ("convo1", ("social_dm_send", {"platform": "bluesky", "to": "convo1", "text": "heard it"})),
        "bluesky_post": ("at://x", ("social_reply", {"platform": "bluesky", "to": "at://x", "text": "heard it"})),
        "chat": ("", ("reach_out", {"message": "heard it"})),
        "discord": ("123", ("discord_respond", {"channel_id": "123", "content": "heard it"})),
    }
    for channel, (target, want) in cases.items():
        o = RB.origin({"channel": channel, "target": target, "who": "Kohl"})
        assert o, channel
        asyncio.run(RB.handler(o, router)({"message": "heard it"}))
        assert sent[-1] == want, channel
    assert set(cases) == set(RB.CHANNELS)
    assert RB.origin({"channel": "babelr_dm"}) is None, "a DM needs someone to reply to"
    assert RB.origin({"channel": "smoke_signals", "target": "x"}) is None
    o = RB.origin({"channel": "babelr_dm", "target": "kohl", "who": "Kohl"})
    assert "Kohl asked in a DM with @kohl on Babelr" in RB.prompt_line(o)


def test_a_reply_doesnt_use_up_a_step(fake_llm, levers):
    from agent_loop import loop as L
    assert "reply_back" in L.FREE_TOOLS and L.FREE_REFUNDS >= 1


def test_a_start_session_origin_from_each_chat_place():
    """wakes.origin_of's raw form (the chat's channel and place) becomes a reply target."""
    dm = RB.origin({"channel": "babelr_dm", "where": "a Babelr DM", "who": "Kohl", "place": "DM with @kohl"})
    assert dm["channel"] == "babelr_dm" and dm["target"] == "kohl"
    room = RB.origin({"channel": "babelr", "who": "Kohl", "place": "#general"})
    assert room["channel"] == "babelr_channel" and room["target"] == "#general"
    disc = RB.origin({"channel": "discord", "who": "Kohl", "channel_id": "42"})
    assert disc["channel"] == "discord" and disc["target"] == "42"
    web = RB.origin({"channel": "websocket", "who": "Kohl", "conversation_id": "c1"})
    assert web["channel"] == "chat"
    assert RB.origin({"channel": "babelr", "who": "Kohl"}) is None, "a room with no name can't be replied to"
