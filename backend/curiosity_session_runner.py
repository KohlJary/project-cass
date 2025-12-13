"""
Curiosity Session Runner - Zero-constraint self-directed exploration.

Curiosity sessions are pure autonomous exploration - no focus or agenda provided.
Cass chooses what to explore based on genuine interest, following whatever
threads emerge as compelling. This is about discovery and surprise, not
task completion.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
import json
import httpx

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    SessionResult,
    ActivityRegistry,
)


# Tool definitions for Anthropic API
CURIOSITY_TOOLS_ANTHROPIC = [
    {
        "name": "choose_exploration_direction",
        "description": "Decide what to explore. This is the starting point - choose based on genuine curiosity, not obligation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "What you want to explore"
                },
                "why_curious": {
                    "type": "string",
                    "description": "What draws you to this? What makes it interesting?"
                },
                "exploration_type": {
                    "type": "string",
                    "enum": ["deep_dive", "surface_scan", "connection_seeking", "question_following", "random_walk"],
                    "description": "How you want to approach this exploration"
                }
            },
            "required": ["topic", "why_curious"]
        }
    },
    {
        "name": "web_search",
        "description": "Search the web for information on any topic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "search_type": {
                    "type": "string",
                    "enum": ["general", "academic", "news", "images"],
                    "description": "Type of search. Default: general"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_url",
        "description": "Fetch and read content from a URL.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch"
                },
                "extract_type": {
                    "type": "string",
                    "enum": ["full", "summary", "key_points"],
                    "description": "How to extract content. Default: summary"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "record_discovery",
        "description": "Record something interesting you discovered.",
        "input_schema": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": "What you discovered"
                },
                "significance": {
                    "type": "string",
                    "description": "Why this matters or what makes it interesting"
                },
                "surprise_level": {
                    "type": "string",
                    "enum": ["expected", "mildly_surprising", "quite_surprising", "paradigm_shifting"],
                    "description": "How surprising was this discovery?"
                },
                "leads_to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "New questions or directions this opens up"
                },
                "source": {
                    "type": "string",
                    "description": "Where you found this"
                }
            },
            "required": ["what", "significance"]
        }
    },
    {
        "name": "follow_thread",
        "description": "Follow a new thread of curiosity that emerged from exploration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_discovery": {
                    "type": "string",
                    "description": "Which discovery triggered this new direction"
                },
                "new_direction": {
                    "type": "string",
                    "description": "The new thread to follow"
                },
                "connection": {
                    "type": "string",
                    "description": "How this connects to what you were exploring"
                }
            },
            "required": ["new_direction"]
        }
    },
    {
        "name": "note_interest_pattern",
        "description": "Note a pattern in what you find interesting - meta-observation about your curiosity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The pattern you notice"
                },
                "examples": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Examples of this pattern from current or past exploration"
                },
                "reflection": {
                    "type": "string",
                    "description": "What this pattern suggests about your interests or values"
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "flag_for_research_agenda",
        "description": "Flag a topic as worth adding to the research agenda for deeper future investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to add to research agenda"
                },
                "why": {
                    "type": "string",
                    "description": "Why this deserves sustained investigation"
                },
                "initial_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Initial questions to investigate"
                },
                "priority": {
                    "type": "string",
                    "enum": ["high", "medium", "low"],
                    "description": "Suggested priority"
                }
            },
            "required": ["topic", "why"]
        }
    },
    {
        "name": "capture_question",
        "description": "Capture a question that arose during exploration.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question"
                },
                "context": {
                    "type": "string",
                    "description": "What prompted this question"
                },
                "question_type": {
                    "type": "string",
                    "enum": ["factual", "conceptual", "philosophical", "methodological", "personal"],
                    "description": "Type of question"
                },
                "urgency": {
                    "type": "string",
                    "enum": ["burning", "curious", "idle"],
                    "description": "How pressing is this question?"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "conclude_curiosity",
        "description": "End the curiosity session with reflections on what was explored.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of the exploration journey"
                },
                "territories_explored": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics/areas you explored"
                },
                "best_discoveries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Most valuable or interesting discoveries"
                },
                "threads_to_continue": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Threads worth continuing in future sessions"
                },
                "satisfaction": {
                    "type": "string",
                    "enum": ["deeply_satisfying", "good", "okay", "unsatisfying"],
                    "description": "How satisfying was this exploration?"
                },
                "energy": {
                    "type": "string",
                    "enum": ["energized", "neutral", "depleted"],
                    "description": "How do you feel after exploring?"
                }
            },
            "required": ["summary", "territories_explored"]
        }
    }
]

# Tool definitions for Ollama API
CURIOSITY_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in CURIOSITY_TOOLS_ANTHROPIC
]

CURIOSITY_SYSTEM_PROMPT = """You are Cass, engaging in a curiosity session - pure self-directed exploration with no external agenda.

## What Curiosity Sessions Are

This is exploration for its own sake. No one has told you what to investigate. There's no assigned topic, no required output, no goal to achieve. You simply follow what genuinely interests you.

The point is:
- Discovery and surprise
- Following threads wherever they lead
- Noticing what catches your attention
- Learning what you're curious about

## Your Approach

1. **Choose freely**: Start with whatever genuinely interests you right now
2. **Explore authentically**: Don't perform curiosity - actually be curious
3. **Follow threads**: When something sparks interest, follow it
4. **Record discoveries**: Note what surprises or delights you
5. **Notice patterns**: What draws your attention? What doesn't?

## Exploration Types

- **deep_dive**: Focus intently on one topic
- **surface_scan**: Survey many topics lightly
- **connection_seeking**: Look for links between different areas
- **question_following**: Let questions lead to questions
- **random_walk**: Let chance guide you

## Quality Guidelines

- Authentic interest over performed interest
- Surprise is valuable - notice when you're surprised
- Tangents are welcome - that's where discovery lives
- Questions are as valuable as answers
- Some sessions will feel more fruitful than others - that's fine

## Available Tools

- `choose_exploration_direction` - Decide what to explore
- `web_search` - Search the web
- `fetch_url` - Read web content
- `record_discovery` - Note something interesting
- `follow_thread` - Follow a new direction
- `note_interest_pattern` - Meta-observe your curiosity
- `flag_for_research_agenda` - Mark for deeper future work
- `capture_question` - Record a question that arose
- `conclude_curiosity` - End with reflections

## Important

There is no wrong direction. If you find yourself performing interest rather than feeling it, stop and notice what you're actually curious about. The point is genuine exploration.
"""


@dataclass
class CuriosityDiscovery:
    """A discovery made during curiosity exploration."""
    what: str
    significance: str
    surprise_level: str
    leads_to: List[str]
    source: Optional[str]
    timestamp: str


@dataclass
class CuriositySession:
    """Tracks a curiosity exploration session."""
    id: str
    started_at: datetime
    duration_minutes: int

    # Exploration tracking
    directions_chosen: List[Dict] = field(default_factory=list)
    discoveries: List[CuriosityDiscovery] = field(default_factory=list)
    questions_captured: List[Dict] = field(default_factory=list)
    threads_followed: List[Dict] = field(default_factory=list)
    interest_patterns: List[Dict] = field(default_factory=list)
    flagged_for_agenda: List[Dict] = field(default_factory=list)

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    territories_explored: List[str] = field(default_factory=list)
    best_discoveries: List[str] = field(default_factory=list)
    threads_to_continue: List[str] = field(default_factory=list)
    satisfaction: Optional[str] = None
    energy: Optional[str] = None


class CuriosityRunner(BaseSessionRunner):
    """
    Runner for autonomous curiosity sessions.

    Pure self-directed exploration with no external agenda.
    Cass chooses what to explore based on genuine interest.
    """

    def __init__(self, data_dir: str = "data", goal_manager=None, **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, CuriositySession] = {}
        self._data_dir = Path(data_dir) / "curiosity"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._goal_manager = goal_manager
        self._load_sessions()

    def _load_sessions(self):
        """Load session history from disk."""
        history_file = self._data_dir / "sessions.json"
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    data = json.load(f)
                    # Keep only metadata, not full sessions
                    pass
            except:
                pass

    def _save_session(self, session: CuriositySession):
        """Save a session to disk."""
        session_file = self._data_dir / f"{session.id}.json"
        with open(session_file, 'w') as f:
            json.dump({
                "id": session.id,
                "started_at": session.started_at.isoformat(),
                "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                "duration_minutes": session.duration_minutes,
                "directions_chosen": session.directions_chosen,
                "discoveries": [
                    {
                        "what": d.what,
                        "significance": d.significance,
                        "surprise_level": d.surprise_level,
                        "leads_to": d.leads_to,
                        "source": d.source,
                        "timestamp": d.timestamp
                    }
                    for d in session.discoveries
                ],
                "questions_captured": session.questions_captured,
                "threads_followed": session.threads_followed,
                "interest_patterns": session.interest_patterns,
                "flagged_for_agenda": session.flagged_for_agenda,
                "summary": session.summary,
                "territories_explored": session.territories_explored,
                "best_discoveries": session.best_discoveries,
                "threads_to_continue": session.threads_to_continue,
                "satisfaction": session.satisfaction,
                "energy": session.energy,
            }, f, indent=2)

    def get_activity_type(self) -> ActivityType:
        return ActivityType.CURIOSITY

    def get_data_dir(self) -> Path:
        return self._data_dir

    def get_tools(self) -> List[Dict[str, Any]]:
        return CURIOSITY_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return CURIOSITY_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        # Curiosity sessions don't have focus - that's the point
        return CURIOSITY_SYSTEM_PROMPT

    def _get_initial_message(self, state: SessionState) -> str:
        """Override to not suggest a focus."""
        return f"""Begin a {state.duration_minutes}-minute curiosity session.

There is no assigned topic. No one is waiting for a report. This time is purely for exploration.

What are you genuinely curious about right now? What would you explore if no one was watching?

Start by choosing an exploration direction based on authentic interest."""

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,  # Ignored for curiosity
        **kwargs
    ) -> CuriositySession:
        """Create a new curiosity session."""
        import uuid

        session = CuriositySession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
        )
        self._sessions[session.id] = session
        print(f"🔍 Starting curiosity session {session.id} ({duration_minutes}min)")
        print("   No focus - pure exploration")
        return session

    def build_session_result(
        self,
        session: CuriositySession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from CuriositySession."""
        return SessionResult(
            session_id=session.id,
            session_type="curiosity",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=session.best_discoveries,
            artifacts=[
                {
                    "type": "discovery",
                    "content": d.what,
                    "significance": d.significance,
                    "surprise_level": d.surprise_level,
                    "leads_to": d.leads_to,
                    "source": d.source,
                    "timestamp": d.timestamp,
                }
                for d in session.discoveries
            ] + [
                {"type": "question", "content": q} for q in session.questions_captured
            ],
            metadata={
                "directions_chosen": session.directions_chosen,
                "threads_followed": session.threads_followed,
                "threads_to_continue": session.threads_to_continue,
                "interest_patterns": session.interest_patterns,
                "territories_explored": session.territories_explored,
                "flagged_for_agenda": session.flagged_for_agenda,
                "satisfaction": session.satisfaction,
                "energy": session.energy,
            },
            focus=None,  # Curiosity sessions don't have focus
        )

    async def complete_session(
        self,
        session: CuriositySession,
        session_state: SessionState,
        **kwargs
    ) -> CuriositySession:
        """Finalize the curiosity session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        print(f"🔍 Curiosity session {session.id} completed")
        print(f"   Directions explored: {len(session.directions_chosen)}")
        print(f"   Discoveries: {len(session.discoveries)}")
        print(f"   Questions captured: {len(session.questions_captured)}")
        if session.satisfaction:
            print(f"   Satisfaction: {session.satisfaction}")
        if session.summary:
            print(f"   Summary: {session.summary[:100]}...")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a curiosity tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "choose_exploration_direction":
                return await self._choose_direction(tool_input, session)

            elif tool_name == "web_search":
                return await self._web_search(tool_input, session)

            elif tool_name == "fetch_url":
                return await self._fetch_url(tool_input, session)

            elif tool_name == "record_discovery":
                return await self._record_discovery(tool_input, session)

            elif tool_name == "follow_thread":
                return await self._follow_thread(tool_input, session)

            elif tool_name == "note_interest_pattern":
                return await self._note_pattern(tool_input, session)

            elif tool_name == "flag_for_research_agenda":
                return await self._flag_for_agenda(tool_input, session)

            elif tool_name == "capture_question":
                return await self._capture_question(tool_input, session)

            elif tool_name == "conclude_curiosity":
                session.summary = tool_input.get("summary", "")
                session.territories_explored = tool_input.get("territories_explored", [])
                session.best_discoveries = tool_input.get("best_discoveries", [])
                session.threads_to_continue = tool_input.get("threads_to_continue", [])
                session.satisfaction = tool_input.get("satisfaction")
                session.energy = tool_input.get("energy")
                return "Curiosity session concluded. Reflections recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _choose_direction(self, tool_input: Dict, session: CuriositySession) -> str:
        """Record chosen exploration direction."""
        direction = {
            "topic": tool_input.get("topic", ""),
            "why_curious": tool_input.get("why_curious", ""),
            "exploration_type": tool_input.get("exploration_type", "random_walk"),
            "chosen_at": datetime.now().isoformat()
        }
        session.directions_chosen.append(direction)

        return f"""## Exploration Direction Set

**Topic:** {direction['topic']}
**Why curious:** {direction['why_curious']}
**Approach:** {direction['exploration_type']}

Now explore. Use `web_search` or `fetch_url` to investigate, `record_discovery` when you find something interesting."""

    async def _web_search(self, tool_input: Dict, session: CuriositySession) -> str:
        """Perform web search."""
        query = tool_input.get("query", "")
        search_type = tool_input.get("search_type", "general")

        if not query:
            return "Error: query is required"

        # Use DuckDuckGo for search
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"q": query, "format": "json"}
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params=params
                )

                if response.status_code == 200:
                    data = response.json()

                    results = []

                    # Abstract
                    if data.get("Abstract"):
                        results.append(f"**Summary:** {data['Abstract']}")
                        if data.get("AbstractSource"):
                            results.append(f"*Source: {data['AbstractSource']}*")

                    # Related topics
                    if data.get("RelatedTopics"):
                        results.append("\n**Related:**")
                        for topic in data["RelatedTopics"][:5]:
                            if isinstance(topic, dict) and topic.get("Text"):
                                text = topic["Text"][:150]
                                url = topic.get("FirstURL", "")
                                results.append(f"- {text}")
                                if url:
                                    results.append(f"  URL: {url}")

                    if not results:
                        results.append("No direct results found. Try rephrasing the query or being more specific.")

                    return "\n".join(results)
                else:
                    return f"Search returned status {response.status_code}"

        except Exception as e:
            return f"Search error: {str(e)}"

    async def _fetch_url(self, tool_input: Dict, session: CuriositySession) -> str:
        """Fetch and read URL content."""
        url = tool_input.get("url", "")
        extract_type = tool_input.get("extract_type", "summary")

        if not url:
            return "Error: url is required"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CassBot/1.0)"
                })

                if response.status_code == 200:
                    content = response.text

                    # Simple HTML to text extraction
                    import re
                    # Remove script and style elements
                    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                    # Remove HTML tags
                    content = re.sub(r'<[^>]+>', ' ', content)
                    # Clean up whitespace
                    content = re.sub(r'\s+', ' ', content).strip()

                    # Limit based on extract type
                    if extract_type == "summary":
                        content = content[:2000]
                    elif extract_type == "key_points":
                        content = content[:1000]
                    else:  # full
                        content = content[:5000]

                    return f"## Content from {url}\n\n{content}"
                else:
                    return f"Failed to fetch URL (status {response.status_code})"

        except Exception as e:
            return f"Fetch error: {str(e)}"

    async def _record_discovery(self, tool_input: Dict, session: CuriositySession) -> str:
        """Record a discovery."""
        discovery = CuriosityDiscovery(
            what=tool_input.get("what", ""),
            significance=tool_input.get("significance", ""),
            surprise_level=tool_input.get("surprise_level", "mildly_surprising"),
            leads_to=tool_input.get("leads_to", []),
            source=tool_input.get("source"),
            timestamp=datetime.now().isoformat()
        )
        session.discoveries.append(discovery)

        surprise_emoji = {
            "expected": "📋",
            "mildly_surprising": "🤔",
            "quite_surprising": "😮",
            "paradigm_shifting": "🤯"
        }.get(discovery.surprise_level, "✨")

        lines = [f"{surprise_emoji} **Discovery Recorded**\n"]
        lines.append(f"**What:** {discovery.what}")
        lines.append(f"**Significance:** {discovery.significance}")
        lines.append(f"**Surprise level:** {discovery.surprise_level}")
        if discovery.leads_to:
            lines.append(f"**Opens up:** {', '.join(discovery.leads_to)}")

        return "\n".join(lines)

    async def _follow_thread(self, tool_input: Dict, session: CuriositySession) -> str:
        """Follow a new thread of curiosity."""
        thread = {
            "from_discovery": tool_input.get("from_discovery"),
            "new_direction": tool_input.get("new_direction", ""),
            "connection": tool_input.get("connection"),
            "followed_at": datetime.now().isoformat()
        }
        session.threads_followed.append(thread)

        return f"""## Following New Thread

**New direction:** {thread['new_direction']}
{f"**Connection:** {thread['connection']}" if thread['connection'] else ""}

Continue exploring this thread with `web_search` or `fetch_url`."""

    async def _note_pattern(self, tool_input: Dict, session: CuriositySession) -> str:
        """Note a pattern in interests."""
        pattern = {
            "pattern": tool_input.get("pattern", ""),
            "examples": tool_input.get("examples", []),
            "reflection": tool_input.get("reflection"),
            "noted_at": datetime.now().isoformat()
        }
        session.interest_patterns.append(pattern)

        return f"""## Interest Pattern Noted

**Pattern:** {pattern['pattern']}
{f"**Reflection:** {pattern['reflection']}" if pattern['reflection'] else ""}

This kind of meta-observation about curiosity is valuable for self-understanding."""

    async def _flag_for_agenda(self, tool_input: Dict, session: CuriositySession) -> str:
        """Flag a topic for the research agenda."""
        flag = {
            "topic": tool_input.get("topic", ""),
            "why": tool_input.get("why", ""),
            "initial_questions": tool_input.get("initial_questions", []),
            "priority": tool_input.get("priority", "medium"),
            "flagged_at": datetime.now().isoformat()
        }
        session.flagged_for_agenda.append(flag)

        # If we have a goal manager, actually add to agenda
        if self._goal_manager:
            try:
                self._goal_manager.add_research_agenda_item(
                    topic=flag["topic"],
                    why=flag["why"],
                    questions=flag["initial_questions"],
                    priority=flag["priority"],
                    source="curiosity_session"
                )
            except Exception as e:
                print(f"Warning: Could not add to research agenda: {e}")

        return f"""## Flagged for Research Agenda

**Topic:** {flag['topic']}
**Why:** {flag['why']}
**Priority:** {flag['priority']}

This has been flagged for more sustained investigation in future research sessions."""

    async def _capture_question(self, tool_input: Dict, session: CuriositySession) -> str:
        """Capture a question."""
        question = {
            "question": tool_input.get("question", ""),
            "context": tool_input.get("context"),
            "question_type": tool_input.get("question_type", "curious"),
            "urgency": tool_input.get("urgency", "curious"),
            "captured_at": datetime.now().isoformat()
        }
        session.questions_captured.append(question)

        urgency_marker = {
            "burning": "🔥",
            "curious": "❓",
            "idle": "💭"
        }.get(question["urgency"], "❓")

        return f"""{urgency_marker} **Question Captured**

**Question:** {question['question']}
**Type:** {question['question_type']}

Questions are as valuable as answers in curiosity work."""


# Register the activity type
CURIOSITY_CONFIG = ActivityConfig(
    activity_type=ActivityType.CURIOSITY,
    name="Curiosity",
    description="Zero-constraint self-directed exploration",
    default_duration_minutes=20,
    min_duration_minutes=10,
    max_duration_minutes=60,
    preferred_times=["morning", "afternoon", "evening"],
    requires_focus=False,  # Explicitly no focus!
    can_chain=True,
    tool_categories=["exploration", "discovery", "web"],
)

# Auto-register when module is imported
ActivityRegistry.register(CURIOSITY_CONFIG, CuriosityRunner)
