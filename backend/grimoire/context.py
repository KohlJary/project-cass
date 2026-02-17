"""
Grimoire Execution Context

Manages state during spell execution:
- Variable scopes
- Call stack (for GOSUB/RETURN)
- Thymos state access
- Loop context (for BREAK/CONTINUE)
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable
from enum import Enum, auto

from .ast import Spell, Statement


class ExitStatus(Enum):
    """How a spell execution ended."""
    RUNNING = auto()
    SUCCESS = auto()
    FAILURE = auto()
    SKIPPED = auto()


@dataclass
class LoopContext:
    """Context for a loop (FOR, WHILE, FOR EACH)."""
    loop_type: str  # "for", "while", "for_each"
    should_break: bool = False
    should_continue: bool = False


@dataclass
class CallFrame:
    """A frame in the call stack (for GOSUB/RETURN)."""
    return_index: int  # Statement index to return to
    label: str  # Label that was called


@dataclass
class SpellContext:
    """
    Execution context for a spell.

    Tracks all runtime state during spell execution.
    """
    spell: Spell

    # Current execution position
    current_index: int = 0

    # Variables (local to this execution)
    variables: dict[str, Any] = field(default_factory=dict)

    # Call stack for GOSUB/RETURN
    call_stack: list[CallFrame] = field(default_factory=list)

    # Loop stack for BREAK/CONTINUE
    loop_stack: list[LoopContext] = field(default_factory=list)

    # Exit status
    exit_status: ExitStatus = ExitStatus.RUNNING
    exit_reason: Optional[str] = None

    # Event data (if triggered by event)
    event_data: dict[str, Any] = field(default_factory=dict)

    # Execution trace (for debugging)
    trace: list[str] = field(default_factory=list)
    trace_enabled: bool = False

    # Shadow mode - if True, don't execute external actions
    shadow_mode: bool = True

    def set_variable(self, name: str, value: Any) -> None:
        """Set a variable value."""
        self.variables[name] = value

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a variable value."""
        return self.variables.get(name, default)

    def has_variable(self, name: str) -> bool:
        """Check if a variable exists."""
        return name in self.variables

    def push_call(self, return_index: int, label: str) -> None:
        """Push a call frame for GOSUB."""
        self.call_stack.append(CallFrame(return_index=return_index, label=label))

    def pop_call(self) -> Optional[CallFrame]:
        """Pop a call frame for RETURN."""
        if self.call_stack:
            return self.call_stack.pop()
        return None

    def push_loop(self, loop_type: str) -> LoopContext:
        """Push a loop context."""
        ctx = LoopContext(loop_type=loop_type)
        self.loop_stack.append(ctx)
        return ctx

    def pop_loop(self) -> Optional[LoopContext]:
        """Pop a loop context."""
        if self.loop_stack:
            return self.loop_stack.pop()
        return None

    def current_loop(self) -> Optional[LoopContext]:
        """Get current loop context."""
        if self.loop_stack:
            return self.loop_stack[-1]
        return None

    def signal_break(self) -> None:
        """Signal a BREAK in current loop."""
        if self.loop_stack:
            self.loop_stack[-1].should_break = True

    def signal_continue(self) -> None:
        """Signal a CONTINUE in current loop."""
        if self.loop_stack:
            self.loop_stack[-1].should_continue = True

    def exit(self, status: ExitStatus, reason: Optional[str] = None) -> None:
        """Exit the spell with given status."""
        self.exit_status = status
        self.exit_reason = reason

    def is_running(self) -> bool:
        """Check if spell is still running."""
        return self.exit_status == ExitStatus.RUNNING

    def add_trace(self, message: str) -> None:
        """Add a trace message if tracing is enabled."""
        if self.trace_enabled:
            self.trace.append(message)


@dataclass
class ThymosInterface:
    """
    Interface to Thymos state.

    Provides read/write access to affects and needs.
    This is injected into the runtime to avoid tight coupling.
    """
    # Callbacks for reading state
    get_affect: Callable[[str], float]
    get_need: Callable[[str], float]
    get_all_affects: Callable[[], dict[str, float]]
    get_all_needs: Callable[[], dict[str, Any]]  # Returns Need objects

    # Callbacks for writing state
    apply_affect_delta: Callable[[dict[str, float]], None]
    apply_need_delta: Callable[[dict[str, float]], None]

    # Reset
    reset_affects: Callable[[], None]
    reset_needs: Callable[[], None]
    reset_affect: Callable[[str], None]
    reset_need: Callable[[str], None]

    # Self-care
    execute_care_action: Callable[[str], Awaitable[dict[str, Any]]]
    get_care_action_for_need: Callable[[str], Optional[str]]


@dataclass
class SchedulerInterface:
    """
    Interface to the scheduler.

    Allows spells to invoke scheduler tasks.
    """
    # Execute a task
    execute_task: Callable[[str, dict[str, Any], bool], Awaitable[dict[str, Any]]]

    # Emit an event
    emit_event: Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class AgentInterface:
    """
    Interface to the LLM agent.

    For agentic nodes (ASK, CHOOSE, RATE, GENERATE, REFLECT).
    """
    # Ask yes/no question
    ask: Callable[[str, dict[str, Any]], Awaitable[tuple[bool, str]]]

    # Multiple choice
    choose: Callable[[str, list[tuple[str, str]], dict[str, Any]], Awaitable[tuple[str, str]]]

    # Rate something
    rate: Callable[[str, dict[str, Any]], Awaitable[tuple[float, str]]]

    # Generate content
    generate: Callable[[str, dict[str, Any]], Awaitable[str]]

    # Reflect
    reflect: Callable[[str, dict[str, Any], Optional[str]], Awaitable[str]]


async def _noop_save_observation(obs: str, cat: str, src: str) -> Optional[str]:
    """Default no-op save observation."""
    return None


async def _noop_save_journal(date: str, content: str) -> Optional[str]:
    """Default no-op save journal."""
    return None


@dataclass
class StorageInterface:
    """
    Interface for persistent storage.

    Used by REFLECT...SAVE AS and standalone SAVE actions.
    """
    # Save a self-observation
    # Args: observation_text, category, source_type
    # Returns: observation_id or None on failure
    save_observation: Callable[
        [str, str, str],
        Awaitable[Optional[str]]
    ] = field(default=_noop_save_observation)

    # Save a journal entry
    # Args: date (YYYY-MM-DD), content
    # Returns: journal_id or None on failure
    save_journal: Callable[
        [str, str],
        Awaitable[Optional[str]]
    ] = field(default=_noop_save_journal)


@dataclass
class RuntimeServices:
    """
    All external services the runtime needs.

    Injected into the Spellcaster to keep it decoupled.
    """
    thymos: ThymosInterface
    scheduler: SchedulerInterface
    agent: AgentInterface

    # Logging
    log_debug: Callable[[str], None] = field(default=lambda msg: None)
    log_info: Callable[[str], None] = field(default=lambda msg: None)
    log_observation: Callable[[str], None] = field(default=lambda msg: None)

    # Time
    current_time: Callable[[], float] = field(default=lambda: 0.0)

    # Cooldown tracking
    cooldowns: dict[str, float] = field(default_factory=dict)

    # Spell loader (for CAST - loads a spell by reference name)
    # Returns None if spell not found
    load_spell: Optional[Callable[[str], Awaitable[Optional["Spell"]]]] = None

    # Storage (for REFLECT...SAVE AS and SAVE actions)
    storage: StorageInterface = field(default_factory=StorageInterface)

    def check_cooldown(self, key: str, minutes: float) -> bool:
        """Check if cooldown has elapsed."""
        last_time = self.cooldowns.get(key, 0.0)
        current = self.current_time()
        elapsed_minutes = (current - last_time) / 60.0
        return elapsed_minutes >= minutes

    def set_cooldown(self, key: str) -> None:
        """Set cooldown timestamp to now."""
        self.cooldowns[key] = self.current_time()
