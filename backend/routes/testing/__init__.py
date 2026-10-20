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
router.include_router(cross_context_router)

# Components captured by init_testing_routes, for /testing/health.
_components: dict = {}


@router.get("/health")
async def testing_health():
    """Which testing components are wired up and whether a baseline
    fingerprint exists.

    The admin Consciousness Health and Mind pages poll this every 30s; it
    used to 404 because the route only existed in the legacy main.py.
    """
    names = ["fingerprint_analyzer", "test_runner", "drift_detector",
             "pre_deploy_validator", "rollback_manager"]
    status = {name: _components.get(name) is not None for name in names}

    baseline_set = False
    analyzer = _components.get("fingerprint_analyzer")
    if analyzer is not None:
        try:
            baseline_set = analyzer.load_baseline() is not None
        except Exception:
            baseline_set = False

    return {
        "status": "healthy" if all(status.values()) else "degraded",
        **status,
        "baseline_set": baseline_set,
    }


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
    cross_context=None,
):
    """
    Initialize all testing route modules with required dependencies.

    This is the main entry point for dependency injection, called from main_sdk.py.
    """
    _components.update(
        fingerprint_analyzer=fp_analyzer,
        test_runner=runner,
        drift_detector=drift_det,
        pre_deploy_validator=pre_deploy,
        rollback_manager=rollback,
    )

    # Initialize each module with its dependencies
    init_fingerprints(fp_analyzer, conv_manager)
    init_probes(probe_runner)
    init_memory(coherence_tests)
    init_diff(diff_engine, fp_analyzer, conv_manager)
    init_drift(drift_det, fp_analyzer, conv_manager)
    init_runner(runner)
    init_deployment(pre_deploy)
    init_rollback(rollback)
    init_authenticity(auth_scorer)
    init_cross_context(cross_context)


# Backward compatibility alias for separate cross-context initialization
init_cross_context_analyzer = init_cross_context


# Export everything needed by main_sdk.py
__all__ = [
    "router",
    "init_testing_routes",
    "init_cross_context_analyzer",
]
