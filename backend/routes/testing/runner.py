"""
Testing API - Test Runner Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["testing-runner"])

# Module-level reference - set by init function
_test_runner = None


def init_runner(test_runner):
    """Initialize module dependencies."""
    global _test_runner
    _test_runner = test_runner


# ============== Pydantic Models ==============

class RunTestSuiteRequest(BaseModel):
    label: str = "test_run"


class RunCategoryTestRequest(BaseModel):
    category: str
    label: str = "category_test"


# ============== Test Runner Endpoints ==============

@router.post("/run")
async def run_full_test_suite(request: RunTestSuiteRequest):
    """
    Run the complete consciousness test suite.

    Returns comprehensive results including pass/fail status,
    deployment safety assessment, and confidence score.
    """
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    result = _test_runner.run_full_suite(label=request.label)

    return {"result": result.to_dict()}


@router.post("/run/markdown")
async def run_full_test_suite_markdown(request: RunTestSuiteRequest):
    """
    Run the complete test suite and return a human-readable markdown report.
    """
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    result = _test_runner.run_full_suite(label=request.label)

    return {"markdown": result.to_markdown()}


@router.post("/run/category")
async def run_category_tests(request: RunCategoryTestRequest):
    """
    Run tests for a specific category.

    Categories: fingerprint, memory, authenticity, drift
    """
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    valid_categories = ["fingerprint", "memory", "authenticity", "drift"]
    if request.category not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Must be one of: {valid_categories}"
        )

    result = _test_runner.run_category(request.category, label=request.label)

    return {"result": result.to_dict()}


@router.get("/run/history")
async def get_test_history(limit: int = 20):
    """Get recent test suite results."""
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    results = _test_runner.get_results_history(limit=limit)

    return {"results": results, "count": len(results)}


@router.get("/run/tests")
async def list_registered_tests():
    """List all registered consciousness tests."""
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    tests = _test_runner.list_tests()

    return {"tests": tests, "count": len(tests)}


@router.get("/run/quick")
async def quick_health_check():
    """
    Quick health check - runs a minimal subset of critical tests.

    Useful for frequent checks without full suite overhead.
    """
    if not _test_runner:
        raise HTTPException(status_code=503, detail="Test runner not initialized")

    # Just run fingerprint tests for quick check
    result = _test_runner.run_category("fingerprint", label="quick_check")

    return {
        "healthy": result.deployment_safe,
        "confidence": result.confidence_score,
        "summary": result.summary,
        "passed": result.passed,
        "failed": result.failed,
        "warnings": result.warnings,
    }
