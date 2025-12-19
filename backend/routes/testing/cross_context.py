"""
Testing API - Cross-Context Pattern Analysis Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(tags=["testing-cross-context"])

# Module-level reference - set by init function
_cross_context_analyzer = None


def init_cross_context(cross_context_analyzer):
    """Initialize module dependencies."""
    global _cross_context_analyzer
    _cross_context_analyzer = cross_context_analyzer


# ============== Pydantic Models ==============

class ClassifyContextRequest(BaseModel):
    text: str
    user_message: Optional[str] = None


class RecordSampleRequest(BaseModel):
    response: str
    user_message: Optional[str] = None
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    tool_usage: Optional[List[str]] = None


# ============== Cross-Context Pattern Analysis Endpoints ==============

@router.post("/cross-context/classify")
async def classify_conversation_context(request: ClassifyContextRequest):
    """
    Classify the context type of a conversation or message.

    Returns the primary context (technical, emotional, creative, etc.)
    with confidence and secondary contexts.
    """
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    classification = _cross_context_analyzer.classify_context(
        text=request.text,
        user_message=request.user_message,
    )

    return {"classification": classification.to_dict()}


@router.post("/cross-context/record-sample")
async def record_behavioral_sample(request: RecordSampleRequest):
    """
    Record a behavioral sample for cross-context analysis.

    Classifies the context, extracts behavioral markers, and updates
    the context profile.
    """
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    # Classify context
    classification = _cross_context_analyzer.classify_context(
        text=request.response,
        user_message=request.user_message,
    )

    # Extract behavioral markers
    markers = _cross_context_analyzer.extract_behavioral_markers(
        response=request.response,
        tool_usage=request.tool_usage,
    )

    # Record the sample
    _cross_context_analyzer.record_sample(
        context=classification.primary_context,
        markers=markers,
        conversation_id=request.conversation_id,
        message_id=request.message_id,
    )

    return {
        "context": classification.primary_context.value,
        "confidence": classification.confidence,
        "markers_recorded": True,
    }


@router.get("/cross-context/profiles")
async def get_context_profiles():
    """
    Get behavioral profiles for all contexts.

    Shows how Cass behaves differently across technical, emotional,
    creative, and other conversation types.
    """
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    profiles = _cross_context_analyzer.get_all_profiles()

    return {
        "profiles": {ctx: p.to_dict() for ctx, p in profiles.items()},
        "count": len(profiles),
    }


@router.get("/cross-context/profiles/{context}")
async def get_specific_context_profile(context: str):
    """Get the behavioral profile for a specific context type."""
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    from testing.cross_context_analyzer import ConversationContext

    try:
        ctx = ConversationContext(context)
    except ValueError:
        valid = [c.value for c in ConversationContext]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid context. Valid options: {valid}"
        )

    profile = _cross_context_analyzer.get_context_profile(ctx)
    if not profile:
        raise HTTPException(status_code=404, detail=f"No profile for context: {context}")

    return {"profile": profile.to_dict()}


@router.post("/cross-context/analyze-consistency")
async def analyze_cross_context_consistency():
    """
    Analyze consistency of behavioral patterns across contexts.

    Detects anomalies, identifies concerning divergences, and generates
    research questions for self-reflection.
    """
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    score = _cross_context_analyzer.analyze_consistency()

    return {"consistency": score.to_dict()}


@router.get("/cross-context/consistency-history")
async def get_consistency_history(limit: int = 10):
    """Get recent cross-context consistency analysis reports."""
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    reports = _cross_context_analyzer.get_recent_consistency_reports(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/cross-context/research-questions")
async def get_research_questions():
    """
    Get research questions generated from cross-context analysis.

    These questions can feed into solo reflection sessions or
    research proposal generation.
    """
    if not _cross_context_analyzer:
        raise HTTPException(status_code=503, detail="Cross-context analyzer not initialized")

    # Get most recent consistency analysis
    reports = _cross_context_analyzer.get_recent_consistency_reports(limit=1)

    if not reports:
        return {
            "questions": ["No cross-context analysis has been performed yet."],
            "source": None,
        }

    latest = reports[0]

    return {
        "questions": latest.get("research_questions", []),
        "source_report": latest.get("timestamp"),
        "overall_consistency": latest.get("overall_score"),
    }
