"""
Testing API - Personality Drift Detection Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter(tags=["testing-drift"])

# Module-level references - set by init function
_drift_detector = None
_fingerprint_analyzer = None
_conversation_manager = None


def init_drift(drift_detector, fingerprint_analyzer, conversation_manager):
    """Initialize module dependencies."""
    global _drift_detector, _fingerprint_analyzer, _conversation_manager
    _drift_detector = drift_detector
    _fingerprint_analyzer = fingerprint_analyzer
    _conversation_manager = conversation_manager


# ============== Pydantic Models ==============

class TakeSnapshotRequest(BaseModel):
    label: str = "snapshot"


class AnalyzeDriftRequest(BaseModel):
    window_days: int = 30
    label: Optional[str] = None


# ============== Personality Drift Detection Endpoints ==============

@router.post("/drift/snapshot")
async def take_drift_snapshot(request: TakeSnapshotRequest):
    """
    Take a fingerprint snapshot for drift tracking.

    Generates a current fingerprint and saves it as a snapshot for
    long-term trend analysis.
    """
    if not _drift_detector or not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    # Generate current fingerprint
    conv_index = _conversation_manager.list_conversations(limit=50)
    all_messages = []
    for conv_meta in conv_index:
        conv = _conversation_manager.load_conversation(conv_meta.get("id"))
        if conv and conv.messages:
            for msg in conv.messages:
                all_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "conversation_id": conv.id,
                })

    if not all_messages:
        raise HTTPException(status_code=404, detail="No conversation data to analyze")

    fingerprint = _fingerprint_analyzer.analyze_messages(all_messages, label=f"snapshot_{request.label}")
    snapshot = _drift_detector.take_snapshot(fingerprint=fingerprint, label=request.label)

    return {"snapshot": snapshot}


@router.post("/drift/analyze")
async def analyze_drift(request: AnalyzeDriftRequest):
    """
    Analyze personality drift over a time window.

    Returns comprehensive report including metric trends, growth indicators,
    concerning drift patterns, and recommendations.
    """
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    report = _drift_detector.analyze_drift(
        window_days=request.window_days,
        label=request.label,
    )

    return {"report": report.to_dict()}


@router.post("/drift/analyze/markdown")
async def analyze_drift_markdown(request: AnalyzeDriftRequest):
    """
    Analyze personality drift and return a human-readable markdown report.
    """
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    report = _drift_detector.analyze_drift(
        window_days=request.window_days,
        label=request.label,
    )

    return {"markdown": report.to_markdown()}


@router.get("/drift/snapshots")
async def get_drift_snapshots(limit: int = 30):
    """Get recent fingerprint snapshots for drift tracking."""
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    snapshots = _drift_detector.get_snapshots_history(limit=limit)

    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/drift/alerts")
async def get_drift_alerts(limit: int = 20, include_acknowledged: bool = False):
    """Get recent drift alerts."""
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    alerts = _drift_detector.get_alerts_history(limit=limit, include_acknowledged=include_acknowledged)

    return {"alerts": alerts, "count": len(alerts)}


@router.post("/drift/alerts/{alert_id}/acknowledge")
async def acknowledge_drift_alert(alert_id: str):
    """Mark a drift alert as acknowledged."""
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    success = _drift_detector.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return {"success": True, "alert_id": alert_id}


@router.get("/drift/reports")
async def get_drift_reports(limit: int = 10):
    """Get recent drift analysis reports."""
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    reports = _drift_detector.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/drift/metric/{metric_name}")
async def get_metric_history(metric_name: str, limit: int = 50):
    """
    Get history for a specific metric across snapshots.

    Useful for visualizing trends over time.
    """
    if not _drift_detector:
        raise HTTPException(status_code=503, detail="Drift detector not initialized")

    history = _drift_detector.get_metric_history(metric_name, limit=limit)

    return {"metric": metric_name, "history": history, "data_points": len(history)}
