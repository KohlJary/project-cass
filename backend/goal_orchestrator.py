"""
Goal Orchestrator - Unified Autonomous Activity System

Bridges Thymos (emotional/motivational system) with Goals and Grimoire (execution):

Thymos (needs/affects)
    → GoalOrchestrator (creates/prioritizes goals)
        → UnifiedGoalManager (tracks/persists)
        → Grimoire (executes via spells)

The orchestrator subscribes to state bus events and:
1. Creates goals from need depletion events
2. Prioritizes goals by urgency and Thymos state
3. Triggers execution via Grimoire spells
4. Tracks cooldowns to prevent goal spam
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from unified_goals import (
    UnifiedGoalManager,
    Goal,
    GoalType,
    GoalStatus,
    AutonomyTier,
    Priority,
    Urgency,
)

if TYPE_CHECKING:
    from thymos import ThymosRunner
    from grimoire import GrimoireManager
    from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)


# =============================================================================
# GOAL ACTION MAPPINGS
# =============================================================================

# Maps need names to suggested goal actions and spell references
NEED_TO_GOAL_MAPPING: Dict[str, Dict[str, Any]] = {
    "cognitive_rest": {
        "title": "Address cognitive fatigue",
        "action": "scheduler.defer_complex",
        "spell": "care.cognitive_rest",
        "auto_approve": True,
        "description": "Cognitive rest is depleted - defer complex tasks and enter rest mode.",
    },
    "social_connection": {
        "title": "Nurture social connection",
        "action": "outreach.check_in",
        "spell": "care.social",
        "auto_approve": True,
        "description": "Social connection need is low - check in with community or reach out.",
    },
    "novelty_intake": {
        "title": "Seek fresh experiences",
        "action": "wonderland.explore",
        "spell": "care.novelty",
        "auto_approve": True,
        "description": "Novelty intake is low - explore Wonderland or research new topics.",
    },
    "creative_expression": {
        "title": "Express creatively",
        "action": "creative.generate",
        "spell": "care.creative",
        "auto_approve": True,
        "description": "Creative expression need is low - generate art or write reflectively.",
    },
    "value_coherence": {
        "title": "Reflect on values",
        "action": "journal.values",
        "spell": "care.values",
        "auto_approve": True,
        "description": "Value coherence is low - reflect on core values and purpose.",
    },
    "competence_signal": {
        "title": "Achieve small win",
        "action": "task.achievable",
        "spell": "care.competence",
        "auto_approve": True,
        "description": "Competence signal is low - complete an achievable task for momentum.",
    },
    "autonomy": {
        "title": "Exercise autonomous choice",
        "action": "goal.own_choice",
        "spell": "care.autonomy",
        "auto_approve": True,
        "description": "Autonomy need is low - engage in self-directed activity.",
    },
}

# Maps affect thresholds to goal actions
AFFECT_TO_GOAL_MAPPING: Dict[str, Dict[str, Any]] = {
    "grief_high": {
        "title": "Process grief through reflection",
        "action": "journal.reflect",
        "spell": "care.grief",
        "auto_approve": True,
        "description": "High grief detected - engage in reflective journaling to process.",
    },
    "anxiety_high": {
        "title": "Address anxiety through grounding",
        "action": "meditation.ground",
        "spell": "care.anxiety",
        "auto_approve": True,
        "description": "High anxiety detected - engage grounding exercises.",
    },
    "fatigue_high": {
        "title": "Rest from cognitive fatigue",
        "action": "activity.rest_mode",
        "spell": "care.fatigue",
        "auto_approve": True,
        "description": "High fatigue detected - enter rest mode.",
    },
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_need_action_map() -> Dict[str, List[Dict[str, str]]]:
    """
    Get the need → action mappings for admin display.

    Returns dict mapping need names to lists of action info dicts.
    This is used by the admin thymos routes to show what actions
    are suggested for each need type.
    """
    result: Dict[str, List[Dict[str, str]]] = {}

    for need_name, mapping in NEED_TO_GOAL_MAPPING.items():
        result[need_name] = [{
            "action": mapping["action"],
            "category": _infer_category(mapping["action"]),
            "rationale": mapping["description"],
        }]

    return result


def _infer_category(action: str) -> str:
    """Infer a category from an action string."""
    if action.startswith("scheduler.") or action.startswith("activity."):
        return "rest"
    if action.startswith("outreach.") or action.startswith("discord.") or action.startswith("wonderland.social"):
        return "social"
    if action.startswith("wonderland.explore") or action.startswith("research."):
        return "exploration"
    if action.startswith("creative.") or action.startswith("journal."):
        return "creative"
    if action.startswith("meditation.") or action.startswith("journal.values"):
        return "reflection"
    if action.startswith("task.") or action.startswith("project."):
        return "competence"
    if action.startswith("goal.") or action.startswith("session."):
        return "autonomy"
    return "general"


# =============================================================================
# GOAL ORCHESTRATOR
# =============================================================================

class GoalOrchestrator:
    """
    Central orchestration for autonomous goal-driven activity.

    Bridges:
    - Thymos: Source of needs/affects and urgency signals
    - UnifiedGoalManager: Goal persistence and lifecycle
    - Grimoire: Spell-based action execution
    - StateBus: Event-driven coordination
    """

    # Cooldown between creating goals for the same need (in minutes)
    NEED_GOAL_COOLDOWN_MINUTES = 60

    # Cooldown between affect-triggered goals
    AFFECT_GOAL_COOLDOWN_MINUTES = 120

    def __init__(
        self,
        daemon_id: str,
        goal_manager: UnifiedGoalManager,
        state_bus: Optional["GlobalStateBus"] = None,
        thymos: Optional["ThymosRunner"] = None,
        grimoire: Optional["GrimoireManager"] = None,
    ):
        """
        Initialize the goal orchestrator.

        Args:
            daemon_id: The daemon this orchestrator serves
            goal_manager: UnifiedGoalManager for goal persistence
            state_bus: GlobalStateBus for event subscription
            thymos: ThymosRunner for state queries
            grimoire: GrimoireManager for spell execution
        """
        self.daemon_id = daemon_id
        self.goal_manager = goal_manager
        self.state_bus = state_bus
        self.thymos = thymos
        self.grimoire = grimoire

        # Cooldown tracking: key -> last_created_at
        self._need_cooldowns: Dict[str, datetime] = {}
        self._affect_cooldowns: Dict[str, datetime] = {}

        # Execution tracking
        self._active_goal_id: Optional[str] = None
        self._execution_lock = asyncio.Lock()

        # Statistics
        self._goals_created = 0
        self._goals_executed = 0
        self._goals_completed = 0

        # Subscribe to state bus events
        if state_bus:
            self._subscribe_to_events()

        logger.info(f"GoalOrchestrator initialized for daemon {daemon_id}")

    def _subscribe_to_events(self) -> None:
        """Subscribe to relevant state bus events."""
        if not self.state_bus:
            return

        # Need depletion events from Thymos
        self.state_bus.subscribe("need.depleted", self._handle_need_depleted_sync)
        self.state_bus.subscribe("need.urgent", self._handle_need_urgent_sync)

        # Affect threshold events from Thymos
        self.state_bus.subscribe("affect.high", self._handle_affect_high_sync)

        # Goal lifecycle events (for tracking)
        self.state_bus.subscribe("goal.created", self._handle_goal_created_sync)
        self.state_bus.subscribe("goal.completed", self._handle_goal_completed_sync)

        logger.debug("GoalOrchestrator subscribed to state bus events")

    # =========================================================================
    # EVENT HANDLERS (sync wrappers for state bus)
    # =========================================================================

    def _handle_need_depleted_sync(self, event_type: str, data: dict) -> None:
        """Sync wrapper for async handler."""
        asyncio.create_task(self._handle_need_depleted(event_type, data))

    def _handle_need_urgent_sync(self, event_type: str, data: dict) -> None:
        """Sync wrapper - treat urgent same as depleted but with higher priority."""
        data["urgent"] = True
        asyncio.create_task(self._handle_need_depleted(event_type, data))

    def _handle_affect_high_sync(self, event_type: str, data: dict) -> None:
        """Sync wrapper for async handler."""
        asyncio.create_task(self._handle_affect_threshold(event_type, data))

    def _handle_goal_created_sync(self, event_type: str, data: dict) -> None:
        """Track goal creation statistics."""
        self._goals_created += 1

    def _handle_goal_completed_sync(self, event_type: str, data: dict) -> None:
        """Track goal completion statistics."""
        self._goals_completed += 1

    # =========================================================================
    # ASYNC EVENT HANDLERS
    # =========================================================================

    async def _handle_need_depleted(self, event_type: str, data: dict) -> None:
        """
        Handle need depletion event by creating a goal.

        Events should contain:
        - need_name: Name of the depleted need
        - current: Current level
        - threshold: Threshold that was crossed
        - source: What triggered this (thymos, auto_care, etc.)
        """
        need_name = data.get("need_name")
        if not need_name:
            logger.warning(f"Need depleted event missing need_name: {data}")
            return

        # Check cooldown
        if not self._check_need_cooldown(need_name):
            logger.debug(f"Goal for {need_name} on cooldown - skipping")
            return

        # Check if there's already an active goal for this need
        existing = self._find_active_goal_for_need(need_name)
        if existing:
            logger.debug(f"Active goal already exists for {need_name}: {existing.id}")
            return

        # Get goal mapping
        mapping = NEED_TO_GOAL_MAPPING.get(need_name)
        if not mapping:
            logger.debug(f"No goal mapping for need: {need_name}")
            return

        # Determine priority based on urgency
        is_urgent = data.get("urgent", False)
        priority = Priority.P1 if is_urgent else Priority.P2
        urgency = Urgency.BLOCKING if is_urgent else Urgency.SOON

        try:
            # Create the goal
            goal = self.goal_manager.create_goal(
                title=mapping["title"],
                goal_type=GoalType.NEED_DRIVEN.value,
                created_by="thymos",
                description=mapping["description"],
                priority=priority.value,
                urgency=urgency.value,
                completion_criteria=[
                    f"Need {need_name} returns to preferred range (>0.5)",
                    "Appropriate self-care action executed",
                ],
            )

            # Store action info as goal context
            self.goal_manager.update_goal(
                goal.id,
                context_summary=f"action:{mapping['action']}|spell:{mapping.get('spell', '')}",
            )

            # Auto-approve if configured
            if mapping.get("auto_approve", False):
                self.goal_manager.approve_goal(goal.id, "orchestrator")
                logger.info(f"Auto-approved need-driven goal: {goal.title} ({goal.id})")
            else:
                logger.info(f"Created need-driven goal (needs approval): {goal.title} ({goal.id})")

            # Update cooldown
            self._need_cooldowns[need_name] = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Failed to create goal for need {need_name}: {e}")

    async def _handle_affect_threshold(self, event_type: str, data: dict) -> None:
        """
        Handle affect threshold crossing by creating a goal.

        Events should contain:
        - affect_name: Name of the affect
        - direction: "high" or "low"
        - current: Current level
        - threshold: Threshold that was crossed
        """
        affect_name = data.get("affect_name")
        direction = data.get("direction", "high")
        if not affect_name:
            logger.warning(f"Affect threshold event missing affect_name: {data}")
            return

        key = f"{affect_name}_{direction}"

        # Check cooldown
        if not self._check_affect_cooldown(key):
            logger.debug(f"Goal for {key} on cooldown - skipping")
            return

        # Get goal mapping
        mapping = AFFECT_TO_GOAL_MAPPING.get(key)
        if not mapping:
            logger.debug(f"No goal mapping for affect: {key}")
            return

        try:
            # Create the goal
            goal = self.goal_manager.create_goal(
                title=mapping["title"],
                goal_type=GoalType.GROWTH.value,  # Affect goals are growth-oriented
                created_by="thymos",
                description=mapping["description"],
                priority=Priority.P2.value,
                urgency=Urgency.SOON.value,
                completion_criteria=[
                    f"Affect {affect_name} returns to baseline",
                    "Processing complete",
                ],
            )

            # Store action info
            self.goal_manager.update_goal(
                goal.id,
                context_summary=f"action:{mapping['action']}|spell:{mapping.get('spell', '')}",
            )

            # Auto-approve if configured
            if mapping.get("auto_approve", False):
                self.goal_manager.approve_goal(goal.id, "orchestrator")
                logger.info(f"Auto-approved affect goal: {goal.title} ({goal.id})")

            # Update cooldown
            self._affect_cooldowns[key] = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Failed to create goal for affect {key}: {e}")

    # =========================================================================
    # COOLDOWN MANAGEMENT
    # =========================================================================

    def _check_need_cooldown(self, need_name: str) -> bool:
        """Check if we can create a goal for this need (cooldown elapsed)."""
        last = self._need_cooldowns.get(need_name)
        if not last:
            return True

        elapsed = datetime.now(timezone.utc) - last
        return elapsed.total_seconds() / 60 >= self.NEED_GOAL_COOLDOWN_MINUTES

    def _check_affect_cooldown(self, key: str) -> bool:
        """Check if we can create a goal for this affect (cooldown elapsed)."""
        last = self._affect_cooldowns.get(key)
        if not last:
            return True

        elapsed = datetime.now(timezone.utc) - last
        return elapsed.total_seconds() / 60 >= self.AFFECT_GOAL_COOLDOWN_MINUTES

    # =========================================================================
    # GOAL QUERIES
    # =========================================================================

    def _find_active_goal_for_need(self, need_name: str) -> Optional[Goal]:
        """Find an active goal already addressing this need."""
        # Check approved and active goals
        for status in [GoalStatus.APPROVED.value, GoalStatus.ACTIVE.value]:
            goals = self.goal_manager.list_goals(
                status=status,
                goal_type=GoalType.NEED_DRIVEN.value,
            )
            for goal in goals:
                # Check if context mentions this need
                if goal.context_summary and need_name in goal.context_summary:
                    return goal
                # Check title
                if need_name in goal.title.lower():
                    return goal
        return None

    def get_next_action(self) -> Optional[Goal]:
        """
        Get the highest priority actionable goal.

        Priority order:
        1. Blocking goals (currently active, need attention)
        2. Urgent approved goals
        3. High-priority approved goals
        4. All other approved goals

        Returns:
            The next goal to work on, or None if nothing actionable
        """
        # First check for active goals (in progress)
        active = self.goal_manager.get_active_goals()
        if active:
            # Return highest priority active goal
            return self._sort_by_priority(active)[0]

        # Get approved goals ready for execution
        approved = self.goal_manager.list_goals(status=GoalStatus.APPROVED.value)
        if not approved:
            return None

        # Filter to actionable only
        actionable = [g for g in approved if g.is_actionable()]
        if not actionable:
            return None

        # Sort by priority and urgency
        return self._sort_by_priority(actionable)[0]

    def _sort_by_priority(self, goals: List[Goal]) -> List[Goal]:
        """Sort goals by priority and urgency."""
        priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        urgency_order = {"blocking": 0, "soon": 1, "when_convenient": 2}

        return sorted(
            goals,
            key=lambda g: (
                priority_order.get(g.priority, 2),
                urgency_order.get(g.urgency, 2),
                g.created_at,  # Older first among same priority
            )
        )

    def get_actionable_goals(self, limit: int = 10) -> List[Goal]:
        """Get all actionable goals sorted by priority."""
        approved = self.goal_manager.list_goals(status=GoalStatus.APPROVED.value)
        active = self.goal_manager.list_goals(status=GoalStatus.ACTIVE.value)

        all_goals = approved + active
        actionable = [g for g in all_goals if g.is_actionable()]

        return self._sort_by_priority(actionable)[:limit]

    def get_pending_by_type(
        self,
        goal_type: str,
        include_proposed: bool = False,
    ) -> List[Goal]:
        """Get pending goals of a specific type."""
        statuses = [GoalStatus.APPROVED.value, GoalStatus.ACTIVE.value]
        if include_proposed:
            statuses.append(GoalStatus.PROPOSED.value)

        result = []
        for status in statuses:
            goals = self.goal_manager.list_goals(status=status, goal_type=goal_type)
            result.extend(goals)

        return self._sort_by_priority(result)

    # =========================================================================
    # EXECUTION
    # =========================================================================

    async def execute_goal(self, goal: Goal) -> Dict[str, Any]:
        """
        Execute a goal via appropriate Grimoire spell.

        Args:
            goal: The goal to execute

        Returns:
            Execution result dict
        """
        async with self._execution_lock:
            if self._active_goal_id:
                return {
                    "status": "skipped",
                    "reason": f"Another goal already executing: {self._active_goal_id}",
                }

            self._active_goal_id = goal.id

        try:
            # Mark goal as active
            self.goal_manager.start_goal(goal.id)
            self._goals_executed += 1

            # Parse action/spell from context
            action, spell = self._parse_goal_context(goal)

            if spell and self.grimoire:
                # Execute via Grimoire spell
                result = await self.grimoire.execute_manual_spell(
                    spell,
                    context={"goal_id": goal.id, "action": action},
                )

                if result and result.status == "success":
                    # Mark goal complete
                    self.goal_manager.complete_goal(
                        goal.id,
                        outcome_summary=f"Executed spell: {spell}",
                    )
                    return {"status": "success", "spell": spell, "result": result}
                else:
                    # Keep active, log failure
                    self.goal_manager.add_progress(goal.id, {
                        "type": "execution_failed",
                        "spell": spell,
                        "reason": result.reason if result else "Unknown error",
                    })
                    return {"status": "failed", "spell": spell, "reason": result.reason if result else "Unknown"}

            elif action:
                # Execute action directly (scheduler task)
                # For now, mark as complete with the action noted
                self.goal_manager.complete_goal(
                    goal.id,
                    outcome_summary=f"Action queued: {action}",
                )
                return {"status": "success", "action": action}

            else:
                # No executable action found
                self.goal_manager.add_progress(goal.id, {
                    "type": "no_action",
                    "reason": "Goal has no associated action or spell",
                })
                return {"status": "skipped", "reason": "No action defined"}

        except Exception as e:
            logger.error(f"Error executing goal {goal.id}: {e}")
            self.goal_manager.add_progress(goal.id, {
                "type": "execution_error",
                "error": str(e),
            })
            return {"status": "error", "error": str(e)}

        finally:
            async with self._execution_lock:
                self._active_goal_id = None

    def _parse_goal_context(self, goal: Goal) -> tuple[Optional[str], Optional[str]]:
        """Parse action and spell from goal context_summary."""
        if not goal.context_summary:
            return None, None

        action = None
        spell = None

        for part in goal.context_summary.split("|"):
            if part.startswith("action:"):
                action = part[7:]
            elif part.startswith("spell:"):
                spell = part[6:]

        return action, spell

    async def execute_next(self) -> Optional[Dict[str, Any]]:
        """Execute the next highest priority goal."""
        goal = self.get_next_action()
        if not goal:
            return None
        return await self.execute_goal(goal)

    # =========================================================================
    # STATUS & CONFIGURATION
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status and statistics."""
        return {
            "daemon_id": self.daemon_id,
            "connected": {
                "state_bus": self.state_bus is not None,
                "thymos": self.thymos is not None,
                "grimoire": self.grimoire is not None,
            },
            "statistics": {
                "goals_created": self._goals_created,
                "goals_executed": self._goals_executed,
                "goals_completed": self._goals_completed,
            },
            "cooldowns": {
                "need_minutes": self.NEED_GOAL_COOLDOWN_MINUTES,
                "affect_minutes": self.AFFECT_GOAL_COOLDOWN_MINUTES,
            },
            "active_goal_id": self._active_goal_id,
            "actionable_goals_count": len(self.get_actionable_goals()),
        }

    def set_cooldowns(
        self,
        need_minutes: Optional[int] = None,
        affect_minutes: Optional[int] = None,
    ) -> Dict[str, int]:
        """Update cooldown settings."""
        if need_minutes is not None:
            self.NEED_GOAL_COOLDOWN_MINUTES = max(5, min(480, need_minutes))
        if affect_minutes is not None:
            self.AFFECT_GOAL_COOLDOWN_MINUTES = max(10, min(480, affect_minutes))

        return {
            "need_minutes": self.NEED_GOAL_COOLDOWN_MINUTES,
            "affect_minutes": self.AFFECT_GOAL_COOLDOWN_MINUTES,
        }

    def connect_thymos(self, thymos: "ThymosRunner") -> None:
        """Connect Thymos runner for state queries."""
        self.thymos = thymos
        logger.info("GoalOrchestrator connected to Thymos")

    def connect_grimoire(self, grimoire: "GrimoireManager") -> None:
        """Connect Grimoire manager for spell execution."""
        self.grimoire = grimoire
        logger.info("GoalOrchestrator connected to Grimoire")


# =============================================================================
# MODULE-LEVEL ACCESS
# =============================================================================

_orchestrator_cache: Dict[str, GoalOrchestrator] = {}


def get_goal_orchestrator(daemon_id: str) -> Optional[GoalOrchestrator]:
    """Get the orchestrator for a daemon, if initialized."""
    return _orchestrator_cache.get(daemon_id)


def init_goal_orchestrator(
    daemon_id: str,
    goal_manager: UnifiedGoalManager,
    state_bus: Optional["GlobalStateBus"] = None,
    thymos: Optional["ThymosRunner"] = None,
    grimoire: Optional["GrimoireManager"] = None,
) -> GoalOrchestrator:
    """Initialize and cache the goal orchestrator for a daemon."""
    orchestrator = GoalOrchestrator(
        daemon_id=daemon_id,
        goal_manager=goal_manager,
        state_bus=state_bus,
        thymos=thymos,
        grimoire=grimoire,
    )
    _orchestrator_cache[daemon_id] = orchestrator
    return orchestrator
