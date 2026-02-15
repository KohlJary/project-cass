"""
Thymos Admin API

Endpoints for monitoring and calibrating the Thymos homeostatic system.

SHADOW MODE: Thymos observes but doesn't drive behavior.
These endpoints allow:
- Viewing current affect/needs state
- Reviewing suggestion history
- Providing feedback for calibration
- Viewing state trends
"""

import copy

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from thymos import persistence
from thymos.shadow_runner import ThymosShadowRunner

router = APIRouter(prefix="/thymos", tags=["thymos"])

# Module-level reference to the shadow runner
_shadow_runner: Optional[ThymosShadowRunner] = None


def init_thymos_runner(runner: ThymosShadowRunner) -> None:
    """Initialize the Thymos shadow runner reference."""
    global _shadow_runner
    _shadow_runner = runner


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
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    state = _shadow_runner.get_current_state()
    return ThymosStateResponse(**state)


@router.get("/state/affect")
async def get_affect_state() -> dict:
    """Get just the affect vector."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _shadow_runner.affect.to_dict()


@router.get("/state/needs")
async def get_needs_state() -> dict:
    """Get just the needs register."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    state = _shadow_runner.get_current_state()
    return state["needs"]


@router.get("/state/felt")
async def get_felt_state() -> dict:
    """Get the current felt state summary."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    if _shadow_runner.current_felt_state:
        return _shadow_runner.current_felt_state.to_dict()
    return {"summary": "No felt state generated yet"}


@router.get("/suggestions")
async def get_suggestions(limit: int = 20) -> list[SuggestionResponse]:
    """Get recent goal suggestions from shadow mode."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    suggestions = _shadow_runner.get_suggestions_log(limit=limit)
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
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    success = persistence.add_suggestion_feedback(suggestion_id, request.feedback)
    if not success:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    return {"status": "feedback recorded", "suggestion_id": suggestion_id}


@router.get("/events")
async def get_recent_events(limit: int = 20) -> list[dict]:
    """Get recent events processed by Thymos."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _shadow_runner.get_recent_events(limit=limit)


@router.get("/snapshots")
async def get_snapshots(limit: int = 20) -> list[SnapshotResponse]:
    """Get recent state snapshots."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    snapshots = _shadow_runner.get_snapshots(limit=limit)
    return [SnapshotResponse(**s) for s in snapshots]


@router.get("/trends/need/{need_name}")
async def get_need_trend(need_name: str, hours: int = 24) -> list[dict]:
    """Get historical trend for a specific need."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    trends = persistence.get_need_trends(
        _shadow_runner.daemon_id,
        need_name,
        hours=hours
    )
    return [{"timestamp": t, "value": v} for t, v in trends]


@router.get("/trends/affect/{dimension}")
async def get_affect_trend(dimension: str, hours: int = 24) -> list[dict]:
    """Get historical trend for a specific affect dimension."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    trends = persistence.get_affect_trends(
        _shadow_runner.daemon_id,
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
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    event_data = request.data if request.data is not None else {}
    await _shadow_runner.process_event(request.event_type, event_data)

    return {
        "status": "event processed",
        "event_type": request.event_type,
        "new_state": _shadow_runner.get_current_state()
    }


@router.post("/simulate/forward")
async def project_forward(request: ProjectForwardRequest) -> dict:
    """
    Project the current state forward in time.

    Shows what the state would look like after X hours of decay
    and coupling, assuming no events occur. Does NOT modify actual state.
    """
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    from thymos import AffectVector, NeedsRegister, AffectNeedDynamics, FeltStateSummarizer

    # Create copies of current state
    projected_affect = AffectVector(state=copy.deepcopy(_shadow_runner.affect.state))
    projected_needs = NeedsRegister(state=copy.deepcopy(_shadow_runner.needs.state))
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
        "current_state": _shadow_runner.get_current_state(),
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
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    _shadow_runner.affect.reset_to_baseline()
    _shadow_runner.needs.reset_to_baseline()
    _shadow_runner.current_felt_state = None
    _shadow_runner.event_count = 0

    return {
        "status": "reset to baseline",
        "new_state": _shadow_runner.get_current_state()
    }


@router.get("/health")
async def thymos_health() -> dict:
    """Health check for Thymos subsystem."""
    if not _shadow_runner:
        return {
            "status": "not_initialized",
            "running": False,
        }

    return {
        "status": "ok" if _shadow_runner.running else "stopped",
        "running": _shadow_runner.running,
        "daemon_id": _shadow_runner.daemon_id,
        "event_count": _shadow_runner.event_count,
        "overall_health": _shadow_runner.needs.overall_health(),
        "auto_care": _shadow_runner.get_auto_care_settings(),
    }


@router.get("/care-log")
async def get_care_log(limit: int = 20) -> list[dict]:
    """Get recent simulated self-care actions."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _shadow_runner.get_care_log(limit=limit)


class AutoCareSettingsRequest(BaseModel):
    """Request to update auto-care settings."""
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    cooldown_seconds: Optional[float] = None


@router.get("/auto-care")
async def get_auto_care_settings() -> dict:
    """Get current auto-care configuration."""
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _shadow_runner.get_auto_care_settings()


@router.post("/auto-care")
async def update_auto_care_settings(request: AutoCareSettingsRequest) -> dict:
    """
    Update auto-care settings.

    Auto-care simulates self-care actions when needs fall below threshold.
    This helps calibrate the system by showing what would happen if
    Thymos were actually driving behavior.
    """
    if not _shadow_runner:
        raise HTTPException(status_code=503, detail="Thymos not initialized")

    return _shadow_runner.set_auto_care_settings(
        enabled=request.enabled,
        threshold=request.threshold,
        cooldown_seconds=request.cooldown_seconds,
    )
