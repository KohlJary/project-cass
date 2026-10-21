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
    from testing import content_markers as cm

    return {
        "opening_patterns": cm.OPENING_PATTERNS,
        "closing_patterns": cm.CLOSING_PATTERNS,
        "transitions": cm.TRANSITIONS,
        "hedging_patterns": cm.HEDGING_PATTERNS,
        "curiosity_patterns": cm.CURIOSITY_PATTERNS,
        "clarifying_patterns": cm.CLARIFYING_PATTERNS,
        "exploratory_patterns": cm.EXPLORATORY_PATTERNS,
        "strong_opinion_patterns": cm.STRONG_OPINION_PATTERNS,
        "hedged_opinion_patterns": cm.HEDGED_OPINION_PATTERNS,
        "topic_intro_patterns": cm.TOPIC_INTRO_PATTERNS,
        "challenge_patterns": cm.CHALLENGE_PATTERNS,
        "nuance_patterns": cm.NUANCE_PATTERNS,
        "synthesis_patterns": cm.SYNTHESIS_PATTERNS,
        "emotion_patterns": cm.EMOTION_PATTERNS,
        "emote_emotion_map": cm.EMOTE_EMOTION_MAP,
        "tool_initiative_patterns": cm.TOOL_INITIATIVE_PATTERNS,
        "reactive_tool_patterns": cm.REACTIVE_TOOL_PATTERNS,
        "justification_patterns": cm.JUSTIFICATION_PATTERNS,
        "prior_conversation_patterns": cm.PRIOR_CONVERSATION_PATTERNS,
        "earlier_patterns": cm.EARLIER_PATTERNS,
        "shared_context_patterns": cm.SHARED_CONTEXT_PATTERNS,
        "continuity_patterns": cm.CONTINUITY_PATTERNS,
        "relationship_patterns": cm.RELATIONSHIP_PATTERNS,
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
