"""
User model tool handler - enables Cass to explicitly reflect on and update her understanding of users.

These tools allow Cass to:
- Review what she knows about a user
- Record observations about users explicitly
- Update user profile fields
- Review observations filtered by category
"""
from typing import Dict, Optional
from users import UserManager, USER_OBSERVATION_CATEGORIES


async def execute_user_model_tool(
    tool_name: str,
    tool_input: Dict,
    user_manager: UserManager,
    target_user_id: str = None,
    conversation_id: str = None,
    memory=None
) -> Dict:
    """
    Execute a user model tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        user_manager: UserManager instance
        target_user_id: ID of user being observed (defaults to current user)
        conversation_id: Current conversation ID
        memory: CassMemory instance (for embedding observations)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "reflect_on_user":
            user_id = tool_input.get("user_id") or target_user_id
            focus = tool_input.get("focus", "general")

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {
                    "success": False,
                    "error": f"User not found: {user_id}"
                }

            if focus == "background":
                result_lines = [f"## Reflection on {profile.display_name}: Background\n"]
                if profile.background:
                    for key, value in profile.background.items():
                        result_lines.append(f"- **{key}**: {value}")
                else:
                    result_lines.append("*No background information recorded yet.*")

            elif focus == "communication":
                result_lines = [f"## Reflection on {profile.display_name}: Communication\n"]
                if profile.communication:
                    style = profile.communication.get("style")
                    if style:
                        result_lines.append(f"**Style:** {style}")
                    prefs = profile.communication.get("preferences", [])
                    if prefs:
                        result_lines.append("**Preferences:**")
                        for pref in prefs:
                            result_lines.append(f"  - {pref}")
                else:
                    result_lines.append("*No communication style information recorded yet.*")

            elif focus == "observations":
                result_lines = [f"## Reflection on {profile.display_name}: My Observations\n"]
                observations = user_manager.get_recent_observations(user_id, limit=15)
                if observations:
                    by_category = {}
                    for obs in observations:
                        if obs.category not in by_category:
                            by_category[obs.category] = []
                        by_category[obs.category].append(obs)

                    for category, obs_list in by_category.items():
                        result_lines.append(f"### {category.replace('_', ' ').title()}")
                        for obs in obs_list:
                            conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                            result_lines.append(f"- {obs.observation} {conf}")
                        result_lines.append("")
                else:
                    result_lines.append("*No observations recorded yet.*")

            elif focus == "values":
                result_lines = [f"## Reflection on {profile.display_name}: Values\n"]
                if profile.values:
                    for value in profile.values:
                        result_lines.append(f"- {value}")
                else:
                    result_lines.append("*No values recorded yet.*")

            else:  # general
                # Full context
                context = user_manager.get_user_context(user_id)
                result_lines = [context] if context else [f"*No information recorded about {profile.display_name} yet.*"]

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "record_user_observation":
            user_id = tool_input.get("user_id") or target_user_id
            observation = tool_input["observation"]
            category = tool_input.get("category", "background")
            confidence = tool_input.get("confidence", 0.7)

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            # Validate category
            if category not in USER_OBSERVATION_CATEGORIES:
                return {
                    "success": False,
                    "error": f"Invalid category '{category}'. Must be one of: {', '.join(USER_OBSERVATION_CATEGORIES)}"
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {
                    "success": False,
                    "error": f"User not found: {user_id}"
                }

            # Add observation
            obs = user_manager.add_observation(
                user_id=user_id,
                observation=observation,
                category=category,
                confidence=confidence,
                source_conversation_id=conversation_id,
                source_type="explicit_reflection"
            )

            # Embed in ChromaDB if memory is available
            if memory and obs:
                memory.embed_user_observation(
                    user_id=user_id,
                    observation_id=obs.id,
                    observation_text=observation,
                    category=category,
                    confidence=confidence,
                    timestamp=obs.timestamp
                )

            return {
                "success": True,
                "result": f"Recorded observation about {profile.display_name}:\n\n**[{category}]** {observation}\n\n*Confidence: {int(confidence * 100)}%*\n\nThis observation is now part of my understanding of {profile.display_name}."
            }

        elif tool_name == "update_user_profile":
            user_id = tool_input.get("user_id") or target_user_id
            field = tool_input["field"]
            value = tool_input["value"]
            action = tool_input.get("action", "set")  # set, append, remove

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {
                    "success": False,
                    "error": f"User not found: {user_id}"
                }

            valid_fields = ["background", "communication", "values", "notes"]
            if field not in valid_fields:
                return {
                    "success": False,
                    "error": f"Invalid field '{field}'. Must be one of: {', '.join(valid_fields)}"
                }

            old_value = None

            if field == "background":
                if action == "set" and isinstance(value, dict):
                    # Set a specific key in background
                    key = list(value.keys())[0] if value else None
                    if key:
                        old_value = profile.background.get(key)
                        profile.background[key] = value[key]
                elif action == "remove" and isinstance(value, str):
                    old_value = profile.background.pop(value, None)

            elif field == "communication":
                if action == "set" and isinstance(value, dict):
                    key = list(value.keys())[0] if value else None
                    if key:
                        old_value = profile.communication.get(key)
                        profile.communication[key] = value[key]
                elif action == "append" and isinstance(value, str):
                    # Append to preferences list
                    if "preferences" not in profile.communication:
                        profile.communication["preferences"] = []
                    profile.communication["preferences"].append(value)

            elif field == "values":
                if action == "append" and isinstance(value, str):
                    if value not in profile.values:
                        profile.values.append(value)
                elif action == "remove" and isinstance(value, str):
                    if value in profile.values:
                        profile.values.remove(value)
                        old_value = value
                elif action == "set" and isinstance(value, list):
                    old_value = profile.values.copy()
                    profile.values = value

            elif field == "notes":
                if action == "set":
                    old_value = profile.notes
                    profile.notes = str(value)
                elif action == "append":
                    profile.notes = profile.notes + "\n" + str(value) if profile.notes else str(value)

            user_manager.update_profile(profile)

            result_msg = f"Updated {profile.display_name}'s profile:\n\n**Field:** {field}\n**Action:** {action}\n**Value:** {value}"
            if old_value:
                result_msg += f"\n**Previous value:** {old_value}"

            return {
                "success": True,
                "result": result_msg
            }

        elif tool_name == "review_user_observations":
            user_id = tool_input.get("user_id") or target_user_id
            category = tool_input.get("category")
            limit = tool_input.get("limit", 10)

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {
                    "success": False,
                    "error": f"User not found: {user_id}"
                }

            if category:
                if category not in USER_OBSERVATION_CATEGORIES:
                    return {
                        "success": False,
                        "error": f"Invalid category '{category}'. Must be one of: {', '.join(USER_OBSERVATION_CATEGORIES)}"
                    }
                observations = user_manager.get_observations_by_category(user_id, category, limit)
                result_lines = [f"## Observations about {profile.display_name} [{category}]\n"]
            else:
                observations = user_manager.get_recent_observations(user_id, limit)
                result_lines = [f"## Recent Observations about {profile.display_name}\n"]

            if observations:
                for obs in observations:
                    conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                    validated = f"[validated {obs.validation_count}x]" if obs.validation_count > 1 else ""
                    result_lines.append(f"- **[{obs.category}]** {obs.observation} {conf} {validated}")
            else:
                result_lines.append(f"*No observations recorded yet{' in this category' if category else ''}.*")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        else:
            return {"success": False, "error": f"Unknown user model tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions for agent_client.py
USER_MODEL_TOOLS = [
    {
        "name": "reflect_on_user",
        "description": "Review what you know about a user. Use this to recall information about someone you're talking to or have talked to before.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "focus": {
                    "type": "string",
                    "description": "What aspect to reflect on: 'general' (full context), 'background' (their background), 'communication' (how they communicate), 'observations' (your observations about them), 'values' (their values)",
                    "enum": ["general", "background", "communication", "observations", "values"],
                    "default": "general"
                }
            },
            "required": []
        }
    },
    {
        "name": "record_user_observation",
        "description": "Record something you've noticed about a user. Use this when you learn something meaningful about someone - their interests, preferences, communication style, values, or relationship patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "observation": {
                    "type": "string",
                    "description": "What you've observed about this person"
                },
                "category": {
                    "type": "string",
                    "description": "Type of observation",
                    "enum": ["interest", "preference", "communication_style", "background", "value", "relationship_dynamic"],
                    "default": "background"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are in this observation (0.0-1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7
                }
            },
            "required": ["observation"]
        }
    },
    {
        "name": "update_user_profile",
        "description": "Update a user's profile with new information. Use this to record stable facts about someone (background info, communication preferences, values).",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "field": {
                    "type": "string",
                    "description": "Which profile field to update",
                    "enum": ["background", "communication", "values", "notes"]
                },
                "value": {
                    "description": "The value to set/append. For background/communication: use {key: value} dict. For values: use string. For notes: use string."
                },
                "action": {
                    "type": "string",
                    "description": "How to apply the value: 'set' (replace), 'append' (add to list), 'remove' (delete)",
                    "enum": ["set", "append", "remove"],
                    "default": "set"
                }
            },
            "required": ["field", "value"]
        }
    },
    {
        "name": "review_user_observations",
        "description": "Review your observations about a user, optionally filtered by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "category": {
                    "type": "string",
                    "description": "Filter by observation category (optional)",
                    "enum": ["interest", "preference", "communication_style", "background", "value", "relationship_dynamic"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of observations to return",
                    "default": 10
                }
            },
            "required": []
        }
    }
]
