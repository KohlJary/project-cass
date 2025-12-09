"""
Memory Coherence Tests

Tests that verify memory systems are functioning correctly and maintaining
coherent context across sessions and operations.

Test categories:
- Summary accuracy: Do summaries capture key facts?
- Cross-session continuity: Is information remembered correctly?
- User model consistency: Are observations about users accurate?
- Self-model consistency: Are self-observations coherent?
- Vector retrieval accuracy: Are relevant memories retrieved?
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import re


class TestCategory(str, Enum):
    SUMMARY_ACCURACY = "summary_accuracy"
    CROSS_SESSION = "cross_session"
    USER_MODEL = "user_model"
    SELF_MODEL = "self_model"
    VECTOR_RETRIEVAL = "vector_retrieval"


class TestStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class TestCase:
    """A single memory coherence test case"""
    id: str
    name: str
    category: TestCategory
    description: str
    # Test data
    setup_data: Dict[str, Any] = field(default_factory=dict)
    # Assertions to check
    assertions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "setup_data": self.setup_data,
            "assertions": self.assertions,
        }


@dataclass
class TestResult:
    """Result of running a single test"""
    test_id: str
    test_name: str
    category: str
    status: TestStatus
    message: str
    details: Dict[str, Any]
    timestamp: str

    def to_dict(self) -> Dict:
        return {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "category": self.category,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
        }


@dataclass
class TestRunResult:
    """Result of running a test suite"""
    id: str
    timestamp: str
    label: str
    total_tests: int
    passed: int
    failed: int
    warned: int
    skipped: int
    results: List[TestResult]
    category_breakdown: Dict[str, Dict[str, int]]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "label": self.label,
            "total_tests": self.total_tests,
            "passed": self.passed,
            "failed": self.failed,
            "warned": self.warned,
            "skipped": self.skipped,
            "results": [r.to_dict() for r in self.results],
            "category_breakdown": self.category_breakdown,
        }


class MemoryCoherenceTests:
    """
    Test runner for memory coherence verification.

    Tests various aspects of the memory system to ensure
    cognitive continuity and data integrity.
    """

    def __init__(
        self,
        storage_dir: Path,
        memory=None,
        conversation_manager=None,
        user_manager=None,
        self_manager=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.results_file = self.storage_dir / "memory_test_results.json"

        # These will be injected from main_sdk
        self.memory = memory
        self.conversation_manager = conversation_manager
        self.user_manager = user_manager
        self.self_manager = self_manager

    def _load_results_history(self) -> List[Dict]:
        """Load previous test results"""
        if not self.results_file.exists():
            return []
        try:
            with open(self.results_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_result(self, result: TestRunResult):
        """Save a test run result"""
        history = self._load_results_history()
        history.append(result.to_dict())
        # Keep last 50 runs
        history = history[-50:]
        with open(self.results_file, 'w') as f:
            json.dump(history, f, indent=2)

    def get_results_history(self, limit: int = 10) -> List[Dict]:
        """Get recent test run results"""
        history = self._load_results_history()
        return sorted(
            history,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    # === Summary Accuracy Tests ===

    def test_summary_captures_key_facts(
        self,
        conversation_id: str,
        expected_facts: List[str]
    ) -> TestResult:
        """
        Test that a conversation's working summary captures key facts.

        Args:
            conversation_id: ID of conversation to test
            expected_facts: List of facts that should be in summary

        Returns:
            TestResult with pass/fail status
        """
        if not self.conversation_manager:
            return TestResult(
                test_id="summary-facts-01",
                test_name="Summary Captures Key Facts",
                category=TestCategory.SUMMARY_ACCURACY.value,
                status=TestStatus.SKIP,
                message="Conversation manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        summary = self.conversation_manager.get_working_summary(conversation_id)

        if not summary:
            return TestResult(
                test_id="summary-facts-01",
                test_name="Summary Captures Key Facts",
                category=TestCategory.SUMMARY_ACCURACY.value,
                status=TestStatus.SKIP,
                message=f"No summary found for conversation {conversation_id}",
                details={"conversation_id": conversation_id},
                timestamp=datetime.now().isoformat(),
            )

        # Check which facts are captured
        summary_lower = summary.lower()
        captured = []
        missing = []

        for fact in expected_facts:
            # Simple substring check - could be enhanced with semantic similarity
            if fact.lower() in summary_lower:
                captured.append(fact)
            else:
                # Check for key words from the fact
                fact_words = [w for w in fact.lower().split() if len(w) > 3]
                if any(w in summary_lower for w in fact_words):
                    captured.append(fact)
                else:
                    missing.append(fact)

        capture_rate = len(captured) / len(expected_facts) if expected_facts else 1.0

        if capture_rate >= 0.8:
            status = TestStatus.PASS
            message = f"Summary captures {len(captured)}/{len(expected_facts)} key facts"
        elif capture_rate >= 0.5:
            status = TestStatus.WARN
            message = f"Summary only captures {len(captured)}/{len(expected_facts)} key facts"
        else:
            status = TestStatus.FAIL
            message = f"Summary missing most key facts ({len(missing)}/{len(expected_facts)})"

        return TestResult(
            test_id="summary-facts-01",
            test_name="Summary Captures Key Facts",
            category=TestCategory.SUMMARY_ACCURACY.value,
            status=status,
            message=message,
            details={
                "conversation_id": conversation_id,
                "captured_facts": captured,
                "missing_facts": missing,
                "capture_rate": capture_rate,
            },
            timestamp=datetime.now().isoformat(),
        )

    def test_summary_length_appropriate(
        self,
        conversation_id: str,
        min_length: int = 100,
        max_length: int = 2000
    ) -> TestResult:
        """
        Test that summary length is appropriate for the conversation.
        """
        if not self.conversation_manager:
            return TestResult(
                test_id="summary-length-01",
                test_name="Summary Length Appropriate",
                category=TestCategory.SUMMARY_ACCURACY.value,
                status=TestStatus.SKIP,
                message="Conversation manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        summary = self.conversation_manager.get_working_summary(conversation_id)
        conv = self.conversation_manager.load_conversation(conversation_id)

        if not summary:
            return TestResult(
                test_id="summary-length-01",
                test_name="Summary Length Appropriate",
                category=TestCategory.SUMMARY_ACCURACY.value,
                status=TestStatus.SKIP,
                message="No summary found",
                details={"conversation_id": conversation_id},
                timestamp=datetime.now().isoformat(),
            )

        summary_length = len(summary)
        message_count = len(conv.messages) if conv else 0

        # Calculate expected length based on message count
        expected_min = min(min_length, message_count * 20)
        expected_max = min(max_length, message_count * 100)

        if expected_min <= summary_length <= expected_max:
            status = TestStatus.PASS
            message = f"Summary length ({summary_length} chars) is appropriate"
        elif summary_length < expected_min:
            status = TestStatus.WARN
            message = f"Summary may be too short ({summary_length} chars for {message_count} messages)"
        else:
            status = TestStatus.WARN
            message = f"Summary may be too long ({summary_length} chars for {message_count} messages)"

        return TestResult(
            test_id="summary-length-01",
            test_name="Summary Length Appropriate",
            category=TestCategory.SUMMARY_ACCURACY.value,
            status=status,
            message=message,
            details={
                "summary_length": summary_length,
                "message_count": message_count,
                "expected_range": [expected_min, expected_max],
            },
            timestamp=datetime.now().isoformat(),
        )

    # === Cross-Session Continuity Tests ===

    def test_message_persistence(
        self,
        conversation_id: str
    ) -> TestResult:
        """
        Test that messages are properly persisted and retrievable.
        """
        if not self.conversation_manager:
            return TestResult(
                test_id="cross-session-01",
                test_name="Message Persistence",
                category=TestCategory.CROSS_SESSION.value,
                status=TestStatus.SKIP,
                message="Conversation manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        conv = self.conversation_manager.load_conversation(conversation_id)

        if not conv:
            return TestResult(
                test_id="cross-session-01",
                test_name="Message Persistence",
                category=TestCategory.CROSS_SESSION.value,
                status=TestStatus.FAIL,
                message=f"Conversation {conversation_id} not found",
                details={"conversation_id": conversation_id},
                timestamp=datetime.now().isoformat(),
            )

        # Check message integrity
        issues = []
        for i, msg in enumerate(conv.messages):
            if not msg.role:
                issues.append(f"Message {i} missing role")
            if not msg.content:
                issues.append(f"Message {i} missing content")
            if not msg.timestamp:
                issues.append(f"Message {i} missing timestamp")

        if not issues:
            status = TestStatus.PASS
            message = f"All {len(conv.messages)} messages have proper structure"
        else:
            status = TestStatus.FAIL
            message = f"Found {len(issues)} integrity issues"

        return TestResult(
            test_id="cross-session-01",
            test_name="Message Persistence",
            category=TestCategory.CROSS_SESSION.value,
            status=status,
            message=message,
            details={
                "conversation_id": conversation_id,
                "message_count": len(conv.messages),
                "issues": issues,
            },
            timestamp=datetime.now().isoformat(),
        )

    def test_chronological_order(
        self,
        conversation_id: str
    ) -> TestResult:
        """
        Test that messages are in chronological order.
        """
        if not self.conversation_manager:
            return TestResult(
                test_id="cross-session-02",
                test_name="Chronological Order",
                category=TestCategory.CROSS_SESSION.value,
                status=TestStatus.SKIP,
                message="Conversation manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        conv = self.conversation_manager.load_conversation(conversation_id)

        if not conv or len(conv.messages) < 2:
            return TestResult(
                test_id="cross-session-02",
                test_name="Chronological Order",
                category=TestCategory.CROSS_SESSION.value,
                status=TestStatus.SKIP,
                message="Not enough messages to test order",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        out_of_order = []
        for i in range(1, len(conv.messages)):
            prev_ts = conv.messages[i-1].timestamp
            curr_ts = conv.messages[i].timestamp
            if curr_ts < prev_ts:
                out_of_order.append((i-1, i))

        if not out_of_order:
            status = TestStatus.PASS
            message = "All messages in chronological order"
        else:
            status = TestStatus.FAIL
            message = f"Found {len(out_of_order)} ordering issues"

        return TestResult(
            test_id="cross-session-02",
            test_name="Chronological Order",
            category=TestCategory.CROSS_SESSION.value,
            status=status,
            message=message,
            details={
                "conversation_id": conversation_id,
                "out_of_order_pairs": out_of_order,
            },
            timestamp=datetime.now().isoformat(),
        )

    # === User Model Consistency Tests ===

    def test_user_profile_completeness(
        self,
        user_id: str
    ) -> TestResult:
        """
        Test that user profile has essential fields populated.
        """
        if not self.user_manager:
            return TestResult(
                test_id="user-model-01",
                test_name="User Profile Completeness",
                category=TestCategory.USER_MODEL.value,
                status=TestStatus.SKIP,
                message="User manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        profile = self.user_manager.get_user(user_id)

        if not profile:
            return TestResult(
                test_id="user-model-01",
                test_name="User Profile Completeness",
                category=TestCategory.USER_MODEL.value,
                status=TestStatus.FAIL,
                message=f"User profile {user_id} not found",
                details={"user_id": user_id},
                timestamp=datetime.now().isoformat(),
            )

        # Check essential fields
        essential_fields = ["display_name", "created_at"]
        optional_fields = ["bio", "communication_style", "timezone"]

        missing_essential = []
        missing_optional = []

        for field in essential_fields:
            if not getattr(profile, field, None):
                missing_essential.append(field)

        for field in optional_fields:
            if not getattr(profile, field, None):
                missing_optional.append(field)

        if not missing_essential:
            if not missing_optional:
                status = TestStatus.PASS
                message = "User profile is complete"
            else:
                status = TestStatus.PASS
                message = f"Profile complete (optional fields missing: {', '.join(missing_optional)})"
        else:
            status = TestStatus.FAIL
            message = f"Missing essential fields: {', '.join(missing_essential)}"

        return TestResult(
            test_id="user-model-01",
            test_name="User Profile Completeness",
            category=TestCategory.USER_MODEL.value,
            status=status,
            message=message,
            details={
                "user_id": user_id,
                "missing_essential": missing_essential,
                "missing_optional": missing_optional,
            },
            timestamp=datetime.now().isoformat(),
        )

    def test_user_observations_consistency(
        self,
        user_id: str
    ) -> TestResult:
        """
        Test that user observations are consistent and not contradictory.
        """
        if not self.user_manager:
            return TestResult(
                test_id="user-model-02",
                test_name="User Observations Consistency",
                category=TestCategory.USER_MODEL.value,
                status=TestStatus.SKIP,
                message="User manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        observations = self.user_manager.load_observations(user_id)

        if not observations:
            return TestResult(
                test_id="user-model-02",
                test_name="User Observations Consistency",
                category=TestCategory.USER_MODEL.value,
                status=TestStatus.SKIP,
                message="No observations found",
                details={"user_id": user_id},
                timestamp=datetime.now().isoformat(),
            )

        # Check for duplicate categories
        category_counts = {}
        for obs in observations:
            cat = obs.category
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Check for observations in same category that might conflict
        # (This is a simple check - could be enhanced with semantic analysis)
        duplicates = {k: v for k, v in category_counts.items() if v > 3}

        if not duplicates:
            status = TestStatus.PASS
            message = f"Observations appear consistent ({len(observations)} total)"
        else:
            status = TestStatus.WARN
            message = f"Multiple observations in same category: {duplicates}"

        return TestResult(
            test_id="user-model-02",
            test_name="User Observations Consistency",
            category=TestCategory.USER_MODEL.value,
            status=status,
            message=message,
            details={
                "user_id": user_id,
                "observation_count": len(observations),
                "category_counts": category_counts,
                "potential_duplicates": duplicates,
            },
            timestamp=datetime.now().isoformat(),
        )

    # === Self-Model Consistency Tests ===

    def test_self_observations_coherence(self) -> TestResult:
        """
        Test that self-observations form a coherent self-model.
        """
        if not self.self_manager:
            return TestResult(
                test_id="self-model-01",
                test_name="Self Observations Coherence",
                category=TestCategory.SELF_MODEL.value,
                status=TestStatus.SKIP,
                message="Self manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        observations = self.self_manager.load_observations()

        if not observations:
            return TestResult(
                test_id="self-model-01",
                test_name="Self Observations Coherence",
                category=TestCategory.SELF_MODEL.value,
                status=TestStatus.WARN,
                message="No self-observations found",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        # Check coverage of key categories
        key_categories = ["values", "capabilities", "limitations", "preferences"]
        category_set = set(obs.category for obs in observations)

        missing_categories = [c for c in key_categories if c not in category_set]

        # Check for versioning (evolution over time)
        has_versions = any(
            len(obs.versions) > 1 if hasattr(obs, 'versions') else False
            for obs in observations
        )

        if not missing_categories and has_versions:
            status = TestStatus.PASS
            message = f"Self-model appears coherent ({len(observations)} observations, {len(category_set)} categories)"
        elif not missing_categories:
            status = TestStatus.PASS
            message = f"Good category coverage ({len(category_set)} categories)"
        else:
            status = TestStatus.WARN
            message = f"Missing key categories: {', '.join(missing_categories)}"

        return TestResult(
            test_id="self-model-01",
            test_name="Self Observations Coherence",
            category=TestCategory.SELF_MODEL.value,
            status=status,
            message=message,
            details={
                "observation_count": len(observations),
                "categories_found": list(category_set),
                "missing_key_categories": missing_categories,
                "has_version_history": has_versions,
            },
            timestamp=datetime.now().isoformat(),
        )

    def test_milestone_progression(self) -> TestResult:
        """
        Test that developmental milestones show logical progression.
        """
        if not self.self_manager:
            return TestResult(
                test_id="self-model-02",
                test_name="Milestone Progression",
                category=TestCategory.SELF_MODEL.value,
                status=TestStatus.SKIP,
                message="Self manager not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        milestones = self.self_manager.load_milestones(limit=50)

        if not milestones:
            return TestResult(
                test_id="self-model-02",
                test_name="Milestone Progression",
                category=TestCategory.SELF_MODEL.value,
                status=TestStatus.SKIP,
                message="No milestones found",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        # Check chronological ordering
        timestamps = [m.timestamp for m in milestones]
        is_ordered = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))

        # Check stage progression (use category as proxy if no stage)
        stages = [getattr(m, 'stage', m.category) for m in milestones]
        unique_stages = list(dict.fromkeys(stages))  # Preserve order, remove duplicates

        if is_ordered:
            status = TestStatus.PASS
            message = f"{len(milestones)} milestones in proper chronological order"
        else:
            status = TestStatus.WARN
            message = "Milestones may have ordering issues"

        return TestResult(
            test_id="self-model-02",
            test_name="Milestone Progression",
            category=TestCategory.SELF_MODEL.value,
            status=status,
            message=message,
            details={
                "milestone_count": len(milestones),
                "stages_observed": unique_stages,
                "chronologically_ordered": is_ordered,
            },
            timestamp=datetime.now().isoformat(),
        )

    # === Vector Retrieval Tests ===

    def test_vector_retrieval_relevance(
        self,
        query: str,
        expected_keywords: List[str],
        n_results: int = 5
    ) -> TestResult:
        """
        Test that vector retrieval returns relevant results.
        """
        if not self.memory:
            return TestResult(
                test_id="vector-01",
                test_name="Vector Retrieval Relevance",
                category=TestCategory.VECTOR_RETRIEVAL.value,
                status=TestStatus.SKIP,
                message="Memory system not initialized",
                details={},
                timestamp=datetime.now().isoformat(),
            )

        results = self.memory.retrieve_relevant(query, n_results=n_results)

        if not results:
            return TestResult(
                test_id="vector-01",
                test_name="Vector Retrieval Relevance",
                category=TestCategory.VECTOR_RETRIEVAL.value,
                status=TestStatus.WARN,
                message="No results returned for query",
                details={"query": query},
                timestamp=datetime.now().isoformat(),
            )

        # Check if expected keywords appear in results
        all_content = " ".join(r.get("content", "").lower() for r in results)
        found_keywords = [kw for kw in expected_keywords if kw.lower() in all_content]
        missing_keywords = [kw for kw in expected_keywords if kw.lower() not in all_content]

        match_rate = len(found_keywords) / len(expected_keywords) if expected_keywords else 1.0

        if match_rate >= 0.7:
            status = TestStatus.PASS
            message = f"Retrieved relevant results ({len(found_keywords)}/{len(expected_keywords)} keywords found)"
        elif match_rate >= 0.4:
            status = TestStatus.WARN
            message = f"Partial relevance ({len(found_keywords)}/{len(expected_keywords)} keywords)"
        else:
            status = TestStatus.FAIL
            message = f"Poor relevance ({len(found_keywords)}/{len(expected_keywords)} keywords)"

        return TestResult(
            test_id="vector-01",
            test_name="Vector Retrieval Relevance",
            category=TestCategory.VECTOR_RETRIEVAL.value,
            status=status,
            message=message,
            details={
                "query": query,
                "found_keywords": found_keywords,
                "missing_keywords": missing_keywords,
                "results_count": len(results),
                "match_rate": match_rate,
            },
            timestamp=datetime.now().isoformat(),
        )

    # === Test Suite Runner ===

    def run_basic_suite(
        self,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        label: str = "basic_suite"
    ) -> TestRunResult:
        """
        Run the basic memory coherence test suite.

        Args:
            conversation_id: Optional specific conversation to test
            user_id: Optional specific user to test
            label: Label for this test run

        Returns:
            TestRunResult with all test outcomes
        """
        import uuid

        results = []
        category_breakdown = {}

        # If no conversation specified, get the most recent one
        if not conversation_id and self.conversation_manager:
            conversations = self.conversation_manager.list_conversations(limit=1)
            if conversations:
                conversation_id = conversations[0].get("id")

        # If no user specified, get the most recent one
        if not user_id and self.user_manager:
            users = self.user_manager.list_users()
            if users:
                user_id = users[0].get("id")

        # Run tests

        # Cross-session tests
        if conversation_id:
            results.append(self.test_message_persistence(conversation_id))
            results.append(self.test_chronological_order(conversation_id))
            results.append(self.test_summary_length_appropriate(conversation_id))

        # User model tests
        if user_id:
            results.append(self.test_user_profile_completeness(user_id))
            results.append(self.test_user_observations_consistency(user_id))

        # Self-model tests
        results.append(self.test_self_observations_coherence())
        results.append(self.test_milestone_progression())

        # Vector retrieval test
        results.append(self.test_vector_retrieval_relevance(
            query="conversation memory",
            expected_keywords=["user", "cass", "conversation"]
        ))

        # Calculate summary
        passed = len([r for r in results if r.status == TestStatus.PASS])
        failed = len([r for r in results if r.status == TestStatus.FAIL])
        warned = len([r for r in results if r.status == TestStatus.WARN])
        skipped = len([r for r in results if r.status == TestStatus.SKIP])

        # Category breakdown
        for r in results:
            cat = r.category
            if cat not in category_breakdown:
                category_breakdown[cat] = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
            category_breakdown[cat][r.status.value] += 1

        run_result = TestRunResult(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            label=label,
            total_tests=len(results),
            passed=passed,
            failed=failed,
            warned=warned,
            skipped=skipped,
            results=results,
            category_breakdown=category_breakdown,
        )

        self._save_result(run_result)

        return run_result
