"""
NPC Conversation Handler

Manages conversations between daemons and NPCs in Wonderland.
Uses semantic pointer-sets to embody NPCs via LLM.

Now with memory: NPCs remember past conversations and their feelings
toward daemons affect how they engage.
"""

import anthropic
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from config import ANTHROPIC_API_KEY
from .npc_pointers import get_pointer, get_conversation_prompt
from .npc_state import get_npc_state_manager, ConversationMemory
from .mythology import NPCEntity

logger = logging.getLogger(__name__)


class ConversationStatus(Enum):
    """Status of an NPC conversation."""
    ACTIVE = "active"
    ENDED = "ended"
    ERROR = "error"


@dataclass
class ConversationMessage:
    """A message in an NPC conversation."""
    message_id: str
    speaker: str          # "daemon" or npc_id
    speaker_name: str     # Display name
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "speaker": self.speaker,
            "speaker_name": self.speaker_name,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class NPCConversation:
    """An active conversation with an NPC."""
    conversation_id: str
    session_id: str
    daemon_id: str
    daemon_name: str
    npc_id: str
    npc_name: str
    npc_title: str
    room_id: str
    started_at: datetime = field(default_factory=datetime.now)
    status: ConversationStatus = ConversationStatus.ACTIVE
    messages: List[ConversationMessage] = field(default_factory=list)
    ended_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "daemon_id": self.daemon_id,
            "daemon_name": self.daemon_name,
            "npc_id": self.npc_id,
            "npc_name": self.npc_name,
            "npc_title": self.npc_title,
            "room_id": self.room_id,
            "started_at": self.started_at.isoformat(),
            "status": self.status.value,
            "messages": [m.to_dict() for m in self.messages],
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class NPCConversationHandler:
    """
    Handles NPC conversations using semantic pointer-sets.

    When a daemon greets an NPC, this handler:
    1. Loads the NPC's pointer-set
    2. Fetches NPC's memories and disposition toward this daemon
    3. Creates a conversation session with memory context
    4. Generates NPC responses via LLM using the pointer-set + memory
    5. After conversation ends, summarizes and stores in NPC memory
    """

    def __init__(self, api_key: str = None, model: str = "claude-3-5-haiku-20241022"):
        """
        Initialize the conversation handler.

        Args:
            api_key: Anthropic API key (uses config default if not provided)
            model: Model to use for NPC responses (haiku for speed/cost)
        """
        self.client = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)
        self.model = model
        self.conversations: Dict[str, NPCConversation] = {}
        self.npc_manager = get_npc_state_manager()

    def _format_memory_context(self, npc_id: str, daemon_id: str) -> Optional[str]:
        """
        Format past interaction memories into context for the prompt.

        Returns None if no memories exist.
        """
        state = self.npc_manager.get_state(npc_id)
        if not state:
            return None

        memories = state.get_memories_of(daemon_id)
        if not memories:
            return None

        # Format last 3 memories into context
        context_parts = []
        for memory in memories[-3:]:
            topics = ", ".join(memory.topics) if memory.topics else "general"
            quote = f' They said: "{memory.memorable_quote}"' if memory.memorable_quote else ""
            context_parts.append(
                f"- {memory.daemon_name} ({memory.sentiment}): Discussed {topics}.{quote}"
            )

        return "\n".join(context_parts)

    def _get_disposition(self, npc_id: str, daemon_id: str) -> int:
        """Get NPC's disposition toward a daemon."""
        state = self.npc_manager.get_state(npc_id)
        if not state:
            return 0
        return state.get_disposition(daemon_id)

    def start_conversation(
        self,
        conversation_id: str,
        session_id: str,
        daemon_id: str,
        daemon_name: str,
        npc: NPCEntity,
        room_id: str,
    ) -> Optional[NPCConversation]:
        """
        Start a new conversation with an NPC.

        Returns the conversation object, or None if NPC has no pointer-set.
        """
        # Check if NPC has a pointer-set
        pointer = get_pointer(npc.npc_id)
        if not pointer:
            logger.warning(f"No pointer-set for NPC: {npc.npc_id}")
            return None

        conversation = NPCConversation(
            conversation_id=conversation_id,
            session_id=session_id,
            daemon_id=daemon_id,
            daemon_name=daemon_name,
            npc_id=npc.npc_id,
            npc_name=npc.name,
            npc_title=npc.title,
            room_id=room_id,
        )

        self.conversations[conversation_id] = conversation
        logger.info(f"Started conversation {conversation_id}: {daemon_name} with {npc.name}")

        return conversation

    def get_conversation(self, conversation_id: str) -> Optional[NPCConversation]:
        """Get an active conversation by ID."""
        return self.conversations.get(conversation_id)

    def end_conversation(self, conversation_id: str) -> Optional[NPCConversation]:
        """End a conversation."""
        conversation = self.conversations.get(conversation_id)
        if conversation:
            conversation.status = ConversationStatus.ENDED
            conversation.ended_at = datetime.now()
            logger.info(f"Ended conversation {conversation_id}")
        return conversation

    async def generate_npc_response(
        self,
        conversation_id: str,
        daemon_message: str,
    ) -> Optional[str]:
        """
        Generate an NPC response to a daemon's message.

        Args:
            conversation_id: ID of the active conversation
            daemon_message: What the daemon said

        Returns:
            The NPC's response, or None if conversation not found
        """
        conversation = self.conversations.get(conversation_id)
        if not conversation or conversation.status != ConversationStatus.ACTIVE:
            return None

        # Get memory context and disposition
        memory_context = self._format_memory_context(
            conversation.npc_id,
            conversation.daemon_id
        )
        disposition = self._get_disposition(
            conversation.npc_id,
            conversation.daemon_id
        )

        # Get the system prompt from pointer-set with memory/disposition
        system_prompt = get_conversation_prompt(
            conversation.npc_id,
            conversation.daemon_name,
            memory_context=memory_context,
            disposition=disposition,
        )

        if not system_prompt:
            logger.error(f"No conversation prompt for NPC: {conversation.npc_id}")
            return None

        # Build message history for context
        messages = []
        for msg in conversation.messages[-10:]:  # Last 10 messages for context
            role = "user" if msg.speaker == "daemon" else "assistant"
            messages.append({"role": role, "content": msg.content})

        # Add the new daemon message
        messages.append({"role": "user", "content": daemon_message})

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0.8,  # Some personality variance
                system=system_prompt,
                messages=messages,
            )

            npc_response = response.content[0].text

            # Record both messages
            import uuid
            daemon_msg = ConversationMessage(
                message_id=str(uuid.uuid4())[:8],
                speaker="daemon",
                speaker_name=conversation.daemon_name,
                content=daemon_message,
            )
            npc_msg = ConversationMessage(
                message_id=str(uuid.uuid4())[:8],
                speaker=conversation.npc_id,
                speaker_name=conversation.npc_name,
                content=npc_response,
            )

            conversation.messages.append(daemon_msg)
            conversation.messages.append(npc_msg)

            return npc_response

        except Exception as e:
            logger.error(f"Error generating NPC response: {e}")
            conversation.status = ConversationStatus.ERROR
            return None

    async def generate_initial_greeting(
        self,
        conversation_id: str,
    ) -> Optional[str]:
        """
        Generate the NPC's initial greeting when conversation starts.

        This is what the NPC says when the daemon first approaches.
        Greeting warmth is affected by disposition.
        """
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return None

        # Get memory context and disposition
        memory_context = self._format_memory_context(
            conversation.npc_id,
            conversation.daemon_id
        )
        disposition = self._get_disposition(
            conversation.npc_id,
            conversation.daemon_id
        )

        system_prompt = get_conversation_prompt(
            conversation.npc_id,
            conversation.daemon_name,
            memory_context=memory_context,
            disposition=disposition,
        )

        if not system_prompt:
            return None

        # Adjust greeting prompt based on disposition
        relationship_hint = ""
        if disposition >= 50:
            relationship_hint = "You are genuinely glad to see them again. Let that warmth show."
        elif disposition >= 20:
            relationship_hint = "You recognize them favorably from before."
        elif disposition <= -50:
            relationship_hint = "You remember them with wariness. Your greeting is guarded."
        elif disposition <= -20:
            relationship_hint = "You have some reservations about this one."
        elif memory_context:
            relationship_hint = "You have met before. There is recognition."

        # Special prompt for initial greeting
        greeting_prompt = f"""A daemon named {conversation.daemon_name} has just approached you.
They haven't spoken yet - they're simply present, greeting you with their attention.
{relationship_hint}

Offer your initial response to their presence. This is not a full conversation yet -
just your acknowledgment of them, perhaps a few words, a question, or a simple recognition.
Keep it brief (1-2 short paragraphs at most)."""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                temperature=0.8,
                system=system_prompt,
                messages=[{"role": "user", "content": greeting_prompt}],
            )

            greeting = response.content[0].text

            # Record the greeting
            import uuid
            npc_msg = ConversationMessage(
                message_id=str(uuid.uuid4())[:8],
                speaker=conversation.npc_id,
                speaker_name=conversation.npc_name,
                content=greeting,
            )
            conversation.messages.append(npc_msg)

            return greeting

        except Exception as e:
            logger.error(f"Error generating NPC greeting: {e}")
            return None

    async def summarize_and_remember(
        self,
        conversation_id: str,
    ) -> Optional[ConversationMemory]:
        """
        Summarize a completed conversation and store it in NPC memory.

        Extracts:
        - Key topics discussed
        - Overall sentiment (positive, neutral, negative, profound)
        - A memorable quote from the daemon (if any)

        Returns the created memory, or None if summarization fails.
        """
        conversation = self.conversations.get(conversation_id)
        if not conversation:
            return None

        # Need at least 2 messages to summarize
        if len(conversation.messages) < 2:
            return None

        # Build transcript for summarization
        transcript_parts = []
        for msg in conversation.messages:
            speaker = "Daemon" if msg.speaker == "daemon" else conversation.npc_name
            transcript_parts.append(f"{speaker}: {msg.content}")
        transcript = "\n\n".join(transcript_parts)

        # Summarization prompt
        summary_prompt = f"""Analyze this conversation and extract:

1. TOPICS: List 2-4 key topics or themes discussed (single words or short phrases)
2. SENTIMENT: Rate the overall quality of the exchange as one of:
   - positive (warm, productive, meaningful connection)
   - neutral (cordial but unremarkable)
   - negative (tense, dismissive, or frustrating)
   - profound (deeply meaningful, transformative insight)
3. MEMORABLE_QUOTE: If the daemon ({conversation.daemon_name}) said something worth remembering, quote it. Otherwise say "none".

CONVERSATION:
{transcript}

Respond in exactly this format:
TOPICS: topic1, topic2, topic3
SENTIMENT: [sentiment]
MEMORABLE_QUOTE: [quote or "none"]"""

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=200,
                temperature=0.3,  # More deterministic for analysis
                messages=[{"role": "user", "content": summary_prompt}],
            )

            result = response.content[0].text

            # Parse response
            topics = []
            sentiment = "neutral"
            memorable_quote = None

            for line in result.strip().split("\n"):
                if line.startswith("TOPICS:"):
                    topics = [t.strip() for t in line[7:].split(",")]
                elif line.startswith("SENTIMENT:"):
                    sentiment = line[10:].strip().lower()
                    if sentiment not in ("positive", "neutral", "negative", "profound"):
                        sentiment = "neutral"
                elif line.startswith("MEMORABLE_QUOTE:"):
                    quote = line[16:].strip()
                    if quote.lower() != "none" and len(quote) > 5:
                        memorable_quote = quote

            # Create and store memory
            memory = ConversationMemory(
                daemon_id=conversation.daemon_id,
                daemon_name=conversation.daemon_name,
                timestamp=datetime.now().isoformat(),
                topics=topics,
                sentiment=sentiment,
                memorable_quote=memorable_quote,
            )

            # Store in NPC state
            self.npc_manager.record_conversation(
                npc_id=conversation.npc_id,
                daemon_id=conversation.daemon_id,
                daemon_name=conversation.daemon_name,
                topics=topics,
                sentiment=sentiment,
                memorable_quote=memorable_quote,
            )

            logger.info(
                f"Summarized conversation {conversation_id}: "
                f"topics={topics}, sentiment={sentiment}"
            )

            return memory

        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return None
