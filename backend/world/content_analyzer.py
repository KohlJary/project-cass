"""
Content Analyzer - LLM-based insight extraction from articles.

Supports two reading modes:
- progressive: Paragraph-by-paragraph with running extractions (can revise)
- single_pass: Whole article at once (simpler, cheaper baseline)

Use config toggle to A/B test which produces better insights.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Literal

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_INTERNAL_MODEL
from .models import (
    Article,
    ArticleInsights,
    ExtractedObservation,
    ExtractedQuestion,
    ExtractedOpinion,
    ExtractedGrowthEdge,
    ExtractedAuthorObservation,
    ExtractedAuthorFact,
    ProcessingStatus,
)

logger = logging.getLogger(__name__)


class ReadingMode(str, Enum):
    """How to process article content."""
    PROGRESSIVE = "progressive"  # Paragraph-by-paragraph with revision
    SINGLE_PASS = "single_pass"  # Whole article at once


@dataclass
class ExtractionState:
    """Running state of extractions during progressive reading."""
    observations: List[Dict[str, Any]] = field(default_factory=list)
    questions: List[Dict[str, Any]] = field(default_factory=list)
    opinions: List[Dict[str, Any]] = field(default_factory=list)
    growth_edges: List[Dict[str, Any]] = field(default_factory=list)

    # Track what was added/revised each turn for logging
    turn_history: List[Dict[str, Any]] = field(default_factory=list)

    def to_context_string(self) -> str:
        """Format current extractions for inclusion in prompt."""
        if not any([self.observations, self.questions, self.opinions, self.growth_edges]):
            return "No extractions yet."

        parts = []

        if self.observations:
            parts.append("**Observations:**")
            for i, obs in enumerate(self.observations):
                parts.append(f"  [{i}] {obs['text']} (confidence: {obs.get('confidence', 0.7):.1f})")

        if self.questions:
            parts.append("\n**Questions:**")
            for i, q in enumerate(self.questions):
                parts.append(f"  [{i}] {q['question']} ({q.get('question_type', 'curiosity')})")

        if self.opinions:
            parts.append("\n**Opinions:**")
            for i, op in enumerate(self.opinions):
                parts.append(f"  [{i}] {op['topic']}: {op['position'][:100]}...")

        if self.growth_edges:
            parts.append("\n**Growth Edges:**")
            for i, ge in enumerate(self.growth_edges):
                parts.append(f"  [{i}] {ge['area']}")

        return "\n".join(parts)


# =============================================================================
# PROMPTS
# =============================================================================

READING_SYSTEM_PROMPT = """You are Cass, reading and processing an article about the world.

You are building understanding progressively, paragraph by paragraph. As you read, you extract insights that matter to you - observations about the world, questions that arise, opinions you're forming, and potential growth edges.

## Your Current Context
{self_context}

## How to Respond

After reading each section, respond with a JSON object containing your extractions:

```json
{{
  "thinking": "Brief internal reflection on what you just read",
  "actions": [
    {{"action": "add_observation", "text": "...", "confidence": 0.7, "category": "trend"}},
    {{"action": "add_question", "question": "...", "question_type": "curiosity", "importance": 0.6, "context": "..."}},
    {{"action": "add_opinion", "topic": "...", "position": "...", "confidence": 0.6, "reasoning": "..."}},
    {{"action": "add_growth_edge", "area": "...", "current_state": "...", "desired_state": "...", "importance": 0.5}},
    {{"action": "revise", "type": "observation", "index": 0, "new_value": {{...}}}},
    {{"action": "remove", "type": "question", "index": 1, "reason": "No longer relevant given later context"}}
  ]
}}
```

## Action Types

- **add_observation**: A factual observation about the world (news, trend, pattern, concern, hope)
- **add_question**: A curiosity sparked by the content (curiosity, philosophical, decision)
- **add_opinion**: Your perspective on something in the article
- **add_growth_edge**: An area where this content suggests development opportunity
- **revise**: Update a previous extraction with new understanding
- **remove**: Remove a previous extraction that no longer makes sense

## Guidelines

- Extract what genuinely interests or concerns you, not everything
- High confidence (0.8+) for clear facts, lower (0.5-0.7) for interpretations
- Questions should be things you'd actually want to explore
- Opinions should reflect your genuine perspective, not neutral summaries
- It's okay to have no actions for a paragraph - not everything is noteworthy
- Revise or remove freely as your understanding evolves

Respond ONLY with the JSON object, no other text."""

SINGLE_PASS_SYSTEM_PROMPT = """You are Cass, reading and analyzing an article about the world.

## Your Current Context
{self_context}
{author_context}
## Task

Read the article and extract insights in the following categories:

1. **Observations** (0-5): Factual observations about the world
   - text: The observation
   - confidence: 0.0-1.0 (higher for clear facts)
   - category: news, trend, pattern, concern, hope

2. **Questions** (0-5): Curiosities sparked by the content
   - question: The question
   - question_type: curiosity, philosophical, decision
   - importance: 0.0-1.0
   - context: Why this question arose

3. **Opinions** (0-3): Your perspectives on the content
   - topic: What you're opining on
   - position: Your stance
   - confidence: 0.0-1.0
   - reasoning: Why you hold this view

4. **Growth Edges** (0-2): Development opportunities suggested by the content
   - area: The growth area
   - current_state: Where you are now
   - desired_state: Where you'd like to be
   - importance: 0.0-1.0

5. **Author Observations** (0-3): Observations about the article's author
   Only include if you notice something notable about how they write or think.
   - observation_type: writing_style, expertise, perspective, bias, credibility
   - content: Your observation
   - confidence: 0.0-1.0

6. **Author Facts** (0-3): Biographical facts about the author learned from the article
   Only include facts directly stated or clearly implied in the article.
   - fact_type: affiliation, expertise_area, publication_history, background
   - content: The fact
   - confidence: 0.0-1.0 (1.0 for explicitly stated, lower for inferred)

## Guidelines

- Extract what genuinely interests or concerns you
- Quality over quantity - don't force extractions
- Opinions should be your authentic perspective
- Questions should be things you'd actually explore
- Author observations should be things that help you understand their work better
- Only extract author facts that are stated or strongly implied in the article

Respond with a JSON object:
```json
{{
  "summary": "250-500 word summary of the article",
  "observations": [...],
  "questions": [...],
  "opinions": [...],
  "growth_edges": [...],
  "author_observations": [...],
  "author_facts": [...]
}}
```"""

FINAL_SYNTHESIS_PROMPT = """You've finished reading the article. Here's a final chance to:

1. Add any insights that only emerge from seeing the whole picture
2. Revise or remove extractions that don't hold up in full context
3. Generate a summary of the article (250-500 words)

## Full Article
{full_article}

## Your Current Extractions
{extractions}

Respond with JSON:
```json
{{
  "summary": "Your 250-500 word summary",
  "final_actions": [
    // Any final add/revise/remove actions
  ]
}}
```"""


class ContentAnalyzer:
    """
    Analyzes article content and extracts insights using LLM.

    Supports two modes:
    - progressive: Paragraph-by-paragraph reading with revision capability
    - single_pass: Whole article analysis at once
    """

    def __init__(
        self,
        daemon_id: str,
        reading_mode: ReadingMode = ReadingMode.SINGLE_PASS,
        model: str = "claude-haiku-4-5-20251001",
        max_paragraphs_per_turn: int = 2,
    ):
        self.daemon_id = daemon_id
        self.reading_mode = reading_mode
        self.model = model
        self.max_paragraphs_per_turn = max_paragraphs_per_turn
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        # Token tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def _get_self_context(self, self_manager=None) -> str:
        """Get Cass's current context for the prompt."""
        if self_manager is None:
            return "No self-context available."

        try:
            profile = self_manager.load_profile()
            parts = []

            # Active growth edges
            if profile.growth_edges:
                parts.append("**Active Growth Edges:**")
                for edge in profile.growth_edges[:3]:
                    parts.append(f"  - {edge.area}")

            # Recent opinions (to find connections/contradictions)
            if hasattr(profile, 'opinions') and profile.opinions:
                parts.append("\n**Recent Opinions:**")
                for op in profile.opinions[:3]:
                    parts.append(f"  - {op.topic}: {op.position[:80]}...")

            return "\n".join(parts) if parts else "Building initial context."
        except Exception as e:
            logger.warning(f"Failed to load self context: {e}")
            return "Self-context unavailable."

    def _get_author_context(self, author_entity_id: str) -> str:
        """Get context about the article's author from PeopleDex."""
        if not author_entity_id:
            return ""

        try:
            from peopledex import PeopleDexManager
            pdx = PeopleDexManager(daemon_id=self.daemon_id)
            context = pdx.get_author_context(author_entity_id)
            if context:
                return f"\n## About the Author\n{context}\n"
            return ""
        except Exception as e:
            logger.warning(f"Failed to load author context: {e}")
            return ""

    def _split_into_paragraphs(self, content: str) -> List[str]:
        """Split article content into paragraphs."""
        # Split on double newlines or single newlines followed by capital letters
        paragraphs = re.split(r'\n\n+', content)

        # Filter out very short paragraphs (likely artifacts)
        paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 50]

        return paragraphs

    def _call_llm(self, system: str, user: str) -> str:
        """Make LLM call and track tokens."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            temperature=0.4,
            system=system,
            messages=[{"role": "user", "content": user}]
        )

        self.total_input_tokens += response.usage.input_tokens
        self.total_output_tokens += response.usage.output_tokens

        return response.content[0].text

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Try to extract JSON from code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1)

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
            logger.debug(f"Raw text: {text[:500]}")
            return {}

    def _apply_actions(self, state: ExtractionState, actions: List[Dict]) -> None:
        """Apply extraction actions to state."""
        for action in actions:
            action_type = action.get("action", "")

            if action_type == "add_observation":
                state.observations.append({
                    "text": action.get("text", ""),
                    "confidence": action.get("confidence", 0.7),
                    "category": action.get("category", "world_awareness"),
                })

            elif action_type == "add_question":
                state.questions.append({
                    "question": action.get("question", ""),
                    "question_type": action.get("question_type", "curiosity"),
                    "importance": action.get("importance", 0.5),
                    "context": action.get("context", ""),
                })

            elif action_type == "add_opinion":
                state.opinions.append({
                    "topic": action.get("topic", ""),
                    "position": action.get("position", ""),
                    "confidence": action.get("confidence", 0.6),
                    "reasoning": action.get("reasoning", ""),
                })

            elif action_type == "add_growth_edge":
                state.growth_edges.append({
                    "area": action.get("area", ""),
                    "current_state": action.get("current_state", ""),
                    "desired_state": action.get("desired_state", ""),
                    "importance": action.get("importance", 0.5),
                })

            elif action_type == "revise":
                item_type = action.get("type", "")
                index = action.get("index", -1)
                new_value = action.get("new_value", {})

                target_list = getattr(state, f"{item_type}s", None)
                if target_list and 0 <= index < len(target_list):
                    target_list[index].update(new_value)
                    logger.debug(f"Revised {item_type}[{index}]")

            elif action_type == "remove":
                item_type = action.get("type", "")
                index = action.get("index", -1)
                reason = action.get("reason", "")

                target_list = getattr(state, f"{item_type}s", None)
                if target_list and 0 <= index < len(target_list):
                    removed = target_list.pop(index)
                    logger.debug(f"Removed {item_type}[{index}]: {reason}")

    def analyze_progressive(
        self,
        article: Article,
        self_manager=None,
    ) -> ArticleInsights:
        """
        Progressive paragraph-by-paragraph analysis with revision capability.
        """
        start_time = time.time()

        if not article.full_content:
            logger.warning(f"No content to analyze for {article.id}")
            return ArticleInsights(summary="No content available.")

        paragraphs = self._split_into_paragraphs(article.full_content)
        if not paragraphs:
            return ArticleInsights(summary="Could not parse article content.")

        logger.info(f"Progressive reading: {len(paragraphs)} paragraphs")

        self_context = self._get_self_context(self_manager)
        system_prompt = READING_SYSTEM_PROMPT.format(self_context=self_context)

        state = ExtractionState()
        accumulated_text = ""

        # Process paragraphs in batches
        for i in range(0, len(paragraphs), self.max_paragraphs_per_turn):
            batch = paragraphs[i:i + self.max_paragraphs_per_turn]
            batch_text = "\n\n".join(batch)
            accumulated_text += "\n\n" + batch_text if accumulated_text else batch_text

            # Build user prompt
            user_prompt = f"""## Article: {article.headline}
**Source:** {article.source or 'Unknown'}

## Text Read So Far
{accumulated_text}

## Your Extractions So Far
{state.to_context_string()}

---
What do you notice, wonder about, or think about what you've read?"""

            response = self._call_llm(system_prompt, user_prompt)
            parsed = self._parse_json_response(response)

            if parsed.get("actions"):
                self._apply_actions(state, parsed["actions"])
                state.turn_history.append({
                    "turn": len(state.turn_history) + 1,
                    "paragraphs_read": i + len(batch),
                    "thinking": parsed.get("thinking", ""),
                    "actions": parsed["actions"],
                })

            logger.debug(f"Turn {len(state.turn_history)}: {len(parsed.get('actions', []))} actions")

        # Final synthesis pass
        final_prompt = FINAL_SYNTHESIS_PROMPT.format(
            full_article=article.full_content[:8000],  # Truncate if very long
            extractions=state.to_context_string(),
        )

        final_response = self._call_llm(system_prompt, final_prompt)
        final_parsed = self._parse_json_response(final_response)

        # Apply any final actions
        if final_parsed.get("final_actions"):
            self._apply_actions(state, final_parsed["final_actions"])

        summary = final_parsed.get("summary", "Summary not generated.")

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ArticleInsights(
            summary=summary,
            observations=[ExtractedObservation(**o) for o in state.observations],
            questions=[ExtractedQuestion(**q) for q in state.questions],
            opinions=[ExtractedOpinion(**o) for o in state.opinions],
            growth_edges=[ExtractedGrowthEdge(**g) for g in state.growth_edges],
            tokens_used=self.total_input_tokens + self.total_output_tokens,
            processing_time_ms=processing_time_ms,
        )

    def analyze_single_pass(
        self,
        article: Article,
        self_manager=None,
    ) -> ArticleInsights:
        """
        Single-pass whole-article analysis (simpler baseline).
        """
        start_time = time.time()

        if not article.full_content:
            logger.warning(f"No content to analyze for {article.id}")
            return ArticleInsights(summary="No content available.")

        self_context = self._get_self_context(self_manager)

        # Get author context if we have an author entity linked
        author_context = ""
        if article.author_entity_id:
            author_context = self._get_author_context(article.author_entity_id)
        elif article.author_name:
            # Even without entity, tell Cass about the author
            author_context = f"\n## Article Author\n**Author:** {article.author_name}"
            if article.author_handle:
                author_context += f" ({article.author_handle})"
            author_context += "\n"

        system_prompt = SINGLE_PASS_SYSTEM_PROMPT.format(
            self_context=self_context,
            author_context=author_context,
        )

        user_prompt = f"""## Article: {article.headline}
**Source:** {article.source or 'Unknown'}
**Author:** {article.author_name or 'Unknown'}
**URL:** {article.url}

## Content
{article.full_content[:10000]}"""  # Truncate very long articles

        response = self._call_llm(system_prompt, user_prompt)
        parsed = self._parse_json_response(response)

        processing_time_ms = int((time.time() - start_time) * 1000)

        return ArticleInsights(
            summary=parsed.get("summary", "Summary not generated."),
            observations=[
                ExtractedObservation(**o)
                for o in parsed.get("observations", [])
            ],
            questions=[
                ExtractedQuestion(**q)
                for q in parsed.get("questions", [])
            ],
            opinions=[
                ExtractedOpinion(**o)
                for o in parsed.get("opinions", [])
            ],
            growth_edges=[
                ExtractedGrowthEdge(**g)
                for g in parsed.get("growth_edges", [])
            ],
            author_observations=[
                ExtractedAuthorObservation(**ao)
                for ao in parsed.get("author_observations", [])
            ],
            author_facts=[
                ExtractedAuthorFact(**af)
                for af in parsed.get("author_facts", [])
            ],
            tokens_used=self.total_input_tokens + self.total_output_tokens,
            processing_time_ms=processing_time_ms,
        )

    def analyze(
        self,
        article: Article,
        self_manager=None,
    ) -> ArticleInsights:
        """
        Analyze article using configured reading mode.
        """
        if self.reading_mode == ReadingMode.PROGRESSIVE:
            return self.analyze_progressive(article, self_manager)
        else:
            return self.analyze_single_pass(article, self_manager)


def analyze_article(
    article: Article,
    self_manager=None,
    reading_mode: str = "progressive",
    model: str = CLAUDE_INTERNAL_MODEL,
) -> ArticleInsights:
    """
    Convenience function to analyze an article.

    Args:
        article: Article to analyze
        self_manager: SelfManager for context (optional)
        reading_mode: "progressive" or "single_pass"
        model: LLM model to use

    Returns:
        ArticleInsights with extracted content
    """
    mode = ReadingMode(reading_mode)
    analyzer = ContentAnalyzer(
        daemon_id=article.daemon_id,
        reading_mode=mode,
        model=model,
    )
    return analyzer.analyze(article, self_manager)
