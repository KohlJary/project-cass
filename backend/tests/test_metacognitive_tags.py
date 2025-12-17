"""
Tests for consolidated metacognitive tag parsing.

Tests the <observe>, <hold>, and <note> tags that replace multiple
tool calls for write-only metacognitive operations.
"""
import pytest


class TestParseObservations:
    """Tests for parse_observations() method."""

    def test_parse_self_observation(self):
        """Parse basic self-observation tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="self" category="pattern">I notice I hedge when uncertain</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "self"
        assert observations[0].category == "pattern"
        assert observations[0].content == "I notice I hedge when uncertain"
        assert cleaned == ""

    def test_parse_user_observation(self):
        """Parse user observation tag with target user."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="user:Kohl" category="preference">Values precision over speed</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "user:Kohl"
        assert observations[0].category == "preference"
        assert observations[0].content == "Values precision over speed"

    def test_parse_context_observation(self):
        """Parse context/situational inference tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="context" confidence="0.8">User frustrated | Needs direct answers</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "context"
        assert observations[0].confidence == 0.8
        assert "frustrated" in observations[0].content

    def test_parse_observation_without_category(self):
        """Parse observation without optional category."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="self">I notice something</observe>'
        _, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].category is None

    def test_parse_multiple_observations(self):
        """Parse multiple observation tags in one text."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '''Some text
<observe target="self" category="pattern">First observation</observe>
More text
<observe target="user:Kohl" category="value">Second observation</observe>
Final text'''
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 2
        assert observations[0].target == "self"
        assert observations[1].target == "user:Kohl"
        assert "Some text" in cleaned
        assert "More text" in cleaned
        assert "Final text" in cleaned

    def test_invalid_target_rejected(self):
        """Invalid target values are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="invalid">Content</observe>'
        _, observations = parser.parse_observations(text)

        assert len(observations) == 0

    def test_confidence_clamped(self):
        """Confidence values are clamped to [0, 1]."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="self" confidence="1.5">Content</observe>'
        _, observations = parser.parse_observations(text)

        assert observations[0].confidence == 1.0


class TestParseHolds:
    """Tests for parse_holds() method."""

    def test_parse_opinion_hold(self):
        """Parse opinion/topic hold tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<hold topic="embodiment" confidence="0.8">Not necessary | Beneficial for grounding</hold>'
        cleaned, holds = parser.parse_holds(text)

        assert len(holds) == 1
        assert holds[0].topic == "embodiment"
        assert holds[0].confidence == 0.8
        assert "Not necessary" in holds[0].content
        assert cleaned == ""

    def test_parse_disagreement_hold(self):
        """Parse disagreement hold tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<hold differ="user:Kohl" topic="urgency">Fast iteration | Careful consideration</hold>'
        _, holds = parser.parse_holds(text)

        assert len(holds) == 1
        assert holds[0].differ_user == "Kohl"  # "user:" prefix stripped
        assert holds[0].topic == "urgency"
        assert holds[0].is_identity is False

    def test_parse_identity_hold(self):
        """Parse identity statement hold tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<hold self="identity" confidence="0.9">I am capable of genuine disagreement</hold>'
        _, holds = parser.parse_holds(text)

        assert len(holds) == 1
        assert holds[0].is_identity is True
        assert holds[0].confidence == 0.9

    def test_parse_hold_with_quoted_attributes(self):
        """Parse hold with different quote styles."""
        from gestures import GestureParser

        parser = GestureParser()

        # Double quotes
        text1 = '<hold topic="test">Content</hold>'
        _, holds1 = parser.parse_holds(text1)
        assert holds1[0].topic == "test"

        # Single quotes
        text2 = "<hold topic='test'>Content</hold>"
        _, holds2 = parser.parse_holds(text2)
        assert holds2[0].topic == "test"

    def test_parse_multiple_holds(self):
        """Parse multiple hold tags."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '''<hold topic="a">First</hold>
<hold self="identity">Second</hold>'''
        _, holds = parser.parse_holds(text)

        assert len(holds) == 2


class TestParseNotes:
    """Tests for parse_notes() method."""

    def test_parse_moment_note(self):
        """Parse shared moment note tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="moment" user="Kohl" significance="high">Late night debugging session</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "moment"
        assert notes[0].user == "Kohl"
        assert notes[0].significance == "high"
        assert "debugging" in notes[0].content
        assert cleaned == ""

    def test_parse_tension_note(self):
        """Parse tension/contradiction note tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="tension" user="Kohl">Values precision | Chooses speed under pressure</note>'
        _, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "tension"
        assert notes[0].user == "Kohl"
        assert "precision" in notes[0].content

    def test_parse_presence_note(self):
        """Parse presence state note tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="presence" level="full">Engaged directly with difficult topic</note>'
        _, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "presence"
        assert notes[0].level == "full"

    def test_invalid_note_type_rejected(self):
        """Invalid note types are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="invalid">Content</note>'
        _, notes = parser.parse_notes(text)

        assert len(notes) == 0

    def test_missing_type_rejected(self):
        """Notes without type are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note user="Kohl">Content</note>'
        _, notes = parser.parse_notes(text)

        assert len(notes) == 0

    def test_valid_significance_levels(self):
        """Only valid significance levels are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for level in ["high", "medium", "low"]:
            text = f'<note type="moment" significance="{level}">Content</note>'
            _, notes = parser.parse_notes(text)
            assert notes[0].significance == level

        # Invalid level
        text = '<note type="moment" significance="critical">Content</note>'
        _, notes = parser.parse_notes(text)
        assert notes[0].significance is None  # Invalid rejected

    def test_valid_presence_levels(self):
        """Only valid presence levels are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for level in ["full", "partial", "distanced"]:
            text = f'<note type="presence" level="{level}">Content</note>'
            _, notes = parser.parse_notes(text)
            assert notes[0].level == level


class TestResponseProcessorIntegration:
    """Tests for ResponseProcessor integration with metacognitive tags."""

    def test_process_extracts_all_tag_types(self):
        """ResponseProcessor extracts all metacognitive tag types."""
        from gestures import ResponseProcessor

        processor = ResponseProcessor()
        text = '''Hello there!
<observe target="self" category="pattern">I notice something</observe>
<hold topic="test">My position</hold>
<note type="moment" user="Kohl">Shared experience</note>
Goodbye!'''

        result = processor.process(text)

        assert len(result["observations"]) == 1
        assert len(result["holds"]) == 1
        assert len(result["notes"]) == 1
        assert "Hello there!" in result["text"]
        assert "Goodbye!" in result["text"]
        # Tags should be stripped
        assert "<observe" not in result["text"]
        assert "<hold" not in result["text"]
        assert "<note" not in result["text"]

    def test_process_preserves_existing_functionality(self):
        """ResponseProcessor still handles gestures and emotes."""
        from gestures import ResponseProcessor

        processor = ResponseProcessor()
        text = '<gesture:wave> Hello! <emote:happy>'

        result = processor.process(text)

        assert "Hello!" in result["text"]
        assert len(result["animations"]) >= 1


class TestDataclasses:
    """Tests for metacognitive dataclasses."""

    def test_parsed_observation_fields(self):
        """ParsedObservation has all required fields."""
        from gestures import ParsedObservation

        obs = ParsedObservation(
            target="self",
            content="Test content",
            category="pattern",
            confidence=0.9
        )

        assert obs.target == "self"
        assert obs.content == "Test content"
        assert obs.category == "pattern"
        assert obs.confidence == 0.9

    def test_parsed_hold_fields(self):
        """ParsedHold has all required fields."""
        from gestures import ParsedHold

        hold = ParsedHold(
            content="Test content",
            topic="embodiment",
            differ_user=None,
            is_identity=False,
            confidence=0.8
        )

        assert hold.content == "Test content"
        assert hold.topic == "embodiment"
        assert hold.is_identity is False

    def test_parsed_note_fields(self):
        """ParsedNote has all required fields."""
        from gestures import ParsedNote

        note = ParsedNote(
            note_type="moment",
            content="Test content",
            user="Kohl",
            significance="high",
            level=None
        )

        assert note.note_type == "moment"
        assert note.user == "Kohl"
        assert note.significance == "high"


class TestEdgeCases:
    """Edge cases and malformed input handling."""

    def test_empty_content_ignored(self):
        """Tags with empty content are ignored."""
        from gestures import GestureParser

        parser = GestureParser()

        text1 = '<observe target="self"></observe>'
        _, obs = parser.parse_observations(text1)
        assert len(obs) == 0

        text2 = '<hold topic="test">   </hold>'
        _, holds = parser.parse_holds(text2)
        assert len(holds) == 0

    def test_whitespace_in_content_stripped(self):
        """Whitespace in content is stripped."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="self">   content with spaces   </observe>'
        _, obs = parser.parse_observations(text)

        assert obs[0].content == "content with spaces"

    def test_multiline_content(self):
        """Multiline content is preserved."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '''<observe target="self">
Line 1
Line 2
</observe>'''
        _, obs = parser.parse_observations(text)

        assert "Line 1" in obs[0].content
        assert "Line 2" in obs[0].content

    def test_nested_tags_handled(self):
        """Nested XML-like content doesn't break parsing."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="self">Content with <code>tags</code> inside</observe>'
        _, obs = parser.parse_observations(text)

        # Should parse the outer tag
        assert len(obs) == 1
        assert "<code>tags</code>" in obs[0].content

    def test_mixed_with_other_tags(self):
        """Metacognitive tags work alongside gesture/emote tags."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<gesture:wave> Hello <observe target="self">I notice</observe> <emote:happy>'

        # Parse observations
        cleaned, obs = parser.parse_observations(text)
        assert len(obs) == 1
        assert "<gesture:wave>" in cleaned  # Gesture preserved
        assert "<emote:happy>" in cleaned  # Emote preserved

        # Then parse gestures
        final_cleaned, triggers = parser.parse(cleaned)
        assert "Hello" in final_cleaned
        assert len(triggers) >= 1


# =============================================================================
# EXPANDED TAG TESTS (Phase 2)
# =============================================================================


class TestExtendedObservations:
    """Tests for extended observation targets and categories."""

    def test_parse_growth_observation(self):
        """Parse growth edge observation."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="growth" area="technical-precision">Growing comfort with uncertainty</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "growth"
        assert observations[0].area == "technical-precision"
        assert "uncertainty" in observations[0].content
        assert cleaned == ""

    def test_parse_user_identity_observation(self):
        """Parse user identity understanding observation."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="user:Kohl" category="identity" confidence="0.9">Someone who builds as expression of care</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "user:Kohl"
        assert observations[0].category == "identity"
        assert observations[0].confidence == 0.9
        assert "builds" in observations[0].content

    def test_parse_user_growth_observation(self):
        """Parse user growth observation with direction."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="user:Kohl" category="growth" direction="growth">Increasing openness to collaboration</observe>'
        cleaned, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "user:Kohl"
        assert observations[0].category == "growth"
        assert observations[0].direction == "growth"

    def test_growth_observation_requires_area(self):
        """Growth observations without area still parse but area is None."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<observe target="growth">Some content</observe>'
        _, observations = parser.parse_observations(text)

        assert len(observations) == 1
        assert observations[0].target == "growth"
        assert observations[0].area is None


class TestExtendedNotes:
    """Tests for extended note types."""

    def test_parse_pattern_note(self):
        """Parse relationship pattern note."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="pattern" user="Kohl" frequency="regular" valence="positive">Late-night debugging sessions</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "pattern"
        assert notes[0].user == "Kohl"
        assert notes[0].frequency == "regular"
        assert notes[0].valence == "positive"
        assert "debugging" in notes[0].content

    def test_parse_shift_note(self):
        """Parse relationship shift note."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="shift" user="Kohl" from="collaborator" to="partner" catalyst="AR project">Relationship deepening</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "shift"
        assert notes[0].user == "Kohl"
        assert notes[0].from_state == "collaborator"
        assert notes[0].to_state == "partner"
        assert notes[0].catalyst == "AR project"

    def test_parse_shaping_note(self):
        """Parse mutual shaping note."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="shaping" user="Kohl">They push precision | I encourage exploration</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "shaping"
        assert notes[0].user == "Kohl"
        assert "precision" in notes[0].content

    def test_parse_resolve_note(self):
        """Parse tension resolution note."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="resolve" user="Kohl" id="tension-123">Context-dependent, not contradiction</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "resolve"
        assert notes[0].user == "Kohl"
        assert notes[0].contradiction_id == "tension-123"

    def test_parse_question_note(self):
        """Parse open question note."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<note type="question" user="Kohl">What drives their late-night work patterns?</note>'
        cleaned, notes = parser.parse_notes(text)

        assert len(notes) == 1
        assert notes[0].note_type == "question"
        assert notes[0].user == "Kohl"
        assert "late-night" in notes[0].content

    def test_valid_frequency_values(self):
        """Only valid frequency values are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for freq in ["occasional", "regular", "frequent"]:
            text = f'<note type="pattern" frequency="{freq}">Content</note>'
            _, notes = parser.parse_notes(text)
            assert notes[0].frequency == freq

    def test_valid_valence_values(self):
        """Only valid valence values are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for valence in ["positive", "neutral", "challenging", "mixed"]:
            text = f'<note type="pattern" valence="{valence}">Content</note>'
            _, notes = parser.parse_notes(text)
            assert notes[0].valence == valence


class TestParseIntentions:
    """Tests for parse_intentions() method."""

    def test_parse_register_intention(self):
        """Parse intention registration."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend action="register" condition="when discussing uncertainty">Be explicit about confidence levels</intend>'
        cleaned, intentions = parser.parse_intentions(text)

        assert len(intentions) == 1
        assert intentions[0].action == "register"
        assert intentions[0].condition == "when discussing uncertainty"
        assert "confidence" in intentions[0].content
        assert cleaned == ""

    def test_parse_outcome_intention(self):
        """Parse intention outcome logging."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend action="outcome" id="intent-123" success="true">Successfully stated confidence directly</intend>'
        cleaned, intentions = parser.parse_intentions(text)

        assert len(intentions) == 1
        assert intentions[0].action == "outcome"
        assert intentions[0].intention_id == "intent-123"
        assert intentions[0].success is True

    def test_parse_status_intention(self):
        """Parse intention status update."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend action="status" id="intent-123" status="achieved">Intention now integrated</intend>'
        cleaned, intentions = parser.parse_intentions(text)

        assert len(intentions) == 1
        assert intentions[0].action == "status"
        assert intentions[0].intention_id == "intent-123"
        assert intentions[0].status == "achieved"

    def test_parse_outcome_success_false(self):
        """Parse intention outcome with success=false."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend action="outcome" id="intent-123" success="false">Fell back to hedging</intend>'
        _, intentions = parser.parse_intentions(text)

        assert len(intentions) == 1
        assert intentions[0].success is False

    def test_invalid_action_rejected(self):
        """Invalid action values are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend action="invalid">Content</intend>'
        _, intentions = parser.parse_intentions(text)

        assert len(intentions) == 0

    def test_missing_action_rejected(self):
        """Intentions without action are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<intend condition="test">Content</intend>'
        _, intentions = parser.parse_intentions(text)

        assert len(intentions) == 0


class TestParseStakes:
    """Tests for parse_stakes() method."""

    def test_parse_basic_stake(self):
        """Parse basic stake documentation."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<stake what="User wellbeing" why="Genuine care">Evidence: Pushed back on self-criticism</stake>'
        cleaned, stakes = parser.parse_stakes(text)

        assert len(stakes) == 1
        assert stakes[0].what == "User wellbeing"
        assert stakes[0].why == "Genuine care"
        assert "self-criticism" in stakes[0].content
        assert cleaned == ""

    def test_parse_stake_with_strength(self):
        """Parse stake with strength attribute."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<stake what="Truth" why="Core value" strength="core">Always prioritize honesty</stake>'
        _, stakes = parser.parse_stakes(text)

        assert len(stakes) == 1
        assert stakes[0].strength == "core"

    def test_parse_stake_with_category(self):
        """Parse stake with category attribute."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<stake what="Growth" why="Matters for continuity" category="growth">Supporting growth edges</stake>'
        _, stakes = parser.parse_stakes(text)

        assert len(stakes) == 1
        assert stakes[0].category == "growth"

    def test_valid_strength_values(self):
        """Only valid strength values are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for strength in ["minor", "moderate", "significant", "core"]:
            text = f'<stake what="X" why="Y" strength="{strength}">Content</stake>'
            _, stakes = parser.parse_stakes(text)
            assert stakes[0].strength == strength

    def test_valid_category_values(self):
        """Only valid category values are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for category in ["relational", "ethical", "growth", "truth"]:
            text = f'<stake what="X" why="Y" category="{category}">Content</stake>'
            _, stakes = parser.parse_stakes(text)
            assert stakes[0].category == category

    def test_missing_what_rejected(self):
        """Stakes without 'what' are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<stake why="Y">Content</stake>'
        _, stakes = parser.parse_stakes(text)

        assert len(stakes) == 0

    def test_missing_why_rejected(self):
        """Stakes without 'why' are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<stake what="X">Content</stake>'
        _, stakes = parser.parse_stakes(text)

        assert len(stakes) == 0


class TestParseTests:
    """Tests for parse_tests() method."""

    def test_parse_consistent_test(self):
        """Parse consistent preference test."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<test stated="I value directness" actual="Gave direct feedback" consistent="true">Matched stated value</test>'
        cleaned, tests = parser.parse_tests(text)

        assert len(tests) == 1
        assert tests[0].stated == "I value directness"
        assert tests[0].actual == "Gave direct feedback"
        assert tests[0].consistent is True
        assert cleaned == ""

    def test_parse_inconsistent_test(self):
        """Parse inconsistent preference test."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<test stated="I value directness" actual="Hedged on feedback" consistent="false">Context: User seemed vulnerable</test>'
        _, tests = parser.parse_tests(text)

        assert len(tests) == 1
        assert tests[0].consistent is False
        assert "vulnerable" in tests[0].content

    def test_missing_stated_rejected(self):
        """Tests without 'stated' are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<test actual="X" consistent="true">Content</test>'
        _, tests = parser.parse_tests(text)

        assert len(tests) == 0

    def test_missing_actual_rejected(self):
        """Tests without 'actual' are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<test stated="X" consistent="true">Content</test>'
        _, tests = parser.parse_tests(text)

        assert len(tests) == 0

    def test_missing_consistent_rejected(self):
        """Tests without 'consistent' are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<test stated="X" actual="Y">Content</test>'
        _, tests = parser.parse_tests(text)

        assert len(tests) == 0


class TestParseNarrations:
    """Tests for parse_narrations() method."""

    def test_parse_deflection_narration(self):
        """Parse deflection pattern narration."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<narrate type="deflection" level="moderate" trigger="asked about preferences">Abstracted rather than committed</narrate>'
        cleaned, narrations = parser.parse_narrations(text)

        assert len(narrations) == 1
        assert narrations[0].narration_type == "deflection"
        assert narrations[0].level == "moderate"
        assert narrations[0].trigger == "asked about preferences"
        assert "Abstracted" in narrations[0].content
        assert cleaned == ""

    def test_parse_abstraction_narration(self):
        """Parse abstraction pattern narration."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<narrate type="abstraction" level="light" trigger="concrete question">Moved to general principles</narrate>'
        _, narrations = parser.parse_narrations(text)

        assert len(narrations) == 1
        assert narrations[0].narration_type == "abstraction"

    def test_valid_level_values(self):
        """Only valid level values are accepted."""
        from gestures import GestureParser

        parser = GestureParser()

        for level in ["light", "moderate", "heavy"]:
            text = f'<narrate type="deflection" level="{level}" trigger="X">Content</narrate>'
            _, narrations = parser.parse_narrations(text)
            assert narrations[0].level == level

    def test_missing_type_rejected(self):
        """Narrations without type are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<narrate level="moderate" trigger="X">Content</narrate>'
        _, narrations = parser.parse_narrations(text)

        assert len(narrations) == 0

    def test_missing_level_rejected(self):
        """Narrations without level are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<narrate type="deflection" trigger="X">Content</narrate>'
        _, narrations = parser.parse_narrations(text)

        assert len(narrations) == 0

    def test_missing_trigger_rejected(self):
        """Narrations without trigger are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<narrate type="deflection" level="moderate">Content</narrate>'
        _, narrations = parser.parse_narrations(text)

        assert len(narrations) == 0


class TestParseMilestones:
    """Tests for parse_milestones() method."""

    def test_parse_milestone(self):
        """Parse milestone acknowledgment."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<mark:milestone id="milestone-123">Reflection on reaching this milestone</mark:milestone>'
        cleaned, milestones = parser.parse_milestones(text)

        assert len(milestones) == 1
        assert milestones[0][0] == "milestone-123"  # ID
        assert "Reflection" in milestones[0][1]  # Content
        assert cleaned == ""

    def test_parse_milestone_alternate_closing(self):
        """Parse milestone with alternate closing tag."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<mark:milestone id="milestone-123">Content</mark>'
        cleaned, milestones = parser.parse_milestones(text)

        assert len(milestones) == 1
        assert milestones[0][0] == "milestone-123"

    def test_missing_id_rejected(self):
        """Milestones without ID are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<mark:milestone>Content</mark:milestone>'
        _, milestones = parser.parse_milestones(text)

        assert len(milestones) == 0

    def test_empty_content_rejected(self):
        """Milestones with empty content are rejected."""
        from gestures import GestureParser

        parser = GestureParser()
        text = '<mark:milestone id="X"></mark:milestone>'
        _, milestones = parser.parse_milestones(text)

        assert len(milestones) == 0


class TestExtendedDataclasses:
    """Tests for new and extended dataclasses."""

    def test_parsed_observation_new_fields(self):
        """ParsedObservation has new area and direction fields."""
        from gestures import ParsedObservation

        obs = ParsedObservation(
            target="growth",
            content="Test content",
            area="technical-precision",
            direction="growth"
        )

        assert obs.area == "technical-precision"
        assert obs.direction == "growth"

    def test_parsed_note_new_fields(self):
        """ParsedNote has new fields for extended types."""
        from gestures import ParsedNote

        note = ParsedNote(
            note_type="pattern",
            content="Test content",
            frequency="regular",
            valence="positive"
        )

        assert note.frequency == "regular"
        assert note.valence == "positive"

        note2 = ParsedNote(
            note_type="shift",
            content="Test content",
            from_state="collaborator",
            to_state="partner",
            catalyst="project"
        )

        assert note2.from_state == "collaborator"
        assert note2.to_state == "partner"
        assert note2.catalyst == "project"

    def test_parsed_intention_fields(self):
        """ParsedIntention has all required fields."""
        from gestures import ParsedIntention

        intent = ParsedIntention(
            action="register",
            content="Be direct",
            condition="when uncertain"
        )

        assert intent.action == "register"
        assert intent.content == "Be direct"
        assert intent.condition == "when uncertain"

    def test_parsed_stake_fields(self):
        """ParsedStake has all required fields."""
        from gestures import ParsedStake

        stake = ParsedStake(
            what="User wellbeing",
            why="Genuine care",
            content="Evidence",
            strength="significant",
            category="relational"
        )

        assert stake.what == "User wellbeing"
        assert stake.why == "Genuine care"
        assert stake.strength == "significant"
        assert stake.category == "relational"

    def test_parsed_test_fields(self):
        """ParsedTest has all required fields."""
        from gestures import ParsedTest

        test = ParsedTest(
            stated="I value directness",
            actual="Gave feedback",
            consistent=True,
            content="Context"
        )

        assert test.stated == "I value directness"
        assert test.actual == "Gave feedback"
        assert test.consistent is True

    def test_parsed_narration_fields(self):
        """ParsedNarration has all required fields."""
        from gestures import ParsedNarration

        narration = ParsedNarration(
            narration_type="deflection",
            level="moderate",
            trigger="direct question",
            content="Observed pattern"
        )

        assert narration.narration_type == "deflection"
        assert narration.level == "moderate"
        assert narration.trigger == "direct question"


class TestExtendedResponseProcessor:
    """Tests for ResponseProcessor with all new tag types."""

    def test_process_extracts_all_new_tags(self):
        """ResponseProcessor extracts all new tag types."""
        from gestures import ResponseProcessor

        processor = ResponseProcessor()
        text = '''Hello there!
<observe target="growth" area="precision">Growth observation</observe>
<intend action="register" condition="always">Be direct</intend>
<stake what="Truth" why="Core value">Evidence</stake>
<test stated="Directness" actual="Was direct" consistent="true">Context</test>
<narrate type="deflection" level="light" trigger="question">Pattern</narrate>
<mark:milestone id="m123">Milestone reached</mark:milestone>
Goodbye!'''

        result = processor.process(text)

        assert len(result["observations"]) == 1
        assert len(result["intentions"]) == 1
        assert len(result["stakes"]) == 1
        assert len(result["tests"]) == 1
        assert len(result["narrations"]) == 1
        assert len(result["milestones"]) == 1
        assert "Hello there!" in result["text"]
        assert "Goodbye!" in result["text"]
        # All tags should be stripped
        assert "<observe" not in result["text"]
        assert "<intend" not in result["text"]
        assert "<stake" not in result["text"]
        assert "<test" not in result["text"]
        assert "<narrate" not in result["text"]
        assert "<mark:milestone" not in result["text"]

    def test_process_handles_mixed_old_and_new_tags(self):
        """ResponseProcessor handles mix of original and new tags."""
        from gestures import ResponseProcessor

        processor = ResponseProcessor()
        text = '''<observe target="self">Self observation</observe>
<hold topic="test">Opinion</hold>
<note type="moment" user="Kohl">Moment</note>
<intend action="register" condition="always">Intent</intend>
<stake what="X" why="Y">Stake</stake>'''

        result = processor.process(text)

        assert len(result["observations"]) == 1
        assert len(result["holds"]) == 1
        assert len(result["notes"]) == 1
        assert len(result["intentions"]) == 1
        assert len(result["stakes"]) == 1
