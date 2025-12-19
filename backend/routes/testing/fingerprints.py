"""
Testing API - Fingerprint Analysis Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(tags=["testing-fingerprints"])

# Module-level references - set by init function
_fingerprint_analyzer = None
_conversation_manager = None


def init_fingerprints(fingerprint_analyzer, conversation_manager):
    """Initialize module dependencies."""
    global _fingerprint_analyzer, _conversation_manager
    _fingerprint_analyzer = fingerprint_analyzer
    _conversation_manager = conversation_manager


# ============== Pydantic Models ==============

class GenerateFingerprintRequest(BaseModel):
    label: str = "analysis"
    conversation_ids: Optional[List[str]] = None
    limit: int = 100


class SetBaselineRequest(BaseModel):
    fingerprint_id: str


class CompareFingerprintsRequest(BaseModel):
    fingerprint_ids: List[str]
    include_details: bool = True


# ============== Fingerprint Endpoints ==============

@router.get("/fingerprint/baseline")
async def get_baseline_fingerprint():
    """Get the current baseline fingerprint"""
    if not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    baseline = _fingerprint_analyzer.load_baseline()
    if not baseline:
        return {"baseline": None, "message": "No baseline has been set"}

    return {"baseline": baseline.to_dict()}


@router.get("/fingerprint/current")
async def get_current_fingerprint():
    """Generate a fingerprint from recent conversations"""
    if not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    # Get recent conversations
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

    fingerprint = _fingerprint_analyzer.analyze_messages(all_messages, label="current")

    return {"fingerprint": fingerprint.to_dict()}


@router.post("/fingerprint/generate")
async def generate_fingerprint(request: GenerateFingerprintRequest):
    """Generate a fingerprint from specified or recent conversations"""
    if not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    all_messages = []

    if request.conversation_ids:
        # Analyze specific conversations
        for conv_id in request.conversation_ids:
            conv = _conversation_manager.load_conversation(conv_id)
            if conv and conv.messages:
                for msg in conv.messages:
                    all_messages.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "conversation_id": conv.id,
                    })
    else:
        # Analyze recent conversations
        conv_index = _conversation_manager.list_conversations(limit=request.limit)
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

    fingerprint = _fingerprint_analyzer.analyze_messages(all_messages, label=request.label)
    _fingerprint_analyzer.save_fingerprint(fingerprint)

    return {
        "fingerprint": fingerprint.to_dict(),
        "messages_analyzed": fingerprint.messages_analyzed,
    }


@router.post("/fingerprint/baseline")
async def set_baseline(request: SetBaselineRequest):
    """Set a fingerprint as the baseline"""
    if not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprint = _fingerprint_analyzer.get_fingerprint(request.fingerprint_id)
    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    _fingerprint_analyzer.save_baseline(fingerprint)

    return {
        "success": True,
        "baseline_id": fingerprint.id,
        "baseline_label": fingerprint.label,
    }


@router.get("/fingerprint/compare")
async def compare_to_baseline():
    """Compare current state to baseline"""
    if not _fingerprint_analyzer or not _conversation_manager:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

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
    comparison = _fingerprint_analyzer.compare_fingerprints(baseline, current)

    return {
        "comparison": comparison,
        "baseline": baseline.to_dict(),
        "current": current.to_dict(),
    }


@router.get("/fingerprint/list")
async def list_fingerprints():
    """List all saved fingerprints"""
    if not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprints = _fingerprint_analyzer.load_fingerprints()
    return {"fingerprints": fingerprints, "count": len(fingerprints)}


@router.get("/fingerprint/{fingerprint_id}")
async def get_fingerprint(fingerprint_id: str):
    """Get a specific fingerprint"""
    if not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fingerprint = _fingerprint_analyzer.get_fingerprint(fingerprint_id)
    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    return {"fingerprint": fingerprint.to_dict()}


@router.get("/fingerprint/compare/{id1}/{id2}")
async def compare_fingerprints(id1: str, id2: str):
    """Compare two fingerprints"""
    if not _fingerprint_analyzer:
        raise HTTPException(status_code=503, detail="Testing infrastructure not initialized")

    fp1 = _fingerprint_analyzer.get_fingerprint(id1)
    fp2 = _fingerprint_analyzer.get_fingerprint(id2)

    if not fp1:
        raise HTTPException(status_code=404, detail=f"Fingerprint {id1} not found")
    if not fp2:
        raise HTTPException(status_code=404, detail=f"Fingerprint {id2} not found")

    comparison = _fingerprint_analyzer.compare_fingerprints(fp1, fp2)

    return {"comparison": comparison}
