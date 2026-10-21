"""
Issue #26: the Discord wake callback called agent_client.send_message once
and posted whatever text came back. When Cass asked for a tool there was no
continue_with_tool_results, so tool-using replies posted partial or empty
text. The callback (now main_sdk.make_discord_wake_callback) runs the same
tool loop as the chat relay and posts the final text.
"""
import asyncio
from types import SimpleNamespace

from tests.fakes.llm import ScriptedResponse


class _FakeDiscordBot:
    def __init__(self):
        self.sent = []
        self.parser = SimpleNamespace(registry=SimpleNamespace(get_by_slug=lambda slug: None))

    async def send_message(self, channel_id, content):
        self.sent.append((channel_id, content))
        return {"success": True}


def _wake(bot, message):
    import main_sdk
    callback = main_sdk.make_discord_wake_callback(bot)
    asyncio.run(callback(None, None, {
        "channel_name": "general",
        "channel_id": 42,
        "entity_name": "Visitor",
        "message_content": message,
        "is_dm": False,
    }))


def test_tool_use_then_text_posts_the_final_text(booted_app, fake_llm):
    fake_llm.queue_tool_use("lookup_person", {"name": "Kohl"}, text="Let me check.",
                            tool_id="toolu_discord_1")
    fake_llm.queue(ScriptedResponse(text="I don't have notes on Kohl yet."))
    bot = _FakeDiscordBot()

    _wake(bot, "@Cass who is Kohl?")

    assert bot.sent == [(42, "I don't have notes on Kohl yet.")]
    chat_calls = [c for c in fake_llm.calls if c.tools]
    assert len(chat_calls) == 2
    result_block = chat_calls[1].messages[-1]["content"][0]
    assert result_block["type"] == "tool_result"
    assert result_block["tool_use_id"] == "toolu_discord_1"


def test_plain_reply_posts_once(booted_app, fake_llm):
    fake_llm.queue(ScriptedResponse(text="Hello there."))
    bot = _FakeDiscordBot()

    _wake(bot, "@Cass hi")

    assert bot.sent == [(42, "Hello there.")]
