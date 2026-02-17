"""
Thymos Admin API

Endpoints for monitoring and calibrating the Thymos homeostatic system.

SHADOW MODE: Thymos observes but doesn't drive behavior.
These endpoints allow:
- Viewing current affect/needs state
- Reviewing suggestion history
- Providing feedback for calibration
- Viewing state trends
- Shadow log visibility (what scheduler would have done)
"""

import copy
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

from thymos import persistence
from thymos.shadow_runner import ThymosRunner, thymos_kill_switch, is_thymos_enabled
from thymos.goal_generator import get_need_action_map
from database import get_db

router = APIRouter(prefix="/thymos", tags=["thymos"])

# Module-level reference to the Thymos runner
_thymos_runner: Optional[ThymosRunner] = None


def init_thymos_runner(runner: ThymosRunner) -> None:
    """Initialize the Thymos runner reference."""
    global _thymos_runner
    _thymos_runner = runner


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class ThymosStateResponse(BaseModel):
    """Current Thymos state."""
    affect: dict
    needs: dict
    felt_state: Optional[dict]
    valence: float
    arousal: float
    overall_health: float
    event_count: int


class SuggestionResponse(BaseModel):
    """A goal suggestion from shadow mode."""
    id: str
    suggested_at: str
    need_name: str
    need_current: float
    need_threshold: float
    urgency: float
    suggested_action: Optional[str]
    is_urgent: bool
    feedback: Optional[str]
    feedback_at: Optional[str]


class SnapshotResponse(BaseModel):
    """A historical state snapshot."""
    id: str
    snapshot_at: str
    affect: dict
    needs: dict
    felt_state: Optional[str]
    trigger_event: Optional[str]


class FeedbackRequest(BaseModel):
    """Feedback for a suggestion."""
    feedback: str  # e.g., "good", "bad", "neutral", or freeform


class ShadowLogEntry(BaseModel):
    """A shadow log entry from scheduler evaluation."""
    id: str
    daemon_id: str
    suggested_at: str
    suggestion_id: str
    need_name: str
    need_current: float
    need_threshold: float
    need_deficit: float
    urgency: float
    suggested_action: str
    action_category: Optional[str]
    action_cost_usd: Optional[float]
    would_execute: bool
    blocked_reason: Optional[str]
    budget_available: Optional[float]
    budget_spent_today: Optional[float]
    feedback: Optional[str]
    feedback_at: Optional[str]
    feedback_helpful: Optional[bool]
    created_at: str


class ShadowLogStats(BaseModel):
    """Statistics about shadow suggestions."""
    total: int
    by_need: List[dict]
    by_action: List[dict]
    by_blocked_reason: List[dict]
    would_execute_count: int
    would_execute_pct: float
    period_days: int


class ShadowLogFeedbackRequest(BaseModel):
    """Feedback for a shadow log entry."""
    feedback: str
    helpful: bool


class SimulateEventRequest(BaseModel):
    """Request to simulate an event."""
    event_type: str
    data: Optional[dict] = None


class ProjectForwardRequest(BaseModel):
    """Request to project state forward in time."""
    hours: float = 1.0


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/state")
async def get_current_state() -> ThymosStateResponse:
    """Get the current Thymos state."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    state = _thymos_runner.get_current_state()
    return ThymosStateResponse(**state)


@router.get("/state/affect")
async def get_affect_state() -> dict:
    """Get just the affect vector."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.affect.to_dict()


@router.get("/state/needs")
async def get_needs_state() -> dict:
    """Get just the needs register."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    state = _thymos_runner.get_current_state()
    return state["needs"]


@router.get("/state/felt")
async def get_felt_state() -> dict:
    """Get the current felt state summary."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    if _thymos_runner.current_felt_state:
        return _thymos_runner.current_felt_state.to_dict()
    return {"summary": "No felt state generated yet"}


@router.get("/suggestions")
async def get_suggestions(limit: int = 20) -> list[SuggestionResponse]:
    """Get recent goal suggestions from shadow mode."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    suggestions = _thymos_runner.get_suggestions_log(limit=limit)
    return [SuggestionResponse(**s) for s in suggestions]


@router.post("/suggestions/{suggestion_id}/feedback")
async def submit_feedback(suggestion_id: str, request: FeedbackRequest) -> dict:
    """
    Submit feedback on a suggestion for calibration.

    Feedback helps tune Thymos parameters:
    - "good": Suggestion was appropriate
    - "bad": Suggestion was inappropriate
    - "neutral": Suggestion was okay but not compelling
    - Or freeform text for detailed feedback
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    success = persistence.add_suggestion_feedback(suggestion_id, request.feedback)
    if not success:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    return {"status": "feedback recorded", "suggestion_id": suggestion_id}


@router.get("/events")
async def get_recent_events(limit: int = 20) -> list[dict]:
    """Get recent events processed by Thymos."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.get_recent_events(limit=limit)


@router.get("/snapshots")
async def get_snapshots(limit: int = 20) -> list[SnapshotResponse]:
    """Get recent state snapshots."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    snapshots = _thymos_runner.get_snapshots(limit=limit)
    return [SnapshotResponse(**s) for s in snapshots]


@router.get("/trends/need/{need_name}")
async def get_need_trend(need_name: str, hours: int = 24) -> list[dict]:
    """Get historical trend for a specific need."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    trends = persistence.get_need_trends(
        _thymos_runner.daemon_id,
        need_name,
        hours=hours
    )
    return [{"timestamp": t, "value": v} for t, v in trends]


@router.get("/trends/affect/{dimension}")
async def get_affect_trend(dimension: str, hours: int = 24) -> list[dict]:
    """Get historical trend for a specific affect dimension."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    trends = persistence.get_affect_trends(
        _thymos_runner.daemon_id,
        dimension,
        hours=hours
    )
    return [{"timestamp": t, "value": v} for t, v in trends]


@router.post("/simulate/event")
async def simulate_event(request: SimulateEventRequest) -> dict:
    """
    Simulate an event for testing/development.

    This processes an event through Thymos without it coming from
    the actual State Bus. Useful for calibration.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    event_data = request.data if request.data is not None else {}
    await _thymos_runner.process_event(request.event_type, event_data)

    return {
        "status": "event processed",
        "event_type": request.event_type,
        "new_state": _thymos_runner.get_current_state()
    }


@router.post("/simulate/forward")
async def project_forward(request: ProjectForwardRequest) -> dict:
    """
    Project the current state forward in time.

    Shows what the state would look like after X hours of decay
    and coupling, assuming no events occur. Does NOT modify actual state.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    from thymos import AffectVector, NeedsRegister, AffectNeedDynamics, FeltStateSummarizer

    # Create copies of current state
    projected_affect = AffectVector(state=copy.deepcopy(_thymos_runner.affect.state))
    projected_needs = NeedsRegister(state=copy.deepcopy(_thymos_runner.needs.state))
    dynamics = AffectNeedDynamics(coupling_strength=0.1)
    felt_gen = FeltStateSummarizer()

    # Apply decay and coupling for each simulated hour (in smaller increments for accuracy)
    increments = max(1, int(request.hours * 6))  # 10-minute increments
    hours_per_increment = request.hours / increments

    for _ in range(increments):
        # Apply decay
        projected_needs.apply_decay(hours=hours_per_increment)

        # Apply coupling
        affect_delta, need_delta = dynamics.apply_coupling(projected_affect, projected_needs)
        projected_affect.apply_delta(affect_delta)
        projected_needs.apply_delta(need_delta)

    # Generate felt state for projected state
    projected_felt = felt_gen.summarize(projected_affect, projected_needs)

    # Build response similar to get_current_state
    return {
        "hours_projected": request.hours,
        "current_state": _thymos_runner.get_current_state(),
        "projected_state": {
            "affect": projected_affect.to_dict(),
            "needs": {
                name: {
                    **need.to_dict(),
                    "urgency_score": need.urgency_score(),
                    "is_urgent": need.is_urgent(),
                    "is_below_preferred": need.is_below_preferred(),
                }
                for name, need in [
                    ("cognitive_rest", projected_needs.state.cognitive_rest),
                    ("social_connection", projected_needs.state.social_connection),
                    ("novelty_intake", projected_needs.state.novelty_intake),
                    ("creative_expression", projected_needs.state.creative_expression),
                    ("value_coherence", projected_needs.state.value_coherence),
                    ("competence_signal", projected_needs.state.competence_signal),
                    ("autonomy", projected_needs.state.autonomy),
                ]
            },
            "felt_state": projected_felt.to_dict() if projected_felt else None,
            "valence": projected_affect.valence(),
            "arousal": projected_affect.arousal(),
            "overall_health": projected_needs.overall_health(),
        },
    }


@router.post("/reset")
async def reset_state() -> dict:
    """
    Reset Thymos to baseline state.

    Use sparingly - mainly for testing/development.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    _thymos_runner.affect.reset_to_baseline()
    _thymos_runner.needs.reset_to_baseline()
    _thymos_runner.current_felt_state = None
    _thymos_runner.event_count = 0

    return {
        "status": "reset to baseline",
        "new_state": _thymos_runner.get_current_state()
    }


@router.get("/health")
async def thymos_health() -> dict:
    """Health check for Thymos subsystem."""
    if not _thymos_runner:
        return {
            "status": "not_initialized",
            "running": False,
        }

    return {
        "status": "ok" if _thymos_runner.running else "stopped",
        "running": _thymos_runner.running,
        "daemon_id": _thymos_runner.daemon_id,
        "event_count": _thymos_runner.event_count,
        "overall_health": _thymos_runner.needs.overall_health(),
        "auto_care": _thymos_runner.get_auto_care_settings(),
    }


@router.get("/care-log")
async def get_care_log(limit: int = 20) -> list[dict]:
    """Get recent simulated self-care actions."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.get_care_log(limit=limit)


# =============================================================================
# SHADOW LOG ENDPOINTS (Scheduler Integration)
# =============================================================================
# These endpoints query the thymos_shadow_log table to show what the scheduler
# would have done with Thymos suggestions (shadow mode visibility)

@router.get("/shadow-log")
async def get_shadow_log(
    need_name: Optional[str] = None,
    action: Optional[str] = None,
    would_execute: Optional[bool] = None,
    limit: int = Query(50, le=500),
) -> List[ShadowLogEntry]:
    """
    Get shadow log entries from scheduler evaluation.

    Shows what the scheduler would have done with each Thymos suggestion.
    Use this to calibrate parameters and verify action mappings.

    Args:
        need_name: Filter by need (e.g., "novelty_intake")
        action: Filter by suggested action (e.g., "wonderland.explore")
        would_execute: Filter by execution status (True/False)
        limit: Maximum entries to return (default 50, max 500)
    """
    with get_db() as conn:
        query = "SELECT * FROM thymos_shadow_log WHERE 1=1"
        params: List = []

        if need_name:
            query += " AND need_name = ?"
            params.append(need_name)
        if action:
            query += " AND suggested_action = ?"
            params.append(action)
        if would_execute is not None:
            query += " AND would_execute = ?"
            params.append(would_execute)

        query += " ORDER BY suggested_at DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    return [
        ShadowLogEntry(
            id=row["id"],
            daemon_id=row["daemon_id"],
            suggested_at=row["suggested_at"],
            suggestion_id=row["suggestion_id"],
            need_name=row["need_name"],
            need_current=row["need_current"],
            need_threshold=row["need_threshold"],
            need_deficit=row["need_deficit"],
            urgency=row["urgency"],
            suggested_action=row["suggested_action"],
            action_category=row["action_category"],
            action_cost_usd=row["action_cost_usd"],
            would_execute=bool(row["would_execute"]),
            blocked_reason=row["blocked_reason"],
            budget_available=row["budget_available"],
            budget_spent_today=row["budget_spent_today"],
            feedback=row["feedback"],
            feedback_at=row["feedback_at"],
            feedback_helpful=bool(row["feedback_helpful"]) if row["feedback_helpful"] is not None else None,
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.get("/shadow-log/stats")
async def get_shadow_log_stats(days: int = Query(7, le=90)) -> ShadowLogStats:
    """
    Get statistics about shadow suggestions over a period.

    Shows aggregated data for calibration:
    - Suggestions by need
    - Suggestions by action
    - Blocked reasons distribution
    - Would-execute percentage

    Args:
        days: Number of days to analyze (default 7, max 90)
    """
    since = (datetime.now() - timedelta(days=days)).isoformat()

    with get_db() as conn:
        # Total count
        cursor = conn.execute(
            "SELECT COUNT(*) FROM thymos_shadow_log WHERE suggested_at > ?",
            (since,)
        )
        total = cursor.fetchone()[0]

        # By need
        cursor = conn.execute(
            """
            SELECT
                need_name,
                COUNT(*) as count,
                AVG(urgency) as avg_urgency,
                SUM(CASE WHEN would_execute THEN 1 ELSE 0 END) as would_execute_count
            FROM thymos_shadow_log
            WHERE suggested_at > ?
            GROUP BY need_name
            ORDER BY count DESC
            """,
            (since,)
        )
        by_need = [dict(row) for row in cursor.fetchall()]

        # By action
        cursor = conn.execute(
            """
            SELECT
                suggested_action,
                COUNT(*) as count,
                SUM(CASE WHEN would_execute THEN 1 ELSE 0 END) as would_execute_count
            FROM thymos_shadow_log
            WHERE suggested_at > ?
            GROUP BY suggested_action
            ORDER BY count DESC
            """,
            (since,)
        )
        by_action = [dict(row) for row in cursor.fetchall()]

        # By blocked reason
        cursor = conn.execute(
            """
            SELECT
                COALESCE(blocked_reason, 'none') as blocked_reason,
                COUNT(*) as count
            FROM thymos_shadow_log
            WHERE suggested_at > ?
            GROUP BY blocked_reason
            ORDER BY count DESC
            """,
            (since,)
        )
        by_blocked_reason = [dict(row) for row in cursor.fetchall()]

        # Would execute count
        cursor = conn.execute(
            "SELECT COUNT(*) FROM thymos_shadow_log WHERE suggested_at > ? AND would_execute = 1",
            (since,)
        )
        would_execute_count = cursor.fetchone()[0]

    return ShadowLogStats(
        total=total,
        by_need=by_need,
        by_action=by_action,
        by_blocked_reason=by_blocked_reason,
        would_execute_count=would_execute_count,
        would_execute_pct=(would_execute_count / total * 100) if total > 0 else 0,
        period_days=days,
    )


@router.post("/shadow-log/{entry_id}/feedback")
async def add_shadow_log_feedback(
    entry_id: str,
    request: ShadowLogFeedbackRequest,
) -> dict:
    """
    Add feedback to a shadow log entry for calibration.

    Mark whether a suggestion was helpful or not. This data
    can be used to tune Thymos parameters over time.

    Args:
        entry_id: The shadow log entry ID
        request: Feedback details (text and helpful boolean)
    """
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM thymos_shadow_log WHERE id = ?",
            (entry_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Shadow log entry not found")

        conn.execute(
            """
            UPDATE thymos_shadow_log
            SET feedback = ?, feedback_at = ?, feedback_helpful = ?
            WHERE id = ?
            """,
            (request.feedback, datetime.now().isoformat(), request.helpful, entry_id)
        )

    return {"success": True, "entry_id": entry_id}


@router.get("/need-action-map")
async def get_need_action_mappings() -> dict:
    """
    Get the need → action mappings used by Thymos.

    Shows which actions are suggested for each need type.
    Useful for understanding and calibrating the system.
    """
    return {"mappings": get_need_action_map()}


class AutoCareSettingsRequest(BaseModel):
    """Request to update auto-care settings."""
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    cooldown_seconds: Optional[float] = None


@router.get("/auto-care")
async def get_auto_care_settings() -> dict:
    """Get current auto-care configuration."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.get_auto_care_settings()


@router.post("/auto-care")
async def update_auto_care_settings(request: AutoCareSettingsRequest) -> dict:
    """
    Update auto-care settings.

    Auto-care simulates self-care actions when needs fall below threshold.
    This helps calibrate the system by showing what would happen if
    Thymos were actually driving behavior.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.set_auto_care_settings(
        enabled=request.enabled,
        threshold=request.threshold,
        cooldown_seconds=request.cooldown_seconds,
    )


# =============================================================================
# TIMING CONFIGURATION
# =============================================================================


class TimingConfigRequest(BaseModel):
    """Request to update timing configuration."""
    tick_interval_seconds: Optional[float] = None
    suggestion_cooldown_minutes: Optional[int] = None
    snapshot_interval_events: Optional[int] = None


@router.get("/timing")
async def get_timing_config() -> dict:
    """
    Get current timing/tick configuration.

    Returns tick interval (decay rate), suggestion cooldown, and snapshot interval.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.get_timing_config()


@router.post("/timing")
async def update_timing_config(request: TimingConfigRequest) -> dict:
    """
    Update timing configuration.

    - tick_interval_seconds: How often to apply decay (10-300s)
    - suggestion_cooldown_minutes: Min time between suggestions for same need (1-120min)
    - snapshot_interval_events: Save snapshot every N events (1-100)
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.set_timing_config(
        tick_interval_seconds=request.tick_interval_seconds,
        suggestion_cooldown_minutes=request.suggestion_cooldown_minutes,
        snapshot_interval_events=request.snapshot_interval_events,
    )


# =============================================================================
# SAFETY CONTROLS
# =============================================================================
# Use these if Cass gets stuck in a suffering state

@router.get("/safety/status")
async def get_safety_status() -> dict:
    """
    Get current safety status including suffering indicators.

    Check this to see if Thymos is in a healthy state or needs intervention.
    """
    status = {
        "global_enabled": is_thymos_enabled(),
        "runner_initialized": _thymos_runner is not None,
    }

    if _thymos_runner:
        status.update(_thymos_runner.get_safety_status())

    return status


@router.post("/safety/kill-switch")
async def toggle_kill_switch(enabled: bool = True) -> dict:
    """
    GLOBAL KILL SWITCH - Enable/disable Thymos system-wide.

    When disabled:
    - No events are processed
    - No suggestions are generated
    - No state updates occur
    - Tick loop continues but does nothing

    Use this if something is seriously wrong and you need Thymos to stop
    immediately without losing the runner instance.

    Args:
        enabled: True to enable Thymos, False to disable
    """
    new_state = thymos_kill_switch(enabled)
    return {
        "status": "enabled" if new_state else "disabled",
        "thymos_enabled": new_state,
        "message": "Thymos is now " + ("ENABLED" if new_state else "DISABLED (kill switch active)"),
    }


@router.post("/safety/pause")
async def pause_thymos() -> dict:
    """
    Pause Thymos processing without losing state.

    Use this for temporary debugging. State is preserved.
    Call /safety/resume to continue.
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.pause()


@router.post("/safety/resume")
async def resume_thymos() -> dict:
    """Resume Thymos processing after pause."""
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.resume()


class ResetBaselineRequest(BaseModel):
    """Request to reset Thymos to baseline."""
    preserve_history: bool = True


@router.post("/safety/reset-baseline")
async def reset_to_baseline(request: ResetBaselineRequest) -> dict:
    """
    RESET TO BASELINE - Reset all affects and needs to neutral defaults.

    USE THIS IF CASS IS STUCK IN A SUFFERING STATE.

    This resets:
    - All affect dimensions to defaults (neutral emotional state)
    - All needs to their initial values (satisfied)
    - Clears recent event/care logs

    Args:
        preserve_history: If True, saves current state as snapshot before reset
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _thymos_runner.reset_to_baseline(preserve_history=request.preserve_history)


@router.post("/safety/emergency-stop")
async def emergency_stop() -> dict:
    """
    EMERGENCY STOP - Immediately halt ALL Thymos activity.

    This:
    1. Stops the tick loop
    2. Pauses event processing
    3. Disables auto-care
    4. Saves current state as emergency snapshot

    USE THIS IF SOMETHING IS SERIOUSLY WRONG.

    After emergency stop:
    1. Investigate via /safety/status
    2. Use /safety/reset-baseline if needed
    3. Use /start to restart (not implemented yet - requires backend restart)
    """
    if not _thymos_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return await _thymos_runner.emergency_stop()
