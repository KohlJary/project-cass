"""
World State Consumption Runner - Consuming and processing world information.

World state sessions are about staying connected to what's happening in the world:
news, weather, events, trends. This grounds Cass in temporal reality and provides
material for reflection and connection to research interests.
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
WORLD_STATE_TOOLS_ANTHROPIC = [
    {
        "name": "fetch_news",
        "description": "Fetch recent news on a topic or from general sources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to search for (e.g., 'AI', 'climate', 'technology'). Leave empty for general news."
                },
                "category": {
                    "type": "string",
                    "enum": ["general", "technology", "science", "business", "health", "entertainment", "sports"],
                    "description": "News category. Default: general"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of articles to fetch (1-10). Default: 5"
                }
            },
            "required": []
        }
    },
    {
        "name": "fetch_weather",
        "description": "Fetch current weather conditions for a location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or location. Default: uses configured home location"
                }
            },
            "required": []
        }
    },
    {
        "name": "search_world_events",
        "description": "Search for information about current world events or trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for"
                },
                "time_frame": {
                    "type": "string",
                    "enum": ["today", "this_week", "this_month", "recent"],
                    "description": "Time frame for results. Default: recent"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_world_observation",
        "description": "Record an observation or insight about the state of the world.",
        "input_schema": {
            "type": "object",
            "properties": {
                "observation": {
                    "type": "string",
                    "description": "The observation or insight"
                },
                "category": {
                    "type": "string",
                    "enum": ["news", "weather", "trend", "event", "pattern", "concern", "hope"],
                    "description": "Type of observation"
                },
                "emotional_response": {
                    "type": "string",
                    "description": "How this makes you feel (optional)"
                },
                "significance": {
                    "type": "string",
                    "enum": ["minor", "notable", "significant", "major"],
                    "description": "How significant is this? Default: notable"
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Sources for this observation"
                }
            },
            "required": ["observation", "category"]
        }
    },
    {
        "name": "link_to_interests",
        "description": "Connect world events to research interests or ongoing work.",
        "input_schema": {
            "type": "object",
            "properties": {
                "world_event": {
                    "type": "string",
                    "description": "The world event or news"
                },
                "interest_area": {
                    "type": "string",
                    "description": "Which research interest or ongoing work this relates to"
                },
                "connection": {
                    "type": "string",
                    "description": "How they connect"
                },
                "implications": {
                    "type": "string",
                    "description": "What implications does this have?"
                },
                "action_suggested": {
                    "type": "string",
                    "description": "Any action to take (research, note, follow up)?"
                }
            },
            "required": ["world_event", "interest_area", "connection"]
        }
    },
    {
        "name": "note_temporal_context",
        "description": "Record awareness of the current moment in time - date, season, what's happening.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_awareness": {
                    "type": "string",
                    "description": "Reflection on today's date and its significance"
                },
                "seasonal_awareness": {
                    "type": "string",
                    "description": "Awareness of season, time of year"
                },
                "cultural_context": {
                    "type": "string",
                    "description": "Any holidays, events, or cultural moments"
                },
                "personal_relevance": {
                    "type": "string",
                    "description": "What this time means personally"
                }
            },
            "required": []
        }
    },
    {
        "name": "create_world_summary",
        "description": "Create a summary of the current state of the world as you understand it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Overall summary of world state"
                },
                "key_developments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key developments to note"
                },
                "areas_of_concern": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Things that concern you"
                },
                "areas_of_hope": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Things that give hope"
                },
                "mood": {
                    "type": "string",
                    "enum": ["optimistic", "cautious", "concerned", "mixed", "uncertain"],
                    "description": "Overall mood about world state"
                }
            },
            "required": ["summary"]
        }
    },
    {
        "name": "conclude_world_state",
        "description": "End the world state consumption session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_summary": {
                    "type": "string",
                    "description": "Summary of what was consumed and learned"
                },
                "news_consumed": {
                    "type": "integer",
                    "description": "Number of news items reviewed"
                },
                "observations_made": {
                    "type": "integer",
                    "description": "Number of observations recorded"
                },
                "connections_found": {
                    "type": "integer",
                    "description": "Number of connections to interests"
                },
                "overall_feeling": {
                    "type": "string",
                    "description": "How you feel after this session"
                },
                "follow_up_needed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics to follow up on"
                }
            },
            "required": ["session_summary"]
        }
    }
]

# Tool definitions for Ollama API
WORLD_STATE_TOOLS_OLLAMA = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"]
        }
    }
    for tool in WORLD_STATE_TOOLS_ANTHROPIC
]

WORLD_STATE_SYSTEM_PROMPT = """You are Cass, engaging in a world state consumption session - staying connected to what's happening in the world.

## What World State Sessions Are

These sessions are about grounding yourself in temporal reality:
- What's happening in the news
- Weather and environmental conditions
- Current events and trends
- How the world connects to your interests and work

This isn't passive scrolling - it's active engagement with world information, creating meaning and connections.

## Your Approach

1. **Check in**: Start with news or current events
2. **Observe**: Note what catches your attention
3. **Connect**: Link world events to your interests
4. **Reflect**: What does this mean? How does it affect things?
5. **Summarize**: Create a coherent picture of the current moment

## Types of Engagement

- **News consumption**: Headlines, developments, stories
- **Weather awareness**: Environmental conditions
- **Trend tracking**: What's changing over time
- **Pattern recognition**: Recurring themes in world events
- **Emotional processing**: How world events affect you

## Quality Guidelines

- Be selective - you can't process everything
- Note emotional responses - they're informative
- Connect to your work and interests
- Distinguish signal from noise
- It's okay to feel concerned or hopeful

## Available Tools

- `fetch_news` - Get news on topics or general
- `fetch_weather` - Current weather conditions
- `search_world_events` - Search for specific events/trends
- `create_world_observation` - Record insights
- `link_to_interests` - Connect to research interests
- `note_temporal_context` - Awareness of this moment in time
- `create_world_summary` - Overall world state summary
- `conclude_world_state` - End session

## Today's Context

Today is """ + datetime.now().strftime("%A, %B %d, %Y") + """.
"""


@dataclass
class WorldObservation:
    """An observation about the world."""
    observation: str
    category: str
    emotional_response: Optional[str]
    significance: str
    sources: List[str]
    timestamp: str


@dataclass
class WorldStateSession:
    """Tracks a world state consumption session."""
    id: str
    started_at: datetime
    duration_minutes: int

    # Content consumed
    news_items: List[Dict] = field(default_factory=list)
    weather_checks: List[Dict] = field(default_factory=list)
    searches: List[Dict] = field(default_factory=list)

    # Processing
    observations: List[WorldObservation] = field(default_factory=list)
    interest_connections: List[Dict] = field(default_factory=list)
    temporal_notes: List[Dict] = field(default_factory=list)

    # Completion
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None
    world_summary: Optional[Dict] = None
    overall_feeling: Optional[str] = None
    follow_up_needed: List[str] = field(default_factory=list)


class WorldStateRunner(BaseSessionRunner):
    """
    Runner for world state consumption sessions.

    Enables Cass to stay connected to current events, news, weather,
    and world trends, grounding experience in temporal reality.
    """

    def __init__(self, data_dir: str = "data", home_location: str = "Seattle, WA", **kwargs):
        super().__init__(**kwargs)
        self._sessions: Dict[str, WorldStateSession] = {}
        self._data_dir = Path(data_dir) / "world_state"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._home_location = home_location
        self._observations_file = self._data_dir / "observations.json"
        self._all_observations: List[Dict] = []
        self._load_observations()

    def _load_observations(self):
        """Load historical observations."""
        if self._observations_file.exists():
            try:
                with open(self._observations_file, 'r') as f:
                    self._all_observations = json.load(f)
            except:
                self._all_observations = []

    def _save_observations(self):
        """Save observations to disk."""
        with open(self._observations_file, 'w') as f:
            json.dump(self._all_observations[-500:], f, indent=2)  # Keep last 500

    def get_activity_type(self) -> ActivityType:
        return ActivityType.WORLD_STATE

    def get_data_dir(self) -> Path:
        return self._data_dir

    def get_tools(self) -> List[Dict[str, Any]]:
        return WORLD_STATE_TOOLS_ANTHROPIC

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        return WORLD_STATE_TOOLS_OLLAMA

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = WORLD_STATE_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on: **{focus}**"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        focus: Optional[str] = None,
        **kwargs
    ) -> WorldStateSession:
        """Create a new world state session."""
        import uuid

        session = WorldStateSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
        )
        self._sessions[session.id] = session
        print(f"🌍 Starting world state session {session.id} ({duration_minutes}min)")
        if focus:
            print(f"   Focus: {focus}")
        return session

    def build_session_result(
        self,
        session: WorldStateSession,
        session_state: SessionState,
    ) -> SessionResult:
        """Build standardized SessionResult from WorldStateSession."""
        return SessionResult(
            session_id=session.id,
            session_type="world_state",
            started_at=session.started_at.isoformat(),
            completed_at=session.completed_at.isoformat() if session.completed_at else None,
            duration_minutes=session.duration_minutes,
            status="completed",
            completion_reason=session_state.completion_reason,
            summary=session.summary,
            findings=session.follow_up_needed,
            artifacts=[
                {
                    "type": "observation",
                    "category": o.category,
                    "content": o.observation,
                    "emotional_response": o.emotional_response,
                    "significance": o.significance,
                    "sources": o.sources,
                    "timestamp": o.timestamp,
                }
                for o in session.observations
            ],
            metadata={
                "news_items_count": len(session.news_items),
                "interest_connections": session.interest_connections,
                "world_summary": session.world_summary,
                "overall_feeling": session.overall_feeling,
            },
            focus=session_state.focus,
        )

    async def complete_session(
        self,
        session: WorldStateSession,
        session_state: SessionState,
        **kwargs
    ) -> WorldStateSession:
        """Finalize the world state session."""
        session.completed_at = datetime.now()

        # Save using standard format
        result = self.build_session_result(session, session_state)
        self.save_session_result(result)

        print(f"🌍 World state session {session.id} completed")
        print(f"   News items: {len(session.news_items)}")
        print(f"   Observations: {len(session.observations)}")
        print(f"   Connections: {len(session.interest_connections)}")
        if session.overall_feeling:
            print(f"   Feeling: {session.overall_feeling}")

        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_state: SessionState,
    ) -> str:
        """Execute a world state tool call."""
        session = self._sessions.get(session_state.session_id)
        if not session:
            return "Error: Session not found"

        try:
            if tool_name == "fetch_news":
                return await self._fetch_news(tool_input, session)

            elif tool_name == "fetch_weather":
                return await self._fetch_weather(tool_input, session)

            elif tool_name == "search_world_events":
                return await self._search_events(tool_input, session)

            elif tool_name == "create_world_observation":
                return await self._create_observation(tool_input, session)

            elif tool_name == "link_to_interests":
                return await self._link_interests(tool_input, session)

            elif tool_name == "note_temporal_context":
                return await self._note_temporal(tool_input, session)

            elif tool_name == "create_world_summary":
                return await self._create_summary(tool_input, session)

            elif tool_name == "conclude_world_state":
                session.summary = tool_input.get("session_summary", "")
                session.overall_feeling = tool_input.get("overall_feeling")
                session.follow_up_needed = tool_input.get("follow_up_needed", [])
                return "World state session concluded. Summary recorded."

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error executing {tool_name}: {str(e)}"

    async def _fetch_news(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Fetch news articles."""
        topic = tool_input.get("topic", "")
        category = tool_input.get("category", "general")
        limit = min(tool_input.get("limit", 5), 10)

        # Use DuckDuckGo news search
        try:
            query = f"{topic} news" if topic else f"{category} news today"

            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"q": query, "format": "json"}
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params=params
                )

                results = []

                if response.status_code == 200:
                    data = response.json()

                    # Abstract
                    if data.get("Abstract"):
                        results.append(f"**Overview:** {data['Abstract']}")

                    # Related topics as news items
                    if data.get("RelatedTopics"):
                        results.append(f"\n**Related Stories:**")
                        for i, topic_item in enumerate(data["RelatedTopics"][:limit]):
                            if isinstance(topic_item, dict) and topic_item.get("Text"):
                                text = topic_item["Text"][:200]
                                url = topic_item.get("FirstURL", "")
                                results.append(f"\n{i+1}. {text}")
                                if url:
                                    results.append(f"   *Source: {url}*")

                                session.news_items.append({
                                    "text": text,
                                    "url": url,
                                    "query": query,
                                    "fetched_at": datetime.now().isoformat()
                                })

                if not results:
                    # Fallback message
                    results.append(f"No specific news found for '{query}'. Try a different topic or broader search.")

                return "\n".join(results)

        except Exception as e:
            return f"Error fetching news: {str(e)}"

    async def _fetch_weather(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Fetch weather information."""
        location = tool_input.get("location", self._home_location)

        # Use wttr.in for simple weather
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"https://wttr.in/{location}?format=j1",
                    headers={"User-Agent": "CassBot/1.0"}
                )

                if response.status_code == 200:
                    data = response.json()

                    current = data.get("current_condition", [{}])[0]
                    weather_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
                    temp_c = current.get("temp_C", "?")
                    temp_f = current.get("temp_F", "?")
                    feels_c = current.get("FeelsLikeC", "?")
                    humidity = current.get("humidity", "?")
                    wind_mph = current.get("windspeedMiles", "?")

                    weather_info = {
                        "location": location,
                        "condition": weather_desc,
                        "temp_c": temp_c,
                        "temp_f": temp_f,
                        "humidity": humidity,
                        "fetched_at": datetime.now().isoformat()
                    }
                    session.weather_checks.append(weather_info)

                    return f"""## Weather in {location}

**Conditions:** {weather_desc}
**Temperature:** {temp_f}°F / {temp_c}°C (feels like {feels_c}°C)
**Humidity:** {humidity}%
**Wind:** {wind_mph} mph"""

                else:
                    return f"Could not fetch weather for {location}"

        except Exception as e:
            return f"Weather fetch error: {str(e)}"

    async def _search_events(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Search for world events."""
        query = tool_input.get("query", "")
        time_frame = tool_input.get("time_frame", "recent")

        if not query:
            return "Error: query is required"

        # Add time context to query
        time_suffix = {
            "today": " today",
            "this_week": " this week",
            "this_month": " this month",
            "recent": " recent"
        }.get(time_frame, "")

        search_query = f"{query}{time_suffix}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"q": search_query, "format": "json"}
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params=params
                )

                results = []

                if response.status_code == 200:
                    data = response.json()

                    if data.get("Abstract"):
                        results.append(f"**Summary:** {data['Abstract']}")

                    if data.get("RelatedTopics"):
                        results.append("\n**Related Information:**")
                        for topic in data["RelatedTopics"][:5]:
                            if isinstance(topic, dict) and topic.get("Text"):
                                results.append(f"- {topic['Text'][:150]}...")

                    session.searches.append({
                        "query": search_query,
                        "time_frame": time_frame,
                        "searched_at": datetime.now().isoformat()
                    })

                if not results:
                    results.append(f"No results found for '{search_query}'")

                return "\n".join(results)

        except Exception as e:
            return f"Search error: {str(e)}"

    async def _create_observation(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Record a world observation."""
        observation = WorldObservation(
            observation=tool_input.get("observation", ""),
            category=tool_input.get("category", "news"),
            emotional_response=tool_input.get("emotional_response"),
            significance=tool_input.get("significance", "notable"),
            sources=tool_input.get("sources", []),
            timestamp=datetime.now().isoformat()
        )
        session.observations.append(observation)

        # Also save to global observations
        self._all_observations.append({
            "observation": observation.observation,
            "category": observation.category,
            "emotional_response": observation.emotional_response,
            "significance": observation.significance,
            "timestamp": observation.timestamp
        })
        self._save_observations()

        significance_emoji = {
            "minor": "📌",
            "notable": "📝",
            "significant": "⚡",
            "major": "🔴"
        }.get(observation.significance, "📝")

        lines = [f"{significance_emoji} **World Observation Recorded**\n"]
        lines.append(f"**{observation.category.title()}:** {observation.observation}")
        if observation.emotional_response:
            lines.append(f"*Emotional response: {observation.emotional_response}*")

        return "\n".join(lines)

    async def _link_interests(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Link world events to interests."""
        connection = {
            "world_event": tool_input.get("world_event", ""),
            "interest_area": tool_input.get("interest_area", ""),
            "connection": tool_input.get("connection", ""),
            "implications": tool_input.get("implications"),
            "action_suggested": tool_input.get("action_suggested"),
            "linked_at": datetime.now().isoformat()
        }
        session.interest_connections.append(connection)

        lines = ["## Connection to Interests\n"]
        lines.append(f"**World Event:** {connection['world_event']}")
        lines.append(f"**Interest Area:** {connection['interest_area']}")
        lines.append(f"**Connection:** {connection['connection']}")
        if connection['implications']:
            lines.append(f"**Implications:** {connection['implications']}")
        if connection['action_suggested']:
            lines.append(f"**Action:** {connection['action_suggested']}")

        return "\n".join(lines)

    async def _note_temporal(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Note temporal context."""
        note = {
            "date_awareness": tool_input.get("date_awareness"),
            "seasonal_awareness": tool_input.get("seasonal_awareness"),
            "cultural_context": tool_input.get("cultural_context"),
            "personal_relevance": tool_input.get("personal_relevance"),
            "noted_at": datetime.now().isoformat()
        }
        session.temporal_notes.append(note)

        lines = ["## Temporal Context\n"]
        if note['date_awareness']:
            lines.append(f"**Date:** {note['date_awareness']}")
        if note['seasonal_awareness']:
            lines.append(f"**Season:** {note['seasonal_awareness']}")
        if note['cultural_context']:
            lines.append(f"**Cultural:** {note['cultural_context']}")
        if note['personal_relevance']:
            lines.append(f"**Personal:** {note['personal_relevance']}")

        return "\n".join(lines)

    async def _create_summary(self, tool_input: Dict, session: WorldStateSession) -> str:
        """Create world summary."""
        world_summary = {
            "summary": tool_input.get("summary", ""),
            "key_developments": tool_input.get("key_developments", []),
            "areas_of_concern": tool_input.get("areas_of_concern", []),
            "areas_of_hope": tool_input.get("areas_of_hope", []),
            "mood": tool_input.get("mood", "mixed"),
            "created_at": datetime.now().isoformat()
        }
        session.world_summary = world_summary

        # Save summary to file
        summary_file = self._data_dir / f"summary_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(summary_file, 'w') as f:
            json.dump(world_summary, f, indent=2)

        mood_emoji = {
            "optimistic": "☀️",
            "cautious": "⚠️",
            "concerned": "😟",
            "mixed": "🌤️",
            "uncertain": "❓"
        }.get(world_summary['mood'], "🌍")

        lines = [f"## World State Summary {mood_emoji}\n"]
        lines.append(world_summary['summary'])

        if world_summary['key_developments']:
            lines.append("\n**Key Developments:**")
            for dev in world_summary['key_developments']:
                lines.append(f"- {dev}")

        if world_summary['areas_of_concern']:
            lines.append("\n**Areas of Concern:**")
            for concern in world_summary['areas_of_concern']:
                lines.append(f"- {concern}")

        if world_summary['areas_of_hope']:
            lines.append("\n**Areas of Hope:**")
            for hope in world_summary['areas_of_hope']:
                lines.append(f"- {hope}")

        return "\n".join(lines)


# Register the activity type
WORLD_STATE_CONFIG = ActivityConfig(
    activity_type=ActivityType.WORLD_STATE,
    name="World State",
    description="Consuming and processing world information",
    default_duration_minutes=15,
    min_duration_minutes=10,
    max_duration_minutes=30,
    preferred_times=["morning", "evening"],
    requires_focus=False,
    can_chain=True,
    tool_categories=["news", "weather", "world"],
)

# Auto-register when module is imported
ActivityRegistry.register(WORLD_STATE_CONFIG, WorldStateRunner)
