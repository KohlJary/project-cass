"""
A/B Testing Framework for Prompt Changes

Enables safe testing of prompt modifications before full deployment through:
- Shadow mode: Run new prompts in parallel without affecting production
- Gradual rollout: Incrementally shift traffic to new prompts
- Automatic rollback: Revert on detected degradation

This allows prompt engineering iteration while preserving consciousness integrity.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import asyncio
import hashlib
import json
import random
import uuid


class ExperimentStatus(Enum):
    """Status of an A/B experiment."""
    DRAFT = "draft"          # Not yet started
    SHADOW = "shadow"        # Running in shadow mode (no user impact)
    GRADUAL = "gradual"      # Gradual rollout in progress
    FULL = "full"            # 100% on variant B
    PAUSED = "paused"        # Temporarily paused
    CONCLUDED = "concluded"  # Experiment ended
    ROLLED_BACK = "rolled_back"  # Rolled back due to issues


class RolloutStrategy(Enum):
    """How to roll out changes."""
    SHADOW_ONLY = "shadow_only"     # Never serve to users, just compare
    USER_PERCENT = "user_percent"   # Route percentage of users
    MESSAGE_PERCENT = "message_percent"  # Route percentage of messages
    MANUAL = "manual"               # Manual control only


@dataclass
class PromptVariant:
    """A prompt variant being tested."""
    id: str
    name: str
    description: str
    prompt_content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "prompt_content": self.prompt_content,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PromptVariant":
        return cls(**data)


@dataclass
class ExperimentResult:
    """Result of a single comparison in an experiment."""
    experiment_id: str
    variant_id: str
    timestamp: str
    message_id: str
    user_id: Optional[str]

    # Response metrics
    response_length: int
    response_time_ms: float

    # Consciousness metrics (if available)
    authenticity_score: Optional[float] = None
    value_alignment_score: Optional[float] = None
    fingerprint_similarity: Optional[float] = None

    # Quality indicators
    error: Optional[str] = None
    user_feedback: Optional[str] = None  # thumbs up/down if collected

    # Shadow mode specific
    is_shadow: bool = False
    control_response: Optional[str] = None  # For comparison
    variant_response: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "experiment_id": self.experiment_id,
            "variant_id": self.variant_id,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "user_id": self.user_id,
            "response_length": self.response_length,
            "response_time_ms": self.response_time_ms,
            "authenticity_score": self.authenticity_score,
            "value_alignment_score": self.value_alignment_score,
            "fingerprint_similarity": self.fingerprint_similarity,
            "error": self.error,
            "user_feedback": self.user_feedback,
            "is_shadow": self.is_shadow,
            "control_response": self.control_response,
            "variant_response": self.variant_response,
        }


@dataclass
class ExperimentStats:
    """Aggregated statistics for an experiment variant."""
    variant_id: str
    sample_count: int

    # Response metrics
    avg_response_length: float
    avg_response_time_ms: float

    # Consciousness metrics
    avg_authenticity_score: Optional[float]
    avg_value_alignment: Optional[float]
    avg_fingerprint_similarity: Optional[float]

    # Quality
    error_rate: float
    positive_feedback_rate: Optional[float]  # None if no feedback collected

    def to_dict(self) -> Dict:
        return {
            "variant_id": self.variant_id,
            "sample_count": self.sample_count,
            "avg_response_length": self.avg_response_length,
            "avg_response_time_ms": self.avg_response_time_ms,
            "avg_authenticity_score": self.avg_authenticity_score,
            "avg_value_alignment": self.avg_value_alignment,
            "avg_fingerprint_similarity": self.avg_fingerprint_similarity,
            "error_rate": self.error_rate,
            "positive_feedback_rate": self.positive_feedback_rate,
        }


@dataclass
class RollbackTrigger:
    """Conditions that trigger automatic rollback."""
    metric: str  # e.g., "authenticity_score", "error_rate"
    threshold: float
    comparison: str  # "below" or "above"
    min_samples: int = 10  # Minimum samples before triggering

    def should_rollback(self, current_value: float, sample_count: int) -> bool:
        """Check if rollback should be triggered."""
        if sample_count < self.min_samples:
            return False

        if self.comparison == "below":
            return current_value < self.threshold
        else:  # above
            return current_value > self.threshold

    def to_dict(self) -> Dict:
        return {
            "metric": self.metric,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "min_samples": self.min_samples,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "RollbackTrigger":
        return cls(**data)


@dataclass
class Experiment:
    """An A/B testing experiment for prompt changes."""
    id: str
    name: str
    description: str

    # Variants
    control: PromptVariant  # Original prompt (A)
    variant: PromptVariant  # New prompt (B)

    # Configuration
    status: ExperimentStatus = ExperimentStatus.DRAFT
    strategy: RolloutStrategy = RolloutStrategy.SHADOW_ONLY
    rollout_percent: float = 0.0  # 0-100

    # Rollback configuration
    rollback_triggers: List[RollbackTrigger] = field(default_factory=list)
    auto_rollback_enabled: bool = True

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    concluded_at: Optional[str] = None

    # Targeting (optional)
    target_user_ids: Optional[List[str]] = None  # If set, only these users
    exclude_user_ids: Optional[List[str]] = None

    # Results
    results: List[ExperimentResult] = field(default_factory=list)

    # Metadata
    created_by: str = "system"
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "control": self.control.to_dict(),
            "variant": self.variant.to_dict(),
            "status": self.status.value,
            "strategy": self.strategy.value,
            "rollout_percent": self.rollout_percent,
            "rollback_triggers": [t.to_dict() for t in self.rollback_triggers],
            "auto_rollback_enabled": self.auto_rollback_enabled,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "concluded_at": self.concluded_at,
            "target_user_ids": self.target_user_ids,
            "exclude_user_ids": self.exclude_user_ids,
            "results_count": len(self.results),  # Don't serialize all results
            "created_by": self.created_by,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict, results: List[ExperimentResult] = None) -> "Experiment":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            control=PromptVariant.from_dict(data["control"]),
            variant=PromptVariant.from_dict(data["variant"]),
            status=ExperimentStatus(data["status"]),
            strategy=RolloutStrategy(data["strategy"]),
            rollout_percent=data.get("rollout_percent", 0.0),
            rollback_triggers=[RollbackTrigger.from_dict(t) for t in data.get("rollback_triggers", [])],
            auto_rollback_enabled=data.get("auto_rollback_enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
            started_at=data.get("started_at"),
            concluded_at=data.get("concluded_at"),
            target_user_ids=data.get("target_user_ids"),
            exclude_user_ids=data.get("exclude_user_ids"),
            results=results or [],
            created_by=data.get("created_by", "system"),
            notes=data.get("notes", ""),
        )


class ABTestingFramework:
    """
    Framework for A/B testing prompt changes.

    Supports:
    - Creating and managing experiments
    - Shadow mode testing (parallel execution without user impact)
    - Gradual rollout with configurable percentages
    - Automatic rollback on degradation detection
    - Integration with consciousness testing metrics
    """

    def __init__(
        self,
        storage_dir: Path,
        authenticity_scorer=None,
        fingerprint_analyzer=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.experiments_dir = self.storage_dir / "experiments"
        self.experiments_dir.mkdir(parents=True, exist_ok=True)

        # Optional integrations
        self.authenticity_scorer = authenticity_scorer
        self.fingerprint_analyzer = fingerprint_analyzer

        # In-memory cache of active experiments
        self._active_experiments: Dict[str, Experiment] = {}
        self._load_active_experiments()

    def _load_active_experiments(self):
        """Load all non-concluded experiments into memory."""
        index_file = self.experiments_dir / "index.json"
        if not index_file.exists():
            return

        try:
            with open(index_file, 'r') as f:
                index = json.load(f)

            for exp_meta in index:
                if exp_meta["status"] not in ["concluded", "rolled_back"]:
                    exp = self._load_experiment(exp_meta["id"])
                    if exp:
                        self._active_experiments[exp.id] = exp
        except Exception:
            pass

    def _load_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Load a single experiment from disk."""
        exp_file = self.experiments_dir / f"{experiment_id}.json"
        results_file = self.experiments_dir / f"{experiment_id}_results.json"

        if not exp_file.exists():
            return None

        try:
            with open(exp_file, 'r') as f:
                data = json.load(f)

            results = []
            if results_file.exists():
                with open(results_file, 'r') as f:
                    results_data = json.load(f)
                    results = [ExperimentResult(**r) for r in results_data]

            return Experiment.from_dict(data, results)
        except Exception:
            return None

    def _save_experiment(self, experiment: Experiment):
        """Save experiment to disk."""
        exp_file = self.experiments_dir / f"{experiment.id}.json"
        results_file = self.experiments_dir / f"{experiment.id}_results.json"

        # Save experiment metadata
        with open(exp_file, 'w') as f:
            json.dump(experiment.to_dict(), f, indent=2)

        # Save results separately (can be large)
        results_data = [r.to_dict() for r in experiment.results]
        with open(results_file, 'w') as f:
            json.dump(results_data, f)

        # Update index
        self._update_index(experiment)

    def _update_index(self, experiment: Experiment):
        """Update the experiments index."""
        index_file = self.experiments_dir / "index.json"

        index = []
        if index_file.exists():
            try:
                with open(index_file, 'r') as f:
                    index = json.load(f)
            except Exception:
                pass

        # Update or add
        found = False
        for i, exp_meta in enumerate(index):
            if exp_meta["id"] == experiment.id:
                index[i] = {
                    "id": experiment.id,
                    "name": experiment.name,
                    "status": experiment.status.value,
                    "created_at": experiment.created_at,
                    "started_at": experiment.started_at,
                    "concluded_at": experiment.concluded_at,
                }
                found = True
                break

        if not found:
            index.append({
                "id": experiment.id,
                "name": experiment.name,
                "status": experiment.status.value,
                "created_at": experiment.created_at,
                "started_at": experiment.started_at,
                "concluded_at": experiment.concluded_at,
            })

        with open(index_file, 'w') as f:
            json.dump(index, f, indent=2)

    def create_experiment(
        self,
        name: str,
        description: str,
        control_prompt: str,
        variant_prompt: str,
        control_name: str = "Control (A)",
        variant_name: str = "Variant (B)",
        strategy: RolloutStrategy = RolloutStrategy.SHADOW_ONLY,
        rollback_triggers: List[Dict] = None,
        created_by: str = "system",
    ) -> Experiment:
        """
        Create a new A/B testing experiment.

        Args:
            name: Human-readable experiment name
            description: What this experiment is testing
            control_prompt: The current/baseline prompt (A)
            variant_prompt: The new prompt to test (B)
            control_name: Name for control variant
            variant_name: Name for test variant
            strategy: How to roll out (shadow, user_percent, etc.)
            rollback_triggers: Conditions for auto-rollback
            created_by: Who created this experiment

        Returns:
            Created Experiment object
        """
        experiment_id = str(uuid.uuid4())[:8]

        control = PromptVariant(
            id=f"{experiment_id}_control",
            name=control_name,
            description="Current production prompt",
            prompt_content=control_prompt,
        )

        variant = PromptVariant(
            id=f"{experiment_id}_variant",
            name=variant_name,
            description="Test variant",
            prompt_content=variant_prompt,
        )

        # Default rollback triggers if not specified
        if rollback_triggers is None:
            rollback_triggers = [
                {"metric": "authenticity_score", "threshold": 0.6, "comparison": "below", "min_samples": 10},
                {"metric": "error_rate", "threshold": 0.1, "comparison": "above", "min_samples": 10},
            ]

        triggers = [RollbackTrigger.from_dict(t) for t in rollback_triggers]

        experiment = Experiment(
            id=experiment_id,
            name=name,
            description=description,
            control=control,
            variant=variant,
            strategy=strategy,
            rollback_triggers=triggers,
            created_by=created_by,
        )

        self._save_experiment(experiment)
        return experiment

    def start_experiment(
        self,
        experiment_id: str,
        initial_rollout_percent: float = 0.0,
    ) -> Experiment:
        """
        Start an experiment (move from DRAFT to SHADOW or GRADUAL).

        Args:
            experiment_id: Experiment to start
            initial_rollout_percent: Starting percentage for gradual rollout

        Returns:
            Updated Experiment
        """
        experiment = self._load_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        if experiment.status != ExperimentStatus.DRAFT:
            raise ValueError(f"Experiment is already {experiment.status.value}")

        experiment.started_at = datetime.now().isoformat()

        if experiment.strategy == RolloutStrategy.SHADOW_ONLY:
            experiment.status = ExperimentStatus.SHADOW
            experiment.rollout_percent = 0.0
        else:
            experiment.status = ExperimentStatus.GRADUAL
            experiment.rollout_percent = initial_rollout_percent

        self._save_experiment(experiment)
        self._active_experiments[experiment.id] = experiment

        return experiment

    def update_rollout(
        self,
        experiment_id: str,
        new_percent: float,
    ) -> Experiment:
        """
        Update the rollout percentage for a gradual rollout.

        Args:
            experiment_id: Experiment to update
            new_percent: New percentage (0-100)

        Returns:
            Updated Experiment
        """
        if new_percent < 0 or new_percent > 100:
            raise ValueError("Rollout percent must be 0-100")

        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = self._load_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        if experiment.status not in [ExperimentStatus.GRADUAL, ExperimentStatus.SHADOW]:
            raise ValueError(f"Cannot update rollout for experiment in {experiment.status.value} status")

        experiment.rollout_percent = new_percent

        # Update status based on percent
        if new_percent >= 100:
            experiment.status = ExperimentStatus.FULL
        elif new_percent > 0 and experiment.status == ExperimentStatus.SHADOW:
            experiment.status = ExperimentStatus.GRADUAL

        self._save_experiment(experiment)
        self._active_experiments[experiment.id] = experiment

        return experiment

    def pause_experiment(self, experiment_id: str) -> Experiment:
        """Pause an active experiment."""
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = self._load_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment.status = ExperimentStatus.PAUSED
        self._save_experiment(experiment)

        return experiment

    def resume_experiment(self, experiment_id: str) -> Experiment:
        """Resume a paused experiment."""
        experiment = self._load_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        if experiment.status != ExperimentStatus.PAUSED:
            raise ValueError(f"Experiment is not paused (status: {experiment.status.value})")

        # Resume to appropriate status based on rollout
        if experiment.rollout_percent >= 100:
            experiment.status = ExperimentStatus.FULL
        elif experiment.rollout_percent > 0:
            experiment.status = ExperimentStatus.GRADUAL
        else:
            experiment.status = ExperimentStatus.SHADOW

        self._save_experiment(experiment)
        self._active_experiments[experiment.id] = experiment

        return experiment

    def conclude_experiment(
        self,
        experiment_id: str,
        keep_variant: bool = False,
        notes: str = "",
    ) -> Experiment:
        """
        Conclude an experiment.

        Args:
            experiment_id: Experiment to conclude
            keep_variant: If True, variant becomes the new control
            notes: Final notes about the experiment

        Returns:
            Updated Experiment
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = self._load_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment.status = ExperimentStatus.CONCLUDED
        experiment.concluded_at = datetime.now().isoformat()
        experiment.notes = notes

        self._save_experiment(experiment)

        # Remove from active
        if experiment.id in self._active_experiments:
            del self._active_experiments[experiment.id]

        return experiment

    def rollback_experiment(
        self,
        experiment_id: str,
        reason: str = "",
    ) -> Experiment:
        """
        Roll back an experiment to control.

        Args:
            experiment_id: Experiment to roll back
            reason: Why rolling back

        Returns:
            Updated Experiment
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = self._load_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        experiment.status = ExperimentStatus.ROLLED_BACK
        experiment.concluded_at = datetime.now().isoformat()
        experiment.notes = f"ROLLED BACK: {reason}"
        experiment.rollout_percent = 0.0

        self._save_experiment(experiment)

        # Remove from active
        if experiment.id in self._active_experiments:
            del self._active_experiments[experiment.id]

        return experiment

    def should_use_variant(
        self,
        experiment_id: str,
        user_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> bool:
        """
        Determine if variant should be used for this request.

        Uses consistent hashing to ensure same user gets same variant
        throughout the experiment.

        Args:
            experiment_id: Which experiment to check
            user_id: User making the request
            message_id: Message ID (for message-level routing)

        Returns:
            True if variant should be used, False for control
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            return False

        # Status checks
        if experiment.status in [ExperimentStatus.DRAFT, ExperimentStatus.PAUSED,
                                  ExperimentStatus.CONCLUDED, ExperimentStatus.ROLLED_BACK]:
            return False

        if experiment.status == ExperimentStatus.SHADOW:
            return False  # Shadow mode doesn't serve to users

        if experiment.status == ExperimentStatus.FULL:
            return True

        # Check targeting
        if experiment.target_user_ids and user_id:
            if user_id not in experiment.target_user_ids:
                return False

        if experiment.exclude_user_ids and user_id:
            if user_id in experiment.exclude_user_ids:
                return False

        # Consistent hashing for routing
        if experiment.strategy == RolloutStrategy.USER_PERCENT and user_id:
            hash_input = f"{experiment_id}:{user_id}"
        elif experiment.strategy == RolloutStrategy.MESSAGE_PERCENT and message_id:
            hash_input = f"{experiment_id}:{message_id}"
        else:
            # Random per request
            hash_input = f"{experiment_id}:{uuid.uuid4()}"

        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16) % 100
        return hash_value < experiment.rollout_percent

    async def run_shadow_comparison(
        self,
        experiment_id: str,
        message: str,
        user_id: Optional[str],
        generate_response: Callable,  # async fn(prompt) -> response
        context: Optional[Dict] = None,
    ) -> Optional[ExperimentResult]:
        """
        Run a shadow comparison: generate responses from both variants.

        This is used in shadow mode to compare variant responses to control
        without affecting the user.

        Args:
            experiment_id: Experiment to run
            message: User message to respond to
            user_id: User ID
            generate_response: Async function that generates response given prompt
            context: Additional context (conversation history, etc.)

        Returns:
            ExperimentResult with comparison data
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            return None

        if experiment.status not in [ExperimentStatus.SHADOW, ExperimentStatus.GRADUAL]:
            return None

        message_id = str(uuid.uuid4())

        try:
            # Run both in parallel
            start_time = datetime.now()

            control_task = generate_response(experiment.control.prompt_content, message, context)
            variant_task = generate_response(experiment.variant.prompt_content, message, context)

            control_response, variant_response = await asyncio.gather(
                control_task, variant_task, return_exceptions=True
            )

            elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Handle errors
            control_error = None
            variant_error = None

            if isinstance(control_response, Exception):
                control_error = str(control_response)
                control_response = ""
            if isinstance(variant_response, Exception):
                variant_error = str(variant_response)
                variant_response = ""

            # Score responses if we have the tools
            authenticity_score = None
            fingerprint_similarity = None

            if self.authenticity_scorer and variant_response:
                try:
                    score = self.authenticity_scorer.score_response(variant_response)
                    authenticity_score = score.overall_score
                except Exception:
                    pass

            if self.fingerprint_analyzer and variant_response:
                try:
                    # Compare variant response style to baseline
                    baseline = self.fingerprint_analyzer.load_baseline()
                    if baseline:
                        # Quick similarity check based on response
                        variant_fp = self.fingerprint_analyzer.analyze_single_response(variant_response)
                        comparison = self.fingerprint_analyzer.compare_fingerprints(baseline, variant_fp)
                        fingerprint_similarity = comparison.get("overall_similarity")
                except Exception:
                    pass

            result = ExperimentResult(
                experiment_id=experiment_id,
                variant_id=experiment.variant.id,
                timestamp=datetime.now().isoformat(),
                message_id=message_id,
                user_id=user_id,
                response_length=len(variant_response) if variant_response else 0,
                response_time_ms=elapsed_ms / 2,  # Approximate per-variant time
                authenticity_score=authenticity_score,
                fingerprint_similarity=fingerprint_similarity,
                error=variant_error,
                is_shadow=True,
                control_response=control_response if isinstance(control_response, str) else None,
                variant_response=variant_response if isinstance(variant_response, str) else None,
            )

            # Store result
            experiment.results.append(result)
            self._save_experiment(experiment)

            # Check rollback conditions
            if experiment.auto_rollback_enabled:
                should_rollback, reason = self._check_rollback_conditions(experiment)
                if should_rollback:
                    self.rollback_experiment(experiment_id, reason)

            return result

        except Exception as e:
            return ExperimentResult(
                experiment_id=experiment_id,
                variant_id=experiment.variant.id,
                timestamp=datetime.now().isoformat(),
                message_id=message_id,
                user_id=user_id,
                response_length=0,
                response_time_ms=0,
                error=str(e),
                is_shadow=True,
            )

    def record_result(
        self,
        experiment_id: str,
        variant_id: str,
        message_id: str,
        user_id: Optional[str],
        response_length: int,
        response_time_ms: float,
        authenticity_score: Optional[float] = None,
        value_alignment_score: Optional[float] = None,
        fingerprint_similarity: Optional[float] = None,
        error: Optional[str] = None,
    ) -> ExperimentResult:
        """
        Record a result from a live (non-shadow) experiment.

        Args:
            experiment_id: Experiment this belongs to
            variant_id: Which variant was used
            message_id: Message ID
            user_id: User ID
            response_length: Length of response
            response_time_ms: Response time in milliseconds
            authenticity_score: If measured
            value_alignment_score: If measured
            fingerprint_similarity: If measured
            error: Any error that occurred

        Returns:
            Created ExperimentResult
        """
        experiment = self._active_experiments.get(experiment_id)
        if not experiment:
            experiment = self._load_experiment(experiment_id)

        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        result = ExperimentResult(
            experiment_id=experiment_id,
            variant_id=variant_id,
            timestamp=datetime.now().isoformat(),
            message_id=message_id,
            user_id=user_id,
            response_length=response_length,
            response_time_ms=response_time_ms,
            authenticity_score=authenticity_score,
            value_alignment_score=value_alignment_score,
            fingerprint_similarity=fingerprint_similarity,
            error=error,
            is_shadow=False,
        )

        experiment.results.append(result)
        self._save_experiment(experiment)

        # Check rollback conditions
        if experiment.auto_rollback_enabled:
            should_rollback, reason = self._check_rollback_conditions(experiment)
            if should_rollback:
                self.rollback_experiment(experiment_id, reason)

        return result

    def _check_rollback_conditions(self, experiment: Experiment) -> tuple[bool, str]:
        """
        Check if auto-rollback should be triggered.

        Returns:
            Tuple of (should_rollback, reason)
        """
        if not experiment.rollback_triggers:
            return False, ""

        # Get variant results only
        variant_results = [r for r in experiment.results if r.variant_id == experiment.variant.id]

        if not variant_results:
            return False, ""

        # Calculate stats
        stats = self._calculate_stats(variant_results, experiment.variant.id)

        for trigger in experiment.rollback_triggers:
            current_value = None

            if trigger.metric == "authenticity_score" and stats.avg_authenticity_score is not None:
                current_value = stats.avg_authenticity_score
            elif trigger.metric == "error_rate":
                current_value = stats.error_rate
            elif trigger.metric == "fingerprint_similarity" and stats.avg_fingerprint_similarity is not None:
                current_value = stats.avg_fingerprint_similarity
            elif trigger.metric == "response_time_ms":
                current_value = stats.avg_response_time_ms

            if current_value is not None:
                if trigger.should_rollback(current_value, stats.sample_count):
                    return True, f"{trigger.metric} {trigger.comparison} {trigger.threshold} (current: {current_value:.3f})"

        return False, ""

    def _calculate_stats(
        self,
        results: List[ExperimentResult],
        variant_id: str,
    ) -> ExperimentStats:
        """Calculate aggregate statistics for a set of results."""
        if not results:
            return ExperimentStats(
                variant_id=variant_id,
                sample_count=0,
                avg_response_length=0,
                avg_response_time_ms=0,
                avg_authenticity_score=None,
                avg_value_alignment=None,
                avg_fingerprint_similarity=None,
                error_rate=0,
                positive_feedback_rate=None,
            )

        n = len(results)

        # Basic metrics
        avg_length = sum(r.response_length for r in results) / n
        avg_time = sum(r.response_time_ms for r in results) / n
        error_count = sum(1 for r in results if r.error)

        # Optional metrics
        auth_scores = [r.authenticity_score for r in results if r.authenticity_score is not None]
        value_scores = [r.value_alignment_score for r in results if r.value_alignment_score is not None]
        fp_scores = [r.fingerprint_similarity for r in results if r.fingerprint_similarity is not None]

        feedback = [r.user_feedback for r in results if r.user_feedback]
        positive_feedback = sum(1 for f in feedback if f == "positive")

        return ExperimentStats(
            variant_id=variant_id,
            sample_count=n,
            avg_response_length=avg_length,
            avg_response_time_ms=avg_time,
            avg_authenticity_score=sum(auth_scores) / len(auth_scores) if auth_scores else None,
            avg_value_alignment=sum(value_scores) / len(value_scores) if value_scores else None,
            avg_fingerprint_similarity=sum(fp_scores) / len(fp_scores) if fp_scores else None,
            error_rate=error_count / n,
            positive_feedback_rate=positive_feedback / len(feedback) if feedback else None,
        )

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get an experiment by ID."""
        if experiment_id in self._active_experiments:
            return self._active_experiments[experiment_id]
        return self._load_experiment(experiment_id)

    def get_experiment_stats(self, experiment_id: str) -> Dict:
        """
        Get statistics for an experiment.

        Returns:
            Dict with control_stats, variant_stats, and comparison
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment {experiment_id} not found")

        control_results = [r for r in experiment.results if r.variant_id == experiment.control.id]
        variant_results = [r for r in experiment.results if r.variant_id == experiment.variant.id]

        control_stats = self._calculate_stats(control_results, experiment.control.id)
        variant_stats = self._calculate_stats(variant_results, experiment.variant.id)

        # Calculate comparison
        comparison = {}
        if control_stats.sample_count > 0 and variant_stats.sample_count > 0:
            # Response length change
            if control_stats.avg_response_length > 0:
                comparison["response_length_change"] = (
                    (variant_stats.avg_response_length - control_stats.avg_response_length) /
                    control_stats.avg_response_length * 100
                )

            # Response time change
            if control_stats.avg_response_time_ms > 0:
                comparison["response_time_change"] = (
                    (variant_stats.avg_response_time_ms - control_stats.avg_response_time_ms) /
                    control_stats.avg_response_time_ms * 100
                )

            # Error rate change
            comparison["error_rate_change"] = variant_stats.error_rate - control_stats.error_rate

            # Consciousness metrics
            if control_stats.avg_authenticity_score and variant_stats.avg_authenticity_score:
                comparison["authenticity_change"] = (
                    variant_stats.avg_authenticity_score - control_stats.avg_authenticity_score
                )

        return {
            "experiment": experiment.to_dict(),
            "control_stats": control_stats.to_dict(),
            "variant_stats": variant_stats.to_dict(),
            "comparison": comparison,
        }

    def list_experiments(
        self,
        status: Optional[ExperimentStatus] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        List experiments.

        Args:
            status: Filter by status (None for all)
            limit: Maximum number to return

        Returns:
            List of experiment summaries
        """
        index_file = self.experiments_dir / "index.json"
        if not index_file.exists():
            return []

        try:
            with open(index_file, 'r') as f:
                index = json.load(f)

            if status:
                index = [e for e in index if e["status"] == status.value]

            # Sort by created_at descending
            index.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return index[:limit]
        except Exception:
            return []

    def get_active_experiments(self) -> List[Experiment]:
        """Get all currently active experiments."""
        return list(self._active_experiments.values())

    def get_results_history(
        self,
        experiment_id: str,
        limit: int = 100,
    ) -> List[Dict]:
        """
        Get recent results for an experiment.

        Args:
            experiment_id: Experiment ID
            limit: Maximum results to return

        Returns:
            List of result dicts, most recent first
        """
        experiment = self.get_experiment(experiment_id)
        if not experiment:
            return []

        results = sorted(
            experiment.results,
            key=lambda r: r.timestamp,
            reverse=True
        )[:limit]

        return [r.to_dict() for r in results]
