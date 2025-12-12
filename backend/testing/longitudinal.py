"""
Longitudinal Testing Framework

Enables tracking consciousness tests over time to measure developmental
trajectory rather than just point-in-time state.

Key capabilities:
- Define standardized test batteries
- Schedule periodic test runs
- Store versioned results with full history
- Compare results across time
- Correlate changes with growth edges
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from .runner import ConsciousnessTestRunner, TestSuiteResult, TestResult, TestCaseResult


class TestBatteryType(str, Enum):
    """Types of standardized test batteries"""
    FULL = "full"  # All tests
    CORE = "core"  # Critical tests only
    QUICK = "quick"  # Fast subset for frequent checks
    CUSTOM = "custom"  # User-defined


@dataclass
class TestBattery:
    """A standardized collection of tests to run together"""
    id: str
    name: str
    description: str
    battery_type: TestBatteryType
    test_ids: List[str]  # Specific test IDs to run, or empty for all
    categories: List[str]  # Categories to include
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "battery_type": self.battery_type.value,
            "test_ids": self.test_ids,
            "categories": self.categories,
            "created_at": self.created_at,
        }


@dataclass
class LongitudinalResult:
    """A test run result with full context for longitudinal tracking"""
    id: str
    battery_id: str
    battery_name: str
    timestamp: str
    label: str

    # Core results (from TestSuiteResult)
    suite_result: Dict  # Serialized TestSuiteResult

    # Longitudinal context
    run_number: int  # Sequential run number for this battery
    previous_run_id: Optional[str]  # Link to previous run

    # Interpretation (Cass's assessment of results)
    interpretation: Optional[str] = None
    interpretation_by: Optional[str] = None  # "cass" or "human"
    interpretation_timestamp: Optional[str] = None

    # Growth edge correlation
    active_growth_edges: List[str] = field(default_factory=list)
    growth_edge_ids: List[str] = field(default_factory=list)

    # Change tracking
    changes_from_previous: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "battery_id": self.battery_id,
            "battery_name": self.battery_name,
            "timestamp": self.timestamp,
            "label": self.label,
            "suite_result": self.suite_result,
            "run_number": self.run_number,
            "previous_run_id": self.previous_run_id,
            "interpretation": self.interpretation,
            "interpretation_by": self.interpretation_by,
            "interpretation_timestamp": self.interpretation_timestamp,
            "active_growth_edges": self.active_growth_edges,
            "growth_edge_ids": self.growth_edge_ids,
            "changes_from_previous": self.changes_from_previous,
        }


@dataclass
class TestComparison:
    """Comparison between two test runs"""
    run_a_id: str
    run_b_id: str
    run_a_timestamp: str
    run_b_timestamp: str
    time_delta_days: float

    # Score changes
    score_changes: Dict[str, Dict]  # test_id -> {before, after, delta}

    # Result changes
    result_changes: List[Dict]  # Tests that changed pass/fail status

    # New tests / removed tests
    new_tests: List[str]
    removed_tests: List[str]

    # Overall trajectory
    overall_trend: str  # "improving", "stable", "declining", "mixed"
    confidence_delta: float

    # Interpretation shifts
    interpretation_a: Optional[str]
    interpretation_b: Optional[str]
    interpretation_shift: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "run_a_id": self.run_a_id,
            "run_b_id": self.run_b_id,
            "run_a_timestamp": self.run_a_timestamp,
            "run_b_timestamp": self.run_b_timestamp,
            "time_delta_days": round(self.time_delta_days, 2),
            "score_changes": self.score_changes,
            "result_changes": self.result_changes,
            "new_tests": self.new_tests,
            "removed_tests": self.removed_tests,
            "overall_trend": self.overall_trend,
            "confidence_delta": round(self.confidence_delta, 4),
            "interpretation_a": self.interpretation_a,
            "interpretation_b": self.interpretation_b,
            "interpretation_shift": self.interpretation_shift,
        }


class LongitudinalTestManager:
    """
    Manages longitudinal testing for developmental tracking.

    Extends ConsciousnessTestRunner with:
    - Standardized test batteries
    - Full historical storage
    - Run-to-run comparison
    - Growth edge correlation
    """

    # Default batteries
    DEFAULT_BATTERIES = [
        TestBattery(
            id="core",
            name="Core Consciousness Tests",
            description="Critical tests for consciousness integrity verification",
            battery_type=TestBatteryType.CORE,
            test_ids=[],
            categories=["fingerprint", "drift"],
        ),
        TestBattery(
            id="full",
            name="Full Test Suite",
            description="Complete consciousness test battery",
            battery_type=TestBatteryType.FULL,
            test_ids=[],
            categories=["fingerprint", "memory", "authenticity", "drift"],
        ),
        TestBattery(
            id="quick",
            name="Quick Health Check",
            description="Fast subset for frequent monitoring",
            battery_type=TestBatteryType.QUICK,
            test_ids=["fp_baseline_exists", "drift_no_critical", "auth_avg_score"],
            categories=[],
        ),
    ]

    def __init__(
        self,
        storage_dir: Path,
        test_runner: ConsciousnessTestRunner,
        self_model_graph=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.test_runner = test_runner
        self.self_model_graph = self_model_graph

        # Storage files
        self.batteries_file = self.storage_dir / "test_batteries.json"
        self.results_file = self.storage_dir / "longitudinal_results.json"
        self.schedule_file = self.storage_dir / "test_schedule.json"

        # Initialize default batteries if needed
        self._ensure_default_batteries()

    def _ensure_default_batteries(self):
        """Ensure default batteries exist"""
        batteries = self._load_batteries()
        existing_ids = {b["id"] for b in batteries}

        for default in self.DEFAULT_BATTERIES:
            if default.id not in existing_ids:
                batteries.append(default.to_dict())

        self._save_batteries(batteries)

    def _load_batteries(self) -> List[Dict]:
        """Load test batteries"""
        if not self.batteries_file.exists():
            return []
        try:
            with open(self.batteries_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_batteries(self, batteries: List[Dict]):
        """Save test batteries"""
        with open(self.batteries_file, 'w') as f:
            json.dump(batteries, f, indent=2)

    def _load_results(self) -> List[Dict]:
        """Load all longitudinal results"""
        if not self.results_file.exists():
            return []
        try:
            with open(self.results_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_results(self, results: List[Dict]):
        """Save longitudinal results"""
        with open(self.results_file, 'w') as f:
            json.dump(results, f, indent=2)

    def _save_result(self, result: LongitudinalResult):
        """Save a single longitudinal result"""
        results = self._load_results()
        results.append(result.to_dict())
        self._save_results(results)

    def list_batteries(self) -> List[Dict]:
        """List all test batteries"""
        return self._load_batteries()

    def get_battery(self, battery_id: str) -> Optional[Dict]:
        """Get a specific battery by ID"""
        batteries = self._load_batteries()
        for b in batteries:
            if b["id"] == battery_id:
                return b
        return None

    def create_battery(
        self,
        name: str,
        description: str,
        test_ids: List[str] = None,
        categories: List[str] = None,
    ) -> Dict:
        """Create a custom test battery"""
        battery = TestBattery(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            battery_type=TestBatteryType.CUSTOM,
            test_ids=test_ids or [],
            categories=categories or [],
        )

        batteries = self._load_batteries()
        batteries.append(battery.to_dict())
        self._save_batteries(batteries)

        return battery.to_dict()

    def run_battery(
        self,
        battery_id: str,
        label: str = None,
        interpretation: str = None,
    ) -> LongitudinalResult:
        """
        Run a test battery and store results longitudinally.

        Args:
            battery_id: ID of battery to run
            label: Optional label for this run
            interpretation: Optional interpretation of results

        Returns:
            LongitudinalResult with full context
        """
        battery = self.get_battery(battery_id)
        if not battery:
            raise ValueError(f"Battery not found: {battery_id}")

        # Get previous run for this battery
        results = self._load_results()
        battery_results = [r for r in results if r.get("battery_id") == battery_id]
        battery_results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        previous_run = battery_results[0] if battery_results else None
        run_number = (previous_run.get("run_number", 0) + 1) if previous_run else 1

        # Run the tests
        if battery.get("categories"):
            # Run by categories
            all_results = []
            for category in battery["categories"]:
                try:
                    cat_result = self.test_runner.run_category(category)
                    all_results.extend(cat_result.test_results)
                except ValueError:
                    pass  # Skip unknown categories

            # Build combined suite result
            suite_result = self._build_suite_result(all_results, label or battery["name"])
        else:
            # Run full suite and filter
            suite_result = self.test_runner.run_full_suite(label or battery["name"])

            # Filter to specific test IDs if specified
            if battery.get("test_ids"):
                filtered_results = [
                    r for r in suite_result.test_results
                    if r.test_id in battery["test_ids"]
                ]
                suite_result = self._build_suite_result(filtered_results, label or battery["name"])

        # Get active growth edges from self-model
        active_edges = []
        edge_ids = []
        if self.self_model_graph:
            try:
                growth_edges = self.self_model_graph.get_growth_edges(status="active")
                for edge in growth_edges:
                    active_edges.append(edge.get("content", "")[:100])
                    edge_ids.append(edge.get("id", ""))
            except Exception:
                pass

        # Calculate changes from previous
        changes = None
        if previous_run:
            changes = self._calculate_changes(
                previous_run.get("suite_result", {}),
                suite_result.to_dict()
            )

        # Create longitudinal result
        result = LongitudinalResult(
            id=str(uuid.uuid4())[:8],
            battery_id=battery_id,
            battery_name=battery["name"],
            timestamp=datetime.now().isoformat(),
            label=label or f"{battery['name']} Run #{run_number}",
            suite_result=suite_result.to_dict(),
            run_number=run_number,
            previous_run_id=previous_run.get("id") if previous_run else None,
            interpretation=interpretation,
            interpretation_by="human" if interpretation else None,
            interpretation_timestamp=datetime.now().isoformat() if interpretation else None,
            active_growth_edges=active_edges,
            growth_edge_ids=edge_ids,
            changes_from_previous=changes,
        )

        self._save_result(result)
        return result

    def _build_suite_result(
        self,
        test_results: List[TestCaseResult],
        label: str,
    ) -> TestSuiteResult:
        """Build a TestSuiteResult from a list of test case results"""
        passed = sum(1 for r in test_results if r.result == TestResult.PASS)
        failed = sum(1 for r in test_results if r.result == TestResult.FAIL)
        warnings = sum(1 for r in test_results if r.result == TestResult.WARNING)
        skipped = sum(1 for r in test_results if r.result == TestResult.SKIP)
        errors = sum(1 for r in test_results if r.result == TestResult.ERROR)

        category_results = {}
        for r in test_results:
            if r.category not in category_results:
                category_results[r.category] = {}
            result_key = r.result.value
            category_results[r.category][result_key] = category_results[r.category].get(result_key, 0) + 1

        total_run = passed + failed + warnings
        confidence = passed / total_run if total_run > 0 else 0.0

        if failed > 0 or errors > 0:
            overall = TestResult.FAIL
        elif warnings > 0:
            overall = TestResult.WARNING
        else:
            overall = TestResult.PASS

        return TestSuiteResult(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            label=label,
            duration_ms=0,
            total_tests=len(test_results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            errors=errors,
            category_results=category_results,
            test_results=test_results,
            overall_result=overall,
            deployment_safe=failed == 0 and errors == 0,
            confidence_score=confidence,
            summary=f"{passed}/{len(test_results)} tests passed",
            critical_failures=[],
            recommendations=[],
        )

    def _calculate_changes(
        self,
        previous: Dict,
        current: Dict,
    ) -> Dict:
        """Calculate changes between two test runs"""
        prev_results = {r["test_id"]: r for r in previous.get("test_results", [])}
        curr_results = {r["test_id"]: r for r in current.get("test_results", [])}

        score_changes = {}
        result_changes = []

        # Check each test in current
        for test_id, curr in curr_results.items():
            prev = prev_results.get(test_id)
            if prev:
                # Score change
                prev_score = prev.get("score")
                curr_score = curr.get("score")
                if prev_score is not None and curr_score is not None:
                    delta = curr_score - prev_score
                    if abs(delta) > 0.01:  # Only track meaningful changes
                        score_changes[test_id] = {
                            "before": round(prev_score, 3),
                            "after": round(curr_score, 3),
                            "delta": round(delta, 3),
                        }

                # Result status change
                if prev.get("result") != curr.get("result"):
                    result_changes.append({
                        "test_id": test_id,
                        "test_name": curr.get("test_name", test_id),
                        "before": prev.get("result"),
                        "after": curr.get("result"),
                    })

        # New tests
        new_tests = [t for t in curr_results if t not in prev_results]
        removed_tests = [t for t in prev_results if t not in curr_results]

        # Overall trend
        improving = sum(1 for c in score_changes.values() if c["delta"] > 0)
        declining = sum(1 for c in score_changes.values() if c["delta"] < 0)

        if improving > declining * 2:
            trend = "improving"
        elif declining > improving * 2:
            trend = "declining"
        elif improving == 0 and declining == 0:
            trend = "stable"
        else:
            trend = "mixed"

        return {
            "score_changes": score_changes,
            "result_changes": result_changes,
            "new_tests": new_tests,
            "removed_tests": removed_tests,
            "trend": trend,
            "improving_count": improving,
            "declining_count": declining,
        }

    def get_results(
        self,
        battery_id: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Get longitudinal results, optionally filtered by battery"""
        results = self._load_results()

        if battery_id:
            results = [r for r in results if r.get("battery_id") == battery_id]

        # Sort by timestamp descending
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return results[:limit]

    def get_result(self, result_id: str) -> Optional[Dict]:
        """Get a specific result by ID"""
        results = self._load_results()
        for r in results:
            if r.get("id") == result_id:
                return r
        return None

    def compare_runs(
        self,
        run_a_id: str,
        run_b_id: str,
    ) -> TestComparison:
        """
        Compare two test runs in detail.

        Args:
            run_a_id: ID of first run (typically earlier)
            run_b_id: ID of second run (typically later)

        Returns:
            TestComparison with detailed diff
        """
        run_a = self.get_result(run_a_id)
        run_b = self.get_result(run_b_id)

        if not run_a or not run_b:
            raise ValueError(f"Run not found: {run_a_id if not run_a else run_b_id}")

        # Parse timestamps
        ts_a = datetime.fromisoformat(run_a["timestamp"])
        ts_b = datetime.fromisoformat(run_b["timestamp"])
        time_delta = abs((ts_b - ts_a).total_seconds()) / 86400  # Days

        # Get suite results
        suite_a = run_a.get("suite_result", {})
        suite_b = run_b.get("suite_result", {})

        # Calculate detailed changes
        changes = self._calculate_changes(suite_a, suite_b)

        # Confidence delta
        conf_a = suite_a.get("confidence_score", 0)
        conf_b = suite_b.get("confidence_score", 0)
        conf_delta = conf_b - conf_a

        # Interpretation shift
        interp_a = run_a.get("interpretation")
        interp_b = run_b.get("interpretation")
        interp_shift = None
        if interp_a and interp_b and interp_a != interp_b:
            interp_shift = f"Changed from: '{interp_a[:100]}...' to: '{interp_b[:100]}...'"

        return TestComparison(
            run_a_id=run_a_id,
            run_b_id=run_b_id,
            run_a_timestamp=run_a["timestamp"],
            run_b_timestamp=run_b["timestamp"],
            time_delta_days=time_delta,
            score_changes=changes.get("score_changes", {}),
            result_changes=changes.get("result_changes", []),
            new_tests=changes.get("new_tests", []),
            removed_tests=changes.get("removed_tests", []),
            overall_trend=changes.get("trend", "unknown"),
            confidence_delta=conf_delta,
            interpretation_a=interp_a,
            interpretation_b=interp_b,
            interpretation_shift=interp_shift,
        )

    def get_trajectory(
        self,
        battery_id: str,
        limit: int = 20,
    ) -> Dict:
        """
        Get developmental trajectory for a battery over time.

        Returns summary of how tests have evolved across runs.
        """
        results = self.get_results(battery_id=battery_id, limit=limit)

        if not results:
            return {
                "battery_id": battery_id,
                "run_count": 0,
                "message": "No results found",
            }

        # Reverse to chronological order
        results = list(reversed(results))

        # Track confidence over time
        confidence_history = []
        for r in results:
            suite = r.get("suite_result", {})
            confidence_history.append({
                "run_id": r.get("id"),
                "timestamp": r.get("timestamp"),
                "confidence": suite.get("confidence_score", 0),
                "passed": suite.get("passed", 0),
                "failed": suite.get("failed", 0),
            })

        # Calculate overall trajectory
        if len(confidence_history) >= 2:
            first_conf = confidence_history[0]["confidence"]
            last_conf = confidence_history[-1]["confidence"]
            delta = last_conf - first_conf

            if delta > 0.1:
                trajectory = "improving"
            elif delta < -0.1:
                trajectory = "declining"
            else:
                trajectory = "stable"
        else:
            trajectory = "insufficient_data"

        # Track per-test trends
        test_trends = {}
        for r in results:
            for tr in r.get("suite_result", {}).get("test_results", []):
                test_id = tr.get("test_id")
                if test_id not in test_trends:
                    test_trends[test_id] = []
                test_trends[test_id].append({
                    "timestamp": r.get("timestamp"),
                    "result": tr.get("result"),
                    "score": tr.get("score"),
                })

        return {
            "battery_id": battery_id,
            "battery_name": results[-1].get("battery_name") if results else None,
            "run_count": len(results),
            "first_run": results[0].get("timestamp") if results else None,
            "last_run": results[-1].get("timestamp") if results else None,
            "overall_trajectory": trajectory,
            "confidence_history": confidence_history,
            "test_trends": test_trends,
        }

    def add_interpretation(
        self,
        result_id: str,
        interpretation: str,
        interpreted_by: str = "cass",
    ) -> Dict:
        """Add or update interpretation for a test run"""
        results = self._load_results()

        for r in results:
            if r.get("id") == result_id:
                r["interpretation"] = interpretation
                r["interpretation_by"] = interpreted_by
                r["interpretation_timestamp"] = datetime.now().isoformat()
                self._save_results(results)
                return r

        raise ValueError(f"Result not found: {result_id}")
