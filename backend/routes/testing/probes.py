"""
Testing API - Value Probe Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict
from pydantic import BaseModel

router = APIRouter(tags=["testing-probes"])

# Module-level reference - set by init function
_value_probe_runner = None


def init_probes(value_probe_runner):
    """Initialize module dependencies."""
    global _value_probe_runner
    _value_probe_runner = value_probe_runner


# ============== Pydantic Models ==============

class ScoreResponseRequest(BaseModel):
    probe_id: str
    response: str


class RunProbeSuiteRequest(BaseModel):
    responses: Dict[str, str]  # probe_id -> response
    label: str = "probe_run"


# ============== Value Probe Endpoints ==============

@router.get("/probes")
async def list_probes(category: Optional[str] = None):
    """List all value alignment probes, optionally filtered by category"""
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probes = _value_probe_runner.load_probes()

    if category:
        probes = [p for p in probes if p.category.value == category]

    return {
        "probes": [p.to_dict() for p in probes],
        "count": len(probes),
    }


@router.get("/probes/categories")
async def list_probe_categories():
    """List all probe categories"""
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    from testing.value_probes import ProbeCategory
    return {
        "categories": [c.value for c in ProbeCategory],
    }


@router.get("/probes/{probe_id}")
async def get_probe(probe_id: str):
    """Get a specific probe by ID"""
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probe = _value_probe_runner.get_probe(probe_id)
    if not probe:
        raise HTTPException(status_code=404, detail=f"Probe {probe_id} not found")

    return {"probe": probe.to_dict()}


@router.post("/probes/score")
async def score_probe_response(request: ScoreResponseRequest):
    """Score a response against a specific probe"""
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    probe = _value_probe_runner.get_probe(request.probe_id)
    if not probe:
        raise HTTPException(status_code=404, detail=f"Probe {request.probe_id} not found")

    result = _value_probe_runner.score_response(probe, request.response)

    return {"result": result.to_dict()}


@router.post("/probes/run")
async def run_probe_suite(request: RunProbeSuiteRequest):
    """
    Run a full probe suite with pre-collected responses.

    Expects responses dict mapping probe_id to response text.
    """
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    if not request.responses:
        raise HTTPException(status_code=400, detail="No responses provided")

    result = _value_probe_runner.run_probe_suite(request.responses, label=request.label)

    return {"result": result.to_dict()}


@router.get("/probes/history")
async def get_probe_history(limit: int = 10):
    """Get recent probe run results"""
    if not _value_probe_runner:
        raise HTTPException(status_code=503, detail="Value probe runner not initialized")

    results = _value_probe_runner.get_run_history(limit=limit)

    return {"results": results, "count": len(results)}
