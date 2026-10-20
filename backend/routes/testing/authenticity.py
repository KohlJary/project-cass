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


def init_authenticity(authenticity_scorer):
    """Initialize module dependencies."""
    global _authenticity_scorer
    _authenticity_scorer = authenticity_scorer


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
    Score a response with enhanced dimensions (emotional, agency, content).

    Includes emotional expression analysis, agency signature detection, and
    content-based authenticity markers in addition to base authenticity scoring.
    """
    if not _authenticity_scorer:
        raise HTTPException(status_code=503, detail="Authenticity scorer not initialized")

    score = _authenticity_scorer.score_response_enhanced(
        response_text=request.response_text,
        context=request.context,
        animations=request.animations,
        tool_uses=request.tool_uses,
        conversation_history=request.conversation_history,
    )

    return {"score": score.to_dict()}


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
