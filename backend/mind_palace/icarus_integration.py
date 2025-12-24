"""
Icarus Bus Integration for Mind Palace.

Bridges Mind Palace work packages with the Icarus coordination bus,
providing causal slice context and room-based coordination.

This module enables:
- Converting Mind Palace WorkPackages to Icarus WorkPackages
- Enriching work with causal slice context
- Mapping completed Icarus work back to Mind Palace diffs
- Room lock coordination between systems

Usage:
    from mind_palace.icarus_integration import IcarusDispatcher

    dispatcher = IcarusDispatcher(project_root)

    # Create and dispatch work
    mp_package = dispatcher.create_work(
        title="Add caching to semantic_search",
        rooms=["backend-memory-semantic-search"],
        focal_points=["backend.memory.semantic_search"],
    )

    # Post to Icarus bus
    icarus_work_id = dispatcher.dispatch(mp_package.id)

    # Monitor progress
    status = dispatcher.check_status(mp_package.id)

    # Collect completed work
    dispatcher.collect_completed()
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .work_packages import WorkPackage, WorkPackageManager, PackageStatus
from .causal_slice import CausalSlicer, SliceBundle, extract_slice_for_work_package


@dataclass
class DispatchResult:
    """Result of dispatching work to Icarus."""
    mp_package_id: str
    icarus_work_id: str
    rooms_locked: List[str]
    slice_nodes: int
    affected_files: int


class IcarusDispatcher:
    """
    Dispatcher for Mind Palace work packages to Icarus bus.

    Handles the full lifecycle:
    1. Create Mind Palace work package
    2. Generate causal slice for context
    3. Lock rooms
    4. Dispatch to Icarus bus
    5. Monitor progress
    6. Collect results and update Mind Palace
    """

    def __init__(self, project_root: Path, bus_root: Optional[Path] = None):
        self.project_root = Path(project_root)
        self.mp_manager = WorkPackageManager(project_root)
        self.slicer = CausalSlicer(project_root)

        # Deferred import to avoid circular dependency
        self._bus = None
        self._bus_root = bus_root

    @property
    def bus(self):
        """Lazy load Icarus bus."""
        if self._bus is None:
            # Import from daedalus package
            import sys
            daedalus_src = self.project_root / "daedalus" / "src"
            if str(daedalus_src) not in sys.path:
                sys.path.insert(0, str(daedalus_src))

            from daedalus.bus.icarus_bus import IcarusBus, BUS_ROOT
            self._bus = IcarusBus(self._bus_root or BUS_ROOT)

            if not self._bus.is_initialized():
                self._bus.initialize()

        return self._bus

    def create_work(
        self,
        title: str,
        rooms: List[str],
        description: str = "",
        focal_points: Optional[List[str]] = None,
        target_files: Optional[List[str]] = None,
        backward_depth: int = 3,
        forward_depth: int = 2,
    ) -> Tuple[WorkPackage, SliceBundle]:
        """
        Create a work package with causal slice.

        Args:
            title: Brief title for the work
            rooms: Room slugs this work affects
            description: Detailed description
            focal_points: Function IDs for causal analysis
            target_files: Explicit list of files to be modified (for pattern finding)
            backward_depth: How far to trace callers
            forward_depth: How far to trace callees

        Returns:
            Tuple of (WorkPackage, SliceBundle)
        """
        # Generate causal slice if focal points provided
        slice_bundle = None
        affected_files = []

        if focal_points:
            slice_bundle, _ = extract_slice_for_work_package(
                self.project_root,
                focal_points,
                backward_depth,
                forward_depth,
            )
            affected_files = list(slice_bundle.affected_files)

        # Merge with explicit target files
        if target_files:
            affected_files = list(set(affected_files) | set(target_files))

        # Create Mind Palace work package
        mp_package = self.mp_manager.create(
            title=title,
            rooms=rooms,
            description=description,
            files=affected_files,
            impact_radius=slice_bundle.total_nodes if slice_bundle else 0,
        )

        # Save slice bundle if generated
        if slice_bundle:
            slice_path = self.mp_manager.work_dir / "slices" / f"{mp_package.id}.json"
            slice_path.parent.mkdir(exist_ok=True)
            slice_bundle.save(slice_path)

        return mp_package, slice_bundle

    def dispatch(
        self,
        mp_package_id: str,
        worker_id: str = "interactive",
        priority: int = 5,
    ) -> DispatchResult:
        """
        Dispatch a Mind Palace work package to the Icarus bus.

        Args:
            mp_package_id: Mind Palace work package ID
            worker_id: ID of the worker/coordinator dispatching
            priority: Work priority (1=highest, 10=lowest)

        Returns:
            DispatchResult with dispatch details
        """
        # Get the Mind Palace package
        mp_package = self.mp_manager.get(mp_package_id)
        if not mp_package:
            raise ValueError(f"Work package not found: {mp_package_id}")

        # Check for conflicts
        conflicts = self.mp_manager.get_conflicts(mp_package.rooms)
        if conflicts:
            locked_rooms = [c.room_slug for c in conflicts]
            raise RuntimeError(f"Rooms already locked: {locked_rooms}")

        # Checkout the package (locks rooms)
        if not self.mp_manager.checkout(mp_package_id, worker_id):
            raise RuntimeError(f"Failed to checkout package: {mp_package_id}")

        # Load causal slice if exists
        slice_context = ""
        slice_nodes = 0
        slice_path = self.mp_manager.work_dir / "slices" / f"{mp_package_id}.json"
        if slice_path.exists():
            with open(slice_path) as f:
                slice_data = json.load(f)
                slice_nodes = slice_data.get("total_nodes", 0)

            # Regenerate context string with full source and patterns
            slicer = CausalSlicer(self.project_root)
            focal = slice_data.get("focal_point", "")
            if "," in focal:
                focals = focal.split(",")
                bundle = slicer.extract_multi(focals)
            else:
                bundle = slicer.extract(focal)
            slice_context = bundle.to_context(
                include_source=True,
                include_patterns=True,
                project_root=self.project_root,
                pattern_files=mp_package.files,  # Include target files for pattern finding
            )

        # Create Icarus work package (use same import path as bus property)
        import sys
        daedalus_src = self.project_root / "daedalus" / "src"
        if str(daedalus_src) not in sys.path:
            sys.path.insert(0, str(daedalus_src))
        from daedalus.bus.icarus_bus import WorkPackage as IcarusWorkPackage

        icarus_work = IcarusWorkPackage(
            id=f"mp-{mp_package_id}",
            type="implementation",
            description=mp_package.description or mp_package.title,
            inputs={
                "mp_package_id": mp_package_id,
                "title": mp_package.title,
                "rooms": mp_package.rooms,
                "files": mp_package.files,
                "causal_slice": slice_context,
            },
            outputs={
                "diff_file": str(self.mp_manager.diffs_dir / f"{mp_package_id}.diff"),
                "result_file": str(self.mp_manager.results_dir / f"{mp_package_id}.yaml"),
            },
            constraints=mp_package.constraints,
            priority=priority,
        )

        # Post to bus
        icarus_work_id = self.bus.post_work(icarus_work)

        return DispatchResult(
            mp_package_id=mp_package_id,
            icarus_work_id=icarus_work_id,
            rooms_locked=mp_package.rooms,
            slice_nodes=slice_nodes,
            affected_files=len(mp_package.files),
        )

    def check_status(self, mp_package_id: str) -> Dict:
        """
        Check status of dispatched work.

        Returns combined Mind Palace and Icarus status.
        """
        mp_package = self.mp_manager.get(mp_package_id)
        icarus_work_id = f"mp-{mp_package_id}"

        # Check Icarus bus
        icarus_work = self.bus.get_work(icarus_work_id)
        icarus_result = self.bus.get_result(icarus_work_id)

        # Handle icarus status (may be enum or string depending on source)
        icarus_status = "not_posted"
        if icarus_work:
            icarus_status = icarus_work.status.value if hasattr(icarus_work.status, 'value') else str(icarus_work.status)

        return {
            "mp_package_id": mp_package_id,
            "mp_status": mp_package.status.value if mp_package else "not_found",
            "icarus_work_id": icarus_work_id,
            "icarus_status": icarus_status,
            "icarus_claimed_by": icarus_work.claimed_by if icarus_work else None,
            "has_result": icarus_result is not None,
            "rooms": mp_package.rooms if mp_package else [],
        }

    def collect_completed(self) -> List[str]:
        """
        Collect completed Icarus work and update Mind Palace.

        Returns list of completed package IDs.
        """
        completed = []

        for result in self.bus.collect_results(clear=False):
            work_id = result.get("work_id", "")

            # Check if it's a Mind Palace package
            if not work_id.startswith("mp-"):
                continue

            mp_package_id = work_id[3:]  # Remove "mp-" prefix
            mp_package = self.mp_manager.get(mp_package_id)

            if not mp_package or mp_package.status == PackageStatus.COMPLETED:
                continue

            # Extract diff if present in result
            icarus_result = result.get("result", {})
            diff_content = icarus_result.get("diff", "")

            if diff_content:
                self.mp_manager.submit_diff(mp_package_id, diff_content)

            # Complete the Mind Palace package
            self.mp_manager.complete(
                mp_package_id,
                result_summary=icarus_result.get("summary", "Completed by Icarus"),
            )

            completed.append(mp_package_id)

        return completed

    def release(self, mp_package_id: str) -> bool:
        """
        Release a dispatched package (abandon work).

        Releases Mind Palace locks and removes from Icarus queue if pending.
        """
        # Release Mind Palace locks
        released = self.mp_manager.release(mp_package_id)

        # Try to remove from Icarus queue (only works if not yet claimed)
        icarus_work_id = f"mp-{mp_package_id}"
        work_file = self.bus.dirs["work_queue"] / f"{icarus_work_id}.json"
        if work_file.exists():
            work_file.unlink()

        return released

    def status_summary(self) -> Dict:
        """
        Get summary of all dispatched work.
        """
        mp_packages = self.mp_manager.list_packages()

        summary = {
            "mind_palace": {
                "pending": len([p for p in mp_packages if p.status == PackageStatus.PENDING]),
                "checked_out": len([p for p in mp_packages if p.status == PackageStatus.CHECKED_OUT]),
                "completed": len([p for p in mp_packages if p.status == PackageStatus.COMPLETED]),
                "merged": len([p for p in mp_packages if p.status == PackageStatus.MERGED]),
            },
            "icarus_bus": self.bus.status_summary() if self.bus.is_initialized() else None,
            "active_locks": len(self.mp_manager.list_locks()),
        }

        return summary


def interactive_dispatch(project_root: Path) -> None:
    """
    Interactive walkthrough for dispatching work.

    This is the "no auto-spawn" mode - walks through each step
    with user confirmation.
    """
    dispatcher = IcarusDispatcher(project_root)

    print("=== Mind Palace → Icarus Dispatch ===\n")

    # Step 1: Show current status
    print("1. Current Status:")
    status = dispatcher.status_summary()
    print(f"   Mind Palace packages: {status['mind_palace']}")
    print(f"   Active room locks: {status['active_locks']}")

    if status['icarus_bus']:
        print(f"   Icarus bus: {status['icarus_bus']['work']}")
    print()

    # Step 2: List pending packages
    pending = dispatcher.mp_manager.list_packages(PackageStatus.PENDING)
    if not pending:
        print("2. No pending work packages to dispatch.")
        print("   Create one with: dispatcher.create_work(...)")
        return

    print("2. Pending Work Packages:")
    for i, pkg in enumerate(pending):
        print(f"   [{i}] {pkg.id}: {pkg.title}")
        print(f"       Rooms: {', '.join(pkg.rooms)}")
    print()

    # Step 3: Select package
    try:
        idx = int(input("   Select package index to dispatch (or -1 to cancel): "))
        if idx < 0 or idx >= len(pending):
            print("   Cancelled.")
            return
    except ValueError:
        print("   Invalid input, cancelled.")
        return

    selected = pending[idx]
    print(f"\n3. Selected: {selected.title}")
    print(f"   Rooms: {selected.rooms}")
    print(f"   Files: {selected.files[:5]}..." if len(selected.files) > 5 else f"   Files: {selected.files}")

    # Step 4: Confirm dispatch
    confirm = input("\n4. Dispatch to Icarus bus? [y/N]: ")
    if confirm.lower() != 'y':
        print("   Cancelled.")
        return

    # Step 5: Dispatch
    try:
        result = dispatcher.dispatch(selected.id)
        print(f"\n5. Dispatched Successfully!")
        print(f"   Icarus work ID: {result.icarus_work_id}")
        print(f"   Rooms locked: {result.rooms_locked}")
        print(f"   Slice nodes: {result.slice_nodes}")
        print(f"   Affected files: {result.affected_files}")
    except Exception as e:
        print(f"\n5. Dispatch failed: {e}")
        return

    print("\n=== Work is now on the Icarus bus ===")
    print("   Workers can claim it with: bus.claim_work(instance_id)")
    print("   Monitor with: dispatcher.check_status(package_id)")


if __name__ == "__main__":
    import sys
    project_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    interactive_dispatch(project_root)
