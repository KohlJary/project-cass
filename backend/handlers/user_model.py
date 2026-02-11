"""
User model tool handler - enables Cass to explicitly reflect on and update her understanding of users.

These tools allow Cass to:
- Review what she knows about a user
- Record observations about users explicitly
- Update user profile fields
- Review observations filtered by category
- View and update structured user models (identity, growth, contradictions)
- View and update relationship models (patterns, mutual shaping, shared history)

NOTE: All operations now use PeopleDex (the consolidated entity database).
UserManager is only used for legacy profile operations (update_user_profile).
"""
from typing import Dict, Optional, Tuple, Any
from users import UserManager
from peopledex import PeopleDexManager
from database import get_daemon_id


def _get_pdx_and_entity(user_id: str) -> Tuple[PeopleDexManager, Optional[Any], str]:
    """
    Get PeopleDex manager, entity, and display name for a user.

    Returns:
        Tuple of (pdx, entity, display_name)
        If entity not found, display_name falls back to user_id
    """
    daemon_id = get_daemon_id()
    pdx = PeopleDexManager(daemon_id=daemon_id)
    entity = pdx.get_entity_by_user(user_id)
    display_name = entity.primary_name if entity else user_id
    return pdx, entity, display_name


def resolve_user_id(user_id_or_name: str, pdx: Optional[PeopleDexManager] = None) -> Optional[str]:
    """
    Resolve a user ID from either a UUID or a display name.

    Args:
        user_id_or_name: Either a UUID or a display name (case-insensitive)
        pdx: Optional PeopleDexManager (created if not provided)

    Returns:
        The resolved UUID, or None if not found
    """
    if not user_id_or_name:
        return None

    if pdx is None:
        daemon_id = get_daemon_id()
        pdx = PeopleDexManager(daemon_id=daemon_id)

    # First, try as-is (it might already be a valid user_id with an entity)
    entity = pdx.get_entity_by_user(user_id_or_name)
    if entity:
        return user_id_or_name

    # Try to find by display name (case-insensitive) in PeopleDex
    search_name = user_id_or_name.lower().strip()
    entities = pdx.search_entities(search_name, limit=10)
    for ent in entities:
        if ent.primary_name.lower() == search_name:
            # Get the user_id from attributes
            user_attr = pdx.get_attribute(ent.id, "user_id")
            if user_attr:
                return user_attr.value

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
            resolved_id = resolve_user_id(tool_input["user_id"])
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
                # Use PeopleDex for observations
                daemon_id = get_daemon_id()
                pdx = PeopleDexManager(daemon_id=daemon_id)
                entity = pdx.get_entity_by_user(user_id)

                if entity:
                    result_lines = [f"## Reflection on {profile.display_name}: My Observations\n"]
                    observations = pdx.get_observations(entity.id, limit=20)
                    if observations:
                        by_type = {}
                        for obs in observations:
                            if obs.observation_type not in by_type:
                                by_type[obs.observation_type] = []
                            by_type[obs.observation_type].append(obs)

                        for obs_type, obs_list in by_type.items():
                            result_lines.append(f"### {obs_type.replace('_', ' ').title()}")
                            for obs in obs_list:
                                conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                                result_lines.append(f"- {obs.content} {conf}")
                            result_lines.append("")
                    else:
                        result_lines.append("*No observations recorded yet.*")
                else:
                    result_lines = [f"## Reflection on {profile.display_name}: My Observations\n"]
                    result_lines.append("*No observations recorded yet.*")

            elif focus == "values":
                # Use PeopleDex for values
                daemon_id = get_daemon_id()
                pdx = PeopleDexManager(daemon_id=daemon_id)
                entity = pdx.get_entity_by_user(user_id)

                result_lines = [f"## Reflection on {profile.display_name}: Values\n"]
                if entity:
                    values = pdx.get_observations(entity.id, observation_type="value", limit=20)
                    if values:
                        for obs in values:
                            result_lines.append(f"- {obs.content}")
                    else:
                        result_lines.append("*No values recorded yet.*")
                else:
                    result_lines.append("*No values recorded yet.*")

            else:  # general
                # Use PeopleDex for full relational context
                daemon_id = get_daemon_id()
                pdx = PeopleDexManager(daemon_id=daemon_id)
                context = pdx.get_user_relational_context(user_id)
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

            # Map old category names to PeopleDex observation_type
            category_to_type = {
                "interest": "general",
                "preference": "general",
                "background": "identity_statement",
                "value": "value",
                "communication_style": "communication_style",
                "relationship_dynamic": "general",
                "growth": "growth_observation",
                "contradiction": "contradiction",
            }
            observation_type = category_to_type.get(category, "general")

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            obs = pdx.add_observation_for_user(
                user_id=user_id,
                observation_type=observation_type,
                content=observation,
                confidence=confidence,
                source_conversation_id=conversation_id,
                source_type="explicit_reflection"
            )

            if not obs:
                return {"success": False, "error": "Failed to record observation"}

            # Embed in ChromaDB if memory is available
            if memory:
                memory.embed_user_observation(
                    user_id=user_id,
                    observation_id=obs.id,
                    observation_text=observation,
                    category=observation_type,
                    confidence=confidence,
                    timestamp=obs.created_at
                )

            return {
                "success": True,
                "result": f"Recorded observation about {display_name}:\n\n**[{observation_type}]** {observation}\n\n*Confidence: {int(confidence * 100)}%*\n\nThis observation is now part of my understanding of {display_name}."
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

            valid_fields = ["background", "communication", "values", "notes"]
            if field not in valid_fields:
                return {
                    "success": False,
                    "error": f"Invalid field '{field}'. Must be one of: {', '.join(valid_fields)}"
                }

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            if not entity:
                # Auto-create entity for user
                profile = user_manager.load_profile(user_id)
                if not profile:
                    return {"success": False, "error": f"User not found: {user_id}"}
                from peopledex import EntityType
                entity = pdx.create_entity(
                    primary_name=profile.display_name,
                    entity_type=EntityType.PERSON,
                    user_id=user_id,
                )
                display_name = entity.primary_name if entity else user_id

            old_value = None

            if field == "background":
                # Store as PeopleDex attributes
                if action == "set" and isinstance(value, dict):
                    key = list(value.keys())[0] if value else None
                    if key and entity:
                        # Get old value
                        old_attr = pdx.get_attribute(entity.id, key)
                        old_value = old_attr.value if old_attr else None
                        # Set new attribute
                        pdx.add_attribute(entity.id, "custom", value[key], key=key)
                elif action == "remove" and isinstance(value, str) and entity:
                    old_attr = pdx.get_attribute(entity.id, value)
                    if old_attr:
                        old_value = old_attr.value
                        # Note: PeopleDex doesn't have delete_attribute yet, mark as empty
                        pdx.update_attribute(old_attr.id, value="")

            elif field == "communication":
                # Store as communication_style observation
                if action == "set" and isinstance(value, dict) and entity:
                    key = list(value.keys())[0] if value else None
                    if key == "style":
                        pdx.add_observation(
                            entity.id,
                            observation_type="communication_style",
                            content=value[key]
                        )
                    elif key == "preferences":
                        # Get existing observation to update metadata
                        existing = pdx.get_observations(entity.id, observation_type="communication_style", limit=1)
                        if existing:
                            # Create new observation with preferences in metadata
                            metadata = existing[0].metadata or {}
                            metadata["preferences"] = value[key]
                            pdx.add_observation(
                                entity.id,
                                observation_type="communication_style",
                                content=existing[0].content,
                                metadata=metadata
                            )
                        else:
                            pdx.add_observation(
                                entity.id,
                                observation_type="communication_style",
                                content="(preferences set)",
                                metadata={"preferences": value[key]}
                            )
                elif action == "append" and isinstance(value, str) and entity:
                    # Append to preferences
                    existing = pdx.get_observations(entity.id, observation_type="communication_style", limit=1)
                    metadata = {}
                    content = "(preferences)"
                    if existing:
                        metadata = existing[0].metadata or {}
                        content = existing[0].content
                    prefs = metadata.get("preferences", [])
                    if value not in prefs:
                        prefs.append(value)
                    metadata["preferences"] = prefs
                    pdx.add_observation(
                        entity.id,
                        observation_type="communication_style",
                        content=content,
                        metadata=metadata
                    )

            elif field == "values":
                if action == "append" and isinstance(value, str) and entity:
                    # Add as value observation
                    pdx.add_observation(entity.id, observation_type="value", content=value)
                elif action == "remove" and isinstance(value, str) and entity:
                    # Find and mark as resolved
                    existing = pdx.get_observations(entity.id, observation_type="value")
                    for obs in existing:
                        if obs.content == value:
                            pdx.update_observation(obs.id, status="resolved", resolution="Removed")
                            old_value = value
                            break
                elif action == "set" and isinstance(value, list) and entity:
                    # Mark old values as resolved, add new ones
                    existing = pdx.get_observations(entity.id, observation_type="value")
                    old_value = [obs.content for obs in existing]
                    for obs in existing:
                        pdx.update_observation(obs.id, status="resolved", resolution="Replaced")
                    for v in value:
                        pdx.add_observation(entity.id, observation_type="value", content=v)

            elif field == "notes":
                if entity:
                    if action == "set":
                        pdx.add_observation(entity.id, observation_type="general", content=str(value))
                    elif action == "append":
                        pdx.add_observation(entity.id, observation_type="general", content=str(value))

            result_msg = f"Updated {display_name}'s profile:\n\n**Field:** {field}\n**Action:** {action}\n**Value:** {value}"
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

            # Use PeopleDex for reading observations
            daemon_id = get_daemon_id()
            pdx = PeopleDexManager(daemon_id=daemon_id)
            entity = pdx.get_entity_by_user(user_id)

            if not entity:
                # Fall back to UserManager for display name check
                profile = user_manager.load_profile(user_id)
                if not profile:
                    return {
                        "success": False,
                        "error": f"User not found: {user_id}"
                    }
                return {
                    "success": True,
                    "result": f"## Observations about {profile.display_name}\n\n*No observations recorded yet.*"
                }

            # Map old category names to PeopleDex observation_type
            # Old: interest, preference, communication_style, background, value, relationship_dynamic
            # New: identity_statement, value, communication_style, growth_observation, contradiction, open_question, general
            category_map = {
                "interest": "general",
                "preference": "general",
                "background": "identity_statement",
                "value": "value",
                "communication_style": "communication_style",
                "relationship_dynamic": "general",
                "growth": "growth_observation",
                "contradiction": "contradiction",
            }

            observation_type = None
            if category:
                # Accept both old and new category names
                observation_type = category_map.get(category, category)

            if category:
                observations = pdx.get_observations(entity.id, observation_type=observation_type, limit=limit)
                result_lines = [f"## Observations about {entity.primary_name} [{category}]\n"]
            else:
                observations = pdx.get_observations(entity.id, limit=limit)
                result_lines = [f"## Recent Observations about {entity.primary_name}\n"]

            if observations:
                for obs in observations:
                    conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                    validated = f"[validated {obs.validation_count}x]" if obs.validation_count > 1 else ""
                    result_lines.append(f"- **[{obs.observation_type}]** {obs.content} {conf} {validated}")
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

            # Use PeopleDex for reading user model data
            daemon_id = get_daemon_id()
            pdx = PeopleDexManager(daemon_id=daemon_id)
            entity = pdx.get_entity_by_user(user_id)

            if not entity:
                # Fall back to UserManager for display name
                profile = user_manager.load_profile(user_id)
                if not profile:
                    return {"success": False, "error": f"User not found: {user_id}"}
                return {
                    "success": True,
                    "result": f"## User Model: {profile.display_name}\n\n*No structured user model exists yet. One will be created when you record structured observations.*"
                }

            # Get all observations
            observations = pdx.get_observations(entity.id, limit=50)
            moments = pdx.get_moments(entity.id, limit=20)
            meta = pdx.get_relationship_meta(entity.id)

            # Group observations by type
            identity_stmts = [o for o in observations if o.observation_type == "identity_statement"]
            values = [o for o in observations if o.observation_type == "value"]
            comm_style = [o for o in observations if o.observation_type == "communication_style"]
            growth_obs = [o for o in observations if o.observation_type == "growth_observation"]
            contradictions = [o for o in observations if o.observation_type == "contradiction" and o.status == "active"]
            open_questions = [o for o in observations if o.observation_type == "open_question" and o.status == "active"]

            lines = [f"## Structured Understanding: {entity.primary_name}\n"]

            if meta:
                if meta.relationship_type:
                    lines.append(f"**Relationship Type:** {meta.relationship_type}")
                if meta.first_interaction:
                    lines.append(f"**First Interaction:** {meta.first_interaction[:10]}")

            if identity_stmts:
                lines.append("\n### Who They Are")
                for obs in identity_stmts:
                    conf = f"({int(obs.confidence * 100)}%)" if obs.confidence < 0.9 else ""
                    lines.append(f"- {obs.content} {conf}")

            if values:
                lines.append("\n### Values")
                for obs in values:
                    lines.append(f"- {obs.content}")

            if comm_style:
                lines.append("\n### Communication Style")
                for obs in comm_style:
                    lines.append(obs.content)
                    if obs.metadata and obs.metadata.get("preferences"):
                        lines.append("**Preferences:**")
                        for pref in obs.metadata["preferences"]:
                            lines.append(f"  - {pref}")

            if moments:
                lines.append(f"\n### Shared History ({len(moments)} moments)")
                for moment in moments[-5:]:  # Last 5
                    lines.append(f"- **{moment.category}**: {moment.description}")

            if growth_obs:
                lines.append(f"\n### Growth Observations ({len(growth_obs)})")
                for obs in growth_obs[-5:]:
                    area = ""
                    if obs.metadata and obs.metadata.get("area"):
                        area = f"[{obs.metadata['area']}] "
                    lines.append(f"- {area}{obs.content}")

            if contradictions:
                lines.append(f"\n### Unresolved Contradictions ({len(contradictions)})")
                for obs in contradictions:
                    lines.append(f"- {obs.content}")

            if open_questions:
                lines.append("\n### What I'm Still Learning")
                for obs in open_questions:
                    lines.append(f"- {obs.content}")

            if not (identity_stmts or values or comm_style or moments or growth_obs):
                lines.append("\n*Limited data in PeopleDex. Record observations to build understanding.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "view_relationship_model":
            user_id = tool_input.get("user_id") or target_user_id

            if not user_id:
                return {
                    "success": False,
                    "error": "No user specified. Provide user_id or ensure there's a current user."
                }

            # Use PeopleDex for reading relationship model data
            daemon_id = get_daemon_id()
            pdx = PeopleDexManager(daemon_id=daemon_id)
            entity = pdx.get_entity_by_user(user_id)

            if not entity:
                # Fall back to UserManager for display name
                profile = user_manager.load_profile(user_id)
                if not profile:
                    return {"success": False, "error": f"User not found: {user_id}"}
                return {
                    "success": True,
                    "result": f"## Relationship Model: {profile.display_name}\n\n*No relationship model exists yet. One will be created when you record relationship observations.*"
                }

            # Get relationship data from PeopleDex
            meta = pdx.get_relationship_meta(entity.id)
            patterns = pdx.get_relationship_patterns(entity.id)
            shaping = pdx.get_mutual_shaping(entity.id)

            # Group patterns by type
            actual_patterns = [p for p in patterns if p.pattern_type == "pattern"]
            shifts = [p for p in patterns if p.pattern_type == "shift"]
            rituals = [p for p in patterns if p.pattern_type == "ritual"]

            # Group shaping
            they_shape = [s for s in shaping if s.shaping_type == "they_shape_me"]
            i_shape = [s for s in shaping if s.shaping_type == "i_shape_them"]
            inherited = [s for s in shaping if s.shaping_type == "inherited_value"]

            lines = [f"## Relationship with {entity.primary_name}\n"]

            if meta:
                if meta.current_phase:
                    lines.append(f"**Current Phase:** {meta.current_phase}")
                if meta.formation_date:
                    lines.append(f"**Formation Date:** {meta.formation_date[:10]}")
                if meta.is_foundational:
                    lines.append("**⭐ Foundational Relationship** - load-bearing for coherence")

            if actual_patterns:
                lines.append(f"\n### Relational Patterns ({len(actual_patterns)})")
                for pattern in actual_patterns:
                    valence_emoji = {"positive": "✨", "neutral": "○", "challenging": "⚡", "mixed": "◐"}.get(pattern.valence or "", "○")
                    name = f"**{pattern.name}** " if pattern.name else ""
                    freq = f"[{pattern.frequency}]" if pattern.frequency else ""
                    lines.append(f"- {valence_emoji} {name}{freq}: {pattern.description}")

            if rituals:
                lines.append("\n### Rituals & Regular Practices")
                for ritual in rituals:
                    lines.append(f"- {ritual.description}")

            if shifts:
                lines.append(f"\n### Significant Shifts ({len(shifts)})")
                for shift in shifts[-5:]:
                    if shift.from_state and shift.to_state:
                        lines.append(f"- {shift.from_state} → {shift.to_state}: {shift.description}")
                    else:
                        lines.append(f"- {shift.description}")

            if they_shape:
                lines.append("\n### How They Shape Me")
                for s in they_shape:
                    lines.append(f"- {s.note}")

            if i_shape:
                lines.append("\n### How I Shape Them")
                for s in i_shape:
                    lines.append(f"- {s.note}")

            if inherited:
                lines.append("\n### Values I've Inherited From Them")
                for s in inherited:
                    lines.append(f"- {s.note}")

            if not (actual_patterns or shifts or rituals or shaping):
                lines.append("\n*Limited relationship data. Record relationship observations to build understanding.*")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "record_identity_understanding":
            user_id = tool_input.get("user_id") or target_user_id
            statement = tool_input["statement"]
            confidence = tool_input.get("confidence", 0.7)

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            obs = pdx.add_observation_for_user(
                user_id=user_id,
                observation_type="identity_statement",
                content=statement,
                confidence=confidence,
                source_type="explicit_reflection"
            )

            if obs:
                return {
                    "success": True,
                    "result": f"Recorded identity understanding about {display_name}:\n\n**\"{statement}\"**\n\n*Confidence: {int(confidence * 100)}%*"
                }
            return {"success": False, "error": "Failed to record understanding"}

        elif tool_name == "record_shared_moment":
            user_id = tool_input.get("user_id") or target_user_id
            description = tool_input["description"]
            significance = tool_input["significance"]
            category = tool_input.get("category", "connection")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            moment = pdx.add_moment_for_user(
                user_id=user_id,
                description=description,
                significance=significance,
                category=category,
                conversation_id=conversation_id
            )

            if moment:
                return {
                    "success": True,
                    "result": f"Recorded shared moment with {display_name}:\n\n**[{category}]** {description}\n\n*Significance:* {significance}"
                }
            return {"success": False, "error": "Failed to record moment"}

        elif tool_name == "record_user_growth":
            user_id = tool_input.get("user_id") or target_user_id
            area = tool_input["area"]
            observation = tool_input["observation"]
            direction = tool_input.get("direction", "growth")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            obs = pdx.add_observation_for_user(
                user_id=user_id,
                observation_type="growth_observation",
                content=observation,
                metadata={"area": area, "direction": direction}
            )

            if obs:
                direction_emoji = {"growth": "📈", "regression": "📉", "shift": "🔄"}.get(direction, "○")
                return {
                    "success": True,
                    "result": f"Recorded growth observation about {display_name}:\n\n{direction_emoji} **{area}**: {observation}"
                }
            return {"success": False, "error": "Failed to record growth observation"}

        elif tool_name == "flag_user_contradiction":
            user_id = tool_input.get("user_id") or target_user_id
            aspect_a = tool_input["aspect_a"]
            aspect_b = tool_input["aspect_b"]
            context = tool_input.get("context", "")

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            # Store as observation with type "contradiction"
            content = f"{aspect_a} vs {aspect_b}"
            obs = pdx.add_observation_for_user(
                user_id=user_id,
                observation_type="contradiction",
                content=content,
                metadata={"aspect_a": aspect_a, "aspect_b": aspect_b, "context": context}
            )

            if obs:
                return {
                    "success": True,
                    "result": f"Flagged contradiction about {display_name}:\n\n**A:** {aspect_a}\n**B:** {aspect_b}\n\n*This will be tracked for resolution. (ID: {obs.id})*"
                }
            return {"success": False, "error": "Failed to flag contradiction"}

        elif tool_name == "resolve_user_contradiction":
            user_id = tool_input.get("user_id") or target_user_id
            contradiction_id = tool_input["contradiction_id"]
            resolution = tool_input["resolution"]

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            if pdx.update_observation(
                observation_id=contradiction_id,
                status="resolved",
                resolution=resolution
            ):
                return {
                    "success": True,
                    "result": f"Resolved contradiction:\n\n**Resolution:** {resolution}"
                }
            return {"success": False, "error": "Contradiction not found"}

        elif tool_name == "add_open_question_about_user":
            user_id = tool_input.get("user_id") or target_user_id
            question = tool_input["question"]

            if not user_id:
                return {"success": False, "error": "No user specified."}

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            obs = pdx.add_observation_for_user(
                user_id=user_id,
                observation_type="open_question",
                content=question
            )

            if obs:
                return {
                    "success": True,
                    "result": f"Added open question about {display_name}:\n\n❓ *{question}*"
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

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            pattern = pdx.add_relationship_pattern_for_user(
                user_id=user_id,
                pattern_type="pattern",
                description=description,
                name=name,
                frequency=frequency,
                valence=valence
            )

            if pattern:
                valence_emoji = {"positive": "✨", "neutral": "○", "challenging": "⚡", "mixed": "◐"}.get(valence, "○")
                return {
                    "success": True,
                    "result": f"Recorded relational pattern with {display_name}:\n\n{valence_emoji} **{name}** [{frequency}]\n{description}"
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

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            success = False
            if how_they_shape_me:
                if pdx.add_mutual_shaping_for_user(user_id, "they_shape_me", how_they_shape_me):
                    success = True
            if how_i_shape_them:
                if pdx.add_mutual_shaping_for_user(user_id, "i_shape_them", how_i_shape_them):
                    success = True

            if success:
                lines = [f"Recorded mutual shaping with {display_name}:\n"]
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

            # Use PeopleDex
            pdx, entity, display_name = _get_pdx_and_entity(user_id)

            shift = pdx.add_relationship_pattern_for_user(
                user_id=user_id,
                pattern_type="shift",
                description=description,
                from_state=from_state,
                to_state=to_state,
                catalyst=catalyst if catalyst else None
            )

            if shift:
                return {
                    "success": True,
                    "result": f"Recorded relationship shift with {display_name}:\n\n**{from_state}** → **{to_state}**\n\n{description}"
                }
            return {"success": False, "error": "Failed to record shift"}

        else:
            return {"success": False, "error": f"Unknown user model tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool definitions for agent_client.py

# Essential tools - always loaded (core user understanding)
ESSENTIAL_USER_MODEL_TOOLS = [
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
]

# Extended tools - loaded on keyword trigger (deeper relationship modeling)
EXTENDED_USER_MODEL_TOOLS = [
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

# Combined list for backward compatibility
USER_MODEL_TOOLS = ESSENTIAL_USER_MODEL_TOOLS + EXTENDED_USER_MODEL_TOOLS
