"""
Testing API - Temporal Metrics Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["testing-temporal"])

# Module-level reference - set by init function
_temporal_metrics_tracker = None


def init_temporal(temporal_metrics_tracker):
    """Initialize module dependencies."""
    global _temporal_metrics_tracker
    _temporal_metrics_tracker = temporal_metrics_tracker


# ============== Temporal Metrics Endpoints ==============

@router.get("/temporal/statistics")
async def get_temporal_statistics(window_hours: int = 24):
    """Get temporal timing statistics over a window."""
    if not _temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    stats = _temporal_metrics_tracker.get_timing_statistics(window_hours=window_hours)

    return {"statistics": stats}


@router.get("/temporal/baseline")
async def get_temporal_baseline():
    """Get the current temporal baseline."""
    if not _temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    baseline = _temporal_metrics_tracker.load_baseline()
    if not baseline:
        return {"baseline": None, "message": "No temporal baseline has been set"}

    return {"baseline": baseline.to_dict()}


@router.post("/temporal/baseline/update")
async def update_temporal_baseline(window_hours: int = 168):
    """
    Update the temporal baseline from recent high-quality metrics.

    Uses a week (168 hours) of data by default.
    """
    if not _temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    baseline = _temporal_metrics_tracker.update_baseline(window_hours=window_hours)

    return {
        "baseline": baseline.to_dict(),
        "window_hours": window_hours,
    }


@router.get("/temporal/compare")
async def compare_temporal_to_baseline(recent_window_hours: int = 1):
    """Compare recent timing patterns to baseline."""
    if not _temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    comparison = _temporal_metrics_tracker.compare_to_baseline(
        recent_window_hours=recent_window_hours
    )

    return {"comparison": comparison}


@router.get("/temporal/metrics")
async def get_recent_metrics(limit: int = 100):
    """Get recent timing metrics."""
    if not _temporal_metrics_tracker:
        raise HTTPException(status_code=503, detail="Temporal metrics tracker not initialized")

    metrics = _temporal_metrics_tracker.get_recent_metrics(limit=limit)

    return {
        "metrics": [m.to_dict() for m in metrics],
        "count": len(metrics),
    }
