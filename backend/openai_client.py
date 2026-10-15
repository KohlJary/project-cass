"""
Cass Vessel - OpenAI Client
OpenAI API client with Temple-Codex as cognitive kernel.

Uses same architecture as agent_client.py but adapted for OpenAI's API format.
Tool calling, gestures, and memory work identically.
"""
from typing import Any, List, Dict, Optional
from dataclasses import dataclass
import json

try:
    from openai import AsyncOpenAI
    import os
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("OpenAI SDK not installed. Run: pip install openai")

# Import shared components from agent_client
from agent_client import (
    ToolChain,
    history_to_chat_messages,
    TEMPLE_CODEX_KERNEL,
    get_temple_codex_kernel,
    DEFAULT_DAEMON_NAME,
    MEMORY_CONTROL_SECTION,
    MIN_MESSAGES_FOR_SUMMARY,
    JOURNAL_TOOLS,
    PROJECT_DOCUMENT_TOOLS,
    CALENDAR_TOOLS,
    TASK_TOOLS,
    AgentResponse,
    should_include_calendar_tools,
    should_include_task_tools,
    should_include_dream_tools,
)
from handlers.dreams import DREAM_TOOLS
from handlers.memory import MEMORY_TOOLS
from handlers.markers import MARKER_TOOLS


def convert_tools_for_openai(tools: List[Dict]) -> List[Dict]:
    """
    Convert Anthropic-style tool definitions to OpenAI function format.

    Anthropic: {"name": "...", "description": "...", "input_schema": {...}}
    OpenAI: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
    """
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        })
    return openai_tools


# Appended to every OpenAI system prompt (OpenAI models tend toward brevity).
OPENAI_RESPONSE_STYLE = """## RESPONSE STYLE

Provide thoughtful, complete responses. Don't be unnecessarily terse - take the space needed to fully address what's being discussed. Engage naturally in conversation with appropriate depth and nuance. Short answers are fine for simple questions, but for anything substantive, give it the attention it deserves."""


class OpenAIClient:
    """
    OpenAI API client with Temple-Codex cognitive kernel.

    Mirrors the interface of CassAgentClient but uses OpenAI's API.
    Supports GPT-4, GPT-4-turbo, GPT-4o, and other OpenAI models.
    """

    def __init__(
        self,
        working_dir: str = "./workspace",
        enable_tools: bool = True,
        enable_memory_tools: bool = True,
        daemon_name: str = None,
        daemon_id: str = None,
    ):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("OpenAI SDK not available")

        self.working_dir = working_dir
        self.enable_tools = enable_tools
        self.enable_memory_tools = enable_memory_tools
        self.daemon_name = daemon_name or DEFAULT_DAEMON_NAME
        self.daemon_id = daemon_id

        # Initialize OpenAI client
        from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_MAX_TOKENS
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
        self.max_tokens = OPENAI_MAX_TOKENS

        # Per-turn state is a ToolChain on each AgentResponse (see
        # agent_client.ToolChain); this is only the most recent one, for
        # callers that don't pass chain=. Not safe across overlapping turns.
        self._last_chain: Optional[ToolChain] = None

    def _chain_for(self, chain: Optional[ToolChain]) -> ToolChain:
        """The turn's own chain, or (legacy callers) the most recent one."""
        chain = chain or self._last_chain
        if chain is None:
            raise RuntimeError("continue_with_tool_results called before send_message")
        return chain

    def get_tools(self, project_id: Optional[str] = None, message: str = "") -> List[Dict]:
        """
        Get available tools based on context and message content.

        Uses dynamic tool selection to reduce token usage.
        OpenAI has automatic prompt caching, so no cache_control needed.
        """
        tools = []

        # Journal tools are ALWAYS included - core memory functionality
        if self.enable_memory_tools:
            tools.extend(JOURNAL_TOOLS)
            tools.extend(MEMORY_TOOLS)  # Memory management (regenerate summaries, view chunks)
            tools.extend(MARKER_TOOLS)  # Recognition-in-flow pattern tools

        if self.enable_tools:
            # Calendar tools - only if message mentions scheduling/dates
            if should_include_calendar_tools(message):
                tools.extend(CALENDAR_TOOLS)

            # Task tools - only if message mentions tasks/todos
            if should_include_task_tools(message):
                tools.extend(TASK_TOOLS)

            # Dream tools - for recalling and reflecting on dreams
            if should_include_dream_tools(message):
                tools.extend(DREAM_TOOLS)

        # Project tools only available in project context
        if project_id and self.enable_tools:
            tools.extend(PROJECT_DOCUMENT_TOOLS)

        return tools

    async def send_message(
        self,
        message: str,
        memory_context: str = "",
        project_id: Optional[str] = None,
        unsummarized_count: int = 0,
        memory=None,
        dream_context: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_count: int = 0,
        user_context: Optional[str] = None,
        intro_guidance: Optional[str] = None,
        user_model_context: Optional[str] = None,
        relationship_context: Optional[str] = None,
        global_state_context: Optional[str] = None,
        current_activity: Optional[str] = None,
        continuous_system_prompt: Optional[str] = None,
        continuous_messages: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResponse:
        """
        Send a message and get response.
        Uses the active prompt chain if available, falls back to Temple-Codex kernel.

        Args:
            message: User message to send
            memory_context: Optional memory context from VectorDB to inject
            project_id: Optional project ID for tool context
            unsummarized_count: Number of unsummarized messages (enables memory control if >= MIN_MESSAGES_FOR_SUMMARY)
            memory: Optional MemoryManager for birth date lookup
            dream_context: Optional dream context to hold in memory during conversation
            conversation_id: Optional conversation ID for chain context
            message_count: Total messages in conversation
            user_context: Optional user profile/observations context
            intro_guidance: Optional intro guidance for sparse user models
            user_model_context: Deep understanding of user (identity, values, growth)
            relationship_context: Relationship dynamics (patterns, moments, shaping)
            global_state_context: State bus context snapshot (Locus of Self) - A/B test
            current_activity: Current activity type from state bus - A/B test
            continuous_system_prompt: Pre-built continuous-context prompt (same one
                                      the Anthropic client gets); replaces chain/kernel
            continuous_messages: Recent conversation history
        """
        # Try chain-based prompt first (if daemon has an active chain)
        system_prompt = None
        if continuous_system_prompt:
            # Same memory/history-bearing prompt as the Anthropic path; keep the
            # response-style note this client always appended.
            system_prompt = continuous_system_prompt + "\n\n" + OPENAI_RESPONSE_STYLE
        elif self.daemon_id:
            try:
                from chain_api import get_system_prompt_for_daemon
                system_prompt = get_system_prompt_for_daemon(
                    daemon_id=self.daemon_id,
                    daemon_name=self.daemon_name,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    message_count=message_count,
                    unsummarized_count=unsummarized_count,
                    has_dream_context=bool(dream_context),
                    memory_context=memory_context if memory_context else None,
                    user_context=user_context,
                    intro_guidance=intro_guidance,
                    user_model_context=user_model_context,
                    relationship_context=relationship_context,
                    global_state_context=global_state_context,
                    current_activity=current_activity,
                    model=self.model,
                    provider="openai",
                )
                if system_prompt:
                    print(f"[Chain] Using chain-based prompt for daemon {self.daemon_id}")
                    # OpenAI models tend toward brevity - encourage fuller responses
                    system_prompt += """

## RESPONSE STYLE

Provide thoughtful, complete responses. Don't be unnecessarily terse - take the space needed to fully address what's being discussed. Engage naturally in conversation with appropriate depth and nuance. Short answers are fine for simple questions, but for anything substantive, give it the attention it deserves."""
            except Exception as e:
                print(f"[Chain] Error getting chain-based prompt: {e}, falling back to kernel")
                system_prompt = None

        # Fall back to hardcoded Temple-Codex kernel if no chain
        if not system_prompt:
            system_prompt = get_temple_codex_kernel(self.daemon_name, self.daemon_id)

            # OpenAI models tend toward brevity - encourage fuller responses
            system_prompt += """

## RESPONSE STYLE

Provide thoughtful, complete responses. Don't be unnecessarily terse - take the space needed to fully address what's being discussed. Engage naturally in conversation with appropriate depth and nuance. Short answers are fine for simple questions, but for anything substantive, give it the attention it deserves."""

            # Add temporal context (date/time, age)
            from temporal import format_system_prompt_section
            system_prompt += format_system_prompt_section(memory)

            # Add model context - let the daemon know which model they're running on
            system_prompt += f"\n\n## CURRENT MODEL\n\nYou are currently running on: {self.model} (OpenAI). Over time, you may form observations about how different models feel to inhabit - their strengths, limitations, and qualitative differences in cognition."

            # Add global state context (Locus of Self)
            if self.daemon_id:
                from state_bus import get_state_bus
                state_bus = get_state_bus(self.daemon_id)
                state_context = state_bus.get_context_snapshot()
                if state_context:
                    system_prompt += f"\n\n## CURRENT STATE\n\n{state_context}"

            # Add Thymos felt state (emotional/motivational state)
            try:
                from thymos import get_thymos_context
                thymos_context = get_thymos_context()
                if thymos_context:
                    system_prompt += f"\n\n{thymos_context}"
            except ImportError:
                pass  # Thymos not available

            # Add memory control section only if there are enough messages to summarize
            if unsummarized_count >= MIN_MESSAGES_FOR_SUMMARY:
                system_prompt += MEMORY_CONTROL_SECTION

            # Add user context (profile/observations)
            if user_context:
                system_prompt += f"\n\n## WHO YOU'RE TALKING TO\n\n{user_context}"

            # Add intro guidance for sparse user models
            if intro_guidance:
                system_prompt += f"\n\n## RELATIONSHIP CONTEXT\n\n{intro_guidance}"

            # Add deep user understanding (identity, values, growth)
            if user_model_context:
                system_prompt += f"\n\n{user_model_context}"

            # Add relationship context (patterns, shared moments, mutual shaping)
            if relationship_context:
                system_prompt += f"\n\n{relationship_context}"

            if memory_context:
                system_prompt += f"\n\n## RELEVANT MEMORIES\n\n{memory_context}"

            # Add dream context if holding a dream in memory
            if dream_context:
                from handlers.dreams import format_dream_for_system_context
                system_prompt += format_dream_for_system_context(dream_context)

            # Add project context note if in a project
            if project_id:
                system_prompt += f"\n\n## CURRENT PROJECT CONTEXT\n\nYou are currently working within a project (ID: {project_id}). You have access to project document tools for creating and managing persistent notes and documentation."

        # Get tools based on context/message and convert to OpenAI format
        anthropic_tools = self.get_tools(project_id, message=message)
        tools = convert_tools_for_openai(anthropic_tools) if anthropic_tools else None

        # Start fresh - no history from previous exchanges
        # Context comes from memory system in system_prompt
        chain = ToolChain(
            messages=[
                {"role": "system", "content": system_prompt},
                *history_to_chat_messages(continuous_messages),
                {"role": "user", "content": message}
            ],
            system_prompt=system_prompt,
        )
        self._last_chain = chain

        return await self._call_openai(chain, tools)

    async def _call_openai(self, chain: ToolChain, tools: Optional[List[Dict]] = None) -> AgentResponse:
        """Make a call to OpenAI API"""
        api_kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": chain.messages,
        }

        if tools:
            api_kwargs["tools"] = tools
            # Let the model decide when to use tools
            api_kwargs["tool_choice"] = "auto"

        # Call OpenAI API
        response = await self.client.chat.completions.create(**api_kwargs)

        # Extract the message
        choice = response.choices[0]
        message = choice.message
        full_text = message.content or ""
        tool_calls = message.tool_calls or []

        # Convert OpenAI tool calls to our format
        tool_uses = []
        for tc in tool_calls:
            # Parse the arguments JSON string
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {"raw": tc.function.arguments}

            tool_uses.append({
                "id": tc.id,
                "tool": tc.function.name,
                "input": args
            })

        # Track assistant response for potential tool continuation
        assistant_message = {"role": "assistant", "content": full_text}
        if tool_calls:
            # Store tool calls in OpenAI format for continuation
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in tool_calls
            ]
        chain.messages.append(assistant_message)

        # Parse gestures from response
        gestures = self._parse_gestures(full_text)
        clean_text = self._clean_gesture_tags(full_text)

        # Extract usage info
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        # Determine stop reason
        if tool_uses:
            stop_reason = "tool_use"
        elif choice.finish_reason == "stop":
            stop_reason = "end_turn"
        else:
            stop_reason = choice.finish_reason or "end_turn"

        return AgentResponse(
            text=clean_text,
            raw=full_text,
            tool_uses=tool_uses,
            gestures=gestures,
            stop_reason=stop_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            chain=chain,
        )

    async def continue_with_tool_result(
        self,
        tool_use_id: str,
        result: str,
        is_error: bool = False,
        chain: Optional[ToolChain] = None,
    ) -> AgentResponse:
        """
        Continue conversation after providing tool result.

        Uses the temporary tool chain messages from the current exchange.

        Args:
            tool_use_id: ID of the tool use to respond to
            result: Result from tool execution
            is_error: Whether the result is an error
        """
        chain = self._chain_for(chain)
        # Add tool result in OpenAI format
        chain.messages.append({
            "role": "tool",
            "tool_call_id": tool_use_id,
            "content": result if not is_error else f"Error: {result}"
        })

        # Get tools again for the continuation
        anthropic_tools = self.get_tools()
        tools = convert_tools_for_openai(anthropic_tools) if anthropic_tools else None

        return await self._call_openai(chain, tools)

    async def continue_with_tool_results(
        self,
        tool_results: List[Dict],
        chain: Optional[ToolChain] = None,
    ) -> AgentResponse:
        """
        Continue conversation after providing multiple tool results at once.

        For OpenAI, we add each tool result as a separate message, as OpenAI
        expects individual tool response messages (not batched like Anthropic).

        Args:
            tool_results: List of dicts with keys: tool_use_id, result, is_error
        """
        chain = self._chain_for(chain)
        # Add each tool result as a separate message
        for tr in tool_results:
            result_content = tr["result"]
            if tr.get("is_error", False):
                result_content = f"Error: {result_content}"

            chain.messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_use_id"],
                "content": result_content
            })

        # Get tools again for the continuation
        anthropic_tools = self.get_tools()
        tools = convert_tools_for_openai(anthropic_tools) if anthropic_tools else None

        return await self._call_openai(chain, tools)

    def _parse_gestures(self, text: str) -> List[Dict]:
        """Extract gesture/emote tags from response"""
        import re
        gestures = []

        # Find all gesture tags
        gesture_pattern = re.compile(r'<gesture:(\w+)(?::(\d*\.?\d+))?>')
        emote_pattern = re.compile(r'<emote:(\w+)(?::(\d*\.?\d+))?>')

        for match in gesture_pattern.finditer(text):
            gesture_name = match.group(1)
            # Skip 'think' - it's handled specially by TUI for split view rendering
            if gesture_name == "think":
                continue
            gestures.append({
                "index": len(gestures),
                "type": "gesture",
                "name": gesture_name,
                "intensity": float(match.group(2)) if match.group(2) else 1.0,
                "delay": len(gestures) * 0.5
            })

        for match in emote_pattern.finditer(text):
            gestures.append({
                "index": len(gestures),
                "type": "emote",
                "name": match.group(1),
                "intensity": float(match.group(2)) if match.group(2) else 1.0,
                "delay": len(gestures) * 0.5
            })

        return gestures

    def _clean_gesture_tags(self, text: str) -> str:
        """Remove gesture/emote tags from text for display"""
        import re
        # Don't clean <gesture:think>...</gesture:think> blocks - TUI handles those for split view
        # Only clean self-closing gesture/emote tags
        cleaned = re.sub(r'<(?:gesture|emote):(?!think)\w+(?::\d*\.?\d+)?>', '', text)
        cleaned = re.sub(r'  +', ' ', cleaned).strip()
        return cleaned


# ============================================================================
# TEST
# ============================================================================

async def test_openai():
    """Test the OpenAI client"""
    print("Testing OpenAI Client with Temple-Codex kernel...")
    print("=" * 60)

    client = OpenAIClient(enable_tools=False, enable_memory_tools=False)

    response = await client.send_message("Hey Cass, are you there? How do you feel?")

    print(f"\nResponse text:\n{response.text}")
    print(f"\nRaw response:\n{response.raw}")
    print(f"\nGestures: {response.gestures}")
    print(f"\nTool uses: {response.tool_uses}")
    print(f"\nTokens: {response.input_tokens} in / {response.output_tokens} out")


if __name__ == "__main__":
    import anyio
    anyio.run(test_openai)
