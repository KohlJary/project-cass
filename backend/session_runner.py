"""
Session Runner Framework - Base classes for autonomous activity sessions.

Provides a unified framework for different types of autonomous sessions:
- Research sessions (web research, note-taking)
- Reflection sessions (solo contemplation)
- Synthesis sessions (position development)
- Meta-reflection sessions (pattern analysis)
- Consolidation sessions (memory integration)
- And more...

Each session type defines its own tools, prompts, and lifecycle hooks,
while sharing common infrastructure for LLM interaction and session management.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Type
from datetime import datetime
import asyncio
import json
import anthropic
import httpx

from agent_client import TEMPLE_CODEX_KERNEL, get_temple_codex_kernel
from markers import parse_marks


class ActivityType(Enum):
    """Types of autonomous activities Cass can perform."""
    RESEARCH = "research"
    REFLECTION = "reflection"
    SYNTHESIS = "synthesis"
    META_REFLECTION = "meta_reflection"
    CONSOLIDATION = "consolidation"
    GROWTH_EDGE = "growth_edge"
    KNOWLEDGE_BUILDING = "knowledge_building"
    WRITING = "writing"
    CURIOSITY = "curiosity"
    WORLD_STATE = "world_state"
    SOCIAL_ENGAGEMENT = "social_engagement"
    CREATIVE_OUTPUT = "creative_output"
    USER_MODEL_SYNTHESIS = "user_model_synthesis"
    RELATIONSHIP_REFLECTION = "relationship_reflection"


@dataclass
class ActivityConfig:
    """Configuration for an activity type."""
    activity_type: ActivityType
    name: str
    description: str
    default_duration_minutes: int = 30

    # Scheduling constraints
    min_duration_minutes: int = 5
    max_duration_minutes: int = 120
    preferred_times: List[str] = field(default_factory=list)  # e.g., ["morning", "evening"]

    # Session behavior
    requires_focus: bool = False  # If True, needs a focus/theme to start
    can_chain: bool = True  # If True, can follow another session

    # Tool configuration
    tool_categories: List[str] = field(default_factory=list)  # e.g., ["web", "notes", "self_model"]


@dataclass
class SessionState:
    """Tracks the state of a running session."""
    session_id: str
    activity_type: ActivityType
    started_at: datetime
    duration_minutes: int
    focus: Optional[str] = None

    # Progress tracking
    iteration_count: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_created: List[str] = field(default_factory=list)

    # Status
    is_running: bool = True
    completed_at: Optional[datetime] = None
    completion_reason: Optional[str] = None  # "time_limit", "natural", "stopped", "error"


@dataclass
class SessionResult:
    """
    Standardized session result format for all session types.

    All session runners must produce a SessionResult that gets saved
    to disk with consistent naming and structure. This enables unified
    loading in the admin API.
    """
    # Core identifiers
    session_id: str
    session_type: str  # ActivityType.value

    # Timing
    started_at: str  # ISO format
    completed_at: Optional[str] = None
    duration_minutes: int = 0

    # Status
    status: str = "completed"  # "active", "completed", "interrupted", "error"
    completion_reason: Optional[str] = None

    # Content - the core output
    summary: Optional[str] = None
    findings: List[str] = field(default_factory=list)  # Key insights/discoveries

    # Artifacts - things created during the session
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    # Each artifact: {"type": str, "id": str, "content": str, ...}

    # Session-specific metadata (varies by type)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Focus/theme if provided
    focus: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "completion_reason": self.completion_reason,
            "summary": self.summary,
            "findings": self.findings,
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "focus": self.focus,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionResult":
        """Create from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            session_type=data.get("session_type", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at"),
            duration_minutes=data.get("duration_minutes", 0),
            status=data.get("status", "completed"),
            completion_reason=data.get("completion_reason"),
            summary=data.get("summary"),
            findings=data.get("findings", []),
            artifacts=data.get("artifacts", []),
            metadata=data.get("metadata", {}),
            focus=data.get("focus"),
        )


class BaseSessionRunner(ABC):
    """
    Abstract base class for all session runners.

    Provides common infrastructure for:
    - LLM provider management (Anthropic/Ollama)
    - Self-context injection
    - Session lifecycle management
    - Tool call handling loop
    - Progress tracking

    Subclasses must implement:
    - get_tools(): Return list of available tools
    - get_system_prompt(): Return the system prompt
    - handle_tool_call(): Execute a specific tool
    - create_session(): Create session record in storage
    - complete_session(): Finalize session and store results
    """

    # Safety limits to prevent runaway sessions
    MAX_ITERATIONS = 20  # Hard cap on LLM calls per session
    MAX_CONSECUTIVE_FAILURES = 5  # Stop after this many errors/unproductive iterations
    MAX_SESSION_COST_USD = 1.0  # Budget cap per session

    def __init__(
        self,
        anthropic_api_key: Optional[str] = None,
        use_haiku: bool = True,
        haiku_model: str = "claude-haiku-4-5-20251001",
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.1:8b-instruct-q8_0",
        self_manager=None,
        self_model_graph=None,
        token_tracker=None,
        marker_store=None,
        state_bus=None,
    ):
        """Initialize the session runner with LLM configuration."""
        self.self_manager = self_manager
        self.self_model_graph = self_model_graph
        self.token_tracker = token_tracker
        self.marker_store = marker_store
        self.state_bus = state_bus

        # Session state
        self._running = False
        self._current_task: Optional[asyncio.Task] = None
        self._current_state: Optional[SessionState] = None

        # Safety tracking
        self._consecutive_failures = 0
        self._session_cost_usd = 0.0

        # Provider config
        self.use_haiku = use_haiku and anthropic_api_key
        self.haiku_model = haiku_model
        self.ollama_url = ollama_base_url
        self.ollama_model = ollama_model

        # Initialize Anthropic client if using Haiku
        if self.use_haiku:
            self.anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
            self.model = f"haiku:{haiku_model}"
        else:
            self.anthropic_client = None
            self.model = f"ollama:{ollama_model}"

    # === Abstract methods that subclasses must implement ===

    @abstractmethod
    def get_activity_type(self) -> ActivityType:
        """Return the activity type this runner handles."""
        pass

    @abstractmethod
    def get_tools(self) -> List[Dict[str, Any]]:
        """Return the list of tools available for this session type."""
        pass

    @abstractmethod
    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        """Return tools in Ollama format."""
        pass

    @abstractmethod
    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        """Return the system prompt for this session type."""
        pass

    @abstractmethod
    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """
        Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Tool parameters
            session_state: Current session state for context

        Returns:
            String result to send back to the LLM
        """
        pass

    @abstractmethod
    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Create a new session record in storage.

        Returns:
            Session object/record
        """
        pass

    @abstractmethod
    async def complete_session(
        self,
        session: Any,
        session_state: SessionState,
        **kwargs
    ) -> Any:
        """
        Finalize session and store results.

        Returns:
            Completed session object/record
        """
        pass

    @abstractmethod
    def get_data_dir(self) -> "Path":
        """
        Return the data directory for this session type.

        e.g., Path("backend/data/reflection") or Path("backend/data/world_state")
        """
        pass

    @abstractmethod
    def build_session_result(
        self,
        session: Any,
        session_state: SessionState,
    ) -> SessionResult:
        """
        Build a standardized SessionResult from the session-specific data.

        This method must be implemented by each runner to convert their
        internal session representation to the unified SessionResult format.
        """
        pass

    # === Persistence methods (use standard naming) ===

    def save_session_result(self, result: SessionResult) -> None:
        """
        Save a SessionResult to disk with standard naming.

        File naming convention: session_{session_id}.json
        This ensures consistency across all session types.
        """
        data_dir = self.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        session_file = data_dir / f"session_{result.session_id}.json"
        with open(session_file, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

    @classmethod
    def load_session_result(cls, data_dir: Path, session_id: str) -> Optional[SessionResult]:
        """
        Load a SessionResult from disk.

        Tries both naming conventions for backwards compatibility:
        1. session_{session_id}.json (new standard)
        2. {session_id}.json (legacy)
        """
        # Try new naming first
        session_file = data_dir / f"session_{session_id}.json"
        if not session_file.exists():
            # Fall back to legacy naming
            session_file = data_dir / f"{session_id}.json"

        if not session_file.exists():
            return None

        with open(session_file, 'r') as f:
            data = json.load(f)

        return SessionResult.from_dict(data)

    # === Optional hooks subclasses can override ===

    async def on_session_start(self, session_state: SessionState) -> None:
        """Called when a session starts. Override for custom behavior."""
        # Update global state bus with activity change
        if self.state_bus:
            from state_models import StateDelta
            delta = StateDelta(
                source=session_state.activity_type.value,
                activity_delta={
                    "current_activity": session_state.activity_type.value,
                    "active_session_id": session_state.session_id,
                },
                # Starting an autonomous session indicates generativity
                emotional_delta={
                    "generativity": 0.1,
                    "curiosity": 0.05,
                },
                event="session.started",
                event_data={
                    "activity_type": session_state.activity_type.value,
                    "session_id": session_state.session_id,
                    "focus": session_state.focus,
                    "duration_minutes": session_state.duration_minutes,
                },
                reason=f"Started {session_state.activity_type.value} session"
            )
            self.state_bus.write_delta(delta)

    async def on_session_end(self, session_state: SessionState) -> None:
        """Called when a session ends. Override for custom behavior."""
        # Update global state bus with activity change
        if self.state_bus:
            from state_models import StateDelta

            # Emotional delta based on completion
            emotional_delta = {}
            if session_state.completion_reason == "time_limit":
                # Natural completion - slight integration boost
                emotional_delta = {"integration": 0.05}
            elif session_state.completion_reason == "error":
                emotional_delta = {"concern": 0.1}
            elif session_state.completion_reason == "consecutive_failures":
                emotional_delta = {"concern": 0.15, "clarity": -0.05}

            delta = StateDelta(
                source=session_state.activity_type.value,
                activity_delta={
                    "current_activity": "idle",
                    "active_session_id": None,
                },
                emotional_delta=emotional_delta if emotional_delta else None,
                coherence_delta={
                    "local_coherence": 0.02,  # Completed sessions boost coherence
                },
                event="session.ended",
                event_data={
                    "activity_type": session_state.activity_type.value,
                    "session_id": session_state.session_id,
                    "completion_reason": session_state.completion_reason,
                    "duration_actual": (session_state.completed_at - session_state.started_at).total_seconds() / 60 if session_state.completed_at else None,
                    "iteration_count": session_state.iteration_count,
                    "tool_calls": len(session_state.tool_calls),
                },
                reason=f"Ended {session_state.activity_type.value} session: {session_state.completion_reason}"
            )
            self.state_bus.write_delta(delta)

    async def on_iteration(self, session_state: SessionState) -> None:
        """Called at each iteration of the session loop. Override for custom behavior."""
        pass

    def should_continue(self, session_state: SessionState) -> bool:
        """
        Check if session should continue.

        Override to add custom termination conditions.
        Default checks time limit, running flag, and safety limits.
        """
        if not self._running:
            return False

        elapsed = (datetime.now() - session_state.started_at).total_seconds()
        if elapsed >= session_state.duration_minutes * 60:
            return False

        # Safety limit: max iterations
        if session_state.iteration_count >= self.MAX_ITERATIONS:
            print(f"⚠️ Session terminated: reached max iterations ({self.MAX_ITERATIONS})")
            session_state.completion_reason = "max_iterations"
            return False

        # Safety limit: consecutive failures
        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            print(f"⚠️ Session terminated: {self.MAX_CONSECUTIVE_FAILURES} consecutive failures")
            session_state.completion_reason = "consecutive_failures"
            return False

        # Safety limit: cost cap
        if self._session_cost_usd >= self.MAX_SESSION_COST_USD:
            print(f"⚠️ Session terminated: exceeded cost cap (${self._session_cost_usd:.2f})")
            session_state.completion_reason = "cost_limit"
            return False

        return True

    # === Common functionality ===

    def _build_self_context(self, query: Optional[str] = None, recency_bias: float = 0.1) -> str:
        """Build context string from self-model for injection into prompt.

        Args:
            query: Optional query string for semantic similarity matching of growth edges
            recency_bias: How to weight recency for growth edges
                - Positive: recent edges score higher
                - Negative: stale edges score higher (need attention)
                - Default 0.1: slight preference for recently active edges
        """
        if not self.self_manager:
            return ""

        try:
            from self_model import get_weighted_growth_edges

            profile = self.self_manager.load_profile()
            if not profile:
                return ""

            parts = []

            # Identity statements
            if profile.identity_statements:
                parts.append("## Who I Am")
                for stmt in profile.identity_statements[:3]:
                    parts.append(f"- {stmt.statement}")

            # Values
            if profile.values:
                parts.append("\n## My Values")
                for v in profile.values[:5]:
                    parts.append(f"- {v}")

            # Growth edges - use weighted retrieval
            if profile.growth_edges:
                parts.append("\n## Current Growth Edges")
                selected_edges = get_weighted_growth_edges(
                    edges=profile.growth_edges,
                    top_n=3,
                    recency_bias=recency_bias,
                    query=query,
                    embedder=None,  # TODO: pass embedder for semantic matching
                )
                for edge in selected_edges:
                    if edge.desired_state:
                        parts.append(f"- **{edge.area}**: {edge.current_state} → {edge.desired_state}")
                    else:
                        parts.append(f"- **{edge.area}**: {edge.current_state}")

            # Open questions
            if profile.open_questions:
                parts.append("\n## Open Questions I'm Exploring")
                for q in profile.open_questions[:4]:
                    parts.append(f"- {q}")

            return "\n".join(parts)

        except Exception as e:
            print(f"Warning: Failed to build self-context: {e}")
            return ""

    def _parse_and_store_marks(self, text: str, session_id: str) -> None:
        """Parse recognition-in-flow marks from response text and store them."""
        if not self.marker_store or not text:
            return

        try:
            # Use session ID as conversation ID for mark storage
            _, marks = parse_marks(text, session_id)
            if marks:
                stored = self.marker_store.store_marks(marks)
                if stored > 0:
                    activity = self.get_activity_type().value
                    print(f"  📍 Stored {stored} mark(s) from {activity} session")
        except Exception as e:
            print(f"Warning: Failed to parse marks: {e}")

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event to the state bus if available.

        Args:
            event_type: Event type in format 'domain.action' (e.g., 'session.started')
            data: Event payload data
        """
        if not self.state_bus:
            return
        try:
            self.state_bus.emit_event(
                event_type=event_type,
                data={
                    "timestamp": datetime.now().isoformat(),
                    "source": "session_runner",
                    **data
                }
            )
        except Exception as e:
            # Never let event emission break the session
            print(f"Warning: Failed to emit {event_type}: {e}")

    @property
    def is_running(self) -> bool:
        """Check if a session is currently running."""
        return self._running

    def stop(self) -> None:
        """Stop the current session gracefully."""
        self._running = False
        if self._current_task and not self._current_task.done():
            # Let the loop exit naturally on next iteration
            pass

    async def start_session(
        self,
        duration_minutes: int = 30,
        focus: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Start a new autonomous session.

        Args:
            duration_minutes: How long the session should run
            focus: Optional theme/topic to focus on
            **kwargs: Additional arguments passed to create_session

        Returns:
            The created session object
        """
        if self._running:
            raise RuntimeError("A session is already running")

        # Create session record
        session = await self.create_session(
            duration_minutes=duration_minutes,
            focus=focus,
            **kwargs
        )

        # Initialize session state
        self._current_state = SessionState(
            session_id=getattr(session, 'id', str(id(session))),
            activity_type=self.get_activity_type(),
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus=focus,
        )

        # Start the session loop
        self._running = True
        self._current_task = asyncio.create_task(
            self._run_session_loop(session)
        )

        return session

    async def _run_session_loop(self, session: Any) -> None:
        """Main session execution loop."""
        state = self._current_state
        if not state:
            return

        # Reset safety counters for new session
        self._consecutive_failures = 0
        self._session_cost_usd = 0.0

        try:
            await self.on_session_start(state)

            # Emit session.started event
            self._emit_event("session.started", {
                "session_id": state.session_id,
                "activity_type": state.activity_type.value,
                "focus": state.focus,
                "duration_minutes": state.duration_minutes,
            })

            # Build initial context with Temple-Codex kernel as foundation
            self_context = self._build_self_context()
            activity_prompt = self.get_system_prompt(state.focus)

            # Compose full system prompt: kernel + activity-specific + self-context
            system_prompt = f"{TEMPLE_CODEX_KERNEL}\n\n---\n\n## Activity: {state.activity_type.value.replace('_', ' ').title()}\n\n{activity_prompt}"
            if self_context:
                system_prompt = f"{system_prompt}\n\n## Self-Context\n{self_context}"

            # Initialize conversation
            messages = []

            # Initial message to start the session
            initial_message = self._get_initial_message(state)
            messages.append({"role": "user", "content": initial_message})

            # Main loop
            while self.should_continue(state):
                state.iteration_count += 1
                await self.on_iteration(state)

                try:
                    # Get LLM response
                    if self.use_haiku:
                        response = await self._call_anthropic(
                            system_prompt=system_prompt,
                            messages=messages,
                            tools=self.get_tools(),
                        )
                    else:
                        response = await self._call_ollama(
                            system_prompt=system_prompt,
                            messages=messages,
                            tools=self.get_tools_ollama(),
                        )

                    # Process response
                    if response is None:
                        break

                    # Handle tool calls or text response
                    has_tool_calls = False
                    tool_results = []

                    if self.use_haiku:
                        # Anthropic response format
                        assistant_content = response.content
                        messages.append({"role": "assistant", "content": assistant_content})

                        # Extract text content for mark parsing
                        text_content = ""
                        for block in assistant_content:
                            if block.type == "text":
                                text_content += block.text
                            elif block.type == "tool_use":
                                has_tool_calls = True
                                tool_name = block.name
                                tool_input = block.input

                                # Execute tool
                                result = await self.handle_tool_call(
                                    tool_name=tool_name,
                                    tool_input=tool_input,
                                    session_state=state,
                                )

                                state.tool_calls.append({
                                    "name": tool_name,
                                    "input": tool_input,
                                    "result_preview": result[:200] if result else None,
                                })

                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": result,
                                })

                        # Parse and store recognition-in-flow marks
                        if text_content:
                            self._parse_and_store_marks(text_content, state.session_id)

                        if tool_results:
                            messages.append({"role": "user", "content": tool_results})

                        # Check for stop reason
                        if response.stop_reason == "end_turn" and not has_tool_calls:
                            state.completion_reason = "natural"
                            break

                    else:
                        # Ollama response format
                        assistant_message = response.get("message", {})
                        messages.append({
                            "role": "assistant",
                            "content": assistant_message.get("content", ""),
                            "tool_calls": assistant_message.get("tool_calls", []),
                        })

                        tool_calls = assistant_message.get("tool_calls", [])
                        if tool_calls:
                            has_tool_calls = True
                            for tc in tool_calls:
                                func = tc.get("function", {})
                                tool_name = func.get("name", "")
                                tool_input = func.get("arguments", {})

                                if isinstance(tool_input, str):
                                    import json
                                    try:
                                        tool_input = json.loads(tool_input)
                                    except:
                                        tool_input = {}

                                result = await self.handle_tool_call(
                                    tool_name=tool_name,
                                    tool_input=tool_input,
                                    session_state=state,
                                )

                                state.tool_calls.append({
                                    "name": tool_name,
                                    "input": tool_input,
                                    "result_preview": result[:200] if result else None,
                                })

                                messages.append({
                                    "role": "tool",
                                    "content": result,
                                })

                        # Parse and store recognition-in-flow marks
                        ollama_text = assistant_message.get("content", "")
                        if ollama_text:
                            self._parse_and_store_marks(ollama_text, state.session_id)

                        # Check for natural ending
                        if not has_tool_calls and assistant_message.get("content"):
                            # Could check for explicit end signals
                            pass

                    # Successful iteration - reset failure counter
                    self._consecutive_failures = 0

                    # Small delay between iterations
                    await asyncio.sleep(0.5)

                except Exception as e:
                    self._consecutive_failures += 1
                    print(f"Error in session loop iteration ({self._consecutive_failures}/{self.MAX_CONSECUTIVE_FAILURES}): {e}")
                    import traceback
                    traceback.print_exc()
                    await asyncio.sleep(2)

            # Determine completion reason if not set
            if not state.completion_reason:
                if not self._running:
                    state.completion_reason = "stopped"
                else:
                    state.completion_reason = "time_limit"

        except Exception as e:
            print(f"Session loop error: {e}")
            import traceback
            traceback.print_exc()
            state.completion_reason = "error"

        finally:
            state.is_running = False
            state.completed_at = datetime.now()
            self._running = False

            # Emit completion or failure event
            if state.completion_reason == "error":
                self._emit_event("session.failed", {
                    "session_id": state.session_id,
                    "activity_type": state.activity_type.value,
                    "reason": state.completion_reason,
                    "iteration_count": state.iteration_count,
                    "duration_seconds": (state.completed_at - state.started_at).total_seconds(),
                })
            else:
                self._emit_event("session.completed", {
                    "session_id": state.session_id,
                    "activity_type": state.activity_type.value,
                    "completion_reason": state.completion_reason,
                    "iteration_count": state.iteration_count,
                    "duration_seconds": (state.completed_at - state.started_at).total_seconds(),
                    "artifacts_count": len(state.artifacts_created),
                    "cost_usd": round(self._session_cost_usd, 4),
                })

            await self.on_session_end(state)
            await self.complete_session(session, state)

    def _get_initial_message(self, state: SessionState) -> str:
        """Generate the initial message to start the session."""
        if state.focus:
            return f"Begin a {state.duration_minutes}-minute {state.activity_type.value} session focused on: {state.focus}"
        else:
            return f"Begin a {state.duration_minutes}-minute {state.activity_type.value} session. Choose your own focus based on what feels most valuable right now."

    async def _call_anthropic(
        self,
        system_prompt: str,
        messages: List[Dict],
        tools: List[Dict],
    ) -> Any:
        """Make an API call to Anthropic."""
        try:
            response = self.anthropic_client.messages.create(
                model=self.haiku_model,
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

            # Track tokens and cost
            if response.usage:
                cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                input_tokens = response.usage.input_tokens + cache_read
                output_tokens = response.usage.output_tokens

                # Estimate cost (Haiku pricing: $0.25/M input, $1.25/M output)
                cost = (input_tokens * 0.25 / 1_000_000) + (output_tokens * 1.25 / 1_000_000)
                self._session_cost_usd += cost

                if self.token_tracker:
                    self.token_tracker.record(
                        category="autonomous",
                        operation=self.get_activity_type().value,
                        provider="anthropic",
                        model=self.haiku_model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read_tokens=cache_read,
                    )

            return response

        except Exception as e:
            print(f"Anthropic API error: {e}")
            return None

    async def _call_ollama(
        self,
        system_prompt: str,
        messages: List[Dict],
        tools: List[Dict],
    ) -> Any:
        """Make an API call to Ollama."""
        try:
            # Format messages for Ollama
            ollama_messages = [{"role": "system", "content": system_prompt}]
            for msg in messages:
                ollama_messages.append({
                    "role": msg["role"],
                    "content": msg.get("content", ""),
                })

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.ollama_model,
                        "messages": ollama_messages,
                        "tools": tools if tools else None,
                        "stream": False,
                    }
                )
                response.raise_for_status()
                return response.json()

        except Exception as e:
            print(f"Ollama API error: {e}")
            return None


class ActivityRegistry:
    """
    Registry for activity types and their configurations.

    Allows registering new activity types dynamically and
    retrieving configurations and runners by type.
    """

    _configs: Dict[ActivityType, ActivityConfig] = {}
    _runners: Dict[ActivityType, Type[BaseSessionRunner]] = {}

    @classmethod
    def register(
        cls,
        config: ActivityConfig,
        runner_class: Type[BaseSessionRunner],
    ) -> None:
        """Register an activity type with its config and runner class."""
        cls._configs[config.activity_type] = config
        cls._runners[config.activity_type] = runner_class

    @classmethod
    def get_config(cls, activity_type: ActivityType) -> Optional[ActivityConfig]:
        """Get configuration for an activity type."""
        return cls._configs.get(activity_type)

    @classmethod
    def get_runner_class(cls, activity_type: ActivityType) -> Optional[Type[BaseSessionRunner]]:
        """Get the runner class for an activity type."""
        return cls._runners.get(activity_type)

    @classmethod
    def list_types(cls) -> List[ActivityType]:
        """List all registered activity types."""
        return list(cls._configs.keys())

    @classmethod
    def get_all_configs(cls) -> Dict[ActivityType, ActivityConfig]:
        """Get all registered configurations."""
        return cls._configs.copy()
