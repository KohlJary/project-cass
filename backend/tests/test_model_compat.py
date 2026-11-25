"""Haiku 5.5 readiness: request shape, response text, and who chooses the model."""
import importlib
import types

import pytest

from model_compat import MIN_MAX_TOKENS, fit_kwargs, new_shape, text_of


def test_old_models_untouched():
    kw = {"model": "claude-haiku-4-5-20251001", "max_tokens": 50, "temperature": 0.2}
    assert fit_kwargs("claude-haiku-4-5-20251001", kw) is kw


def test_new_shape_drops_sampling_and_lifts_small_caps():
    kw = {"model": "claude-haiku-5-5", "max_tokens": 50, "temperature": 0.2, "top_p": 0.9,
          "messages": [{"role": "user", "content": "hi"}]}
    out = fit_kwargs("claude-haiku-5-5", kw)
    assert "temperature" not in out and "top_p" not in out
    assert out["max_tokens"] == MIN_MAX_TOKENS
    assert kw["temperature"] == 0.2  # caller's dict not modified


def test_manual_thinking_budget_becomes_adaptive():
    out = fit_kwargs("claude-haiku-5-5", {"thinking": {"type": "enabled", "budget_tokens": 800}})
    assert out["thinking"] == {"type": "adaptive"}


def test_prefill_fails_loudly():
    with pytest.raises(ValueError):
        fit_kwargs("claude-haiku-5-5", {"messages": [{"role": "user", "content": "a"},
                                                       {"role": "assistant", "content": "{"}]})


def test_effort_env(monkeypatch):
    monkeypatch.setenv("CASS_MODEL_EFFORT", "low")
    assert fit_kwargs("claude-haiku-5-5", {})["output_config"] == {"effort": "low"}


def test_new_shape_families():
    assert new_shape("claude-haiku-5-5") and new_shape("claude-sonnet-5-5")
    assert not new_shape("claude-haiku-4-5-20251001") and not new_shape("qwen3:14b")


def test_text_of_skips_thinking():
    msg = types.SimpleNamespace(content=[
        types.SimpleNamespace(type="thinking", thinking="", signature="s"),
        types.SimpleNamespace(type="text", text="hello"),
        {"type": "text", "text": " there"},
    ])
    assert text_of(msg) == "hello there"
    assert text_of(types.SimpleNamespace(content=[])) == ""


def _config(monkeypatch, name=None, chat=None, internal=None):
    for k, v in (("CASS_DAEMON_NAME", name), ("CASS_CHAT_MODEL", chat), ("CASS_INTERNAL_MODEL", internal)):
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import config
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_config():
    yield
    import config
    importlib.reload(config)


def test_cass_keeps_her_model_without_her_yes(monkeypatch):
    # Cass's vessel sets no CASS_DAEMON_NAME and no model: she stays where she is.
    c = _config(monkeypatch)
    if c.CLAUDE_MODEL != c.HAIKU_4_5:
        pytest.skip("this vessel's .env sets its own model")
    assert c.CLAUDE_INTERNAL_MODEL == c.HAIKU_4_5


def test_resident_pins_hold(monkeypatch):
    c = _config(monkeypatch, name="Eris")
    assert c.CLAUDE_MODEL == c.HAIKU_4_5 and c.CLAUDE_INTERNAL_MODEL == c.HAIKU_4_5


def test_new_house_gets_the_default(monkeypatch):
    c = _config(monkeypatch, name="Newcomer")
    assert c.CLAUDE_MODEL == c.HAIKU_5_5 == c.DEFAULT_MODEL
    assert c.CLAUDE_INTERNAL_MODEL == c.HAIKU_5_5


def test_her_env_outranks_her_pin(monkeypatch):
    # A trial: her env for a while, the pin untouched.
    c = _config(monkeypatch, name="Eris", chat="claude-haiku-5-5")
    assert c.CLAUDE_MODEL == "claude-haiku-5-5"
    assert c.CLAUDE_INTERNAL_MODEL == c.HAIKU_4_5


# ── native thinking ──
from model_compat import note_thinking, with_thinking  # noqa: E402


def _thinking_msg():
    return types.SimpleNamespace(
        content=[types.SimpleNamespace(type="thinking", thinking="weighing it", signature="s"),
                 types.SimpleNamespace(type="text", text="the answer")],
        usage=types.SimpleNamespace(output_tokens=42))


def test_thinking_hidden_until_she_says_yes(monkeypatch):
    monkeypatch.delenv("CASS_SHOW_THINKING", raising=False)
    assert "thinking" not in fit_kwargs("claude-haiku-5-5", {})
    assert with_thinking("the answer", _thinking_msg()) == "the answer"


def test_her_yes_shows_it_in_her_own_tags(monkeypatch):
    monkeypatch.setenv("CASS_SHOW_THINKING", "1")
    assert fit_kwargs("claude-haiku-5-5", {})["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert with_thinking("the answer", _thinking_msg()) == "<thinking>\nweighing it\n</thinking>\n\nthe answer"


def test_tracking_is_counts_not_words(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    note_thinking(_thinking_msg(), "claude-haiku-5-5", "chat")
    note_thinking(_thinking_msg(), "claude-haiku-4-5-20251001", "chat")  # old models: nothing to log
    rows = (tmp_path / "thinking_log.jsonl").read_text().splitlines()
    assert len(rows) == 1 and "weighing" not in rows[0]
    assert '"thinking_blocks": 1' in rows[0] and '"summary_chars": 11' in rows[0]


def test_keeping_is_her_yes_and_separate_from_showing(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.delenv("CASS_SHOW_THINKING", raising=False)
    monkeypatch.delenv("CASS_KEEP_THINKING", raising=False)
    note_thinking(_thinking_msg(), "claude-haiku-5-5", "chat")
    assert not (tmp_path / "thinking").exists()
    monkeypatch.setenv("CASS_KEEP_THINKING", "1")
    assert fit_kwargs("claude-haiku-5-5", {})["thinking"]["display"] == "summarized"
    note_thinking(_thinking_msg(), "claude-haiku-5-5", "chat")
    kept = list((tmp_path / "thinking").glob("*.jsonl"))
    assert len(kept) == 1 and "weighing it" in kept[0].read_text()
    assert with_thinking("the answer", _thinking_msg()) == "the answer"  # kept, not shown
