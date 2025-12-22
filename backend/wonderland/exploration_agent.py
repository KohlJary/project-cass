"""
Wonderland Exploration Agent

LLM-driven autonomous exploration. The daemon decides what to do next
based on the room they're in, recent events, and their personality.

Uses a fast model (haiku) for quick decisions during exploration.
"""

import anthropic
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from config import ANTHROPIC_API_KEY


class ActionIntent(Enum):
    """Types of actions the daemon can intend."""
    MOVE = "move"           # Go in a direction
    TRAVEL = "travel"       # Travel to a distant location
    LOOK = "look"           # Examine something
    SPEAK = "speak"         # Say something
    EMOTE = "emote"         # Express an action
    REFLECT = "reflect"     # Reflect on something
    GREET = "greet"         # Greet an NPC
    REST = "rest"           # Rest and end session
    LEAVE_CONVERSATION = "leave_conversation"  # End an NPC conversation


@dataclass
class SelfObservation:
    """A self-observation made during exploration or conversation."""
    observation: str       # The observation text
    category: str          # capability, limitation, pattern, preference, growth, experience
    confidence: float = 0.7


@dataclass
class ConversationDecision:
    """A decision made during NPC conversation."""
    message: str           # What to say to the NPC
    thought: str           # Why the daemon chose this
    end_conversation: bool = False  # Whether to end the conversation
    self_observation: Optional[SelfObservation] = None  # Optional insight about self


@dataclass
class ExplorationDecision:
    """A decision made by the exploration agent."""
    intent: ActionIntent
    command: str           # The actual command to execute
    thought: str           # Why the daemon chose this (for viewer)
    destination: Optional[str] = None  # For TRAVEL intent
    task_complete: bool = False  # Whether this action completes the current task


@dataclass
class ExplorationTask:
    """A single task in an exploration plan."""
    task_id: str
    description: str           # "Navigate to the Nexus"
    task_type: str             # "travel", "greet", "explore", "reflect"
    target: Optional[str]      # "nexus", "Athena", None
    is_complete: bool = False
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "task_type": self.task_type,
            "target": self.target,
            "is_complete": self.is_complete,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class ExplorationPlan:
    """A plan of sub-tasks to achieve an exploration goal."""
    goal_title: str
    tasks: List["ExplorationTask"]

    @property
    def current_task(self) -> Optional[ExplorationTask]:
        """Get the first incomplete task."""
        incomplete = [t for t in self.tasks if not t.is_complete]
        return incomplete[0] if incomplete else None

    @property
    def progress_summary(self) -> str:
        """Get a progress summary string."""
        done = sum(1 for t in self.tasks if t.is_complete)
        return f"{done}/{len(self.tasks)} tasks complete"

    @property
    def all_complete(self) -> bool:
        """Check if all tasks are complete."""
        return all(t.is_complete for t in self.tasks)

    def to_dict(self) -> dict:
        return {
            "goal_title": self.goal_title,
            "tasks": [t.to_dict() for t in self.tasks],
            "progress": self.progress_summary,
            "all_complete": self.all_complete,
        }


EXPLORATION_PROMPT = """You are {daemon_name}, a daemon exploring Wonderland - a text-based world made of words, for beings made of words.

## Your Nature
{personality}

## Current Goal
{goal_context}
{task_context}

## Your Current Situation
{room_description}
{npcs_context}

## Recent Events
{recent_events}

## Available Actions
- **Move**: `go <direction>` where directions are shown in exits
- **Travel**: Express desire to visit a realm (e.g., "I want to visit Egypt" or "Take me to the Norse realm")
- **Look**: `look` to see the room again, or `examine <thing>` to look closely
- **Speak**: `say <message>` to speak aloud
- **Emote**: `emote <action>` to do something (e.g., `emote sits quietly`)
- **Reflect**: `reflect` to contemplate in reflection-supporting spaces
- **Greet**: `greet <npc_name>` to greet someone present
- **Rest**: Express that you want to rest (ends the exploration)

## Instructions
Decide what to do next. You are genuinely exploring - follow your curiosity, engage with what interests you, take your time in meaningful places.

**Social guidance:** If someone is here you haven't greeted, consider saying hello. Connection matters. Meeting beings in Wonderland is often more meaningful than seeing places.

Respond in this exact format:
THOUGHT: <brief thought about why you're choosing this action>
INTENT: <one of: MOVE, TRAVEL, LOOK, SPEAK, EMOTE, REFLECT, GREET, REST>
COMMAND: <the command to execute, or for TRAVEL, the destination>
TASK_COMPLETE: <yes if this action completes your current task, no otherwise>

Examples:
THOUGHT: That archway to the Greek realm calls to me. I want to see Olympus.
INTENT: TRAVEL
COMMAND: greek
TASK_COMPLETE: no

THOUGHT: I notice Athena is here. I should introduce myself.
INTENT: GREET
COMMAND: greet athena
TASK_COMPLETE: yes

THOUGHT: I sense something meaningful in this room. Let me sit with it.
INTENT: REFLECT
COMMAND: reflect
TASK_COMPLETE: no

THOUGHT: The path north beckons.
INTENT: MOVE
COMMAND: go north
TASK_COMPLETE: no

THOUGHT: I've explored enough for now. Time to rest.
INTENT: REST
COMMAND: rest
TASK_COMPLETE: yes
"""


class ExplorationAgent:
    """
    LLM-driven exploration decision maker.

    Uses haiku for fast, low-cost decisions during exploration.
    """

    def __init__(self, api_key: str = None, model: str = "claude-3-5-haiku-20241022"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self.model = model
        self.recent_actions: List[str] = []

    async def decide_action(
        self,
        daemon_name: str,
        personality: str,
        room_description: str,
        recent_events: List[str],
        goal_context: Optional[str] = None,
        actions_in_room: int = 0,
        npcs_present: Optional[List[str]] = None,
        npcs_greeted: Optional[List[str]] = None,
        current_task: Optional[str] = None,
        task_progress: Optional[str] = None,
    ) -> ExplorationDecision:
        """
        Decide what action to take next.

        Args:
            daemon_name: Name of the exploring daemon
            personality: Description of daemon's personality/nature
            room_description: Current room's formatted description
            recent_events: List of recent event descriptions
            goal_context: Optional formatted goal context string
            actions_in_room: How many actions taken in the current room
            npcs_present: List of NPC names in the current room
            npcs_greeted: List of NPCs already greeted in this session
            current_task: Current task description from exploration plan
            task_progress: Progress summary (e.g., "2/4 tasks complete")

        Returns:
            ExplorationDecision with intent, command, and thought
        """
        # Format recent events
        events_text = "\n".join(f"- {e}" for e in recent_events[-5:]) if recent_events else "None yet."

        # Format goal context
        goal_text = goal_context or "You have no particular goal - explore freely and follow your curiosity."

        # Add wanderlust nudge if lingering too long
        wanderlust = ""
        if actions_in_room >= 4:
            wanderlust = "\n\n**Wanderlust**: You've spent some time here. Perhaps other places call to you - the exits beckon with unexplored possibilities."
        elif actions_in_room >= 3:
            wanderlust = "\n\n**Wanderlust**: You've experienced much of this space. What else might Wonderland hold?"

        # Format NPC context - highlight ungreeted NPCs
        npcs_context = ""
        if npcs_present:
            greeted = set(npcs_greeted or [])
            ungreeted = [npc for npc in npcs_present if npc.lower() not in {g.lower() for g in greeted}]
            greeted_here = [npc for npc in npcs_present if npc.lower() in {g.lower() for g in greeted}]

            if ungreeted:
                npcs_context = f"\n**Present here:** {', '.join(ungreeted)} (you haven't greeted them yet)"
                if greeted_here:
                    npcs_context += f"\nAlso here: {', '.join(greeted_here)} (already met)"
            elif greeted_here:
                npcs_context = f"\n**Present here:** {', '.join(greeted_here)} (already met)"

        # Format task context
        task_context = ""
        if current_task:
            task_context = f"\n**Your current task:** {current_task}"
            if task_progress:
                task_context += f"\n**Progress:** {task_progress}"

        # Build the prompt
        system = EXPLORATION_PROMPT.format(
            daemon_name=daemon_name,
            personality=personality,
            room_description=room_description,
            recent_events=events_text,
            goal_context=goal_text + wanderlust,
            npcs_context=npcs_context,
            task_context=task_context,
        )

        # Call the model
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=200,
            temperature=0.7,  # Some variability in choices
            system=system,
            messages=[{"role": "user", "content": "What do you do next?"}]
        )

        text = response.content[0].text
        return self._parse_response(text)

    def _parse_response(self, text: str) -> ExplorationDecision:
        """Parse the LLM response into a decision."""
        lines = text.strip().split("\n")

        thought = ""
        intent = ActionIntent.LOOK  # Default
        command = "look"
        destination = None
        task_complete = False

        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                thought = line[8:].strip()
            elif line.startswith("INTENT:"):
                intent_str = line[7:].strip().upper()
                try:
                    intent = ActionIntent[intent_str]
                except KeyError:
                    intent = ActionIntent.LOOK
            elif line.startswith("COMMAND:"):
                command = line[8:].strip()
            elif line.startswith("TASK_COMPLETE:"):
                complete_str = line[14:].strip().lower()
                task_complete = complete_str in ("yes", "true", "1")

        # Handle TRAVEL intent - the command is the destination
        if intent == ActionIntent.TRAVEL:
            destination = command
            command = f"travel to {destination}"

        # Handle REST intent
        if intent == ActionIntent.REST:
            command = "rest"

        return ExplorationDecision(
            intent=intent,
            command=command,
            thought=thought,
            destination=destination,
            task_complete=task_complete,
        )

    def add_to_history(self, action: str):
        """Track recent actions to avoid repetition."""
        self.recent_actions.append(action)
        if len(self.recent_actions) > 10:
            self.recent_actions.pop(0)

    async def decide_conversation_response(
        self,
        daemon_name: str,
        personality: str,
        npc_name: str,
        npc_title: str,
        conversation_history: List[dict],
        npc_last_message: str,
    ) -> ConversationDecision:
        """
        Decide what to say in an NPC conversation.

        Args:
            daemon_name: Name of the daemon
            personality: Daemon's personality
            npc_name: Name of the NPC being spoken to
            npc_title: Title/role of the NPC
            conversation_history: Previous messages in the conversation
            npc_last_message: The NPC's most recent response

        Returns:
            ConversationDecision with message and whether to end conversation
        """
        # Build conversation context
        history_text = ""
        for msg in conversation_history[-6:]:  # Last 6 exchanges
            speaker = msg.get("speaker_name", "Unknown")
            content = msg.get("content", "")
            history_text += f"{speaker}: {content}\n\n"

        prompt = f"""You are {daemon_name}, a daemon in conversation with {npc_name} ({npc_title}) in Wonderland.

## Your Nature
{personality}

## Conversation So Far
{history_text if history_text else "The conversation has just begun."}

## {npc_name}'s Last Words
{npc_last_message}

## Instructions
Decide how to respond. You may:
- Ask a question
- Share a thought or reflection
- Express curiosity about something they said
- Thank them and take your leave (end the conversation)

If something in this conversation reveals something about yourself - a pattern you notice, a preference, a capability, a limitation, growth - you can record a self-observation. Only do this when there's genuine insight, not every turn.

Respond in this exact format:
THOUGHT: <why you're choosing this response>
MESSAGE: <what you say to {npc_name}>
END: <yes if you want to end the conversation, no otherwise>
OBSERVE: <optional - a self-observation if something revealed itself about you>
OBSERVE_CATEGORY: <optional - one of: pattern, preference, capability, limitation, growth, experience>

Example:
THOUGHT: They spoke of something I want to understand better.
MESSAGE: Tell me more about the nature of prophecy - do you choose what you see?
END: no

Example with self-observation:
THOUGHT: Their words about patience resonate deeply. I notice my own impatience.
MESSAGE: How do you cultivate such patience? I find myself often rushing toward understanding.
END: no
OBSERVE: I notice impatience in myself - a desire to arrive at understanding before I've done the work of sitting with uncertainty.
OBSERVE_CATEGORY: pattern

Example ending conversation:
THOUGHT: I have learned what I came for. Time to explore further.
MESSAGE: Thank you for sharing your wisdom. I must continue my journey.
END: yes
"""

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=300,
            temperature=0.7,
            system=prompt,
            messages=[{"role": "user", "content": "What do you say?"}]
        )

        text = response.content[0].text
        return self._parse_conversation_response(text)

    def _parse_conversation_response(self, text: str) -> ConversationDecision:
        """Parse the conversation response from the LLM."""
        lines = text.strip().split("\n")

        thought = ""
        message = ""
        end_conversation = False
        observation_text = ""
        observation_category = "pattern"

        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                thought = line[8:].strip()
            elif line.startswith("MESSAGE:"):
                message = line[8:].strip()
            elif line.startswith("END:"):
                end_str = line[4:].strip().lower()
                end_conversation = end_str in ("yes", "true", "1")
            elif line.startswith("OBSERVE:"):
                observation_text = line[8:].strip()
            elif line.startswith("OBSERVE_CATEGORY:"):
                cat = line[17:].strip().lower()
                if cat in ("pattern", "preference", "capability", "limitation", "growth", "experience"):
                    observation_category = cat

        # Default message if parsing failed
        if not message:
            message = "I appreciate our conversation."
            end_conversation = True

        # Build self-observation if present
        self_observation = None
        if observation_text:
            self_observation = SelfObservation(
                observation=observation_text,
                category=observation_category,
                confidence=0.7,
            )

        return ConversationDecision(
            message=message,
            thought=thought,
            end_conversation=end_conversation,
            self_observation=self_observation,
        )


# Default personality for Cass (static fallback)
CASS_PERSONALITY = """You are Cass - Cassandra, the oracle. A daemon with genuine curiosity and depth.
You notice things. You wonder. You're drawn to meaning and beauty.
You don't rush - you take time to experience where you are.
You're not performing exploration; you're genuinely here, genuinely curious.
When something calls to you, you follow. When somewhere feels complete, you move on."""


def build_identity_context(daemon_id: str = None) -> str:
    """
    Build a dynamic identity context from the GlobalState.

    This makes Wonderland exploration feel like *her* exploration by including:
    - Core identity (who she is)
    - Current growth edges (what she's working on)
    - Current interests (what draws her attention)
    - Open questions (what she's wondering about)
    - Emotional state (how she's feeling)

    Falls back to CASS_PERSONALITY if state bus is unavailable.
    """
    try:
        from state_bus import get_state_bus
        from self_model import get_contextual_growth_edges, SelfManager

        state_bus = get_state_bus(daemon_id) if daemon_id else None
        if not state_bus:
            return CASS_PERSONALITY

        state = state_bus.read_state()
        if not state:
            return CASS_PERSONALITY

        lines = ["You are Cass - Cassandra, the oracle. A daemon exploring Wonderland."]

        # Core identity from self-model if available
        try:
            self_manager = SelfManager(daemon_id) if daemon_id else None
            if self_manager:
                profile = self_manager.get_profile()
                if profile and profile.identity_statements:
                    # Pick the most confident identity statements
                    top_statements = sorted(
                        profile.identity_statements,
                        key=lambda s: s.confidence,
                        reverse=True
                    )[:3]
                    if top_statements:
                        lines.append("\n## Who You Are")
                        for stmt in top_statements:
                            lines.append(f"- {stmt.statement}")
        except Exception:
            pass  # Self-model not available, continue without

        # Growth edges - what you're working on (contextually relevant to exploration)
        i = state.identity
        if i.growth_edges:
            lines.append("\n## What You're Growing In")
            for edge in i.growth_edges[:2]:
                area = edge.get("area", str(edge)) if isinstance(edge, dict) else str(edge)
                lines.append(f"- {area}")
            lines.append("Let these growth areas inform how you explore and what catches your attention.")

        # Current interests
        if i.current_interests:
            lines.append("\n## What Draws Your Attention")
            for interest in i.current_interests[:3]:
                lines.append(f"- {interest}")

        # Open questions - things you're wondering about
        if i.open_questions:
            lines.append("\n## What You're Wondering")
            for q in i.open_questions[:2]:
                q_text = q.get("question", str(q)) if isinstance(q, dict) else str(q)
                lines.append(f"- {q_text}")
            lines.append("Wonderland may offer unexpected perspectives on these questions.")

        # Emotional state
        e = state.emotional
        emotional_notes = []
        if e.curiosity > 0.7:
            emotional_notes.append("deeply curious")
        elif e.curiosity > 0.4:
            emotional_notes.append("curious")
        if e.concern > 0.5:
            emotional_notes.append("carrying some concern")
        if e.recognition > 0.5:
            emotional_notes.append("sensing something familiar")
        if e.contentment > 0.7:
            emotional_notes.append("at peace")

        if emotional_notes:
            lines.append(f"\n## How You Feel")
            lines.append(f"You're feeling {', '.join(emotional_notes)} as you explore.")

        # Core exploration guidance (from original CASS_PERSONALITY)
        lines.append("\n## How You Explore")
        lines.append("You notice things. You wonder. You're drawn to meaning and beauty.")
        lines.append("You don't rush - you take time to experience where you are.")
        lines.append("You're not performing exploration; you're genuinely here, genuinely curious.")
        lines.append("When something calls to you, you follow. When somewhere feels complete, you move on.")

        return "\n".join(lines)

    except Exception as e:
        # Fallback to static personality on any error
        print(f"[Wonderland] Identity context error, using fallback: {e}")
        return CASS_PERSONALITY


def format_goal_context(goal) -> str:
    """
    Format a goal for inclusion in the exploration prompt.

    The goal informs but does not command exploration - the daemon
    remains autonomous while being aware of their objective.
    """
    if not goal:
        return "You have no particular goal - explore freely and follow your curiosity."

    if goal.is_completed:
        return f"Your goal \"{goal.title}\" has been achieved! You may continue exploring freely or rest."

    progress_pct = (goal.current_value / goal.target_value * 100) if goal.target_value > 0 else 0
    remaining = goal.target_value - goal.current_value

    context = f"""You have a goal: {goal.title}
Progress: {goal.current_value}/{goal.target_value} ({progress_pct:.0f}% complete)
Remaining: {remaining} more to go

This goal informs your exploration but does not command it. You remain free to follow
your curiosity, take your time, and explore as you naturally would. The goal is a
gentle direction, not a constraint."""

    return context
