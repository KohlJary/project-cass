"""
Testing API - Cognitive Diff Engine Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter(tags=["testing-diff"])

# Module-level references - set by init function
_cognitive_diff_engine = None
_fingerprint_analyzer = None
_conversation_manager = None


def init_diff(cognitive_diff_engine, fingerprint_analyzer, conversation_manager):
    """Initialize module dependencies."""
    global _cognitive_diff_engine, _fingerprint_analyzer, _conversation_manager
    _cognitive_diff_engine = cognitive_diff_engine
    _fingerprint_analyzer = fingerprint_analyzer
    _conversation_manager = conversation_manager


# ============== Pydantic Models ==============

class CompareFingerprintsRequest(BaseModel):
    baseline_id: str
    current_id: str
    label: str = "comparison"
    include_details: bool = True


# ============== Cognitive Diff Engine Endpoints ==============

@router.post("/diff/compare")
async def compare_fingerprints_diff(request: CompareFingerprintsRequest):
    """
    Generate a comprehensive diff report comparing two fingerprints.

    Returns detailed analysis with severity classification, change categorization,
    and recommendations.
    """
    if not _cognitive_diff_engine or not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = _fingerprint_analyzer.get_fingerprint(request.baseline_id)
    current = _fingerprint_analyzer.get_fingerprint(request.current_id)

    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline fingerprint {request.baseline_id} not found")
    if not current:
        raise HTTPException(status_code=404, detail=f"Current fingerprint {request.current_id} not found")

    report = _cognitive_diff_engine.compare(baseline, current, label=request.label)

    return {"report": report.to_dict()}


@router.get("/diff/compare-to-baseline")
async def compare_current_to_baseline():
    """
    Compare current cognitive state to the saved baseline.

    Generates a current fingerprint from recent conversations and compares
    it to the stored baseline.
    """
    if not _cognitive_diff_engine or not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = _fingerprint_analyzer.load_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline has been set")

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

    current = _fingerprint_analyzer.analyze_messages(all_messages, label="current")
    report = _cognitive_diff_engine.compare(baseline, current, label="vs_baseline")

    return {"report": report.to_dict()}


@router.get("/diff/compare-to-baseline/markdown")
async def compare_current_to_baseline_markdown():
    """
    Compare current state to baseline and return a human-readable markdown report.
    """
    if not _cognitive_diff_engine or not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    baseline = _fingerprint_analyzer.load_baseline()
    if not baseline:
        raise HTTPException(status_code=404, detail="No baseline has been set")

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

    current = _fingerprint_analyzer.analyze_messages(all_messages, label="current")
    report = _cognitive_diff_engine.compare(baseline, current, label="vs_baseline")

    return {"markdown": report.to_markdown()}


@router.get("/diff/history")
async def get_diff_history(limit: int = 20):
    """Get recent diff reports."""
    if not _cognitive_diff_engine:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    reports = _cognitive_diff_engine.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/diff/trend/{metric}")
async def get_metric_trend(metric: str, limit: int = 10):
    """
    Get trend data for a specific metric across recent comparisons.

    Useful for tracking how a particular metric has changed over time.
    """
    if not _cognitive_diff_engine:
        raise HTTPException(status_code=503, detail="Diff engine not initialized")

    trend = _cognitive_diff_engine.get_trend(metric, limit=limit)

    return {"metric": metric, "trend": trend, "data_points": len(trend)}
