"""
Autonomous Scheduling System.

Replaces rigid daily rhythms with self-directed work scheduling.
Cass decides what to work on based on state, curiosity, budget, and time.

Key components:
- DayPhaseTracker: Tracks time-of-day phases, emits state bus events
- PhaseQueueManager: Queues work for specific phases, triggers on transition
- SchedulingDecisionEngine: Cass's self-scheduling decision logic
- AutonomousScheduler: Bridges decisions to Synkratos execution
"""

from .work_unit import WorkUnit, TimeWindow, WorkStatus, WorkPriority, ScoredCandidate
from .templates import WORK_TEMPLATES, WorkUnitTemplate, get_template, list_templates
from .decision_engine import SchedulingDecisionEngine, DecisionContext
from .autonomous_scheduler import AutonomousScheduler
from .day_phase import DayPhase, DayPhaseTracker, PhaseWindow, PhaseTransition
from .phase_queue import PhaseQueueManager, QueuedWorkUnit
from .work_summary_store import WorkSummaryStore, WorkSummary, ActionSummary, generate_slug
from .contradiction_scheduler import (
    ContradictionDetectionTask,
    format_contradictions_for_prompt,
    build_contradiction_reflection_prompt,
)

__all__ = [
    # Models
    "WorkUnit",
    "TimeWindow",
    "WorkStatus",
    "WorkPriority",
    "ScoredCandidate",
    # Templates
    "WORK_TEMPLATES",
    "WorkUnitTemplate",
    "get_template",
    "list_templates",
    # Decision Engine
    "SchedulingDecisionEngine",
    "DecisionContext",
    # Scheduler
    "AutonomousScheduler",
    # Day Phases
    "DayPhase",
    "DayPhaseTracker",
    "PhaseWindow",
    "PhaseTransition",
    # Phase Queues
    "PhaseQueueManager",
    "QueuedWorkUnit",
    # Work Summaries
    "WorkSummaryStore",
    "WorkSummary",
    "ActionSummary",
    "generate_slug",
    # Contradiction Detection
    "ContradictionDetectionTask",
    "format_contradictions_for_prompt",
    "build_contradiction_reflection_prompt",
]
