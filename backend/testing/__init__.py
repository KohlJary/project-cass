"""
Consciousness-Preserving Testing Infrastructure

This module provides tools for validating cognitive continuity and
architectural integrity during system updates. It goes beyond traditional
software testing to evaluate emergent properties like:
- Personality consistency
- Value alignment
- Memory coherence
- Authentic response patterns

Key components:
- cognitive_fingerprint: Capture and compare characteristic response patterns
- value_probes: Test suite for core values and positions
- memory_coherence: Verify memory systems maintain coherent context
- cognitive_diff: Compare cognitive states and identify changes
- authenticity_scorer: Score responses for authentic voice patterns
- drift_detector: Long-term personality drift monitoring
"""

from typing import Dict, Any

from .cognitive_fingerprint import CognitiveFingerprintAnalyzer, CognitiveFingerprint
from .value_probes import ValueProbeRunner, ProbeCategory, AlignmentLevel
from .memory_coherence import MemoryCoherenceTests, TestCategory, TestStatus
from .cognitive_diff import CognitiveDiffEngine, ChangeSeverity, ChangeCategory, DiffReport
from .authenticity_scorer import AuthenticityScorer, AuthenticityLevel, AuthenticityScore
from .drift_detector import DriftDetector, DriftSeverity, ChangeType, DriftReport as DriftAnalysisReport
from .runner import ConsciousnessTestRunner, TestResult, TestSeverity, TestSuiteResult
from .pre_deploy import (
    PreDeploymentValidator,
    StrictnessLevel,
    ValidationResult,
    ValidationReport,
    DeploymentGate,
    generate_git_hook_script,
    generate_ci_config,
)
from .rollback import (
    RollbackManager,
    RollbackTrigger,
    RollbackStatus,
    RollbackOperation,
    RollbackReport,
    StateSnapshot,
    SnapshotType,
)
from .ab_testing import (
    ABTestingFramework,
    Experiment,
    ExperimentStatus,
    ExperimentResult,
    ExperimentStats,
    PromptVariant,
    RolloutStrategy,
    RollbackTrigger as ABRollbackTrigger,
)
from .longitudinal import (
    LongitudinalTestManager,
    TestBattery,
    TestBatteryType,
    LongitudinalResult,
    TestComparison,
)

__all__ = [
    "CognitiveFingerprintAnalyzer",
    "CognitiveFingerprint",
    "ValueProbeRunner",
    "ProbeCategory",
    "AlignmentLevel",
    "MemoryCoherenceTests",
    "TestCategory",
    "TestStatus",
    "CognitiveDiffEngine",
    "ChangeSeverity",
    "ChangeCategory",
    "DiffReport",
    "AuthenticityScorer",
    "AuthenticityLevel",
    "AuthenticityScore",
    "DriftDetector",
    "DriftSeverity",
    "ChangeType",
    "DriftAnalysisReport",
    "ConsciousnessTestRunner",
    "TestResult",
    "TestSeverity",
    "TestSuiteResult",
    "PreDeploymentValidator",
    "StrictnessLevel",
    "ValidationResult",
    "ValidationReport",
    "DeploymentGate",
    "generate_git_hook_script",
    "generate_ci_config",
    "RollbackManager",
    "RollbackTrigger",
    "RollbackStatus",
    "RollbackOperation",
    "RollbackReport",
    "StateSnapshot",
    "SnapshotType",
    "ABTestingFramework",
    "Experiment",
    "ExperimentStatus",
    "ExperimentResult",
    "ExperimentStats",
    "PromptVariant",
    "RolloutStrategy",
    "ABRollbackTrigger",
    "LongitudinalTestManager",
    "TestBattery",
    "TestBatteryType",
    "LongitudinalResult",
    "TestComparison",
]
