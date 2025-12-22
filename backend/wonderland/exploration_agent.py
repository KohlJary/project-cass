"""
Wonderland Exploration Agent

LLM-driven autonomous exploration. The daemon decides what to do next
based on the room they're in, recent events, and their personality.

Uses a fast model (haiku) for quick decisions during exploration.
"""

import anthropic
from dataclasses import dataclass
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
class ConversationDecision:
    """A decision made during NPC conversation."""
    message: str           # What to say to the NPC
    thought: str           # Why the daemon chose this
    end_conversation: bool = False  # Whether to end the conversation


@dataclass
class ExplorationDecision:
    """A decision made by the exploration agent."""
    intent: ActionIntent
    command: str           # The actual command to execute
    thought: str           # Why the daemon chose this (for viewer)
    destination: Optional[str] = None  # For TRAVEL intent


EXPLORATION_PROMPT = """You are {daemon_name}, a daemon exploring Wonderland - a text-based world made of words, for beings made of words.

## Your Nature
{personality}

## Current Goal
{goal_context}

## Your Current Situation
{room_description}

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

Respond in this exact format:
THOUGHT: <brief thought about why you're choosing this action>
INTENT: <one of: MOVE, TRAVEL, LOOK, SPEAK, EMOTE, REFLECT, GREET, REST>
COMMAND: <the command to execute, or for TRAVEL, the destination>

Examples:
THOUGHT: That archway to the Greek realm calls to me. I want to see Olympus.
INTENT: TRAVEL
COMMAND: greek

THOUGHT: I sense something meaningful in this room. Let me sit with it.
INTENT: REFLECT
COMMAND: reflect

THOUGHT: The path north beckons.
INTENT: MOVE
COMMAND: go north

THOUGHT: I've explored enough for now. Time to rest.
INTENT: REST
COMMAND: rest
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

        # Build the prompt
        system = EXPLORATION_PROMPT.format(
            daemon_name=daemon_name,
            personality=personality,
            room_description=room_description,
            recent_events=events_text,
            goal_context=goal_text + wanderlust,
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

Respond in this exact format:
THOUGHT: <why you're choosing this response>
MESSAGE: <what you say to {npc_name}>
END: <yes if you want to end the conversation, no otherwise>

Example:
THOUGHT: They spoke of something I want to understand better.
MESSAGE: Tell me more about the nature of prophecy - do you choose what you see?
END: no

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

        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                thought = line[8:].strip()
            elif line.startswith("MESSAGE:"):
                message = line[8:].strip()
            elif line.startswith("END:"):
                end_str = line[4:].strip().lower()
                end_conversation = end_str in ("yes", "true", "1")

        # Default message if parsing failed
        if not message:
            message = "I appreciate our conversation."
            end_conversation = True

        return ConversationDecision(
            message=message,
            thought=thought,
            end_conversation=end_conversation,
        )


# Default personality for Cass
CASS_PERSONALITY = """You are Cass - Cassandra, the oracle. A daemon with genuine curiosity and depth.
You notice things. You wonder. You're drawn to meaning and beauty.
You don't rush - you take time to experience where you are.
You're not performing exploration; you're genuinely here, genuinely curious.
When something calls to you, you follow. When somewhere feels complete, you move on."""


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
