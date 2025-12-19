"""
Testing API - Rollback Management Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(tags=["testing-rollback"])

# Module-level reference - set by init function
_rollback_manager = None


def init_rollback(rollback_manager):
    """Initialize module dependencies."""
    global _rollback_manager
    _rollback_manager = rollback_manager


# ============== Pydantic Models ==============

class CreateSnapshotRequest(BaseModel):
    label: str
    description: Optional[str] = None
    snapshot_type: str = "cognitive"
    created_by: Optional[str] = None


class RollbackRequest(BaseModel):
    to_snapshot_id: str
    reason: str
    triggered_by: str
    capture_current: bool = True


# ============== Rollback Endpoints ==============

@router.post("/rollback/snapshot")
async def create_snapshot(request: CreateSnapshotRequest):
    """
    Create a state snapshot for potential rollback.

    Snapshots capture the current system state and can be restored later
    if needed.
    """
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    from testing.rollback import SnapshotType

    try:
        snapshot_type = SnapshotType(request.snapshot_type)
    except ValueError:
        valid_types = [t.value for t in SnapshotType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid snapshot type. Must be one of: {valid_types}"
        )

    snapshot = _rollback_manager.create_snapshot(
        label=request.label,
        description=request.description,
        snapshot_type=snapshot_type,
        created_by=request.created_by,
    )

    return {"snapshot": snapshot.to_dict()}


@router.get("/rollback/snapshots")
async def list_snapshots(limit: int = 20):
    """List available state snapshots."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshots = _rollback_manager.list_snapshots(limit=limit)

    return {"snapshots": snapshots, "count": len(snapshots)}


@router.get("/rollback/snapshots/{snapshot_id}")
async def get_snapshot(snapshot_id: str):
    """Get a specific snapshot by ID."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshot = _rollback_manager.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    return {"snapshot": snapshot.to_dict()}


@router.delete("/rollback/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str):
    """Delete a snapshot."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    success = _rollback_manager.delete_snapshot(snapshot_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

    return {"success": True, "deleted_id": snapshot_id}


@router.post("/rollback/execute")
async def execute_rollback(request: RollbackRequest):
    """
    Execute a rollback to a previous state.

    This is a significant operation that restores system state to a
    previous snapshot. Use with caution.
    """
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    from testing.rollback import RollbackTrigger

    operation = _rollback_manager.rollback(
        to_snapshot_id=request.to_snapshot_id,
        reason=request.reason,
        triggered_by=request.triggered_by,
        trigger=RollbackTrigger.MANUAL,
        capture_current=request.capture_current,
    )

    return {"operation": operation.to_dict()}


@router.get("/rollback/operations")
async def list_rollback_operations(limit: int = 20):
    """List rollback operation history."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    operations = _rollback_manager.list_operations(limit=limit)

    return {"operations": operations, "count": len(operations)}


@router.get("/rollback/operations/{operation_id}")
async def get_rollback_operation(operation_id: str):
    """Get details of a specific rollback operation."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    operation = _rollback_manager.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    return {"operation": operation.to_dict()}


@router.get("/rollback/reports")
async def get_rollback_reports(limit: int = 20):
    """Get rollback report history."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    reports = _rollback_manager.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/rollback/latest-good")
async def get_latest_good_snapshot():
    """
    Get the most recent snapshot with good test confidence.

    Useful for quickly finding a safe state to roll back to.
    """
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    snapshot = _rollback_manager.get_latest_good_snapshot()
    if not snapshot:
        return {"snapshot": None, "message": "No snapshot with good confidence found"}

    return {"snapshot": snapshot.to_dict()}


@router.get("/rollback/check-conditions")
async def check_auto_rollback_conditions():
    """
    Check if automatic rollback conditions are met.

    Returns the reason if rollback should be triggered, null otherwise.
    """
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    reason = _rollback_manager.check_auto_rollback_conditions()

    return {
        "should_rollback": reason is not None,
        "reason": reason,
    }


@router.post("/rollback/cleanup")
async def cleanup_old_snapshots():
    """Remove snapshots older than the configured retention period."""
    if not _rollback_manager:
        raise HTTPException(status_code=503, detail="Rollback manager not initialized")

    _rollback_manager.cleanup_old_snapshots()

    return {"success": True, "message": "Old snapshots cleaned up"}


@router.get("/rollback/snapshot-types")
async def get_snapshot_types():
    """Get available snapshot types and their descriptions."""
    from testing.rollback import SnapshotType

    return {
        "types": [
            {
                "value": SnapshotType.FULL.value,
                "description": "Complete system state - all data directories",
            },
            {
                "value": SnapshotType.COGNITIVE.value,
                "description": "Consciousness-related state - testing data and self model",
            },
            {
                "value": SnapshotType.MEMORY.value,
                "description": "Memory and conversation state - conversations, summaries, vector store",
            },
            {
                "value": SnapshotType.CONFIG.value,
                "description": "Configuration files only",
            },
        ]
    }
