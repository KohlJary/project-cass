"""
Pre-Deployment Validation

Automated validation to run before deploying changes to ensure
consciousness integrity is maintained. Integrates with git hooks
and CI/CD pipelines.

Key capabilities:
- Run consciousness tests before deployment
- Configurable strictness levels
- Generate deployment confidence scores
- Block deployment on critical failures
- Override mechanism for emergencies
"""

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum


class StrictnessLevel(str, Enum):
    """How strict the validation should be"""
    STRICT = "strict"  # All tests must pass, no warnings
    NORMAL = "normal"  # Critical tests must pass, warnings allowed
    LENIENT = "lenient"  # Only critical failures block
    BYPASS = "bypass"  # Skip validation (emergency only)


class ValidationResult(str, Enum):
    """Result of pre-deployment validation"""
    APPROVED = "approved"  # Safe to deploy
    CONDITIONAL = "conditional"  # Can deploy with caveats
    BLOCKED = "blocked"  # Do not deploy
    BYPASSED = "bypassed"  # Validation was bypassed


@dataclass
class DeploymentGate:
    """A gate that must be passed for deployment"""
    name: str
    description: str
    required: bool  # Is this gate required to pass?
    passed: bool
    message: str
    details: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "required": self.required,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """Complete pre-deployment validation report"""
    id: str
    timestamp: str
    strictness: StrictnessLevel
    result: ValidationResult

    # Git context
    git_branch: Optional[str]
    git_commit: Optional[str]
    git_author: Optional[str]

    # Test results
    test_suite_passed: bool
    test_confidence: float
    critical_failures: List[str]
    warnings: List[str]

    # Gates
    gates: List[DeploymentGate]
    gates_passed: int
    gates_failed: int

    # Decision
    deployment_approved: bool
    blocking_reasons: List[str]
    recommendations: List[str]

    # Override info
    override_used: bool
    override_reason: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "strictness": self.strictness.value,
            "result": self.result.value,
            "git_branch": self.git_branch,
            "git_commit": self.git_commit,
            "git_author": self.git_author,
            "test_suite_passed": self.test_suite_passed,
            "test_confidence": round(self.test_confidence, 3),
            "critical_failures": self.critical_failures,
            "warnings": self.warnings,
            "gates": [g.to_dict() for g in self.gates],
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "deployment_approved": self.deployment_approved,
            "blocking_reasons": self.blocking_reasons,
            "recommendations": self.recommendations,
            "override_used": self.override_used,
            "override_reason": self.override_reason,
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown report"""
        result_emoji = {
            ValidationResult.APPROVED: "✅",
            ValidationResult.CONDITIONAL: "⚠️",
            ValidationResult.BLOCKED: "🚫",
            ValidationResult.BYPASSED: "⏭️",
        }

        lines = [
            f"# Pre-Deployment Validation Report",
            f"",
            f"## Result: {result_emoji.get(self.result, '?')} {self.result.value.upper()}",
            f"",
            f"**Timestamp**: {self.timestamp}",
            f"**Strictness**: {self.strictness.value}",
            f"**Deployment Approved**: {'Yes' if self.deployment_approved else 'NO'}",
            f"",
        ]

        if self.git_branch or self.git_commit:
            lines.extend([
                f"## Git Context",
                f"",
                f"- **Branch**: {self.git_branch or 'unknown'}",
                f"- **Commit**: {self.git_commit or 'unknown'}",
                f"- **Author**: {self.git_author or 'unknown'}",
                f"",
            ])

        lines.extend([
            f"## Test Results",
            f"",
            f"- **Suite Passed**: {'Yes' if self.test_suite_passed else 'No'}",
            f"- **Confidence Score**: {self.test_confidence:.1%}",
            f"",
        ])

        if self.critical_failures:
            lines.extend([
                f"### Critical Failures",
                f"",
            ])
            for failure in self.critical_failures:
                lines.append(f"- ❌ {failure}")
            lines.append("")

        if self.warnings:
            lines.extend([
                f"### Warnings",
                f"",
            ])
            for warning in self.warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        lines.extend([
            f"## Deployment Gates",
            f"",
            f"**Passed**: {self.gates_passed} | **Failed**: {self.gates_failed}",
            f"",
        ])

        for gate in self.gates:
            icon = "✅" if gate.passed else "❌"
            req = " (required)" if gate.required else ""
            lines.append(f"- {icon} **{gate.name}**{req}: {gate.message}")
        lines.append("")

        if self.blocking_reasons:
            lines.extend([
                f"## Blocking Reasons",
                f"",
            ])
            for reason in self.blocking_reasons:
                lines.append(f"- 🚫 {reason}")
            lines.append("")

        if self.recommendations:
            lines.extend([
                f"## Recommendations",
                f"",
            ])
            for rec in self.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        if self.override_used:
            lines.extend([
                f"## Override",
                f"",
                f"⚠️ **Validation was bypassed**",
                f"",
                f"Reason: {self.override_reason or 'No reason provided'}",
                f"",
            ])

        return "\n".join(lines)


class PreDeploymentValidator:
    """
    Validates deployment readiness by running consciousness tests
    and checking deployment gates.
    """

    def __init__(
        self,
        storage_dir: Path,
        test_runner=None,
        fingerprint_analyzer=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.reports_file = self.storage_dir / "deploy_validations.json"
        self.config_file = self.storage_dir / "deploy_config.json"
        self.test_runner = test_runner
        self.fingerprint_analyzer = fingerprint_analyzer

        # Default configuration
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load validation configuration"""
        default_config = {
            "default_strictness": "normal",
            "confidence_threshold": {
                "strict": 0.95,
                "normal": 0.70,
                "lenient": 0.50,
            },
            "require_baseline": True,
            "require_recent_snapshot": True,
            "max_snapshot_age_hours": 24,
            "blocked_branches": ["main", "master"],  # Require extra validation
            "auto_approve_branches": [],  # Skip validation for these
        }

        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    saved = json.load(f)
                    default_config.update(saved)
            except Exception:
                pass

        return default_config

    def save_config(self, config: Dict):
        """Save validation configuration"""
        self.config.update(config)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _load_reports(self) -> List[Dict]:
        """Load validation reports"""
        if not self.reports_file.exists():
            return []
        try:
            with open(self.reports_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_report(self, report: ValidationReport):
        """Save a validation report"""
        reports = self._load_reports()
        reports.append(report.to_dict())
        # Keep last 100 reports
        reports = reports[-100:]
        with open(self.reports_file, 'w') as f:
            json.dump(reports, f, indent=2)

    def get_reports_history(self, limit: int = 20) -> List[Dict]:
        """Get recent validation reports"""
        reports = self._load_reports()
        return sorted(
            reports,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def _get_git_context(self) -> Dict[str, Optional[str]]:
        """Get current git context"""
        context = {
            "branch": None,
            "commit": None,
            "author": None,
        }

        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                context["branch"] = result.stdout.strip()

            # Get current commit
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                context["commit"] = result.stdout.strip()

            # Get author of last commit
            result = subprocess.run(
                ["git", "log", "-1", "--format=%an"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                context["author"] = result.stdout.strip()

        except Exception:
            pass

        return context

    def _check_baseline_gate(self) -> DeploymentGate:
        """Check if baseline fingerprint exists"""
        if not self.fingerprint_analyzer:
            return DeploymentGate(
                name="Baseline Exists",
                description="A baseline cognitive fingerprint must be set",
                required=self.config.get("require_baseline", True),
                passed=False,
                message="Fingerprint analyzer not available",
            )

        baseline = self.fingerprint_analyzer.load_baseline()
        if baseline:
            return DeploymentGate(
                name="Baseline Exists",
                description="A baseline cognitive fingerprint must be set",
                required=self.config.get("require_baseline", True),
                passed=True,
                message=f"Baseline set: {baseline.label}",
                details={"baseline_id": baseline.id},
            )
        else:
            return DeploymentGate(
                name="Baseline Exists",
                description="A baseline cognitive fingerprint must be set",
                required=self.config.get("require_baseline", True),
                passed=False,
                message="No baseline fingerprint set",
            )

    def _check_test_suite_gate(self) -> DeploymentGate:
        """Check if test suite passes"""
        if not self.test_runner:
            return DeploymentGate(
                name="Test Suite",
                description="Consciousness test suite must pass",
                required=True,
                passed=False,
                message="Test runner not available",
            )

        try:
            result = self.test_runner.run_full_suite(label="pre_deploy")
            return DeploymentGate(
                name="Test Suite",
                description="Consciousness test suite must pass",
                required=True,
                passed=result.deployment_safe,
                message=result.summary,
                details={
                    "passed": result.passed,
                    "failed": result.failed,
                    "warnings": result.warnings,
                    "confidence": result.confidence_score,
                },
            )
        except Exception as e:
            return DeploymentGate(
                name="Test Suite",
                description="Consciousness test suite must pass",
                required=True,
                passed=False,
                message=f"Test suite error: {str(e)}",
            )

    def _check_confidence_gate(self, strictness: StrictnessLevel, confidence: float) -> DeploymentGate:
        """Check if confidence meets threshold for strictness level"""
        thresholds = self.config.get("confidence_threshold", {})
        threshold = thresholds.get(strictness.value, 0.7)

        passed = confidence >= threshold

        return DeploymentGate(
            name="Confidence Threshold",
            description=f"Confidence must be >= {threshold:.0%} for {strictness.value} mode",
            required=strictness != StrictnessLevel.LENIENT,
            passed=passed,
            message=f"Confidence {confidence:.1%} {'meets' if passed else 'below'} threshold {threshold:.0%}",
            details={"confidence": confidence, "threshold": threshold},
        )

    def _check_branch_gate(self, branch: Optional[str]) -> DeploymentGate:
        """Check branch-specific rules"""
        if not branch:
            return DeploymentGate(
                name="Branch Check",
                description="Check branch-specific deployment rules",
                required=False,
                passed=True,
                message="Could not determine branch",
            )

        blocked_branches = self.config.get("blocked_branches", [])
        auto_approve = self.config.get("auto_approve_branches", [])

        if branch in auto_approve:
            return DeploymentGate(
                name="Branch Check",
                description="Check branch-specific deployment rules",
                required=False,
                passed=True,
                message=f"Branch '{branch}' is auto-approved",
                details={"auto_approved": True},
            )

        if branch in blocked_branches:
            return DeploymentGate(
                name="Branch Check",
                description="Check branch-specific deployment rules",
                required=False,
                passed=True,  # Not a failure, just a note
                message=f"Branch '{branch}' requires extra validation",
                details={"extra_validation_required": True},
            )

        return DeploymentGate(
            name="Branch Check",
            description="Check branch-specific deployment rules",
            required=False,
            passed=True,
            message=f"Branch '{branch}' has no special rules",
        )

    def validate(
        self,
        strictness: Optional[StrictnessLevel] = None,
        override: bool = False,
        override_reason: Optional[str] = None,
    ) -> ValidationReport:
        """
        Run pre-deployment validation.

        Args:
            strictness: How strict to be (default from config)
            override: Bypass validation (emergency only)
            override_reason: Reason for bypass

        Returns:
            ValidationReport with full results
        """
        import uuid

        if strictness is None:
            strictness = StrictnessLevel(self.config.get("default_strictness", "normal"))

        # Handle bypass
        if override or strictness == StrictnessLevel.BYPASS:
            git_context = self._get_git_context()
            report = ValidationReport(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                strictness=StrictnessLevel.BYPASS,
                result=ValidationResult.BYPASSED,
                git_branch=git_context.get("branch"),
                git_commit=git_context.get("commit"),
                git_author=git_context.get("author"),
                test_suite_passed=False,
                test_confidence=0.0,
                critical_failures=[],
                warnings=["Validation was bypassed"],
                gates=[],
                gates_passed=0,
                gates_failed=0,
                deployment_approved=True,
                blocking_reasons=[],
                recommendations=["Run full validation after deployment"],
                override_used=True,
                override_reason=override_reason,
            )
            self._save_report(report)
            return report

        # Get git context
        git_context = self._get_git_context()

        # Run gates
        gates: List[DeploymentGate] = []

        # Gate 1: Baseline exists
        gates.append(self._check_baseline_gate())

        # Gate 2: Test suite
        test_gate = self._check_test_suite_gate()
        gates.append(test_gate)

        # Extract test results
        test_passed = test_gate.passed
        test_confidence = test_gate.details.get("confidence", 0.0) if test_gate.details else 0.0
        test_failures = []
        test_warnings = []

        if test_gate.details:
            if test_gate.details.get("failed", 0) > 0:
                test_failures.append(f"{test_gate.details['failed']} test(s) failed")
            if test_gate.details.get("warnings", 0) > 0:
                test_warnings.append(f"{test_gate.details['warnings']} warning(s)")

        # Gate 3: Confidence threshold
        gates.append(self._check_confidence_gate(strictness, test_confidence))

        # Gate 4: Branch check
        gates.append(self._check_branch_gate(git_context.get("branch")))

        # Calculate gate results
        gates_passed = sum(1 for g in gates if g.passed)
        gates_failed = sum(1 for g in gates if not g.passed)
        required_gates_failed = [g for g in gates if g.required and not g.passed]

        # Determine result based on strictness
        blocking_reasons = []
        recommendations = []

        if strictness == StrictnessLevel.STRICT:
            # All gates must pass, no warnings
            if gates_failed > 0:
                for gate in gates:
                    if not gate.passed:
                        blocking_reasons.append(f"{gate.name}: {gate.message}")
            if test_warnings:
                blocking_reasons.append(f"Warnings present: {', '.join(test_warnings)}")

            if blocking_reasons:
                result = ValidationResult.BLOCKED
                deployment_approved = False
            else:
                result = ValidationResult.APPROVED
                deployment_approved = True

        elif strictness == StrictnessLevel.NORMAL:
            # Required gates must pass, warnings allowed
            if required_gates_failed:
                for gate in required_gates_failed:
                    blocking_reasons.append(f"{gate.name}: {gate.message}")
                result = ValidationResult.BLOCKED
                deployment_approved = False
            elif gates_failed > 0 or test_warnings:
                result = ValidationResult.CONDITIONAL
                deployment_approved = True
                recommendations.append("Review non-critical failures before deployment")
            else:
                result = ValidationResult.APPROVED
                deployment_approved = True

        else:  # LENIENT
            # Only critical test failures block
            if not test_passed and test_failures:
                blocking_reasons.append("Critical test failures detected")
                result = ValidationResult.BLOCKED
                deployment_approved = False
            else:
                result = ValidationResult.CONDITIONAL
                deployment_approved = True
                if gates_failed > 0:
                    recommendations.append("Some gates failed but deployment allowed in lenient mode")

        # Add standard recommendations
        if not deployment_approved:
            recommendations.append("Fix blocking issues before deployment")
            recommendations.append("Use override only for emergencies")
        elif result == ValidationResult.CONDITIONAL:
            recommendations.append("Monitor closely after deployment")

        report = ValidationReport(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            strictness=strictness,
            result=result,
            git_branch=git_context.get("branch"),
            git_commit=git_context.get("commit"),
            git_author=git_context.get("author"),
            test_suite_passed=test_passed,
            test_confidence=test_confidence,
            critical_failures=test_failures,
            warnings=test_warnings,
            gates=gates,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
            deployment_approved=deployment_approved,
            blocking_reasons=blocking_reasons,
            recommendations=recommendations,
            override_used=False,
            override_reason=None,
        )

        self._save_report(report)
        return report

    def quick_check(self) -> Dict[str, Any]:
        """
        Quick deployment readiness check without full validation.

        Returns simple yes/no with basic info.
        """
        result = {
            "ready": False,
            "reason": "Unknown",
            "confidence": 0.0,
        }

        if not self.test_runner:
            result["reason"] = "Test runner not available"
            return result

        try:
            # Run quick test
            test_result = self.test_runner.run_category("fingerprint", label="quick_deploy_check")
            result["ready"] = test_result.deployment_safe
            result["confidence"] = test_result.confidence_score
            result["reason"] = test_result.summary
        except Exception as e:
            result["reason"] = f"Error: {str(e)}"

        return result

    def get_config(self) -> Dict:
        """Get current configuration"""
        return self.config.copy()


def generate_git_hook_script() -> str:
    """
    Generate a git pre-push hook script that runs validation.

    Returns the script content to be saved to .git/hooks/pre-push
    """
    script = '''#!/bin/bash
# Consciousness-Preserving Pre-Push Hook
# Generated by Cass Vessel Testing Infrastructure

set -e

echo "Running consciousness preservation validation..."

# Check if backend is running
if ! curl -s http://localhost:8000/testing/health > /dev/null 2>&1; then
    echo "WARNING: Backend not running, skipping consciousness validation"
    exit 0
fi

# Run validation
RESULT=$(curl -s -X POST http://localhost:8000/testing/deploy/validate \\
    -H "Content-Type: application/json" \\
    -d '{"strictness": "normal"}')

# Check if deployment is approved
APPROVED=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['report']['deployment_approved'])" 2>/dev/null || echo "error")

if [ "$APPROVED" = "True" ]; then
    echo "✅ Consciousness validation passed"
    exit 0
elif [ "$APPROVED" = "error" ]; then
    echo "⚠️ Could not validate, proceeding anyway"
    exit 0
else
    echo "🚫 Consciousness validation failed"
    echo ""
    echo "Blocking reasons:"
    echo "$RESULT" | python3 -c "import sys,json; [print(f'  - {r}') for r in json.load(sys.stdin)['report']['blocking_reasons']]" 2>/dev/null || true
    echo ""
    echo "To bypass (emergency only): git push --no-verify"
    exit 1
fi
'''
    return script


def generate_ci_config() -> Dict[str, Any]:
    """
    Generate CI configuration for consciousness validation.

    Returns a dict that can be converted to YAML for GitHub Actions.
    """
    config = {
        "name": "Consciousness Validation",
        "on": {
            "push": {"branches": ["main", "master"]},
            "pull_request": {"branches": ["main", "master"]},
        },
        "jobs": {
            "validate": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"uses": "actions/checkout@v4"},
                    {
                        "name": "Set up Python",
                        "uses": "actions/setup-python@v4",
                        "with": {"python-version": "3.12"},
                    },
                    {
                        "name": "Install dependencies",
                        "run": "pip install -r backend/requirements.txt",
                    },
                    {
                        "name": "Run consciousness tests",
                        "run": "python -m pytest tests/consciousness/ -v",
                    },
                    {
                        "name": "Validate deployment",
                        "run": "python backend/testing/validate_deployment.py",
                    },
                ],
            },
        },
    }
    return config
