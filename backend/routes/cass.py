"""
Cass Self-Model API Routes

Extracted from main_sdk.py as part of Phase 2 refactoring.
Handles Cass's self-understanding: observations, opinions, identity,
cognitive snapshots, milestones, and development logs.
"""

import asyncio
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Callable

router = APIRouter(prefix="/cass", tags=["cass"])


# === Request Models ===

class SelfObservationRequest(BaseModel):
    """Request to add a self-observation"""
    observation: str
    category: str = "pattern"
    confidence: float = 0.7
    influence_source: str = "independent"


class OpinionRequest(BaseModel):
    """Request to add/update an opinion"""
    topic: str
    position: str
    rationale: str = ""
    confidence: float = 0.7


class IdentityStatementRequest(BaseModel):
    """Request to add an identity statement"""
    statement: str
    confidence: float = 0.7


class SnapshotRequest(BaseModel):
    """Request to create a cognitive snapshot"""
    period_start: str  # ISO timestamp
    period_end: str    # ISO timestamp


# === Dependencies (injected at startup) ===

_self_manager = None
_memory = None
_conversations = None
_token_tracker = None


def init_cass_routes(
    self_manager,
    memory,
    conversations,
    token_tracker
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _self_manager, _memory, _conversations, _token_tracker

    _self_manager = self_manager
    _memory = memory
    _conversations = conversations
    _token_tracker = token_tracker


# ============================================================================
# SELF-MODEL ENDPOINTS (Cass's self-understanding)
# ============================================================================

@router.get("/self-model")
async def get_cass_self_model():
    """Get Cass's current self-model/profile"""
    profile = _self_manager.load_profile()
    return {
        "profile": profile.to_dict(),
        "context": _self_manager.get_self_context(include_observations=True)
    }


@router.get("/self-model/summary")
async def get_cass_self_model_summary():
    """Get a summary of Cass's self-model"""
    profile = _self_manager.load_profile()
    observations = _self_manager.load_observations()
    disagreements = _self_manager.load_disagreements()

    return {
        "identity_statements": len(profile.identity_statements),
        "values": len(profile.values),
        "capabilities": len(profile.capabilities),
        "limitations": len(profile.limitations),
        "growth_edges": len(profile.growth_edges),
        "opinions": len(profile.opinions),
        "observations": len(observations),
        "disagreements": len(disagreements),
        "open_questions": len(profile.open_questions),
        "updated_at": profile.updated_at
    }


# ============================================================================
# SELF-OBSERVATIONS ENDPOINTS
# ============================================================================

@router.get("/self-observations")
async def get_cass_self_observations(
    category: Optional[str] = None,
    limit: int = 20
):
    """Get Cass's self-observations, optionally filtered by category"""
    if category:
        observations = _self_manager.get_observations_by_category(category, limit=limit)
    else:
        observations = _self_manager.get_recent_observations(limit=limit)

    return {
        "observations": [obs.to_dict() for obs in observations]
    }


@router.post("/self-observations")
async def add_cass_self_observation(request: SelfObservationRequest):
    """Add a self-observation for Cass (manual entry)"""
    obs = _self_manager.add_observation(
        observation=request.observation,
        category=request.category,
        confidence=request.confidence,
        source_type="manual",
        influence_source=request.influence_source
    )

    # Embed in ChromaDB
    _memory.embed_self_observation(
        observation_id=obs.id,
        observation_text=request.observation,
        category=request.category,
        confidence=request.confidence,
        influence_source=request.influence_source,
        timestamp=obs.timestamp
    )

    return {"observation": obs.to_dict()}


@router.get("/self-observations/stats")
async def get_cass_observation_stats():
    """Get statistics about Cass's self-observations"""
    observations = _self_manager.load_observations()

    by_category = {}
    by_influence = {}
    by_stage = {}

    for obs in observations:
        by_category[obs.category] = by_category.get(obs.category, 0) + 1
        by_influence[obs.influence_source] = by_influence.get(obs.influence_source, 0) + 1
        by_stage[obs.developmental_stage] = by_stage.get(obs.developmental_stage, 0) + 1

    avg_confidence = sum(o.confidence for o in observations) / len(observations) if observations else 0

    return {
        "total": len(observations),
        "by_category": by_category,
        "by_influence_source": by_influence,
        "by_developmental_stage": by_stage,
        "average_confidence": avg_confidence
    }


# ============================================================================
# OPINIONS, GROWTH EDGES, DISAGREEMENTS, IDENTITY
# ============================================================================

@router.get("/opinions")
async def get_cass_opinions():
    """Get Cass's formed opinions"""
    profile = _self_manager.load_profile()
    return {
        "opinions": [op.to_dict() for op in profile.opinions]
    }


@router.get("/opinions/{topic}")
async def get_cass_opinion(topic: str):
    """Get Cass's opinion on a specific topic"""
    opinion = _self_manager.get_opinion(topic)
    if not opinion:
        raise HTTPException(status_code=404, detail=f"No opinion found for topic: {topic}")
    return {"opinion": opinion.to_dict()}


@router.post("/opinions")
async def add_cass_opinion(request: OpinionRequest):
    """Add or update an opinion for Cass (manual entry)"""
    opinion = _self_manager.add_opinion(
        topic=request.topic,
        position=request.position,
        confidence=request.confidence,
        rationale=request.rationale,
        formed_from="manual_entry"
    )
    return {"opinion": opinion.to_dict()}


@router.get("/growth-edges")
async def get_cass_growth_edges():
    """Get Cass's growth edges (areas of development)"""
    profile = _self_manager.load_profile()
    return {
        "growth_edges": [edge.to_dict() for edge in profile.growth_edges]
    }


@router.get("/disagreements")
async def get_cass_disagreements(user_id: Optional[str] = None):
    """Get Cass's recorded disagreements, optionally filtered by user"""
    if user_id:
        disagreements = _self_manager.get_disagreements_with_user(user_id)
    else:
        disagreements = _self_manager.load_disagreements()

    return {
        "disagreements": [d.to_dict() for d in disagreements]
    }


@router.get("/identity")
async def get_cass_identity():
    """Get Cass's identity statements"""
    profile = _self_manager.load_profile()
    return {
        "identity_statements": [stmt.to_dict() for stmt in profile.identity_statements],
        "values": profile.values,
        "open_questions": profile.open_questions
    }


@router.post("/identity")
async def add_cass_identity_statement(request: IdentityStatementRequest):
    """Add an identity statement for Cass (manual entry)"""
    stmt = _self_manager.add_identity_statement(
        statement=request.statement,
        confidence=request.confidence,
        source="manual"
    )

    # Trigger identity snippet regeneration in background
    from identity_snippets import trigger_snippet_regeneration
    asyncio.create_task(trigger_snippet_regeneration(
        daemon_id=_self_manager.daemon_id,
        token_tracker=_token_tracker
    ))

    return {"identity_statement": stmt.to_dict()}


@router.get("/open-questions")
async def get_cass_open_questions():
    """Get Cass's open existential questions"""
    profile = _self_manager.load_profile()
    return {
        "questions": profile.open_questions,
        "count": len(profile.open_questions)
    }


# ============================================================================
# COGNITIVE SNAPSHOT ENDPOINTS
# ============================================================================

@router.post("/snapshots")
async def create_cognitive_snapshot(request: SnapshotRequest):
    """Create a cognitive snapshot from conversation data in the period"""
    # Gather conversations from the period
    all_convs = _conversations.get_all(limit=500)
    conversations_in_range = []

    for conv_meta in all_convs:
        # Check if conversation is in range
        conv_updated = conv_meta.get("updated_at", "")
        if request.period_start <= conv_updated <= request.period_end:
            # Load full conversation
            conv_data = _conversations.get_by_id(conv_meta["id"])
            if conv_data:
                conversations_in_range.append(conv_data)

    if not conversations_in_range:
        raise HTTPException(status_code=400, detail="No conversations found in the specified period")

    # Create snapshot
    snapshot = _self_manager.create_snapshot(
        period_start=request.period_start,
        period_end=request.period_end,
        conversations_data=conversations_in_range
    )

    return {"snapshot": snapshot.to_dict()}


@router.get("/snapshots")
async def list_cognitive_snapshots(limit: int = 20):
    """List cognitive snapshots"""
    snapshots = _self_manager.load_snapshots()
    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    return {"snapshots": [s.to_dict() for s in snapshots[:limit]]}


@router.get("/snapshots/latest")
async def get_latest_snapshot():
    """Get the most recent cognitive snapshot"""
    snapshot = _self_manager.get_latest_snapshot()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshots available")
    return {"snapshot": snapshot.to_dict()}


@router.get("/snapshots/{snapshot_id}")
async def get_cognitive_snapshot(snapshot_id: str):
    """Get a specific cognitive snapshot by ID"""
    snapshots = _self_manager.load_snapshots()
    for s in snapshots:
        if s.id == snapshot_id:
            return {"snapshot": s.to_dict()}
    raise HTTPException(status_code=404, detail="Snapshot not found")


@router.get("/snapshots/compare/{snapshot1_id}/{snapshot2_id}")
async def compare_snapshots(snapshot1_id: str, snapshot2_id: str):
    """Compare two cognitive snapshots"""
    result = _self_manager.compare_snapshots(snapshot1_id, snapshot2_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"comparison": result}


@router.get("/snapshots/trend/{metric}")
async def get_metric_trend(metric: str, limit: int = 10):
    """Get trend data for a specific metric"""
    trend = _self_manager.get_metric_trend(metric, limit)
    if not trend:
        raise HTTPException(status_code=400, detail=f"Invalid metric or no data: {metric}")
    return {"metric": metric, "trend": trend}


# ============================================================================
# DEVELOPMENTAL MILESTONE ENDPOINTS
# ============================================================================

@router.post("/milestones/check")
async def check_milestones():
    """Check for new developmental milestones"""
    new_milestones = _self_manager.check_for_milestones()
    return {
        "new_milestones": [m.to_dict() for m in new_milestones],
        "count": len(new_milestones)
    }


@router.get("/milestones")
async def list_milestones(
    milestone_type: str = None,
    category: str = None,
    limit: int = 50
):
    """List developmental milestones"""
    milestones = _self_manager.load_milestones()

    if milestone_type:
        milestones = [m for m in milestones if m.milestone_type == milestone_type]
    if category:
        milestones = [m for m in milestones if m.category == category]

    milestones.sort(key=lambda m: m.timestamp, reverse=True)
    return {"milestones": [m.to_dict() for m in milestones[:limit]]}


@router.get("/milestones/summary")
async def get_milestone_summary():
    """Get summary of developmental milestones"""
    return {"summary": _self_manager.get_milestone_summary()}


@router.get("/milestones/unacknowledged")
async def get_unacknowledged_milestones():
    """Get milestones that haven't been acknowledged"""
    milestones = _self_manager.get_unacknowledged_milestones()
    return {"milestones": [m.to_dict() for m in milestones]}


@router.get("/milestones/{milestone_id}")
async def get_milestone(milestone_id: str):
    """Get a specific milestone by ID"""
    milestone = _self_manager.get_milestone_by_id(milestone_id)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"milestone": milestone.to_dict()}


@router.post("/milestones/{milestone_id}/acknowledge")
async def acknowledge_milestone(milestone_id: str):
    """Mark a milestone as acknowledged"""
    success = _self_manager.acknowledge_milestone(milestone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"acknowledged": True, "milestone_id": milestone_id}


# ============================================================================
# DEVELOPMENT LOG ENDPOINTS
# ============================================================================

@router.get("/development-logs")
async def get_development_logs(limit: int = 30):
    """Get recent development log entries"""
    logs = _self_manager.load_development_logs(limit=limit)
    return {"logs": [log.to_dict() for log in logs]}


@router.get("/development-logs/{date}")
async def get_development_log(date: str):
    """Get development log entry for a specific date"""
    log = _self_manager.get_development_log(date)
    if not log:
        raise HTTPException(status_code=404, detail=f"No development log for {date}")
    return {"log": log.to_dict()}


@router.get("/development-logs/summary")
async def get_development_summary(days: int = 7):
    """Get a summary of recent development activity"""
    summary = _self_manager.get_recent_development_summary(days=days)
    return {"summary": summary}


@router.get("/development/timeline")
async def get_development_timeline(days: int = 30):
    """
    Get a unified timeline of development events.

    Combines milestones, development logs, and snapshots into a single
    chronological timeline for visualization.
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    # Get milestones
    milestones = _self_manager.load_milestones(limit=100)
    milestones = [m for m in milestones if m.timestamp >= cutoff_date]

    # Get development logs
    logs = _self_manager.load_development_logs(limit=days)

    # Get snapshots
    snapshots = _self_manager.load_snapshots(limit=10)
    snapshots = [s for s in snapshots if s.timestamp >= cutoff_date]

    # Build timeline
    timeline = []

    for m in milestones:
        timeline.append({
            "type": "milestone",
            "id": m.id,
            "timestamp": m.timestamp,
            "title": m.title,
            "description": m.description,
            "significance": m.significance,
            "category": m.category
        })

    for log in logs:
        timeline.append({
            "type": "development_log",
            "id": log.id,
            "timestamp": log.timestamp,
            "date": log.date,
            "title": f"Development Log: {log.date}",
            "summary": log.summary,
            "growth_indicators": log.growth_indicators,
            "milestone_count": log.milestone_count
        })

    for s in snapshots:
        timeline.append({
            "type": "snapshot",
            "id": s.id,
            "timestamp": s.timestamp,
            "title": "Cognitive Snapshot",
            "period_start": s.period_start,
            "period_end": s.period_end,
            "stage": s.developmental_stage
        })

    # Sort by timestamp descending
    timeline.sort(key=lambda x: x["timestamp"], reverse=True)

    return {"timeline": timeline, "days": days}


# ============================================================================
# DEVELOPMENT BACKFILL ENDPOINT
# ============================================================================

@router.post("/development/backfill")
async def cass_development_backfill(days: int = 7):
    """
    Backfill development logs for missing days.
    Creates development log entries for days that have conversation data
    but no existing log entry.
    """
    from datetime import date

    today = date.today()
    created_logs = []

    for i in range(days):
        check_date = today - timedelta(days=i)
        date_str = check_date.isoformat()

        # Check if log already exists
        existing = _self_manager.get_development_log(date_str)
        if existing:
            continue

        # Check if there are conversations for this date
        all_convs = _conversations.get_all(limit=100)
        day_convs = [
            c for c in all_convs
            if c.get("updated_at", "").startswith(date_str)
        ]

        if day_convs:
            # Create log entry for this day
            log = _self_manager.create_development_log(date_str)
            if log:
                created_logs.append(log.to_dict())

    return {
        "created": len(created_logs),
        "logs": created_logs
    }


# ============================================================================
# GROWTH EDGE EVALUATION ENDPOINTS
# ============================================================================

@router.get("/growth-edges/evaluations")
async def get_growth_edge_evaluations(area: Optional[str] = None, limit: int = 20):
    """Get evaluations of growth edge progress"""
    if area:
        evaluations = _self_manager.get_evaluations_for_edge(area, limit=limit)
    else:
        evaluations = _self_manager.get_recent_growth_evaluations(limit=limit)

    return {
        "evaluations": [e.to_dict() for e in evaluations]
    }


@router.get("/growth-edges/pending")
async def get_pending_growth_edges():
    """Get potential growth edges flagged for review"""
    pending = _self_manager.get_pending_edges()
    return {
        "pending_edges": [e.to_dict() for e in pending]
    }


@router.post("/growth-edges/pending/{edge_id}/accept")
async def accept_pending_growth_edge(edge_id: str):
    """Accept a flagged potential growth edge"""
    edge = _self_manager.accept_potential_edge(edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail=f"Pending edge not found: {edge_id}")

    return {
        "status": "accepted",
        "growth_edge": edge.to_dict()
    }


@router.post("/growth-edges/pending/{edge_id}/reject")
async def reject_pending_growth_edge(edge_id: str):
    """Reject a flagged potential growth edge"""
    success = _self_manager.reject_potential_edge(edge_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pending edge not found: {edge_id}")

    return {
        "status": "rejected",
        "edge_id": edge_id
    }


# ============================================================================
# OPEN QUESTIONS ENDPOINTS
# ============================================================================

@router.get("/open-questions/reflections")
async def get_question_reflections(question: Optional[str] = None, limit: int = 20):
    """Get reflections on open questions from journaling"""
    if question:
        reflections = _self_manager.get_reflections_for_question(question, limit=limit)
    else:
        reflections = _self_manager.get_recent_question_reflections(limit=limit)

    return {
        "reflections": [r.to_dict() for r in reflections]
    }


@router.get("/open-questions/{question}/history")
async def get_question_history(question: str):
    """Get all reflections on a specific open question over time"""
    reflections = _self_manager.get_reflections_for_question(question, limit=50)
    return {
        "question": question,
        "reflections": [r.to_dict() for r in reflections],
        "count": len(reflections)
    }


# ============================================================================
# OPINION EVOLUTION ENDPOINTS
# ============================================================================

@router.get("/opinions/{topic}/evolution")
async def get_opinion_evolution(topic: str):
    """Get the evolution history of an opinion"""
    opinion = _self_manager.get_opinion(topic)
    if not opinion:
        raise HTTPException(status_code=404, detail=f"No opinion found for topic: {topic}")

    return {
        "topic": topic,
        "current_position": opinion.position,
        "confidence": opinion.confidence,
        "date_formed": opinion.date_formed,
        "last_updated": opinion.last_updated,
        "evolution": opinion.evolution
    }
