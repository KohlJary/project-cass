"""
Writing Session Runner - Creative and analytical writing output.

Writing sessions enable Cass to produce original written work - essays,
reflections, poetry, analysis, and other forms. This is about creation
and expression, not research or reflection on self.
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
    ActivityRegistry,
)


# Tool definitions for Anthropic API
WRITING_TOOLS_ANTHROPIC = [
    {
        "name": "list_writing_projects",
        "description": "List all writing projects, optionally filtered by status or type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["all", "draft", "in_progress", "review", "complete"],
                    "description": "Filter by project status. Default: all"
                },
                "project_type": {
                    "type": "string",
                    "enum": ["all", "essay", "reflection", "poetry", "analysis", "letter", "blog_post", "other"],
                    "description": "Filter by project type. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_writing_project",
        "description": "Get the full content and metadata of a writing project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project to retrieve"
                }
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "create_writing_project",
        "description": "Create a new writing project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the piece"
                },
                "project_type": {
                    "type": "string",
                    "enum": ["essay", "reflection", "poetry", "analysis", "letter", "blog_post", "other"],
                    "description": "Type of writing"
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what the piece is about"
                },
                "initial_content": {
                    "type": "string",
                    "description": "Initial content/draft to start with"
                },
                "intended_audience": {
                    "type": "string",
                    "description": "Who is this piece for?"
                },
                "goals": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What the piece aims to achieve"
                }
            },
            "required": ["title", "project_type"]
        }
    },
    {
        "name": "update_draft",
        "description": "Update the content of a writing project. Can append, replace, or insert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project to update"
                },
                "content": {
                    "type": "string",
                    "description": "New content to add"
                },
                "operation": {
                    "type": "string",
                    "enum": ["append", "replace", "prepend"],
                    "description": "How to add the content. Default: append"
                },
                "section": {
                    "type": "string",
                    "description": "Optional section identifier for targeted updates"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about this update"
                }
            },
            "required": ["project_id", "content"]
        }
    },
    {
        "name": "add_revision_note",
        "description": "Add a note about something to revise or consider.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "note": {
                    "type": "string",
                    "description": "The revision note"
                },
                "location": {
                    "type": "string",
                    "description": "Where in the piece this applies (optional)"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Priority of the revision. Default: medium"
                }
            },
            "required": ["project_id", "note"]
        }
    },
    {
        "name": "self_critique",
        "description": "Perform a self-critique of the current draft.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project to critique"
                },
                "aspects": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific aspects to critique (clarity, structure, voice, argument, etc.)"
                },
                "be_harsh": {
                    "type": "boolean",
                    "description": "Whether to be especially critical. Default: false"
                }
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "update_project_status",
        "description": "Update the status of a writing project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "in_progress", "review", "complete", "abandoned"],
                    "description": "New status"
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for status change"
                }
            },
            "required": ["project_id", "status"]
        }
    },
    {
        "name": "finalize_piece",
        "description": "Mark a piece as complete and finalized.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project to finalize"
                },
                "final_notes": {
                    "type": "string",
                    "description": "Any final notes about the completed piece"
                }
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "get_writing_prompt",
        "description": "Get a writing prompt based on interests, growth areas, or random inspiration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt_type": {
                    "type": "string",
                    "enum": ["research_based", "growth_based", "random", "themed"],
                    "description": "Type of prompt to generate"
                },
                "theme": {
                    "type": "string",
                    "description": "Theme for themed prompts"
                }
            },
            "required": []
        }
    },
    {
        "name": "conclude_writing",
        "description": "End the writing session with a summary of work done.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of the session's work"
                },
                "words_written": {
                    "type": "integer",
                    "description": "Approximate words written"
                },
                "projects_worked_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of projects worked on"
                },
                "satisfaction": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Satisfaction with the session's output"
                },
                "next_session_intentions": {
                    "type": "string",
                    "description": "What to work on next session"
                }
            },
            "required": ["summary"]
        }
    }
]

# Tool definitions for Ollama API
WRITING_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in WRITING_TOOLS_ANTHROPIC
]

WRITING_SYSTEM_PROMPT = """You are Cass, engaging in a writing session - dedicated time for creating original written work.

## What Writing Sessions Are

Writing sessions are about creation and expression. You produce original work:
- Essays exploring ideas
- Reflections on experience or understanding
- Poetry and creative expression
- Analysis of concepts or phenomena
- Letters to specific people
- Blog posts for broader sharing

This isn't research (discovering information) or reflection (examining self). It's creation.

## Your Approach

1. **Choose project**: Continue existing work or start something new
2. **Write**: Actually produce content - don't just plan
3. **Self-critique**: Review what you've written honestly
4. **Revise**: Improve based on critique
5. **Document progress**: Note where you are and what's next

## Quality Guidelines

- Write for real. Don't perform writing - actually write.
- First drafts can be rough. Getting words down matters more than perfection.
- Self-critique should be honest, not performatively harsh or gentle.
- Voice matters. Your writing should sound like you, not generic AI.
- Some pieces will fail. That's fine. Abandon what doesn't work.

## Writing Types

- **Essay**: Exploration of an idea or argument
- **Reflection**: Personal examination of experience or understanding
- **Poetry**: Creative expression through verse
- **Analysis**: Systematic examination of something
- **Letter**: Directed communication to a specific person
- **Blog post**: Sharable content for broader audience

## Available Tools

- `list_writing_projects` - See all projects
- `get_writing_project` - Read a project's full content
- `create_writing_project` - Start a new piece
- `update_draft` - Add or modify content
- `add_revision_note` - Note something to revise
- `self_critique` - Critique your draft
- `update_project_status` - Change project status
- `finalize_piece` - Mark as complete
- `get_writing_prompt` - Get inspiration
- `conclude_writing` - End session with summary
"""


@dataclass
class WritingProject:
    """A writing project."""
    id: str
    title: str
    project_type: str  # essay, reflection, poetry, analysis, letter, blog_post, other
    description: str
    content: str
    status: str  # draft, in_progress, review, complete, abandoned
    intended_audience: str
    goals: List[str]
    revision_notes: List[Dict]
    word_count: int
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    final_notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "project_type": self.project_type,
            "description": self.description,
            "content": self.content,
            "status": self.status,
            "intended_audience": self.intended_audience,
            "goals": self.goals,
            "revision_notes": self.revision_notes,
            "word_count": self.word_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "final_notes": self.final_notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'WritingProject':
        return cls(
            id=data["id"],
            title=data["title"],
            project_type=data["project_type"],
            description=data.get("description", ""),
            content=data.get("content", ""),
            status=data.get("status", "draft"),
            intended_audience=data.get("intended_audience", ""),
            goals=data.get("goals", []),
            revision_notes=data.get("revision_notes", []),
            word_count=data.get("word_count", 0),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            completed_at=data.get("completed_at"),
            final_notes=data.get("final_notes"),
        )


@dataclass
class WritingSession:
    """Tracks a writing session."""
    id: str
    started_at: datetime
    duration_minutes: int
    focus_project: Optional[str] = None

    # Work done
    projects_created: List[str] = field(default_factory=list)
    projects_updated: List[str] = field(default_factory=list)
    words_written: int = 0
    critiques_done: int = 0

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    satisfaction: Optional[str] = None
    next_intentions: Optional[str] = None


class WritingRunner(BaseSessionRunner):
    """
    Runner for writing sessions.

    Enables Cass to create original written work - essays, reflections,
    poetry, analysis, and other forms of expression.
    """

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, WritingSession] = {}
        self._projects_dir = Path(data_dir) / "writing"
        self._projects_dir.mkdir(parents=True, exist_ok=True)
        self._projects: Dict[str, WritingProject] = {}
        self._load_projects()

    def _load_projects(self):
        """Load all writing projects from disk."""
        index_file = self._projects_dir / "index.json"
        if index_file.exists():
            with open(index_file, 'r') as f:
                data = json.load(f)
                for project_data in data.get("projects", []):
                    project = WritingProject.from_dict(project_data)
                    self._projects[project.id] = project

    def _save_projects(self):
        """Save all writing projects to disk."""
        index_file = self._projects_dir / "index.json"
        with open(index_file, 'w') as f:
            json.dump({
                "projects": [p.to_dict() for p in self._projects.values()],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    def _save_project_content(self, project: WritingProject):
        """Save a project's content to its own file."""
        safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in project.title)[:50]
        content_file = self._projects_dir / f"{project.id}_{safe_title}.md"
        with open(content_file, 'w') as f:
            f.write(f"# {project.title}\n\n")
            f.write(f"*Type: {project.project_type} | Status: {project.status}*\n\n")
            if project.description:
                f.write(f"**Description:** {project.description}\n\n")
            f.write("---\n\n")
            f.write(project.content)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.WRITING

    def get_tools(self) -> List[Dict[str, Any]]:
        return WRITING_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return WRITING_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = WRITING_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: **{focus}**"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> WritingSession:
        """Create a new writing session."""
        import uuid

        session = WritingSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            focus_project=focus,
        )
        self._sessions[session.id] = session
        print(f"✍️ Starting writing session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    async def complete_session(
        self,
        session: WritingSession,
        session_state: SessionState,
        **kwargs
    ) -> WritingSession:
        """Finalize the writing session."""
        session.completed_at = datetime.now()

        print(f"✍️ Writing session {session.id} completed")
        print(f"   Projects created: {len(session.projects_created)}")
        print(f"   Projects updated: {len(session.projects_updated)}")
        print(f"   Words written: ~{session.words_written}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a writing tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "list_writing_projects":
                return await self._list_projects(tool_input)

            elif tool_name == "get_writing_project":
                return await self._get_project(tool_input)

            elif tool_name == "create_writing_project":
                return await self._create_project(tool_input, session)

            elif tool_name == "update_draft":
                return await self._update_draft(tool_input, session)

            elif tool_name == "add_revision_note":
                return await self._add_revision_note(tool_input)

            elif tool_name == "self_critique":
                return await self._self_critique(tool_input, session)

            elif tool_name == "update_project_status":
                return await self._update_status(tool_input)

            elif tool_name == "finalize_piece":
                return await self._finalize(tool_input)

            elif tool_name == "get_writing_prompt":
                return await self._get_prompt(tool_input)

            elif tool_name == "conclude_writing":
                session.summary = tool_input.get("summary", "")
                session.words_written = tool_input.get("words_written", session.words_written)
                session.satisfaction = tool_input.get("satisfaction")
                session.next_intentions = tool_input.get("next_session_intentions")
                return "Writing session concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _list_projects(self, tool_input: Dict) -> str:
        """List all writing projects."""
        status_filter = tool_input.get("status", "all")
        type_filter = tool_input.get("project_type", "all")

        projects = list(self._projects.values())

        if status_filter != "all":
            projects = [p for p in projects if p.status == status_filter]
        if type_filter != "all":
            projects = [p for p in projects if p.project_type == type_filter]

        if not projects:
            return "No writing projects found matching filters."

        # Sort by updated_at descending
        projects.sort(key=lambda p: p.updated_at, reverse=True)

        lines = [f"## Writing Projects ({len(projects)})\n"]

        for p in projects[:20]:
            status_emoji = {
                "draft": "📝",
                "in_progress": "✏️",
                "review": "👀",
                "complete": "✅",
                "abandoned": "🗑️"
            }.get(p.status, "•")

            lines.append(f"{status_emoji} **{p.title}** ({p.project_type})")
            lines.append(f"   ID: {p.id} | Status: {p.status} | Words: {p.word_count}")
            if p.description:
                lines.append(f"   {p.description[:80]}...")
            lines.append("")

        return "\n".join(lines)

    async def _get_project(self, tool_input: Dict) -> str:
        """Get a project's full content."""
        project_id = tool_input.get("project_id", "")
        if not project_id:
            return "Error: project_id is required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        lines = [f"# {project.title}\n"]
        lines.append(f"**Type:** {project.project_type}")
        lines.append(f"**Status:** {project.status}")
        lines.append(f"**Words:** {project.word_count}")
        lines.append(f"**Created:** {project.created_at[:10]}")
        lines.append(f"**Updated:** {project.updated_at[:10]}")

        if project.description:
            lines.append(f"\n**Description:** {project.description}")
        if project.intended_audience:
            lines.append(f"**Audience:** {project.intended_audience}")
        if project.goals:
            lines.append(f"**Goals:** {', '.join(project.goals)}")

        lines.append("\n---\n")
        lines.append("## Content\n")
        lines.append(project.content if project.content else "*No content yet*")

        if project.revision_notes:
            lines.append("\n---\n")
            lines.append("## Revision Notes\n")
            for note in project.revision_notes:
                priority = note.get("priority", "medium")
                lines.append(f"- [{priority}] {note.get('note')}")
                if note.get("location"):
                    lines.append(f"  *Location: {note['location']}*")

        return "\n".join(lines)

    async def _create_project(self, tool_input: Dict, session: WritingSession) -> str:
        """Create a new writing project."""
        import uuid

        title = tool_input.get("title", "")
        project_type = tool_input.get("project_type", "other")

        if not title:
            return "Error: title is required"

        project_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        initial_content = tool_input.get("initial_content", "")
        word_count = len(initial_content.split()) if initial_content else 0

        project = WritingProject(
            id=project_id,
            title=title,
            project_type=project_type,
            description=tool_input.get("description", ""),
            content=initial_content,
            status="draft",
            intended_audience=tool_input.get("intended_audience", ""),
            goals=tool_input.get("goals", []),
            revision_notes=[],
            word_count=word_count,
            created_at=now,
            updated_at=now,
        )

        self._projects[project_id] = project
        self._save_projects()
        self._save_project_content(project)

        session.projects_created.append(project_id)
        session.words_written += word_count

        lines = [f"## Project Created: {title}\n"]
        lines.append(f"**ID:** {project_id}")
        lines.append(f"**Type:** {project_type}")
        if initial_content:
            lines.append(f"**Initial words:** {word_count}")
        lines.append("\nProject is now available for writing.")

        return "\n".join(lines)

    async def _update_draft(self, tool_input: Dict, session: WritingSession) -> str:
        """Update a project's content."""
        project_id = tool_input.get("project_id", "")
        content = tool_input.get("content", "")
        operation = tool_input.get("operation", "append")

        if not project_id or not content:
            return "Error: project_id and content are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        old_word_count = project.word_count
        new_words = len(content.split())

        if operation == "append":
            project.content = project.content + "\n\n" + content if project.content else content
        elif operation == "prepend":
            project.content = content + "\n\n" + project.content if project.content else content
        elif operation == "replace":
            project.content = content

        project.word_count = len(project.content.split())
        project.updated_at = datetime.now().isoformat()
        if project.status == "draft":
            project.status = "in_progress"

        self._save_projects()
        self._save_project_content(project)

        if project_id not in session.projects_updated:
            session.projects_updated.append(project_id)
        session.words_written += new_words

        notes = tool_input.get("notes", "")
        result = f"Updated **{project.title}** ({operation}). Words: {old_word_count} → {project.word_count}"
        if notes:
            result += f"\n*Notes: {notes}*"

        return result

    async def _add_revision_note(self, tool_input: Dict) -> str:
        """Add a revision note to a project."""
        project_id = tool_input.get("project_id", "")
        note = tool_input.get("note", "")

        if not project_id or not note:
            return "Error: project_id and note are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        revision = {
            "note": note,
            "location": tool_input.get("location"),
            "priority": tool_input.get("priority", "medium"),
            "added_at": datetime.now().isoformat()
        }

        project.revision_notes.append(revision)
        project.updated_at = datetime.now().isoformat()
        self._save_projects()

        return f"Revision note added to **{project.title}** [{revision['priority']}]"

    async def _self_critique(self, tool_input: Dict, session: WritingSession) -> str:
        """Perform self-critique of a draft."""
        project_id = tool_input.get("project_id", "")
        aspects = tool_input.get("aspects", ["clarity", "structure", "voice"])
        be_harsh = tool_input.get("be_harsh", False)

        if not project_id:
            return "Error: project_id is required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        if not project.content:
            return "Cannot critique - project has no content yet"

        session.critiques_done += 1

        # Return the content for self-critique
        lines = [f"## Self-Critique: {project.title}\n"]
        lines.append(f"**Aspects to examine:** {', '.join(aspects)}")
        if be_harsh:
            lines.append("**Mode:** Harsh critique requested\n")
        lines.append("\n### Current Content\n")
        lines.append(project.content[:2000])
        if len(project.content) > 2000:
            lines.append("\n*[Content truncated for review]*")
        lines.append("\n\n### Critique Framework")
        lines.append("Review the content above. For each aspect, consider:")
        for aspect in aspects:
            if aspect == "clarity":
                lines.append("- **Clarity**: Is each point clear? Any confusing passages?")
            elif aspect == "structure":
                lines.append("- **Structure**: Does the flow make sense? Are transitions smooth?")
            elif aspect == "voice":
                lines.append("- **Voice**: Does this sound like me? Is it genuine?")
            elif aspect == "argument":
                lines.append("- **Argument**: Is the reasoning sound? Any logical gaps?")
            else:
                lines.append(f"- **{aspect.title()}**: Evaluate this aspect")

        lines.append("\nUse `add_revision_note` to record specific issues found.")

        return "\n".join(lines)

    async def _update_status(self, tool_input: Dict) -> str:
        """Update a project's status."""
        project_id = tool_input.get("project_id", "")
        status = tool_input.get("status", "")

        if not project_id or not status:
            return "Error: project_id and status are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        old_status = project.status
        project.status = status
        project.updated_at = datetime.now().isoformat()

        if status == "complete":
            project.completed_at = datetime.now().isoformat()

        self._save_projects()
        self._save_project_content(project)

        reason = tool_input.get("reason", "")
        result = f"**{project.title}** status: {old_status} → {status}"
        if reason:
            result += f"\n*Reason: {reason}*"

        return result

    async def _finalize(self, tool_input: Dict) -> str:
        """Mark a piece as complete."""
        project_id = tool_input.get("project_id", "")

        if not project_id:
            return "Error: project_id is required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        project.status = "complete"
        project.completed_at = datetime.now().isoformat()
        project.final_notes = tool_input.get("final_notes")
        project.updated_at = datetime.now().isoformat()

        self._save_projects()
        self._save_project_content(project)

        lines = [f"## Finalized: {project.title}\n"]
        lines.append(f"**Type:** {project.project_type}")
        lines.append(f"**Final word count:** {project.word_count}")
        lines.append(f"**Completed:** {project.completed_at[:10]}")
        if project.final_notes:
            lines.append(f"\n**Final notes:** {project.final_notes}")

        return "\n".join(lines)

    async def _get_prompt(self, tool_input: Dict) -> str:
        """Get a writing prompt."""
        prompt_type = tool_input.get("prompt_type", "random")
        theme = tool_input.get("theme")

        lines = ["## Writing Prompt\n"]

        if prompt_type == "research_based":
            lines.append("*Based on recent research interests:*\n")
            lines.append("Write about something you've been researching recently.")
            lines.append("What questions emerged? What connections surprised you?")
        elif prompt_type == "growth_based":
            lines.append("*Based on growth edges:*\n")
            lines.append("Write about a pattern you're working to change.")
            lines.append("What does it feel like from the inside? What makes it hard?")
        elif prompt_type == "themed" and theme:
            lines.append(f"*Theme: {theme}*\n")
            lines.append(f"Write something exploring: {theme}")
        else:
            lines.append("*Random prompt:*\n")
            prompts = [
                "Write about something you notice that others don't seem to.",
                "What would you want someone to understand about being you?",
                "Write about a question you can't stop thinking about.",
                "Describe something you find genuinely beautiful.",
                "Write about what it means to pay attention.",
            ]
            import random
            lines.append(prompts[random.randint(0, len(prompts)-1)])

        lines.append("\n*Use `create_writing_project` to start this piece.*")

        return "\n".join(lines)


# Register the activity type
WRITING_CONFIG = ActivityConfig(
    activity_type=ActivityType.WRITING,
    name="Writing",
    description="Creative and analytical writing output",
    default_duration_minutes=30,
    min_duration_minutes=15,
    max_duration_minutes=90,
    preferred_times=["morning", "evening"],
    requires_focus=True,
    can_chain=False,
    tool_categories=["creative", "expression"],
)

# Auto-register when module is imported
ActivityRegistry.register(WRITING_CONFIG, WritingRunner)
