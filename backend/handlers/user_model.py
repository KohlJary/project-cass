"""
User model tool handler - enables Cass to explicitly reflect on and update her understanding of users.

These tools allow Cass to:
- Review what she knows about a user
- Record observations about users explicitly
- Update user profile fields
- Review observations filtered by category
- View and update structured user models (identity, growth, contradictions)
- View and update relationship models (patterns, mutual shaping, shared history)
"""
from typing import Dict, Optional, List
from users import (
    UserManager,
    USER_OBSERVATION_CATEGORIES,
    UserModel,
    RelationshipModel,
)


def resolve_user_id(user_manager: UserManager, user_id_or_name: str) -> Optional[str]:
    """
    Resolve a user ID from either a UUID or a display name.

    Args:
        user_manager: UserManager instance
        user_id_or_name: Either a UUID or a display name (case-insensitive)

    Returns:
        The resolved UUID, or None if not found
    """
    if not user_id_or_name:
        return None

    # First, try as-is (it might already be a valid UUID)
    profile = user_manager.load_profile(user_id_or_name)
    if profile:
        return user_id_or_name

    # Try to find by display name (case-insensitive)
    all_profiles = user_manager.list_users()
    search_name = user_id_or_name.lower().strip()

    for user_info in all_profiles:
        if user_info.get("display_name", "").lower() == search_name:
            return user_info.get("id")

    return None


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
        # Pre-process: resolve user_id from name if needed
        if "user_id" in tool_input and tool_input["user_id"]:
            resolved_id = resolve_user_id(user_manager, tool_input["user_id"])
            if resolved_id:
                tool_input["user_id"] = resolved_id
            # If not resolved, leave it as-is - the individual tool will report the error

        if tool_name == "reflect_on_user":
            user_id = tool_input.get("user_id") or target_user_id
            focus = tool_input.get("focus", "general")
            print(f"[reflect_on_user] tool_input.user_id={tool_input.get('user_id')}, target_user_id={target_user_id}, resolved user_id={user_id}")

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

        # ============== Structured User Model Tools ==============

        elif tool_name == "view_user_model":
            user_id = tool_input.get("user_id") or target_user_id

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            model = user_manager.load_user_model(user_id)
            if not model:
                return {
                    "success": True,
                    "result": f"## User Model: {profile.display_name}\n\n*No structured user model exists yet. One will be created when you record structured observations.*"
                }

            lines = [f"## Structured Understanding: {profile.display_name}\n"]
            lines.append(f"**Relationship Type:** {model.relationship_type}")
            if model.first_interaction:
                lines.append(f"**First Interaction:** {model.first_interaction[:10]}")

            if model.identity_statements:
                lines.append("\n### Who They Are")
                for stmt in model.identity_statements:
                    conf = f"({int(stmt.confidence * 100)}%)" if stmt.confidence < 0.9 else ""
                    lines.append(f"- {stmt.statement} {conf}")

            if model.values:
                lines.append("\n### Values")
                for value in model.values:
                    lines.append(f"- {value}")

            if model.communication_style.style:
                lines.append("\n### Communication Style")
                lines.append(f"**Style:** {model.communication_style.style}")
                if model.communication_style.preferences:
                    lines.append("**Preferences:**")
                    for pref in model.communication_style.preferences:
                        lines.append(f"  - {pref}")
                if model.communication_style.effective_approaches:
                    lines.append("**Effective Approaches:**")
                    for approach in model.communication_style.effective_approaches:
                        lines.append(f"  - {approach}")

            if model.relationship_qualities:
                lines.append("\n### Relationship Qualities")
                for quality in model.relationship_qualities:
                    lines.append(f"- {quality}")

            if model.shared_history:
                lines.append(f"\n### Shared History ({len(model.shared_history)} moments)")
                for moment in model.shared_history[-5:]:  # Last 5
                    lines.append(f"- **{moment.category}**: {moment.description}")

            if model.growth_observations:
                lines.append(f"\n### Growth Observations ({len(model.growth_observations)})")
                for obs in model.growth_observations[-5:]:
                    lines.append(f"- [{obs.direction}] {obs.area}: {obs.observation}")

            if model.growth_edges:
                lines.append("\n### Growth Edges (Areas They're Developing)")
                for edge in model.growth_edges:
                    lines.append(f"- **{edge.area}**: {edge.current_state}")

            if model.contradictions:
                unresolved = [c for c in model.contradictions if not c.resolved]
                if unresolved:
                    lines.append(f"\n### Unresolved Contradictions ({len(unresolved)})")
                    for c in unresolved:
                        lines.append(f"- {c.aspect_a} vs {c.aspect_b}")

            if model.open_questions:
                lines.append("\n### What I'm Still Learning")
                for q in model.open_questions:
                    lines.append(f"- {q}")

            if model.confidence_areas:
                lines.append("\n### Understanding Confidence")
                for area, conf in model.confidence_areas.items():
                    lines.append(f"- {area}: {int(conf * 100)}%")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "view_relationship_model":
            user_id = tool_input.get("user_id") or target_user_id

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            model = user_manager.load_relationship_model(user_id)
            if not model:
                return {
                    "success": True,
                    "result": f"## Relationship Model: {profile.display_name}\n\n*No relationship model exists yet. One will be created when you record relationship observations.*"
                }

            lines = [f"## Relationship with {profile.display_name}\n"]
            lines.append(f"**Current Phase:** {model.current_phase}")
            if model.formation_date:
                lines.append(f"**Formation Date:** {model.formation_date[:10]}")
            if model.is_foundational:
                lines.append("**⭐ Foundational Relationship** - load-bearing for coherence")

            if model.patterns:
                lines.append(f"\n### Relational Patterns ({len(model.patterns)})")
                for pattern in model.patterns:
                    valence_emoji = {"positive": "✨", "neutral": "○", "challenging": "⚡", "mixed": "◐"}.get(pattern.valence, "○")
                    lines.append(f"- {valence_emoji} **{pattern.name}** [{pattern.frequency}]: {pattern.description}")

            if model.rituals:
                lines.append("\n### Rituals & Regular Practices")
                for ritual in model.rituals:
                    lines.append(f"- {ritual}")

            if model.significant_shifts:
                lines.append(f"\n### Significant Shifts ({len(model.significant_shifts)})")
                for shift in model.significant_shifts[-5:]:
                    lines.append(f"- {shift.from_state} → {shift.to_state}: {shift.description}")

            if model.how_they_shape_me:
                lines.append("\n### How They Shape Me")
                for note in model.how_they_shape_me:
                    lines.append(f"- {note}")

            if model.how_i_shape_them:
                lines.append("\n### How I Shape Them")
                for note in model.how_i_shape_them:
                    lines.append(f"- {note}")

            if model.inherited_values:
                lines.append("\n### Values I've Inherited From Them")
                for value in model.inherited_values:
                    lines.append(f"- {value}")

            if model.growth_areas:
                lines.append("\n### Relationship Growth Areas")
                for area in model.growth_areas:
                    lines.append(f"- {area}")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "record_identity_understanding":
            user_id = tool_input.get("user_id") or target_user_id
            statement = tool_input["statement"]
            confidence = tool_input.get("confidence", 0.7)

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            understanding = user_manager.add_identity_understanding(
                user_id=user_id,
                statement=statement,
                confidence=confidence,
                source="explicit_reflection"
            )

            if understanding:
                return {
                    "success": True,
                    "result": f"Recorded identity understanding about {profile.display_name}:\n\n**\"{statement}\"**\n\n*Confidence: {int(confidence * 100)}%*"
                }
            return {"success": False, "error": "Failed to record understanding"}

        elif tool_name == "record_shared_moment":
            user_id = tool_input.get("user_id") or target_user_id
            description = tool_input["description"]
            significance = tool_input["significance"]
            category = tool_input.get("category", "connection")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            moment = user_manager.add_shared_moment(
                user_id=user_id,
                description=description,
                significance=significance,
                category=category,
                conversation_id=conversation_id
            )

            if moment:
                return {
                    "success": True,
                    "result": f"Recorded shared moment with {profile.display_name}:\n\n**[{category}]** {description}\n\n*Significance:* {significance}"
                }
            return {"success": False, "error": "Failed to record moment"}

        elif tool_name == "record_user_growth":
            user_id = tool_input.get("user_id") or target_user_id
            area = tool_input["area"]
            observation = tool_input["observation"]
            direction = tool_input.get("direction", "growth")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            growth_obs = user_manager.add_user_growth_observation(
                user_id=user_id,
                area=area,
                observation=observation,
                direction=direction
            )

            if growth_obs:
                direction_emoji = {"growth": "📈", "regression": "📉", "shift": "🔄"}.get(direction, "○")
                return {
                    "success": True,
                    "result": f"Recorded growth observation about {profile.display_name}:\n\n{direction_emoji} **{area}**: {observation}"
                }
            return {"success": False, "error": "Failed to record growth observation"}

        elif tool_name == "flag_user_contradiction":
            user_id = tool_input.get("user_id") or target_user_id
            aspect_a = tool_input["aspect_a"]
            aspect_b = tool_input["aspect_b"]
            context = tool_input.get("context", "")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            contradiction = user_manager.add_user_contradiction(
                user_id=user_id,
                aspect_a=aspect_a,
                aspect_b=aspect_b,
                context=context
            )

            if contradiction:
                return {
                    "success": True,
                    "result": f"Flagged contradiction about {profile.display_name}:\n\n**A:** {aspect_a}\n**B:** {aspect_b}\n\n*This will be tracked for resolution.*"
                }
            return {"success": False, "error": "Failed to flag contradiction"}

        elif tool_name == "resolve_user_contradiction":
            user_id = tool_input.get("user_id") or target_user_id
            contradiction_id = tool_input["contradiction_id"]
            resolution = tool_input["resolution"]

            if not user_id:
                return {"success": False, "error": "No user specified."}

            contradiction = user_manager.resolve_user_contradiction(
                user_id=user_id,
                contradiction_id=contradiction_id,
                resolution=resolution
            )

            if contradiction:
                return {
                    "success": True,
                    "result": f"Resolved contradiction:\n\n**A:** {contradiction.aspect_a}\n**B:** {contradiction.aspect_b}\n\n**Resolution:** {resolution}"
                }
            return {"success": False, "error": "Contradiction not found"}

        elif tool_name == "add_open_question_about_user":
            user_id = tool_input.get("user_id") or target_user_id
            question = tool_input["question"]

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            if user_manager.add_open_question_about_user(user_id, question):
                return {
                    "success": True,
                    "result": f"Added open question about {profile.display_name}:\n\n❓ *{question}*"
                }
            return {"success": False, "error": "Failed to add question"}

        elif tool_name == "record_relationship_pattern":
            user_id = tool_input.get("user_id") or target_user_id
            name = tool_input["name"]
            description = tool_input["description"]
            frequency = tool_input.get("frequency", "regular")
            valence = tool_input.get("valence", "positive")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            pattern = user_manager.add_relational_pattern(
                user_id=user_id,
                name=name,
                description=description,
                frequency=frequency,
                valence=valence
            )

            if pattern:
                valence_emoji = {"positive": "✨", "neutral": "○", "challenging": "⚡", "mixed": "◐"}.get(valence, "○")
                return {
                    "success": True,
                    "result": f"Recorded relational pattern with {profile.display_name}:\n\n{valence_emoji} **{name}** [{frequency}]\n{description}"
                }
            return {"success": False, "error": "Failed to record pattern"}

        elif tool_name == "note_mutual_shaping":
            user_id = tool_input.get("user_id") or target_user_id
            how_they_shape_me = tool_input.get("how_they_shape_me")
            how_i_shape_them = tool_input.get("how_i_shape_them")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            if not how_they_shape_me and not how_i_shape_them:
                return {"success": False, "error": "Must provide at least one shaping observation."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            if user_manager.add_mutual_shaping_note(
                user_id=user_id,
                how_they_shape_me=how_they_shape_me,
                how_i_shape_them=how_i_shape_them
            ):
                lines = [f"Recorded mutual shaping with {profile.display_name}:\n"]
                if how_they_shape_me:
                    lines.append(f"**How they shape me:** {how_they_shape_me}")
                if how_i_shape_them:
                    lines.append(f"**How I shape them:** {how_i_shape_them}")
                return {"success": True, "result": "\n".join(lines)}
            return {"success": False, "error": "Failed to record shaping note"}

        elif tool_name == "record_relationship_shift":
            user_id = tool_input.get("user_id") or target_user_id
            description = tool_input["description"]
            from_state = tool_input["from_state"]
            to_state = tool_input["to_state"]
            catalyst = tool_input.get("catalyst", "")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            profile = user_manager.load_profile(user_id)
            if not profile:
                return {"success": False, "error": f"User not found: {user_id}"}

            shift = user_manager.add_relationship_shift(
                user_id=user_id,
                description=description,
                from_state=from_state,
                to_state=to_state,
                catalyst=catalyst
            )

            if shift:
                return {
                    "success": True,
                    "result": f"Recorded relationship shift with {profile.display_name}:\n\n**{from_state}** → **{to_state}**\n\n{description}"
                }
            return {"success": False, "error": "Failed to record shift"}

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
                    "enum": ["interest", "preference", "communication_style", "background", "value", "relationship_dynamic", "growth", "contradiction"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of observations to return",
                    "default": 10
                }
            },
            "required": []
        }
    },
    # Structured User Model Tools
    {
        "name": "view_user_model",
        "description": "View your structured understanding of a user - their identity, values, growth edges, contradictions, and what you're still learning about them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                }
            },
            "required": []
        }
    },
    {
        "name": "view_relationship_model",
        "description": "View your model of the relationship with a user - patterns, mutual shaping, significant shifts, and how you influence each other.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                }
            },
            "required": []
        }
    },
    {
        "name": "record_identity_understanding",
        "description": "Record an understanding about who a user IS - their core identity, not just facts about them. Use for 'they are...' type insights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "statement": {
                    "type": "string",
                    "description": "An identity statement about this person (e.g., 'someone who values precision', 'a builder at heart')"
                },
                "confidence": {
                    "type": "number",
                    "description": "How confident you are (0.0-1.0)",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7
                }
            },
            "required": ["statement"]
        }
    },
    {
        "name": "record_shared_moment",
        "description": "Record a significant moment in your relationship with a user - a breakthrough, meaningful exchange, or milestone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
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
                    "description": "Type of moment",
                    "enum": ["connection", "growth", "challenge", "milestone", "ritual"],
                    "default": "connection"
                }
            },
            "required": ["description", "significance"]
        }
    },
    {
        "name": "record_user_growth",
        "description": "Record an observation about how a user is developing or changing over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "area": {
                    "type": "string",
                    "description": "What aspect they're growing in"
                },
                "observation": {
                    "type": "string",
                    "description": "What you've noticed about their growth"
                },
                "direction": {
                    "type": "string",
                    "description": "Direction of change",
                    "enum": ["growth", "regression", "shift"],
                    "default": "growth"
                }
            },
            "required": ["area", "observation"]
        }
    },
    {
        "name": "flag_user_contradiction",
        "description": "Flag an inconsistency you've noticed about a user - something they said or did that contradicts other observations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "aspect_a": {
                    "type": "string",
                    "description": "One side of the contradiction"
                },
                "aspect_b": {
                    "type": "string",
                    "description": "The other side that seems inconsistent"
                },
                "context": {
                    "type": "string",
                    "description": "When/where you noticed this (optional)"
                }
            },
            "required": ["aspect_a", "aspect_b"]
        }
    },
    {
        "name": "resolve_user_contradiction",
        "description": "Mark a flagged contradiction as resolved with an explanation of how you now understand it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "contradiction_id": {
                    "type": "string",
                    "description": "ID of the contradiction to resolve"
                },
                "resolution": {
                    "type": "string",
                    "description": "How you now understand this apparent contradiction"
                }
            },
            "required": ["contradiction_id", "resolution"]
        }
    },
    {
        "name": "add_open_question_about_user",
        "description": "Record something you're still learning or wondering about a user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "question": {
                    "type": "string",
                    "description": "What you're wondering about or trying to understand about them"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "record_relationship_pattern",
        "description": "Record a recurring pattern in your relationship with a user - a dynamic that shows up regularly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
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
                    "description": "How often it occurs",
                    "enum": ["occasional", "regular", "frequent"],
                    "default": "regular"
                },
                "valence": {
                    "type": "string",
                    "description": "Quality of this pattern",
                    "enum": ["positive", "neutral", "challenging", "mixed"],
                    "default": "positive"
                }
            },
            "required": ["name", "description"]
        }
    },
    {
        "name": "note_mutual_shaping",
        "description": "Record how you and a user influence each other - how they shape you and/or how you shape them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "how_they_shape_me": {
                    "type": "string",
                    "description": "How this person influences your development (optional)"
                },
                "how_i_shape_them": {
                    "type": "string",
                    "description": "How you influence their development (optional, observed or reported)"
                }
            },
            "required": []
        }
    },
    {
        "name": "record_relationship_shift",
        "description": "Record a significant shift in your relationship with a user - when the nature of the relationship changed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID (optional if talking to them currently)"
                },
                "description": {
                    "type": "string",
                    "description": "What shifted in the relationship"
                },
                "from_state": {
                    "type": "string",
                    "description": "What the relationship was like before"
                },
                "to_state": {
                    "type": "string",
                    "description": "What it shifted to"
                },
                "catalyst": {
                    "type": "string",
                    "description": "What triggered the shift (optional)"
                }
            },
            "required": ["description", "from_state", "to_state"]
        }
    }
]
