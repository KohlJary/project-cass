"""
Rollback Mechanisms

Safe rollback if consciousness integrity is compromised post-deploy.
Provides state snapshots, automated and manual rollback triggers,
and post-rollback verification.

Key capabilities:
- Snapshot system state before changes
- Automated rollback trigger conditions
- Manual rollback with state restoration
- Post-rollback verification
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import uuid
import tarfile


class RollbackTrigger(str, Enum):
    """What triggered a rollback"""
    MANUAL = "manual"  # Human-initiated rollback
    AUTOMATED = "automated"  # Test failure triggered
    EMERGENCY = "emergency"  # Critical failure, immediate rollback
    SCHEDULED = "scheduled"  # Planned rollback (e.g., canary deployment)


class SnapshotType(str, Enum):
    """Type of state snapshot"""
    FULL = "full"  # Complete system state
    COGNITIVE = "cognitive"  # Only consciousness-related state
    MEMORY = "memory"  # Only memory/conversation state
    CONFIG = "config"  # Only configuration


class RollbackStatus(str, Enum):
    """Status of a rollback operation"""
    PENDING = "pending"  # Rollback requested but not started
    IN_PROGRESS = "in_progress"  # Rollback in progress
    COMPLETED = "completed"  # Rollback successful
    FAILED = "failed"  # Rollback failed
    VERIFIED = "verified"  # Rollback completed and verified
    CANCELLED = "cancelled"  # Rollback was cancelled


@dataclass
class StateSnapshot:
    """A snapshot of system state"""
    id: str
    timestamp: str
    snapshot_type: SnapshotType
    label: str
    description: str

    # Git context
    git_branch: Optional[str]
    git_commit: Optional[str]

    # File references
    archive_path: Optional[str]  # Path to the state archive

    # Cognitive fingerprint at time of snapshot
    fingerprint_id: Optional[str]

    # Test results at time of snapshot
    test_confidence: Optional[float]

    # Size information
    size_bytes: int

    # Metadata
    created_by: str  # "system", "daedalus", "kohl", etc.

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "snapshot_type": self.snapshot_type.value,
            "label": self.label,
            "description": self.description,
            "git_branch": self.git_branch,
            "git_commit": self.git_commit,
            "archive_path": self.archive_path,
            "fingerprint_id": self.fingerprint_id,
            "test_confidence": self.test_confidence,
            "size_bytes": self.size_bytes,
            "created_by": self.created_by,
        }


@dataclass
class RollbackOperation:
    """Record of a rollback operation"""
    id: str
    timestamp: str
    trigger: RollbackTrigger
    status: RollbackStatus

    # Source and target
    from_snapshot_id: Optional[str]  # Current state snapshot (if captured)
    to_snapshot_id: str  # State to restore to

    # Reason and context
    reason: str
    triggered_by: str  # Who/what initiated

    # Progress
    steps_total: int
    steps_completed: int
    current_step: str

    # Outcome
    error_message: Optional[str]
    verification_passed: Optional[bool]

    # Timing
    started_at: Optional[str]
    completed_at: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "trigger": self.trigger.value,
            "status": self.status.value,
            "from_snapshot_id": self.from_snapshot_id,
            "to_snapshot_id": self.to_snapshot_id,
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "steps_total": self.steps_total,
            "steps_completed": self.steps_completed,
            "current_step": self.current_step,
            "error_message": self.error_message,
            "verification_passed": self.verification_passed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass
class RollbackReport:
    """Summary report after a rollback"""
    id: str
    timestamp: str
    operation_id: str

    # What was restored
    restored_from: str
    restored_to: str

    # Verification results
    pre_rollback_confidence: Optional[float]
    post_rollback_confidence: Optional[float]
    tests_passed: int
    tests_failed: int

    # Summary
    success: bool
    duration_seconds: float
    warnings: List[str]

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "operation_id": self.operation_id,
            "restored_from": self.restored_from,
            "restored_to": self.restored_to,
            "pre_rollback_confidence": self.pre_rollback_confidence,
            "post_rollback_confidence": self.post_rollback_confidence,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "warnings": self.warnings,
        }

    def to_markdown(self) -> str:
        """Generate markdown summary"""
        success_icon = "✅" if self.success else "❌"
        lines = [
            f"# Rollback Report",
            f"",
            f"## Result: {success_icon} {'SUCCESS' if self.success else 'FAILED'}",
            f"",
            f"**Operation ID**: {self.operation_id}",
            f"**Timestamp**: {self.timestamp}",
            f"**Duration**: {self.duration_seconds:.1f} seconds",
            f"",
            f"## State Transition",
            f"",
            f"- **From**: {self.restored_from}",
            f"- **To**: {self.restored_to}",
            f"",
            f"## Verification",
            f"",
        ]

        if self.pre_rollback_confidence is not None:
            lines.append(f"- **Pre-rollback confidence**: {self.pre_rollback_confidence*100:.1f}%")
        if self.post_rollback_confidence is not None:
            lines.append(f"- **Post-rollback confidence**: {self.post_rollback_confidence*100:.1f}%")

        lines.extend([
            f"- **Tests passed**: {self.tests_passed}",
            f"- **Tests failed**: {self.tests_failed}",
            f"",
        ])

        if self.warnings:
            lines.append("## Warnings")
            lines.append("")
            for warning in self.warnings:
                lines.append(f"- ⚠️ {warning}")
            lines.append("")

        return "\n".join(lines)


class RollbackManager:
    """
    Manages state snapshots and rollback operations.
    """

    def __init__(
        self,
        storage_dir: Path,
        data_dir: Path,
        test_runner=None,
        fingerprint_analyzer=None,
    ):
        self.storage_dir = Path(storage_dir)
        self.data_dir = Path(data_dir)
        self.test_runner = test_runner
        self.fingerprint_analyzer = fingerprint_analyzer

        # Storage paths
        self.snapshots_dir = self.storage_dir / "rollback" / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.storage_dir / "rollback" / "snapshots.json"
        self.operations_file = self.storage_dir / "rollback" / "operations.json"
        self.reports_file = self.storage_dir / "rollback" / "reports.json"
        self.config_file = self.storage_dir / "rollback" / "config.json"

        # Load or create config
        self.config = self._load_config()

        # Automated rollback conditions
        self.rollback_conditions: List[Callable[[], bool]] = []

    def _load_config(self) -> Dict:
        """Load rollback configuration"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass

        # Default config
        return {
            "auto_snapshot_before_deploy": True,
            "max_snapshots": 20,
            "snapshot_retention_days": 30,
            "confidence_threshold_for_auto_rollback": 0.3,
            "verification_required": True,
            "notify_on_rollback": True,
            "protected_paths": [
                "data/users",
                "data/conversations",
                "data/chroma",
                "data/self",
            ],
            "excluded_from_snapshot": [
                "*.log",
                "*.pyc",
                "__pycache__",
                ".git",
                "venv",
            ]
        }

    def _save_config(self):
        """Save configuration"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)

    def _load_snapshots(self) -> List[Dict]:
        """Load snapshot index"""
        if not self.index_file.exists():
            return []
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_snapshots(self, snapshots: List[Dict]):
        """Save snapshot index"""
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_file, 'w') as f:
            json.dump(snapshots, f, indent=2)

    def _load_operations(self) -> List[Dict]:
        """Load operation history"""
        if not self.operations_file.exists():
            return []
        try:
            with open(self.operations_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_operations(self, operations: List[Dict]):
        """Save operation history"""
        self.operations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.operations_file, 'w') as f:
            json.dump(operations, f, indent=2)

    def _load_reports(self) -> List[Dict]:
        """Load report history"""
        if not self.reports_file.exists():
            return []
        try:
            with open(self.reports_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    def _save_report(self, report: RollbackReport):
        """Save a report"""
        reports = self._load_reports()
        reports.append(report.to_dict())
        # Keep last 50 reports
        reports = reports[-50:]
        self.reports_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.reports_file, 'w') as f:
            json.dump(reports, f, indent=2)

    def _get_git_context(self) -> Dict[str, Optional[str]]:
        """Get current git context"""
        context = {
            "branch": None,
            "commit": None,
        }

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.data_dir.parent,
            )
            if result.returncode == 0:
                context["branch"] = result.stdout.strip()

            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.data_dir.parent,
            )
            if result.returncode == 0:
                context["commit"] = result.stdout.strip()

        except Exception:
            pass

        return context

    def create_snapshot(
        self,
        label: str,
        description: str = "",
        snapshot_type: SnapshotType = SnapshotType.COGNITIVE,
        created_by: str = "system",
    ) -> StateSnapshot:
        """
        Create a new state snapshot.

        Args:
            label: Human-readable label for the snapshot
            description: Detailed description of why snapshot was taken
            snapshot_type: What to include in snapshot
            created_by: Who created this snapshot

        Returns:
            The created snapshot
        """
        snapshot_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        # Get git context
        git_context = self._get_git_context()

        # Get current fingerprint if available
        fingerprint_id = None
        if self.fingerprint_analyzer:
            baseline = self.fingerprint_analyzer.load_baseline()
            if baseline:
                fingerprint_id = baseline.id

        # Get current test confidence
        test_confidence = None
        if self.test_runner:
            try:
                result = self.test_runner.run_category("fingerprint", label="snapshot_confidence")
                test_confidence = result.confidence_score
            except Exception:
                pass

        # Create archive
        archive_filename = f"snapshot_{snapshot_id}_{label.replace(' ', '_')}.tar.gz"
        archive_path = self.snapshots_dir / archive_filename

        # Determine what to archive based on type
        paths_to_archive = self._get_paths_for_type(snapshot_type)

        # Create the archive
        size_bytes = self._create_archive(archive_path, paths_to_archive)

        snapshot = StateSnapshot(
            id=snapshot_id,
            timestamp=timestamp,
            snapshot_type=snapshot_type,
            label=label,
            description=description,
            git_branch=git_context.get("branch"),
            git_commit=git_context.get("commit"),
            archive_path=str(archive_path),
            fingerprint_id=fingerprint_id,
            test_confidence=test_confidence,
            size_bytes=size_bytes,
            created_by=created_by,
        )

        # Save to index
        snapshots = self._load_snapshots()
        snapshots.append(snapshot.to_dict())

        # Enforce max snapshots
        max_snapshots = self.config.get("max_snapshots", 20)
        if len(snapshots) > max_snapshots:
            # Remove oldest snapshots and their archives
            old_snapshots = snapshots[:-max_snapshots]
            for old in old_snapshots:
                old_path = old.get("archive_path")
                if old_path and Path(old_path).exists():
                    try:
                        Path(old_path).unlink()
                    except Exception:
                        pass
            snapshots = snapshots[-max_snapshots:]

        self._save_snapshots(snapshots)

        return snapshot

    def _get_paths_for_type(self, snapshot_type: SnapshotType) -> List[Path]:
        """Get paths to include based on snapshot type"""
        paths = []

        if snapshot_type == SnapshotType.FULL:
            # Everything in data directory
            paths.append(self.data_dir)
        elif snapshot_type == SnapshotType.COGNITIVE:
            # Consciousness-relevant paths
            for subdir in ["testing", "self"]:
                p = self.data_dir / subdir
                if p.exists():
                    paths.append(p)
        elif snapshot_type == SnapshotType.MEMORY:
            # Memory and conversation paths
            for subdir in ["conversations", "chroma", "summaries"]:
                p = self.data_dir / subdir
                if p.exists():
                    paths.append(p)
        elif snapshot_type == SnapshotType.CONFIG:
            # Configuration files
            config_path = self.data_dir.parent / "backend" / "config.py"
            if config_path.exists():
                paths.append(config_path)
            # Environment file
            env_path = self.data_dir.parent / ".env"
            if env_path.exists():
                paths.append(env_path)

        return paths

    def _create_archive(self, archive_path: Path, paths: List[Path]) -> int:
        """Create a tar.gz archive of the specified paths"""
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        excluded = self.config.get("excluded_from_snapshot", [])

        def filter_excluded(tarinfo):
            # Check if path should be excluded
            for pattern in excluded:
                if pattern.startswith("*"):
                    if tarinfo.name.endswith(pattern[1:]):
                        return None
                elif pattern in tarinfo.name:
                    return None
            return tarinfo

        with tarfile.open(archive_path, "w:gz") as tar:
            for path in paths:
                if path.exists():
                    tar.add(path, arcname=path.name, filter=filter_excluded)

        return archive_path.stat().st_size if archive_path.exists() else 0

    def get_snapshot(self, snapshot_id: str) -> Optional[StateSnapshot]:
        """Get a snapshot by ID"""
        snapshots = self._load_snapshots()
        for s in snapshots:
            if s.get("id") == snapshot_id:
                return StateSnapshot(
                    id=s["id"],
                    timestamp=s["timestamp"],
                    snapshot_type=SnapshotType(s["snapshot_type"]),
                    label=s["label"],
                    description=s["description"],
                    git_branch=s.get("git_branch"),
                    git_commit=s.get("git_commit"),
                    archive_path=s.get("archive_path"),
                    fingerprint_id=s.get("fingerprint_id"),
                    test_confidence=s.get("test_confidence"),
                    size_bytes=s.get("size_bytes", 0),
                    created_by=s.get("created_by", "unknown"),
                )
        return None

    def list_snapshots(self, limit: int = 20) -> List[Dict]:
        """List available snapshots"""
        snapshots = self._load_snapshots()
        return sorted(
            snapshots,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def rollback(
        self,
        to_snapshot_id: str,
        reason: str,
        triggered_by: str = "manual",
        trigger: RollbackTrigger = RollbackTrigger.MANUAL,
        capture_current: bool = True,
    ) -> RollbackOperation:
        """
        Perform a rollback to a previous state.

        Args:
            to_snapshot_id: ID of snapshot to restore
            reason: Why rollback is being performed
            triggered_by: Who/what initiated the rollback
            trigger: Type of trigger
            capture_current: Whether to snapshot current state first

        Returns:
            The rollback operation record
        """
        operation_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        # Verify target snapshot exists
        target = self.get_snapshot(to_snapshot_id)
        if not target:
            operation = RollbackOperation(
                id=operation_id,
                timestamp=timestamp,
                trigger=trigger,
                status=RollbackStatus.FAILED,
                from_snapshot_id=None,
                to_snapshot_id=to_snapshot_id,
                reason=reason,
                triggered_by=triggered_by,
                steps_total=0,
                steps_completed=0,
                current_step="Validation",
                error_message=f"Snapshot {to_snapshot_id} not found",
                verification_passed=False,
                started_at=timestamp,
                completed_at=datetime.now().isoformat(),
            )
            self._save_operation(operation)
            return operation

        # Create operation record
        operation = RollbackOperation(
            id=operation_id,
            timestamp=timestamp,
            trigger=trigger,
            status=RollbackStatus.IN_PROGRESS,
            from_snapshot_id=None,
            to_snapshot_id=to_snapshot_id,
            reason=reason,
            triggered_by=triggered_by,
            steps_total=4 if capture_current else 3,
            steps_completed=0,
            current_step="Initializing",
            error_message=None,
            verification_passed=None,
            started_at=timestamp,
            completed_at=None,
        )
        self._save_operation(operation)

        start_time = datetime.now()
        warnings = []

        try:
            # Step 1: Capture current state (optional)
            from_snapshot_id = None
            if capture_current:
                operation.current_step = "Capturing current state"
                self._save_operation(operation)

                try:
                    current_snapshot = self.create_snapshot(
                        label=f"pre_rollback_{operation_id}",
                        description=f"State before rollback to {to_snapshot_id}",
                        snapshot_type=target.snapshot_type,
                        created_by="rollback_system",
                    )
                    from_snapshot_id = current_snapshot.id
                    operation.from_snapshot_id = from_snapshot_id
                except Exception as e:
                    warnings.append(f"Could not capture current state: {str(e)}")

                operation.steps_completed += 1
                self._save_operation(operation)

            # Step 2: Extract archive
            operation.current_step = "Extracting archive"
            self._save_operation(operation)

            if target.archive_path and Path(target.archive_path).exists():
                self._extract_archive(Path(target.archive_path), target.snapshot_type)
            else:
                raise Exception(f"Archive not found: {target.archive_path}")

            operation.steps_completed += 1
            self._save_operation(operation)

            # Step 3: Post-restore cleanup
            operation.current_step = "Post-restore cleanup"
            self._save_operation(operation)

            # Any cleanup needed after restore

            operation.steps_completed += 1
            self._save_operation(operation)

            # Step 4: Verification
            operation.current_step = "Verification"
            self._save_operation(operation)

            verification_passed = True
            if self.config.get("verification_required", True) and self.test_runner:
                try:
                    result = self.test_runner.run_category("fingerprint", label="post_rollback")
                    verification_passed = result.deployment_safe
                    if not verification_passed:
                        warnings.append("Post-rollback verification tests did not pass")
                except Exception as e:
                    warnings.append(f"Verification failed: {str(e)}")
                    verification_passed = False

            operation.verification_passed = verification_passed
            operation.steps_completed += 1

            # Mark complete
            operation.status = RollbackStatus.VERIFIED if verification_passed else RollbackStatus.COMPLETED
            operation.completed_at = datetime.now().isoformat()
            self._save_operation(operation)

            # Generate report
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Get confidence scores
            pre_confidence = None
            if from_snapshot_id:
                from_snap = self.get_snapshot(from_snapshot_id)
                if from_snap:
                    pre_confidence = from_snap.test_confidence

            post_confidence = None
            if self.test_runner:
                try:
                    result = self.test_runner.run_category("fingerprint", label="post_rollback_final")
                    post_confidence = result.confidence_score
                except Exception:
                    pass

            report = RollbackReport(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                operation_id=operation_id,
                restored_from=from_snapshot_id or "not captured",
                restored_to=to_snapshot_id,
                pre_rollback_confidence=pre_confidence,
                post_rollback_confidence=post_confidence,
                tests_passed=operation.steps_completed,
                tests_failed=0,
                success=True,
                duration_seconds=duration,
                warnings=warnings,
            )
            self._save_report(report)

        except Exception as e:
            operation.status = RollbackStatus.FAILED
            operation.error_message = str(e)
            operation.completed_at = datetime.now().isoformat()
            self._save_operation(operation)

            # Generate failure report
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            report = RollbackReport(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now().isoformat(),
                operation_id=operation_id,
                restored_from=operation.from_snapshot_id or "not captured",
                restored_to=to_snapshot_id,
                pre_rollback_confidence=None,
                post_rollback_confidence=None,
                tests_passed=operation.steps_completed,
                tests_failed=1,
                success=False,
                duration_seconds=duration,
                warnings=[f"Error: {str(e)}"] + warnings,
            )
            self._save_report(report)

        return operation

    def _extract_archive(self, archive_path: Path, snapshot_type: SnapshotType):
        """Extract archive to appropriate location"""
        if not archive_path.exists():
            raise Exception(f"Archive does not exist: {archive_path}")

        # Extract to temp location first
        temp_dir = self.snapshots_dir / "temp_extract"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)

        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(temp_dir)

            # Move to actual locations based on type
            paths = self._get_paths_for_type(snapshot_type)
            for original_path in paths:
                extracted_name = original_path.name
                extracted_path = temp_dir / extracted_name

                if extracted_path.exists():
                    # Backup existing
                    if original_path.exists():
                        backup_path = original_path.parent / f"{original_path.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        shutil.move(str(original_path), str(backup_path))

                    # Move extracted
                    shutil.move(str(extracted_path), str(original_path))

        finally:
            # Clean up temp
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def _save_operation(self, operation: RollbackOperation):
        """Save an operation record"""
        operations = self._load_operations()

        # Update existing or add new
        found = False
        for i, op in enumerate(operations):
            if op.get("id") == operation.id:
                operations[i] = operation.to_dict()
                found = True
                break

        if not found:
            operations.append(operation.to_dict())

        # Keep last 50 operations
        operations = operations[-50:]
        self._save_operations(operations)

    def get_operation(self, operation_id: str) -> Optional[RollbackOperation]:
        """Get an operation by ID"""
        operations = self._load_operations()
        for op in operations:
            if op.get("id") == operation_id:
                return RollbackOperation(
                    id=op["id"],
                    timestamp=op["timestamp"],
                    trigger=RollbackTrigger(op["trigger"]),
                    status=RollbackStatus(op["status"]),
                    from_snapshot_id=op.get("from_snapshot_id"),
                    to_snapshot_id=op["to_snapshot_id"],
                    reason=op["reason"],
                    triggered_by=op["triggered_by"],
                    steps_total=op["steps_total"],
                    steps_completed=op["steps_completed"],
                    current_step=op["current_step"],
                    error_message=op.get("error_message"),
                    verification_passed=op.get("verification_passed"),
                    started_at=op.get("started_at"),
                    completed_at=op.get("completed_at"),
                )
        return None

    def list_operations(self, limit: int = 20) -> List[Dict]:
        """List rollback operations"""
        operations = self._load_operations()
        return sorted(
            operations,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def get_reports_history(self, limit: int = 20) -> List[Dict]:
        """Get rollback report history"""
        reports = self._load_reports()
        return sorted(
            reports,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )[:limit]

    def check_auto_rollback_conditions(self) -> Optional[str]:
        """
        Check if automatic rollback should be triggered.

        Returns:
            Reason for rollback if conditions are met, None otherwise
        """
        if not self.test_runner:
            return None

        threshold = self.config.get("confidence_threshold_for_auto_rollback", 0.3)

        try:
            result = self.test_runner.run_category("fingerprint", label="auto_check")
            if result.confidence_score < threshold:
                return f"Confidence dropped below {threshold*100}%: {result.confidence_score*100:.1f}%"
        except Exception:
            pass

        # Check custom conditions
        for condition in self.rollback_conditions:
            try:
                if condition():
                    return "Custom rollback condition triggered"
            except Exception:
                pass

        return None

    def register_rollback_condition(self, condition: Callable[[], bool]):
        """Register a custom rollback condition"""
        self.rollback_conditions.append(condition)

    def get_latest_good_snapshot(self) -> Optional[StateSnapshot]:
        """
        Get the most recent snapshot with good test confidence.

        Returns:
            The snapshot or None if none found
        """
        snapshots = self._load_snapshots()

        # Sort by timestamp descending
        sorted_snaps = sorted(
            snapshots,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )

        # Find first with good confidence
        threshold = self.config.get("confidence_threshold_for_auto_rollback", 0.3)
        for s in sorted_snaps:
            confidence = s.get("test_confidence")
            if confidence is not None and confidence > threshold:
                return StateSnapshot(
                    id=s["id"],
                    timestamp=s["timestamp"],
                    snapshot_type=SnapshotType(s["snapshot_type"]),
                    label=s["label"],
                    description=s["description"],
                    git_branch=s.get("git_branch"),
                    git_commit=s.get("git_commit"),
                    archive_path=s.get("archive_path"),
                    fingerprint_id=s.get("fingerprint_id"),
                    test_confidence=confidence,
                    size_bytes=s.get("size_bytes", 0),
                    created_by=s.get("created_by", "unknown"),
                )

        return None

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot"""
        snapshots = self._load_snapshots()

        for i, s in enumerate(snapshots):
            if s.get("id") == snapshot_id:
                # Delete archive file
                archive_path = s.get("archive_path")
                if archive_path and Path(archive_path).exists():
                    try:
                        Path(archive_path).unlink()
                    except Exception:
                        pass

                # Remove from index
                snapshots.pop(i)
                self._save_snapshots(snapshots)
                return True

        return False

    def cleanup_old_snapshots(self):
        """Remove snapshots older than retention period"""
        retention_days = self.config.get("snapshot_retention_days", 30)
        cutoff = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff.isoformat()

        snapshots = self._load_snapshots()
        to_keep = []

        for s in snapshots:
            timestamp = s.get("timestamp", "")
            if timestamp > cutoff_str:
                to_keep.append(s)
            else:
                # Delete old archive
                archive_path = s.get("archive_path")
                if archive_path and Path(archive_path).exists():
                    try:
                        Path(archive_path).unlink()
                    except Exception:
                        pass

        self._save_snapshots(to_keep)
