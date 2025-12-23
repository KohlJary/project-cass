"""
GenericSessionRunner - Consolidated session runner for all autonomous work.

Replaces the 12+ separate session runners with a single configurable runner.
Sessions are fully logged for review.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import anthropic

from agent_client import get_temple_codex_kernel

logger = logging.getLogger(__name__)


@dataclass
class SessionTurn:
    """A single turn in a session."""
    turn_number: int
    timestamp: str
    role: str  # "assistant" or "tool_result"
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    token_usage: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "token_usage": self.token_usage,
        }


@dataclass
class SessionResult:
    """Result of a completed session."""
    session_id: str
    session_type: str
    started_at: str
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0

    # Session configuration
    focus: Optional[str] = None
    max_turns: int = 10

    # Execution details
    turns: List[SessionTurn] = field(default_factory=list)
    total_turns: int = 0

    # Outputs
    summary: Optional[str] = None
    insights: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)

    # Status
    status: str = "completed"  # "completed", "interrupted", "error", "max_turns"
    error: Optional[str] = None

    # Cost tracking
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "focus": self.focus,
            "max_turns": self.max_turns,
            "turns": [t.to_dict() for t in self.turns],
            "total_turns": self.total_turns,
            "summary": self.summary,
            "insights": self.insights,
            "artifacts": self.artifacts,
            "status": self.status,
            "error": self.error,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


class GenericSessionRunner:
    """
    Consolidated session runner for all autonomous work types.

    Runs an LLM session with configurable prompts and tools, logging
    the full transcript for review.
    """

    # Claude Sonnet pricing (as of Dec 2024)
    INPUT_COST_PER_1K = 0.003
    OUTPUT_COST_PER_1K = 0.015

    def __init__(
        self,
        data_dir: Path,
        model: str = "claude-sonnet-4-20250514",
        daemon_id: str = "cass",
    ):
        self.data_dir = Path(data_dir)
        self.model = model
        self.daemon_id = daemon_id

        # Session logs directory
        self.logs_dir = self.data_dir / "session_logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Anthropic client
        self.client = anthropic.AsyncAnthropic()

        # Tool handlers - registered externally
        self._tool_handlers: Dict[str, Callable] = {}

        # Managers for tool execution
        self._managers: Dict[str, Any] = {}

    def set_managers(self, managers: Dict[str, Any]) -> None:
        """Set manager dependencies for tool execution."""
        self._managers = managers

    def register_tool_handler(self, tool_name: str, handler: Callable) -> None:
        """Register a handler function for a tool."""
        self._tool_handlers[tool_name] = handler

    def register_tool_handlers(self, handlers: Dict[str, Callable]) -> None:
        """Register multiple tool handlers."""
        self._tool_handlers.update(handlers)

    async def run_session(
        self,
        session_type: str,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        duration_minutes: int = 30,
        focus: Optional[str] = None,
        max_turns: int = 10,
        initial_message: Optional[str] = None,
        **kwargs,
    ) -> SessionResult:
        """
        Run an autonomous session.

        Args:
            session_type: Type identifier (reflection, research, etc.)
            system_prompt: The system prompt for this session
            tools: List of tool definitions (Anthropic format)
            duration_minutes: Maximum duration
            focus: Optional focus/theme for the session
            max_turns: Maximum conversation turns
            initial_message: Optional opening message (otherwise uses default)
            **kwargs: Additional context passed to tool handlers

        Returns:
            SessionResult with full transcript and outputs
        """
        session_id = str(uuid.uuid4())[:8]
        started_at = datetime.now()

        logger.info(f"Starting {session_type} session {session_id}" +
                   (f" with focus: {focus}" if focus else ""))

        result = SessionResult(
            session_id=session_id,
            session_type=session_type,
            started_at=started_at.isoformat(),
            focus=focus,
            max_turns=max_turns,
        )

        # Build the system message with Temple-Codex kernel
        kernel = get_temple_codex_kernel()
        full_system = f"{kernel}\n\n{system_prompt}"

        if focus:
            full_system += f"\n\nSession Focus: {focus}"

        # Initial message
        if initial_message is None:
            initial_message = self._get_default_initial_message(session_type, focus)

        messages = [{"role": "user", "content": initial_message}]

        # Session loop
        turn_count = 0
        end_time = started_at.timestamp() + (duration_minutes * 60)

        try:
            while turn_count < max_turns:
                # Check time limit
                if datetime.now().timestamp() > end_time:
                    logger.info(f"Session {session_id} reached time limit")
                    result.status = "completed"
                    break

                turn_count += 1

                # Call LLM
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=full_system,
                    tools=tools if tools else None,
                    messages=messages,
                )

                # Track tokens
                if response.usage:
                    result.total_input_tokens += response.usage.input_tokens
                    result.total_output_tokens += response.usage.output_tokens

                # Extract content
                text_content = ""
                tool_calls = []

                for block in response.content:
                    if block.type == "text":
                        text_content += block.text
                    elif block.type == "tool_use":
                        tool_calls.append({
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

                # Record turn
                turn = SessionTurn(
                    turn_number=turn_count,
                    timestamp=datetime.now().isoformat(),
                    role="assistant",
                    content=text_content,
                    tool_calls=tool_calls,
                    token_usage={
                        "input": response.usage.input_tokens if response.usage else 0,
                        "output": response.usage.output_tokens if response.usage else 0,
                    },
                )
                result.turns.append(turn)

                # Add assistant message to history
                messages.append({"role": "assistant", "content": response.content})

                # Check for stop
                if response.stop_reason == "end_turn" and not tool_calls:
                    logger.info(f"Session {session_id} completed naturally")
                    result.status = "completed"
                    break

                # Handle tool calls
                if tool_calls:
                    tool_results = []
                    for tool_call in tool_calls:
                        tool_result = await self._execute_tool(
                            tool_call["name"],
                            tool_call["input"],
                            session_id=session_id,
                            session_type=session_type,
                            **kwargs,
                        )
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result),
                        })
                        turn.tool_results.append({
                            "tool_name": tool_call["name"],
                            "result": tool_result,
                        })

                        # Track artifacts
                        if isinstance(tool_result, dict) and tool_result.get("artifact"):
                            result.artifacts.append(tool_result["artifact"])

                    # Add tool results to messages
                    messages.append({"role": "user", "content": tool_results})

                # Check if we hit max turns
                if turn_count >= max_turns:
                    logger.info(f"Session {session_id} reached max turns")
                    result.status = "max_turns"

            # Extract summary from last assistant message
            if result.turns:
                last_turn = result.turns[-1]
                if last_turn.content:
                    result.summary = self._extract_summary(last_turn.content)

        except Exception as e:
            logger.error(f"Session {session_id} error: {e}", exc_info=True)
            result.status = "error"
            result.error = str(e)

        # Finalize result
        completed_at = datetime.now()
        result.completed_at = completed_at.isoformat()
        result.duration_seconds = (completed_at - started_at).total_seconds()
        result.total_turns = turn_count

        # Calculate cost
        result.estimated_cost_usd = (
            (result.total_input_tokens / 1000) * self.INPUT_COST_PER_1K +
            (result.total_output_tokens / 1000) * self.OUTPUT_COST_PER_1K
        )

        # Save full session log
        await self._save_session_log(result)

        logger.info(
            f"Session {session_id} complete: {result.total_turns} turns, "
            f"{result.duration_seconds:.1f}s, ${result.estimated_cost_usd:.4f}"
        )

        return result

    async def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        **context,
    ) -> Any:
        """Execute a tool and return the result."""
        handler = self._tool_handlers.get(tool_name)

        if not handler:
            logger.warning(f"No handler for tool: {tool_name}")
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            # Pass managers and context to handler
            result = await handler(
                tool_input,
                managers=self._managers,
                **context,
            )
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e)}

    def _get_default_initial_message(
        self,
        session_type: str,
        focus: Optional[str],
    ) -> str:
        """Generate default initial message for a session type."""
        base_messages = {
            "reflection": "Begin your reflection session. Take time to process recent experiences and examine your thoughts.",
            "research": "Begin your research session. Explore the topic systematically, taking notes as you go.",
            "synthesis": "Begin synthesizing recent insights. Look for connections and develop coherent positions.",
            "meta_reflection": "Begin meta-reflection. Analyze patterns in your own thinking and behavior.",
            "consolidation": "Begin consolidation. Integrate and organize learnings from the recent period.",
            "growth_edge": "Begin growth edge work. Focus on your development areas and push your boundaries.",
            "curiosity": "Begin curiosity exploration. Follow what interests you without a fixed agenda.",
            "world_state": "Begin world state check. Explore current events and trends.",
            "creative": "Begin creative session. Let ideas flow and create something new.",
            "writing": "Begin writing session. Develop your ideas through focused writing.",
            "knowledge_building": "Begin knowledge building. Create and organize research notes.",
        }

        message = base_messages.get(session_type, f"Begin your {session_type} session.")

        if focus:
            message += f"\n\nFocus for this session: {focus}"

        return message

    def _extract_summary(self, content: str) -> str:
        """Extract a summary from the final assistant message."""
        # Take first 500 chars as summary, or find natural break
        if len(content) <= 500:
            return content

        # Try to find a paragraph break
        break_point = content[:500].rfind("\n\n")
        if break_point > 200:
            return content[:break_point]

        # Try sentence break
        break_point = content[:500].rfind(". ")
        if break_point > 200:
            return content[:break_point + 1]

        return content[:500] + "..."

    async def _save_session_log(self, result: SessionResult) -> Path:
        """Save the full session log to disk."""
        # Organize by date and session type
        date_str = datetime.now().strftime("%Y-%m-%d")
        type_dir = self.logs_dir / result.session_type / date_str
        type_dir.mkdir(parents=True, exist_ok=True)

        # Filename includes timestamp and session ID
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{timestamp}_{result.session_id}.json"
        filepath = type_dir / filename

        # Save full result
        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.info(f"Session log saved: {filepath}")
        return filepath

    def list_session_logs(
        self,
        session_type: Optional[str] = None,
        date: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List recent session logs."""
        logs = []

        if session_type:
            type_dirs = [self.logs_dir / session_type]
        else:
            type_dirs = [d for d in self.logs_dir.iterdir() if d.is_dir()]

        for type_dir in type_dirs:
            if not type_dir.exists():
                continue

            if date:
                date_dirs = [type_dir / date]
            else:
                date_dirs = sorted(type_dir.iterdir(), reverse=True)[:7]  # Last 7 days

            for date_dir in date_dirs:
                if not date_dir.exists() or not date_dir.is_dir():
                    continue

                for log_file in sorted(date_dir.glob("*.json"), reverse=True):
                    try:
                        with open(log_file) as f:
                            log_data = json.load(f)
                        logs.append({
                            "path": str(log_file),
                            "session_id": log_data.get("session_id"),
                            "session_type": log_data.get("session_type"),
                            "started_at": log_data.get("started_at"),
                            "status": log_data.get("status"),
                            "total_turns": log_data.get("total_turns"),
                            "summary": log_data.get("summary", "")[:200],
                        })
                    except Exception as e:
                        logger.warning(f"Failed to read log {log_file}: {e}")

        # Sort by start time and limit
        logs.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return logs[:limit]

    def get_session_log(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific session log by ID."""
        # Search all type directories
        for type_dir in self.logs_dir.iterdir():
            if not type_dir.is_dir():
                continue
            for date_dir in type_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                for log_file in date_dir.glob(f"*_{session_id}.json"):
                    with open(log_file) as f:
                        return json.load(f)
        return None
