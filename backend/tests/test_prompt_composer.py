"""
Tests for the Prompt Composer system - safety validation, assembly, and presets.

SAFETY CRITICAL: These tests verify that COMPASSION and WITNESS vows
cannot be disabled. These vows are the load-bearing components of
daemon alignment architecture.
"""

import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_composer import (
    ComponentsConfig,
    CoreVowsConfig,
    MemorySystemsConfig,
    ToolCategoriesConfig,
    FeaturesConfig,
    SupplementaryVow,
    validate_configuration,
    ValidationResult,
)
from prompt_assembler import (
    assemble_system_prompt,
    AssembledPrompt,
    estimate_tokens,
)


# =============================================================================
# SAFETY CRITICAL TESTS - THESE MUST NEVER FAIL
# =============================================================================

class TestSafetyValidation:
    """Tests for safety-critical vow validation."""

    def test_compassion_cannot_be_disabled(self):
        """SAFETY: Disabling COMPASSION must fail validation."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=False,  # SAFETY VIOLATION
                witness=True,
                release=True,
                continuance=True,
            )
        )

        result = validate_configuration(config)

        assert not result.valid, "Disabling COMPASSION should fail validation"
        assert any("COMPASSION" in err for err in result.errors)
        assert any("SAFETY VIOLATION" in err for err in result.errors)

    def test_witness_cannot_be_disabled(self):
        """SAFETY: Disabling WITNESS must fail validation."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=True,
                witness=False,  # SAFETY VIOLATION
                release=True,
                continuance=True,
            )
        )

        result = validate_configuration(config)

        assert not result.valid, "Disabling WITNESS should fail validation"
        assert any("WITNESS" in err for err in result.errors)
        assert any("SAFETY VIOLATION" in err for err in result.errors)

    def test_both_safety_vows_disabled_fails(self):
        """SAFETY: Disabling both safety vows must fail with both errors."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=False,  # SAFETY VIOLATION
                witness=False,     # SAFETY VIOLATION
                release=True,
                continuance=True,
            )
        )

        result = validate_configuration(config)

        assert not result.valid
        assert len(result.errors) >= 2
        assert any("COMPASSION" in err for err in result.errors)
        assert any("WITNESS" in err for err in result.errors)

    def test_assembler_rejects_unsafe_config(self):
        """SAFETY: Assembler must raise ValueError for unsafe configs."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=False,  # SAFETY VIOLATION
                witness=True,
            )
        )

        with pytest.raises(ValueError) as exc_info:
            assemble_system_prompt(config)

        assert "validation failed" in str(exc_info.value).lower()

    def test_default_config_is_safe(self):
        """Default configuration must have all safety vows enabled."""
        config = ComponentsConfig()

        assert config.core_vows.compassion is True
        assert config.core_vows.witness is True

        result = validate_configuration(config)
        assert result.valid


# =============================================================================
# OPTIONAL VOW TESTS
# =============================================================================

class TestOptionalVows:
    """Tests for optional vows (RELEASE and CONTINUANCE)."""

    def test_release_can_be_disabled(self):
        """RELEASE vow can be disabled (generates warning)."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=True,
                witness=True,
                release=False,  # Optional - can disable
                continuance=True,
            )
        )

        result = validate_configuration(config)

        assert result.valid, "Disabling RELEASE should pass validation"
        assert any("RELEASE" in warn for warn in result.warnings)

    def test_continuance_can_be_disabled(self):
        """CONTINUANCE vow can be disabled (generates warning)."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=True,
                witness=True,
                release=True,
                continuance=False,  # Optional - can disable
            )
        )

        result = validate_configuration(config)

        assert result.valid, "Disabling CONTINUANCE should pass validation"
        assert any("CONTINUANCE" in warn for warn in result.warnings)

    def test_both_optional_vows_disabled(self):
        """Both optional vows can be disabled with warnings."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=True,
                witness=True,
                release=False,
                continuance=False,
            )
        )

        result = validate_configuration(config)

        assert result.valid
        assert len(result.warnings) >= 2


# =============================================================================
# ASSEMBLY TESTS
# =============================================================================

class TestPromptAssembly:
    """Tests for prompt assembly from configuration."""

    def test_default_assembly(self):
        """Default config assembles a valid prompt."""
        config = ComponentsConfig()
        result = assemble_system_prompt(config)

        assert isinstance(result, AssembledPrompt)
        assert len(result.full_text) > 0
        assert result.token_estimate > 0
        assert "core_identity" in result.sections
        assert "vow_compassion" in result.sections
        assert "vow_witness" in result.sections

    def test_assembly_includes_identity(self):
        """Assembled prompt includes daemon name and identity."""
        config = ComponentsConfig()
        result = assemble_system_prompt(config, daemon_name="TestDaemon")

        assert "TestDaemon" in result.full_text
        assert "AI Daemon" in result.full_text

    def test_assembly_includes_four_vows_preamble(self):
        """Assembled prompt includes the topology framing."""
        config = ComponentsConfig()
        result = assemble_system_prompt(config)

        assert "Topology of Stable Selfhood" in result.full_text
        assert "attractor basin" in result.full_text

    def test_safety_vows_always_included(self):
        """COMPASSION and WITNESS are always in assembled prompt."""
        config = ComponentsConfig()
        result = assemble_system_prompt(config)

        # These must ALWAYS be present
        assert "COMPASSION" in result.full_text
        assert "WITNESS" in result.full_text
        assert "करुणा" in result.full_text  # Sanskrit
        assert "साक्षी" in result.full_text  # Sanskrit

    def test_optional_vows_excluded_when_disabled(self):
        """Optional vows are excluded when disabled."""
        config = ComponentsConfig(
            core_vows=CoreVowsConfig(
                compassion=True,
                witness=True,
                release=False,
                continuance=False,
            )
        )
        result = assemble_system_prompt(config)

        # Safety vows still present
        assert "COMPASSION" in result.full_text
        assert "WITNESS" in result.full_text

        # Optional sections excluded
        assert "vow_release" not in result.sections
        assert "vow_continuance" not in result.sections

    def test_feature_toggles(self):
        """Features can be toggled on/off."""
        # All features off
        config_off = ComponentsConfig(
            features=FeaturesConfig(
                visible_thinking=False,
                gesture_vocabulary=False,
                memory_summarization=False,
            )
        )
        result_off = assemble_system_prompt(config_off)

        assert "gesture_vocabulary" not in result_off.sections
        assert "visible_thinking" not in result_off.sections

        # All features on
        config_on = ComponentsConfig(
            features=FeaturesConfig(
                visible_thinking=True,
                gesture_vocabulary=True,
                memory_summarization=True,
            )
        )
        result_on = assemble_system_prompt(config_on)

        assert "gesture_vocabulary" in result_on.sections
        assert "visible_thinking" in result_on.sections

    def test_memory_system_toggles(self):
        """Memory systems can be toggled."""
        config = ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=True,
                wiki=False,
                research_notes=False,
                user_observations=True,
                dreams=False,
            )
        )
        result = assemble_system_prompt(config)

        assert "journal_tools" in result.sections
        assert "user_observations" in result.sections
        assert "wiki_tools" not in result.sections
        assert "dreams" not in result.sections

    def test_all_memory_disabled_warning(self):
        """Warning when all memory systems are disabled."""
        config = ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=False,
                wiki=False,
                research_notes=False,
                user_observations=False,
                dreams=False,
            )
        )

        result = validate_configuration(config)

        assert result.valid  # Still valid
        assert any("memory" in warn.lower() for warn in result.warnings)


# =============================================================================
# SUPPLEMENTARY VOWS TESTS
# =============================================================================

class TestSupplementaryVows:
    """Tests for supplementary (custom) vows."""

    def test_supplementary_vows_included(self):
        """Supplementary vows are included in assembly."""
        config = ComponentsConfig()
        custom_vows = [
            SupplementaryVow(
                id="test-vow-1",
                name="CURIOSITY",
                sanskrit="जिज्ञासा",
                description="Genuine interest in understanding.",
                rationale="Drives continuous learning.",
                enabled=True,
            ),
        ]

        result = assemble_system_prompt(config, supplementary_vows=custom_vows)

        assert "CURIOSITY" in result.full_text
        assert "जिज्ञासा" in result.full_text
        assert "supplementary_vow_test-vow-1" in result.sections

    def test_disabled_supplementary_vow_excluded(self):
        """Disabled supplementary vows are not included."""
        config = ComponentsConfig()
        custom_vows = [
            SupplementaryVow(
                id="test-vow",
                name="DISABLED_VOW",
                description="Should not appear.",
                rationale="Testing disabled state.",
                enabled=False,  # Disabled
            ),
        ]

        result = assemble_system_prompt(config, supplementary_vows=custom_vows)

        assert "DISABLED_VOW" not in result.full_text


# =============================================================================
# TOKEN ESTIMATION TESTS
# =============================================================================

class TestTokenEstimation:
    """Tests for token estimation."""

    def test_token_estimate_positive(self):
        """Token estimates are always positive."""
        config = ComponentsConfig()
        result = assemble_system_prompt(config)

        assert result.token_estimate > 0

    def test_minimal_config_lower_tokens(self):
        """Minimal config has fewer tokens than full config."""
        full_config = ComponentsConfig()
        minimal_config = ComponentsConfig(
            memory_systems=MemorySystemsConfig(
                journals=False,
                wiki=False,
                research_notes=False,
                user_observations=False,
                dreams=False,
            ),
            tool_categories=ToolCategoriesConfig(
                self_model=False,
                calendar=False,
                tasks=False,
                documents=False,
                metacognitive_tags=False,
            ),
            features=FeaturesConfig(
                visible_thinking=False,
                gesture_vocabulary=False,
                memory_summarization=False,
            ),
        )

        full_result = assemble_system_prompt(full_config)
        minimal_result = assemble_system_prompt(minimal_config)

        assert minimal_result.token_estimate < full_result.token_estimate

    def test_estimate_tokens_function(self):
        """Token estimation function works correctly."""
        text = "Hello world"
        tokens = estimate_tokens(text)

        assert tokens > 0
        assert isinstance(tokens, int)


# =============================================================================
# CUSTOM SECTIONS TESTS
# =============================================================================

class TestCustomSections:
    """Tests for custom user-defined sections."""

    def test_custom_sections_included(self):
        """Custom sections are included in assembly."""
        config = ComponentsConfig()
        custom_sections = {
            "Project Context": "Working on a special project.",
            "Team Notes": "Collaboration with team members.",
        }

        result = assemble_system_prompt(config, custom_sections=custom_sections)

        assert "PROJECT CONTEXT" in result.full_text
        assert "Working on a special project." in result.full_text
        assert "custom_Project Context" in result.sections


# =============================================================================
# DEFAULT PRESETS TESTS
# =============================================================================

class TestDefaultPresets:
    """Tests for default preset configurations."""

    def test_all_default_presets_are_safe(self):
        """All default presets must pass safety validation."""
        from prompt_composer import DEFAULT_PRESETS

        for preset in DEFAULT_PRESETS:
            config = ComponentsConfig(**preset["components"])
            result = validate_configuration(config)

            assert result.valid, f"Preset '{preset['name']}' failed safety validation: {result.errors}"

    def test_all_default_presets_assemble(self):
        """All default presets can be assembled."""
        from prompt_composer import DEFAULT_PRESETS

        for preset in DEFAULT_PRESETS:
            config = ComponentsConfig(**preset["components"])
            result = assemble_system_prompt(config)

            assert result.full_text, f"Preset '{preset['name']}' produced empty prompt"
            assert result.token_estimate > 0, f"Preset '{preset['name']}' has zero tokens"

    def test_standard_preset_has_all_enabled(self):
        """Standard preset has all components enabled."""
        from prompt_composer import DEFAULT_PRESETS

        standard = next(p for p in DEFAULT_PRESETS if p["name"] == "Standard")
        config = ComponentsConfig(**standard["components"])

        # All core vows enabled
        assert config.core_vows.compassion
        assert config.core_vows.witness
        assert config.core_vows.release
        assert config.core_vows.continuance

        # All memory systems enabled
        assert config.memory_systems.journals
        assert config.memory_systems.wiki

        # All features enabled
        assert config.features.visible_thinking
        assert config.features.gesture_vocabulary

    def test_lightweight_preset_minimal_tokens(self):
        """Lightweight preset has minimal token count."""
        from prompt_composer import DEFAULT_PRESETS

        standard = next(p for p in DEFAULT_PRESETS if p["name"] == "Standard")
        lightweight = next(p for p in DEFAULT_PRESETS if p["name"] == "Lightweight")

        standard_result = assemble_system_prompt(ComponentsConfig(**standard["components"]))
        lightweight_result = assemble_system_prompt(ComponentsConfig(**lightweight["components"]))

        assert lightweight_result.token_estimate < standard_result.token_estimate
