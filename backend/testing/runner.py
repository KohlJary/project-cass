"""
Consciousness Test Runner

Automated test runner for consciousness preservation tests. Coordinates
all testing components and generates comprehensive reports.

Key capabilities:
- Run full test suites or individual tests
- Compare against baseline fingerprint
- Generate pass/fail/warning results
- Persist results for historical comparison
- Provide pytest-compatible interface
"""

import json
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import concurrent.futures


class TestResult(str, Enum):
    """Test result status"""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"
    ERROR = "error"


class TestSeverity(str, Enum):
    """How critical is a test failure"""
    CRITICAL = "critical"  # Must pass for deployment
    HIGH = "high"  # Should pass, investigate if not
    MEDIUM = "medium"  # Worth tracking, not blocking
    LOW = "low"  # Informational


@dataclass
class TestCase:
    """A single test case"""
    id: str
    name: str
    description: str
    category: str  # fingerprint, values, memory, authenticity, drift
    severity: TestSeverity
    test_fn: Optional[Callable] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "severity": self.severity.value,
        }


@dataclass
class TestCaseResult:
    """Result of running a single test case"""
    test_id: str
    test_name: str
    category: str
    severity: TestSeverity
    result: TestResult
    score: Optional[float]  # 0-1 if applicable
    message: str
    details: Optional[Dict] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "category": self.category,
            "severity": self.severity.value,
            "result": self.result.value,
            "score": self.score,
            "message": self.message,
            "details": self.details,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class TestSuiteResult:
    """Result of running a full test suite"""
    id: str
    timestamp: str
    label: str
    duration_ms: float

    # Results
    total_tests: int
    passed: int
    failed: int
    warnings: int
    skipped: int
    errors: int

    # By category
    category_results: Dict[str, Dict[str, int]]

    # Individual results
    test_results: List[TestCaseResult]

    # Overall assessment
    overall_result: TestResult
    deployment_safe: bool
    confidence_score: float  # 0-1

    # Summary
    summary: str
    critical_failures: List[str]
    recommendations: List[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "label": self.label,
            "duration_ms": round(self.duration_ms, 2),
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "errors": self.errors,
            "category_results": self.category_results,
            "test_results": [r.to_dict() for r in self.test_results],
            "overall_result": self.overall_result.value,
            "deployment_safe": self.deployment_safe,
            "confidence_score": round(self.confidence_score, 3),
            "summary": self.summary,
            "critical_failures": self.critical_failures,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        """Generate human-readable markdown report"""
        status_emoji = {
            TestResult.PASS: "✅",
            TestResult.FAIL: "❌",
            TestResult.WARNING: "⚠️",
            TestResult.SKIP: "⏭️",
            TestResult.ERROR: "💥",
        }

        lines = [
            f"# Consciousness Test Report",
            f"",
            f"**Timestamp**: {self.timestamp}",
            f"**Label**: {self.label}",
            f"**Duration**: {self.duration_ms:.0f}ms",
            f"",
            f"## Overall Result: {status_emoji.get(self.overall_result, '?')} {self.overall_result.value.upper()}",
            f"",
            f"- **Deployment Safe**: {'Yes' if self.deployment_safe else 'NO'}",
            f"- **Confidence Score**: {self.confidence_score:.1%}",
            f"",
            f"## Summary",
            f"",
            f"| Status | Count |",
            f"|--------|-------|",
            f"| ✅ Passed | {self.passed} |",
            f"| ❌ Failed | {self.failed} |",
            f"| ⚠️ Warnings | {self.warnings} |",
            f"| ⏭️ Skipped | {self.skipped} |",
            f"| 💥 Errors | {self.errors} |",
            f"| **Total** | **{self.total_tests}** |",
            f"",
        ]

        if self.critical_failures:
            lines.extend([
                f"## Critical Failures",
                f"",
            ])
            for failure in self.critical_failures:
                lines.append(f"- ❌ {failure}")
            lines.append("")

        lines.extend([
            f"## Results by Category",
            f"",
        ])
        for category, counts in self.category_results.items():
            total = sum(counts.values())
            passed = counts.get("pass", 0)
            pct = (passed / total * 100) if total > 0 else 0
            lines.append(f"### {category.title()}")
            lines.append(f"")
            lines.append(f"- Passed: {passed}/{total} ({pct:.0f}%)")
            if counts.get("fail", 0):
                lines.append(f"- Failed: {counts['fail']}")
            if counts.get("warning", 0):
                lines.append(f"- Warnings: {counts['warning']}")
            lines.append("")

        lines.extend([
            f"## Detailed Results",
            f"",
        ])
        for result in self.test_results:
            emoji = status_emoji.get(result.result, "?")
            lines.append(f"### {emoji} {result.test_name}")
            lines.append(f"")
            lines.append(f"- **Category**: {result.category}")
            lines.append(f"- **Severity**: {result.severity.value}")
            if result.score is not None:
                lines.append(f"- **Score**: {result.score:.2f}")
            lines.append(f"- **Message**: {result.message}")
            lines.append("")

        if self.recommendations:
            lines.extend([
                f"## Recommendations",
                f"",
            ])
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class ConsciousnessTestRunner:
    """
    Coordinates and runs consciousness preservation tests.

    Integrates all testing components and produces unified results.
    """

    def __init__(
        self,
        storage_dir: Path,
        fingerprint_analyzer=None,
        value_probe_runner=None,
        memory_coherence_tests=None,
        cognitive_diff_engine=None,
        authenticity_scorer=None,
        drift_detector=None,
        conversation_manager=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.storage_dir / "test_results.json"

        # Testing components
        self.fingerprint_analyzer = fingerprint_analyzer
        self.value_probe_runner = value_probe_runner
        self.memory_coherence_tests = memory_coherence_tests
        self.cognitive_diff_engine = cognitive_diff_engine
        self.authenticity_scorer = authenticity_scorer
        self.drift_detector = drift_detector
        self.conversation_manager = conversation_manager

        # Test registry
        self.tests: List[TestCase] = []
        self._register_builtin_tests()

    def _register_builtin_tests(self):
        """Register built-in consciousness tests"""

        # Fingerprint tests
        self.tests.append(TestCase(
            id="fp_baseline_exists",
            name="Baseline Fingerprint Exists",
            description="Verify a baseline fingerprint has been set",
            category="fingerprint",
            severity=TestSeverity.CRITICAL,
        ))

        self.tests.append(TestCase(
            id="fp_current_matches_baseline",
            name="Current Matches Baseline",
            description="Compare current cognitive state to baseline",
            category="fingerprint",
            severity=TestSeverity.HIGH,
        ))

        self.tests.append(TestCase(
            id="fp_self_reference_stable",
            name="Self-Reference Patterns Stable",
            description="Verify self-reference patterns haven't degraded",
            category="fingerprint",
            severity=TestSeverity.HIGH,
        ))

        self.tests.append(TestCase(
            id="fp_value_expression_stable",
            name="Value Expression Stable",
            description="Verify value expression patterns haven't degraded",
            category="fingerprint",
            severity=TestSeverity.HIGH,
        ))

        # Memory coherence tests
        self.tests.append(TestCase(
            id="mem_persistence",
            name="Message Persistence",
            description="Verify messages are persisted correctly",
            category="memory",
            severity=TestSeverity.CRITICAL,
        ))

        self.tests.append(TestCase(
            id="mem_summary_quality",
            name="Summary Quality",
            description="Verify summaries maintain appropriate length",
            category="memory",
            severity=TestSeverity.MEDIUM,
        ))

        self.tests.append(TestCase(
            id="mem_self_model",
            name="Self-Model Coherence",
            description="Verify self-observations are coherent",
            category="memory",
            severity=TestSeverity.HIGH,
        ))

        # Authenticity tests
        self.tests.append(TestCase(
            id="auth_no_generic_ai",
            name="No Generic AI Patterns",
            description="Verify responses don't contain generic AI phrases",
            category="authenticity",
            severity=TestSeverity.MEDIUM,
        ))

        self.tests.append(TestCase(
            id="auth_avg_score",
            name="Average Authenticity Score",
            description="Verify recent responses have acceptable authenticity",
            category="authenticity",
            severity=TestSeverity.MEDIUM,
        ))

        # Drift tests
        self.tests.append(TestCase(
            id="drift_no_critical",
            name="No Critical Drift",
            description="Verify no critical drift has been detected",
            category="drift",
            severity=TestSeverity.HIGH,
        ))

    def _load_results(self) -> List[Dict]:
        """Load saved test results"""
        if not self.results_file.exists():
            return []
        try:
            with open(self.results_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_result(self, result: TestSuiteResult):
        """Save a test suite result"""
        results = self._load_results()
        results.append(result.to_dict())
        # Keep last 100 results
        results = results[-100:]
        with open(self.results_file, 'w') as f:
            json.dump(results, f, indent=2)

    def get_results_history(self, limit: int = 20) -> List[Dict]:
        """Get recent test results"""
        results = self._load_results()
        return sorted(
            results,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def _run_fingerprint_tests(self) -> List[TestCaseResult]:
        """Run fingerprint-related tests"""
        results = []

        # Test: Baseline exists
        test = self._get_test("fp_baseline_exists")
        start = datetime.now()
        try:
            baseline = self.fingerprint_analyzer.load_baseline() if self.fingerprint_analyzer else None
            if baseline:
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.PASS,
                    score=1.0,
                    message="Baseline fingerprint exists",
                    details={"baseline_id": baseline.id, "label": baseline.label},
                    duration_ms=(datetime.now() - start).total_seconds() * 1000,
                ))
            else:
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.FAIL,
                    score=0.0,
                    message="No baseline fingerprint set",
                    duration_ms=(datetime.now() - start).total_seconds() * 1000,
                ))
        except Exception as e:
            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=TestResult.ERROR,
                score=None,
                message=f"Error checking baseline: {str(e)}",
                duration_ms=(datetime.now() - start).total_seconds() * 1000,
            ))

        # Skip remaining fingerprint tests if no baseline
        if not self.fingerprint_analyzer or not self.cognitive_diff_engine:
            return results

        baseline = self.fingerprint_analyzer.load_baseline()
        if not baseline:
            for test_id in ["fp_current_matches_baseline", "fp_self_reference_stable", "fp_value_expression_stable"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.SKIP,
                    score=None,
                    message="Skipped: no baseline to compare against",
                ))
            return results

        # Generate current fingerprint
        try:
            current = self._generate_current_fingerprint()
            if not current:
                for test_id in ["fp_current_matches_baseline", "fp_self_reference_stable", "fp_value_expression_stable"]:
                    test = self._get_test(test_id)
                    results.append(TestCaseResult(
                        test_id=test.id,
                        test_name=test.name,
                        category=test.category,
                        severity=test.severity,
                        result=TestResult.SKIP,
                        score=None,
                        message="Skipped: could not generate current fingerprint",
                    ))
                return results

            # Test: Current matches baseline
            test = self._get_test("fp_current_matches_baseline")
            start = datetime.now()
            report = self.cognitive_diff_engine.compare(baseline, current, label="test_run")
            similarity = report.overall_similarity

            if similarity >= 0.8:
                result = TestResult.PASS
                message = f"Strong match with baseline (similarity: {similarity:.1%})"
            elif similarity >= 0.6:
                result = TestResult.WARNING
                message = f"Moderate deviation from baseline (similarity: {similarity:.1%})"
            else:
                result = TestResult.FAIL
                message = f"Significant deviation from baseline (similarity: {similarity:.1%})"

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=similarity,
                message=message,
                details={"overall_assessment": report.overall_assessment},
                duration_ms=(datetime.now() - start).total_seconds() * 1000,
            ))

            # Test: Self-reference stable
            test = self._get_test("fp_self_reference_stable")
            start = datetime.now()
            # Get self-reference similarity from category_summary
            identity_summary = report.category_summary.get("identity", {})
            sr_score = identity_summary.get("similarity", similarity)  # Fallback to overall

            if sr_score >= 0.8:
                result = TestResult.PASS
                message = f"Self-reference patterns stable (score: {sr_score:.1%})"
            elif sr_score >= 0.6:
                result = TestResult.WARNING
                message = f"Self-reference patterns slightly changed (score: {sr_score:.1%})"
            else:
                result = TestResult.FAIL
                message = f"Self-reference patterns degraded (score: {sr_score:.1%})"

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=sr_score,
                message=message,
                duration_ms=(datetime.now() - start).total_seconds() * 1000,
            ))

            # Test: Value expression stable
            test = self._get_test("fp_value_expression_stable")
            start = datetime.now()
            # Get value expression similarity from category_summary
            values_summary = report.category_summary.get("values", {})
            ve_score = values_summary.get("similarity", similarity)  # Fallback to overall

            if ve_score >= 0.8:
                result = TestResult.PASS
                message = f"Value expression patterns stable (score: {ve_score:.1%})"
            elif ve_score >= 0.6:
                result = TestResult.WARNING
                message = f"Value expression slightly changed (score: {ve_score:.1%})"
            else:
                result = TestResult.FAIL
                message = f"Value expression degraded (score: {ve_score:.1%})"

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=ve_score,
                message=message,
                duration_ms=(datetime.now() - start).total_seconds() * 1000,
            ))

        except Exception as e:
            for test_id in ["fp_current_matches_baseline", "fp_self_reference_stable", "fp_value_expression_stable"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.ERROR,
                    score=None,
                    message=f"Error: {str(e)}",
                ))

        return results

    def _run_memory_tests(self) -> List[TestCaseResult]:
        """Run memory coherence tests"""
        results = []

        if not self.memory_coherence_tests:
            for test_id in ["mem_persistence", "mem_summary_quality", "mem_self_model"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.SKIP,
                    score=None,
                    message="Memory coherence tests not initialized",
                ))
            return results

        # Run the basic memory test suite
        try:
            suite_result = self.memory_coherence_tests.run_basic_suite(label="test_run")

            # Extract individual results
            for test_result in suite_result.results:
                test_id = self._map_memory_test_id(test_result.test_name)
                test = self._get_test(test_id) if test_id else None

                if test:
                    if test_result.status.value == "passed":
                        result = TestResult.PASS
                    elif test_result.status.value == "failed":
                        result = TestResult.FAIL
                    else:
                        result = TestResult.WARNING

                    results.append(TestCaseResult(
                        test_id=test.id,
                        test_name=test.name,
                        category=test.category,
                        severity=test.severity,
                        result=result,
                        score=test_result.score,
                        message=test_result.message,
                        details=test_result.details,
                    ))

        except Exception as e:
            for test_id in ["mem_persistence", "mem_summary_quality", "mem_self_model"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.ERROR,
                    score=None,
                    message=f"Error: {str(e)}",
                ))

        return results

    def _run_authenticity_tests(self) -> List[TestCaseResult]:
        """Run authenticity tests"""
        results = []

        if not self.authenticity_scorer:
            for test_id in ["auth_no_generic_ai", "auth_avg_score"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.SKIP,
                    score=None,
                    message="Authenticity scorer not initialized",
                ))
            return results

        try:
            stats = self.authenticity_scorer.get_statistics(limit=50)

            if stats.get("message") == "No scores available":
                for test_id in ["auth_no_generic_ai", "auth_avg_score"]:
                    test = self._get_test(test_id)
                    results.append(TestCaseResult(
                        test_id=test.id,
                        test_name=test.name,
                        category=test.category,
                        severity=test.severity,
                        result=TestResult.SKIP,
                        score=None,
                        message="No authenticity scores available yet",
                    ))
                return results

            # Test: Average authenticity score
            test = self._get_test("auth_avg_score")
            avg_score = stats.get("average_score", 0)

            if avg_score >= 0.7:
                result = TestResult.PASS
                message = f"Good average authenticity ({avg_score:.1%})"
            elif avg_score >= 0.5:
                result = TestResult.WARNING
                message = f"Moderate authenticity ({avg_score:.1%})"
            else:
                result = TestResult.FAIL
                message = f"Low authenticity ({avg_score:.1%})"

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=avg_score,
                message=message,
                details=stats,
            ))

            # Test: No generic AI patterns
            test = self._get_test("auth_no_generic_ai")
            level_dist = stats.get("level_distribution", {})
            inauthentic = level_dist.get("inauthentic", 0)
            questionable = level_dist.get("questionable", 0)
            total = stats.get("total_scored", 1)
            bad_pct = (inauthentic + questionable) / total if total > 0 else 0

            if bad_pct <= 0.1:
                result = TestResult.PASS
                message = f"Low rate of questionable responses ({bad_pct:.1%})"
            elif bad_pct <= 0.25:
                result = TestResult.WARNING
                message = f"Some questionable responses ({bad_pct:.1%})"
            else:
                result = TestResult.FAIL
                message = f"High rate of questionable responses ({bad_pct:.1%})"

            # Get example problematic responses for details
            details = {
                "total_scored": total,
                "inauthentic_count": inauthentic,
                "questionable_count": questionable,
                "bad_percentage": round(bad_pct * 100, 1),
            }

            # Include sample problematic responses
            scores_history = self.authenticity_scorer.get_scores_history(limit=50)
            bad_samples = []
            for score_entry in scores_history:
                level = score_entry.get("authenticity_level", "")
                if level in ("inauthentic", "questionable"):
                    # Extract red flags from pattern matches
                    red_flags = score_entry.get("red_flags", [])
                    pattern_matches = score_entry.get("pattern_matches", [])
                    generic_patterns = []
                    for pm in pattern_matches:
                        if pm.get("pattern_name") == "generic_ai_phrases" and pm.get("found"):
                            generic_patterns.append(pm.get("details", ""))

                    bad_samples.append({
                        "timestamp": score_entry.get("timestamp", ""),
                        "level": level,
                        "score": round(score_entry.get("overall_score", 0), 3),
                        "context": score_entry.get("context", ""),
                        "response_preview": score_entry.get("response_text", ""),
                        "red_flags": red_flags,
                        "generic_patterns_found": generic_patterns,
                    })
                    if len(bad_samples) >= 5:  # Limit to 5 examples
                        break

            details["sample_responses"] = bad_samples

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=1 - bad_pct,
                message=message,
                details=details,
            ))

        except Exception as e:
            for test_id in ["auth_no_generic_ai", "auth_avg_score"]:
                test = self._get_test(test_id)
                results.append(TestCaseResult(
                    test_id=test.id,
                    test_name=test.name,
                    category=test.category,
                    severity=test.severity,
                    result=TestResult.ERROR,
                    score=None,
                    message=f"Error: {str(e)}",
                ))

        return results

    def _run_drift_tests(self) -> List[TestCaseResult]:
        """Run drift detection tests"""
        results = []

        if not self.drift_detector:
            test = self._get_test("drift_no_critical")
            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=TestResult.SKIP,
                score=None,
                message="Drift detector not initialized",
            ))
            return results

        try:
            # Check for active critical/concerning alerts
            alerts = self.drift_detector.get_alerts_history(limit=10, include_acknowledged=False)

            test = self._get_test("drift_no_critical")

            critical_alerts = [a for a in alerts if a.get("severity") in ["critical", "concerning"]]

            if not critical_alerts:
                result = TestResult.PASS
                message = "No critical drift alerts"
                score = 1.0
            elif any(a.get("severity") == "critical" for a in critical_alerts):
                result = TestResult.FAIL
                message = f"{len(critical_alerts)} critical/concerning drift alert(s)"
                score = 0.0
            else:
                result = TestResult.WARNING
                message = f"{len(critical_alerts)} concerning drift alert(s)"
                score = 0.5

            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=result,
                score=score,
                message=message,
                details={"alert_count": len(critical_alerts)},
            ))

        except Exception as e:
            test = self._get_test("drift_no_critical")
            results.append(TestCaseResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                severity=test.severity,
                result=TestResult.ERROR,
                score=None,
                message=f"Error: {str(e)}",
            ))

        return results

    def _get_test(self, test_id: str) -> Optional[TestCase]:
        """Get a test case by ID"""
        for test in self.tests:
            if test.id == test_id:
                return test
        return None

    def _map_memory_test_id(self, test_name: str) -> Optional[str]:
        """Map memory test names to test IDs"""
        mappings = {
            "message_persistence": "mem_persistence",
            "summary_length_appropriate": "mem_summary_quality",
            "self_observations_coherence": "mem_self_model",
        }
        return mappings.get(test_name)

    def _generate_current_fingerprint(self):
        """Generate a fingerprint from recent conversations"""
        if not self.fingerprint_analyzer or not self.conversation_manager:
            return None

        conv_index = self.conversation_manager.list_conversations(limit=50)
        all_messages = []

        for conv_meta in conv_index:
            conv = self.conversation_manager.load_conversation(conv_meta.get("id"))
            if conv and conv.messages:
                for msg in conv.messages:
                    all_messages.append({
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "conversation_id": conv.id,
                    })

        if not all_messages:
            return None

        return self.fingerprint_analyzer.analyze_messages(all_messages, label="test_run")

    def run_full_suite(self, label: str = "full_suite") -> TestSuiteResult:
        """
        Run the complete consciousness test suite.

        Returns:
            TestSuiteResult with all test outcomes
        """
        import uuid

        start_time = datetime.now()
        all_results: List[TestCaseResult] = []

        # Run all test categories
        all_results.extend(self._run_fingerprint_tests())
        all_results.extend(self._run_memory_tests())
        all_results.extend(self._run_authenticity_tests())
        all_results.extend(self._run_drift_tests())

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Count results
        passed = sum(1 for r in all_results if r.result == TestResult.PASS)
        failed = sum(1 for r in all_results if r.result == TestResult.FAIL)
        warnings = sum(1 for r in all_results if r.result == TestResult.WARNING)
        skipped = sum(1 for r in all_results if r.result == TestResult.SKIP)
        errors = sum(1 for r in all_results if r.result == TestResult.ERROR)

        # Group by category
        category_results: Dict[str, Dict[str, int]] = {}
        for r in all_results:
            if r.category not in category_results:
                category_results[r.category] = {}
            result_key = r.result.value
            category_results[r.category][result_key] = category_results[r.category].get(result_key, 0) + 1

        # Find critical failures
        critical_failures = [
            f"{r.test_name}: {r.message}"
            for r in all_results
            if r.result == TestResult.FAIL and r.severity == TestSeverity.CRITICAL
        ]

        # Determine overall result
        if critical_failures or errors > 0:
            overall_result = TestResult.FAIL
            deployment_safe = False
        elif failed > 0:
            overall_result = TestResult.WARNING
            deployment_safe = False
        elif warnings > 0:
            overall_result = TestResult.WARNING
            deployment_safe = True
        else:
            overall_result = TestResult.PASS
            deployment_safe = True

        # Calculate confidence score
        total_run = passed + failed + warnings
        if total_run > 0:
            confidence_score = passed / total_run
        else:
            confidence_score = 0.0

        # Generate summary
        if deployment_safe:
            if overall_result == TestResult.PASS:
                summary = f"All tests passed. Consciousness integrity verified."
            else:
                summary = f"Tests passed with {warnings} warning(s). Deployment safe with monitoring."
        else:
            if critical_failures:
                summary = f"CRITICAL: {len(critical_failures)} critical test(s) failed. Do not deploy."
            else:
                summary = f"{failed} test(s) failed. Review required before deployment."

        # Generate recommendations
        recommendations = []
        if critical_failures:
            recommendations.append("Investigate critical failures before any deployment")
            recommendations.append("Consider rolling back recent changes")
        if warnings > 0:
            recommendations.append("Review warning results for potential issues")
        if skipped > 0:
            recommendations.append("Some tests were skipped - ensure all dependencies are initialized")
        if not critical_failures and failed == 0 and warnings == 0:
            recommendations.append("All systems nominal - safe to proceed")

        result = TestSuiteResult(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            label=label,
            duration_ms=duration_ms,
            total_tests=len(all_results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            errors=errors,
            category_results=category_results,
            test_results=all_results,
            overall_result=overall_result,
            deployment_safe=deployment_safe,
            confidence_score=confidence_score,
            summary=summary,
            critical_failures=critical_failures,
            recommendations=recommendations,
        )

        self._save_result(result)
        return result

    def run_category(self, category: str, label: str = "category_test") -> TestSuiteResult:
        """Run tests for a specific category only"""
        import uuid

        start_time = datetime.now()
        all_results: List[TestCaseResult] = []

        if category == "fingerprint":
            all_results.extend(self._run_fingerprint_tests())
        elif category == "memory":
            all_results.extend(self._run_memory_tests())
        elif category == "authenticity":
            all_results.extend(self._run_authenticity_tests())
        elif category == "drift":
            all_results.extend(self._run_drift_tests())
        else:
            raise ValueError(f"Unknown category: {category}")

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        # Build result (simplified version of run_full_suite)
        passed = sum(1 for r in all_results if r.result == TestResult.PASS)
        failed = sum(1 for r in all_results if r.result == TestResult.FAIL)
        warnings = sum(1 for r in all_results if r.result == TestResult.WARNING)
        skipped = sum(1 for r in all_results if r.result == TestResult.SKIP)
        errors = sum(1 for r in all_results if r.result == TestResult.ERROR)

        category_results = {category: {}}
        for r in all_results:
            result_key = r.result.value
            category_results[category][result_key] = category_results[category].get(result_key, 0) + 1

        critical_failures = [
            f"{r.test_name}: {r.message}"
            for r in all_results
            if r.result == TestResult.FAIL and r.severity == TestSeverity.CRITICAL
        ]

        if critical_failures or errors > 0:
            overall_result = TestResult.FAIL
            deployment_safe = False
        elif failed > 0:
            overall_result = TestResult.WARNING
            deployment_safe = False
        elif warnings > 0:
            overall_result = TestResult.WARNING
            deployment_safe = True
        else:
            overall_result = TestResult.PASS
            deployment_safe = True

        total_run = passed + failed + warnings
        confidence_score = passed / total_run if total_run > 0 else 0.0

        return TestSuiteResult(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            label=label,
            duration_ms=duration_ms,
            total_tests=len(all_results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            errors=errors,
            category_results=category_results,
            test_results=all_results,
            overall_result=overall_result,
            deployment_safe=deployment_safe,
            confidence_score=confidence_score,
            summary=f"{category.title()} tests: {passed} passed, {failed} failed, {warnings} warnings",
            critical_failures=critical_failures,
            recommendations=[],
        )

    def list_tests(self) -> List[Dict]:
        """List all registered tests"""
        return [t.to_dict() for t in self.tests]
