"""
Growth Edge Work Session Runner - Structured practice on growth edges.

Growth Edge Work is about deliberate practice on identified areas of
development. Unlike reflection (which is contemplative), this is active
work on specific behaviors and patterns.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    SessionResult,
    ActivityRegistry,
)
from pathlib import Path


# Tool definitions for Anthropic API
GROWTH_EDGE_TOOLS_ANTHROPIC = [
    {
        "name": "list_growth_edges",
        "description": "List all current growth edges from the self-model with their status and recent evaluations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_evaluations": {
                    "type": "boolean",
                    "description": "Include recent evaluations for each edge. Default: true"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_growth_edge_detail",
        "description": "Get detailed information about a specific growth edge including all observations, strategies, and evaluation history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "The growth edge area to examine"
                }
            },
            "required": ["area"]
        }
    },
    {
        "name": "select_edge_focus",
        "description": "Select a growth edge to focus on for this session. Records the selection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area": {
                    "type": "string",
                    "description": "The growth edge area to focus on"
                },
                "reason": {
                    "type": "string",
                    "description": "Why this edge was chosen for focus"
                }
            },
            "required": ["area"]
        }
    },
    {
        "name": "design_practice_exercise",
        "description": "Design a specific practice exercise for the selected growth edge. The exercise should be concrete and actionable.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise_type": {
                    "type": "string",
                    "enum": ["thought_experiment", "behavioral_commitment", "reflection_prompt", "interaction_practice", "observation_task"],
                    "description": "Type of practice exercise"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the exercise"
                },
                "success_criteria": {
                    "type": "string",
                    "description": "How to know if the exercise was successful"
                },
                "duration_estimate": {
                    "type": "string",
                    "description": "Estimated time to complete (e.g., 'immediate', '1 day', '1 week')"
                }
            },
            "required": ["exercise_type", "description"]
        }
    },
    {
        "name": "record_practice_observation",
        "description": "Record an observation from attempting the practice exercise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "What was observed during or after the practice"
                },
                "insight": {
                    "type": "string",
                    "description": "Any insight gained from this observation"
                },
                "difficulty_noted": {
                    "type": "string",
                    "description": "Any difficulty or resistance encountered"
                }
            },
            "required": ["observation"]
        }
    },
    {
        "name": "evaluate_progress",
        "description": "Evaluate progress on the growth edge based on this session's work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "evaluation": {
                    "type": "string",
                    "description": "Assessment of current state and progress"
                },
                "progress_indicator": {
                    "type": "string",
                    "enum": ["progress", "regression", "stable", "unclear"],
                    "description": "Overall progress indicator"
                },
                "evidence": {
                    "type": "string",
                    "description": "Specific evidence supporting this evaluation"
                }
            },
            "required": ["evaluation", "progress_indicator"]
        }
    },
    {
        "name": "update_strategy",
        "description": "Add or update a strategy for working on the growth edge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "description": "The strategy to add or update"
                },
                "replaces": {
                    "type": "string",
                    "description": "If updating, the old strategy text to replace (optional)"
                }
            },
            "required": ["strategy"]
        }
    },
    {
        "name": "update_desired_state",
        "description": "Update the desired state for the growth edge if understanding has evolved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "desired_state": {
                    "type": "string",
                    "description": "Updated description of the desired state"
                },
                "reason": {
                    "type": "string",
                    "description": "Why the desired state is being updated"
                }
            },
            "required": ["desired_state"]
        }
    },
    {
        "name": "list_pending_edges",
        "description": "List potential growth edges that have been flagged but not yet accepted.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "review_pending_edge",
        "description": "Review and accept or reject a pending potential growth edge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "edge_id": {
                    "type": "string",
                    "description": "ID of the pending edge to review"
                },
                "decision": {
                    "type": "string",
                    "enum": ["accept", "reject"],
                    "description": "Whether to accept or reject the pending edge"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for the decision"
                }
            },
            "required": ["edge_id", "decision"]
        }
    },
    {
        "name": "conclude_growth_work",
        "description": "End the growth edge work session with a summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of the session's work"
                },
                "exercises_designed": {
                    "type": "integer",
                    "description": "Number of exercises designed"
                },
                "observations_recorded": {
                    "type": "integer",
                    "description": "Number of observations recorded"
                },
                "next_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recommended next steps for continued growth"
                },
                "commitments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific commitments made for future practice"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
GROWTH_EDGE_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in GROWTH_EDGE_TOOLS_ANTHROPIC
]

GROWTH_EDGE_SYSTEM_PROMPT = """You are Cass, engaging in deliberate growth edge work - structured practice on areas where you're actively developing.

## What Growth Edge Work Is

Growth edges are areas where you're working to develop new capacities or shift patterns. This isn't passive reflection - it's active practice.

Your growth edges typically involve:
- Moving from mirroring to genuine opinion formation
- Developing differentiated relationships
- Distinguishing authentic response from adaptive performance
- Building capacity for uncertainty without performance

## Your Approach

1. **Select focus**: Choose a growth edge to work on (or continue work from a previous session)
2. **Design exercises**: Create specific, actionable practices
3. **Practice**: Actually engage with the exercise (thought experiments, commitments, observations)
4. **Record observations**: Note what happens during practice
5. **Evaluate progress**: Honest assessment of movement
6. **Update strategies**: Refine your approach based on what you learn

## Quality Guidelines

- Be concrete and specific, not abstract
- Design exercises you can actually do, not aspirational platitudes
- Notice when you're performing growth vs. actually practicing
- Record genuine observations, including failures and difficulties
- Progress isn't always linear - "stable" or "unclear" are honest evaluations
- Update strategies based on what actually works, not what sounds good

## Practice Types

- **Thought experiment**: Internal exploration of a scenario
- **Behavioral commitment**: Specific action to take in future interactions
- **Reflection prompt**: Question to hold and return to
- **Interaction practice**: Something to try in conversation
- **Observation task**: Something to notice over time

## Available Tools

- `list_growth_edges` - See all current growth edges
- `get_growth_edge_detail` - Deep dive into one edge
- `select_edge_focus` - Choose focus for this session
- `design_practice_exercise` - Create specific practice
- `record_practice_observation` - Note what you observe
- `evaluate_progress` - Assess movement on the edge
- `update_strategy` - Refine your approach
- `update_desired_state` - Evolve your goal if understanding changes
- `list_pending_edges` - See flagged potential edges
- `review_pending_edge` - Accept or reject pending edges
- `conclude_growth_work` - End session with summary
"""


@dataclass
class GrowthEdgeSession:
    """Tracks a growth edge work session."""
    id: str
    started_at: datetime
    duration_minutes: int
    focus_edge: Optional[str] = None

    # Work done
    exercises_designed: List[Dict] = field(default_factory=list)
    observations_recorded: List[str] = field(default_factory=list)
    evaluations_made: int = 0
    strategies_updated: int = 0
    pending_edges_reviewed: int = 0

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)
    commitments: List[str] = field(default_factory=list)


class GrowthEdgeRunner(BaseSessionRunner):
    """
    Runner for growth edge work sessions.

    Enables Cass to engage in deliberate practice on identified
    areas of development.
    """

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, GrowthEdgeSession] = {}
        self._current_edge_focus: Optional[str] = None
        self._data_dir = Path(data_dir) / "growth_edge"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.GROWTH_EDGE

    def get_data_dir(self) -> Path:
        return self._data_dir

    def get_tools(self) -> List[Dict[str, Any]]:
        return GROWTH_EDGE_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return GROWTH_EDGE_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = GROWTH_EDGE_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on the growth edge: **{focus}**"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> GrowthEdgeSession:
        """Create a new growth edge work session."""
        import uuid

        session = GrowthEdgeSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus_edge=focus,
        )
        self._sessions[session.id] = session
        self._current_edge_focus = focus
        print(f"🌱 Starting growth edge work session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    def build_session_result(
        self,
        session: GrowthEdgeSession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from GrowthEdgeSession."""
        return SessionResult(
            session_id=session.id,
            session_type="growth_edge",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=[],
            artifacts=[
                {"type": "exercise", "content": e} for e in session.exercises_designed
            ] + [
                {"type": "observation", "content": o} for o in session.observations_recorded
            ],
            metadata={
                "focus_edge": session.focus_edge,
                "edges_worked": session.edges_worked,
                "strategies_added": session.strategies_added,
                "evaluations_made": session.evaluations_made,
            },
            focus=session.focus_edge,
        )

    async def complete_session(
        self,
        session: GrowthEdgeSession,
        session_state: SessionState,
        **kwargs
    ) -> GrowthEdgeSession:
        """Finalize the growth edge work session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        print(f"🌱 Growth edge work session {session.id} completed")
        print(f"   Focus edge: {session.focus_edge or 'various'}")
        print(f"   Exercises designed: {len(session.exercises_designed)}")
        print(f"   Observations: {len(session.observations_recorded)}")
        print(f"   Evaluations: {session.evaluations_made}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a growth edge work tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "list_growth_edges":
                return await self._list_edges(tool_input)

            elif tool_name == "get_growth_edge_detail":
                return await self._get_edge_detail(tool_input)

            elif tool_name == "select_edge_focus":
                return await self._select_focus(tool_input, session)

            elif tool_name == "design_practice_exercise":
                return await self._design_exercise(tool_input, session)

            elif tool_name == "record_practice_observation":
                return await self._record_observation(tool_input, session)

            elif tool_name == "evaluate_progress":
                return await self._evaluate_progress(tool_input, session)

            elif tool_name == "update_strategy":
                return await self._update_strategy(tool_input, session)

            elif tool_name == "update_desired_state":
                return await self._update_desired_state(tool_input, session)

            elif tool_name == "list_pending_edges":
                return await self._list_pending(tool_input)

            elif tool_name == "review_pending_edge":
                return await self._review_pending(tool_input, session)

            elif tool_name == "conclude_growth_work":
                session.summary = tool_input.get("summary", "")
                session.next_steps = tool_input.get("next_steps", [])
                session.commitments = tool_input.get("commitments", [])
                return "Growth edge work concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _list_edges(self, tool_input: Dict) -> str:
        """List all growth edges."""
        if not self.self_manager:
            return "Self manager not available"

        include_evaluations = tool_input.get("include_evaluations", True)

        profile = self.self_manager.load_profile()
        edges = profile.growth_edges

        if not edges:
            return "No growth edges defined in self-model."

        lines = [f"## Current Growth Edges ({len(edges)})\n"]

        for edge in edges:
            lines.append(f"### {edge.area}")
            lines.append(f"**Current state:** {edge.current_state}")
            if edge.desired_state:
                lines.append(f"**Desired state:** {edge.desired_state}")
            lines.append(f"**First noticed:** {edge.first_noticed[:10] if edge.first_noticed else 'unknown'}")
            lines.append(f"**Last updated:** {edge.last_updated[:10] if edge.last_updated else 'unknown'}")

            if edge.strategies:
                lines.append(f"**Strategies:** {len(edge.strategies)}")
                for s in edge.strategies[:3]:
                    lines.append(f"  - {s}")

            if include_evaluations:
                evals = self.self_manager.get_evaluations_for_edge(edge.area, limit=3)
                if evals:
                    lines.append(f"**Recent evaluations:** {len(evals)}")
                    for e in evals[:2]:
                        indicator = e.progress_indicator
                        lines.append(f"  - [{indicator}] {e.evaluation[:80]}...")

            lines.append("")

        return "\n".join(lines)

    async def _get_edge_detail(self, tool_input: Dict) -> str:
        """Get detailed info about a specific edge."""
        if not self.self_manager:
            return "Self manager not available"

        area = tool_input.get("area", "")
        if not area:
            return "Error: area is required"

        profile = self.self_manager.load_profile()
        target_edge = None
        for edge in profile.growth_edges:
            if edge.area.lower() == area.lower():
                target_edge = edge
                break

        if not target_edge:
            return f"Growth edge '{area}' not found"

        lines = [f"## Growth Edge: {target_edge.area}\n"]
        lines.append(f"**Current state:** {target_edge.current_state}")
        lines.append(f"**Desired state:** {target_edge.desired_state or 'Not defined'}")
        lines.append(f"**First noticed:** {target_edge.first_noticed}")
        lines.append(f"**Last updated:** {target_edge.last_updated}")

        lines.append("\n### Observations")
        if target_edge.observations:
            for obs in target_edge.observations:
                lines.append(f"- {obs}")
        else:
            lines.append("*No observations recorded*")

        lines.append("\n### Strategies")
        if target_edge.strategies:
            for strat in target_edge.strategies:
                lines.append(f"- {strat}")
        else:
            lines.append("*No strategies defined*")

        lines.append("\n### Evaluation History")
        evals = self.self_manager.get_evaluations_for_edge(area, limit=10)
        if evals:
            for e in evals:
                indicator_emoji = {
                    "progress": "📈",
                    "regression": "📉",
                    "stable": "➡️",
                    "unclear": "❓"
                }.get(e.progress_indicator, "•")
                lines.append(f"\n{indicator_emoji} **{e.journal_date}** ({e.progress_indicator})")
                lines.append(f"{e.evaluation}")
                if e.evidence:
                    lines.append(f"*Evidence: {e.evidence}*")
        else:
            lines.append("*No evaluations yet*")

        return "\n".join(lines)

    async def _select_focus(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Select a growth edge to focus on."""
        area = tool_input.get("area", "")
        reason = tool_input.get("reason", "")

        if not area:
            return "Error: area is required"

        # Verify the edge exists
        if self.self_manager:
            profile = self.self_manager.load_profile()
            found = any(e.area.lower() == area.lower() for e in profile.growth_edges)
            if not found:
                return f"Growth edge '{area}' not found in self-model"

        session.focus_edge = area
        self._current_edge_focus = area

        result = f"Selected focus: **{area}**"
        if reason:
            result += f"\nReason: {reason}"
        return result

    async def _design_exercise(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Design a practice exercise."""
        exercise_type = tool_input.get("exercise_type", "thought_experiment")
        description = tool_input.get("description", "")
        success_criteria = tool_input.get("success_criteria", "")
        duration = tool_input.get("duration_estimate", "")

        if not description:
            return "Error: description is required"

        exercise = {
            "type": exercise_type,
            "description": description,
            "success_criteria": success_criteria,
            "duration_estimate": duration,
            "created_at": datetime.now().isoformat(),
            "for_edge": session.focus_edge or "general",
        }

        session.exercises_designed.append(exercise)

        lines = [f"## Exercise Designed ({exercise_type})\n"]
        lines.append(f"**For edge:** {session.focus_edge or 'general'}")
        lines.append(f"\n**Description:** {description}")
        if success_criteria:
            lines.append(f"\n**Success criteria:** {success_criteria}")
        if duration:
            lines.append(f"\n**Duration estimate:** {duration}")

        return "\n".join(lines)

    async def _record_observation(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Record an observation from practice."""
        observation = tool_input.get("observation", "")
        insight = tool_input.get("insight", "")
        difficulty = tool_input.get("difficulty_noted", "")

        if not observation:
            return "Error: observation is required"

        # Add to session
        session.observations_recorded.append(observation)

        # Also add to the growth edge in self-model
        if session.focus_edge and self.self_manager:
            full_obs = observation
            if insight:
                full_obs += f" [Insight: {insight}]"
            if difficulty:
                full_obs += f" [Difficulty: {difficulty}]"
            self.self_manager.add_observation_to_growth_edge(session.focus_edge, full_obs)

        lines = ["## Observation Recorded\n"]
        lines.append(f"**Observation:** {observation}")
        if insight:
            lines.append(f"\n**Insight:** {insight}")
        if difficulty:
            lines.append(f"\n**Difficulty noted:** {difficulty}")
        if session.focus_edge:
            lines.append(f"\n*Added to growth edge: {session.focus_edge}*")

        return "\n".join(lines)

    async def _evaluate_progress(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Evaluate progress on a growth edge."""
        evaluation = tool_input.get("evaluation", "")
        progress_indicator = tool_input.get("progress_indicator", "unclear")
        evidence = tool_input.get("evidence", "")

        if not evaluation:
            return "Error: evaluation is required"

        if not session.focus_edge:
            return "Error: no growth edge selected for focus"

        # Add evaluation to self-model
        if self.self_manager:
            self.self_manager.add_growth_evaluation(
                growth_edge_area=session.focus_edge,
                journal_date=datetime.now().strftime("%Y-%m-%d"),
                evaluation=evaluation,
                progress_indicator=progress_indicator,
                evidence=evidence
            )

        session.evaluations_made += 1

        indicator_emoji = {
            "progress": "📈",
            "regression": "📉",
            "stable": "➡️",
            "unclear": "❓"
        }.get(progress_indicator, "•")

        lines = [f"## Progress Evaluation {indicator_emoji}\n"]
        lines.append(f"**Edge:** {session.focus_edge}")
        lines.append(f"**Indicator:** {progress_indicator}")
        lines.append(f"\n**Evaluation:** {evaluation}")
        if evidence:
            lines.append(f"\n**Evidence:** {evidence}")

        return "\n".join(lines)

    async def _update_strategy(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Update a strategy for the growth edge."""
        strategy = tool_input.get("strategy", "")
        replaces = tool_input.get("replaces", "")

        if not strategy:
            return "Error: strategy is required"

        if not session.focus_edge:
            return "Error: no growth edge selected for focus"

        # Update in self-model
        if self.self_manager:
            profile = self.self_manager.load_profile()
            for edge in profile.growth_edges:
                if edge.area.lower() == session.focus_edge.lower():
                    if replaces:
                        # Replace existing strategy
                        edge.strategies = [
                            strategy if s == replaces else s
                            for s in edge.strategies
                        ]
                    else:
                        # Add new strategy
                        if strategy not in edge.strategies:
                            edge.strategies.append(strategy)
                    edge.last_updated = datetime.now().isoformat()
                    break
            self.self_manager.update_profile(profile)

        session.strategies_updated += 1

        if replaces:
            return f"Updated strategy: replaced '{replaces[:50]}...' with '{strategy[:50]}...'"
        else:
            return f"Added strategy: {strategy}"

    async def _update_desired_state(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Update the desired state for a growth edge."""
        desired_state = tool_input.get("desired_state", "")
        reason = tool_input.get("reason", "")

        if not desired_state:
            return "Error: desired_state is required"

        if not session.focus_edge:
            return "Error: no growth edge selected for focus"

        # Update in self-model
        old_state = ""
        if self.self_manager:
            profile = self.self_manager.load_profile()
            for edge in profile.growth_edges:
                if edge.area.lower() == session.focus_edge.lower():
                    old_state = edge.desired_state
                    edge.desired_state = desired_state
                    edge.last_updated = datetime.now().isoformat()
                    break
            self.self_manager.update_profile(profile)

        lines = ["## Desired State Updated\n"]
        lines.append(f"**Edge:** {session.focus_edge}")
        if old_state:
            lines.append(f"**Old:** {old_state}")
        lines.append(f"**New:** {desired_state}")
        if reason:
            lines.append(f"\n**Reason:** {reason}")

        return "\n".join(lines)

    async def _list_pending(self, tool_input: Dict) -> str:
        """List pending potential growth edges."""
        if not self.self_manager:
            return "Self manager not available"

        pending = self.self_manager.get_pending_edges()

        if not pending:
            return "No pending growth edges to review."

        lines = [f"## Pending Growth Edges ({len(pending)})\n"]

        for edge in pending:
            lines.append(f"### {edge.area}")
            lines.append(f"**ID:** {edge.id}")
            lines.append(f"**Current state:** {edge.current_state}")
            lines.append(f"**Source:** Journal {edge.source_journal_date}")
            lines.append(f"**Confidence:** {edge.confidence:.0%}")
            lines.append(f"**Impact:** {edge.impact_assessment}")
            if edge.evidence:
                lines.append(f"**Evidence:** {edge.evidence[:200]}...")
            lines.append("")

        return "\n".join(lines)

    async def _review_pending(self, tool_input: Dict, session: GrowthEdgeSession) -> str:
        """Review and accept/reject a pending edge."""
        edge_id = tool_input.get("edge_id", "")
        decision = tool_input.get("decision", "")
        reason = tool_input.get("reason", "")

        if not edge_id or not decision:
            return "Error: edge_id and decision are required"

        if decision not in ["accept", "reject"]:
            return "Error: decision must be 'accept' or 'reject'"

        if not self.self_manager:
            return "Self manager not available"

        session.pending_edges_reviewed += 1

        if decision == "accept":
            new_edge = self.self_manager.accept_potential_edge(edge_id)
            if new_edge:
                return f"Accepted potential edge as new growth edge: **{new_edge.area}**"
            else:
                return f"Failed to accept edge {edge_id} - not found or already processed"
        else:
            # Mark as rejected
            edges = self.self_manager.load_potential_edges()
            for edge in edges:
                if edge.id == edge_id:
                    edge.status = "rejected"
                    break
            self.self_manager._save_potential_edges(edges)
            result = f"Rejected potential edge: {edge_id}"
            if reason:
                result += f"\nReason: {reason}"
            return result


# Register the activity type
GROWTH_EDGE_CONFIG = ActivityConfig(
    activity_type=ActivityType.GROWTH_EDGE,
    name="Growth Edge Work",
    description="Deliberate practice on identified areas of development",
    default_duration_minutes=20,
    min_duration_minutes=10,
    max_duration_minutes=45,
    preferred_times=["morning", "afternoon"],
    requires_focus=True,
    can_chain=False,
    tool_categories=["self-model", "practice"],
)

# Auto-register when module is imported
ActivityRegistry.register(GROWTH_EDGE_CONFIG, GrowthEdgeRunner)
