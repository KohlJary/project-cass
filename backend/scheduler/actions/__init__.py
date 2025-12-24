"""
Atomic Actions - JSON-defined actions with Python handlers.

Actions are the atomic units of autonomous work. Each action:
- Has a JSON definition (metadata, cost, category)
- Has a Python handler function
- Returns a HandlerResult
- Can be invoked by Synkratos or composed into larger work units
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ActionDefinition:
    """An atomic action definition loaded from JSON."""
    id: str
    name: str
    description: str
    category: str
    handler: str  # Module.function path
    estimated_cost_usd: float = 0.0
    default_duration_minutes: int = 30
    priority: str = "normal"
    requires_idle: bool = False
    runner_key: Optional[str] = None  # For session actions
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """Result from executing an action."""
    success: bool
    message: str
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)


class ActionRegistry:
    """
    Registry for atomic actions.

    Loads action definitions from JSON and resolves handlers.
    """

    def __init__(self):
        self._definitions: Dict[str, ActionDefinition] = {}
        self._handlers: Dict[str, Callable] = {}
        self._runners: Dict[str, Any] = {}  # Injected session runners
        self._managers: Dict[str, Any] = {}  # Injected manager dependencies

    def load_definitions(self, json_path: Optional[Path] = None) -> int:
        """
        Load action definitions from JSON file.

        Args:
            json_path: Path to definitions.json. Defaults to same directory.

        Returns:
            Number of actions loaded.
        """
        if json_path is None:
            json_path = Path(__file__).parent / "definitions.json"

        if not json_path.exists():
            logger.warning(f"Action definitions not found: {json_path}")
            return 0

        try:
            with open(json_path) as f:
                data = json.load(f)

            for action_id, action_data in data.get("actions", {}).items():
                self._definitions[action_id] = ActionDefinition(
                    id=action_data.get("id", action_id),
                    name=action_data.get("name", action_id),
                    description=action_data.get("description", ""),
                    category=action_data.get("category", "other"),
                    handler=action_data.get("handler", ""),
                    estimated_cost_usd=action_data.get("estimated_cost_usd", 0.0),
                    default_duration_minutes=action_data.get("default_duration_minutes", 30),
                    priority=action_data.get("priority", "normal"),
                    requires_idle=action_data.get("requires_idle", False),
                    runner_key=action_data.get("runner_key"),
                )

            logger.info(f"Loaded {len(self._definitions)} action definitions")
            return len(self._definitions)

        except Exception as e:
            logger.error(f"Failed to load action definitions: {e}")
            return 0

    def register_handler(self, action_id: str, handler: Callable) -> None:
        """Register a handler function for an action."""
        self._handlers[action_id] = handler

    def set_runners(self, runners: Dict[str, Any]) -> None:
        """Inject session runners for session actions."""
        self._runners = runners

    def set_managers(self, managers: Dict[str, Any]) -> None:
        """Inject manager dependencies."""
        self._managers = managers

    def get_definition(self, action_id: str) -> Optional[ActionDefinition]:
        """Get action definition by ID."""
        return self._definitions.get(action_id)

    def get_all_definitions(self) -> Dict[str, ActionDefinition]:
        """Get all action definitions."""
        return self._definitions.copy()

    def get_by_category(self, category: str) -> Dict[str, ActionDefinition]:
        """Get all actions in a category."""
        return {
            k: v for k, v in self._definitions.items()
            if v.category == category
        }

    async def execute(
        self,
        action_id: str,
        duration_minutes: Optional[int] = None,
        **kwargs
    ) -> ActionResult:
        """
        Execute an action by ID.

        Args:
            action_id: The action to execute
            duration_minutes: Override default duration
            **kwargs: Additional arguments for the handler

        Returns:
            ActionResult with success status, message, cost, and data
        """
        import time

        definition = self._definitions.get(action_id)
        if not definition:
            return ActionResult(
                success=False,
                message=f"Unknown action: {action_id}"
            )

        handler = self._handlers.get(action_id)
        if not handler:
            # Try to auto-resolve handler from definition
            handler = self._resolve_handler(definition.handler)
            if handler:
                self._handlers[action_id] = handler
            else:
                return ActionResult(
                    success=False,
                    message=f"No handler registered for: {action_id}"
                )

        # Build context for handler
        duration = duration_minutes or definition.default_duration_minutes
        context = {
            "definition": definition,
            "duration_minutes": duration,
            "runners": self._runners,
            "managers": self._managers,
            **kwargs
        }

        start_time = time.time()

        try:
            result = await handler(context)
            elapsed = time.time() - start_time

            if isinstance(result, ActionResult):
                result.duration_seconds = elapsed
                return result
            elif isinstance(result, dict):
                return ActionResult(
                    success=result.get("success", True),
                    message=result.get("message", "Completed"),
                    cost_usd=result.get("cost_usd", 0.0),
                    duration_seconds=elapsed,
                    data=result.get("data", {})
                )
            else:
                return ActionResult(
                    success=True,
                    message="Completed",
                    duration_seconds=elapsed
                )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Action {action_id} failed: {e}")
            return ActionResult(
                success=False,
                message=f"Action failed: {e}",
                duration_seconds=elapsed
            )

    def _resolve_handler(self, handler_path: str) -> Optional[Callable]:
        """
        Try to resolve a handler from its module.function path.

        Handler path format: "module_name.function_name"
        Looks in scheduler.actions.{module_name}
        """
        if not handler_path or "." not in handler_path:
            return None

        module_name, func_name = handler_path.rsplit(".", 1)

        try:
            # Try importing from actions subpackage
            import importlib
            module = importlib.import_module(f"scheduler.actions.{module_name}")
            return getattr(module, func_name, None)
        except (ImportError, AttributeError) as e:
            logger.debug(f"Could not resolve handler {handler_path}: {e}")
            return None


# Global registry instance
_registry: Optional[ActionRegistry] = None


def get_action_registry() -> ActionRegistry:
    """Get or create the global action registry."""
    global _registry
    if _registry is None:
        _registry = ActionRegistry()
        _registry.load_definitions()
    return _registry


def init_action_registry(
    runners: Dict[str, Any] = None,
    managers: Dict[str, Any] = None
) -> ActionRegistry:
    """
    Initialize the action registry with dependencies.

    Call this at startup after runners/managers are available.
    """
    registry = get_action_registry()
    if runners:
        registry.set_runners(runners)
    if managers:
        registry.set_managers(managers)

    # Auto-register handlers
    _register_all_handlers(registry)

    return registry


def _register_all_handlers(registry: ActionRegistry) -> None:
    """Register all handler functions from handler modules."""
    try:
        from . import session_handlers
        from . import journal_handlers
        from . import memory_handlers
        from . import system_handlers
        from . import research_handlers
        from . import world_handlers
        from . import web_handlers
        from . import wiki_handlers
        from . import self_handlers
        from . import outreach_handlers

        # Session actions (12 total)
        registry.register_handler("session.reflection", session_handlers.reflection_action)
        registry.register_handler("session.synthesis", session_handlers.synthesis_action)
        registry.register_handler("session.meta_reflection", session_handlers.meta_reflection_action)
        registry.register_handler("session.consolidation", session_handlers.consolidation_action)
        registry.register_handler("session.growth_edge", session_handlers.growth_edge_action)
        registry.register_handler("session.curiosity", session_handlers.curiosity_action)
        registry.register_handler("session.world_state", session_handlers.world_state_action)
        registry.register_handler("session.research", session_handlers.research_action)
        registry.register_handler("session.knowledge_building", session_handlers.knowledge_building_action)
        registry.register_handler("session.writing", session_handlers.writing_action)
        registry.register_handler("session.creative", session_handlers.creative_action)
        registry.register_handler("session.user_synthesis", session_handlers.user_synthesis_action)

        # Journal actions
        registry.register_handler("journal.generate_daily", journal_handlers.generate_daily_action)
        registry.register_handler("dream.nightly", journal_handlers.nightly_dream_action)

        # Memory actions
        registry.register_handler("memory.summarize_conversation", memory_handlers.summarize_conversation_action)
        registry.register_handler("memory.summarize_idle_conversations", memory_handlers.summarize_idle_conversations_action)

        # System actions
        registry.register_handler("system.github_metrics", system_handlers.github_metrics_action)

        # Research actions
        registry.register_handler("research.run_batch", research_handlers.run_batch_action)
        registry.register_handler("research.run_single", research_handlers.run_single_action)
        registry.register_handler("research.refresh_queue", research_handlers.refresh_queue_action)

        # World actions (granular)
        registry.register_handler("world.fetch_news", world_handlers.fetch_news_action)
        registry.register_handler("world.fetch_weather", world_handlers.fetch_weather_action)
        registry.register_handler("world.search_events", world_handlers.search_events_action)

        # Web actions (granular)
        registry.register_handler("web.search", web_handlers.web_search_action)
        registry.register_handler("web.fetch_url", web_handlers.fetch_url_action)

        # Wiki actions (granular)
        registry.register_handler("wiki.create_note", wiki_handlers.create_note_action)
        registry.register_handler("wiki.update_note", wiki_handlers.update_note_action)

        # Self actions (granular)
        registry.register_handler("self.add_observation", self_handlers.add_observation_action)
        registry.register_handler("self.record_insight", self_handlers.record_insight_action)
        registry.register_handler("self.update_growth_edge", self_handlers.update_growth_edge_action)

        # Outreach actions
        registry.register_handler("outreach.draft", outreach_handlers.draft_outreach_action)
        registry.register_handler("outreach.submit", outreach_handlers.submit_outreach_action)
        registry.register_handler("outreach.send_email", outreach_handlers.send_email_action)
        registry.register_handler("outreach.check_track_record", outreach_handlers.check_track_record_action)
        registry.register_handler("outreach.get_stats", outreach_handlers.get_outreach_stats_action)

        logger.info("Registered all action handlers")

    except ImportError as e:
        logger.warning(f"Some handler modules not available: {e}")
