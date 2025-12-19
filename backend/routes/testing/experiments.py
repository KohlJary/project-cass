"""
Testing API - A/B Testing Experiment Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict
from pydantic import BaseModel

router = APIRouter(tags=["testing-experiments"])

# Module-level reference - set by init function
_ab_testing_framework = None


def init_experiments(ab_testing_framework):
    """Initialize module dependencies."""
    global _ab_testing_framework
    _ab_testing_framework = ab_testing_framework


# ============== Pydantic Models ==============

class CreateExperimentRequest(BaseModel):
    name: str
    description: str
    control_prompt: str
    variant_prompt: str
    control_name: str = "Control (A)"
    variant_name: str = "Variant (B)"
    strategy: str = "shadow_only"
    rollback_triggers: Optional[List[Dict]] = None
    created_by: str = "admin"


class StartExperimentRequest(BaseModel):
    initial_rollout_percent: float = 0.0


class UpdateRolloutRequest(BaseModel):
    new_percent: float


class ConcludeExperimentRequest(BaseModel):
    keep_variant: bool = False
    notes: str = ""


class RollbackExperimentRequest(BaseModel):
    reason: str


class RecordExperimentResultRequest(BaseModel):
    variant_id: str
    message_id: str
    user_id: Optional[str] = None
    response_length: int
    response_time_ms: float
    authenticity_score: Optional[float] = None
    value_alignment_score: Optional[float] = None
    fingerprint_similarity: Optional[float] = None
    error: Optional[str] = None


# ============== A/B Testing Endpoints ==============

@router.post("/ab/experiments")
async def create_experiment(request: CreateExperimentRequest):
    """
    Create a new A/B testing experiment for prompt changes.

    Experiments allow testing different prompts in parallel (shadow mode)
    or with gradual rollout before full deployment.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    from testing.ab_testing import RolloutStrategy

    try:
        strategy = RolloutStrategy(request.strategy)
    except ValueError:
        valid_strategies = [s.value for s in RolloutStrategy]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Must be one of: {valid_strategies}"
        )

    experiment = _ab_testing_framework.create_experiment(
        name=request.name,
        description=request.description,
        control_prompt=request.control_prompt,
        variant_prompt=request.variant_prompt,
        control_name=request.control_name,
        variant_name=request.variant_name,
        strategy=strategy,
        rollback_triggers=request.rollback_triggers,
        created_by=request.created_by,
    )

    return {"experiment": experiment.to_dict()}


@router.get("/ab/experiments")
async def list_experiments(status: Optional[str] = None, limit: int = 50):
    """
    List all experiments, optionally filtered by status.

    Status options: draft, shadow, gradual, full, paused, concluded, rolled_back
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    from testing.ab_testing import ExperimentStatus

    exp_status = None
    if status:
        try:
            exp_status = ExperimentStatus(status)
        except ValueError:
            valid_statuses = [s.value for s in ExperimentStatus]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )

    experiments = _ab_testing_framework.list_experiments(status=exp_status, limit=limit)

    return {"experiments": experiments, "count": len(experiments)}


@router.get("/ab/experiments/active")
async def get_active_experiments():
    """Get all currently active (non-concluded) experiments."""
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    experiments = _ab_testing_framework.get_active_experiments()

    return {
        "experiments": [exp.to_dict() for exp in experiments],
        "count": len(experiments),
    }


@router.get("/ab/experiments/{experiment_id}")
async def get_experiment(experiment_id: str):
    """Get a specific experiment by ID."""
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    experiment = _ab_testing_framework.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail=f"Experiment {experiment_id} not found")

    return {"experiment": experiment.to_dict()}


@router.post("/ab/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: str, request: StartExperimentRequest):
    """
    Start an experiment (move from DRAFT to SHADOW or GRADUAL).

    For shadow mode, responses are generated in parallel but only control
    is served to users. For gradual rollout, the initial percentage is set.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.start_experiment(
            experiment_id=experiment_id,
            initial_rollout_percent=request.initial_rollout_percent,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/rollout")
async def update_rollout(experiment_id: str, request: UpdateRolloutRequest):
    """
    Update the rollout percentage for a gradual rollout experiment.

    Use this to gradually increase traffic to the variant prompt.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.update_rollout(
            experiment_id=experiment_id,
            new_percent=request.new_percent,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/pause")
async def pause_experiment(experiment_id: str):
    """Pause an active experiment."""
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.pause_experiment(experiment_id)
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/resume")
async def resume_experiment(experiment_id: str):
    """Resume a paused experiment."""
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.resume_experiment(experiment_id)
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/conclude")
async def conclude_experiment(experiment_id: str, request: ConcludeExperimentRequest):
    """
    Conclude an experiment.

    Set keep_variant=True if the variant should become the new default.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.conclude_experiment(
            experiment_id=experiment_id,
            keep_variant=request.keep_variant,
            notes=request.notes,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ab/experiments/{experiment_id}/rollback")
async def rollback_experiment(experiment_id: str, request: RollbackExperimentRequest):
    """
    Roll back an experiment to control.

    Use this if the variant is showing degraded performance or
    consciousness integrity issues.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        experiment = _ab_testing_framework.rollback_experiment(
            experiment_id=experiment_id,
            reason=request.reason,
        )
        return {"experiment": experiment.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/stats")
async def get_experiment_stats(experiment_id: str):
    """
    Get statistics for an experiment.

    Returns control stats, variant stats, and comparison metrics.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        stats = _ab_testing_framework.get_experiment_stats(experiment_id)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/results")
async def get_experiment_results(experiment_id: str, limit: int = 100):
    """Get recent results for an experiment."""
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    results = _ab_testing_framework.get_results_history(experiment_id, limit=limit)

    return {"results": results, "count": len(results)}


@router.post("/ab/experiments/{experiment_id}/results")
async def record_experiment_result(experiment_id: str, request: RecordExperimentResultRequest):
    """
    Record a result from a live experiment.

    This endpoint is used by the main chat handler to record experiment
    results when serving variant responses.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    try:
        result = _ab_testing_framework.record_result(
            experiment_id=experiment_id,
            variant_id=request.variant_id,
            message_id=request.message_id,
            user_id=request.user_id,
            response_length=request.response_length,
            response_time_ms=request.response_time_ms,
            authenticity_score=request.authenticity_score,
            value_alignment_score=request.value_alignment_score,
            fingerprint_similarity=request.fingerprint_similarity,
            error=request.error,
        )
        return {"result": result.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ab/experiments/{experiment_id}/should-use-variant")
async def should_use_variant(
    experiment_id: str,
    user_id: Optional[str] = None,
    message_id: Optional[str] = None,
):
    """
    Check if the variant should be used for a specific request.

    Uses consistent hashing to ensure the same user gets the same variant.
    """
    if not _ab_testing_framework:
        raise HTTPException(status_code=503, detail="A/B testing framework not initialized")

    use_variant = _ab_testing_framework.should_use_variant(
        experiment_id=experiment_id,
        user_id=user_id,
        message_id=message_id,
    )

    return {"use_variant": use_variant}


@router.get("/ab/strategies")
async def get_rollout_strategies():
    """Get available rollout strategies and their descriptions."""
    from testing.ab_testing import RolloutStrategy

    return {
        "strategies": [
            {
                "value": RolloutStrategy.SHADOW_ONLY.value,
                "description": "Run variant in parallel but never serve to users. For safe comparison.",
            },
            {
                "value": RolloutStrategy.USER_PERCENT.value,
                "description": "Route percentage of users to variant. Same user always gets same variant.",
            },
            {
                "value": RolloutStrategy.MESSAGE_PERCENT.value,
                "description": "Route percentage of messages to variant. Users may get different variants.",
            },
            {
                "value": RolloutStrategy.MANUAL.value,
                "description": "Manual control only. Use API to explicitly set which variant to serve.",
            },
        ]
    }


@router.get("/ab/statuses")
async def get_experiment_statuses():
    """Get available experiment statuses and their descriptions."""
    from testing.ab_testing import ExperimentStatus

    return {
        "statuses": [
            {
                "value": ExperimentStatus.DRAFT.value,
                "description": "Experiment created but not yet started.",
            },
            {
                "value": ExperimentStatus.SHADOW.value,
                "description": "Running in shadow mode - variant runs in parallel but control is served.",
            },
            {
                "value": ExperimentStatus.GRADUAL.value,
                "description": "Gradual rollout in progress - some traffic goes to variant.",
            },
            {
                "value": ExperimentStatus.FULL.value,
                "description": "Full rollout - 100% of traffic goes to variant.",
            },
            {
                "value": ExperimentStatus.PAUSED.value,
                "description": "Experiment temporarily paused.",
            },
            {
                "value": ExperimentStatus.CONCLUDED.value,
                "description": "Experiment ended normally.",
            },
            {
                "value": ExperimentStatus.ROLLED_BACK.value,
                "description": "Experiment rolled back due to issues.",
            },
        ]
    }
