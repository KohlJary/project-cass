"""
Atomic Task Handlers - Single-execution versions of background tasks.

These handlers are designed to run once and return, letting the scheduler
handle timing and recurrence. They mirror the functionality of the existing
loop-based tasks in background_tasks.py but are atomic/idempotent.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HandlerResult:
    """Result from a task handler execution."""
    success: bool
    message: str
    cost_usd: float = 0.0
    data: Dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


def get_active_daemon_activity_mode() -> str:
    """Get the activity_mode of the active daemon. Returns 'active' or 'dormant'."""
    try:
        from database import get_db
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT activity_mode FROM daemons WHERE status = 'active' LIMIT 1"
            )
            row = cursor.fetchone()
            return row["activity_mode"] if row and row["activity_mode"] else "active"
    except Exception:
        return "active"


async def github_metrics_handler(github_metrics_manager) -> HandlerResult:
    """
    Fetch GitHub metrics once.

    Mirrors: background_tasks.github_metrics_task
    Atomic: Yes - single fetch operation
    Cost: Minimal (API calls only)
    """
    if not github_metrics_manager:
        return HandlerResult(
            success=False,
            message="GitHub metrics manager not available"
        )

    try:
        await github_metrics_manager.refresh_metrics()
        logger.info("GitHub metrics fetch completed")
        return HandlerResult(
            success=True,
            message="GitHub metrics refreshed",
            cost_usd=0.0
        )
    except Exception as e:
        logger.error(f"GitHub metrics fetch failed: {e}")
        return HandlerResult(
            success=False,
            message=f"GitHub metrics fetch failed: {e}"
        )


async def idle_summarization_handler(
    conversation_manager,
    memory,
    token_tracker=None,
    idle_minutes: int = 30,
    min_unsummarized: int = 5,
) -> HandlerResult:
    """
    Summarize idle conversations once.

    Mirrors: background_tasks.idle_summarization_task
    Atomic: Yes - processes current batch of idle conversations
    Cost: ~$0.01-0.10 depending on conversation count
    """
    from summary_generation import generate_and_store_summary

    if not conversation_manager or not memory:
        return HandlerResult(
            success=False,
            message="Required managers not available"
        )

    try:
        idle_conversations = conversation_manager.get_idle_conversations_needing_summary(
            idle_minutes=idle_minutes,
            min_unsummarized=min_unsummarized
        )

        if not idle_conversations:
            return HandlerResult(
                success=True,
                message="No idle conversations needing summarization",
                data={"summarized_count": 0}
            )

        logger.info(f"Found {len(idle_conversations)} idle conversations needing summarization")
        summarized = 0
        total_cost = 0.0

        for conv_id in idle_conversations:
            try:
                logger.info(f"Summarizing idle conversation {conv_id[:8]}...")
                result = await generate_and_store_summary(
                    conversation_id=conv_id,
                    memory=memory,
                    conversation_manager=conversation_manager,
                    token_tracker=token_tracker,
                    force=False
                )
                summarized += 1
                # Estimate cost (rough estimate)
                total_cost += 0.01
            except Exception as e:
                logger.error(f"Failed to summarize conversation {conv_id}: {e}")

        return HandlerResult(
            success=True,
            message=f"Summarized {summarized}/{len(idle_conversations)} conversations",
            cost_usd=total_cost,
            data={"summarized_count": summarized}
        )

    except Exception as e:
        logger.error(f"Idle summarization failed: {e}")
        return HandlerResult(
            success=False,
            message=f"Idle summarization failed: {e}"
        )


async def daily_journal_handler(
    generate_missing_journals_func=None,
    generate_nightly_dream_func=None,
    self_manager=None,
    data_dir=None,
) -> HandlerResult:
    """
    Generate daily journal entry once.

    Mirrors: journal_tasks.daily_journal_task
    Atomic: Yes - generates journal for yesterday if needed
    Cost: ~$0.10-0.20 for journal + dream
    """
    results = {"journal_generated": False, "dream_generated": False}
    total_cost = 0.0

    # Generate yesterday's journal
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if generate_missing_journals_func:
        try:
            generated = await generate_missing_journals_func(days_to_check=1)
            if generated:
                logger.info(f"Generated journal for {generated[0]}")
                results["journal_generated"] = True
                results["journal_date"] = generated[0]
                total_cost += 0.10
            else:
                logger.info(f"No journal needed for {yesterday}")
        except Exception as e:
            logger.error(f"Journal generation failed: {e}")
            return HandlerResult(
                success=False,
                message=f"Journal generation failed: {e}",
                cost_usd=total_cost
            )

    # Generate nightly dream
    if generate_nightly_dream_func and self_manager and data_dir:
        try:
            dream_id = await generate_nightly_dream_func(
                data_dir=data_dir,
                self_manager=self_manager,
                max_turns=4
            )
            if dream_id:
                logger.info(f"Nightly dream generated: {dream_id}")
                results["dream_generated"] = True
                results["dream_id"] = dream_id
                total_cost += 0.10
        except Exception as e:
            logger.warning(f"Nightly dream generation failed: {e}")
            # Don't fail the whole task for dream failure

    return HandlerResult(
        success=True,
        message=f"Daily journal complete (journal: {results['journal_generated']}, dream: {results['dream_generated']})",
        cost_usd=total_cost,
        data=results
    )


async def rhythm_phase_handler(
    rhythm_manager,
    runners: Dict[str, Any] = None,
    self_model_graph=None,
) -> HandlerResult:
    """
    Check and process current rhythm phase once.

    Mirrors: background_tasks.rhythm_phase_monitor_task
    Atomic: Yes - checks current state and triggers if needed
    Cost: Varies by session type ($0.00-0.50)

    This handler:
    1. Checks if daemon is dormant (skip if so)
    2. Gets current phase from rhythm manager
    3. If phase is pending and runner available, starts session
    4. Does NOT loop - scheduler handles recurrence
    """
    if not rhythm_manager:
        return HandlerResult(
            success=False,
            message="Rhythm manager not available"
        )

    # Check dormancy
    if get_active_daemon_activity_mode() == "dormant":
        return HandlerResult(
            success=True,
            message="Daemon is dormant, skipping rhythm check",
            data={"skipped": True, "reason": "dormant"}
        )

    runners = runners or {}

    try:
        status = rhythm_manager.get_rhythm_status()
        current_phase = status.get("current_phase")

        if not current_phase:
            return HandlerResult(
                success=True,
                message="No active rhythm phase",
                data={"current_phase": None}
            )

        # Find phase config
        phase_config = None
        for phase in status.get("phases", []):
            if phase.get("name") == current_phase:
                phase_config = phase
                break

        if not phase_config:
            return HandlerResult(
                success=True,
                message=f"Phase config not found for {current_phase}",
                data={"current_phase": current_phase}
            )

        activity_type = phase_config.get("activity_type")
        phase_status = phase_config.get("status")
        phase_id = phase_config.get("id")
        window = phase_config.get("window", "")

        # Only trigger for pending phases
        if phase_status != "pending":
            return HandlerResult(
                success=True,
                message=f"Phase {current_phase} is {phase_status}, not pending",
                data={"current_phase": current_phase, "phase_status": phase_status}
            )

        # Map activity types
        effective_type = "research" if activity_type == "any" else activity_type
        if effective_type == "creative_output":
            effective_type = "creative"

        runner = runners.get(effective_type)
        if not runner:
            return HandlerResult(
                success=True,
                message=f"No runner for {effective_type}",
                data={"current_phase": current_phase, "missing_runner": effective_type}
            )

        if runner.is_running:
            return HandlerResult(
                success=True,
                message=f"Runner for {effective_type} already running",
                data={"current_phase": current_phase, "runner_busy": True}
            )

        # Calculate duration
        duration = _calculate_duration(window, effective_type)

        logger.info(f"Starting {effective_type} session for phase {current_phase} ({duration} min)")

        # Build session kwargs
        session_kwargs = _build_session_kwargs(effective_type, current_phase, duration)

        try:
            session = await runner.start_session(**session_kwargs)
            if session:
                session_id = getattr(session, 'session_id', None) or getattr(session, 'id', None)
                rhythm_manager.mark_phase_completed(
                    phase_id,
                    session_type=effective_type,
                    session_id=session_id
                )
                logger.info(f"Started {effective_type} session {session_id}")

                return HandlerResult(
                    success=True,
                    message=f"Started {effective_type} session for {current_phase}",
                    cost_usd=0.0,  # Will be tracked by the session
                    data={
                        "current_phase": current_phase,
                        "session_type": effective_type,
                        "session_id": session_id,
                        "duration_minutes": duration
                    }
                )
        except Exception as e:
            logger.error(f"Failed to start {effective_type} session: {e}")
            return HandlerResult(
                success=False,
                message=f"Failed to start session: {e}",
                data={"current_phase": current_phase, "error": str(e)}
            )

    except Exception as e:
        logger.error(f"Rhythm phase check failed: {e}")
        return HandlerResult(
            success=False,
            message=f"Rhythm phase check failed: {e}"
        )

    return HandlerResult(
        success=True,
        message="Rhythm phase check complete",
        data={"current_phase": current_phase}
    )


async def autonomous_research_handler(
    scheduler=None,
    mode: str = "supervised",
    max_tasks: int = 5,
) -> HandlerResult:
    """
    Run autonomous research based on mode.

    Mirrors: background_tasks.autonomous_research_task
    Atomic: Yes - runs one batch/cycle
    Cost: ~$0.10-0.50 depending on tasks

    Modes:
    - supervised: Do nothing (manual only)
    - batched: Run a batch of tasks
    - continuous: Run single task
    - triggered: Refresh queue only
    """
    if not scheduler:
        return HandlerResult(
            success=False,
            message="Research scheduler not available"
        )

    # Check dormancy
    if get_active_daemon_activity_mode() == "dormant":
        return HandlerResult(
            success=True,
            message="Daemon is dormant, skipping research",
            data={"skipped": True, "reason": "dormant"}
        )

    try:
        if mode == "supervised":
            return HandlerResult(
                success=True,
                message="Supervised mode - manual control only",
                data={"mode": mode}
            )

        elif mode == "batched":
            scheduler.refresh_tasks()
            report = await scheduler.run_batch(max_tasks=max_tasks)

            if report:
                return HandlerResult(
                    success=True,
                    message=f"Batch complete: {report.tasks_completed} tasks, {len(report.pages_created)} pages",
                    cost_usd=0.10 * report.tasks_completed,
                    data={
                        "mode": mode,
                        "tasks_completed": report.tasks_completed,
                        "pages_created": report.pages_created
                    }
                )
            else:
                return HandlerResult(
                    success=True,
                    message="No tasks to run",
                    data={"mode": mode, "tasks_completed": 0}
                )

        elif mode == "continuous":
            stats = scheduler.queue.get_stats()
            if stats.get("queued", 0) > 0:
                report = await scheduler.run_single_task()
                if report and report.tasks_completed > 0:
                    return HandlerResult(
                        success=True,
                        message=f"Completed task: {report.pages_created[0] if report.pages_created else 'task'}",
                        cost_usd=0.10,
                        data={"mode": mode, "tasks_completed": 1}
                    )
            scheduler.refresh_tasks()
            return HandlerResult(
                success=True,
                message="Queue empty or task skipped",
                data={"mode": mode, "tasks_completed": 0}
            )

        elif mode == "triggered":
            scheduler.refresh_tasks()
            return HandlerResult(
                success=True,
                message="Queue refreshed",
                data={"mode": mode, "queued": scheduler.queue.get_stats().get("queued", 0)}
            )

    except Exception as e:
        logger.error(f"Autonomous research failed: {e}")
        return HandlerResult(
            success=False,
            message=f"Autonomous research failed: {e}"
        )


def _calculate_duration(window: str, activity_type: str, max_duration: int = None) -> int:
    """Calculate session duration based on phase window and activity type."""
    if max_duration is None:
        max_duration = {
            "research": 45, "reflection": 30, "synthesis": 30,
            "meta_reflection": 25, "consolidation": 30, "growth_edge": 30,
            "knowledge_building": 40, "writing": 45, "curiosity": 30,
            "world_state": 20, "creative": 45
        }.get(activity_type, 30)

    if "-" not in window:
        return min(30, max_duration)

    try:
        end_time_str = window.split("-")[1]
        now = datetime.now()
        end_hour, end_min = map(int, end_time_str.split(":"))
        end_time = now.replace(hour=end_hour, minute=end_min, second=0)
        remaining_minutes = int((end_time - now).total_seconds() / 60)
        return min(max_duration, max(15, remaining_minutes - 5))
    except (ValueError, TypeError):
        return min(30, max_duration)


def _build_session_kwargs(activity_type: str, phase_name: str, duration: int) -> Dict[str, Any]:
    """Build kwargs for session start based on activity type."""
    kwargs = {"duration_minutes": duration}

    if activity_type == "research":
        kwargs["focus"] = f"Self-directed research during {phase_name}"
        kwargs["mode"] = "explore"
        kwargs["trigger"] = "rhythm_phase"
    elif activity_type == "reflection":
        if "morning" in phase_name.lower():
            kwargs["theme"] = "Setting intentions and preparing for the day ahead"
        elif "evening" in phase_name.lower() or "synthesis" in phase_name.lower():
            kwargs["theme"] = "Integrating the day's experiences and insights"
        else:
            kwargs["theme"] = "Private contemplation and self-examination"
        kwargs["trigger"] = "rhythm_phase"
    elif activity_type == "synthesis":
        kwargs["focus"] = None
        kwargs["mode"] = "general"
    elif activity_type == "meta_reflection":
        kwargs["focus"] = None
    elif activity_type == "consolidation":
        kwargs["period_type"] = "daily"
    elif activity_type in ("growth_edge", "knowledge_building", "writing", "world_state", "creative"):
        kwargs["focus"] = None

    return kwargs
