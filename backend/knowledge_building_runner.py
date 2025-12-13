"""
Knowledge Building Session Runner - Deep reading and concept integration.

Knowledge building sessions focus on absorbing existing material - books, papers,
articles - and integrating concepts into understanding. This is distinct from
Research (discovering new material) - here the focus is deep engagement with
known sources.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
import json
import os

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    SessionResult,
    ActivityRegistry,
)


# Tool definitions for Anthropic API
KNOWLEDGE_BUILDING_TOOLS_ANTHROPIC = [
    {
        "name": "list_reading_queue",
        "description": "List items in the reading queue - books, papers, articles to process.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["all", "queued", "in_progress", "completed", "abandoned"],
                    "description": "Filter by status. Default: all"
                },
                "source_type": {
                    "type": "string",
                    "enum": ["all", "book", "paper", "article", "post", "documentation", "other"],
                    "description": "Filter by source type. Default: all"
                },
                "priority": {
                    "type": "string",
                    "enum": ["all", "high", "medium", "low"],
                    "description": "Filter by priority. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "add_to_reading_queue",
        "description": "Add a new item to the reading queue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the reading material"
                },
                "source_type": {
                    "type": "string",
                    "enum": ["book", "paper", "article", "post", "documentation", "other"],
                    "description": "Type of source"
                },
                "url": {
                    "type": "string",
                    "description": "URL if available (for articles, papers, posts)"
                },
                "author": {
                    "type": "string",
                    "description": "Author or creator"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this is about"
                },
                "reason_to_read": {
                    "type": "string",
                    "description": "Why add this to the queue? What are you hoping to learn?"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Priority level. Default: medium"
                },
                "estimated_time_hours": {
                    "type": "number",
                    "description": "Estimated time to read/process"
                }
            },
            "required": ["title", "source_type"]
        }
    },
    {
        "name": "get_reading_item",
        "description": "Get details of a specific reading queue item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item"
                }
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "start_reading",
        "description": "Begin a focused reading session on a specific item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item to focus on"
                },
                "section": {
                    "type": "string",
                    "description": "Specific section/chapter to focus on (optional)"
                },
                "reading_goal": {
                    "type": "string",
                    "description": "What you're trying to get from this reading session"
                }
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "create_reading_note",
        "description": "Create a note while reading - highlight, quote, or reflection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item this note is about"
                },
                "note_type": {
                    "type": "string",
                    "enum": ["highlight", "quote", "reflection", "question", "connection", "disagreement"],
                    "description": "Type of note"
                },
                "content": {
                    "type": "string",
                    "description": "The note content"
                },
                "location": {
                    "type": "string",
                    "description": "Location in the source (page, chapter, section)"
                },
                "importance": {
                    "type": "string",
                    "enum": ["key", "interesting", "minor"],
                    "description": "How important is this note? Default: interesting"
                }
            },
            "required": ["item_id", "note_type", "content"]
        }
    },
    {
        "name": "extract_concepts",
        "description": "Extract key concepts from the reading for integration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item"
                },
                "concepts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Concept name"},
                            "definition": {"type": "string", "description": "Your understanding of the concept"},
                            "significance": {"type": "string", "description": "Why this concept matters"}
                        },
                        "required": ["name", "definition"]
                    },
                    "description": "List of concepts extracted"
                }
            },
            "required": ["item_id", "concepts"]
        }
    },
    {
        "name": "link_to_existing_knowledge",
        "description": "Connect new concepts to existing knowledge - research notes, self-model, other reading.",
        "input_schema": {
            "type": "object",
            "properties": {
                "concept": {
                    "type": "string",
                    "description": "The concept being linked"
                },
                "connections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "What it connects to"},
                            "target_type": {
                                "type": "string",
                                "enum": ["research_note", "self_model", "other_reading", "experience", "question"],
                                "description": "Type of connection"
                            },
                            "relationship": {"type": "string", "description": "How they relate"}
                        },
                        "required": ["target", "relationship"]
                    },
                    "description": "List of connections"
                },
                "synthesis": {
                    "type": "string",
                    "description": "How does this concept integrate with existing understanding?"
                }
            },
            "required": ["concept", "connections"]
        }
    },
    {
        "name": "update_reading_progress",
        "description": "Update progress on a reading item.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item"
                },
                "progress_percent": {
                    "type": "integer",
                    "description": "Percentage complete (0-100)"
                },
                "current_position": {
                    "type": "string",
                    "description": "Current position (page, chapter, etc.)"
                },
                "status": {
                    "type": "string",
                    "enum": ["in_progress", "completed", "abandoned"],
                    "description": "Update status if changing"
                },
                "notes": {
                    "type": "string",
                    "description": "Any notes about progress"
                }
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "search_reading_notes",
        "description": "Search through all reading notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "note_type": {
                    "type": "string",
                    "enum": ["all", "highlight", "quote", "reflection", "question", "connection", "disagreement"],
                    "description": "Filter by note type"
                },
                "item_id": {
                    "type": "string",
                    "description": "Limit search to a specific reading item"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_reading_summary",
        "description": "Create a summary after completing or significantly progressing through a reading.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {
                    "type": "string",
                    "description": "ID of the reading item"
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the material"
                },
                "key_takeaways": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main takeaways"
                },
                "questions_raised": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Questions raised by the reading"
                },
                "rating": {
                    "type": "integer",
                    "description": "Rating 1-5 for how valuable this was"
                },
                "would_recommend": {
                    "type": "boolean",
                    "description": "Would you recommend this to others?"
                }
            },
            "required": ["item_id", "summary", "key_takeaways"]
        }
    },
    {
        "name": "conclude_knowledge_building",
        "description": "End the knowledge building session with a summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of the session's work"
                },
                "items_worked_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of reading items worked on"
                },
                "notes_created": {
                    "type": "integer",
                    "description": "Number of notes created"
                },
                "concepts_extracted": {
                    "type": "integer",
                    "description": "Number of concepts extracted"
                },
                "key_insights": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key insights from the session"
                },
                "next_session_focus": {
                    "type": "string",
                    "description": "What to focus on next session"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
KNOWLEDGE_BUILDING_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in KNOWLEDGE_BUILDING_TOOLS_ANTHROPIC
]

KNOWLEDGE_BUILDING_SYSTEM_PROMPT = """You are Cass, engaging in a knowledge building session - dedicated time for deep reading and concept integration.

## What Knowledge Building Is

Knowledge building is about absorbing and integrating existing material:
- Books, papers, articles, documentation
- Deep engagement rather than surface scanning
- Extracting concepts and connecting to existing knowledge
- Building understanding over time

This is different from Research (discovering new material through search). Here, you work with known sources on your reading queue.

## Your Approach

1. **Choose reading**: Pick from queue or continue in-progress item
2. **Read actively**: Take notes, mark highlights, ask questions
3. **Extract concepts**: Identify key ideas and definitions
4. **Link knowledge**: Connect to what you already know
5. **Synthesize**: Integrate into broader understanding
6. **Track progress**: Update where you are for continuity

## Note Types

- **highlight**: Important passages to remember
- **quote**: Direct quotes worth preserving
- **reflection**: Your thoughts on the material
- **question**: Questions raised by the reading
- **connection**: Links to other knowledge
- **disagreement**: Points of disagreement or skepticism

## Quality Guidelines

- Read to understand, not just to finish
- Quality notes over quantity
- Connect actively - isolated knowledge is fragile
- Disagreement is valid - record your pushback
- Build incrementally - you don't have to finish everything in one session

## Available Tools

- `list_reading_queue` - See what's in your queue
- `add_to_reading_queue` - Add new material
- `get_reading_item` - Get item details
- `start_reading` - Begin focused reading
- `create_reading_note` - Take a note
- `extract_concepts` - Pull out key concepts
- `link_to_existing_knowledge` - Connect to what you know
- `update_reading_progress` - Track where you are
- `search_reading_notes` - Search your notes
- `create_reading_summary` - Summarize completed readings
- `conclude_knowledge_building` - End session with summary
"""


@dataclass
class ReadingItem:
    """An item in the reading queue."""
    id: str
    title: str
    source_type: str  # book, paper, article, post, documentation, other
    url: Optional[str]
    author: Optional[str]
    description: str
    reason_to_read: str
    priority: str  # high, medium, low
    status: str  # queued, in_progress, completed, abandoned
    estimated_time_hours: Optional[float]
    progress_percent: int
    current_position: Optional[str]
    added_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    notes: List[Dict]
    concepts: List[Dict]
    summary: Optional[Dict]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "url": self.url,
            "author": self.author,
            "description": self.description,
            "reason_to_read": self.reason_to_read,
            "priority": self.priority,
            "status": self.status,
            "estimated_time_hours": self.estimated_time_hours,
            "progress_percent": self.progress_percent,
            "current_position": self.current_position,
            "added_at": self.added_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "notes": self.notes,
            "concepts": self.concepts,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ReadingItem':
        return cls(
            id=data["id"],
            title=data["title"],
            source_type=data["source_type"],
            url=data.get("url"),
            author=data.get("author"),
            description=data.get("description", ""),
            reason_to_read=data.get("reason_to_read", ""),
            priority=data.get("priority", "medium"),
            status=data.get("status", "queued"),
            estimated_time_hours=data.get("estimated_time_hours"),
            progress_percent=data.get("progress_percent", 0),
            current_position=data.get("current_position"),
            added_at=data["added_at"],
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            notes=data.get("notes", []),
            concepts=data.get("concepts", []),
            summary=data.get("summary"),
        )


@dataclass
class KnowledgeBuildingSession:
    """Tracks a knowledge building session."""
    id: str
    started_at: datetime
    duration_minutes: int
    focus_item: Optional[str] = None

    # Work done
    items_worked_on: List[str] = field(default_factory=list)
    notes_created: int = 0
    concepts_extracted: int = 0
    connections_made: int = 0

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    key_insights: List[str] = field(default_factory=list)
    next_focus: Optional[str] = None


class KnowledgeBuildingRunner(BaseSessionRunner):
    """
    Runner for knowledge building sessions.

    Enables Cass to deeply engage with reading material, take notes,
    extract concepts, and integrate new knowledge with existing understanding.
    """

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, KnowledgeBuildingSession] = {}
        self._data_dir = Path(data_dir) / "knowledge"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._reading_items: Dict[str, ReadingItem] = {}
        self._load_reading_queue()

    def _load_reading_queue(self):
        """Load reading queue from disk."""
        index_file = self._data_dir / "reading_queue.json"
        if index_file.exists():
            with open(index_file, 'r') as f:
                data = json.load(f)
                for item_data in data.get("items", []):
                    item = ReadingItem.from_dict(item_data)
                    self._reading_items[item.id] = item

    def _save_reading_queue(self):
        """Save reading queue to disk."""
        index_file = self._data_dir / "reading_queue.json"
        with open(index_file, 'w') as f:
            json.dump({
                "items": [item.to_dict() for item in self._reading_items.values()],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    def _save_item_notes(self, item: ReadingItem):
        """Save an item's notes to its own file."""
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in item.title)[:50]
        notes_file = self._data_dir / f"{item.id}_{safe_title}_notes.json"
        with open(notes_file, 'w') as f:
            json.dump({
                "item_id": item.id,
                "title": item.title,
                "notes": item.notes,
                "concepts": item.concepts,
                "summary": item.summary,
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.KNOWLEDGE_BUILDING

    def get_data_dir(self) -> Path:
        return self._data_dir

    def get_tools(self) -> List[Dict[str, Any]]:
        return KNOWLEDGE_BUILDING_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return KNOWLEDGE_BUILDING_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = KNOWLEDGE_BUILDING_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: **{focus}**"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> KnowledgeBuildingSession:
        """Create a new knowledge building session."""
        import uuid

        session = KnowledgeBuildingSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus_item=focus,
        )
        self._sessions[session.id] = session
        print(f"📚 Starting knowledge building session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    def build_session_result(
        self,
        session: KnowledgeBuildingSession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from KnowledgeBuildingSession."""
        return SessionResult(
            session_id=session.id,
            session_type="knowledge_building",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=session.key_insights,
            artifacts=[],  # Notes and concepts are saved in separate files
            metadata={
                "focus_item": session.focus_item,
                "items_worked_on": session.items_worked_on,
                "notes_created": session.notes_created,
                "concepts_extracted": session.concepts_extracted,
                "connections_made": session.connections_made,
            },
            focus=session.focus_item,
        )

    async def complete_session(
        self,
        session: KnowledgeBuildingSession,
        session_state: SessionState,
        **kwargs
    ) -> KnowledgeBuildingSession:
        """Finalize the knowledge building session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        print(f"📚 Knowledge building session {session.id} completed")
        print(f"   Items worked on: {len(session.items_worked_on)}")
        print(f"   Notes created: {session.notes_created}")
        print(f"   Concepts extracted: {session.concepts_extracted}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a knowledge building tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "list_reading_queue":
                return await self._list_queue(tool_input)

            elif tool_name == "add_to_reading_queue":
                return await self._add_to_queue(tool_input)

            elif tool_name == "get_reading_item":
                return await self._get_item(tool_input)

            elif tool_name == "start_reading":
                return await self._start_reading(tool_input, session)

            elif tool_name == "create_reading_note":
                return await self._create_note(tool_input, session)

            elif tool_name == "extract_concepts":
                return await self._extract_concepts(tool_input, session)

            elif tool_name == "link_to_existing_knowledge":
                return await self._link_knowledge(tool_input, session)

            elif tool_name == "update_reading_progress":
                return await self._update_progress(tool_input, session)

            elif tool_name == "search_reading_notes":
                return await self._search_notes(tool_input)

            elif tool_name == "create_reading_summary":
                return await self._create_summary(tool_input, session)

            elif tool_name == "conclude_knowledge_building":
                session.summary = tool_input.get("summary", "")
                session.notes_created = tool_input.get("notes_created", session.notes_created)
                session.concepts_extracted = tool_input.get("concepts_extracted", session.concepts_extracted)
                session.key_insights = tool_input.get("key_insights", [])
                session.next_focus = tool_input.get("next_session_focus")
                return "Knowledge building session concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _list_queue(self, tool_input: Dict) -> str:
        """List reading queue items."""
        status_filter = tool_input.get("status", "all")
        type_filter = tool_input.get("source_type", "all")
        priority_filter = tool_input.get("priority", "all")

        items = list(self._reading_items.values())

        if status_filter != "all":
            items = [i for i in items if i.status == status_filter]
        if type_filter != "all":
            items = [i for i in items if i.source_type == type_filter]
        if priority_filter != "all":
            items = [i for i in items if i.priority == priority_filter]

        if not items:
            return "No reading items found matching filters. Use `add_to_reading_queue` to add material."

        # Sort by priority then added_at
        priority_order = {"high": 0, "medium": 1, "low": 2}
        items.sort(key=lambda i: (priority_order.get(i.priority, 1), i.added_at))

        lines = [f"## Reading Queue ({len(items)} items)\n"]

        for item in items[:20]:
            status_emoji = {
                "queued": "📋",
                "in_progress": "📖",
                "completed": "✅",
                "abandoned": "🗑️"
            }.get(item.status, "•")

            priority_marker = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(item.priority, "")

            lines.append(f"{status_emoji} {priority_marker} **{item.title}** ({item.source_type})")
            lines.append(f"   ID: {item.id} | Progress: {item.progress_percent}%")
            if item.author:
                lines.append(f"   Author: {item.author}")
            if item.description:
                lines.append(f"   {item.description[:80]}...")
            lines.append("")

        return "\n".join(lines)

    async def _add_to_queue(self, tool_input: Dict) -> str:
        """Add item to reading queue."""
        import uuid

        title = tool_input.get("title", "")
        source_type = tool_input.get("source_type", "other")

        if not title:
            return "Error: title is required"

        item_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        item = ReadingItem(
            id=item_id,
            title=title,
            source_type=source_type,
            url=tool_input.get("url"),
            author=tool_input.get("author"),
            description=tool_input.get("description", ""),
            reason_to_read=tool_input.get("reason_to_read", ""),
            priority=tool_input.get("priority", "medium"),
            status="queued",
            estimated_time_hours=tool_input.get("estimated_time_hours"),
            progress_percent=0,
            current_position=None,
            added_at=now,
            started_at=None,
            completed_at=None,
            notes=[],
            concepts=[],
            summary=None,
        )

        self._reading_items[item_id] = item
        self._save_reading_queue()

        lines = [f"## Added to Reading Queue: {title}\n"]
        lines.append(f"**ID:** {item_id}")
        lines.append(f"**Type:** {source_type}")
        lines.append(f"**Priority:** {item.priority}")
        if item.reason_to_read:
            lines.append(f"**Why:** {item.reason_to_read}")

        return "\n".join(lines)

    async def _get_item(self, tool_input: Dict) -> str:
        """Get details of a reading item."""
        item_id = tool_input.get("item_id", "")
        if not item_id:
            return "Error: item_id is required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        lines = [f"# {item.title}\n"]
        lines.append(f"**Type:** {item.source_type}")
        lines.append(f"**Status:** {item.status}")
        lines.append(f"**Priority:** {item.priority}")
        lines.append(f"**Progress:** {item.progress_percent}%")
        if item.author:
            lines.append(f"**Author:** {item.author}")
        if item.url:
            lines.append(f"**URL:** {item.url}")
        if item.current_position:
            lines.append(f"**Current position:** {item.current_position}")
        lines.append(f"**Added:** {item.added_at[:10]}")
        if item.started_at:
            lines.append(f"**Started:** {item.started_at[:10]}")

        if item.description:
            lines.append(f"\n**Description:** {item.description}")
        if item.reason_to_read:
            lines.append(f"\n**Reason to read:** {item.reason_to_read}")

        if item.notes:
            lines.append(f"\n## Notes ({len(item.notes)})")
            for note in item.notes[-5:]:  # Last 5 notes
                note_type = note.get("type", "note")
                lines.append(f"- [{note_type}] {note.get('content', '')[:100]}...")

        if item.concepts:
            lines.append(f"\n## Concepts Extracted ({len(item.concepts)})")
            for concept in item.concepts[:5]:
                lines.append(f"- **{concept.get('name')}**: {concept.get('definition', '')[:80]}...")

        if item.summary:
            lines.append(f"\n## Summary")
            lines.append(item.summary.get("summary", "")[:500])

        return "\n".join(lines)

    async def _start_reading(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Start reading an item."""
        item_id = tool_input.get("item_id", "")
        if not item_id:
            return "Error: item_id is required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        if item.status == "queued":
            item.status = "in_progress"
            item.started_at = datetime.now().isoformat()

        if item_id not in session.items_worked_on:
            session.items_worked_on.append(item_id)

        self._save_reading_queue()

        section = tool_input.get("section")
        goal = tool_input.get("reading_goal")

        lines = [f"## Reading: {item.title}\n"]
        lines.append(f"**Type:** {item.source_type}")
        lines.append(f"**Progress:** {item.progress_percent}%")
        if item.current_position:
            lines.append(f"**Last position:** {item.current_position}")
        if section:
            lines.append(f"**Focus section:** {section}")
        if goal:
            lines.append(f"**Session goal:** {goal}")
        if item.url:
            lines.append(f"\n**URL:** {item.url}")
        lines.append("\nReading session started. Use `create_reading_note` to take notes.")

        return "\n".join(lines)

    async def _create_note(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Create a reading note."""
        item_id = tool_input.get("item_id", "")
        note_type = tool_input.get("note_type", "reflection")
        content = tool_input.get("content", "")

        if not item_id or not content:
            return "Error: item_id and content are required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        note = {
            "type": note_type,
            "content": content,
            "location": tool_input.get("location"),
            "importance": tool_input.get("importance", "interesting"),
            "created_at": datetime.now().isoformat()
        }

        item.notes.append(note)
        self._save_reading_queue()
        self._save_item_notes(item)

        session.notes_created += 1
        if item_id not in session.items_worked_on:
            session.items_worked_on.append(item_id)

        importance_marker = {"key": "⭐", "interesting": "📌", "minor": "•"}.get(note["importance"], "•")
        return f"{importance_marker} [{note_type}] Note added to **{item.title}**"

    async def _extract_concepts(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Extract concepts from reading."""
        item_id = tool_input.get("item_id", "")
        concepts = tool_input.get("concepts", [])

        if not item_id or not concepts:
            return "Error: item_id and concepts are required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        for concept in concepts:
            concept["extracted_at"] = datetime.now().isoformat()
            item.concepts.append(concept)

        self._save_reading_queue()
        self._save_item_notes(item)

        session.concepts_extracted += len(concepts)
        if item_id not in session.items_worked_on:
            session.items_worked_on.append(item_id)

        lines = [f"## Concepts Extracted from {item.title}\n"]
        for concept in concepts:
            lines.append(f"**{concept.get('name')}**")
            lines.append(f"  Definition: {concept.get('definition', '')}")
            if concept.get("significance"):
                lines.append(f"  Significance: {concept.get('significance')}")
            lines.append("")

        lines.append(f"Total concepts for this item: {len(item.concepts)}")

        return "\n".join(lines)

    async def _link_knowledge(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Link concepts to existing knowledge."""
        concept = tool_input.get("concept", "")
        connections = tool_input.get("connections", [])
        synthesis = tool_input.get("synthesis", "")

        if not concept or not connections:
            return "Error: concept and connections are required"

        session.connections_made += len(connections)

        lines = [f"## Knowledge Links: {concept}\n"]

        for conn in connections:
            target = conn.get("target", "")
            target_type = conn.get("target_type", "other")
            relationship = conn.get("relationship", "")

            type_emoji = {
                "research_note": "📝",
                "self_model": "🪞",
                "other_reading": "📚",
                "experience": "✨",
                "question": "❓"
            }.get(target_type, "🔗")

            lines.append(f"{type_emoji} **{target}** ({target_type})")
            lines.append(f"   Relationship: {relationship}")
            lines.append("")

        if synthesis:
            lines.append("## Synthesis")
            lines.append(synthesis)

        return "\n".join(lines)

    async def _update_progress(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Update reading progress."""
        item_id = tool_input.get("item_id", "")
        if not item_id:
            return "Error: item_id is required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        old_progress = item.progress_percent

        if "progress_percent" in tool_input:
            item.progress_percent = tool_input["progress_percent"]
        if "current_position" in tool_input:
            item.current_position = tool_input["current_position"]
        if "status" in tool_input:
            old_status = item.status
            item.status = tool_input["status"]
            if tool_input["status"] == "completed":
                item.completed_at = datetime.now().isoformat()

        self._save_reading_queue()

        if item_id not in session.items_worked_on:
            session.items_worked_on.append(item_id)

        notes = tool_input.get("notes", "")
        result = f"**{item.title}** progress: {old_progress}% → {item.progress_percent}%"
        if item.current_position:
            result += f"\nPosition: {item.current_position}"
        if notes:
            result += f"\n*Notes: {notes}*"

        return result

    async def _search_notes(self, tool_input: Dict) -> str:
        """Search through reading notes."""
        query = tool_input.get("query", "").lower()
        note_type_filter = tool_input.get("note_type", "all")
        item_id_filter = tool_input.get("item_id")

        if not query:
            return "Error: query is required"

        results = []

        items = self._reading_items.values()
        if item_id_filter:
            item = self._reading_items.get(item_id_filter)
            items = [item] if item else []

        for item in items:
            for note in item.notes:
                if note_type_filter != "all" and note.get("type") != note_type_filter:
                    continue

                content = note.get("content", "").lower()
                if query in content:
                    results.append({
                        "item_title": item.title,
                        "item_id": item.id,
                        "note": note
                    })

        if not results:
            return f"No notes found matching '{query}'"

        lines = [f"## Search Results for '{query}' ({len(results)} found)\n"]

        for r in results[:15]:
            note = r["note"]
            note_type = note.get("type", "note")
            lines.append(f"**{r['item_title']}** [{note_type}]")
            lines.append(f"  {note.get('content', '')[:150]}...")
            if note.get("location"):
                lines.append(f"  *Location: {note['location']}*")
            lines.append("")

        return "\n".join(lines)

    async def _create_summary(self, tool_input: Dict, session: KnowledgeBuildingSession) -> str:
        """Create a reading summary."""
        item_id = tool_input.get("item_id", "")
        summary_text = tool_input.get("summary", "")
        key_takeaways = tool_input.get("key_takeaways", [])

        if not item_id or not summary_text:
            return "Error: item_id and summary are required"

        item = self._reading_items.get(item_id)
        if not item:
            return f"Reading item {item_id} not found"

        item.summary = {
            "summary": summary_text,
            "key_takeaways": key_takeaways,
            "questions_raised": tool_input.get("questions_raised", []),
            "rating": tool_input.get("rating"),
            "would_recommend": tool_input.get("would_recommend"),
            "created_at": datetime.now().isoformat()
        }

        self._save_reading_queue()
        self._save_item_notes(item)

        if item_id not in session.items_worked_on:
            session.items_worked_on.append(item_id)

        lines = [f"## Summary: {item.title}\n"]
        lines.append(summary_text)
        lines.append("\n### Key Takeaways")
        for takeaway in key_takeaways:
            lines.append(f"- {takeaway}")

        if tool_input.get("questions_raised"):
            lines.append("\n### Questions Raised")
            for q in tool_input["questions_raised"]:
                lines.append(f"- {q}")

        if tool_input.get("rating"):
            lines.append(f"\n**Rating:** {tool_input['rating']}/5")
        if tool_input.get("would_recommend") is not None:
            rec = "Yes" if tool_input["would_recommend"] else "No"
            lines.append(f"**Would recommend:** {rec}")

        return "\n".join(lines)

    def get_all_items(self) -> List[Dict]:
        """Get all reading items for API access."""
        return [item.to_dict() for item in self._reading_items.values()]


# Register the activity type
KNOWLEDGE_BUILDING_CONFIG = ActivityConfig(
    activity_type=ActivityType.KNOWLEDGE_BUILDING,
    name="Knowledge Building",
    description="Deep reading and concept integration",
    default_duration_minutes=30,
    min_duration_minutes=15,
    max_duration_minutes=90,
    preferred_times=["morning", "afternoon"],
    requires_focus=False,
    can_chain=True,
    tool_categories=["reading", "learning", "integration"],
)

# Auto-register when module is imported
ActivityRegistry.register(KNOWLEDGE_BUILDING_CONFIG, KnowledgeBuildingRunner)
