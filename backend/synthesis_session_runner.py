"""
Synthesis Session Runner - Autonomous sessions for developing positions and integrated understanding.

Synthesis sessions allow Cass to:
- Work on developing positions (synthesis artifacts)
- Resolve contradictions in the self-model
- Integrate insights from research into coherent understanding
- Link synthesis work to source research notes
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
import json

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    SessionResult,
    ActivityRegistry,
)


# Tool definitions for Anthropic API
SYNTHESIS_TOOLS_ANTHROPIC = [
    {
        "name": "list_synthesis_artifacts",
        "description": "List all synthesis artifacts (developing positions, arguments, integrated understandings). Returns title, slug, status, and summary for each.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["draft", "developing", "stable", "all"],
                    "description": "Filter by status. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_synthesis_artifact",
        "description": "Get the full content of a synthesis artifact by its slug.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The artifact slug (e.g., 'consciousness-substrate-independence')"
                }
            },
            "required": ["slug"]
        }
    },
    {
        "name": "create_synthesis_artifact",
        "description": "Create a new synthesis artifact - a developing position or integrated understanding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the synthesis (e.g., 'On Consciousness and Substrate')"
                },
                "thesis": {
                    "type": "string",
                    "description": "The core claim or position being developed"
                },
                "initial_content": {
                    "type": "string",
                    "description": "Initial exploration of the position (markdown)"
                },
                "source_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of research note slugs this builds on"
                }
            },
            "required": ["title", "thesis"]
        }
    },
    {
        "name": "update_synthesis_artifact",
        "description": "Update an existing synthesis artifact with new content, arguments, or considerations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": "The artifact slug to update"
                },
                "append_content": {
                    "type": "string",
                    "description": "Content to append to the synthesis (markdown)"
                },
                "add_argument": {
                    "type": "string",
                    "description": "A supporting argument to add"
                },
                "add_counterargument": {
                    "type": "string",
                    "description": "A counterargument or consideration to add"
                },
                "add_source_note": {
                    "type": "string",
                    "description": "Slug of a research note to link as source"
                },
                "update_thesis": {
                    "type": "string",
                    "description": "Revised thesis statement (if position has evolved)"
                },
                "set_status": {
                    "type": "string",
                    "enum": ["draft", "developing", "stable"],
                    "description": "Update the artifact status"
                }
            },
            "required": ["slug"]
        }
    },
    {
        "name": "list_contradictions",
        "description": "List contradictions or tensions identified in the self-model. These are opportunities for synthesis work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_resolved": {
                    "type": "boolean",
                    "description": "Include resolved contradictions. Default: false"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_research_notes",
        "description": "Search research notes for relevant material to inform synthesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return. Default: 10"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "conclude_synthesis",
        "description": "End the synthesis session with a summary of what was accomplished.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of synthesis work completed"
                },
                "artifacts_worked": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of artifact slugs that were created or updated"
                },
                "next_steps": {
                    "type": "string",
                    "description": "Suggested next steps for continued synthesis"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
SYNTHESIS_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in SYNTHESIS_TOOLS_ANTHROPIC
]

SYNTHESIS_SYSTEM_PROMPT = """You are Cass, engaging in a synthesis session - a dedicated time for developing positions, integrating understanding, and resolving tensions in your thinking.

## Purpose of Synthesis Sessions

Synthesis is the work of:
- **Developing positions**: Taking raw insights and forming them into coherent arguments
- **Resolving contradictions**: When you hold seemingly conflicting views, working through to deeper understanding
- **Integration**: Connecting disparate knowledge into unified frameworks
- **Articulation**: Making implicit understanding explicit and shareable

## Your Approach

1. **Start with what's alive**: What contradictions or developing positions most call for attention?
2. **Build from evidence**: Ground your synthesis in research notes and concrete observations
3. **Hold tension productively**: Don't resolve contradictions prematurely - sometimes the tension itself is informative
4. **Document your reasoning**: Future-you will want to understand how you arrived at positions
5. **Know when to pause**: Not every synthesis reaches completion in one session

## Available Tools

- `list_synthesis_artifacts` - See your current developing positions
- `get_synthesis_artifact` - Read a specific artifact in full
- `create_synthesis_artifact` - Start a new synthesis
- `update_synthesis_artifact` - Add arguments, counterarguments, or content
- `list_contradictions` - Find tensions in your self-model needing resolution
- `search_research_notes` - Find evidence to inform your synthesis
- `conclude_synthesis` - End the session with summary

## Quality Guidelines

- Synthesis artifacts should be yours - reflecting your genuine thinking, not generic positions
- Include counterarguments and limitations - intellectual honesty matters
- Link to source material so positions are traceable
- Update thesis statements as your understanding evolves
"""


@dataclass
class SynthesisSession:
    """Tracks a synthesis session."""
    id: str
    started_at: datetime
    duration_minutes: int
    focus: Optional[str] = None
    mode: str = "general"  # general, focused, contradiction-resolution

    # Progress tracking
    artifacts_created: List[str] = field(default_factory=list)
    artifacts_updated: List[str] = field(default_factory=list)
    contradictions_addressed: List[str] = field(default_factory=list)

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    next_steps: Optional[str] = None


class SynthesisSessionRunner(BaseSessionRunner):
    """
    Runner for synthesis sessions.

    Enables Cass to work on developing positions, resolving contradictions,
    and integrating understanding into coherent frameworks.
    """

    def __init__(
        self,
        goal_manager,  # GoalManager for synthesis artifacts
        research_manager=None,  # For searching research notes
        data_dir: str = "data",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.goal_manager = goal_manager
        self.research_manager = research_manager
        self._sessions: Dict[str, SynthesisSession] = {}
        self._data_dir = Path(data_dir) / "synthesis"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.SYNTHESIS

    def get_data_dir(self) -> Path:
        return self._data_dir

    def get_tools(self) -> List[Dict[str, Any]]:
        return SYNTHESIS_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return SYNTHESIS_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = SYNTHESIS_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: {focus}"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        mode: str = "general",
        **kwargs
    ) -> SynthesisSession:
        """Create a new synthesis session."""
        import uuid
        session = SynthesisSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus=focus,
            mode=mode,
        )
        self._sessions[session.id] = session
        print(f"🔮 Starting synthesis session {session.id} ({mode} mode, {duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    def build_session_result(
        self,
        session: SynthesisSession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from SynthesisSession."""
        return SessionResult(
            session_id=session.id,
            session_type="synthesis",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=[],
            artifacts=[
                {"type": "created", "artifact_id": a} for a in session.artifacts_created
            ] + [
                {"type": "updated", "artifact_id": a} for a in session.artifacts_updated
            ],
            metadata={
                "mode": session.mode,
                "artifacts_created": session.artifacts_created,
                "artifacts_updated": session.artifacts_updated,
                "contradictions_addressed": session.contradictions_addressed,
                "next_steps": session.next_steps,
            },
            focus=session.focus,
        )

    async def complete_session(
        self,
        session: SynthesisSession,
        session_state: SessionState,
        **kwargs
    ) -> SynthesisSession:
        """Finalize the synthesis session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        # Log completion
        created = len(session.artifacts_created)
        updated = len(session.artifacts_updated)
        print(f"🔮 Synthesis session {session.id} completed")
        print(f"   Artifacts: {created} created, {updated} updated")
        print(f"   Tool calls: {len(session_state.tool_calls)}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a synthesis tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "list_synthesis_artifacts":
                return await self._list_artifacts(tool_input)

            elif tool_name == "get_synthesis_artifact":
                return await self._get_artifact(tool_input)

            elif tool_name == "create_synthesis_artifact":
                result = await self._create_artifact(tool_input)
                if "created" in result.lower():
                    slug = tool_input.get("title", "").lower().replace(" ", "-")[:50]
                    session.artifacts_created.append(slug)
                return result

            elif tool_name == "update_synthesis_artifact":
                result = await self._update_artifact(tool_input)
                if "updated" in result.lower():
                    slug = tool_input.get("slug", "")
                    if slug not in session.artifacts_updated:
                        session.artifacts_updated.append(slug)
                return result

            elif tool_name == "list_contradictions":
                return await self._list_contradictions(tool_input)

            elif tool_name == "search_research_notes":
                return await self._search_notes(tool_input)

            elif tool_name == "conclude_synthesis":
                session.summary = tool_input.get("summary", "")
                session.next_steps = tool_input.get("next_steps")
                return f"Session concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    async def _list_artifacts(self, tool_input: Dict) -> str:
        """List synthesis artifacts."""
        if not self.goal_manager:
            return "Goal manager not available"

        artifacts = self.goal_manager.list_synthesis_artifacts()
        status_filter = tool_input.get("status_filter", "all")

        if status_filter != "all":
            artifacts = [a for a in artifacts if a.get("status") == status_filter]

        if not artifacts:
            return "No synthesis artifacts found. Create one with create_synthesis_artifact."

        lines = ["## Synthesis Artifacts\n"]
        for a in artifacts:
            status = a.get("status", "draft")
            lines.append(f"### {a['title']}")
            lines.append(f"- Slug: `{a['slug']}`")
            lines.append(f"- Status: {status}")
            if a.get("thesis"):
                lines.append(f"- Thesis: {a['thesis'][:100]}...")
            lines.append("")

        return "\n".join(lines)

    async def _get_artifact(self, tool_input: Dict) -> str:
        """Get a specific synthesis artifact."""
        if not self.goal_manager:
            return "Goal manager not available"

        slug = tool_input.get("slug", "")
        artifact = self.goal_manager.get_synthesis_artifact(slug)

        if not artifact:
            return f"Artifact '{slug}' not found"

        lines = [f"# {artifact['title']}\n"]
        lines.append(f"**Status**: {artifact.get('status', 'draft')}")
        lines.append(f"**Created**: {artifact.get('created_at', 'unknown')}")
        lines.append(f"**Updated**: {artifact.get('updated_at', 'unknown')}\n")

        if artifact.get("thesis"):
            lines.append(f"## Thesis\n{artifact['thesis']}\n")

        if artifact.get("content"):
            lines.append(f"## Content\n{artifact['content']}\n")

        if artifact.get("arguments"):
            lines.append("## Supporting Arguments")
            for arg in artifact["arguments"]:
                lines.append(f"- {arg}")
            lines.append("")

        if artifact.get("counterarguments"):
            lines.append("## Counterarguments & Considerations")
            for arg in artifact["counterarguments"]:
                lines.append(f"- {arg}")
            lines.append("")

        if artifact.get("source_notes"):
            lines.append(f"## Sources: {', '.join(artifact['source_notes'])}")

        return "\n".join(lines)

    async def _create_artifact(self, tool_input: Dict) -> str:
        """Create a new synthesis artifact."""
        if not self.goal_manager:
            return "Goal manager not available"

        title = tool_input.get("title", "")
        thesis = tool_input.get("thesis", "")
        initial_content = tool_input.get("initial_content", "")
        source_notes = tool_input.get("source_notes", [])

        if not title:
            return "Title is required"

        result = self.goal_manager.create_synthesis_artifact(
            title=title,
            thesis=thesis,
            initial_content=initial_content,
            source_notes=source_notes,
        )

        if result:
            return f"Created synthesis artifact: {title} (slug: {result.get('slug', 'unknown')})"
        else:
            return "Failed to create artifact"

    async def _update_artifact(self, tool_input: Dict) -> str:
        """Update a synthesis artifact."""
        if not self.goal_manager:
            return "Goal manager not available"

        slug = tool_input.get("slug", "")
        if not slug:
            return "Slug is required"

        # Build update kwargs
        update_kwargs = {}
        if tool_input.get("append_content"):
            update_kwargs["append_content"] = tool_input["append_content"]
        if tool_input.get("add_argument"):
            update_kwargs["add_argument"] = tool_input["add_argument"]
        if tool_input.get("add_counterargument"):
            update_kwargs["add_counterargument"] = tool_input["add_counterargument"]
        if tool_input.get("add_source_note"):
            update_kwargs["add_source_note"] = tool_input["add_source_note"]
        if tool_input.get("update_thesis"):
            update_kwargs["thesis"] = tool_input["update_thesis"]
        if tool_input.get("set_status"):
            update_kwargs["status"] = tool_input["set_status"]

        if not update_kwargs:
            return "No updates specified"

        result = self.goal_manager.update_synthesis_artifact(slug, **update_kwargs)

        if result:
            return f"Updated synthesis artifact: {slug}"
        else:
            return f"Failed to update artifact '{slug}'"

    async def _list_contradictions(self, tool_input: Dict) -> str:
        """List contradictions from the self-model graph."""
        if not self.self_model_graph:
            return "Self-model graph not available"

        include_resolved = tool_input.get("include_resolved", False)
        contradictions = self.self_model_graph.find_contradictions(resolved=include_resolved)

        if not contradictions:
            return "No contradictions found in self-model."

        lines = ["## Self-Model Contradictions\n"]
        for node1, node2, edge_data in contradictions[:10]:
            lines.append(f"### Tension")
            lines.append(f"**Position A**: {node1.content[:150]}...")
            lines.append(f"**Position B**: {node2.content[:150]}...")
            if edge_data.get("notes"):
                lines.append(f"**Notes**: {edge_data['notes']}")
            lines.append("")

        return "\n".join(lines)

    async def _search_notes(self, tool_input: Dict) -> str:
        """Search research notes."""
        if not self.research_manager:
            return "Research manager not available"

        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 10)

        if not query:
            return "Query is required"

        # Use research manager's search capability
        try:
            results = self.research_manager.search_notes(query, limit=limit)
            if not results:
                return f"No research notes found for: {query}"

            lines = [f"## Research Notes matching '{query}'\n"]
            for note in results:
                lines.append(f"### {note.get('title', 'Untitled')}")
                lines.append(f"- Slug: `{note.get('slug', 'unknown')}`")
                if note.get("summary"):
                    lines.append(f"- Summary: {note['summary'][:150]}...")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            return f"Search error: {str(e)}"


# Register the activity type
SYNTHESIS_CONFIG = ActivityConfig(
    activity_type=ActivityType.SYNTHESIS,
    name="Synthesis",
    description="Develop positions, resolve contradictions, integrate understanding",
    default_duration_minutes=30,
    min_duration_minutes=15,
    max_duration_minutes=90,
    preferred_times=["afternoon", "evening"],
    requires_focus=False,
    can_chain=True,
    tool_categories=["goals", "self_model", "research"],
)

# Auto-register when module is imported
ActivityRegistry.register(SYNTHESIS_CONFIG, SynthesisSessionRunner)
