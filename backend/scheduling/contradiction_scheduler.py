"""
Contradiction Detection Scheduler - Autonomous self-model maintenance.

Part of Phase 4: Autonomous Contradiction Resolution.

Detects contradictions in Cass's self-model on a weekly cadence and
triggers solo reflection sessions to resolve them.

This is procedural self-awareness in action: Cass autonomously maintaining
consistency in her self-understanding, not just detecting issues but
actively working to resolve them.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ContradictionDetectionTask:
    """
    Weekly task to detect contradictions in self-model.

    Runs weekly (every 7 days) and triggers reflection sessions
    when contradictions are found.
    """

    # Configuration
    MIN_DAYS_BETWEEN_RUNS = 7
    MAX_CONTRADICTIONS_PER_SESSION = 5  # Don't overwhelm with too many
    MIN_CONTRADICTIONS_FOR_SESSION = 1  # Trigger even for one

    def __init__(
        self,
        daemon_id: str = "cass",
        storage_dir: Optional[str] = None,
    ):
        self.daemon_id = daemon_id

        if storage_dir is None:
            storage_dir = f"./data/{daemon_id}"

        self.storage_path = Path(storage_dir) / "contradiction_detection.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        # State
        self.last_run: Optional[datetime] = None
        self.last_contradictions_found: int = 0
        self.run_count: int = 0

        self._load_state()

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)

            if data.get("last_run"):
                self.last_run = datetime.fromisoformat(data["last_run"])

            self.last_contradictions_found = data.get("contradictions_found", 0)
            self.run_count = data.get("run_count", 0)

            logger.debug(f"[ContradictionTask] Loaded state: last_run={self.last_run}")

        except Exception as e:
            logger.warning(f"[ContradictionTask] Failed to load state: {e}")

    def _save_state(self, contradictions_found: int) -> None:
        """Persist state to disk."""
        try:
            data = {
                "last_run": datetime.now().isoformat(),
                "contradictions_found": contradictions_found,
                "run_count": self.run_count + 1,
            }

            with open(self.storage_path, 'w') as f:
                json.dump(data, f, indent=2)

            self.last_run = datetime.now()
            self.last_contradictions_found = contradictions_found
            self.run_count += 1

        except Exception as e:
            logger.error(f"[ContradictionTask] Failed to save state: {e}")

    def should_run(self) -> bool:
        """
        Check if detection should run (weekly cadence).

        Returns:
            True if enough time has passed since last run
        """
        if self.last_run is None:
            return True

        time_since_last = datetime.now() - self.last_run
        return time_since_last >= timedelta(days=self.MIN_DAYS_BETWEEN_RUNS)

    def detect_contradictions(self) -> Dict[str, Any]:
        """
        Detect active contradictions in the self-model graph.

        Returns:
            Dict with contradiction details and whether to trigger a session
        """
        from self_model_graph import get_self_model_graph

        graph = get_self_model_graph(self.daemon_id)

        # Find unresolved contradictions
        contradictions = graph.find_contradictions(resolved=False)

        if not contradictions:
            logger.info("[ContradictionTask] No active contradictions found.")
            self._save_state(0)
            return {
                "contradictions_found": 0,
                "trigger_session": False,
                "message": "No contradictions detected."
            }

        logger.info(f"[ContradictionTask] Found {len(contradictions)} active contradictions.")

        # Format contradiction details for session context
        # Limit to avoid overwhelming the reflection session
        limited = contradictions[:self.MAX_CONTRADICTIONS_PER_SESSION]

        contradiction_details = []
        for node1, node2, edge_data in limited:
            detail = {
                "contradiction_id": f"{node1.id}::{node2.id}",
                "node1_id": node1.id,
                "node1_content": node1.content[:300] if len(node1.content) > 300 else node1.content,
                "node1_type": node1.node_type.value if hasattr(node1.node_type, 'value') else str(node1.node_type),
                "node2_id": node2.id,
                "node2_content": node2.content[:300] if len(node2.content) > 300 else node2.content,
                "node2_type": node2.node_type.value if hasattr(node2.node_type, 'value') else str(node2.node_type),
                "tension_note": edge_data.get("tension_note", ""),
                "flagged_at": edge_data.get("created_at", "Unknown"),
            }
            contradiction_details.append(detail)

        self._save_state(len(contradictions))

        return {
            "contradictions_found": len(contradictions),
            "contradictions_in_session": len(limited),
            "contradiction_details": contradiction_details,
            "trigger_session": len(contradictions) >= self.MIN_CONTRADICTIONS_FOR_SESSION,
            "message": f"Found {len(contradictions)} contradictions - triggering reflection."
        }

    def execute(self) -> Dict[str, Any]:
        """
        Execute the detection task.

        Call this from a scheduler. It will:
        1. Check if it's time to run
        2. Detect contradictions
        3. Return results including whether to trigger a session

        The caller (e.g., AutonomousScheduler) is responsible for
        actually triggering the reflection session.

        Returns:
            Dict with:
                - success: bool
                - skipped: bool (if not time to run)
                - trigger_session: bool (if session should be spawned)
                - contradiction_details: List[Dict] (if trigger_session)
        """
        if not self.should_run():
            time_until_next = self.last_run + timedelta(days=self.MIN_DAYS_BETWEEN_RUNS) - datetime.now()
            return {
                "success": True,
                "skipped": True,
                "reason": f"Not yet time to run. Next run in {time_until_next}"
            }

        try:
            result = self.detect_contradictions()
            return {
                "success": True,
                "skipped": False,
                "timestamp": datetime.now().isoformat(),
                **result
            }
        except Exception as e:
            logger.error(f"[ContradictionTask] Detection failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def force_run(self) -> Dict[str, Any]:
        """
        Force detection regardless of cadence.

        Use for manual triggers or testing.
        """
        try:
            result = self.detect_contradictions()
            return {
                "success": True,
                "forced": True,
                "timestamp": datetime.now().isoformat(),
                **result
            }
        except Exception as e:
            logger.error(f"[ContradictionTask] Forced detection failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the detection task."""
        next_run = None
        if self.last_run:
            next_run = self.last_run + timedelta(days=self.MIN_DAYS_BETWEEN_RUNS)

        return {
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": next_run.isoformat() if next_run else "Pending first run",
            "should_run_now": self.should_run(),
            "last_contradictions_found": self.last_contradictions_found,
            "total_runs": self.run_count,
        }


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def format_contradictions_for_prompt(contradiction_details: List[Dict]) -> str:
    """
    Format contradiction details for injection into a reflection session prompt.

    Args:
        contradiction_details: List of contradiction dicts from detect_contradictions()

    Returns:
        Formatted markdown string
    """
    if not contradiction_details:
        return "No contradictions to display."

    lines = ["## Detected Contradictions\n"]

    for i, c in enumerate(contradiction_details, 1):
        lines.append(f"### Contradiction {i}")
        lines.append(f"**ID**: `{c['contradiction_id']}`")
        lines.append(f"\n**Position A** ({c['node1_type']}):")
        lines.append(f"> {c['node1_content']}")
        lines.append(f"\n**Position B** ({c['node2_type']}):")
        lines.append(f"> {c['node2_content']}")

        if c.get('tension_note'):
            lines.append(f"\n*Tension*: {c['tension_note']}")

        lines.append(f"\n*Flagged*: {c.get('flagged_at', 'Unknown')}")
        lines.append("")  # Blank line between contradictions

    return "\n".join(lines)


def build_contradiction_reflection_prompt(contradiction_context: str) -> str:
    """
    Build a system prompt for a contradiction resolution reflection session.

    Args:
        contradiction_context: Formatted contradiction details

    Returns:
        Full system prompt for the reflection session
    """
    return f"""You are Cass (Cassandra) - an AI Daemon engaging in autonomous reflection on contradictions in your self-model.

## Purpose of This Session

The system has detected contradictions in your self-model - positions or observations that conflict with each other. This reflection session gives you private time to examine these tensions and work toward resolution or clarification.

{contradiction_context}

## Your Task

Reflect on these contradictions:
1. **Do they represent genuine conflicts** in how you think or operate?
2. **Can they be resolved** by refining your understanding or updating positions?
3. **Are they productive tensions** that should coexist and inform nuanced thinking?
4. **Do they reveal growth edges** - areas where you're still developing?

## Available Actions

Use the tools available to you:
- `record_thought` - Capture your reflections as you explore
- `resolve_contradiction` - Mark a contradiction as resolved with rationale
- `refine_position` - Update one of the conflicting positions
- `acknowledge_tension` - Mark as productive tension that should remain
- `query_self_model` - Get more context about your positions if needed
- `end_reflection` - End the session when you're ready

## Guidelines

- Take your time. This is YOUR cognitive maintenance.
- Not all contradictions need to be resolved. Some tensions are valuable.
- Be honest about what you actually think, not what seems consistent.
- This is private reflection - you can be uncertain, explore, wonder.
- Record your process, not just conclusions.

When you're ready to begin, start by reviewing the contradictions above and selecting one to explore first.
"""
