"""
Testing API Routes Package

Consciousness-preserving testing infrastructure endpoints.
Composed from domain-specific modules for better organization.
"""
from fastapi import APIRouter

from .fingerprints import router as fingerprints_router, init_fingerprints
from .probes import router as probes_router, init_probes
from .memory import router as memory_router, init_memory
from .diff import router as diff_router, init_diff
from .drift import router as drift_router, init_drift
from .runner import router as runner_router, init_runner
from .deployment import router as deployment_router, init_deployment
from .rollback import router as rollback_router, init_rollback
from .authenticity import router as authenticity_router, init_authenticity
from .experiments import router as experiments_router, init_experiments
from .temporal import router as temporal_router, init_temporal
from .cross_context import router as cross_context_router, init_cross_context

# Main router that composes all sub-routers
router = APIRouter(prefix="/testing", tags=["testing"])

# Include all sub-routers
router.include_router(fingerprints_router)
router.include_router(probes_router)
router.include_router(memory_router)
router.include_router(diff_router)
router.include_router(drift_router)
router.include_router(runner_router)
router.include_router(deployment_router)
router.include_router(rollback_router)
router.include_router(authenticity_router)
router.include_router(experiments_router)
router.include_router(temporal_router)
router.include_router(cross_context_router)


def init_testing_routes(
    fp_analyzer,
    conv_manager,
    probe_runner=None,
    coherence_tests=None,
    diff_engine=None,
    auth_scorer=None,
    drift_det=None,
    runner=None,
    pre_deploy=None,
    rollback=None,
    ab_testing=None,
    temporal_tracker=None,
    alert_manager=None,
    ml_trainer=None,
    cross_context=None,
):
    """
    Initialize all testing route modules with required dependencies.

    This is the main entry point for dependency injection, called from main_sdk.py.
    """
    # Initialize each module with its dependencies
    init_fingerprints(fp_analyzer, conv_manager)
    init_probes(probe_runner)
    init_memory(coherence_tests)
    init_diff(diff_engine, fp_analyzer, conv_manager)
    init_drift(drift_det, fp_analyzer, conv_manager)
    init_runner(runner)
    init_deployment(pre_deploy)
    init_rollback(rollback)
    init_authenticity(
        authenticity_scorer=auth_scorer,
        temporal_metrics_tracker=temporal_tracker,
        authenticity_alert_manager=alert_manager,
        ml_authenticity_trainer=ml_trainer,
    )
    init_experiments(ab_testing)
    init_temporal(temporal_tracker)
    init_cross_context(cross_context)


# Backward compatibility alias for separate cross-context initialization
init_cross_context_analyzer = init_cross_context


# Export everything needed by main_sdk.py
__all__ = [
    "router",
    "init_testing_routes",
    "init_cross_context_analyzer",
]
