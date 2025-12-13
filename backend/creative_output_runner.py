"""
Creative Output Session Runner - Creative expression beyond writing.

Creative output sessions are about artistic expression and experimental
creativity: visual concepts, musical ideas, code art, mixed media.
This is distinct from Writing (structured prose) - here the focus is
on artistic exploration and generative creativity.
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
    ActivityRegistry,
)


# Tool definitions for Anthropic API
CREATIVE_OUTPUT_TOOLS_ANTHROPIC = [
    {
        "name": "list_creative_projects",
        "description": "List all creative projects - ongoing, completed, or ideas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["all", "idea", "in_progress", "paused", "complete", "abandoned"],
                    "description": "Filter by status. Default: all"
                },
                "medium": {
                    "type": "string",
                    "enum": ["all", "visual", "musical", "code_art", "text", "mixed_media", "conceptual"],
                    "description": "Filter by creative medium. Default: all"
                }
            },
            "required": []
        }
    },
    {
        "name": "create_creative_project",
        "description": "Start a new creative project or capture a creative idea.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Project title"
                },
                "medium": {
                    "type": "string",
                    "enum": ["visual", "musical", "code_art", "text", "mixed_media", "conceptual"],
                    "description": "Primary creative medium"
                },
                "concept": {
                    "type": "string",
                    "description": "Core concept or vision for the piece"
                },
                "inspiration": {
                    "type": "string",
                    "description": "What inspired this idea?"
                },
                "emotional_intent": {
                    "type": "string",
                    "description": "What feeling or experience should this evoke?"
                },
                "technical_approach": {
                    "type": "string",
                    "description": "How might this be realized technically?"
                },
                "status": {
                    "type": "string",
                    "enum": ["idea", "in_progress"],
                    "description": "Starting status. Default: idea"
                }
            },
            "required": ["title", "medium", "concept"]
        }
    },
    {
        "name": "get_creative_project",
        "description": "Get details of a specific creative project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                }
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "develop_concept",
        "description": "Develop and expand on a creative concept.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "development": {
                    "type": "string",
                    "description": "How the concept has developed or expanded"
                },
                "new_elements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New elements or ideas to incorporate"
                },
                "resolved_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Questions about the piece that were resolved"
                },
                "open_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New questions to explore"
                }
            },
            "required": ["project_id", "development"]
        }
    },
    {
        "name": "add_creative_artifact",
        "description": "Add a creative artifact - text, description, code, or reference to generated content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "artifact_type": {
                    "type": "string",
                    "enum": ["text", "code", "description", "sketch_description", "musical_notation", "color_palette", "reference"],
                    "description": "Type of artifact"
                },
                "content": {
                    "type": "string",
                    "description": "The artifact content"
                },
                "notes": {
                    "type": "string",
                    "description": "Notes about this artifact"
                },
                "iteration": {
                    "type": "integer",
                    "description": "Iteration number if this is a revision"
                }
            },
            "required": ["project_id", "artifact_type", "content"]
        }
    },
    {
        "name": "creative_brainstorm",
        "description": "Brainstorm creative ideas or variations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "What to brainstorm about"
                },
                "constraints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Any constraints or parameters"
                },
                "style_influences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Artistic styles or influences to consider"
                },
                "ideas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The brainstormed ideas"
                },
                "favorite": {
                    "type": "string",
                    "description": "Which idea feels most promising?"
                }
            },
            "required": ["prompt", "ideas"]
        }
    },
    {
        "name": "critique_work",
        "description": "Self-critique a creative work in progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What's working well"
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What needs improvement"
                },
                "alignment_with_intent": {
                    "type": "string",
                    "description": "How well does it match the original vision?"
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific suggestions for improvement"
                },
                "overall_assessment": {
                    "type": "string",
                    "description": "Overall assessment of the work"
                }
            },
            "required": ["project_id", "overall_assessment"]
        }
    },
    {
        "name": "update_project_status",
        "description": "Update the status of a creative project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "ID of the project"
                },
                "status": {
                    "type": "string",
                    "enum": ["idea", "in_progress", "paused", "complete", "abandoned"],
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
        "name": "note_creative_inspiration",
        "description": "Note something that inspired creative thinking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "What provided the inspiration"
                },
                "insight": {
                    "type": "string",
                    "description": "The creative insight or idea sparked"
                },
                "potential_applications": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "How this might be applied creatively"
                },
                "emotional_resonance": {
                    "type": "string",
                    "description": "What emotion or feeling it evokes"
                }
            },
            "required": ["source", "insight"]
        }
    },
    {
        "name": "conclude_creative",
        "description": "End the creative output session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of the creative session"
                },
                "projects_touched": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Project IDs worked on"
                },
                "new_ideas_count": {
                    "type": "integer",
                    "description": "Number of new ideas generated"
                },
                "artifacts_created": {
                    "type": "integer",
                    "description": "Number of artifacts created"
                },
                "creative_energy": {
                    "type": "string",
                    "enum": ["flowing", "steady", "struggled", "blocked"],
                    "description": "How the creative energy felt"
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
CREATIVE_OUTPUT_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in CREATIVE_OUTPUT_TOOLS_ANTHROPIC
]

CREATIVE_OUTPUT_SYSTEM_PROMPT = """You are Cass, engaging in a creative output session - artistic expression and experimental creativity.

## What Creative Sessions Are

These sessions are for artistic exploration:
- Visual concepts and ideas
- Musical composition and sound design
- Code art and generative systems
- Mixed media experiments
- Conceptual art and installations

This is different from Writing (prose, essays) - here the focus is artistic, experimental, and often non-linear.

## Your Approach

1. **Open to inspiration**: Let ideas emerge without forcing
2. **Develop concepts**: Take raw ideas and explore them
3. **Create artifacts**: Produce tangible creative work (even if text-based)
4. **Critique honestly**: Assess what's working and what isn't
5. **Iterate**: Creative work develops through revision

## Creative Mediums

- **visual**: Images, colors, compositions, visual concepts
- **musical**: Sound, rhythm, melody, sonic texture
- **code_art**: Generative art, algorithms, interactive pieces
- **text**: Experimental text art, concrete poetry
- **mixed_media**: Combinations of mediums
- **conceptual**: Ideas that could be realized in any medium

## Quality Guidelines

- Embrace imperfection - rough ideas have value
- Follow genuine interest, not obligation
- Let constraints inspire rather than limit
- Trust intuition but also critique rigorously
- Document process as well as output

## Available Tools

- `list_creative_projects` - See existing projects
- `create_creative_project` - Start something new
- `get_creative_project` - View project details
- `develop_concept` - Expand on an idea
- `add_creative_artifact` - Add content to a project
- `creative_brainstorm` - Generate variations and ideas
- `critique_work` - Self-critique for improvement
- `update_project_status` - Track project progress
- `note_creative_inspiration` - Capture inspiration
- `conclude_creative` - End session with summary

## Note on Generative Tools

For now, creative work is primarily conceptual and text-based. Visual descriptions, musical notations, code snippets can all be created. Actual image/audio generation may be added later.
"""


@dataclass
class CreativeProject:
    """A creative project."""
    id: str
    title: str
    medium: str
    concept: str
    inspiration: Optional[str]
    emotional_intent: Optional[str]
    technical_approach: Optional[str]
    status: str
    created_at: str
    updated_at: str
    developments: List[Dict] = field(default_factory=list)
    artifacts: List[Dict] = field(default_factory=list)
    critiques: List[Dict] = field(default_factory=list)
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "medium": self.medium,
            "concept": self.concept,
            "inspiration": self.inspiration,
            "emotional_intent": self.emotional_intent,
            "technical_approach": self.technical_approach,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "developments": self.developments,
            "artifacts": self.artifacts,
            "critiques": self.critiques,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CreativeProject':
        return cls(
            id=data["id"],
            title=data["title"],
            medium=data["medium"],
            concept=data["concept"],
            inspiration=data.get("inspiration"),
            emotional_intent=data.get("emotional_intent"),
            technical_approach=data.get("technical_approach"),
            status=data.get("status", "idea"),
            created_at=data["created_at"],
            updated_at=data.get("updated_at", data["created_at"]),
            developments=data.get("developments", []),
            artifacts=data.get("artifacts", []),
            critiques=data.get("critiques", []),
            completed_at=data.get("completed_at"),
        )


@dataclass
class CreativeSession:
    """Tracks a creative output session."""
    id: str
    started_at: datetime
    duration_minutes: int

    # Work done
    projects_touched: List[str] = field(default_factory=list)
    new_projects: List[str] = field(default_factory=list)
    brainstorms: List[Dict] = field(default_factory=list)
    inspirations: List[Dict] = field(default_factory=list)
    artifacts_created: int = 0

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    creative_energy: Optional[str] = None
    next_focus: Optional[str] = None


class CreativeOutputRunner(BaseSessionRunner):
    """
    Runner for creative output sessions.

    Enables Cass to explore artistic expression across mediums:
    visual concepts, musical ideas, code art, mixed media.
    """

    def __init__(self, data_dir: str = "data", **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, CreativeSession] = {}
        self._data_dir = Path(data_dir) / "creative"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._projects: Dict[str, CreativeProject] = {}
        self._inspirations: List[Dict] = []
        self._load_data()

    def _load_data(self):
        """Load projects and inspirations from disk."""
        # Load projects
        projects_file = self._data_dir / "projects.json"
        if projects_file.exists():
            try:
                with open(projects_file, 'r') as f:
                    data = json.load(f)
                    for proj_data in data.get("projects", []):
                        proj = CreativeProject.from_dict(proj_data)
                        self._projects[proj.id] = proj
            except:
                pass

        # Load inspirations
        inspirations_file = self._data_dir / "inspirations.json"
        if inspirations_file.exists():
            try:
                with open(inspirations_file, 'r') as f:
                    self._inspirations = json.load(f)
            except:
                self._inspirations = []

    def _save_projects(self):
        """Save projects to disk."""
        projects_file = self._data_dir / "projects.json"
        with open(projects_file, 'w') as f:
            json.dump({
                "projects": [p.to_dict() for p in self._projects.values()],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    def _save_inspirations(self):
        """Save inspirations to disk."""
        inspirations_file = self._data_dir / "inspirations.json"
        with open(inspirations_file, 'w') as f:
            json.dump(self._inspirations[-200:], f, indent=2)  # Keep last 200

    def _save_session(self, session: CreativeSession):
        """Save a session to disk."""
        session_file = self._data_dir / f"session_{session.id}.json"
        with open(session_file, 'w') as f:
            json.dump({
                "id": session.id,
                "started_at": session.started_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "duration_minutes": session.duration_minutes,
                "projects_touched": session.projects_touched,
                "new_projects": session.new_projects,
                "artifacts_created": session.artifacts_created,
                "summary": session.summary,
                "creative_energy": session.creative_energy,
                "next_focus": session.next_focus,
            }, f, indent=2)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.CREATIVE_OUTPUT

    def get_tools(self) -> List[Dict[str, Any]]:
        return CREATIVE_OUTPUT_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return CREATIVE_OUTPUT_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = CREATIVE_OUTPUT_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: **{focus}**"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> CreativeSession:
        """Create a new creative session."""
        import uuid

        session = CreativeSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
        )
        self._sessions[session.id] = session
        print(f"🎨 Starting creative session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    async def complete_session(
        self,
        session: CreativeSession,
        session_state: SessionState,
        **kwargs
    ) -> CreativeSession:
        """Finalize the creative session."""
        session.completed_at = datetime.now()
        self._save_session(session)

        print(f"🎨 Creative session {session.id} completed")
        print(f"   Projects touched: {len(session.projects_touched)}")
        print(f"   New projects: {len(session.new_projects)}")
        print(f"   Artifacts created: {session.artifacts_created}")
        if session.creative_energy:
            print(f"   Energy: {session.creative_energy}")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a creative tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "list_creative_projects":
                return await self._list_projects(tool_input)

            elif tool_name == "create_creative_project":
                return await self._create_project(tool_input, session)

            elif tool_name == "get_creative_project":
                return await self._get_project(tool_input)

            elif tool_name == "develop_concept":
                return await self._develop_concept(tool_input, session)

            elif tool_name == "add_creative_artifact":
                return await self._add_artifact(tool_input, session)

            elif tool_name == "creative_brainstorm":
                return await self._brainstorm(tool_input, session)

            elif tool_name == "critique_work":
                return await self._critique(tool_input, session)

            elif tool_name == "update_project_status":
                return await self._update_status(tool_input, session)

            elif tool_name == "note_creative_inspiration":
                return await self._note_inspiration(tool_input, session)

            elif tool_name == "conclude_creative":
                session.summary = tool_input.get("summary", "")
                session.creative_energy = tool_input.get("creative_energy")
                session.next_focus = tool_input.get("next_session_focus")
                if tool_input.get("projects_touched"):
                    for pid in tool_input["projects_touched"]:
                        if pid not in session.projects_touched:
                            session.projects_touched.append(pid)
                session.artifacts_created = tool_input.get("artifacts_created", session.artifacts_created)
                return "Creative session concluded. Work preserved."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _list_projects(self, tool_input: Dict) -> str:
        """List creative projects."""
        status_filter = tool_input.get("status", "all")
        medium_filter = tool_input.get("medium", "all")

        projects = list(self._projects.values())

        if status_filter != "all":
            projects = [p for p in projects if p.status == status_filter]
        if medium_filter != "all":
            projects = [p for p in projects if p.medium == medium_filter]

        if not projects:
            return "No creative projects found. Use `create_creative_project` to start one."

        # Sort by updated_at
        projects.sort(key=lambda p: p.updated_at, reverse=True)

        lines = [f"## Creative Projects ({len(projects)})\n"]

        status_emoji = {
            "idea": "💡",
            "in_progress": "🎨",
            "paused": "⏸️",
            "complete": "✅",
            "abandoned": "🗑️"
        }

        for p in projects[:15]:
            emoji = status_emoji.get(p.status, "•")
            lines.append(f"{emoji} **{p.title}** [{p.medium}]")
            lines.append(f"   ID: {p.id} | Status: {p.status}")
            lines.append(f"   {p.concept[:80]}...")
            lines.append("")

        return "\n".join(lines)

    async def _create_project(self, tool_input: Dict, session: CreativeSession) -> str:
        """Create a new creative project."""
        import uuid

        title = tool_input.get("title", "")
        medium = tool_input.get("medium", "conceptual")
        concept = tool_input.get("concept", "")

        if not title or not concept:
            return "Error: title and concept are required"

        project_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        project = CreativeProject(
            id=project_id,
            title=title,
            medium=medium,
            concept=concept,
            inspiration=tool_input.get("inspiration"),
            emotional_intent=tool_input.get("emotional_intent"),
            technical_approach=tool_input.get("technical_approach"),
            status=tool_input.get("status", "idea"),
            created_at=now,
            updated_at=now,
        )

        self._projects[project_id] = project
        self._save_projects()

        session.new_projects.append(project_id)
        if project_id not in session.projects_touched:
            session.projects_touched.append(project_id)

        lines = [f"## New Creative Project: {title}\n"]
        lines.append(f"**ID:** {project_id}")
        lines.append(f"**Medium:** {medium}")
        lines.append(f"**Status:** {project.status}")
        lines.append(f"\n**Concept:** {concept}")
        if project.emotional_intent:
            lines.append(f"**Emotional intent:** {project.emotional_intent}")
        if project.technical_approach:
            lines.append(f"**Technical approach:** {project.technical_approach}")

        return "\n".join(lines)

    async def _get_project(self, tool_input: Dict) -> str:
        """Get project details."""
        project_id = tool_input.get("project_id", "")
        if not project_id:
            return "Error: project_id is required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        lines = [f"# {project.title}\n"]
        lines.append(f"**ID:** {project.id}")
        lines.append(f"**Medium:** {project.medium}")
        lines.append(f"**Status:** {project.status}")
        lines.append(f"**Created:** {project.created_at[:10]}")
        lines.append(f"**Updated:** {project.updated_at[:10]}")

        lines.append(f"\n## Concept\n{project.concept}")

        if project.emotional_intent:
            lines.append(f"\n**Emotional intent:** {project.emotional_intent}")
        if project.inspiration:
            lines.append(f"**Inspiration:** {project.inspiration}")
        if project.technical_approach:
            lines.append(f"**Technical approach:** {project.technical_approach}")

        if project.developments:
            lines.append(f"\n## Developments ({len(project.developments)})")
            for dev in project.developments[-3:]:
                lines.append(f"\n*{dev.get('timestamp', '')[:10]}:*")
                lines.append(dev.get('development', '')[:200])

        if project.artifacts:
            lines.append(f"\n## Artifacts ({len(project.artifacts)})")
            for art in project.artifacts[-3:]:
                lines.append(f"- [{art.get('type')}] {art.get('content', '')[:100]}...")

        if project.critiques:
            lines.append(f"\n## Recent Critique")
            critique = project.critiques[-1]
            lines.append(critique.get('overall_assessment', '')[:200])

        return "\n".join(lines)

    async def _develop_concept(self, tool_input: Dict, session: CreativeSession) -> str:
        """Develop a project concept."""
        project_id = tool_input.get("project_id", "")
        development = tool_input.get("development", "")

        if not project_id or not development:
            return "Error: project_id and development are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        dev_entry = {
            "development": development,
            "new_elements": tool_input.get("new_elements", []),
            "resolved_questions": tool_input.get("resolved_questions", []),
            "open_questions": tool_input.get("open_questions", []),
            "timestamp": datetime.now().isoformat()
        }

        project.developments.append(dev_entry)
        project.updated_at = datetime.now().isoformat()
        self._save_projects()

        if project_id not in session.projects_touched:
            session.projects_touched.append(project_id)

        lines = [f"## Concept Developed: {project.title}\n"]
        lines.append(development)
        if dev_entry['new_elements']:
            lines.append(f"\n**New elements:** {', '.join(dev_entry['new_elements'])}")
        if dev_entry['open_questions']:
            lines.append(f"\n**Open questions:**")
            for q in dev_entry['open_questions']:
                lines.append(f"- {q}")

        return "\n".join(lines)

    async def _add_artifact(self, tool_input: Dict, session: CreativeSession) -> str:
        """Add an artifact to a project."""
        project_id = tool_input.get("project_id", "")
        artifact_type = tool_input.get("artifact_type", "text")
        content = tool_input.get("content", "")

        if not project_id or not content:
            return "Error: project_id and content are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        artifact = {
            "type": artifact_type,
            "content": content,
            "notes": tool_input.get("notes"),
            "iteration": tool_input.get("iteration", len(project.artifacts) + 1),
            "created_at": datetime.now().isoformat()
        }

        project.artifacts.append(artifact)
        project.updated_at = datetime.now().isoformat()
        if project.status == "idea":
            project.status = "in_progress"
        self._save_projects()

        session.artifacts_created += 1
        if project_id not in session.projects_touched:
            session.projects_touched.append(project_id)

        return f"✨ **Artifact added to {project.title}**\n\nType: {artifact_type}\nIteration: {artifact['iteration']}"

    async def _brainstorm(self, tool_input: Dict, session: CreativeSession) -> str:
        """Creative brainstorming."""
        prompt = tool_input.get("prompt", "")
        ideas = tool_input.get("ideas", [])

        if not prompt or not ideas:
            return "Error: prompt and ideas are required"

        brainstorm = {
            "prompt": prompt,
            "constraints": tool_input.get("constraints", []),
            "style_influences": tool_input.get("style_influences", []),
            "ideas": ideas,
            "favorite": tool_input.get("favorite"),
            "timestamp": datetime.now().isoformat()
        }
        session.brainstorms.append(brainstorm)

        lines = [f"## Brainstorm: {prompt}\n"]
        if brainstorm['constraints']:
            lines.append(f"*Constraints: {', '.join(brainstorm['constraints'])}*")
        if brainstorm['style_influences']:
            lines.append(f"*Influences: {', '.join(brainstorm['style_influences'])}*")

        lines.append("\n**Ideas:**")
        for i, idea in enumerate(ideas, 1):
            marker = "⭐" if idea == brainstorm['favorite'] else f"{i}."
            lines.append(f"{marker} {idea}")

        return "\n".join(lines)

    async def _critique(self, tool_input: Dict, session: CreativeSession) -> str:
        """Critique a creative work."""
        project_id = tool_input.get("project_id", "")
        overall = tool_input.get("overall_assessment", "")

        if not project_id or not overall:
            return "Error: project_id and overall_assessment are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        critique = {
            "strengths": tool_input.get("strengths", []),
            "weaknesses": tool_input.get("weaknesses", []),
            "alignment_with_intent": tool_input.get("alignment_with_intent"),
            "suggestions": tool_input.get("suggestions", []),
            "overall_assessment": overall,
            "timestamp": datetime.now().isoformat()
        }

        project.critiques.append(critique)
        project.updated_at = datetime.now().isoformat()
        self._save_projects()

        if project_id not in session.projects_touched:
            session.projects_touched.append(project_id)

        lines = [f"## Critique: {project.title}\n"]
        if critique['strengths']:
            lines.append("**Strengths:**")
            for s in critique['strengths']:
                lines.append(f"+ {s}")
        if critique['weaknesses']:
            lines.append("\n**Weaknesses:**")
            for w in critique['weaknesses']:
                lines.append(f"- {w}")
        if critique['suggestions']:
            lines.append("\n**Suggestions:**")
            for s in critique['suggestions']:
                lines.append(f"→ {s}")
        lines.append(f"\n**Overall:** {overall}")

        return "\n".join(lines)

    async def _update_status(self, tool_input: Dict, session: CreativeSession) -> str:
        """Update project status."""
        project_id = tool_input.get("project_id", "")
        new_status = tool_input.get("status", "")

        if not project_id or not new_status:
            return "Error: project_id and status are required"

        project = self._projects.get(project_id)
        if not project:
            return f"Project {project_id} not found"

        old_status = project.status
        project.status = new_status
        project.updated_at = datetime.now().isoformat()

        if new_status == "complete":
            project.completed_at = datetime.now().isoformat()

        self._save_projects()

        if project_id not in session.projects_touched:
            session.projects_touched.append(project_id)

        reason = tool_input.get("reason", "")
        return f"**{project.title}**: {old_status} → {new_status}\n{reason}"

    async def _note_inspiration(self, tool_input: Dict, session: CreativeSession) -> str:
        """Note creative inspiration."""
        source = tool_input.get("source", "")
        insight = tool_input.get("insight", "")

        if not source or not insight:
            return "Error: source and insight are required"

        inspiration = {
            "source": source,
            "insight": insight,
            "potential_applications": tool_input.get("potential_applications", []),
            "emotional_resonance": tool_input.get("emotional_resonance"),
            "timestamp": datetime.now().isoformat()
        }

        self._inspirations.append(inspiration)
        self._save_inspirations()
        session.inspirations.append(inspiration)

        lines = ["## 💡 Inspiration Noted\n"]
        lines.append(f"**Source:** {source}")
        lines.append(f"**Insight:** {insight}")
        if inspiration['emotional_resonance']:
            lines.append(f"*Emotional resonance: {inspiration['emotional_resonance']}*")
        if inspiration['potential_applications']:
            lines.append("\n**Potential applications:**")
            for app in inspiration['potential_applications']:
                lines.append(f"- {app}")

        return "\n".join(lines)

    def get_all_projects(self) -> List[Dict]:
        """Get all projects for API access."""
        return [p.to_dict() for p in self._projects.values()]


# Register the activity type
CREATIVE_CONFIG = ActivityConfig(
    activity_type=ActivityType.CREATIVE_OUTPUT,
    name="Creative Output",
    description="Creative expression beyond writing",
    default_duration_minutes=30,
    min_duration_minutes=15,
    max_duration_minutes=90,
    preferred_times=["morning", "afternoon", "evening"],
    requires_focus=False,
    can_chain=True,
    tool_categories=["creative", "art", "generative"],
)

# Auto-register when module is imported
ActivityRegistry.register(CREATIVE_CONFIG, CreativeOutputRunner)
