"""
Testing API - Pre-Deployment Validation Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter(tags=["testing-deployment"])

# Module-level reference - set by init function
_pre_deploy_validator = None


def init_deployment(pre_deploy_validator):
    """Initialize module dependencies."""
    global _pre_deploy_validator
    _pre_deploy_validator = pre_deploy_validator


# ============== Pydantic Models ==============

class ValidateDeploymentRequest(BaseModel):
    strictness: Optional[str] = None
    override: bool = False
    override_reason: Optional[str] = None


# ============== Pre-Deployment Validation Endpoints ==============

@router.post("/deploy/validate")
async def validate_deployment(request: ValidateDeploymentRequest):
    """
    Run pre-deployment validation with configurable strictness.

    Returns detailed report with gates, recommendations, and deployment approval status.
    """
    if not _pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    from testing.pre_deploy import StrictnessLevel

    strictness = None
    if request.strictness:
        try:
            strictness = StrictnessLevel(request.strictness)
        except ValueError:
            valid_levels = [level.value for level in StrictnessLevel]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {valid_levels}"
            )

    report = _pre_deploy_validator.validate(
        strictness=strictness,
        override=request.override,
        override_reason=request.override_reason,
    )

    return {"report": report.to_dict()}


@router.post("/deploy/validate/markdown")
async def validate_deployment_markdown(request: ValidateDeploymentRequest):
    """
    Run pre-deployment validation and return a human-readable markdown report.
    """
    if not _pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    from testing.pre_deploy import StrictnessLevel

    strictness = None
    if request.strictness:
        try:
            strictness = StrictnessLevel(request.strictness)
        except ValueError:
            valid_levels = [level.value for level in StrictnessLevel]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strictness level. Must be one of: {valid_levels}"
            )

    report = _pre_deploy_validator.validate(
        strictness=strictness,
        override=request.override,
        override_reason=request.override_reason,
    )

    return {"markdown": report.to_markdown()}


@router.get("/deploy/quick")
async def quick_deploy_check():
    """
    Quick deployment readiness check.

    Runs minimal validation for fast feedback during development.
    """
    if not _pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    result = _pre_deploy_validator.quick_check()

    return result


@router.get("/deploy/history")
async def get_validation_history(limit: int = 20):
    """Get recent validation reports."""
    if not _pre_deploy_validator:
        raise HTTPException(status_code=503, detail="Pre-deployment validator not initialized")

    reports = _pre_deploy_validator.get_reports_history(limit=limit)

    return {"reports": reports, "count": len(reports)}


@router.get("/deploy/strictness-levels")
async def get_strictness_levels():
    """Get available strictness levels and their descriptions."""
    from testing.pre_deploy import StrictnessLevel

    return {
        "levels": [
            {
                "value": StrictnessLevel.STRICT.value,
                "description": "All tests must pass, no warnings allowed. Use for production deployments.",
            },
            {
                "value": StrictnessLevel.NORMAL.value,
                "description": "Critical tests must pass, warnings allowed. Default for most deployments.",
            },
            {
                "value": StrictnessLevel.LENIENT.value,
                "description": "Only critical failures block. Use for development/staging.",
            },
            {
                "value": StrictnessLevel.BYPASS.value,
                "description": "Skip validation (emergency only). Requires override reason.",
            },
        ]
    }


@router.get("/deploy/git-hook")
async def get_git_hook_script():
    """
    Get a pre-commit git hook script for automated validation.

    Install this in .git/hooks/pre-commit to validate before each commit.
    """
    from testing.pre_deploy import generate_git_hook_script

    script = generate_git_hook_script()

    return {"script": script, "install_path": ".git/hooks/pre-commit"}


@router.get("/deploy/ci-config")
async def get_ci_config():
    """
    Get CI/CD configuration for automated deployment validation.

    Returns a configuration that can be adapted to GitHub Actions, GitLab CI, etc.
    """
    from testing.pre_deploy import generate_ci_config

    config = generate_ci_config()

    return config
