"""
Grimoire Manager

Integrates Grimoire spell execution with the Thymos system.
Loads spells, evaluates triggers, and executes matching spells.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field

from .ast import Spell, TimerTrigger
from .registry import SpellRegistry, SpellMatch
from .runtime import Spellcaster
from .context import (
    SpellContext,
    ThymosInterface,
    SchedulerInterface,
    AgentInterface,
    StorageInterface,
    GoalInterface,
    RuntimeServices,
)

# Optional cron support
try:
    from croniter import croniter
    CRON_AVAILABLE = True
except ImportError:
    CRON_AVAILABLE = False
    croniter = None

logger = logging.getLogger(__name__)


@dataclass
class SpellExecutionResult:
    """Result of executing a spell."""
    spell_name: str
    trigger_type: str
    status: str
    reason: Optional[str] = None
    execution_time_ms: float = 0.0
    trace: Optional[list[str]] = None


class GrimoireManager:
    """
    Manages Grimoire spell execution integrated with Thymos.

    Responsibilities:
    - Load spells from a directory
    - Evaluate triggers when Thymos state changes
    - Execute matching spells (respecting shadow mode and cooldowns)
    - Provide service interfaces to spells
    """

    def __init__(
        self,
        spells_directory: Optional[Path] = None,
        shadow_mode: bool = True,
        enable_trace: bool = False,
        daemon_id: Optional[str] = None,
    ):
        """
        Initialize the Grimoire manager.

        Args:
            spells_directory: Directory to load spells from
            shadow_mode: If True, don't execute external actions in spells
            enable_trace: If True, record execution traces
            daemon_id: Daemon ID for persistence (if None, state is memory-only)
        """
        self.registry = SpellRegistry()
        self.shadow_mode = shadow_mode
        self.enable_trace = enable_trace
        self.daemon_id = daemon_id

        # Spell execution cooldowns (spell_name -> last_execution_time)
        self._spell_cooldowns: dict[str, float] = {}

        # Timer trigger state (spell_name -> last_timer_execution_time)
        # Separate from cooldowns since timers have their own scheduling logic
        self._timer_last_run: dict[str, float] = {}

        # Service interfaces (set via configure_services)
        self._services: Optional[RuntimeServices] = None
        self._caster: Optional[Spellcaster] = None

        # Execution log
        self._execution_log: list[SpellExecutionResult] = []
        self._max_log_entries = 100

        # Phase queue manager reference (for QUEUE statements)
        self._phase_queue_manager: Optional[Any] = None

        # Load spells if directory provided
        if spells_directory:
            self.load_spells(spells_directory)

        # Load persisted state if daemon_id provided
        if daemon_id:
            self._load_persisted_state()

    def load_spells(self, directory: Path) -> int:
        """Load spells from a directory."""
        count = self.registry.load_directory(directory)
        logger.info(f"Grimoire loaded {count} spells from {directory}")
        return count

    def set_phase_queue_manager(self, manager: Any) -> None:
        """Set the phase queue manager for QUEUE statements."""
        self._phase_queue_manager = manager
        logger.info("Phase queue manager configured for Grimoire")

    def _load_persisted_state(self) -> None:
        """Load spell state from database."""
        if not self.daemon_id:
            return

        try:
            from .persistence import load_all_spell_states
            states = load_all_spell_states(self.daemon_id)

            for spell_name, state in states.items():
                if state["last_executed_at"]:
                    self._spell_cooldowns[spell_name] = state["last_executed_at"]
                if state["timer_last_run_at"]:
                    self._timer_last_run[spell_name] = state["timer_last_run_at"]

            if states:
                logger.info(f"Loaded persisted state for {len(states)} spell(s)")
        except Exception as e:
            logger.warning(f"Could not load Grimoire state: {e}")

    def _persist_spell_execution(
        self,
        spell_name: str,
        trigger_type: str,
        cooldown_time: Optional[float] = None,
        timer_time: Optional[float] = None,
    ) -> None:
        """Persist spell execution state to database."""
        if not self.daemon_id:
            return

        try:
            from .persistence import save_spell_state
            save_spell_state(
                self.daemon_id,
                spell_name,
                last_executed_at=cooldown_time,
                timer_last_run_at=timer_time,
            )
        except Exception as e:
            logger.warning(f"Could not persist spell state: {e}")

    def _log_execution_to_db(self, result: SpellExecutionResult) -> None:
        """Log execution to database."""
        if not self.daemon_id:
            return

        try:
            from .persistence import log_execution
            log_execution(
                self.daemon_id,
                result.spell_name,
                result.trigger_type,
                result.status,
                reason=result.reason,
                execution_time_ms=result.execution_time_ms,
                trace=result.trace,
            )
        except Exception as e:
            logger.warning(f"Could not log execution: {e}")

    def configure_services(
        self,
        thymos_runner: Any,  # ThymosRunner - avoid circular import
        scheduler: Optional[Any] = None,
        agent: Optional[Any] = None,
        self_manager: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        goal_manager: Optional[Any] = None,
    ) -> None:
        """
        Configure service interfaces for spell execution.

        Args:
            thymos_runner: The ThymosRunner instance
            scheduler: Optional scheduler for TASK actions
            agent: Optional agent client for agentic actions
            self_manager: Optional SelfManager for saving observations
            memory_manager: Optional MemoryManager for saving journals
            goal_manager: Optional UnifiedGoalManager for goal operations
        """
        # Build ThymosInterface from the runner
        thymos_interface = self._build_thymos_interface(thymos_runner)

        # Build SchedulerInterface
        scheduler_interface = self._build_scheduler_interface(scheduler)

        # Build AgentInterface
        agent_interface = self._build_agent_interface(agent)

        # Build StorageInterface
        storage_interface = self._build_storage_interface(self_manager, memory_manager)

        # Build GoalInterface
        goal_interface = self._build_goal_interface(goal_manager)

        # Create RuntimeServices
        self._services = RuntimeServices(
            thymos=thymos_interface,
            scheduler=scheduler_interface,
            agent=agent_interface,
            storage=storage_interface,
            goals=goal_interface,
            log_debug=lambda msg: logger.debug(f"[Spell] {msg}"),
            log_info=lambda msg: logger.info(f"[Spell] {msg}"),
            log_observation=lambda msg: logger.info(f"[Spell/Observation] {msg}"),
            current_time=time.time,
            load_spell=self._load_spell_by_name,
            queue_for_phase=self._queue_for_phase_bridge,
        )

        # Create Spellcaster
        self._caster = Spellcaster(self._services)
        logger.info("Grimoire services configured")

    def _build_thymos_interface(self, runner: Any) -> ThymosInterface:
        """Build ThymosInterface from a ThymosRunner."""
        # Import thymos modules (handle both relative and absolute)
        try:
            from ..thymos.dynamics import get_care_action_for_need
        except ImportError:
            from thymos.dynamics import get_care_action_for_need

        def get_affect(name: str) -> float:
            if runner is None or runner.affect is None:
                return 0.5
            state = runner.affect.state
            if state is None:
                return 0.5
            return getattr(state, name, 0.5)

        def get_need(name: str) -> float:
            if runner is None or runner.needs is None:
                return 0.5
            state = runner.needs.state
            if state is None:
                return 0.5
            need = getattr(state, name, None)
            if need:
                return need.current
            return 0.5

        def get_all_affects() -> dict[str, float]:
            if runner is None or runner.affect is None:
                return {}
            return runner.affect.to_dict()

        def get_all_needs() -> dict[str, Any]:
            if runner is None or runner.needs is None:
                return {}
            state = runner.needs.state
            if state is None:
                return {}
            return {
                "cognitive_rest": state.cognitive_rest,
                "social_connection": state.social_connection,
                "novelty_intake": state.novelty_intake,
                "creative_expression": state.creative_expression,
                "value_coherence": state.value_coherence,
                "competence_signal": state.competence_signal,
                "autonomy": state.autonomy,
            }

        def apply_affect_delta(deltas: dict[str, float]) -> None:
            try:
                from ..thymos.models import AffectDelta
            except ImportError:
                from thymos.models import AffectDelta
            delta = AffectDelta(deltas=deltas, source="grimoire")
            runner.affect.apply_delta(delta)

        def apply_need_delta(deltas: dict[str, float]) -> None:
            try:
                from ..thymos.models import NeedDelta
            except ImportError:
                from thymos.models import NeedDelta
            delta = NeedDelta(deltas=deltas, source="grimoire")
            runner.needs.apply_delta(delta)

        def reset_affects() -> None:
            try:
                from ..thymos.affect_vector import AffectVector
            except ImportError:
                from thymos.affect_vector import AffectVector
            runner.affect = AffectVector()

        def reset_needs() -> None:
            try:
                from ..thymos.needs_register import NeedsRegister
            except ImportError:
                from thymos.needs_register import NeedsRegister
            runner.needs = NeedsRegister()

        def reset_affect(name: str) -> None:
            state = runner.affect.state
            if hasattr(state, name):
                setattr(state, name, 0.5)

        def reset_need(name: str) -> None:
            state = runner.needs.state
            need = getattr(state, name, None)
            if need:
                need.current = need.preferred_high

        async def execute_care_action(key: str) -> dict[str, Any]:
            # This would trigger the actual care action
            # For now, just log and return success
            logger.info(f"Care action requested: {key}")
            return {"action": key, "status": "executed"}

        def get_care_action_for_need_fn(need_name: str) -> Optional[str]:
            action = get_care_action_for_need(need_name)
            return action.key if action else None

        return ThymosInterface(
            get_affect=get_affect,
            get_need=get_need,
            get_all_affects=get_all_affects,
            get_all_needs=get_all_needs,
            apply_affect_delta=apply_affect_delta,
            apply_need_delta=apply_need_delta,
            reset_affects=reset_affects,
            reset_needs=reset_needs,
            reset_affect=reset_affect,
            reset_need=reset_need,
            execute_care_action=execute_care_action,
            get_care_action_for_need=get_care_action_for_need_fn,
        )

    def _build_scheduler_interface(self, scheduler: Optional[Any]) -> SchedulerInterface:
        """Build SchedulerInterface."""
        async def execute_task(action: str, params: dict, await_completion: bool) -> dict:
            if scheduler and hasattr(scheduler, 'execute_action'):
                return await scheduler.execute_action(action, params, await_completion)
            logger.info(f"Scheduler task (no scheduler): {action} params={params}")
            return {"status": "no_scheduler", "action": action}

        async def emit_event(event_type: str, data: dict) -> None:
            if scheduler and hasattr(scheduler, 'emit_event'):
                await scheduler.emit_event(event_type, data)
            else:
                logger.info(f"Event emit (no scheduler): {event_type} data={data}")

        return SchedulerInterface(
            execute_task=execute_task,
            emit_event=emit_event,
        )

    def _build_agent_interface(self, agent: Optional[Any]) -> AgentInterface:
        """Build AgentInterface for agentic actions."""
        # Default implementations that work in shadow mode
        async def ask(question: str, context: dict) -> tuple[bool, str]:
            if agent and hasattr(agent, 'ask_yes_no'):
                return await agent.ask_yes_no(question, context)
            logger.debug(f"Agent ask (no agent): {question}")
            return False, "No agent configured"

        async def choose(prompt: str, options: list, context: dict) -> tuple[str, str]:
            if agent and hasattr(agent, 'choose'):
                return await agent.choose(prompt, options, context)
            logger.debug(f"Agent choose (no agent): {prompt}")
            return options[0][0] if options else "", "No agent configured"

        async def rate(prompt: str, context: dict) -> tuple[float, str]:
            if agent and hasattr(agent, 'rate'):
                return await agent.rate(prompt, context)
            logger.debug(f"Agent rate (no agent): {prompt}")
            return 0.5, "No agent configured"

        async def generate(prompt: str, context: dict) -> str:
            if agent and hasattr(agent, 'generate'):
                return await agent.generate(prompt, context)
            logger.debug(f"Agent generate (no agent): {prompt}")
            return f"[Generated: {prompt}]"

        async def reflect(prompt: str, context: dict, save_as: Optional[str]) -> str:
            if agent and hasattr(agent, 'reflect'):
                return await agent.reflect(prompt, context, save_as)
            logger.debug(f"Agent reflect (no agent): {prompt}")
            return f"[Reflection: {prompt}]"

        return AgentInterface(
            ask=ask,
            choose=choose,
            rate=rate,
            generate=generate,
            reflect=reflect,
        )

    def _build_storage_interface(
        self,
        self_manager: Optional[Any],
        memory_manager: Optional[Any],
    ) -> StorageInterface:
        """Build StorageInterface for saving observations and journals."""

        async def save_observation(
            observation: str,
            category: str,
            source_type: str,
        ) -> Optional[str]:
            """Save a self-observation."""
            if self_manager and hasattr(self_manager, 'add_observation'):
                try:
                    obs = self_manager.add_observation(
                        observation=observation,
                        category=category,
                        source_type=source_type,
                        influence_source="grimoire",
                    )
                    logger.info(f"Saved observation via grimoire: {obs.id}")
                    return obs.id
                except Exception as e:
                    logger.error(f"Failed to save observation: {e}")
                    return None
            logger.debug("No self_manager configured - observation not saved")
            return None

        async def save_journal(
            date: str,
            content: str,
        ) -> Optional[str]:
            """Save a journal entry."""
            if memory_manager and hasattr(memory_manager, 'store_journal_entry'):
                try:
                    journal_id = await memory_manager.store_journal_entry(
                        date=date,
                        journal_text=content,
                        summary_count=0,
                        conversation_count=0,
                    )
                    logger.info(f"Saved journal via grimoire: {journal_id}")
                    return journal_id
                except Exception as e:
                    logger.error(f"Failed to save journal: {e}")
                    return None
            logger.debug("No memory_manager configured - journal not saved")
            return None

        return StorageInterface(
            save_observation=save_observation,
            save_journal=save_journal,
        )

    def _build_goal_interface(self, goal_manager: Optional[Any]) -> GoalInterface:
        """Build GoalInterface for goal operations."""

        def get_actionable(limit: int = 10) -> list[dict[str, Any]]:
            """Get actionable goals."""
            if not goal_manager:
                return []
            try:
                goals = goal_manager.get_actionable_goals(limit=limit)
                return [g.to_dict() for g in goals]
            except Exception as e:
                logger.error(f"Failed to get actionable goals: {e}")
                return []

        def get_by_type(goal_type: str, active_only: bool = True) -> list[dict[str, Any]]:
            """Get goals by type."""
            if not goal_manager:
                return []
            try:
                goals = goal_manager.get_pending_by_type(goal_type, include_proposed=not active_only)
                return [g.to_dict() for g in goals]
            except Exception as e:
                logger.error(f"Failed to get goals by type: {e}")
                return []

        def create_goal(
            title: str,
            goal_type: str,
            created_by: str,
            description: str = "",
            priority: str = "P2",
        ) -> dict[str, Any]:
            """Create a new goal."""
            if not goal_manager:
                return {}
            try:
                goal = goal_manager.create_goal(
                    title=title,
                    goal_type=goal_type,
                    created_by=created_by,
                    description=description,
                    priority=priority,
                )
                return goal.to_dict()
            except Exception as e:
                logger.error(f"Failed to create goal: {e}")
                return {}

        def start_goal(goal_id: str) -> Optional[dict[str, Any]]:
            """Mark a goal as active."""
            if not goal_manager:
                return None
            try:
                goal = goal_manager.start_goal(goal_id)
                return goal.to_dict() if goal else None
            except Exception as e:
                logger.error(f"Failed to start goal: {e}")
                return None

        def complete_goal(goal_id: str, outcome: str = "") -> Optional[dict[str, Any]]:
            """Mark a goal as completed."""
            if not goal_manager:
                return None
            try:
                goal = goal_manager.complete_goal(goal_id, outcome_summary=outcome)
                return goal.to_dict() if goal else None
            except Exception as e:
                logger.error(f"Failed to complete goal: {e}")
                return None

        def abandon_goal(goal_id: str, reason: str = "") -> Optional[dict[str, Any]]:
            """Mark a goal as abandoned."""
            if not goal_manager:
                return None
            try:
                goal = goal_manager.abandon_goal(goal_id, reason=reason)
                return goal.to_dict() if goal else None
            except Exception as e:
                logger.error(f"Failed to abandon goal: {e}")
                return None

        def add_progress(goal_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
            """Add progress to a goal."""
            if not goal_manager:
                return None
            try:
                goal = goal_manager.add_progress(goal_id, data)
                return goal.to_dict() if goal else None
            except Exception as e:
                logger.error(f"Failed to add progress: {e}")
                return None

        def is_available() -> bool:
            """Check if goal system is available."""
            return goal_manager is not None

        return GoalInterface(
            get_actionable=get_actionable,
            get_by_type=get_by_type,
            create_goal=create_goal,
            start_goal=start_goal,
            complete_goal=complete_goal,
            abandon_goal=abandon_goal,
            add_progress=add_progress,
            is_available=is_available,
        )

    async def _load_spell_by_name(self, name: str) -> Optional[Spell]:
        """Load a spell by name (for CAST action)."""
        return self.registry.get_spell(name)

    async def _queue_for_phase_bridge(
        self,
        action: str,
        phase: str,
        priority: int,
        parameters: dict[str, Any],
        source_spell: str,
    ) -> bool:
        """
        Bridge function for QUEUE statements to PhaseQueueManager.

        Converts Grimoire-style parameters to PhaseQueueManager's WorkUnit format.
        """
        if not self._phase_queue_manager:
            logger.warning("No phase queue manager configured - cannot queue work")
            return False

        try:
            # Import scheduling modules
            from scheduling.day_phase import DayPhase
            from scheduling.templates import WORK_TEMPLATES
            from scheduling.work_unit import WorkUnit, WorkPriority

            # Map phase string to DayPhase enum
            phase_map = {
                "morning": DayPhase.MORNING,
                "afternoon": DayPhase.AFTERNOON,
                "evening": DayPhase.EVENING,
                "night": DayPhase.NIGHT,
            }
            target_phase = phase_map.get(phase.lower())
            if not target_phase:
                logger.error(f"Unknown phase: {phase}")
                return False

            # Check if action is a template ID
            template = WORK_TEMPLATES.get(action)
            if template:
                # Instantiate work unit from template
                work_unit = template.instantiate(
                    focus=parameters.get("focus"),
                    motivation=parameters.get("motivation", f"Queued by spell: {source_spell}"),
                    duration_override=parameters.get("duration"),
                    priority_override=WorkPriority(priority) if priority in range(5) else None,
                )
            else:
                # Create a simple work unit for direct action reference
                import uuid
                work_unit = WorkUnit(
                    id=str(uuid.uuid4()),
                    name=f"Spell-queued: {action}",
                    description=f"Queued by {source_spell}",
                    action_sequence=[action],  # Single action
                    template_id=None,
                    estimated_duration_minutes=parameters.get("duration", 15),
                    estimated_cost_usd=parameters.get("cost", 0.01),
                    priority=WorkPriority(priority) if priority in range(5) else WorkPriority.NORMAL,
                    focus=parameters.get("focus"),
                    motivation=parameters.get("motivation", f"Queued by spell: {source_spell}"),
                    category=parameters.get("category", "reflection"),
                )

            # Queue the work unit
            success = self._phase_queue_manager.queue_for_phase(
                work_unit=work_unit,
                target_phase=target_phase,
                priority=priority,
            )

            if success:
                logger.info(
                    f"Spell {source_spell} queued {action} for {phase} phase "
                    f"(priority {priority})"
                )
            return success

        except Exception as e:
            logger.error(f"Failed to queue work from spell: {e}", exc_info=True)
            return False

    # =========================================================================
    # TRIGGER EVALUATION AND EXECUTION
    # =========================================================================

    async def check_and_execute_need_triggers(
        self,
        needs: dict[str, float],
    ) -> list[SpellExecutionResult]:
        """
        Check need-based triggers and execute matching spells.

        Args:
            needs: Dictionary of need_name -> current_value

        Returns:
            List of execution results
        """
        if not self._caster:
            logger.warning("Grimoire not configured - skipping trigger check")
            return []

        matches = self.registry.check_need_triggers(needs)
        return await self._execute_matches(matches, "need")

    async def check_and_execute_affect_triggers(
        self,
        affects: dict[str, float],
    ) -> list[SpellExecutionResult]:
        """
        Check affect-based triggers and execute matching spells.

        Args:
            affects: Dictionary of affect_name -> current_value

        Returns:
            List of execution results
        """
        if not self._caster:
            logger.warning("Grimoire not configured - skipping trigger check")
            return []

        matches = self.registry.check_affect_triggers(affects)
        return await self._execute_matches(matches, "affect")

    async def check_and_execute_event_triggers(
        self,
        event_type: str,
        event_data: dict[str, Any],
    ) -> list[SpellExecutionResult]:
        """
        Check event-based triggers and execute matching spells.

        Args:
            event_type: The event type (e.g., "session.started")
            event_data: The event payload

        Returns:
            List of execution results
        """
        if not self._caster:
            logger.warning("Grimoire not configured - skipping trigger check")
            return []

        matches = self.registry.check_event_triggers(event_type, event_data)
        return await self._execute_matches(matches, "event")

    async def check_and_execute_timer_triggers(
        self,
        current_time: Optional[float] = None,
    ) -> list[SpellExecutionResult]:
        """
        Check timer-based triggers and execute due spells.

        Timer spells run on intervals (every N minutes) or cron schedules.
        Each timer tracks its own last-run time independently of cooldowns.

        Args:
            current_time: Current timestamp (defaults to time.time())

        Returns:
            List of execution results
        """
        if not self._caster:
            logger.warning("Grimoire not configured - skipping timer check")
            return []

        if current_time is None:
            current_time = time.time()

        results = []
        timer_spells = self.registry.get_timer_spells()

        for spell, trigger in timer_spells:
            spell_name = spell.metadata.name

            # Check if this timer is due
            if not self._is_timer_due(spell_name, trigger, current_time):
                continue

            # Also check regular cooldown
            if not self._check_cooldown(spell):
                logger.debug(f"Timer spell {spell_name} on cooldown - skipping")
                continue

            # Execute the spell
            result = await self._execute_spell(
                spell,
                {"trigger_type": "timer", "timestamp": current_time},
                "timer"
            )
            results.append(result)

            # Update timer last-run time and persist
            self._timer_last_run[spell_name] = current_time
            cooldown_time = None
            if spell.metadata.cooldown_minutes > 0:
                self._spell_cooldowns[spell_name] = current_time
                cooldown_time = current_time

            self._persist_spell_execution(
                spell_name,
                "timer",
                cooldown_time=cooldown_time,
                timer_time=current_time,
            )

        return results

    def _is_timer_due(
        self,
        spell_name: str,
        trigger: TimerTrigger,
        current_time: float,
    ) -> bool:
        """
        Check if a timer trigger is due to run.

        Args:
            spell_name: Name of the spell
            trigger: The TimerTrigger configuration
            current_time: Current timestamp

        Returns:
            True if the timer should fire
        """
        last_run = self._timer_last_run.get(spell_name, 0)

        # Handle interval-based timers
        if trigger.interval_minutes is not None:
            if last_run == 0:
                # First run - execute immediately
                logger.debug(f"Timer spell {spell_name}: first run")
                return True

            elapsed_minutes = (current_time - last_run) / 60.0
            if elapsed_minutes >= trigger.interval_minutes:
                logger.debug(
                    f"Timer spell {spell_name}: interval due "
                    f"({elapsed_minutes:.1f}m >= {trigger.interval_minutes}m)"
                )
                return True
            return False

        # Handle cron-based timers
        if trigger.cron_expr is not None:
            if not CRON_AVAILABLE:
                logger.warning(
                    f"Timer spell {spell_name} uses cron expression but croniter "
                    "is not installed. Install with: pip install croniter"
                )
                return False

            try:
                from datetime import datetime
                # Get the next scheduled time from the cron expression
                base_time = datetime.fromtimestamp(last_run) if last_run > 0 else datetime.now()
                cron = croniter(trigger.cron_expr, base_time)
                next_run = cron.get_next(float)

                if current_time >= next_run:
                    logger.debug(
                        f"Timer spell {spell_name}: cron due "
                        f"(cron={trigger.cron_expr})"
                    )
                    return True
                return False
            except Exception as e:
                logger.error(f"Invalid cron expression for {spell_name}: {e}")
                return False

        # No valid timer configuration
        logger.warning(f"Timer spell {spell_name} has no interval or cron configured")
        return False

    def get_timer_status(self) -> list[dict]:
        """
        Get status of all timer triggers.

        Returns:
            List of timer status dicts with spell name, config, and next run info
        """
        current_time = time.time()
        timer_spells = self.registry.get_timer_spells()
        status = []

        for spell, trigger in timer_spells:
            spell_name = spell.metadata.name
            last_run = self._timer_last_run.get(spell_name, 0)

            entry = {
                "spell_name": spell_name,
                "interval_minutes": trigger.interval_minutes,
                "cron_expr": trigger.cron_expr,
                "last_run": last_run,
                "last_run_ago_minutes": (current_time - last_run) / 60.0 if last_run > 0 else None,
            }

            # Calculate next run time for interval-based
            if trigger.interval_minutes is not None:
                if last_run == 0:
                    entry["next_run_in_minutes"] = 0  # Will run immediately
                else:
                    remaining = trigger.interval_minutes - ((current_time - last_run) / 60.0)
                    entry["next_run_in_minutes"] = max(0, remaining)
            elif trigger.cron_expr is not None and CRON_AVAILABLE:
                try:
                    from datetime import datetime
                    base_time = datetime.fromtimestamp(last_run) if last_run > 0 else datetime.now()
                    cron = croniter(trigger.cron_expr, base_time)
                    next_run = cron.get_next(float)
                    entry["next_run_in_minutes"] = max(0, (next_run - current_time) / 60.0)
                except Exception:
                    entry["next_run_in_minutes"] = None

            status.append(entry)

        return status

    async def execute_manual_spell(
        self,
        label: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[SpellExecutionResult]:
        """
        Execute a spell by its manual trigger label.

        Args:
            label: The manual trigger label
            context: Optional context data

        Returns:
            Execution result, or None if not found
        """
        if not self._caster:
            logger.warning("Grimoire not configured - cannot execute spell")
            return None

        spell = self.registry.find_manual_spell(label)
        if not spell:
            logger.warning(f"No spell found with manual trigger: {label}")
            return None

        return await self._execute_spell(spell, context or {}, "manual")

    async def _execute_matches(
        self,
        matches: list[SpellMatch],
        trigger_type: str,
    ) -> list[SpellExecutionResult]:
        """Execute matching spells, respecting cooldowns."""
        results = []

        for match in matches:
            spell = match.spell
            spell_name = spell.metadata.name

            # Check cooldown
            if not self._check_cooldown(spell):
                logger.debug(f"Spell {spell_name} on cooldown - skipping")
                continue

            # Execute
            result = await self._execute_spell(spell, match.trigger_data, trigger_type)
            results.append(result)

            # Set cooldown and persist
            if spell.metadata.cooldown_minutes > 0:
                now = time.time()
                self._spell_cooldowns[spell_name] = now
                self._persist_spell_execution(spell_name, trigger_type, cooldown_time=now)

        return results

    async def _execute_spell(
        self,
        spell: Spell,
        event_data: dict[str, Any],
        trigger_type: str,
    ) -> SpellExecutionResult:
        """Execute a single spell."""
        spell_name = spell.metadata.name
        start_time = time.time()

        logger.info(f"Grimoire executing spell: {spell_name} (trigger: {trigger_type})")

        try:
            result = await self._caster.cast(
                spell,
                event_data=event_data,
                shadow_mode=self.shadow_mode,
                trace=self.enable_trace,
            )

            execution_time = (time.time() - start_time) * 1000

            exec_result = SpellExecutionResult(
                spell_name=spell_name,
                trigger_type=trigger_type,
                status=result["status"],
                reason=result.get("reason"),
                execution_time_ms=execution_time,
                trace=result.get("trace"),
            )

            logger.info(
                f"Spell {spell_name} completed: {result['status']} "
                f"({execution_time:.1f}ms)"
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Spell {spell_name} failed: {e}")

            exec_result = SpellExecutionResult(
                spell_name=spell_name,
                trigger_type=trigger_type,
                status="error",
                reason=str(e),
                execution_time_ms=execution_time,
            )

        # Log execution (in-memory and database)
        self._execution_log.append(exec_result)
        if len(self._execution_log) > self._max_log_entries:
            self._execution_log.pop(0)

        # Persist to database
        self._log_execution_to_db(exec_result)

        return exec_result

    def _check_cooldown(self, spell: Spell) -> bool:
        """Check if a spell's cooldown has elapsed."""
        cooldown_minutes = spell.metadata.cooldown_minutes
        if cooldown_minutes <= 0:
            return True

        spell_name = spell.metadata.name
        last_execution = self._spell_cooldowns.get(spell_name, 0)
        elapsed_minutes = (time.time() - last_execution) / 60.0

        return elapsed_minutes >= cooldown_minutes

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def get_loaded_spells(self) -> list[dict]:
        """Get list of loaded spells."""
        return [
            {
                "name": spell.metadata.name,
                "author": spell.metadata.author,
                "priority": spell.metadata.priority,
                "cooldown_minutes": spell.metadata.cooldown_minutes,
                "tags": spell.metadata.tags,
                "trigger_count": len(spell.triggers),
                "statement_count": len(spell.body),
            }
            for spell in self.registry.spells.values()
        ]

    def get_execution_log(self, limit: int = 20) -> list[dict]:
        """Get recent spell executions."""
        log = list(reversed(self._execution_log[-limit:]))
        return [
            {
                "spell_name": r.spell_name,
                "trigger_type": r.trigger_type,
                "status": r.status,
                "reason": r.reason,
                "execution_time_ms": r.execution_time_ms,
            }
            for r in log
        ]

    def get_status(self) -> dict:
        """Get Grimoire manager status."""
        timer_spells = self.registry.get_timer_spells()
        return {
            "shadow_mode": self.shadow_mode,
            "trace_enabled": self.enable_trace,
            "spells_loaded": len(self.registry.spells),
            "services_configured": self._caster is not None,
            "recent_executions": len(self._execution_log),
            "timer_spells_count": len(timer_spells),
            "cron_support": CRON_AVAILABLE,
        }


# =============================================================================
# INTEGRATION HOOK
# =============================================================================

def create_grimoire_hooks(manager: GrimoireManager):
    """
    Create hooks for integrating Grimoire into ThymosRunner.

    Returns functions that can be called from the shadow runner's
    tick() and process_event() methods.
    """
    async def on_tick(affects: dict[str, float], needs: dict[str, float]) -> list[SpellExecutionResult]:
        """Called on each Thymos tick."""
        results = []

        # Check timer triggers (interval/cron based)
        timer_results = await manager.check_and_execute_timer_triggers()
        results.extend(timer_results)

        # Check need triggers
        need_results = await manager.check_and_execute_need_triggers(needs)
        results.extend(need_results)

        # Check affect triggers
        affect_results = await manager.check_and_execute_affect_triggers(affects)
        results.extend(affect_results)

        return results

    async def on_event(event_type: str, event_data: dict) -> list[SpellExecutionResult]:
        """Called when a Thymos event is processed."""
        return await manager.check_and_execute_event_triggers(event_type, event_data)

    return on_tick, on_event
