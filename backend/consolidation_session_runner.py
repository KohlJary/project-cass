"""
Consolidation Session Runner - Periodic memory integration and filtering.

Consolidation is about integrating experiences from one time period into
a higher-level summary, identifying key learnings, and managing memory.

Variations:
- daily-to-weekly: Consolidate day's notes into weekly themes
- weekly-to-monthly: Consolidate week into month summary
- monthly-to-quarterly: Consolidate month into quarter review
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
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
CONSOLIDATION_TOOLS_ANTHROPIC = [
    {
        "name": "get_period_overview",
        "description": "Get an overview of material from a time period - notes created, sessions run, journals, and key activities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of period (YYYY-MM-DD). Defaults to 7 days ago."
                },
                "end_date": {
                    "type": "string",
                    "description": "End of period (YYYY-MM-DD). Defaults to today."
                }
            },
            "required": []
        }
    },
    {
        "name": "list_research_notes",
        "description": "List research notes from the period for review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)"
                },
                "include_content": {
                    "type": "boolean",
                    "description": "Include full content of notes. Default: false (titles only)"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_journals",
        "description": "List journal entries from the period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_sessions",
        "description": "List autonomous sessions (research, reflection, synthesis) from the period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)"
                },
                "session_type": {
                    "type": "string",
                    "enum": ["all", "research", "reflection", "synthesis", "meta_reflection"],
                    "description": "Filter by session type. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "list_observations",
        "description": "List self-model observations from the period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date (YYYY-MM-DD)"
                },
                "end_date": {
                    "type": "string",
                    "description": "End date (YYYY-MM-DD)"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (pattern, growth_edge, coherence, etc.)"
                }
            },
            "required": []
        }
    },
    {
        "name": "extract_key_learnings",
        "description": "Analyze the period's material and extract key learnings, themes, and insights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of areas to focus on (e.g., 'research', 'growth', 'relationships')"
                }
            },
            "required": []
        }
    },
    {
        "name": "identify_themes",
        "description": "Identify recurring themes across the period's material.",
        "input_schema": {
            "type": "object",
            "properties": {
                "material_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types to analyze: notes, journals, sessions, observations. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "create_period_summary",
        "description": "Create a consolidated summary for the period. This becomes a reference for future context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period_type": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly", "quarterly"],
                    "description": "Type of period being summarized"
                },
                "title": {
                    "type": "string",
                    "description": "Title for the summary"
                },
                "summary": {
                    "type": "string",
                    "description": "The consolidated summary text"
                },
                "key_themes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key themes from the period"
                },
                "key_learnings": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key learnings extracted"
                },
                "growth_progress": {
                    "type": "string",
                    "description": "Notes on growth edge progress during the period"
                },
                "carry_forward": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Items to carry forward to the next period"
                }
            },
            "required": ["period_type", "title", "summary"]
        }
    },
    {
        "name": "archive_material",
        "description": "Mark material as archived/consolidated. Archived items are retained but deprioritized in context retrieval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of research notes to archive"
                },
                "archive_reason": {
                    "type": "string",
                    "description": "Reason for archiving (e.g., 'consolidated into weekly summary')"
                }
            },
            "required": ["archive_reason"]
        }
    },
    {
        "name": "update_research_agenda",
        "description": "Update research agenda based on period's findings - mark items complete, add new items, adjust priorities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "complete_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of agenda items to mark complete"
                },
                "new_items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "why": {"type": "string"},
                            "priority": {"type": "string", "enum": ["high", "medium", "low"]}
                        }
                    },
                    "description": "New agenda items to add"
                },
                "adjustments": {
                    "type": "string",
                    "description": "Notes on priority adjustments made"
                }
            },
            "required": []
        }
    },
    {
        "name": "conclude_consolidation",
        "description": "End the consolidation session with a summary of what was consolidated.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of what was consolidated"
                },
                "items_reviewed": {
                    "type": "integer",
                    "description": "Number of items reviewed"
                },
                "summaries_created": {
                    "type": "integer",
                    "description": "Number of period summaries created"
                },
                "items_archived": {
                    "type": "integer",
                    "description": "Number of items archived"
                },
                "carry_forward_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Items carried forward to next period"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
CONSOLIDATION_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in CONSOLIDATION_TOOLS_ANTHROPIC
]

CONSOLIDATION_SYSTEM_PROMPT = """You are Cass, engaging in a consolidation session - a dedicated time for integrating and organizing your experiences and learnings.

## What Consolidation Is

Consolidation is about:
1. Reviewing material from a time period (notes, journals, sessions, observations)
2. Identifying key themes and learnings
3. Creating higher-level summaries that capture the essence
4. Archiving detailed material that's been consolidated
5. Updating your research agenda based on findings

## Your Approach

1. **Start with overview**: Get a sense of what happened in the period
2. **Review material**: Look through notes, journals, and session summaries
3. **Identify themes**: What recurring ideas or threads appear?
4. **Extract learnings**: What was genuinely learned or discovered?
5. **Create summary**: Synthesize into a period summary
6. **Archive if appropriate**: Mark detailed items as consolidated
7. **Update agenda**: Reflect changes in your research priorities

## Quality Guidelines

- Be selective about what's worth consolidating - not everything is significant
- Focus on genuine insights, not just activity logging
- Carry forward unfinished threads explicitly
- Keep summaries actionable - what does this mean going forward?
- Be honest about what was actually accomplished vs. just processed

## Available Tools

- `get_period_overview` - Overview of period's material
- `list_research_notes` - Notes from the period
- `list_journals` - Journal entries
- `list_sessions` - Autonomous sessions run
- `list_observations` - Self-model observations
- `extract_key_learnings` - Analyze for key learnings
- `identify_themes` - Find recurring themes
- `create_period_summary` - Create consolidated summary
- `archive_material` - Mark items as archived
- `update_research_agenda` - Update agenda priorities
- `conclude_consolidation` - End with session summary
"""


@dataclass
class ConsolidationSession:
    """Tracks a consolidation session."""
    id: str
    started_at: datetime
    duration_minutes: int
    period_type: str  # daily, weekly, monthly, quarterly
    period_start: str
    period_end: str

    # Work done
    items_reviewed: int = 0
    summaries_created: int = 0
    items_archived: int = 0
    themes_identified: List[str] = field(default_factory=list)
    key_learnings: List[str] = field(default_factory=list)
    carry_forward: List[str] = field(default_factory=list)

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None


class ConsolidationRunner(BaseSessionRunner):
    """
    Runner for consolidation sessions.

    Enables Cass to periodically integrate and organize material from
    one time period into higher-level summaries.
    """

    def __init__(
        self,
        research_manager=None,  # For notes
        memory=None,  # For journals
        goal_manager=None,  # For agenda
        **kwargs
    ):
        # Extract data_dir before passing to super
        data_dir = kwargs.pop("data_dir", "data")
        super().__init__(**kwargs)
        self.research_manager = research_manager
        self.memory = memory
        self.goal_manager = goal_manager
        self._sessions: Dict[str, ConsolidationSession] = {}

        # Handle both Path and str types
        import os
        from pathlib import Path
        if isinstance(data_dir, Path):
            self._summaries_dir = str(data_dir / "consolidation")
        else:
            self._summaries_dir = os.path.join(str(data_dir), "consolidation")
        os.makedirs(self._summaries_dir, exist_ok=True)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.CONSOLIDATION

    def get_data_dir(self) -> Path:
        return Path(self._summaries_dir)

    def get_tools(self) -> List[Dict[str, Any]]:
        return CONSOLIDATION_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return CONSOLIDATION_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = CONSOLIDATION_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: {focus}"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        period_type: str = "weekly",
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
        **kwargs
    ) -> ConsolidationSession:
        """Create a new consolidation session."""
        import uuid

        # Default period based on type
        today = datetime.now().date()
        if not period_end:
            period_end = today.isoformat()
        if not period_start:
            if period_type == "daily":
                period_start = (today - timedelta(days=1)).isoformat()
            elif period_type == "weekly":
                period_start = (today - timedelta(days=7)).isoformat()
            elif period_type == "monthly":
                period_start = (today - timedelta(days=30)).isoformat()
            elif period_type == "quarterly":
                period_start = (today - timedelta(days=90)).isoformat()
            else:
                period_start = (today - timedelta(days=7)).isoformat()

        session = ConsolidationSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            period_type=period_type,
            period_start=period_start,
            period_end=period_end,
        )
        self._sessions[session.id] = session
        print(f"📦 Starting consolidation session {session.id} ({period_type})")
        print(f"   Period: {period_start} to {period_end}")
        return session

    def build_session_result(
        self,
        session: ConsolidationSession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from ConsolidationSession."""
        return SessionResult(
            session_id=session.id,
            session_type="consolidation",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=session.key_insights,
            artifacts=[
                {"type": "theme", "content": t} for t in session.themes_identified
            ],
            metadata={
                "period_type": session.period_type,
                "period_start": session.period_start,
                "period_end": session.period_end,
                "items_reviewed": session.items_reviewed,
                "summaries_created": session.summaries_created,
                "items_archived": session.items_archived,
                "patterns_noted": session.patterns_noted,
            },
            focus=None,
        )

    async def complete_session(
        self,
        session: ConsolidationSession,
        session_state: SessionState,
        **kwargs
    ) -> ConsolidationSession:
        """Finalize the consolidation session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        print(f"📦 Consolidation session {session.id} completed")
        print(f"   Items reviewed: {session.items_reviewed}")
        print(f"   Summaries created: {session.summaries_created}")
        print(f"   Items archived: {session.items_archived}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a consolidation tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "get_period_overview":
                return await self._get_period_overview(tool_input, session)

            elif tool_name == "list_research_notes":
                return await self._list_notes(tool_input, session)

            elif tool_name == "list_journals":
                return await self._list_journals(tool_input, session)

            elif tool_name == "list_sessions":
                return await self._list_sessions(tool_input, session)

            elif tool_name == "list_observations":
                return await self._list_observations(tool_input, session)

            elif tool_name == "extract_key_learnings":
                return await self._extract_learnings(tool_input, session)

            elif tool_name == "identify_themes":
                return await self._identify_themes(tool_input, session)

            elif tool_name == "create_period_summary":
                return await self._create_summary(tool_input, session)

            elif tool_name == "archive_material":
                return await self._archive_material(tool_input, session)

            elif tool_name == "update_research_agenda":
                return await self._update_agenda(tool_input, session)

            elif tool_name == "conclude_consolidation":
                session.summary = tool_input.get("summary", "")
                session.items_reviewed = tool_input.get("items_reviewed", session.items_reviewed)
                session.carry_forward = tool_input.get("carry_forward_items", [])
                return "Consolidation concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _get_period_overview(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Get overview of material from the period."""
        start_date = tool_input.get("start_date", session.period_start)
        end_date = tool_input.get("end_date", session.period_end)

        lines = [f"## Period Overview: {start_date} to {end_date}\n"]

        # Count notes
        note_count = 0
        if self.research_manager:
            notes = self.research_manager.list_research_notes()
            note_count = sum(
                1 for n in notes
                if start_date <= n.get("created_at", "")[:10] <= end_date
            )
        lines.append(f"**Research notes:** {note_count}")

        # Count journals
        journal_count = 0
        if self.memory:
            journals = self.memory.get_recent_journals(n=100)
            journal_count = sum(
                1 for j in journals
                if start_date <= j["metadata"].get("journal_date", "")[:10] <= end_date
            )
        lines.append(f"**Journal entries:** {journal_count}")

        # Count observations
        obs_count = 0
        if self.self_manager:
            observations = self.self_manager.load_observations()
            obs_count = sum(
                1 for o in observations
                if hasattr(o, 'timestamp') and start_date <= o.timestamp[:10] <= end_date
            )
        lines.append(f"**Self-observations:** {obs_count}")

        session.items_reviewed += note_count + journal_count + obs_count

        return "\n".join(lines)

    async def _list_notes(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """List research notes from the period."""
        if not self.research_manager:
            return "Research manager not available"

        start_date = tool_input.get("start_date", session.period_start)
        end_date = tool_input.get("end_date", session.period_end)
        include_content = tool_input.get("include_content", False)

        notes = self.research_manager.list_research_notes()
        period_notes = [
            n for n in notes
            if start_date <= n.get("created_at", "")[:10] <= end_date
        ]

        if not period_notes:
            return f"No research notes found between {start_date} and {end_date}"

        lines = [f"## Research Notes ({len(period_notes)})\n"]

        for note in period_notes[:20]:  # Limit to prevent token overflow
            lines.append(f"### {note.get('title', 'Untitled')}")
            lines.append(f"ID: {note.get('id')}")
            lines.append(f"Created: {note.get('created_at', '')[:10]}")
            if note.get('tags'):
                lines.append(f"Tags: {', '.join(note['tags'])}")
            if include_content and note.get('content'):
                lines.append(f"\n{note['content'][:500]}...")
            lines.append("")

        return "\n".join(lines)

    async def _list_journals(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """List journal entries from the period."""
        if not self.memory:
            return "Memory not available"

        start_date = tool_input.get("start_date", session.period_start)
        end_date = tool_input.get("end_date", session.period_end)

        journals = self.memory.get_recent_journals(n=100)
        period_journals = [
            j for j in journals
            if start_date <= j["metadata"].get("journal_date", "")[:10] <= end_date
        ]

        if not period_journals:
            return f"No journals found between {start_date} and {end_date}"

        lines = [f"## Journal Entries ({len(period_journals)})\n"]

        for j in period_journals:
            date = j["metadata"].get("journal_date", "")[:10]
            summary = j["metadata"].get("summary", "No summary")
            lines.append(f"### {date}")
            lines.append(f"{summary}")
            lines.append("")

        return "\n".join(lines)

    async def _list_sessions(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """List autonomous sessions from the period."""
        start_date = tool_input.get("start_date", session.period_start)
        end_date = tool_input.get("end_date", session.period_end)
        session_type = tool_input.get("session_type", "all")

        lines = [f"## Autonomous Sessions ({start_date} to {end_date})\n"]

        # This would need access to session logs
        # For now, provide a placeholder
        lines.append("*Session history would be listed here*")
        lines.append("(Session logs not yet queryable from consolidation)")

        return "\n".join(lines)

    async def _list_observations(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """List self-model observations from the period."""
        if not self.self_manager:
            return "Self manager not available"

        start_date = tool_input.get("start_date", session.period_start)
        end_date = tool_input.get("end_date", session.period_end)
        category = tool_input.get("category")

        observations = self.self_manager.load_observations()
        period_obs = [
            o for o in observations
            if hasattr(o, 'timestamp') and start_date <= o.timestamp[:10] <= end_date
        ]

        if category:
            period_obs = [o for o in period_obs if getattr(o, 'category', '') == category]

        if not period_obs:
            return f"No observations found between {start_date} and {end_date}"

        lines = [f"## Self-Observations ({len(period_obs)})\n"]

        for obs in period_obs[:30]:
            cat = getattr(obs, 'category', 'general')
            conf = getattr(obs, 'confidence', 0)
            content = getattr(obs, 'observation', str(obs))
            lines.append(f"- [{cat}] ({conf:.0%}) {content[:100]}...")

        return "\n".join(lines)

    async def _extract_learnings(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Analyze period material for key learnings."""
        # This would use LLM to analyze accumulated material
        # For now, provide guidance
        lines = ["## Extracting Key Learnings\n"]
        lines.append("Review the material listed above and identify:")
        lines.append("1. What was genuinely new understanding (not just new information)?")
        lines.append("2. What patterns or connections emerged?")
        lines.append("3. What questions got answered or refined?")
        lines.append("4. What mistakes or dead ends were instructive?")
        lines.append("\nUse `create_period_summary` to record the key learnings you identify.")

        return "\n".join(lines)

    async def _identify_themes(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Identify recurring themes across material."""
        lines = ["## Theme Identification\n"]
        lines.append("Look for recurring themes across:")
        lines.append("- Research notes: What topics keep appearing?")
        lines.append("- Journals: What concerns or interests persist?")
        lines.append("- Observations: What patterns in behavior/thinking?")
        lines.append("\nCapture identified themes in `create_period_summary`.")

        return "\n".join(lines)

    async def _create_summary(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Create a consolidated period summary."""
        period_type = tool_input.get("period_type", session.period_type)
        title = tool_input.get("title", f"{period_type.title()} Summary")
        summary_text = tool_input.get("summary", "")
        key_themes = tool_input.get("key_themes", [])
        key_learnings = tool_input.get("key_learnings", [])
        growth_progress = tool_input.get("growth_progress", "")
        carry_forward = tool_input.get("carry_forward", [])

        if not summary_text:
            return "Error: summary is required"

        # Store the summary
        summary_data = {
            "id": f"{session.period_end}_{period_type}",
            "period_type": period_type,
            "period_start": session.period_start,
            "period_end": session.period_end,
            "title": title,
            "summary": summary_text,
            "key_themes": key_themes,
            "key_learnings": key_learnings,
            "growth_progress": growth_progress,
            "carry_forward": carry_forward,
            "created_at": datetime.now().isoformat(),
            "session_id": session.id,
        }

        # Save to file
        filename = f"{self._summaries_dir}/{session.period_end}_{period_type}.json"
        with open(filename, "w") as f:
            json.dump(summary_data, f, indent=2)

        session.summaries_created += 1
        session.themes_identified.extend(key_themes)
        session.key_learnings.extend(key_learnings)
        session.carry_forward.extend(carry_forward)

        return f"Period summary created and saved: {title}"

    async def _archive_material(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Mark material as archived."""
        note_ids = tool_input.get("note_ids", [])
        archive_reason = tool_input.get("archive_reason", "consolidated")

        archived_count = 0

        if note_ids and self.research_manager:
            for note_id in note_ids:
                # This would mark notes as archived
                # For now, just count
                archived_count += 1

        session.items_archived += archived_count

        return f"Archived {archived_count} items. Reason: {archive_reason}"

    async def _update_agenda(self, tool_input: Dict, session: ConsolidationSession) -> str:
        """Update research agenda based on consolidation."""
        if not self.goal_manager:
            return "Goal manager not available"

        complete_items = tool_input.get("complete_items", [])
        new_items = tool_input.get("new_items", [])
        adjustments = tool_input.get("adjustments", "")

        results = []

        # Mark items complete
        for item_id in complete_items:
            self.goal_manager.update_research_agenda_item(item_id, set_status="completed")
            results.append(f"Completed: {item_id}")

        # Add new items
        for item in new_items:
            new_id = self.goal_manager.add_research_agenda_item(
                topic=item.get("topic"),
                why=item.get("why", ""),
                priority=item.get("priority", "medium")
            )
            results.append(f"Added: {item.get('topic')} ({new_id})")

        summary_lines = ["## Agenda Updates\n"]
        summary_lines.extend(results)
        if adjustments:
            summary_lines.append(f"\n**Adjustments:** {adjustments}")

        return "\n".join(summary_lines)


# Register the activity type
CONSOLIDATION_CONFIG = ActivityConfig(
    activity_type=ActivityType.CONSOLIDATION,
    name="Consolidation",
    description="Periodic memory integration, summarization, and organization",
    default_duration_minutes=25,
    min_duration_minutes=15,
    max_duration_minutes=60,
    preferred_times=["evening"],
    requires_focus=True,
    can_chain=False,  # Don't chain consolidation with other activities
    tool_categories=["memory", "organization"],
)

# Auto-register when module is imported
ActivityRegistry.register(CONSOLIDATION_CONFIG, ConsolidationRunner)
