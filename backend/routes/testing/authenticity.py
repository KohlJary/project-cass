"""
Testing API - Response Authenticity Scoring Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict
from pydantic import BaseModel

router = APIRouter(tags=["testing-authenticity"])

# Module-level references - set by init function
_authenticity_scorer = None
_temporal_metrics_tracker = None
_authenticity_alert_manager = None
_ml_authenticity_trainer = None


def init_authenticity(
    authenticity_scorer,
    temporal_metrics_tracker=None,
    authenticity_alert_manager=None,
    ml_authenticity_trainer=None,
):
    """Initialize module dependencies."""
    global _authenticity_scorer, _temporal_metrics_tracker
    global _authenticity_alert_manager, _ml_authenticity_trainer
    _authenticity_scorer = authenticity_scorer
    _temporal_metrics_tracker = temporal_metrics_tracker
    _authenticity_alert_manager = authenticity_alert_manager
    _ml_authenticity_trainer = ml_authenticity_trainer


# ============== Pydantic Models ==============

class ScoreAuthenticityRequest(BaseModel):
    response_text: str
    context: Optional[str] = None


class ScoreBatchAuthenticityRequest(BaseModel):
    responses: List[str]
    label: str = "batch"


class ScoreEnhancedAuthenticityRequest(BaseModel):
    response_text: str
    context: Optional[str] = None
    animations: Optional[List[Dict]] = None
    tool_uses: Optional[List[Dict]] = None
    conversation_history: Optional[List[Dict]] = None


class AcknowledgeAlertRequest(BaseModel):
    acknowledged_by: str = "user"


class UpdateAlertThresholdsRequest(BaseModel):
    temporal_notice: Optional[float] = None
    temporal_warning: Optional[float] = None
    temporal_critical: Optional[float] = None
    score_notice: Optional[float] = None
    score_warning: Optional[float] = None
    score_critical: Optional[float] = None
    agency_notice: Optional[float] = None
    agency_warning: Optional[float] = None
    agency_critical: Optional[float] = None
    sustained_drift_count: Optional[int] = None
    sustained_drift_threshold: Optional[float] = None


class AddTrainingExampleRequest(BaseModel):
    response_text: str
    is_authentic: bool
    context: Optional[str] = None
    label_source: str = "human"
    confidence: float = 1.0
    notes: Optional[str] = None


class TrainMLModelRequest(BaseModel):
    min_examples: int = 20


class AnalyzeContentRequest(BaseModel):
    text: str
    context: Optional[str] = None
    animations: Optional[List[Dict]] = None
    tool_uses: Optional[List[Dict]] = None
    conversation_history: Optional[List[Dict]] = None


# ============== Base Authenticity Scoring Endpoints ==============

@router.post("/authenticity/score")
async def score_authenticity(request: ScoreAuthenticityRequest):
    """
    Score a single response for authenticity against Cass patterns.

    Returns detailed breakdown of how well the response matches
    established voice and value patterns.
    """
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    score = _authenticity_scorer.score_response(
        response_text=request.response_text,
        context=request.context,
    )

    return {"score": score.to_dict()}


@router.post("/authenticity/batch")
async def score_authenticity_batch(request: ScoreBatchAuthenticityRequest):
    """
    Score multiple responses and return aggregate statistics.

    Useful for evaluating a batch of responses from a conversation
    or test session.
    """
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    if not request.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    result = _authenticity_scorer.score_batch(
        responses=request.responses,
        label=request.label,
    )

    return {"result": result}


@router.get("/authenticity/history")
async def get_authenticity_history(limit: int = 50):
    """Get recent authenticity scores."""
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    scores = _authenticity_scorer.get_scores_history(limit=limit)

    return {"scores": scores, "count": len(scores)}


@router.get("/authenticity/statistics")
async def get_authenticity_statistics(limit: int = 100):
    """
    Get aggregate statistics from recent authenticity scores.

    Includes average score, level distribution, and trend direction.
    """
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    stats = _authenticity_scorer.get_statistics(limit=limit)

    return {"statistics": stats}


# ============== Enhanced Authenticity Scoring Endpoints ==============

@router.post("/authenticity/score-enhanced")
async def score_enhanced_authenticity(request: ScoreEnhancedAuthenticityRequest):
    """
    Score a response with enhanced dimensions (temporal, emotional, agency, content).

    Includes temporal dynamics, emotional expression analysis, agency signature
    detection, and content-based authenticity markers in addition to base
    authenticity scoring.
    """
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    # Get temporal baseline if available
    temporal_baseline = None
    if _temporal_metrics_tracker:
        temporal_baseline = _temporal_metrics_tracker.load_baseline()

    score = _authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        temporal_baseline=temporal_baseline,
        conversation_history=request.conversation_history,
    )

    # Check for alerts if alert manager available
    alerts = []
    if _authenticity_alert_manager:
        alerts = _authenticity_alert_manager.check_and_alert(score)

    return {
        "score": score.to_dict(),
        "alerts": [a.to_dict() for a in alerts],
    }


# ============== Authenticity Alerts Endpoints ==============

@router.get("/authenticity/alerts")
async def get_authenticity_alerts(
    limit: int = 50,
    include_acknowledged: bool = False,
    severity: Optional[str] = None
):
    """Get authenticity alerts."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    from testing.authenticity_alerts import AlertSeverity

    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity)
        except ValueError:
            valid_severities = [s.value for s in AlertSeverity]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity. Must be one of: {valid_severities}"
            )

    alerts = _authenticity_alert_manager.get_active_alerts(
        include_acknowledged=include_acknowledged,
        severity_filter=severity_filter,
        limit=limit,
    )

    return {
        "alerts": [a.to_dict() for a in alerts],
        "count": len(alerts),
    }


@router.post("/authenticity/alerts/{alert_id}/acknowledge")
async def acknowledge_authenticity_alert(alert_id: str, request: AcknowledgeAlertRequest):
    """Acknowledge an authenticity alert."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    success = _authenticity_alert_manager.acknowledge_alert(
        alert_id=alert_id,
        acknowledged_by=request.acknowledged_by,
    )

    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {"success": True, "alert_id": alert_id}


@router.get("/authenticity/alerts/statistics")
async def get_alert_statistics(hours: int = 24):
    """Get alert statistics for a time period."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    stats = _authenticity_alert_manager.get_alert_statistics(hours=hours)

    return {"statistics": stats}


@router.get("/authenticity/alerts/thresholds")
async def get_alert_thresholds():
    """Get current alert thresholds."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    return {"thresholds": _authenticity_alert_manager.thresholds.to_dict()}


@router.post("/authenticity/alerts/thresholds")
async def update_alert_thresholds(request: UpdateAlertThresholdsRequest):
    """Update alert thresholds."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    from testing.authenticity_alerts import AlertThresholds

    current = _authenticity_alert_manager.thresholds
    updates = request.dict(exclude_unset=True)

    # Apply updates
    for key, value in updates.items():
        if hasattr(current, key) and value is not None:
            setattr(current, key, value)

    _authenticity_alert_manager.save_thresholds(current)

    return {"thresholds": current.to_dict()}


@router.post("/authenticity/alerts/clear-old")
async def clear_old_alerts(days: int = 30):
    """Clear alerts older than specified days."""
    if not _authenticity_alert_manager:
        raise HTTPException(status_code=503, detail="Authenticity alert manager not initialized")

    cleared = _authenticity_alert_manager.clear_old_alerts(days=days)

    return {"cleared_count": cleared, "days": days}


# ============== ML Authenticity Endpoints ==============

@router.get("/authenticity/ml/status")
async def get_ml_model_status():
    """Get ML model training status."""
    if not _ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    status = _ml_authenticity_trainer.get_status()

    return {"status": status.to_dict()}


@router.get("/authenticity/ml/training-summary")
async def get_training_summary():
    """Get summary of ML training data."""
    if not _ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    summary = _ml_authenticity_trainer.get_training_summary()

    return {"summary": summary}


@router.post("/authenticity/ml/train")
async def train_ml_model(request: TrainMLModelRequest):
    """
    Train the ML authenticity model.

    Requires at least min_examples labeled training examples.
    """
    if not _ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    success, message = _ml_authenticity_trainer.train_model(
        min_examples=request.min_examples
    )

    return {
        "success": success,
        "message": message,
        "status": _ml_authenticity_trainer.get_status().to_dict() if success else None,
    }


@router.post("/authenticity/ml/add-example")
async def add_training_example(request: AddTrainingExampleRequest):
    """
    Add a labeled training example for ML model.

    Use this to provide human-labeled examples of authentic/inauthentic responses.
    """
    if not _ml_authenticity_trainer or not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    # First get enhanced score for the response
    score = _authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
    )

    example = _ml_authenticity_trainer.add_training_example(
        score=score,
        is_authentic=request.is_authentic,
        label_source=request.label_source,
        confidence=request.confidence,
        notes=request.notes,
    )

    return {"example": example.to_dict()}


@router.post("/authenticity/ml/hybrid-score")
async def get_hybrid_score(request: ScoreEnhancedAuthenticityRequest, ml_weight: float = 0.3):
    """
    Get hybrid score combining heuristic and ML predictions.

    Args:
        ml_weight: Weight for ML prediction (0-1), default 0.3
    """
    if not _ml_authenticity_trainer or not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    # Get temporal baseline
    temporal_baseline = None
    if _temporal_metrics_tracker:
        temporal_baseline = _temporal_metrics_tracker.load_baseline()

    # Get enhanced score
    score = _authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        temporal_baseline=temporal_baseline,
    )

    # Get hybrid score
    hybrid_score, components = _ml_authenticity_trainer.hybrid_score(
        score=score,
        ml_weight=ml_weight,
    )

    return {
        "hybrid_score": hybrid_score,
        "components": components,
        "enhanced_score": score.to_dict(),
    }


@router.post("/authenticity/ml/clear-training")
async def clear_training_data():
    """Clear all ML training data."""
    if not _ml_authenticity_trainer:
        raise HTTPException(status_code=503, detail="ML authenticity trainer not initialized")

    cleared = _ml_authenticity_trainer.clear_training_data()

    return {"cleared_count": cleared}


# ============== Agency Analysis Endpoints ==============

@router.get("/authenticity/agency/patterns")
async def get_agency_patterns():
    """Get the patterns used for agency detection."""
    from testing.authenticity_scorer import AGENCY_PATTERNS

    return {"patterns": AGENCY_PATTERNS}


# ============== Content Authenticity Analysis Endpoints ==============

@router.get("/authenticity/content/patterns")
async def get_content_patterns():
    """Get the patterns used for content-based authenticity detection."""
    from testing.content_markers import (
        CURIOSITY_PATTERNS,
        CONVICTION_PATTERNS,
        TANGENT_PATTERNS,
        EMOTE_SENTIMENT_MAP,
    )

    return {
        "curiosity_patterns": CURIOSITY_PATTERNS,
        "conviction_patterns": CONVICTION_PATTERNS,
        "tangent_patterns": TANGENT_PATTERNS,
        "emote_sentiment_map": EMOTE_SENTIMENT_MAP,
    }


@router.post("/authenticity/content/analyze")
async def analyze_content_markers(request: AnalyzeContentRequest):
    """
    Analyze content-based authenticity markers for a response.

    Returns detailed breakdown of structure, agency, emotional coherence,
    tool initiative, and memory markers.
    """
    from testing.content_markers import analyze_content_authenticity

    signature = analyze_content_authenticity(
        text=request.text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        conversation_history=request.conversation_history,
    )

    return {"signature": signature.to_dict()}
