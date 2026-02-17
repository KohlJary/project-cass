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

from .ast import Spell
from .registry import SpellRegistry, SpellMatch
from .runtime import Spellcaster
from .context import (
    SpellContext,
    ThymosInterface,
    SchedulerInterface,
    AgentInterface,
    RuntimeServices,
)

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
    ):
        """
        Initialize the Grimoire manager.

        Args:
            spells_directory: Directory to load spells from
            shadow_mode: If True, don't execute external actions in spells
            enable_trace: If True, record execution traces
        """
        self.registry = SpellRegistry()
        self.shadow_mode = shadow_mode
        self.enable_trace = enable_trace

        # Spell execution cooldowns (spell_name -> last_execution_time)
        self._spell_cooldowns: dict[str, float] = {}

        # Service interfaces (set via configure_services)
        self._services: Optional[RuntimeServices] = None
        self._caster: Optional[Spellcaster] = None

        # Execution log
        self._execution_log: list[SpellExecutionResult] = []
        self._max_log_entries = 100

        # Load spells if directory provided
        if spells_directory:
            self.load_spells(spells_directory)

    def load_spells(self, directory: Path) -> int:
        """Load spells from a directory."""
        count = self.registry.load_directory(directory)
        logger.info(f"Grimoire loaded {count} spells from {directory}")
        return count

    def configure_services(
        self,
        thymos_runner: Any,  # ThymosShadowRunner - avoid circular import
        scheduler: Optional[Any] = None,
        agent: Optional[Any] = None,
    ) -> None:
        """
        Configure service interfaces for spell execution.

        Args:
            thymos_runner: The ThymosShadowRunner instance
            scheduler: Optional scheduler for TASK actions
            agent: Optional agent client for agentic actions
        """
        # Build ThymosInterface from the runner
        thymos_interface = self._build_thymos_interface(thymos_runner)

        # Build SchedulerInterface
        scheduler_interface = self._build_scheduler_interface(scheduler)

        # Build AgentInterface
        agent_interface = self._build_agent_interface(agent)

        # Create RuntimeServices
        self._services = RuntimeServices(
            thymos=thymos_interface,
            scheduler=scheduler_interface,
            agent=agent_interface,
            log_debug=lambda msg: logger.debug(f"[Spell] {msg}"),
            log_info=lambda msg: logger.info(f"[Spell] {msg}"),
            log_observation=lambda msg: logger.info(f"[Spell/Observation] {msg}"),
            current_time=time.time,
            load_spell=self._load_spell_by_name,
        )

        # Create Spellcaster
        self._caster = Spellcaster(self._services)
        logger.info("Grimoire services configured")

    def _build_thymos_interface(self, runner: Any) -> ThymosInterface:
        """Build ThymosInterface from a ThymosShadowRunner."""
        # Import thymos modules (handle both relative and absolute)
        try:
            from ..thymos.dynamics import get_care_action_for_need
        except ImportError:
            from thymos.dynamics import get_care_action_for_need

        def get_affect(name: str) -> float:
            state = runner.affect.state
            return getattr(state, name, 0.5)

        def get_need(name: str) -> float:
            state = runner.needs.state
            need = getattr(state, name, None)
            if need:
                return need.current
            return 0.5

        def get_all_affects() -> dict[str, float]:
            return runner.affect.to_dict()

        def get_all_needs() -> dict[str, Any]:
            state = runner.needs.state
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

    async def _load_spell_by_name(self, name: str) -> Optional[Spell]:
        """Load a spell by name (for CAST action)."""
        return self.registry.get_spell(name)

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

            # Set cooldown
            if spell.metadata.cooldown_minutes > 0:
                self._spell_cooldowns[spell_name] = time.time()

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

        # Log execution
        self._execution_log.append(exec_result)
        if len(self._execution_log) > self._max_log_entries:
            self._execution_log.pop(0)

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
        return {
            "shadow_mode": self.shadow_mode,
            "trace_enabled": self.enable_trace,
            "spells_loaded": len(self.registry.spells),
            "services_configured": self._caster is not None,
            "recent_executions": len(self._execution_log),
        }


# =============================================================================
# INTEGRATION HOOK
# =============================================================================

def create_grimoire_hooks(manager: GrimoireManager):
    """
    Create hooks for integrating Grimoire into ThymosShadowRunner.

    Returns functions that can be called from the shadow runner's
    tick() and process_event() methods.
    """
    async def on_tick(affects: dict[str, float], needs: dict[str, float]) -> list[SpellExecutionResult]:
        """Called on each Thymos tick."""
        results = []

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
