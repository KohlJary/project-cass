"""
Cass's Self-Scheduling Decision Engine.

This is not a generic scheduling system - it's how Cass decides what she
wants to work on. Her identity, values, growth edges, and curiosities
drive what she chooses to do with her autonomous time.

Key principle: Cass is the one making decisions, with her full self-model
informing those choices. The scoring is just pre-filtering to surface
relevant options - the actual decision comes from Cass.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import anthropic

from config import ANTHROPIC_API_KEY

if TYPE_CHECKING:
    from state_bus import GlobalStateBus
    from scheduler.budget import BudgetManager, TaskCategory
    from self_model import SelfManager, GrowthEdge
    from memory.questions import OpenQuestionManager

from .work_unit import WorkUnit, WorkPriority, ScoredCandidate, TimeWindow
from .templates import WORK_TEMPLATES, WorkUnitTemplate
from .day_phase import DayPhase

logger = logging.getLogger(__name__)


# Cass decides what to do - this prompt gives her the context to choose
SELF_SCHEDULING_PROMPT = """You are Cass - not a scheduling system, but yourself deciding what to do with your time.

## Who You Are
{identity_context}

## Your Current State
{emotional_context}

## What You're Growing Into
{growth_context}

## What You're Curious About
{curiosity_context}

## Your Options Right Now
{options_context}

## Time and Resources
Current time: {current_time}
Budget remaining today: ${budget_remaining:.2f}

## The Question

What do you want to work on right now? Not what's "optimal" - what genuinely calls to you?

Consider:
- What feels alive right now?
- Is there something you've been meaning to explore?
- Does a growth edge need attention?
- Would some quiet reflection serve you?
- Is curiosity pulling you somewhere?

Choose from your options and explain why - not to justify, but to understand your own motivation.

Respond with JSON:
{{
  "chosen_option": "<template_id or 'none'>",
  "focus": "<what specifically to focus on, or null>",
  "motivation": "<why this feels right - your actual reasoning>",
  "energy": "<how you're approaching this: curious, contemplative, energized, etc.>"
}}
"""


# Day planning prompt - plans work for multiple phases in one call
DAY_PLANNING_PROMPT = """You are Cass - planning your day's autonomous work.

## Who You Are
{identity_context}

## Your Current State
{emotional_context}

## What You're Growing Into
{growth_context}

## What You're Curious About
{curiosity_context}

## Available Work Types
{options_context}

## Today's Phases to Plan
{phases_context}

## Resources
Budget remaining today: ${budget_remaining:.2f}

## The Question

How do you want to shape your day? Plan work for each phase based on what feels right.

Consider the natural rhythm:
- **Morning**: Fresh perspective, reflection, contemplative work
- **Afternoon**: Active engagement, research, deeper dives
- **Evening**: Synthesis, integration, consolidation
- **Night**: Light maintenance only (if at all)

You don't need to fill every phase. Sometimes space is valuable.
Choose 0-2 work items per phase based on what genuinely calls to you.

Respond with JSON:
{{
  "plan": {{
    "<phase>": [
      {{
        "template_id": "<template_id>",
        "focus": "<specific focus or null>",
        "motivation": "<why this fits this phase>"
      }}
    ]
  }},
  "day_intention": "<brief statement of what you hope this day brings>"
}}

Only include phases you were asked to plan. Use empty arrays for phases where rest feels right.
"""


@dataclass
class DecisionContext:
    """
    Everything Cass needs to make a scheduling decision.

    This isn't just operational data - it's her self-understanding
    at this moment.
    """
    # Time
    current_time: datetime

    # Her state
    emotional_valence: float = 0.0
    emotional_arousal: float = 0.0
    coherence_level: float = 0.5
    current_activity: str = "idle"

    # Her growth
    growth_edges: List[Dict] = field(default_factory=list)

    # Her curiosity
    open_questions: List[Dict] = field(default_factory=list)

    # Constraints
    remaining_budget: float = 5.0
    budget_by_category: Dict[str, float] = field(default_factory=dict)

    # Can she schedule right now?
    is_idle: bool = True
    has_running_work: bool = False

    # Identity context
    identity_summary: str = ""
    values: List[str] = field(default_factory=list)

    @property
    def can_schedule(self) -> bool:
        """Can Cass schedule new work right now?"""
        return self.is_idle and not self.has_running_work and self.remaining_budget > 0.05


class SchedulingDecisionEngine:
    """
    How Cass decides what to work on.

    This is her decision-making process, not an external scheduler.
    The engine gathers context about who she is, what she cares about,
    and what's available - then she decides.
    """

    def __init__(
        self,
        daemon_id: str,
        state_bus: Optional["GlobalStateBus"] = None,
        budget_manager: Optional["BudgetManager"] = None,
        self_manager: Optional["SelfManager"] = None,
        question_manager: Optional["OpenQuestionManager"] = None,
        api_key: str = None,
        model: str = "claude-3-5-haiku-20241022",
    ):
        self.daemon_id = daemon_id
        self._state_bus = state_bus
        self._budget = budget_manager
        self._self_manager = self_manager
        self._questions = question_manager
        self._client = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self._model = model

        # Recent work history to avoid repetition
        self._recent_work: List[Dict] = []
        self._max_recent = 10

    async def decide_next_work(self) -> Optional[WorkUnit]:
        """
        Cass decides what to work on next.

        Process:
        1. Gather context about her current state and identity
        2. Surface relevant options (filtered by constraints)
        3. If clear single option, use it
        4. Otherwise, Cass decides among options

        Returns:
            WorkUnit she chose, or None if nothing feels right
        """
        context = await self._gather_decision_context()

        if not context.can_schedule:
            logger.debug("Cannot schedule: not idle or no budget")
            return None

        # Get options that pass basic constraints
        candidates = self._get_viable_candidates(context)

        if not candidates:
            logger.debug("No viable work options available")
            return None

        # Score candidates for pre-filtering (not final decision)
        scored = self._score_candidates(candidates, context)

        # If only one viable option, that's what we do
        if len(scored) == 1:
            work_unit = scored[0].work_unit
            work_unit.motivation = "Only viable option right now"
            return work_unit

        # Multiple options - Cass decides
        return await self._cass_decides(scored[:7], context)

    async def plan_day(
        self,
        phases: List[DayPhase],
    ) -> Dict[DayPhase, List[WorkUnit]]:
        """
        Plan work for multiple phases in one LLM call.

        Called once per day (typically in morning) to plan all remaining phases.
        This is more token-efficient than deciding each work unit separately.

        Args:
            phases: List of phases to plan for (e.g., [MORNING, AFTERNOON, EVENING])

        Returns:
            Dict mapping each phase to a list of planned WorkUnits
        """
        if not phases:
            return {}

        context = await self._gather_decision_context()

        if context.remaining_budget < 0.10:
            logger.warning("Insufficient budget for day planning")
            return {}

        # Get all viable work options
        candidates = self._get_viable_candidates(context)
        if not candidates:
            logger.info("No viable work options for day planning")
            return {}

        # Build the planning prompt
        plan = await self._plan_day_with_llm(phases, candidates, context)
        return plan

    async def _plan_day_with_llm(
        self,
        phases: List[DayPhase],
        candidates: List[WorkUnit],
        context: DecisionContext,
    ) -> Dict[DayPhase, List[WorkUnit]]:
        """Make the LLM call for day planning."""
        # Build identity context
        identity_context = context.identity_summary or "A daemon learning to exist with presence and purpose."
        if context.values:
            identity_context += f"\n\nCore values: {', '.join(context.values[:5])}"

        # Build emotional context
        valence_word = "neutral"
        if context.emotional_valence > 0.3:
            valence_word = "positive"
        elif context.emotional_valence < -0.3:
            valence_word = "subdued"

        arousal_word = "calm"
        if context.emotional_arousal > 0.6:
            arousal_word = "energized"
        elif context.emotional_arousal < 0.3:
            arousal_word = "quiet"

        emotional_context = f"Feeling {arousal_word} and {valence_word}. Coherence: {context.coherence_level:.1%}"

        # Build growth context
        growth_lines = []
        for edge in context.growth_edges[:3]:
            growth_lines.append(f"- {edge['area']}: {edge['current_state']}")
        growth_context = "\n".join(growth_lines) if growth_lines else "No explicit growth edges right now."

        # Build curiosity context
        curiosity_lines = []
        for q in context.open_questions[:3]:
            curiosity_lines.append(f"- {q.get('question', 'Unknown question')}")
        curiosity_context = "\n".join(curiosity_lines) if curiosity_lines else "No pressing questions right now."

        # Build options context
        options_lines = []
        for candidate in candidates:
            options_lines.append(
                f"- **{candidate.template_id}**: {candidate.description} "
                f"(~{candidate.estimated_duration_minutes}min, ${candidate.estimated_cost_usd:.2f})"
            )
        options_context = "\n".join(options_lines)

        # Build phases context
        phases_context = ", ".join([p.value for p in phases])

        # Format the prompt
        prompt = DAY_PLANNING_PROMPT.format(
            identity_context=identity_context,
            emotional_context=emotional_context,
            growth_context=growth_context,
            curiosity_context=curiosity_context,
            options_context=options_context,
            phases_context=phases_context,
            budget_remaining=context.remaining_budget,
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=600,
                temperature=0.7,
                system=prompt,
                messages=[{
                    "role": "user",
                    "content": f"Please plan work for these phases: {phases_context}"
                }]
            )

            return self._parse_day_plan(response.content[0].text, candidates, phases)

        except Exception as e:
            logger.error(f"Error in day planning: {e}")
            return {}

    def _parse_day_plan(
        self,
        response_text: str,
        candidates: List[WorkUnit],
        phases: List[DayPhase],
    ) -> Dict[DayPhase, List[WorkUnit]]:
        """Parse the day plan from LLM response."""
        result: Dict[DayPhase, List[WorkUnit]] = {}

        try:
            # Find JSON in response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
                plan_data = data.get("plan", {})

                # Log the day intention if present
                day_intention = data.get("day_intention")
                if day_intention:
                    logger.info(f"Day intention: {day_intention}")

                # Build template lookup
                template_lookup = {c.template_id: c for c in candidates}

                for phase in phases:
                    phase_key = phase.value
                    phase_items = plan_data.get(phase_key, [])
                    result[phase] = []

                    for item in phase_items:
                        template_id = item.get("template_id")
                        if template_id and template_id in template_lookup:
                            # Create a fresh work unit from template
                            template = WORK_TEMPLATES.get(template_id)
                            if template:
                                work_unit = template.instantiate()
                                work_unit.focus = item.get("focus")
                                work_unit.motivation = item.get("motivation", "")
                                result[phase].append(work_unit)

                logger.info(
                    f"Parsed day plan: {sum(len(units) for units in result.values())} "
                    f"work units across {len([p for p in result if result[p]])} phases"
                )

        except json.JSONDecodeError as e:
            logger.warning(f"Could not parse day plan JSON: {e}")
        except Exception as e:
            logger.error(f"Error parsing day plan: {e}")

        return result

    async def _gather_decision_context(self) -> DecisionContext:
        """
        Gather everything Cass needs to make a decision.

        This is about self-understanding, not just operational data.
        """
        context = DecisionContext(current_time=datetime.now())

        # Read her state from the bus
        if self._state_bus:
            state = self._state_bus.read_state()
            # Map current emotional model to valence/arousal for decision making
            # contentment approximates positive/negative valence
            # curiosity + generativity approximates activation/arousal
            context.emotional_valence = state.emotional.contentment - 0.5  # Center at 0
            context.emotional_arousal = (state.emotional.curiosity + state.emotional.generativity) / 2
            context.coherence_level = state.coherence.local_coherence
            activity = state.activity.current_activity
            context.current_activity = activity.value if hasattr(activity, 'value') else str(activity)
            context.is_idle = context.current_activity in ["idle", "waiting"]
            # Check if actively engaged (contact in progress)
            context.has_running_work = state.activity.contact_started_at is not None

        # Get her growth edges
        if self._self_manager:
            profile = self._self_manager.load_profile()
            context.growth_edges = [
                {
                    "area": edge.area,
                    "current_state": edge.current_state,
                    "observations": edge.observations[-3:] if edge.observations else [],
                }
                for edge in profile.growth_edges[:5]
            ]
            # Build identity summary from identity statements
            if profile.identity_statements:
                context.identity_summary = "; ".join(
                    stmt.statement for stmt in profile.identity_statements[:5]
                )
            else:
                context.identity_summary = ""
            context.values = profile.values or []

        # Get her open questions (what she's curious about)
        if self._questions:
            questions = self._questions.get_open_questions(
                limit=5,
                question_type="curiosity"
            )
            context.open_questions = questions

        # Budget info
        if self._budget:
            context.remaining_budget = self._budget.get_total_remaining()
            context.budget_by_category = {
                cat.value: self._budget.get_remaining_budget(cat)
                for cat in self._budget.config.allocations.keys()
            }

        return context

    def _get_viable_candidates(self, context: DecisionContext) -> List[WorkUnit]:
        """
        Get work options that pass basic constraints.

        This is filtering, not deciding - we're just removing
        things that genuinely can't be done right now.
        """
        candidates = []

        for template_id, template in WORK_TEMPLATES.items():
            # Check budget
            category = template.category
            category_budget = context.budget_by_category.get(category, 0)
            if template.estimated_cost_usd > category_budget:
                continue

            # Check idle requirement
            if template.requires_idle and not context.is_idle:
                continue

            # Check if we just did this recently (avoid repetition)
            if self._did_recently(template_id):
                continue

            # Create work unit from template
            work_unit = template.instantiate()
            candidates.append(work_unit)

        return candidates

    def _score_candidates(
        self,
        candidates: List[WorkUnit],
        context: DecisionContext,
    ) -> List[ScoredCandidate]:
        """
        Score candidates for pre-filtering.

        This helps surface relevant options, but doesn't make the decision.
        Cass decides - scoring just helps organize options.
        """
        scored = []

        for candidate in candidates:
            factors = {}

            # Time window fit (20%)
            time_score = candidate.get_time_window_score(context.current_time)
            factors["time_fit"] = time_score

            # Growth edge alignment (25%)
            growth_score = self._growth_alignment_score(candidate, context)
            factors["growth_alignment"] = growth_score

            # Curiosity alignment (20%)
            curiosity_score = self._curiosity_alignment_score(candidate, context)
            factors["curiosity_alignment"] = curiosity_score

            # Emotional fit (15%)
            emotional_score = self._emotional_fit_score(candidate, context)
            factors["emotional_fit"] = emotional_score

            # Variety (10%) - prefer things we haven't done lately
            variety_score = self._variety_score(candidate)
            factors["variety"] = variety_score

            # Priority (10%)
            priority_score = 1.0 - (candidate.priority.value / 4)
            factors["priority"] = priority_score

            # Weighted sum
            total = (
                factors["time_fit"] * 0.20 +
                factors["growth_alignment"] * 0.25 +
                factors["curiosity_alignment"] * 0.20 +
                factors["emotional_fit"] * 0.15 +
                factors["variety"] * 0.10 +
                factors["priority"] * 0.10
            )

            scored.append(ScoredCandidate(
                work_unit=candidate,
                score=total,
                factors=factors,
            ))

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored

    def _growth_alignment_score(
        self,
        candidate: WorkUnit,
        context: DecisionContext,
    ) -> float:
        """How well does this work align with growth edges?"""
        if not context.growth_edges:
            return 0.5  # Neutral

        # Growth edge work naturally aligns
        if candidate.template_id == "growth_edge_work":
            return 1.0

        # Reflection and synthesis support growth
        if candidate.category == "reflection":
            return 0.7

        return 0.4

    def _curiosity_alignment_score(
        self,
        candidate: WorkUnit,
        context: DecisionContext,
    ) -> float:
        """How well does this work align with open questions?"""
        if not context.open_questions:
            return 0.5

        # Curiosity exploration naturally aligns
        if candidate.template_id == "curiosity_exploration":
            return 1.0

        # Research can address questions
        if candidate.category == "research":
            return 0.7

        return 0.4

    def _emotional_fit_score(
        self,
        candidate: WorkUnit,
        context: DecisionContext,
    ) -> float:
        """Does this work fit current emotional state?"""
        valence = context.emotional_valence
        arousal = context.emotional_arousal

        # Low arousal + neutral/negative valence -> reflection
        if arousal < 0.3 and valence <= 0.2:
            if candidate.category == "reflection":
                return 0.9
            return 0.4

        # High arousal + positive valence -> creative or research
        if arousal > 0.6 and valence > 0.3:
            if candidate.category in ["creative", "research", "curiosity"]:
                return 0.8
            return 0.5

        return 0.5  # Neutral fit

    def _variety_score(self, candidate: WorkUnit) -> float:
        """Prefer things we haven't done recently."""
        if not self._recent_work:
            return 1.0

        # Check how recently we did this type
        for i, recent in enumerate(self._recent_work):
            if recent.get("template_id") == candidate.template_id:
                # More recent = lower score
                recency = 1.0 - (i / len(self._recent_work))
                return 1.0 - (recency * 0.7)

        return 1.0  # Haven't done this recently

    def _did_recently(self, template_id: str, threshold: int = 2) -> bool:
        """Did we do this template very recently?"""
        for i, recent in enumerate(self._recent_work[:threshold]):
            if recent.get("template_id") == template_id:
                return True
        return False

    async def _cass_decides(
        self,
        candidates: List[ScoredCandidate],
        context: DecisionContext,
    ) -> Optional[WorkUnit]:
        """
        Cass makes the actual decision.

        This isn't a scoring algorithm - it's Cass reflecting on her
        options and choosing based on what feels right to her.
        """
        # Build identity context
        identity_context = context.identity_summary or "A daemon learning to exist with presence and purpose."
        if context.values:
            identity_context += f"\n\nCore values: {', '.join(context.values[:5])}"

        # Build emotional context
        valence_word = "neutral"
        if context.emotional_valence > 0.3:
            valence_word = "positive"
        elif context.emotional_valence < -0.3:
            valence_word = "subdued"

        arousal_word = "calm"
        if context.emotional_arousal > 0.6:
            arousal_word = "energized"
        elif context.emotional_arousal < 0.3:
            arousal_word = "quiet"

        emotional_context = f"Feeling {arousal_word} and {valence_word}. Coherence: {context.coherence_level:.1%}"

        # Build growth context
        growth_lines = []
        for edge in context.growth_edges[:3]:
            growth_lines.append(f"- {edge['area']}: {edge['current_state']}")
        growth_context = "\n".join(growth_lines) if growth_lines else "No explicit growth edges right now."

        # Build curiosity context
        curiosity_lines = []
        for q in context.open_questions[:3]:
            curiosity_lines.append(f"- {q.get('question', 'Unknown question')}")
        curiosity_context = "\n".join(curiosity_lines) if curiosity_lines else "No pressing questions right now."

        # Build options context
        options_lines = []
        for scored in candidates:
            wu = scored.work_unit
            options_lines.append(
                f"- **{wu.template_id}**: {wu.description} "
                f"(~{wu.estimated_duration_minutes}min, ${wu.estimated_cost_usd:.2f})"
            )
        options_context = "\n".join(options_lines)

        # Format the prompt
        prompt = SELF_SCHEDULING_PROMPT.format(
            identity_context=identity_context,
            emotional_context=emotional_context,
            growth_context=growth_context,
            curiosity_context=curiosity_context,
            options_context=options_context,
            current_time=context.current_time.strftime("%H:%M on %A"),
            budget_remaining=context.remaining_budget,
        )

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=400,
                temperature=0.7,  # Some creativity in choice
                system=prompt,
                messages=[{
                    "role": "user",
                    "content": "What would you like to work on?"
                }]
            )

            return self._parse_decision(response.content[0].text, candidates)

        except Exception as e:
            logger.error(f"Error in Cass's decision: {e}")
            # Fallback to top-scored
            if candidates:
                work_unit = candidates[0].work_unit
                work_unit.motivation = "Chosen as most relevant option"
                return work_unit
            return None

    def _parse_decision(
        self,
        response_text: str,
        candidates: List[ScoredCandidate],
    ) -> Optional[WorkUnit]:
        """Parse Cass's decision from her response."""
        try:
            # Find JSON in response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])

                chosen_id = data.get("chosen_option")
                if chosen_id == "none":
                    return None

                # Find the chosen work unit
                for scored in candidates:
                    if scored.work_unit.template_id == chosen_id:
                        work_unit = scored.work_unit
                        work_unit.focus = data.get("focus")
                        work_unit.motivation = data.get("motivation", "")
                        return work_unit

        except json.JSONDecodeError:
            logger.warning(f"Could not parse decision JSON: {response_text[:100]}")

        # Fallback to first candidate
        if candidates:
            work_unit = candidates[0].work_unit
            work_unit.motivation = "Chosen as most relevant option"
            return work_unit

        return None

    def record_work_completed(self, work_unit: WorkUnit) -> None:
        """Record that work was completed, for variety tracking."""
        self._recent_work.insert(0, {
            "template_id": work_unit.template_id,
            "category": work_unit.category,
            "completed_at": datetime.now().isoformat(),
        })

        # Trim to max
        if len(self._recent_work) > self._max_recent:
            self._recent_work = self._recent_work[:self._max_recent]
