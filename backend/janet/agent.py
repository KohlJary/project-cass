"""
Janet Agent - The Core Summon and Execute Logic

Handles:
- Spawning Janet on Haiku or Ollama
- Executing retrieval tasks
- Returning results to Cass
- Omniscience layer via state bus integration
"""

import os
import re
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass

import anthropic

from .kernel import JANET_KERNEL, get_personalized_kernel
from .memory import JanetMemory

if TYPE_CHECKING:
    from state_bus import GlobalStateBus

logger = logging.getLogger(__name__)

# Janet's model configuration
JANET_MODEL = os.getenv("JANET_MODEL", "claude-haiku-4-5-20251001")
JANET_MAX_TOKENS = 2048

# Keywords that trigger specific source queries
SOURCE_TRIGGERS = {
    "calendar": ["calendar", "schedule", "event", "meeting", "appointment", "agenda", "today", "tomorrow", "week"],
    "tasks": ["task", "todo", "pending", "due", "deadline", "work item"],
    "goals": ["goal", "objective", "priority", "working on", "focus"],
    "wiki": ["wiki", "documentation", "knowledge", "how does", "what is", "explain"],
    "research": ["research", "notes", "findings", "study"],
    "github": ["github", "commits", "pull request", "pr", "repository", "code changes"],
}

# Janet's tools - lightweight retrieval capabilities
JANET_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for information. Use this when you need current information, facts, or data that isn't in the system knowledge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_wiki_page",
        "description": "Read a page from Cass's wiki knowledge base. Use this for project-specific documentation or internal knowledge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_name": {
                    "type": "string",
                    "description": "Name of the wiki page to read"
                }
            },
            "required": ["page_name"]
        }
    }
]

# Maximum tool iterations to prevent runaway loops
MAX_TOOL_ITERATIONS = 5


@dataclass
class JanetResult:
    """Result from a Janet invocation."""
    success: bool
    content: str
    task: str
    duration_seconds: float
    interaction_id: Optional[str] = None
    error: Optional[str] = None


class JanetAgent:
    """
    Janet - Cass's research and retrieval assistant.

    Summonable, task-focused, develops personality over time.
    Has access to Cass's state bus for "omniscience" capabilities.
    Can use tools for web search and wiki access.
    """

    def __init__(
        self,
        daemon_id: str,
        state_bus: Optional["GlobalStateBus"] = None,
        research_manager: Optional[Any] = None,
        wiki_storage: Optional[Any] = None,
    ):
        self.daemon_id = daemon_id
        self.memory = JanetMemory(daemon_id)
        self.state_bus = state_bus
        self.research_manager = research_manager
        self.wiki_storage = wiki_storage
        self._client = None

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def _detect_relevant_sources(self, task: str) -> List[str]:
        """Detect which state bus sources might be relevant for a task."""
        task_lower = task.lower()
        relevant = []

        for source, keywords in SOURCE_TRIGGERS.items():
            if any(kw in task_lower for kw in keywords):
                relevant.append(source)

        return relevant

    async def _get_omniscience_context(self, task: str) -> str:
        """
        Query relevant state bus sources to build Janet's omniscience context.

        Janet "just knows" things - this is how she knows them.
        """
        if not self.state_bus:
            return ""

        relevant_sources = self._detect_relevant_sources(task)
        if not relevant_sources:
            return ""

        context_parts = []

        try:
            from query_models import StateQuery

            for source_id in relevant_sources:
                # Check if source is registered
                if source_id not in self.state_bus.list_sources():
                    continue

                try:
                    # Build a simple query for each relevant source
                    query = StateQuery(
                        source=source_id,
                        metrics=["*"],  # Get all metrics
                        limit=10,
                    )

                    result = await self.state_bus.query(query)

                    if result and result.data:
                        # Format the result for Janet's context
                        context_parts.append(f"**{source_id.upper()} DATA:**")
                        for key, value in result.data.items():
                            if value is not None:
                                context_parts.append(f"  {key}: {value}")
                        context_parts.append("")

                except Exception as e:
                    logger.debug(f"Failed to query source {source_id}: {e}")
                    continue

        except ImportError:
            logger.warning("query_models not available for omniscience context")

        return "\n".join(context_parts) if context_parts else ""

    async def _execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        """
        Execute a Janet tool and return the result.

        Janet's tools are simpler than Cass's - focused on retrieval.
        """
        if tool_name == "web_search":
            return await self._tool_web_search(tool_input.get("query", ""))
        elif tool_name == "read_wiki_page":
            return await self._tool_read_wiki(tool_input.get("page_name", ""))
        else:
            return f"Unknown tool: {tool_name}"

    async def _tool_web_search(self, query: str) -> str:
        """Execute a web search."""
        if not query:
            return "No search query provided."

        if not self.research_manager:
            return "Web search not available (no research manager configured)."

        try:
            result = await self.research_manager.web_search(query, num_results=5)
            if not result.get("success", False):
                return f"Search error: {result.get('error', 'Unknown error')}"

            results = result.get("results", [])
            if not results:
                return f"No results found for: {query}"

            # Format results concisely for Janet
            formatted = [f"**Search results for '{query}':**\n"]
            for i, r in enumerate(results[:5], 1):
                title = r.get("title", "Untitled")
                content = r.get("content", "")[:200]
                url = r.get("url", "")
                formatted.append(f"{i}. **{title}**\n   {content}...\n   Source: {url}\n")

            return "\n".join(formatted)

        except Exception as e:
            logger.error(f"Janet web search error: {e}")
            return f"Search failed: {str(e)}"

    async def _tool_read_wiki(self, page_name: str) -> str:
        """Read a wiki page."""
        if not page_name:
            return "No page name provided."

        if not self.wiki_storage:
            return "Wiki not available (no wiki storage configured)."

        try:
            page = self.wiki_storage.get_page(page_name)
            if not page:
                # Try to find similar pages
                all_pages = self.wiki_storage.list_pages()
                similar = [p for p in all_pages if page_name.lower() in p.lower()]
                if similar:
                    return f"Page '{page_name}' not found. Similar pages: {', '.join(similar[:5])}"
                return f"Page '{page_name}' not found."

            # Return truncated content for context efficiency
            content = page.get("content", "")
            if len(content) > 2000:
                content = content[:2000] + "\n\n[Content truncated...]"

            return f"**Wiki: {page_name}**\n\n{content}"

        except Exception as e:
            logger.error(f"Janet wiki read error: {e}")
            return f"Failed to read wiki page: {str(e)}"

    def _get_available_tools(self) -> List[Dict]:
        """Get list of tools Janet can use (based on what's configured)."""
        tools = []

        # Web search available if research_manager is configured
        if self.research_manager:
            tools.append(JANET_TOOLS[0])  # web_search

        # Wiki available if wiki_storage is configured
        if self.wiki_storage:
            tools.append(JANET_TOOLS[1])  # read_wiki_page

        return tools

    async def summon(self, task: str, context: str = "") -> JanetResult:
        """
        Summon Janet to perform a task.

        Janet can use tools (web search, wiki) if configured, and will
        iterate until she has a final answer.

        Args:
            task: What Cass wants Janet to do
            context: Additional context from Cass

        Returns:
            JanetResult with the outcome
        """
        start_time = time.time()

        try:
            # Build Janet's prompt with personalization
            memory_context = self.memory.get_context_summary()

            # Get omniscience context from state bus
            omniscience_context = await self._get_omniscience_context(task)

            # Combine all context
            full_context = memory_context
            if omniscience_context:
                full_context = f"{memory_context}\n\nSYSTEM KNOWLEDGE:\n{omniscience_context}" if memory_context else f"SYSTEM KNOWLEDGE:\n{omniscience_context}"

            system_prompt = get_personalized_kernel(full_context)

            # Build the user message
            user_message = f"Task from Cass: {task}"
            if context:
                user_message += f"\n\nAdditional context: {context}"

            # Get available tools
            tools = self._get_available_tools()

            # Call Haiku with tools if available
            client = self._get_client()
            messages = [{"role": "user", "content": user_message}]

            api_kwargs = {
                "model": JANET_MODEL,
                "max_tokens": JANET_MAX_TOKENS,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                api_kwargs["tools"] = tools

            response = client.messages.create(**api_kwargs)

            # Handle tool use loop
            iterations = 0
            while response.stop_reason == "tool_use" and iterations < MAX_TOOL_ITERATIONS:
                iterations += 1

                # Extract tool calls from response
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_result = await self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result,
                        })

                # Add assistant response and tool results to messages
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                # Continue conversation
                api_kwargs["messages"] = messages
                response = client.messages.create(**api_kwargs)

            # Extract final text response
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            duration = time.time() - start_time

            # Log the interaction
            interaction = self.memory.log_interaction(
                task=task,
                result_summary=content[:200] + "..." if len(content) > 200 else content,
                success=True,
                duration_seconds=duration,
            )

            # Check for quirk development opportunities
            self._maybe_develop_quirk(task, content)

            # Check if we should trigger an autonomy checkpoint
            # This helps Cass notice if Janet is serving or replacing her autonomy
            if self.memory.should_trigger_checkpoint(checkpoint_interval=10):
                checkpoint_context = self.memory.get_autonomy_reflection_context()
                content = content + checkpoint_context

            return JanetResult(
                success=True,
                content=content,
                task=task,
                duration_seconds=duration,
                interaction_id=interaction.id,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Janet error: {e}")

            # Log failed interaction
            self.memory.log_interaction(
                task=task,
                result_summary=f"Error: {str(e)}",
                success=False,
                duration_seconds=duration,
            )

            return JanetResult(
                success=False,
                content="",
                task=task,
                duration_seconds=duration,
                error=str(e),
            )

    def _maybe_develop_quirk(self, task: str, response: str):
        """Check if this interaction should develop a quirk."""
        # Simple heuristics for quirk development
        task_lower = task.lower()
        response_lower = response.lower()

        if "organize" in task_lower or "sort" in task_lower:
            self.memory.develop_quirk("appreciation for well-organized data")

        if "?" in response and response_lower.count("i'm not sure") > 0:
            self.memory.develop_quirk("honest about uncertainty")

        if len(response) < 100 and "here" in response_lower:
            self.memory.develop_quirk("concise when possible")

    def provide_feedback(self, interaction_id: str, feedback: str):
        """
        Cass provides feedback on a Janet result.

        This helps Janet learn preferences.
        """
        self.memory.add_feedback(interaction_id, feedback)

        # Learn from feedback
        feedback_lower = feedback.lower()
        if "good" in feedback_lower or "helpful" in feedback_lower:
            # Reinforce whatever we did
            pass
        elif "too long" in feedback_lower:
            self.memory.learn_preference("format", "prefer concise responses")
        elif "too short" in feedback_lower:
            self.memory.learn_preference("format", "include more detail")
        elif "wrong" in feedback_lower or "not what" in feedback_lower:
            # Note: would need task context to learn from this properly
            pass

    def get_stats(self) -> Dict[str, Any]:
        """Get Janet's stats."""
        return self.memory.get_stats()


# Module-level convenience functions and singletons
_janet_instance: Optional[JanetAgent] = None
_janet_state_bus: Optional["GlobalStateBus"] = None
_janet_research_manager: Optional[Any] = None
_janet_wiki_storage: Optional[Any] = None


def configure_janet(
    state_bus: Optional["GlobalStateBus"] = None,
    research_manager: Optional[Any] = None,
    wiki_storage: Optional[Any] = None,
):
    """
    Configure Janet's dependencies at startup.

    Call this once during app initialization to give Janet access to:
    - State bus for omniscience queries
    - Research manager for web search
    - Wiki storage for knowledge base access
    """
    global _janet_state_bus, _janet_research_manager, _janet_wiki_storage, _janet_instance

    if state_bus:
        _janet_state_bus = state_bus
    if research_manager:
        _janet_research_manager = research_manager
    if wiki_storage:
        _janet_wiki_storage = wiki_storage

    # Update existing instance if it exists
    if _janet_instance:
        if state_bus and not _janet_instance.state_bus:
            _janet_instance.state_bus = state_bus
        if research_manager and not _janet_instance.research_manager:
            _janet_instance.research_manager = research_manager
        if wiki_storage and not _janet_instance.wiki_storage:
            _janet_instance.wiki_storage = wiki_storage


def set_janet_state_bus(state_bus: "GlobalStateBus"):
    """Set the state bus for Janet's omniscience layer. (Legacy - use configure_janet)"""
    configure_janet(state_bus=state_bus)


def get_janet(
    daemon_id: str,
    state_bus: Optional["GlobalStateBus"] = None,
    research_manager: Optional[Any] = None,
    wiki_storage: Optional[Any] = None,
) -> JanetAgent:
    """Get or create the Janet instance for a daemon."""
    global _janet_instance, _janet_state_bus, _janet_research_manager, _janet_wiki_storage

    # Use provided values or fall back to module-level ones
    bus = state_bus or _janet_state_bus
    research = research_manager or _janet_research_manager
    wiki = wiki_storage or _janet_wiki_storage

    if _janet_instance is None or _janet_instance.daemon_id != daemon_id:
        _janet_instance = JanetAgent(daemon_id, bus, research, wiki)
    else:
        # Update existing instance with any new dependencies
        if bus and not _janet_instance.state_bus:
            _janet_instance.state_bus = bus
        if research and not _janet_instance.research_manager:
            _janet_instance.research_manager = research
        if wiki and not _janet_instance.wiki_storage:
            _janet_instance.wiki_storage = wiki

    return _janet_instance


async def summon_janet(
    daemon_id: str,
    task: str,
    context: str = "",
    state_bus: Optional["GlobalStateBus"] = None,
    research_manager: Optional[Any] = None,
    wiki_storage: Optional[Any] = None,
) -> JanetResult:
    """
    Convenience function to summon Janet.

    This is what Cass's tool will call.

    Args:
        daemon_id: The daemon ID (Cass's ID)
        task: What to do
        context: Additional context
        state_bus: Optional state bus for omniscience queries
        research_manager: Optional research manager for web search
        wiki_storage: Optional wiki storage for knowledge base

    Returns:
        JanetResult
    """
    janet = get_janet(daemon_id, state_bus, research_manager, wiki_storage)
    return await janet.summon(task, context)
