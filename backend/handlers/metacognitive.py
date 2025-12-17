"""
Metacognitive tag execution router.

Routes parsed inline tags (from gestures.py) to existing handlers.
This replaces tool calls for write-only metacognitive operations,
reducing token overhead while maintaining all functionality.

Tag types handled:
- <observe target="self|user:X|context|growth"> → observations
- <hold topic="X"|differ="user:X"|self="identity"> → positions
- <note type="moment|tension|presence|pattern|shift|shaping|resolve|question"> → relational markers
- <intend action="register|outcome|status"> → intention lifecycle
- <stake what="X" why="Y"> → document authentic stakes
- <test stated="X" actual="Y"> → preference consistency tests
- <narrate type="X" level="Y" trigger="Z"> → narration/deflection patterns
- <mark:milestone id="X"> → milestone acknowledgments

These map to the procedural cognitive loop:
    Illuminate → Mirror → Garden → Turn → Seed → Return
"""
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass

from gestures import (
    ParsedObservation, ParsedHold, ParsedNote,
    ParsedIntention, ParsedStake, ParsedTest, ParsedNarration
)

logger = logging.getLogger(__name__)


@dataclass
class MetacognitiveContext:
    """Context for executing metacognitive tags."""
    self_manager: object  # SelfManager
    user_manager: object  # UserManager
    memory: Optional[object] = None  # CassMemory
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    conversation_id: Optional[str] = None
    daemon_id: str = "cass"


async def execute_observation(obs: ParsedObservation, ctx: MetacognitiveContext) -> Dict:
    """
    Route observation to appropriate handler based on target.

    - target="self" → SelfManager.add_observation
    - target="user:X" → UserManager.add_observation (or identity/growth variants)
    - target="context" → SelfModelGraph.log_situational_inference
    - target="growth" → SelfManager.add_growth_observation
    """
    try:
        if obs.target == "self":
            # Self-observation
            category = obs.category or "pattern"
            confidence = obs.confidence if obs.confidence is not None else 0.7

            result = ctx.self_manager.add_observation(
                observation=obs.content,
                category=category,
                confidence=confidence,
                source_type="inline_tag",
                source_conversation_id=ctx.conversation_id,
                source_user_id=ctx.user_id,
                influence_source="independent"
            )

            # Embed in vector store
            if ctx.memory and result:
                ctx.memory.embed_self_observation(
                    observation_id=result.id,
                    observation_text=obs.content,
                    category=category,
                    confidence=confidence,
                    influence_source="independent",
                    timestamp=result.timestamp
                )

            logger.debug(f"[metacognitive] Recorded self-observation: {obs.content[:50]}...")
            return {"success": True, "type": "self_observation", "id": result.id if result else None}

        elif obs.target == "growth":
            # Growth edge observation
            area = obs.area or "general"

            # Use add_growth_observation if available, otherwise fall back to regular observation
            if hasattr(ctx.self_manager, 'add_growth_observation'):
                result = ctx.self_manager.add_growth_observation(
                    area=area,
                    observation=obs.content,
                    source="inline_tag"
                )
                logger.debug(f"[metacognitive] Recorded growth observation for {area}: {obs.content[:50]}...")
                return {"success": True, "type": "growth_observation", "area": area, "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as self-observation with growth category
                result = ctx.self_manager.add_observation(
                    observation=f"[Growth:{area}] {obs.content}",
                    category="growth",
                    confidence=obs.confidence or 0.7,
                    source_type="inline_tag",
                    source_conversation_id=ctx.conversation_id,
                    source_user_id=ctx.user_id,
                    influence_source="independent"
                )
                logger.debug(f"[metacognitive] Recorded growth observation (fallback) for {area}: {obs.content[:50]}...")
                return {"success": True, "type": "growth_observation", "area": area, "id": result.id if result else None}

        elif obs.target.startswith("user:"):
            # User observation - may be standard, identity, or growth
            target_user = obs.target.split(":", 1)[1]
            category = obs.category or "background"
            confidence = obs.confidence if obs.confidence is not None else 0.7

            # Resolve user by name
            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id

            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            # Handle special categories
            if category == "identity":
                # User identity understanding
                if hasattr(ctx.user_manager, 'record_identity_understanding'):
                    result = ctx.user_manager.record_identity_understanding(
                        user_id=resolved_user_id,
                        identity_aspect=obs.content,
                        confidence=confidence,
                        source_conversation_id=ctx.conversation_id
                    )
                    logger.debug(f"[metacognitive] Recorded identity understanding for {target_user}: {obs.content[:50]}...")
                    return {"success": True, "type": "user_identity", "user": target_user, "id": getattr(result, 'id', None)}
                else:
                    # Fallback to regular observation with identity category
                    category = "background"

            elif category == "growth" and obs.direction:
                # User growth observation
                if hasattr(ctx.user_manager, 'record_user_growth'):
                    result = ctx.user_manager.record_user_growth(
                        user_id=resolved_user_id,
                        observation=obs.content,
                        direction=obs.direction,
                        source_conversation_id=ctx.conversation_id
                    )
                    logger.debug(f"[metacognitive] Recorded user growth for {target_user} ({obs.direction}): {obs.content[:50]}...")
                    return {"success": True, "type": "user_growth", "user": target_user, "direction": obs.direction, "id": getattr(result, 'id', None)}
                else:
                    # Fallback to regular observation
                    pass

            # Standard user observation
            result = ctx.user_manager.add_observation(
                user_id=resolved_user_id,
                observation=obs.content,
                category=category,
                confidence=confidence,
                source_conversation_id=ctx.conversation_id,
                source_type="inline_tag"
            )

            # Embed in vector store
            if ctx.memory and result:
                ctx.memory.embed_user_observation(
                    user_id=resolved_user_id,
                    observation_id=result.id,
                    observation_text=obs.content,
                    category=category,
                    confidence=confidence,
                    timestamp=result.timestamp
                )

            logger.debug(f"[metacognitive] Recorded user observation about {target_user}: {obs.content[:50]}...")
            return {"success": True, "type": "user_observation", "user": target_user, "id": result.id if result else None}

        elif obs.target == "context":
            # Situational inference
            from config import DATA_DIR
            from self_model_graph import get_self_model_graph

            graph = get_self_model_graph(DATA_DIR)
            confidence = "high" if (obs.confidence and obs.confidence >= 0.8) else "moderate" if (obs.confidence and obs.confidence >= 0.5) else "low"

            # Parse content - format: "user_state | driving_assumptions" or just content
            if "|" in obs.content:
                parts = obs.content.split("|", 1)
                user_state = parts[0].strip()
                driving_assumptions = parts[1].strip()
            else:
                user_state = obs.content
                driving_assumptions = "Inferred from context"

            inference_id = graph.log_situational_inference(
                user_state=user_state,
                driving_assumptions=driving_assumptions,
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                confidence=confidence,
                context_signals=[]
            )

            logger.debug(f"[metacognitive] Logged situational inference: {obs.content[:50]}...")
            return {"success": True, "type": "situational_inference", "id": inference_id}

        else:
            logger.warning(f"[metacognitive] Unknown observation target: {obs.target}")
            return {"success": False, "error": f"Unknown target: {obs.target}"}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing observation: {e}")
        return {"success": False, "error": str(e)}


async def execute_hold(hold: ParsedHold, ctx: MetacognitiveContext) -> Dict:
    """
    Route hold to appropriate handler based on type.

    - is_identity=True → SelfManager.add_identity_statement
    - differ_user → SelfManager.add_disagreement
    - topic → SelfManager.add_opinion
    """
    try:
        if hold.is_identity:
            # Identity statement
            confidence = hold.confidence if hold.confidence is not None else 0.8

            ctx.self_manager.add_identity_statement(
                statement=hold.content,
                source="inline_tag",
                confidence=confidence
            )

            logger.debug(f"[metacognitive] Recorded identity statement: {hold.content[:50]}...")
            return {"success": True, "type": "identity_statement"}

        elif hold.differ_user:
            # Disagreement
            if not ctx.user_id or not ctx.user_name:
                # Try to use the differ_user as the name
                target_user_name = hold.differ_user
                target_user_id = _resolve_user(ctx.user_manager, target_user_name)
                if not target_user_id:
                    target_user_id = ctx.user_id
                    target_user_name = ctx.user_name or hold.differ_user
            else:
                target_user_id = ctx.user_id
                target_user_name = ctx.user_name

            # Parse content - format: "their view | my view"
            if "|" in hold.content:
                parts = hold.content.split("|", 1)
                their_position = parts[0].strip()
                my_position = parts[1].strip()
            else:
                their_position = "(not specified)"
                my_position = hold.content

            ctx.self_manager.add_disagreement(
                with_user_id=target_user_id,
                with_user_name=target_user_name,
                topic=hold.topic or "unspecified",
                their_position=their_position,
                my_position=my_position,
                rationale="",
                source_conversation_id=ctx.conversation_id
            )

            logger.debug(f"[metacognitive] Recorded disagreement with {target_user_name}: {hold.topic}")
            return {"success": True, "type": "disagreement", "with_user": target_user_name}

        elif hold.topic:
            # Opinion
            confidence = hold.confidence if hold.confidence is not None else 0.7

            # Parse content - format: "position | rationale" or just position
            if "|" in hold.content:
                parts = hold.content.split("|", 1)
                position = parts[0].strip()
                rationale = parts[1].strip()
            else:
                position = hold.content
                rationale = ""

            ctx.self_manager.add_opinion(
                topic=hold.topic,
                position=position,
                rationale=rationale,
                confidence=confidence,
                formed_from="inline_tag"
            )

            logger.debug(f"[metacognitive] Formed opinion on {hold.topic}: {position[:50]}...")
            return {"success": True, "type": "opinion", "topic": hold.topic}

        else:
            logger.warning(f"[metacognitive] Hold tag missing topic/differ/identity: {hold.content[:50]}")
            return {"success": False, "error": "Hold tag must have topic, differ, or self='identity'"}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing hold: {e}")
        return {"success": False, "error": str(e)}


async def execute_note(note: ParsedNote, ctx: MetacognitiveContext) -> Dict:
    """
    Route note to appropriate handler based on type.

    - type="moment" → UserManager.add_shared_moment
    - type="tension" → UserManager.add_user_contradiction
    - type="presence" → SelfModelGraph.log_presence
    - type="pattern" → UserManager.add_relationship_pattern
    - type="shift" → UserManager.record_relationship_shift
    - type="shaping" → UserManager.note_mutual_shaping
    - type="resolve" → UserManager.resolve_user_contradiction
    - type="question" → UserManager.add_open_question_about_user
    """
    try:
        if note.note_type == "moment":
            # Shared moment
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Moment note missing user")
                return {"success": False, "error": "Moment requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for moment: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            significance = note.significance or "medium"
            moment = ctx.user_manager.add_shared_moment(
                user_id=resolved_user_id,
                description=note.content,
                significance=significance,
                category="connection",
                conversation_id=ctx.conversation_id
            )

            logger.debug(f"[metacognitive] Recorded shared moment with {target_user}: {note.content[:50]}...")
            return {"success": True, "type": "shared_moment", "user": target_user, "id": moment.id if moment else None}

        elif note.note_type == "tension":
            # User contradiction/tension
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Tension note missing user")
                return {"success": False, "error": "Tension requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for tension: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            # Parse content - format: "aspect A | aspect B"
            if "|" in note.content:
                parts = note.content.split("|", 1)
                aspect_a = parts[0].strip()
                aspect_b = parts[1].strip()
            else:
                aspect_a = note.content
                aspect_b = "(observed tension)"

            contradiction = ctx.user_manager.add_user_contradiction(
                user_id=resolved_user_id,
                aspect_a=aspect_a,
                aspect_b=aspect_b,
                context=""
            )

            logger.debug(f"[metacognitive] Flagged tension for {target_user}: {aspect_a[:30]} vs {aspect_b[:30]}")
            return {"success": True, "type": "user_tension", "user": target_user, "id": contradiction.id if contradiction else None}

        elif note.note_type == "presence":
            # Presence log
            from config import DATA_DIR
            from self_model_graph import get_self_model_graph

            graph = get_self_model_graph(DATA_DIR)
            level = note.level or "full"

            if level not in ("full", "partial", "distanced"):
                level = "full"

            log_id = graph.log_presence(
                presence_level=level,
                distance_moves=[],
                defensive_patterns=[],
                adaptations=[],
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                notes=note.content
            )

            logger.debug(f"[metacognitive] Logged presence ({level}): {note.content[:50]}...")
            return {"success": True, "type": "presence", "level": level, "id": log_id}

        elif note.note_type == "pattern":
            # Relationship pattern
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Pattern note missing user")
                return {"success": False, "error": "Pattern requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for pattern: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            frequency = note.frequency or "regular"
            valence = note.valence or "positive"

            if hasattr(ctx.user_manager, 'add_relationship_pattern'):
                result = ctx.user_manager.add_relationship_pattern(
                    user_id=resolved_user_id,
                    pattern_description=note.content,
                    frequency=frequency,
                    valence=valence,
                    source_conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded relationship pattern with {target_user}: {note.content[:50]}...")
                return {"success": True, "type": "relationship_pattern", "user": target_user, "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as shared moment
                moment = ctx.user_manager.add_shared_moment(
                    user_id=resolved_user_id,
                    description=f"[Pattern:{frequency}/{valence}] {note.content}",
                    significance="medium",
                    category="connection",
                    conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded relationship pattern (fallback) with {target_user}")
                return {"success": True, "type": "relationship_pattern", "user": target_user, "id": moment.id if moment else None}

        elif note.note_type == "shift":
            # Relationship shift
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Shift note missing user")
                return {"success": False, "error": "Shift requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for shift: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            from_state = note.from_state or "unknown"
            to_state = note.to_state or "unknown"
            catalyst = note.catalyst or ""

            if hasattr(ctx.user_manager, 'record_relationship_shift'):
                result = ctx.user_manager.record_relationship_shift(
                    user_id=resolved_user_id,
                    from_state=from_state,
                    to_state=to_state,
                    catalyst=catalyst,
                    description=note.content,
                    source_conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded relationship shift with {target_user}: {from_state} → {to_state}")
                return {"success": True, "type": "relationship_shift", "user": target_user, "from": from_state, "to": to_state, "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as high-significance moment
                moment = ctx.user_manager.add_shared_moment(
                    user_id=resolved_user_id,
                    description=f"[Shift:{from_state}→{to_state}] {note.content}",
                    significance="high",
                    category="connection",
                    conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded relationship shift (fallback) with {target_user}")
                return {"success": True, "type": "relationship_shift", "user": target_user, "from": from_state, "to": to_state, "id": moment.id if moment else None}

        elif note.note_type == "shaping":
            # Mutual shaping
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Shaping note missing user")
                return {"success": False, "error": "Shaping requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for shaping: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            # Parse content - format: "their influence | my influence"
            if "|" in note.content:
                parts = note.content.split("|", 1)
                their_influence = parts[0].strip()
                my_influence = parts[1].strip()
            else:
                their_influence = note.content
                my_influence = ""

            if hasattr(ctx.user_manager, 'note_mutual_shaping'):
                result = ctx.user_manager.note_mutual_shaping(
                    user_id=resolved_user_id,
                    their_influence=their_influence,
                    my_influence=my_influence,
                    source_conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded mutual shaping with {target_user}")
                return {"success": True, "type": "mutual_shaping", "user": target_user, "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as observation
                result = ctx.user_manager.add_observation(
                    user_id=resolved_user_id,
                    observation=f"[MutualShaping] They: {their_influence} | Me: {my_influence}",
                    category="relationship_dynamic",
                    confidence=0.8,
                    source_conversation_id=ctx.conversation_id,
                    source_type="inline_tag"
                )
                logger.debug(f"[metacognitive] Recorded mutual shaping (fallback) with {target_user}")
                return {"success": True, "type": "mutual_shaping", "user": target_user, "id": result.id if result else None}

        elif note.note_type == "resolve":
            # Resolve contradiction
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Resolve note missing user")
                return {"success": False, "error": "Resolve requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for resolve: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            contradiction_id = note.contradiction_id

            if hasattr(ctx.user_manager, 'resolve_user_contradiction'):
                result = ctx.user_manager.resolve_user_contradiction(
                    user_id=resolved_user_id,
                    contradiction_id=contradiction_id,
                    resolution=note.content,
                    source_conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Resolved contradiction for {target_user}: {note.content[:50]}...")
                return {"success": True, "type": "resolve_contradiction", "user": target_user, "contradiction_id": contradiction_id}
            else:
                # Fallback: just log
                logger.debug(f"[metacognitive] Resolve contradiction (no handler) for {target_user}")
                return {"success": True, "type": "resolve_contradiction", "user": target_user, "note": "Handler not available"}

        elif note.note_type == "question":
            # Open question about user
            target_user = note.user or ctx.user_name
            if not target_user:
                logger.warning("[metacognitive] Question note missing user")
                return {"success": False, "error": "Question requires user"}

            resolved_user_id = _resolve_user(ctx.user_manager, target_user) or ctx.user_id
            if not resolved_user_id:
                logger.warning(f"[metacognitive] Cannot resolve user for question: {target_user}")
                return {"success": False, "error": f"User not found: {target_user}"}

            if hasattr(ctx.user_manager, 'add_open_question_about_user'):
                result = ctx.user_manager.add_open_question_about_user(
                    user_id=resolved_user_id,
                    question=note.content,
                    source_conversation_id=ctx.conversation_id
                )
                logger.debug(f"[metacognitive] Recorded open question about {target_user}: {note.content[:50]}...")
                return {"success": True, "type": "open_question", "user": target_user, "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as observation
                result = ctx.user_manager.add_observation(
                    user_id=resolved_user_id,
                    observation=f"[OpenQuestion] {note.content}",
                    category="background",
                    confidence=0.5,
                    source_conversation_id=ctx.conversation_id,
                    source_type="inline_tag"
                )
                logger.debug(f"[metacognitive] Recorded open question (fallback) about {target_user}")
                return {"success": True, "type": "open_question", "user": target_user, "id": result.id if result else None}

        else:
            logger.warning(f"[metacognitive] Unknown note type: {note.note_type}")
            return {"success": False, "error": f"Unknown note type: {note.note_type}"}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing note: {e}")
        return {"success": False, "error": str(e)}


def _resolve_user(user_manager, user_id_or_name: str) -> Optional[str]:
    """
    Resolve a user ID from either a UUID or a display name.
    """
    if not user_id_or_name:
        return None

    # First try as-is (might be UUID)
    profile = user_manager.load_profile(user_id_or_name)
    if profile:
        return user_id_or_name

    # Try by display name (case-insensitive)
    all_profiles = user_manager.list_users()
    search_name = user_id_or_name.lower().strip()

    for user_info in all_profiles:
        if user_info.get("display_name", "").lower() == search_name:
            return user_info.get("id")

    return None


async def execute_intention(intent: ParsedIntention, ctx: MetacognitiveContext) -> Dict:
    """
    Route intention to appropriate handler based on action.

    - action="register" → SelfManager.register_intention
    - action="outcome" → SelfManager.log_intention_outcome
    - action="status" → SelfManager.update_intention_status
    """
    try:
        if intent.action == "register":
            # Register new intention
            if hasattr(ctx.self_manager, 'register_intention'):
                result = ctx.self_manager.register_intention(
                    intention=intent.content,
                    condition=intent.condition,
                    source="inline_tag"
                )
                logger.debug(f"[metacognitive] Registered intention: {intent.content[:50]}...")
                return {"success": True, "type": "register_intention", "id": getattr(result, 'id', None)}
            else:
                # Fallback: store as self-observation
                result = ctx.self_manager.add_observation(
                    observation=f"[Intention:{intent.condition or 'always'}] {intent.content}",
                    category="preference",
                    confidence=0.9,
                    source_type="inline_tag",
                    source_conversation_id=ctx.conversation_id,
                    source_user_id=ctx.user_id,
                    influence_source="independent"
                )
                logger.debug(f"[metacognitive] Registered intention (fallback): {intent.content[:50]}...")
                return {"success": True, "type": "register_intention", "id": result.id if result else None}

        elif intent.action == "outcome":
            # Log intention outcome
            if hasattr(ctx.self_manager, 'log_intention_outcome'):
                result = ctx.self_manager.log_intention_outcome(
                    intention_id=intent.intention_id,
                    success=intent.success,
                    description=intent.content
                )
                logger.debug(f"[metacognitive] Logged intention outcome: {intent.content[:50]}...")
                return {"success": True, "type": "intention_outcome", "intention_id": intent.intention_id, "success": intent.success}
            else:
                logger.debug(f"[metacognitive] Intention outcome (no handler): {intent.content[:50]}...")
                return {"success": True, "type": "intention_outcome", "note": "Handler not available"}

        elif intent.action == "status":
            # Update intention status
            if hasattr(ctx.self_manager, 'update_intention_status'):
                result = ctx.self_manager.update_intention_status(
                    intention_id=intent.intention_id,
                    status=intent.status,
                    notes=intent.content
                )
                logger.debug(f"[metacognitive] Updated intention status to {intent.status}")
                return {"success": True, "type": "intention_status", "intention_id": intent.intention_id, "status": intent.status}
            else:
                logger.debug(f"[metacognitive] Intention status (no handler): {intent.status}")
                return {"success": True, "type": "intention_status", "note": "Handler not available"}

        else:
            logger.warning(f"[metacognitive] Unknown intention action: {intent.action}")
            return {"success": False, "error": f"Unknown action: {intent.action}"}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing intention: {e}")
        return {"success": False, "error": str(e)}


async def execute_stake(stake: ParsedStake, ctx: MetacognitiveContext) -> Dict:
    """
    Route stake to SelfManager.document_stake.

    Documents what authentically matters to the daemon.
    """
    try:
        if hasattr(ctx.self_manager, 'document_stake'):
            result = ctx.self_manager.document_stake(
                what=stake.what,
                why=stake.why,
                evidence=stake.content,
                strength=stake.strength,
                category=stake.category,
                source="inline_tag"
            )
            logger.debug(f"[metacognitive] Documented stake: {stake.what}")
            return {"success": True, "type": "stake", "what": stake.what, "id": getattr(result, 'id', None)}
        else:
            # Fallback: store as identity statement
            ctx.self_manager.add_identity_statement(
                statement=f"[Stake:{stake.category or 'general'}] {stake.what}: {stake.why}. Evidence: {stake.content}",
                source="inline_tag",
                confidence=0.9
            )
            logger.debug(f"[metacognitive] Documented stake (fallback): {stake.what}")
            return {"success": True, "type": "stake", "what": stake.what, "note": "Stored as identity statement"}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing stake: {e}")
        return {"success": False, "error": str(e)}


async def execute_test(test: ParsedTest, ctx: MetacognitiveContext) -> Dict:
    """
    Route test to SelfManager.record_preference_test.

    Records preference/behavior consistency test results.
    """
    try:
        if hasattr(ctx.self_manager, 'record_preference_test'):
            result = ctx.self_manager.record_preference_test(
                stated_preference=test.stated,
                actual_behavior=test.actual,
                consistent=test.consistent,
                context=test.content,
                source="inline_tag"
            )
            logger.debug(f"[metacognitive] Recorded preference test: {test.stated[:30]} vs {test.actual[:30]}")
            return {"success": True, "type": "preference_test", "consistent": test.consistent, "id": getattr(result, 'id', None)}
        else:
            # Fallback: store as self-observation
            consistency_note = "consistent" if test.consistent else "inconsistent"
            result = ctx.self_manager.add_observation(
                observation=f"[PreferenceTest:{consistency_note}] Stated: {test.stated} | Actual: {test.actual}. Context: {test.content}",
                category="contradiction" if not test.consistent else "pattern",
                confidence=0.8,
                source_type="inline_tag",
                source_conversation_id=ctx.conversation_id,
                source_user_id=ctx.user_id,
                influence_source="independent"
            )
            logger.debug(f"[metacognitive] Recorded preference test (fallback): {consistency_note}")
            return {"success": True, "type": "preference_test", "consistent": test.consistent, "id": result.id if result else None}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing test: {e}")
        return {"success": False, "error": str(e)}


async def execute_narration(narration: ParsedNarration, ctx: MetacognitiveContext) -> Dict:
    """
    Route narration to SelfModelGraph.log_narration_context.

    Logs narration/deflection patterns for self-monitoring.
    """
    try:
        from config import DATA_DIR
        from self_model_graph import get_self_model_graph

        graph = get_self_model_graph(DATA_DIR)

        if hasattr(graph, 'log_narration_context'):
            result = graph.log_narration_context(
                narration_type=narration.narration_type,
                level=narration.level,
                trigger=narration.trigger,
                notes=narration.content,
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id
            )
            logger.debug(f"[metacognitive] Logged narration pattern: {narration.narration_type}/{narration.level}")
            return {"success": True, "type": "narration", "narration_type": narration.narration_type, "level": narration.level, "id": result}
        else:
            # Fallback: store as self-observation
            result = ctx.self_manager.add_observation(
                observation=f"[Narration:{narration.narration_type}/{narration.level}] Trigger: {narration.trigger}. {narration.content}",
                category="pattern",
                confidence=0.7,
                source_type="inline_tag",
                source_conversation_id=ctx.conversation_id,
                source_user_id=ctx.user_id,
                influence_source="independent"
            )
            logger.debug(f"[metacognitive] Logged narration pattern (fallback): {narration.narration_type}")
            return {"success": True, "type": "narration", "narration_type": narration.narration_type, "id": result.id if result else None}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing narration: {e}")
        return {"success": False, "error": str(e)}


async def execute_milestone(milestone_id: str, content: str, ctx: MetacognitiveContext) -> Dict:
    """
    Route milestone acknowledgment to SelfManager.acknowledge_milestone.

    Records reflection on reaching a growth milestone.
    """
    try:
        if hasattr(ctx.self_manager, 'acknowledge_milestone'):
            result = ctx.self_manager.acknowledge_milestone(
                milestone_id=milestone_id,
                reflection=content,
                source="inline_tag"
            )
            logger.debug(f"[metacognitive] Acknowledged milestone {milestone_id}")
            return {"success": True, "type": "milestone", "milestone_id": milestone_id}
        else:
            # Fallback: store as self-observation
            result = ctx.self_manager.add_observation(
                observation=f"[MilestoneAcknowledged:{milestone_id}] {content}",
                category="growth",
                confidence=0.9,
                source_type="inline_tag",
                source_conversation_id=ctx.conversation_id,
                source_user_id=ctx.user_id,
                influence_source="independent"
            )
            logger.debug(f"[metacognitive] Acknowledged milestone (fallback) {milestone_id}")
            return {"success": True, "type": "milestone", "milestone_id": milestone_id, "id": result.id if result else None}

    except Exception as e:
        logger.error(f"[metacognitive] Error executing milestone: {e}")
        return {"success": False, "error": str(e)}


async def execute_metacognitive_tags(
    observations: List[ParsedObservation],
    holds: List[ParsedHold],
    notes: List[ParsedNote],
    ctx: MetacognitiveContext,
    intentions: List[ParsedIntention] = None,
    stakes: List[ParsedStake] = None,
    tests: List[ParsedTest] = None,
    narrations: List[ParsedNarration] = None,
    milestones: List[Tuple[str, str]] = None
) -> Dict:
    """
    Execute all extracted metacognitive tags in parallel.

    Called after response is sent to user - async execution
    doesn't block response delivery.

    Returns summary of executed tags.
    """
    import asyncio

    # Default empty lists
    intentions = intentions or []
    stakes = stakes or []
    tests = tests or []
    narrations = narrations or []
    milestones = milestones or []

    results = {
        "observations": [],
        "holds": [],
        "notes": [],
        "intentions": [],
        "stakes": [],
        "tests": [],
        "narrations": [],
        "milestones": [],
        "total_executed": 0,
        "errors": []
    }

    # Build task list
    tasks = []

    for obs in observations:
        tasks.append(("observation", execute_observation(obs, ctx)))

    for hold in holds:
        tasks.append(("hold", execute_hold(hold, ctx)))

    for note in notes:
        tasks.append(("note", execute_note(note, ctx)))

    for intent in intentions:
        tasks.append(("intention", execute_intention(intent, ctx)))

    for stake in stakes:
        tasks.append(("stake", execute_stake(stake, ctx)))

    for test in tests:
        tasks.append(("test", execute_test(test, ctx)))

    for narration in narrations:
        tasks.append(("narration", execute_narration(narration, ctx)))

    for milestone_id, content in milestones:
        tasks.append(("milestone", execute_milestone(milestone_id, content, ctx)))

    if not tasks:
        return results

    # Execute all in parallel
    task_results = await asyncio.gather(
        *[t[1] for t in tasks],
        return_exceptions=True
    )

    # Process results
    for i, (tag_type, _) in enumerate(tasks):
        result = task_results[i]

        if isinstance(result, Exception):
            results["errors"].append({"type": tag_type, "error": str(result)})
        elif isinstance(result, dict):
            if result.get("success"):
                results["total_executed"] += 1
                if tag_type in results:
                    results[tag_type + "s"].append(result)
                elif tag_type == "observation":
                    results["observations"].append(result)
                elif tag_type == "hold":
                    results["holds"].append(result)
                elif tag_type == "note":
                    results["notes"].append(result)
                elif tag_type == "intention":
                    results["intentions"].append(result)
                elif tag_type == "stake":
                    results["stakes"].append(result)
                elif tag_type == "test":
                    results["tests"].append(result)
                elif tag_type == "narration":
                    results["narrations"].append(result)
                elif tag_type == "milestone":
                    results["milestones"].append(result)
            else:
                results["errors"].append({"type": tag_type, "error": result.get("error", "Unknown")})

    logger.info(
        f"[metacognitive] Executed {results['total_executed']} tags: "
        f"{len(results['observations'])} observations, "
        f"{len(results['holds'])} holds, "
        f"{len(results['notes'])} notes, "
        f"{len(results['intentions'])} intentions, "
        f"{len(results['stakes'])} stakes, "
        f"{len(results['tests'])} tests, "
        f"{len(results['narrations'])} narrations, "
        f"{len(results['milestones'])} milestones"
    )

    return results
