"""
Goal Planner - Decomposes goals into sub-goals using registered capabilities.

This is the generic goal planning system that:
1. Queries the state bus for registered planning capabilities
2. Uses LLM to decompose goals into sub-goals based on available capabilities
3. Creates sub-goals as children in the unified goal system
4. Optionally creates tasks for atomic action sequences

Architecture:
- Goal (unified_goals.py) = Strategic objective
- Sub-Goal (child of goal) = Milestone
- Task (task_manager.py) = Atomic action step

The planner doesn't know about specific domains (Wonderland, Library, etc.)
until they register their capabilities. This makes it extensible.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import anthropic

from config import ANTHROPIC_API_KEY
from unified_goals import (
    UnifiedGoalManager, Goal, GoalType, GoalStatus,
    LinkType, Priority, Urgency
)
from task_manager import TaskManager, Task, Priority as TaskPriority
from planning_source import PlanningSchema, PlanningCapabilitySource

if TYPE_CHECKING:
    from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)


# Template for generating sub-goals
SUBGOAL_GENERATION_PROMPT = """You are helping decompose a goal into actionable sub-goals.

## The Goal
Title: {goal_title}
Description: {goal_description}
Type: {goal_type}

## Available Capabilities
{capabilities_context}

## Instructions
Break this goal into 3-6 concrete sub-goals (milestones). Each should:
- Be specific and achievable using the available capabilities
- Build logically toward the main goal
- Use the domains, actions, and entities available

Sub-goal types (pick the most appropriate):
- visit_domain: Go to a specific domain/realm
- visit_location: Go to a specific location within a domain
- interact_entity: Interact with a specific entity (NPC, item, etc.)
- explore: Discover and observe in an area
- accomplish: Complete a specific objective
- reflect: Pause for contemplation or processing

Output JSON:
{{
  "subgoals": [
    {{
      "title": "Short descriptive title",
      "description": "What this accomplishes and why",
      "subgoal_type": "visit_domain|visit_location|interact_entity|explore|accomplish|reflect",
      "target_domain": "domain name or null",
      "target_entity": "entity name or null",
      "priority": "P1|P2|P3"
    }}
  ],
  "reasoning": "Brief explanation of why you structured the plan this way"
}}
"""


class GoalPlanner:
    """
    Generic goal planner that uses registered capabilities.

    Does not hardcode any domain knowledge - learns capabilities
    from registered PlanningCapabilitySources via the state bus.
    """

    def __init__(
        self,
        daemon_id: str,
        state_bus: Optional["GlobalStateBus"] = None,
        api_key: str = None,
        model: str = "claude-3-5-haiku-20241022",
    ):
        self._daemon_id = daemon_id
        self._state_bus = state_bus
        self._client = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self._model = model
        self._goal_manager = UnifiedGoalManager(daemon_id)
        self._task_manager = TaskManager(daemon_id)

        # Planning capability sources (registered via state bus or directly)
        self._planning_sources: Dict[str, PlanningCapabilitySource] = {}

    def register_planning_source(self, source: PlanningCapabilitySource) -> None:
        """
        Register a planning capability source directly.

        Alternative to state bus registration for simpler setups.
        """
        self._planning_sources[source.source_id] = source
        source.on_registered()
        logger.info(f"GoalPlanner: Registered planning source '{source.source_id}'")

    def unregister_planning_source(self, source_id: str) -> None:
        """Unregister a planning source."""
        if source_id in self._planning_sources:
            source = self._planning_sources[source_id]
            source.on_unregistered()
            del self._planning_sources[source_id]

    def get_available_capabilities(self) -> Dict[str, PlanningSchema]:
        """
        Get all available planning capabilities.

        Returns dict mapping source_id to schema.
        """
        schemas = {}
        for source_id, source in self._planning_sources.items():
            try:
                schemas[source_id] = source.get_planning_schema()
            except Exception as e:
                logger.error(f"Error getting schema from {source_id}: {e}")
        return schemas

    def get_capabilities_context(self, goal: Goal) -> str:
        """
        Build LLM context describing available capabilities.

        Filters to capabilities relevant to the goal type/tags.
        """
        schemas = self.get_available_capabilities()

        if not schemas:
            return "No planning capabilities registered. Generate generic sub-goals."

        lines = []
        for source_id, schema in schemas.items():
            lines.append(schema.describe_for_llm())
            lines.append("")

        return "\n".join(lines)

    async def generate_subgoals(
        self,
        parent_goal: Goal,
    ) -> List[Dict]:
        """
        Generate sub-goal suggestions using LLM.

        Returns list of sub-goal dicts (not yet persisted).
        """
        capabilities_context = self.get_capabilities_context(parent_goal)

        prompt = SUBGOAL_GENERATION_PROMPT.format(
            goal_title=parent_goal.title,
            goal_description=parent_goal.description or parent_goal.title,
            goal_type=parent_goal.goal_type,
            capabilities_context=capabilities_context,
        )

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=800,
            temperature=0.7,
            system=prompt,
            messages=[{"role": "user", "content": "Generate sub-goals for this goal."}]
        )

        text = response.content[0].text
        return self._parse_subgoals_response(text)

    def _parse_subgoals_response(self, text: str) -> List[Dict]:
        """Parse LLM response into sub-goal dicts."""
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)
                return data.get("subgoals", [])
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse subgoals JSON: {e}")
        return []

    async def create_plan(
        self,
        parent_goal_id: str,
        session_context: Optional[Dict] = None,
    ) -> List[Goal]:
        """
        Create sub-goals for a goal.

        1. Get the parent goal
        2. Generate sub-goals via LLM using registered capabilities
        3. Create child goals in unified_goals system
        4. Link them to parent

        Args:
            parent_goal_id: ID of the goal to decompose
            session_context: Optional context (session_id, user_id, etc.)

        Returns:
            List of created child Goal objects.
        """
        parent_goal = self._goal_manager.get_goal(parent_goal_id)
        if not parent_goal:
            logger.error(f"Parent goal not found: {parent_goal_id}")
            return []

        # Generate sub-goals
        subgoal_dicts = await self.generate_subgoals(parent_goal)

        if not subgoal_dicts:
            logger.warning(f"No sub-goals generated for {parent_goal_id}")
            return []

        # Create child goals
        created_goals = []
        for i, sg in enumerate(subgoal_dicts):
            try:
                child_goal = self._goal_manager.create_goal(
                    title=sg.get("title", f"Sub-goal {i+1}"),
                    goal_type=GoalType.INITIATIVE.value,
                    created_by="planner",
                    description=sg.get("description"),
                    parent_id=parent_goal_id,
                    priority=sg.get("priority", Priority.P2.value),
                    urgency=Urgency.SOON.value,
                    completion_criteria=[sg.get("description", "Complete this milestone")],
                )

                # Store metadata in progress
                self._goal_manager.add_progress(child_goal.id, {
                    "type": "subgoal_metadata",
                    "subgoal_type": sg.get("subgoal_type", "accomplish"),
                    "target_domain": sg.get("target_domain"),
                    "target_entity": sg.get("target_entity"),
                    "session_context": session_context,
                })

                # Add parent-child links
                self._goal_manager.add_goal_link(
                    parent_goal_id,
                    child_goal.id,
                    LinkType.CHILD.value,
                )
                self._goal_manager.add_goal_link(
                    child_goal.id,
                    parent_goal_id,
                    LinkType.PARENT.value,
                )

                # Auto-approve (low autonomy planning goals)
                self._goal_manager.approve_goal(child_goal.id, "auto")

                created_goals.append(child_goal)
                logger.info(f"Created sub-goal: {child_goal.title} (parent={parent_goal_id})")

            except Exception as e:
                logger.error(f"Failed to create sub-goal: {e}")

        return created_goals

    def get_subgoals(self, parent_goal_id: str) -> List[Goal]:
        """Get all sub-goals for a parent goal."""
        all_goals = self._goal_manager.list_goals(limit=100)
        return [g for g in all_goals if g.parent_id == parent_goal_id]

    def get_current_subgoal(self, parent_goal_id: str) -> Optional[Goal]:
        """Get the first incomplete sub-goal."""
        subgoals = self.get_subgoals(parent_goal_id)

        # Sort by priority then creation time
        def sort_key(g):
            priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
            return (priority_order.get(g.priority, 2), g.created_at)

        subgoals.sort(key=sort_key)

        for sg in subgoals:
            if sg.status not in [GoalStatus.COMPLETED.value, GoalStatus.ABANDONED.value]:
                return sg
        return None

    def get_subgoal_metadata(self, goal: Goal) -> Dict:
        """Extract subgoal metadata from progress entries."""
        for entry in goal.progress:
            if entry.get("type") == "subgoal_metadata":
                return {
                    "subgoal_type": entry.get("subgoal_type", "accomplish"),
                    "target_domain": entry.get("target_domain"),
                    "target_entity": entry.get("target_entity"),
                    "session_context": entry.get("session_context"),
                }
        return {"subgoal_type": "accomplish", "target_domain": None, "target_entity": None}

    def start_subgoal(self, subgoal_id: str) -> Optional[Goal]:
        """Mark a sub-goal as active."""
        return self._goal_manager.start_goal(subgoal_id)

    def complete_subgoal(
        self,
        subgoal_id: str,
        outcome: str = None,
    ) -> Optional[Goal]:
        """Mark a sub-goal as completed."""
        return self._goal_manager.complete_goal(
            subgoal_id,
            outcome_summary=outcome or "Completed"
        )

    def get_progress_summary(self, parent_goal_id: str) -> Dict:
        """Get progress summary for a goal and its sub-goals."""
        parent = self._goal_manager.get_goal(parent_goal_id)
        subgoals = self.get_subgoals(parent_goal_id)

        completed = sum(1 for sg in subgoals if sg.status == GoalStatus.COMPLETED.value)
        total = len(subgoals)

        current = self.get_current_subgoal(parent_goal_id)

        return {
            "parent_goal": parent.title if parent else None,
            "parent_status": parent.status if parent else None,
            "total_subgoals": total,
            "completed_subgoals": completed,
            "progress_text": f"{completed}/{total} milestones complete" if total else "No milestones",
            "current_subgoal": current.title if current else None,
            "current_subgoal_id": current.id if current else None,
            "current_subgoal_type": self.get_subgoal_metadata(current).get("subgoal_type") if current else None,
        }

    # === Route/Task Planning ===

    def create_route_tasks(
        self,
        user_id: str,
        subgoal_id: str,
        source_id: str,
        from_location: str,
        to_target: str,
    ) -> List[Task]:
        """
        Create tasks for a route using a planning source's pathfinding.

        Args:
            user_id: Owner of the tasks
            subgoal_id: Sub-goal these tasks fulfill
            source_id: Planning source to use for routing
            from_location: Starting point
            to_target: Destination

        Returns:
            List of created Task objects
        """
        source = self._planning_sources.get(source_id)
        if not source:
            logger.error(f"Planning source not found: {source_id}")
            return []

        # Get route from source
        route_steps = source.get_route(from_location, to_target)
        if not route_steps:
            logger.warning(f"No route found from {from_location} to {to_target}")
            return []

        # Create tasks
        created_tasks = []
        for i, step in enumerate(route_steps):
            task = self._task_manager.add(
                user_id=user_id,
                description=step.get("description", step.get("action", f"Step {i+1}")),
                priority=TaskPriority.MEDIUM,
                tags=[source_id, "route", f"subgoal:{subgoal_id}"],
                project=source_id,
                notes=json.dumps({
                    "action": step.get("action"),
                    "subgoal_id": subgoal_id,
                    "step_index": i,
                }),
            )
            created_tasks.append(task)

        return created_tasks

    def get_pending_tasks(
        self,
        user_id: str,
        subgoal_id: str,
    ) -> List[Task]:
        """Get pending tasks for a sub-goal."""
        tasks = self._task_manager.list_tasks(
            user_id=user_id,
            filter_str=f"+route",
            include_completed=False,
        )
        return [t for t in tasks if f"subgoal:{subgoal_id}" in t.tags]

    def complete_task(self, user_id: str, task_id: str) -> Optional[Task]:
        """Mark a task as completed."""
        return self._task_manager.complete(user_id, task_id)
