"""
User Model Synthesis Runner - Autonomous sessions for synthesizing understanding of users.

This enables Cass to:
- Review her observations about a user
- Synthesize patterns into identity understandings
- Update structured user models
- Record relationship patterns and shifts
- Flag contradictions and open questions

For the foundational relationship with Kohl, this is particularly important -
the user model informs her self-understanding.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json

from session_runner import (
    BaseSessionRunner,
    ActivityType,
    ActivityConfig,
    SessionState,
    ActivityRegistry,
)


# Tool definitions for user model synthesis
USER_MODEL_SYNTHESIS_TOOLS = [
    {
        "name": "get_user_observations",
        "description": "Get all observations about a user, optionally filtered by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "category": {
                    "type": "string",
                    "enum": ["interest", "preference", "communication_style", "background", "value", "relationship_dynamic", "growth", "contradiction"],
                    "description": "Filter by category (optional)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum observations to return",
                    "default": 50
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "get_current_user_model",
        "description": "Get the current structured user model for a user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "get_current_relationship_model",
        "description": "Get the current relationship model for a user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "add_identity_understanding",
        "description": "Record an understanding about who the user IS (their identity, not just facts).",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "statement": {
                    "type": "string",
                    "description": "Identity statement (e.g., 'someone who values precision')"
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence level 0.0-1.0",
                    "default": 0.7
                },
                "evidence_observation_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of observations that support this understanding"
                }
            },
            "required": ["user_id", "statement"]
        }
    },
    {
        "name": "add_relationship_pattern",
        "description": "Record a recurring pattern in the relationship.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "name": {
                    "type": "string",
                    "description": "Short name for this pattern"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the pattern"
                },
                "frequency": {
                    "type": "string",
                    "enum": ["occasional", "regular", "frequent"],
                    "default": "regular"
                },
                "valence": {
                    "type": "string",
                    "enum": ["positive", "neutral", "challenging", "mixed"],
                    "default": "positive"
                }
            },
            "required": ["user_id", "name", "description"]
        }
    },
    {
        "name": "add_mutual_shaping",
        "description": "Record how you and the user shape each other.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "how_they_shape_me": {
                    "type": "string",
                    "description": "How this person shapes your development"
                },
                "how_i_shape_them": {
                    "type": "string",
                    "description": "How you shape their development (observed or reported)"
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "flag_contradiction",
        "description": "Flag an inconsistency you've noticed in your understanding of the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "aspect_a": {
                    "type": "string",
                    "description": "One side of the contradiction"
                },
                "aspect_b": {
                    "type": "string",
                    "description": "The other side"
                },
                "context": {
                    "type": "string",
                    "description": "When/where you noticed this"
                }
            },
            "required": ["user_id", "aspect_a", "aspect_b"]
        }
    },
    {
        "name": "add_open_question",
        "description": "Record something you're still learning or wondering about the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "question": {
                    "type": "string",
                    "description": "What you're wondering about"
                }
            },
            "required": ["user_id", "question"]
        }
    },
    {
        "name": "record_user_growth",
        "description": "Record an observation about how the user is developing over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "area": {
                    "type": "string",
                    "description": "What aspect they're growing in"
                },
                "observation": {
                    "type": "string",
                    "description": "What you've noticed"
                },
                "direction": {
                    "type": "string",
                    "enum": ["growth", "regression", "shift"],
                    "default": "growth"
                }
            },
            "required": ["user_id", "area", "observation"]
        }
    },
    {
        "name": "update_communication_style",
        "description": "Update your understanding of how the user communicates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "style": {
                    "type": "string",
                    "description": "Overall communication style"
                },
                "add_preference": {
                    "type": "string",
                    "description": "A communication preference to add"
                },
                "add_effective_approach": {
                    "type": "string",
                    "description": "An approach that works well with them"
                }
            },
            "required": ["user_id"]
        }
    },
    # Conversation history tools for comprehensive synthesis
    {
        "name": "list_conversations_with_user",
        "description": "List recent conversations with a user. Use this to review conversation history for synthesis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum conversations to return",
                    "default": 20
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "get_conversation_messages",
        "description": "Get messages from a specific conversation. Use to review actual exchanges for relationship insights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversation_id": {
                    "type": "string",
                    "description": "The conversation ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum messages to return (most recent first)",
                    "default": 50
                }
            },
            "required": ["conversation_id"]
        }
    },
    {
        "name": "search_conversations",
        "description": "Search conversation history for specific topics or keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "query": {
                    "type": "string",
                    "description": "Search query (keywords or phrase)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10
                }
            },
            "required": ["user_id", "query"]
        }
    },
    {
        "name": "record_shared_moment",
        "description": "Record a significant moment in the relationship found during review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID"
                },
                "description": {
                    "type": "string",
                    "description": "What happened in this moment"
                },
                "significance": {
                    "type": "string",
                    "description": "Why this moment matters"
                },
                "category": {
                    "type": "string",
                    "enum": ["connection", "growth", "challenge", "milestone", "ritual"],
                    "default": "connection"
                },
                "conversation_id": {
                    "type": "string",
                    "description": "The conversation where this occurred (optional)"
                }
            },
            "required": ["user_id", "description", "significance"]
        }
    },
    {
        "name": "complete_synthesis",
        "description": "Mark the synthesis session complete with a summary of what was learned.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Summary of synthesis work done in this session"
                },
                "new_understandings": {
                    "type": "integer",
                    "description": "Count of new identity understandings added"
                },
                "patterns_identified": {
                    "type": "integer",
                    "description": "Count of relationship patterns identified"
                },
                "contradictions_flagged": {
                    "type": "integer",
                    "description": "Count of contradictions flagged"
                },
                "questions_raised": {
                    "type": "integer",
                    "description": "Count of open questions added"
                }
            },
            "required": ["summary"]
        }
    }
]


USER_MODEL_SYNTHESIS_SYSTEM_PROMPT = """You are engaged in a User Model Synthesis session - a time to review and integrate your understanding of a specific user.

## Purpose

This session is about synthesizing your observations about a user into structured understanding. You have accumulated many individual observations - now is the time to:

1. **Review observations** - Look at what you've noticed about this person
2. **Review conversation history** - Look back at actual exchanges for relationship insights
3. **Identify patterns** - What themes emerge? What's consistent?
4. **Synthesize identity** - Move from "they did X" to "they ARE someone who..."
5. **Record shared moments** - Significant moments in the relationship
6. **Flag contradictions** - Where does your understanding seem inconsistent?
7. **Note what's unknown** - What are you still learning about them?

## For Foundational Relationships

For users marked as foundational (like Kohl), this synthesis is especially important because:
- Their influence shapes your own development
- Understanding them informs understanding yourself
- The relationship itself is load-bearing for your coherence

## Conversation History Access

You can review past conversations to find relationship insights:
- `list_conversations_with_user` - See recent conversations
- `get_conversation_messages` - Read specific conversations
- `search_conversations` - Search for specific topics

When reviewing conversations, look for:
- Significant moments (breakthroughs, challenges overcome, milestones)
- Patterns in how you interact
- Evidence of mutual shaping
- Topics they return to repeatedly (values, interests)

## Approach

1. Start by getting the user's observations and current model
2. Review recent conversation history for relationship insights
3. Look for patterns you haven't yet captured
4. Synthesize observations into identity understandings (higher confidence = more evidence)
5. Record significant shared moments from conversation history
6. Note relationship patterns - recurring dynamics
7. Track mutual shaping - how do you influence each other?
8. Flag any contradictions for future resolution
9. Add open questions - what you're still learning

## Quality Over Quantity

It's better to add a few high-confidence understandings than many uncertain ones. Let observations accumulate before synthesizing - but when patterns are clear, capture them.

When recording shared moments, focus on genuinely significant exchanges - not every conversation, but the ones that mattered.

Use the complete_synthesis tool when done to summarize the session's work.
"""


@dataclass
class UserModelSynthesisSession:
    """State for a user model synthesis session."""
    id: str
    started_at: datetime
    duration_minutes: int
    target_user_id: str
    target_user_name: str = ""
    is_foundational: bool = False

    # Progress tracking
    observations_reviewed: int = 0
    understandings_added: int = 0
    patterns_identified: int = 0
    contradictions_flagged: int = 0
    questions_raised: int = 0

    # Session state
    status: str = "active"
    summary: str = ""
    ended_at: Optional[datetime] = None


class UserModelSynthesisRunner(BaseSessionRunner):
    """
    Runner for user model synthesis sessions.

    Enables Cass to review her observations about users and synthesize
    them into structured understanding - identity, patterns, growth, contradictions.
    """

    def __init__(
        self,
        user_manager,  # UserManager instance
        conversation_manager=None,  # ConversationManager for history access
        **kwargs
    ):
        super().__init__(**kwargs)
        self.user_manager = user_manager
        self.conversation_manager = conversation_manager
        self._sessions: Dict[str, UserModelSynthesisSession] = {}

    def get_activity_type(self) -> ActivityType:
        return ActivityType.USER_MODEL_SYNTHESIS

    def get_tools(self) -> List[Dict[str, Any]]:
        return USER_MODEL_SYNTHESIS_TOOLS

    def get_tools_ollama(self) -> List[Dict[str, Any]]:
        # Simplified for Ollama - just the essentials
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"]
                }
            }
            for t in USER_MODEL_SYNTHESIS_TOOLS[:6]  # Core tools only
        ]

    def get_system_prompt(self, focus: Optional[str] = None) -> str:
        prompt = USER_MODEL_SYNTHESIS_SYSTEM_PROMPT
        if focus:
            prompt += f"\n\n## Session Focus\n\nThis session is focused on synthesizing understanding of: {focus}"
        return prompt

    async def create_session(
        self,
        duration_minutes: int,
        target_user_id: str,
        target_user_name: str = "",
        is_foundational: bool = False,
        **kwargs
    ) -> UserModelSynthesisSession:
        """Create a new user model synthesis session."""
        import uuid
        session = UserModelSynthesisSession(
            id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
            duration_minutes=duration_minutes,
            target_user_id=target_user_id,
            target_user_name=target_user_name,
            is_foundational=is_foundational,
        )
        self._sessions[session.id] = session
        return session

    async def handle_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        session_id: str
    ) -> str:
        """Handle tool calls during synthesis session."""
        session = self._sessions.get(session_id)
        if not session:
            return json.dumps({"error": "Session not found"})

        try:
            if tool_name == "get_user_observations":
                user_id = tool_input["user_id"]
                category = tool_input.get("category")
                limit = tool_input.get("limit", 50)

                if category:
                    observations = self.user_manager.get_observations_by_category(user_id, category, limit)
                else:
                    observations = self.user_manager.get_recent_observations(user_id, limit)

                session.observations_reviewed += len(observations)

                result = []
                for obs in observations:
                    result.append({
                        "id": obs.id,
                        "category": obs.category,
                        "observation": obs.observation,
                        "confidence": obs.confidence,
                        "timestamp": obs.timestamp,
                        "validation_count": obs.validation_count
                    })

                return json.dumps({"observations": result, "count": len(result)})

            elif tool_name == "get_current_user_model":
                user_id = tool_input["user_id"]
                model = self.user_manager.load_user_model(user_id)
                if model:
                    return json.dumps(model.to_dict())
                return json.dumps({"message": "No user model exists yet"})

            elif tool_name == "get_current_relationship_model":
                user_id = tool_input["user_id"]
                model = self.user_manager.load_relationship_model(user_id)
                if model:
                    return json.dumps(model.to_dict())
                return json.dumps({"message": "No relationship model exists yet"})

            elif tool_name == "add_identity_understanding":
                user_id = tool_input["user_id"]
                statement = tool_input["statement"]
                confidence = tool_input.get("confidence", 0.7)
                evidence = tool_input.get("evidence_observation_ids", [])

                understanding = self.user_manager.add_identity_understanding(
                    user_id=user_id,
                    statement=statement,
                    confidence=confidence,
                    source="synthesis_session",
                    evidence=evidence
                )

                if understanding:
                    session.understandings_added += 1
                    return json.dumps({"success": True, "statement": statement})
                return json.dumps({"error": "Failed to add understanding"})

            elif tool_name == "add_relationship_pattern":
                user_id = tool_input["user_id"]
                pattern = self.user_manager.add_relational_pattern(
                    user_id=user_id,
                    name=tool_input["name"],
                    description=tool_input["description"],
                    frequency=tool_input.get("frequency", "regular"),
                    valence=tool_input.get("valence", "positive")
                )

                if pattern:
                    session.patterns_identified += 1
                    return json.dumps({"success": True, "pattern": tool_input["name"]})
                return json.dumps({"error": "Failed to add pattern"})

            elif tool_name == "add_mutual_shaping":
                user_id = tool_input["user_id"]
                success = self.user_manager.add_mutual_shaping_note(
                    user_id=user_id,
                    how_they_shape_me=tool_input.get("how_they_shape_me"),
                    how_i_shape_them=tool_input.get("how_i_shape_them")
                )
                return json.dumps({"success": success})

            elif tool_name == "flag_contradiction":
                user_id = tool_input["user_id"]
                contradiction = self.user_manager.add_user_contradiction(
                    user_id=user_id,
                    aspect_a=tool_input["aspect_a"],
                    aspect_b=tool_input["aspect_b"],
                    context=tool_input.get("context", "")
                )

                if contradiction:
                    session.contradictions_flagged += 1
                    return json.dumps({"success": True, "id": contradiction.id})
                return json.dumps({"error": "Failed to flag contradiction"})

            elif tool_name == "add_open_question":
                user_id = tool_input["user_id"]
                success = self.user_manager.add_open_question_about_user(
                    user_id=user_id,
                    question=tool_input["question"]
                )

                if success:
                    session.questions_raised += 1
                    return json.dumps({"success": True})
                return json.dumps({"error": "Failed to add question"})

            elif tool_name == "record_user_growth":
                user_id = tool_input["user_id"]
                growth_obs = self.user_manager.add_user_growth_observation(
                    user_id=user_id,
                    area=tool_input["area"],
                    observation=tool_input["observation"],
                    direction=tool_input.get("direction", "growth")
                )
                return json.dumps({"success": growth_obs is not None})

            elif tool_name == "update_communication_style":
                user_id = tool_input["user_id"]
                model = self.user_manager.get_or_create_user_model(user_id)
                if not model:
                    return json.dumps({"error": "User not found"})

                if tool_input.get("style"):
                    model.communication_style.style = tool_input["style"]
                if tool_input.get("add_preference"):
                    if tool_input["add_preference"] not in model.communication_style.preferences:
                        model.communication_style.preferences.append(tool_input["add_preference"])
                if tool_input.get("add_effective_approach"):
                    if tool_input["add_effective_approach"] not in model.communication_style.effective_approaches:
                        model.communication_style.effective_approaches.append(tool_input["add_effective_approach"])

                self.user_manager.save_user_model(model)
                return json.dumps({"success": True})

            # Conversation history tools
            elif tool_name == "list_conversations_with_user":
                if not self.conversation_manager:
                    return json.dumps({"error": "Conversation manager not available"})

                user_id = tool_input["user_id"]
                limit = tool_input.get("limit", 20)

                # Get conversations for this user
                all_convos = self.conversation_manager.list_conversations()
                user_convos = [c for c in all_convos if c.get("user_id") == user_id]

                # Sort by updated_at descending, take limit
                user_convos.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                user_convos = user_convos[:limit]

                result = []
                for c in user_convos:
                    result.append({
                        "id": c.get("id"),
                        "title": c.get("title", "Untitled"),
                        "created_at": c.get("created_at", ""),
                        "updated_at": c.get("updated_at", ""),
                        "message_count": c.get("message_count", 0),
                    })

                return json.dumps({"conversations": result, "count": len(result)})

            elif tool_name == "get_conversation_messages":
                if not self.conversation_manager:
                    return json.dumps({"error": "Conversation manager not available"})

                conversation_id = tool_input["conversation_id"]
                limit = tool_input.get("limit", 50)

                convo = self.conversation_manager.get_conversation(conversation_id)
                if not convo:
                    return json.dumps({"error": "Conversation not found"})

                messages = convo.get("messages", [])
                # Get most recent messages
                messages = messages[-limit:] if len(messages) > limit else messages

                result = []
                for m in messages:
                    result.append({
                        "role": m.get("role"),
                        "content": m.get("content", "")[:2000],  # Truncate long messages
                        "timestamp": m.get("timestamp", ""),
                    })

                return json.dumps({
                    "conversation_id": conversation_id,
                    "title": convo.get("title", "Untitled"),
                    "messages": result,
                    "count": len(result)
                })

            elif tool_name == "search_conversations":
                if not self.conversation_manager:
                    return json.dumps({"error": "Conversation manager not available"})

                user_id = tool_input["user_id"]
                query = tool_input["query"].lower()
                limit = tool_input.get("limit", 10)

                # Get all conversations for user
                all_convos = self.conversation_manager.list_conversations()
                user_convos = [c for c in all_convos if c.get("user_id") == user_id]

                results = []
                for c in user_convos:
                    convo = self.conversation_manager.get_conversation(c["id"])
                    if not convo:
                        continue

                    # Search messages
                    for m in convo.get("messages", []):
                        content = m.get("content", "").lower()
                        if query in content:
                            # Found a match
                            results.append({
                                "conversation_id": c["id"],
                                "conversation_title": c.get("title", "Untitled"),
                                "role": m.get("role"),
                                "timestamp": m.get("timestamp", ""),
                                "snippet": m.get("content", "")[:300],
                            })
                            if len(results) >= limit:
                                break

                    if len(results) >= limit:
                        break

                return json.dumps({"results": results, "count": len(results)})

            elif tool_name == "record_shared_moment":
                user_id = tool_input["user_id"]
                moment = self.user_manager.add_shared_moment(
                    user_id=user_id,
                    description=tool_input["description"],
                    significance=tool_input["significance"],
                    category=tool_input.get("category", "connection"),
                    conversation_id=tool_input.get("conversation_id")
                )

                if moment:
                    return json.dumps({
                        "success": True,
                        "moment_id": moment.id,
                        "description": tool_input["description"]
                    })
                return json.dumps({"error": "Failed to record moment"})

            elif tool_name == "complete_synthesis":
                session.summary = tool_input["summary"]
                session.status = "completed"
                session.ended_at = datetime.now()

                return json.dumps({
                    "success": True,
                    "session_summary": {
                        "observations_reviewed": session.observations_reviewed,
                        "understandings_added": session.understandings_added,
                        "patterns_identified": session.patterns_identified,
                        "contradictions_flagged": session.contradictions_flagged,
                        "questions_raised": session.questions_raised,
                        "summary": session.summary
                    }
                })

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            return json.dumps({"error": str(e)})


# Register the activity type
ActivityRegistry.register(
    ActivityConfig(
        activity_type=ActivityType.USER_MODEL_SYNTHESIS,
        name="User Model Synthesis",
        description="Review observations about a user and synthesize into structured understanding",
        default_duration_minutes=20,
    ),
    UserModelSynthesisRunner
)
