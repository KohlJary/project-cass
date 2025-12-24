"""
Work Package system for Mind Palace.

Manages the packaging, locking, and dispatch of work units for parallel execution
by Icarus workers. Each work package bundles:
- Scope (which rooms/functions are affected)
- Routes (pre-computed paths from pathfinding)
- Constraints (dependencies, required tests)
- Locks (room-level reservations to prevent collisions)

Directory structure:
.mind-palace/work/
├── packages/
│   ├── {package_id}.yaml    # Work package definition
│   └── ...
├── locks/
│   ├── {room_slug}.lock     # Room reservation files
│   └── ...
├── diffs/
│   ├── {package_id}.diff    # Proposed changes (Ariadne)
│   └── ...
└── results/
    ├── {package_id}.yaml    # Execution results
    └── ...

Usage:
    from mind_palace.work_packages import WorkPackageManager, WorkPackage

    manager = WorkPackageManager(project_root)

    # Create a work package
    package = manager.create(
        title="Add caching to semantic_search",
        rooms=["backend-memory-semantic-search"],
        description="Add LRU cache to frequently queried embeddings"
    )

    # Check out (locks the rooms)
    if manager.checkout(package.id, worker_id="icarus-123"):
        # Worker does the work...
        manager.submit_diff(package.id, diff_content)
        manager.complete(package.id)
    else:
        # Rooms are locked by another worker
        pass
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import yaml
import uuid
import os
import fcntl


class PackageStatus(str, Enum):
    PENDING = "pending"      # Created, not yet checked out
    CHECKED_OUT = "checked_out"  # Locked by a worker
    COMPLETED = "completed"  # Work done, diff submitted
    MERGED = "merged"        # Ariadne merged the changes
    ABANDONED = "abandoned"  # Work cancelled


@dataclass
class RoomLock:
    """A lock on a palace room."""
    room_slug: str
    package_id: str
    worker_id: str
    locked_at: str
    expires_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "room_slug": self.room_slug,
            "package_id": self.package_id,
            "worker_id": self.worker_id,
            "locked_at": self.locked_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "RoomLock":
        return cls(**data)


@dataclass
class WorkPackage:
    """A bundle of work for an Icarus worker."""
    id: str
    title: str
    description: str
    status: PackageStatus

    # Scope
    rooms: List[str]  # Room slugs this package touches
    files: List[str]  # Files that will be modified
    impact_radius: int  # Number of transitive callers

    # Context
    routes: List[str] = field(default_factory=list)  # Pre-computed paths
    constraints: List[str] = field(default_factory=list)  # Dependencies, requirements
    test_files: List[str] = field(default_factory=list)  # Tests to run

    # Execution
    worker_id: Optional[str] = None
    created_at: Optional[str] = None
    checked_out_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Results
    diff_file: Optional[str] = None
    result_summary: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "rooms": self.rooms,
            "files": self.files,
            "impact_radius": self.impact_radius,
            "routes": self.routes,
            "constraints": self.constraints,
            "test_files": self.test_files,
            "worker_id": self.worker_id,
            "created_at": self.created_at,
            "checked_out_at": self.checked_out_at,
            "completed_at": self.completed_at,
            "diff_file": self.diff_file,
            "result_summary": self.result_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WorkPackage":
        data = data.copy()
        data["status"] = PackageStatus(data["status"])
        return cls(**data)


class WorkPackageManager:
    """
    Manages work packages and room locks.

    Thread-safe via file-based locking.
    """

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.work_dir = self.project_root / ".mind-palace" / "work"

        # Ensure directories exist
        self.packages_dir = self.work_dir / "packages"
        self.locks_dir = self.work_dir / "locks"
        self.diffs_dir = self.work_dir / "diffs"
        self.results_dir = self.work_dir / "results"

        for dir in [self.packages_dir, self.locks_dir, self.diffs_dir, self.results_dir]:
            dir.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        title: str,
        rooms: List[str],
        description: str = "",
        files: Optional[List[str]] = None,
        impact_radius: int = 0,
        routes: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        test_files: Optional[List[str]] = None,
    ) -> WorkPackage:
        """
        Create a new work package.

        Args:
            title: Brief title for the work
            rooms: List of room slugs this work touches
            description: Detailed description
            files: Files that will be modified
            impact_radius: Number of transitive callers
            routes: Pre-computed paths from pathfinding
            constraints: Dependencies or requirements
            test_files: Tests that should pass

        Returns:
            New WorkPackage instance
        """
        package = WorkPackage(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            status=PackageStatus.PENDING,
            rooms=rooms,
            files=files or [],
            impact_radius=impact_radius,
            routes=routes or [],
            constraints=constraints or [],
            test_files=test_files or [],
            created_at=datetime.utcnow().isoformat(),
        )

        self._save_package(package)
        return package

    def get(self, package_id: str) -> Optional[WorkPackage]:
        """Get a work package by ID."""
        path = self.packages_dir / f"{package_id}.yaml"
        if not path.exists():
            return None

        with open(path) as f:
            return WorkPackage.from_dict(yaml.safe_load(f))

    def list_packages(
        self,
        status: Optional[PackageStatus] = None
    ) -> List[WorkPackage]:
        """List all packages, optionally filtered by status."""
        packages = []
        for path in self.packages_dir.glob("*.yaml"):
            with open(path) as f:
                package = WorkPackage.from_dict(yaml.safe_load(f))
                if status is None or package.status == status:
                    packages.append(package)
        return packages

    def checkout(
        self,
        package_id: str,
        worker_id: str,
        timeout_hours: float = 1.0
    ) -> bool:
        """
        Check out a work package, locking its rooms.

        Args:
            package_id: ID of the package to check out
            worker_id: ID of the worker claiming this package
            timeout_hours: Lock timeout in hours

        Returns:
            True if checkout succeeded, False if rooms are locked
        """
        package = self.get(package_id)
        if not package:
            return False

        if package.status != PackageStatus.PENDING:
            return False

        # Try to acquire locks on all rooms
        locks_acquired = []
        try:
            for room_slug in package.rooms:
                lock = self._try_lock(room_slug, package_id, worker_id)
                if lock:
                    locks_acquired.append(lock)
                else:
                    # Room is locked, release what we got
                    for acquired_lock in locks_acquired:
                        self._release_lock(acquired_lock.room_slug)
                    return False

            # All locks acquired, update package
            package.status = PackageStatus.CHECKED_OUT
            package.worker_id = worker_id
            package.checked_out_at = datetime.utcnow().isoformat()
            self._save_package(package)
            return True

        except Exception:
            # Release any locks on error
            for acquired_lock in locks_acquired:
                self._release_lock(acquired_lock.room_slug)
            raise

    def release(self, package_id: str) -> bool:
        """
        Release a checked-out package back to pending.

        Used when a worker abandons work.
        """
        package = self.get(package_id)
        if not package:
            return False

        if package.status != PackageStatus.CHECKED_OUT:
            return False

        # Release all locks
        for room_slug in package.rooms:
            self._release_lock(room_slug)

        package.status = PackageStatus.PENDING
        package.worker_id = None
        package.checked_out_at = None
        self._save_package(package)
        return True

    def submit_diff(self, package_id: str, diff_content: str) -> bool:
        """
        Submit a diff for a checked-out package.

        The diff is stored for Ariadne to review and merge.
        """
        package = self.get(package_id)
        if not package:
            return False

        if package.status != PackageStatus.CHECKED_OUT:
            return False

        # Save diff file
        diff_path = self.diffs_dir / f"{package_id}.diff"
        with open(diff_path, "w") as f:
            f.write(diff_content)

        package.diff_file = str(diff_path)
        self._save_package(package)
        return True

    def complete(
        self,
        package_id: str,
        result_summary: Optional[str] = None
    ) -> bool:
        """
        Mark a package as completed.

        Releases locks but keeps the diff for Ariadne.
        """
        package = self.get(package_id)
        if not package:
            return False

        if package.status != PackageStatus.CHECKED_OUT:
            return False

        # Release all locks
        for room_slug in package.rooms:
            self._release_lock(room_slug)

        package.status = PackageStatus.COMPLETED
        package.completed_at = datetime.utcnow().isoformat()
        package.result_summary = result_summary
        self._save_package(package)

        # Save result file
        result_path = self.results_dir / f"{package_id}.yaml"
        with open(result_path, "w") as f:
            yaml.dump(package.to_dict(), f, default_flow_style=False)

        return True

    def abandon(self, package_id: str, reason: Optional[str] = None) -> bool:
        """Abandon a package, releasing locks."""
        package = self.get(package_id)
        if not package:
            return False

        # Release all locks
        for room_slug in package.rooms:
            self._release_lock(room_slug)

        package.status = PackageStatus.ABANDONED
        package.result_summary = reason
        self._save_package(package)
        return True

    def mark_merged(self, package_id: str) -> bool:
        """Mark a package as merged by Ariadne."""
        package = self.get(package_id)
        if not package:
            return False

        if package.status != PackageStatus.COMPLETED:
            return False

        package.status = PackageStatus.MERGED
        self._save_package(package)
        return True

    def get_lock(self, room_slug: str) -> Optional[RoomLock]:
        """Get the current lock on a room, if any."""
        lock_path = self.locks_dir / f"{room_slug}.lock"
        if not lock_path.exists():
            return None

        try:
            with open(lock_path) as f:
                return RoomLock.from_dict(json.load(f))
        except Exception:
            return None

    def list_locks(self) -> List[RoomLock]:
        """List all active locks."""
        locks = []
        for path in self.locks_dir.glob("*.lock"):
            try:
                with open(path) as f:
                    locks.append(RoomLock.from_dict(json.load(f)))
            except Exception:
                pass
        return locks

    def get_conflicts(self, rooms: List[str]) -> List[RoomLock]:
        """Check if any of the given rooms are locked."""
        conflicts = []
        for room_slug in rooms:
            lock = self.get_lock(room_slug)
            if lock:
                conflicts.append(lock)
        return conflicts

    def get_diff(self, package_id: str) -> Optional[str]:
        """Get the diff content for a completed package."""
        diff_path = self.diffs_dir / f"{package_id}.diff"
        if not diff_path.exists():
            return None

        with open(diff_path) as f:
            return f.read()

    def _save_package(self, package: WorkPackage):
        """Save a package to disk."""
        path = self.packages_dir / f"{package.id}.yaml"
        with open(path, "w") as f:
            yaml.dump(package.to_dict(), f, default_flow_style=False)

    def _try_lock(
        self,
        room_slug: str,
        package_id: str,
        worker_id: str
    ) -> Optional[RoomLock]:
        """
        Try to acquire a lock on a room.

        Uses file-based locking for thread safety.
        Returns the lock if acquired, None if room is already locked.
        """
        lock_path = self.locks_dir / f"{room_slug}.lock"

        # Use exclusive file locking
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # Lock file exists, check if it's valid
            existing = self.get_lock(room_slug)
            if existing:
                # TODO: Check if lock has expired
                return None
            # Lock file exists but is invalid, try to remove and retry
            try:
                os.remove(lock_path)
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except Exception:
                return None

        try:
            lock = RoomLock(
                room_slug=room_slug,
                package_id=package_id,
                worker_id=worker_id,
                locked_at=datetime.utcnow().isoformat(),
            )

            os.write(fd, json.dumps(lock.to_dict()).encode())
            return lock
        finally:
            os.close(fd)

    def _release_lock(self, room_slug: str) -> bool:
        """Release a lock on a room."""
        lock_path = self.locks_dir / f"{room_slug}.lock"
        try:
            os.remove(lock_path)
            return True
        except FileNotFoundError:
            return False
