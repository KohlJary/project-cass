"""
Tests for tts.py - Text-to-Speech module.

Tests cover:
- Emote extraction
- Synthesis config selection
- Text cleaning for TTS
- Voice listing
- Model path utilities
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from tts import (
    extract_dominant_emote,
    get_synth_config,
    clean_text_for_tts,
    list_voices,
    _get_model_path,
    EMOTE_CONFIGS,
    DEFAULT_SYNTH_CONFIG,
    VOICES,
    DEFAULT_MODEL,
    MODELS_DIR
)


# ---------------------------------------------------------------------------
# Emote Extraction Tests
# ---------------------------------------------------------------------------

class TestExtractDominantEmote:
    """Tests for extract_dominant_emote."""

    def test_extract_happy_emote(self):
        """Should extract 'happy' from emote tag."""
        text = "<emote:happy> Hello there!"
        assert extract_dominant_emote(text) == "happy"

    def test_extract_excited_emote(self):
        """Should extract 'excited' from emote tag."""
        text = "I'm <emote:excited> so thrilled!"
        assert extract_dominant_emote(text) == "excited"

    def test_extract_concern_emote(self):
        """Should extract 'concern' from emote tag."""
        text = "<emote:concern> That's worrying..."
        assert extract_dominant_emote(text) == "concern"

    def test_extract_thinking_emote(self):
        """Should extract 'thinking' from emote tag."""
        text = "<emote:thinking> Let me consider..."
        assert extract_dominant_emote(text) == "thinking"

    def test_extract_love_emote(self):
        """Should extract 'love' from emote tag."""
        text = "<emote:love> I appreciate you"
        assert extract_dominant_emote(text) == "love"

    def test_extract_surprised_emote(self):
        """Should extract 'surprised' from emote tag."""
        text = "<emote:surprised> Oh wow!"
        assert extract_dominant_emote(text) == "surprised"

    def test_extract_emote_with_params(self):
        """Should extract emote even with additional parameters."""
        text = "<emote:happy:intensity=high> Great news!"
        assert extract_dominant_emote(text) == "happy"

    def test_no_emote_returns_none(self):
        """Should return None when no emote present."""
        text = "Just a plain message"
        assert extract_dominant_emote(text) is None

    def test_unknown_emote_returns_none(self):
        """Should return None for unrecognized emote."""
        text = "<emote:angry> Grr!"
        assert extract_dominant_emote(text) is None

    def test_first_emote_wins(self):
        """Should return the first emote found."""
        text = "<emote:happy> First <emote:excited> Second"
        assert extract_dominant_emote(text) == "happy"


# ---------------------------------------------------------------------------
# Synthesis Config Tests
# ---------------------------------------------------------------------------

class TestGetSynthConfig:
    """Tests for get_synth_config."""

    def test_get_happy_config(self):
        """Should return happy synthesis config."""
        config = get_synth_config("happy")
        assert config == EMOTE_CONFIGS["happy"]
        assert config.length_scale == 0.95

    def test_get_excited_config(self):
        """Excited config should be faster."""
        config = get_synth_config("excited")
        assert config.length_scale == 0.85  # Faster

    def test_get_thinking_config(self):
        """Thinking config should be slower."""
        config = get_synth_config("thinking")
        assert config.length_scale == 1.15  # Slower

    def test_get_default_config(self):
        """Should return default config for None."""
        config = get_synth_config(None)
        assert config == DEFAULT_SYNTH_CONFIG

    def test_get_default_for_unknown(self):
        """Should return default config for unknown emote."""
        config = get_synth_config("angry")
        assert config == DEFAULT_SYNTH_CONFIG

    def test_all_emote_configs_exist(self):
        """All known emotes should have configs."""
        expected_emotes = ["happy", "excited", "concern", "thinking", "love", "surprised"]
        for emote in expected_emotes:
            assert emote in EMOTE_CONFIGS


# ---------------------------------------------------------------------------
# Text Cleaning Tests
# ---------------------------------------------------------------------------

class TestCleanTextForTts:
    """Tests for clean_text_for_tts."""

    def test_remove_gesture_tags(self):
        """Should remove gesture tags."""
        text = "<gesture:wave> Hello there!"
        result = clean_text_for_tts(text)
        assert "<gesture" not in result
        assert "Hello there!" in result

    def test_remove_emote_tags(self):
        """Should remove emote tags."""
        text = "<emote:happy> I'm glad!"
        result = clean_text_for_tts(text)
        assert "<emote" not in result
        assert "I'm glad!" in result

    def test_remove_memory_tags(self):
        """Should remove memory tags."""
        text = "<memory:recall> Remember this?"
        result = clean_text_for_tts(text)
        assert "<memory" not in result

    def test_remove_code_blocks(self):
        """Should replace code blocks with placeholder."""
        text = "Here's code:\n```python\nprint('hello')\n```\nThat's it."
        result = clean_text_for_tts(text)
        assert "```" not in result
        assert "[code block]" in result

    def test_remove_inline_code(self):
        """Should remove inline code."""
        text = "Use the `print()` function"
        result = clean_text_for_tts(text)
        assert "`" not in result

    def test_preserve_link_text(self):
        """Should keep link text, remove URL."""
        text = "Check out [the docs](https://example.com) here"
        result = clean_text_for_tts(text)
        assert "the docs" in result
        assert "https://" not in result

    def test_remove_markdown_bold(self):
        """Should remove bold/italic markers."""
        text = "This is **bold** and *italic*"
        result = clean_text_for_tts(text)
        assert "**" not in result
        assert "*" not in result
        assert "bold" in result
        assert "italic" in result

    def test_remove_headers(self):
        """Should remove markdown headers."""
        text = "## Header\nContent here"
        result = clean_text_for_tts(text)
        assert "##" not in result
        assert "Header" in result

    def test_remove_bullet_points(self):
        """Should remove bullet markers."""
        text = "- Item one\n- Item two"
        result = clean_text_for_tts(text)
        # Bullets removed, content preserved
        assert "Item one" in result
        assert "Item two" in result

    def test_convert_ellipsis_to_pause(self):
        """Should convert ... to pause markers."""
        text = "Hmm... let me think"
        result = clean_text_for_tts(text)
        assert ". . ." in result

    def test_convert_unicode_ellipsis(self):
        """Should handle unicode ellipsis."""
        text = "Well… that's interesting"
        result = clean_text_for_tts(text)
        assert "…" not in result

    def test_convert_em_dash(self):
        """Should convert em-dash to comma pause."""
        text = "One thing — another thing"
        result = clean_text_for_tts(text)
        assert "—" not in result
        assert "," in result

    def test_normalize_whitespace(self):
        """Should collapse multiple whitespace."""
        text = "Too    many     spaces"
        result = clean_text_for_tts(text)
        assert "  " not in result

    def test_empty_after_cleaning(self):
        """Should handle text that becomes empty."""
        text = "<gesture:wave><emote:happy>"
        result = clean_text_for_tts(text)
        assert result == ""


# ---------------------------------------------------------------------------
# Voice Utilities Tests
# ---------------------------------------------------------------------------

class TestVoiceUtilities:
    """Tests for voice-related utilities."""

    def test_list_voices(self):
        """list_voices should return available voices."""
        voices = list_voices()
        assert "amy" in voices
        assert voices["amy"] == "en_US-amy-medium"

    def test_list_voices_returns_copy(self):
        """list_voices should return a copy, not the original."""
        voices = list_voices()
        voices["test"] = "test-value"
        assert "test" not in VOICES

    def test_get_model_path(self):
        """_get_model_path should construct correct path."""
        path = _get_model_path("en_US-amy-medium")
        assert path == MODELS_DIR / "en_US-amy-medium.onnx"

    def test_default_model_exists(self):
        """DEFAULT_MODEL should be defined."""
        assert DEFAULT_MODEL == "en_US-amy-medium"


# ---------------------------------------------------------------------------
# Text to Speech Integration Tests (Mocked)
# ---------------------------------------------------------------------------

class TestTextToSpeechMocked:
    """Mocked tests for text_to_speech."""

    def test_text_to_speech_empty_returns_empty(self):
        """Should return empty bytes for empty text after cleaning."""
        from tts import text_to_speech

        # This would require mocking the voice loading
        # For now, test the cleaning behavior
        text = "<gesture:wave>"
        clean = clean_text_for_tts(text)
        assert clean == ""

    def test_emote_extracted_for_synthesis(self):
        """Emote should be extracted when not explicitly provided."""
        text = "<emote:excited> Great news!"
        emote = extract_dominant_emote(text)
        config = get_synth_config(emote)

        assert emote == "excited"
        assert config.length_scale == 0.85


# ---------------------------------------------------------------------------
# Emote Config Values Tests
# ---------------------------------------------------------------------------

class TestEmoteConfigValues:
    """Tests for emote config parameter values."""

    def test_happy_is_slightly_faster(self):
        """Happy should be slightly faster than default."""
        assert EMOTE_CONFIGS["happy"].length_scale < DEFAULT_SYNTH_CONFIG.length_scale

    def test_excited_is_fastest(self):
        """Excited should be the fastest emote."""
        excited_scale = EMOTE_CONFIGS["excited"].length_scale
        for emote, config in EMOTE_CONFIGS.items():
            if emote != "excited":
                assert excited_scale <= config.length_scale

    def test_thinking_is_slowest(self):
        """Thinking should be one of the slowest emotes."""
        assert EMOTE_CONFIGS["thinking"].length_scale > DEFAULT_SYNTH_CONFIG.length_scale

    def test_concern_is_slower(self):
        """Concern should be slower than default."""
        assert EMOTE_CONFIGS["concern"].length_scale > DEFAULT_SYNTH_CONFIG.length_scale

    def test_surprised_has_high_variation(self):
        """Surprised should have high noise_scale for expressiveness."""
        assert EMOTE_CONFIGS["surprised"].noise_scale >= 0.9
