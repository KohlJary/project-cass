#!/usr/bin/env python3
"""
Icarus Coordination Bus

File-based coordination system for Daedalus/Icarus parallelization.
Enables work dispatch, status tracking, and result collection.

Directory structure:
    /tmp/icarus-bus/
        instances/          # Instance registration and status
            icarus-001.json
        work-queue/         # Pending work packages
            work-001.yaml
        claimed/            # Work in progress (moved from queue)
            work-001.yaml
        results/            # Completed work outputs
            work-001.json
        streams/            # Live output streams
            icarus-001.log
        requests/           # Requests needing Daedalus attention
            req-001.json
        responses/          # Daedalus responses to requests
            req-001.json
"""

import json
import os
import time
import uuid
import fcntl
from pathlib import Path
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any


# Base directory for the bus
BUS_ROOT = Path("/tmp/icarus-bus")


class InstanceStatus(str, Enum):
    SPAWNING = "spawning"
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"      # Waiting on something
    COMPLETE = "complete"    # Finished current work
    FAILED = "failed"
    TERMINATED = "terminated"


class WorkStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


class RequestType(str, Enum):
    APPROVAL = "approval"       # Needs permission for something
    INPUT = "input"             # Needs information/decision
    HELP = "help"               # Stuck, needs guidance
    ESCALATE = "escalate"       # Beyond Icarus scope


@dataclass
class IcarusInstance:
    """Represents a registered Icarus worker."""
    id: str
    pid: int
    status: InstanceStatus
    current_work: Optional[str] = None
    spawned_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkPackage:
    """Self-contained unit of work for Icarus."""
    id: str
    type: str                   # implementation, refactor, test, research
    description: str
    inputs: Dict[str, Any]      # files, context, parameters
    outputs: Dict[str, Any]     # expected deliverables, report location
    constraints: List[str] = field(default_factory=list)
    priority: int = 5           # 1=highest, 10=lowest
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "daedalus"
    status: WorkStatus = WorkStatus.PENDING
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None


@dataclass
class Request:
    """Request from Icarus needing Daedalus attention."""
    id: str
    instance_id: str
    work_id: Optional[str]
    type: RequestType
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False


@dataclass
class Response:
    """Daedalus response to an Icarus request."""
    request_id: str
    decision: str               # approved, denied, answer, guidance
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IcarusBus:
    """
    Coordination bus for Icarus instances.

    Usage (Daedalus side):
        bus = IcarusBus()
        bus.initialize()

        # Post work
        work_id = bus.post_work(WorkPackage(...))

        # Monitor
        instances = bus.list_instances()
        pending = bus.list_pending_work()
        requests = bus.list_pending_requests()

        # Respond to requests
        bus.respond_to_request(request_id, Response(...))

        # Collect results
        results = bus.collect_results()

    Usage (Icarus side):
        bus = IcarusBus()
        instance_id = bus.register_instance(pid=os.getpid())

        # Claim work
        work = bus.claim_work(instance_id)

        # Update status
        bus.update_status(instance_id, InstanceStatus.WORKING, work_id=work.id)
        bus.heartbeat(instance_id)
        bus.stream_output(instance_id, "Working on X...")

        # Request help if needed
        bus.request_help(instance_id, work.id, RequestType.INPUT, "Need clarification on...")
        response = bus.wait_for_response(request_id)

        # Complete
        bus.submit_result(work.id, instance_id, {"success": True, "output": ...})
        bus.update_status(instance_id, InstanceStatus.IDLE)
    """

    def __init__(self, root: Path = BUS_ROOT):
        self.root = root
        self.dirs = {
            "instances": root / "instances",
            "work_queue": root / "work-queue",
            "claimed": root / "claimed",
            "results": root / "results",
            "streams": root / "streams",
            "requests": root / "requests",
            "responses": root / "responses",
        }

    def initialize(self) -> None:
        """Create bus directory structure."""
        for dir_path in self.dirs.values():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Create a manifest file
        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "daedalus_pid": os.getpid(),
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2))

    def is_initialized(self) -> bool:
        """Check if bus is initialized."""
        return (self.root / "manifest.json").exists()

    # ========== Instance Management ==========

    def register_instance(self, pid: int, metadata: Dict = None) -> str:
        """Register a new Icarus instance. Returns instance ID."""
        instance_id = f"icarus-{uuid.uuid4().hex[:8]}"
        instance = IcarusInstance(
            id=instance_id,
            pid=pid,
            status=InstanceStatus.IDLE,
            metadata=metadata or {},
        )
        self._write_instance(instance)

        # Create stream file
        (self.dirs["streams"] / f"{instance_id}.log").touch()

        return instance_id

    def unregister_instance(self, instance_id: str) -> None:
        """Remove an instance registration."""
        instance_file = self.dirs["instances"] / f"{instance_id}.json"
        if instance_file.exists():
            instance_file.unlink()

        stream_file = self.dirs["streams"] / f"{instance_id}.log"
        if stream_file.exists():
            stream_file.unlink()

    def update_status(
        self,
        instance_id: str,
        status: InstanceStatus,
        work_id: Optional[str] = None
    ) -> None:
        """Update instance status."""
        instance = self._read_instance(instance_id)
        if instance:
            instance.status = status
            instance.current_work = work_id
            instance.last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._write_instance(instance)

    def heartbeat(self, instance_id: str) -> None:
        """Update instance heartbeat timestamp."""
        instance = self._read_instance(instance_id)
        if instance:
            instance.last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._write_instance(instance)

    def list_instances(self, status: Optional[InstanceStatus] = None) -> List[IcarusInstance]:
        """List all registered instances, optionally filtered by status."""
        instances = []
        for f in self.dirs["instances"].glob("*.json"):
            instance = self._read_instance(f.stem)
            if instance:
                if status is None or instance.status == status:
                    instances.append(instance)
        return instances

    def get_instance(self, instance_id: str) -> Optional[IcarusInstance]:
        """Get a specific instance."""
        return self._read_instance(instance_id)

    def stream_output(self, instance_id: str, message: str) -> None:
        """Append to instance's output stream."""
        stream_file = self.dirs["streams"] / f"{instance_id}.log"
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with open(stream_file, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

    def read_stream(self, instance_id: str, tail: int = 50) -> List[str]:
        """Read recent lines from instance's output stream."""
        stream_file = self.dirs["streams"] / f"{instance_id}.log"
        if not stream_file.exists():
            return []

        lines = stream_file.read_text().splitlines()
        return lines[-tail:] if tail else lines

    # ========== Work Management ==========

    def post_work(self, work: WorkPackage) -> str:
        """Post a work package to the queue. Returns work ID."""
        if not work.id:
            work.id = f"work-{uuid.uuid4().hex[:8]}"

        work_file = self.dirs["work_queue"] / f"{work.id}.json"
        work_file.write_text(json.dumps(asdict(work), indent=2))
        return work.id

    def claim_work(self, instance_id: str) -> Optional[WorkPackage]:
        """
        Claim the highest priority available work package.
        Returns None if no work available.
        Uses file locking to prevent race conditions.
        """
        work_files = sorted(
            self.dirs["work_queue"].glob("*.json"),
            key=lambda f: self._get_work_priority(f)
        )

        for work_file in work_files:
            try:
                # Try to atomically move the file (claim it)
                claimed_path = self.dirs["claimed"] / work_file.name

                # Use file locking for safe claiming
                with open(work_file, "r") as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    work_data = json.load(f)

                    # Update claim info
                    work_data["status"] = WorkStatus.CLAIMED.value
                    work_data["claimed_by"] = instance_id
                    work_data["claimed_at"] = datetime.now(timezone.utc).isoformat()

                    # Write to claimed directory
                    claimed_path.write_text(json.dumps(work_data, indent=2))

                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

                # Remove from queue
                work_file.unlink()

                return WorkPackage(**work_data)

            except (BlockingIOError, FileNotFoundError):
                # Someone else claimed it, try next
                continue

        return None

    def list_pending_work(self) -> List[WorkPackage]:
        """List all pending work packages."""
        work_list = []
        for f in self.dirs["work_queue"].glob("*.json"):
            data = json.loads(f.read_text())
            work_list.append(WorkPackage(**data))
        return sorted(work_list, key=lambda w: w.priority)

    def list_claimed_work(self) -> List[WorkPackage]:
        """List all claimed (in-progress) work packages."""
        work_list = []
        for f in self.dirs["claimed"].glob("*.json"):
            data = json.loads(f.read_text())
            work_list.append(WorkPackage(**data))
        return work_list

    def get_work(self, work_id: str) -> Optional[WorkPackage]:
        """Get a work package by ID (checks queue and claimed)."""
        for dir_name in ["work_queue", "claimed"]:
            work_file = self.dirs[dir_name] / f"{work_id}.json"
            if work_file.exists():
                data = json.loads(work_file.read_text())
                return WorkPackage(**data)
        return None

    def submit_result(
        self,
        work_id: str,
        instance_id: str,
        result: Dict[str, Any]
    ) -> None:
        """Submit result for completed work."""
        result_data = {
            "work_id": work_id,
            "instance_id": instance_id,
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        result_file = self.dirs["results"] / f"{work_id}.json"
        result_file.write_text(json.dumps(result_data, indent=2))

        # Remove from claimed
        claimed_file = self.dirs["claimed"] / f"{work_id}.json"
        if claimed_file.exists():
            claimed_file.unlink()

    def collect_results(self, clear: bool = False) -> List[Dict]:
        """Collect all completed results."""
        results = []
        for f in self.dirs["results"].glob("*.json"):
            results.append(json.loads(f.read_text()))
            if clear:
                f.unlink()
        return results

    def get_result(self, work_id: str) -> Optional[Dict]:
        """Get result for specific work package."""
        result_file = self.dirs["results"] / f"{work_id}.json"
        if result_file.exists():
            return json.loads(result_file.read_text())
        return None

    # ========== Request/Response ==========

    def request_help(
        self,
        instance_id: str,
        work_id: Optional[str],
        request_type: RequestType,
        message: str,
        context: Dict = None
    ) -> str:
        """Submit a request needing Daedalus attention. Returns request ID."""
        request_id = f"req-{uuid.uuid4().hex[:8]}"
        request = Request(
            id=request_id,
            instance_id=instance_id,
            work_id=work_id,
            type=request_type,
            message=message,
            context=context or {},
        )

        request_file = self.dirs["requests"] / f"{request_id}.json"
        request_file.write_text(json.dumps(asdict(request), indent=2))

        return request_id

    def list_pending_requests(self) -> List[Request]:
        """List all pending requests needing attention."""
        requests = []
        for f in self.dirs["requests"].glob("*.json"):
            data = json.loads(f.read_text())
            if not data.get("resolved"):
                requests.append(Request(**data))
        return requests

    def respond_to_request(self, request_id: str, response: Response) -> None:
        """Respond to an Icarus request."""
        response.request_id = request_id

        response_file = self.dirs["responses"] / f"{request_id}.json"
        response_file.write_text(json.dumps(asdict(response), indent=2))

        # Mark request as resolved
        request_file = self.dirs["requests"] / f"{request_id}.json"
        if request_file.exists():
            data = json.loads(request_file.read_text())
            data["resolved"] = True
            request_file.write_text(json.dumps(data, indent=2))

    def wait_for_response(
        self,
        request_id: str,
        timeout: float = 300,
        poll_interval: float = 1.0
    ) -> Optional[Response]:
        """Wait for Daedalus response to a request."""
        response_file = self.dirs["responses"] / f"{request_id}.json"
        start = time.time()

        while time.time() - start < timeout:
            if response_file.exists():
                data = json.loads(response_file.read_text())
                return Response(**data)
            time.sleep(poll_interval)

        return None

    def get_response(self, request_id: str) -> Optional[Response]:
        """Get response for a request (non-blocking)."""
        response_file = self.dirs["responses"] / f"{request_id}.json"
        if response_file.exists():
            data = json.loads(response_file.read_text())
            return Response(**data)
        return None

    # ========== Cleanup ==========

    def cleanup_stale_instances(self, stale_seconds: int = 300) -> List[str]:
        """Remove instances that haven't sent a heartbeat recently."""
        stale = []
        cutoff = datetime.now(timezone.utc).timestamp() - stale_seconds

        for instance in self.list_instances():
            heartbeat = datetime.fromisoformat(instance.last_heartbeat).timestamp()
            if heartbeat < cutoff:
                stale.append(instance.id)
                self.unregister_instance(instance.id)

        return stale

    def reset(self) -> None:
        """Clear all bus data. Use with caution."""
        import shutil
        if self.root.exists():
            shutil.rmtree(self.root)
        self.initialize()

    # ========== Status Summary ==========

    def status_summary(self) -> Dict[str, Any]:
        """Get overall bus status."""
        instances = self.list_instances()
        return {
            "initialized": self.is_initialized(),
            "instances": {
                "total": len(instances),
                "by_status": {
                    status.value: len([i for i in instances if i.status == status])
                    for status in InstanceStatus
                },
            },
            "work": {
                "pending": len(self.list_pending_work()),
                "claimed": len(self.list_claimed_work()),
                "completed": len(list(self.dirs["results"].glob("*.json"))),
            },
            "requests": {
                "pending": len(self.list_pending_requests()),
            },
        }

    # ========== Private Helpers ==========

    def _write_instance(self, instance: IcarusInstance) -> None:
        """Write instance data to file."""
        instance_file = self.dirs["instances"] / f"{instance.id}.json"
        instance_file.write_text(json.dumps(asdict(instance), indent=2))

    def _read_instance(self, instance_id: str) -> Optional[IcarusInstance]:
        """Read instance data from file."""
        instance_file = self.dirs["instances"] / f"{instance_id}.json"
        if instance_file.exists():
            data = json.loads(instance_file.read_text())
            # Convert string status back to enum
            data["status"] = InstanceStatus(data["status"])
            return IcarusInstance(**data)
        return None

    def _get_work_priority(self, work_file: Path) -> int:
        """Get priority from work file for sorting."""
        try:
            data = json.loads(work_file.read_text())
            return data.get("priority", 5)
        except:
            return 5


# ========== CLI Interface ==========

def main():
    """CLI for interacting with the Icarus bus."""
    import argparse

    parser = argparse.ArgumentParser(description="Icarus Coordination Bus")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    subparsers.add_parser("init", help="Initialize the bus")

    # status
    subparsers.add_parser("status", help="Show bus status")

    # instances
    subparsers.add_parser("instances", help="List instances")

    # work
    work_parser = subparsers.add_parser("work", help="Work management")
    work_parser.add_argument("action", choices=["list", "pending", "claimed", "results"])

    # post
    post_parser = subparsers.add_parser("post", help="Post work package")
    post_parser.add_argument("--type", required=True, help="Work type")
    post_parser.add_argument("--desc", required=True, help="Description")
    post_parser.add_argument("--priority", type=int, default=5, help="Priority (1-10)")

    # requests
    subparsers.add_parser("requests", help="List pending requests")

    # streams
    stream_parser = subparsers.add_parser("stream", help="View instance stream")
    stream_parser.add_argument("instance_id", help="Instance ID")
    stream_parser.add_argument("--tail", type=int, default=50, help="Lines to show")

    # reset
    subparsers.add_parser("reset", help="Reset bus (clears all data)")

    args = parser.parse_args()
    bus = IcarusBus()

    if args.command == "init":
        bus.initialize()
        print(f"Bus initialized at {bus.root}")

    elif args.command == "status":
        if not bus.is_initialized():
            print("Bus not initialized. Run: icarus_bus.py init")
            return
        summary = bus.status_summary()
        print(json.dumps(summary, indent=2))

    elif args.command == "instances":
        for inst in bus.list_instances():
            print(f"{inst.id}: {inst.status.value} (work: {inst.current_work or 'none'})")

    elif args.command == "work":
        if args.action == "pending":
            for w in bus.list_pending_work():
                print(f"{w.id}: [{w.priority}] {w.description[:50]}")
        elif args.action == "claimed":
            for w in bus.list_claimed_work():
                print(f"{w.id}: {w.claimed_by} - {w.description[:50]}")
        elif args.action == "results":
            for r in bus.collect_results(clear=False):
                print(f"{r['work_id']}: {r['instance_id']}")

    elif args.command == "post":
        work = WorkPackage(
            id="",
            type=args.type,
            description=args.desc,
            inputs={},
            outputs={},
            priority=args.priority,
        )
        work_id = bus.post_work(work)
        print(f"Posted work: {work_id}")

    elif args.command == "requests":
        for req in bus.list_pending_requests():
            print(f"{req.id}: [{req.type.value}] {req.message[:50]}")

    elif args.command == "stream":
        lines = bus.read_stream(args.instance_id, tail=args.tail)
        for line in lines:
            print(line)

    elif args.command == "reset":
        confirm = input("This will clear all bus data. Continue? [y/N] ")
        if confirm.lower() == "y":
            bus.reset()
            print("Bus reset.")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
