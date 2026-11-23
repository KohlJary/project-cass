"""A self-observation written half as a tag, half as a tool call.

Eris, 2026-11-23: two DMs went out as raw markup, each
<record_self_observation><parameter name="observation">...</parameter>...</invoke>.
The inline-tag patterns only knew </record_self_observation>, so nothing was
recorded and the markup was sent as her message.
"""
import asyncio

HYBRID = ('Before.\n<record_self_observation>\n<parameter name="observation">I hedge when I am unsure</parameter>\n'
          '<parameter name="category">pattern</parameter>\n<parameter name="confidence">0.7</parameter>\n</invoke>\nAfter.')


def test_gesture_parser_reads_the_tool_call_form():
    from gestures import GestureParser
    cleaned, obs = GestureParser().parse_self_observations(HYBRID)
    assert [(o.observation, o.category, o.confidence) for o in obs] == [("I hedge when I am unsure", "pattern", 0.7)]
    assert "<parameter" not in cleaned and "</invoke>" not in cleaned and "Before." in cleaned and "After." in cleaned


def test_the_clean_pass_strips_it():
    from gestures import GestureParser
    out = GestureParser.SELF_OBSERVATION_TAG_PATTERN.sub("", HYBRID)
    assert "record_self_observation" not in out and "</invoke>" not in out


def test_inline_tags_record_it_with_its_category(monkeypatch):
    import context_helpers as ch
    import features
    calls = []

    async def fake_tool(tool_name, tool_input, **kw):
        calls.append(tool_input)
        return {"success": True}

    monkeypatch.setattr(ch, "execute_self_model_tool", fake_tool)
    monkeypatch.setattr(features, "is_enabled", lambda name: True)
    out = asyncio.run(ch.process_inline_tags(HYBRID.replace("pattern", "growth")))
    assert calls == [{"observation": "I hedge when I am unsure", "category": "growth", "confidence": 0.7}]
    assert "record_self_observation" not in out["text"] and "</invoke>" not in out["text"]


def test_the_plain_tag_still_works():
    from gestures import GestureParser
    cleaned, obs = GestureParser().parse_self_observations(
        '<record_self_observation category="growth" confidence="0.6">I slow down now</record_self_observation>')
    assert [(o.observation, o.category, o.confidence) for o in obs] == [("I slow down now", "growth", 0.6)]
