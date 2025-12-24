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


async def goal_refinement_handler(
    daemon_id: str = None,
    agent_client=None,
) -> HandlerResult:
    """
    Review and refine goals that need more detail.

    Finds goals missing proper descriptions or completion criteria
    and asks Cass to flesh them out.

    Atomic: Yes - processes one batch of goals needing refinement
    Cost: ~$0.10-0.30 depending on number of goals
    """
    from unified_goals import UnifiedGoalManager, GoalStatus

    if not daemon_id:
        from database import get_daemon_id
        daemon_id = get_daemon_id()

    manager = UnifiedGoalManager(daemon_id)

    try:
        # Find goals needing refinement (active/approved but lacking detail)
        all_goals = manager.list_goals()
        needs_refinement = []

        for goal in all_goals:
            if goal.status not in [GoalStatus.ACTIVE.value, GoalStatus.APPROVED.value]:
                continue
            if goal.parent_id:  # Skip sub-goals - focus on top-level
                continue

            needs_work = False
            reasons = []

            # Check description quality
            if not goal.description or len(goal.description.strip()) < 50:
                needs_work = True
                reasons.append("missing or brief description")

            # Check completion criteria
            if not goal.completion_criteria or len(goal.completion_criteria) < 2:
                needs_work = True
                reasons.append("missing or insufficient completion criteria")

            if needs_work:
                needs_refinement.append({
                    "goal": goal,
                    "reasons": reasons,
                })

        if not needs_refinement:
            return HandlerResult(
                success=True,
                message="All active goals are well-defined",
                data={"goals_checked": len(all_goals), "needs_refinement": 0}
            )

        # Log goals needing refinement (actual refinement requires conversation with Cass)
        goal_titles = [g["goal"].title for g in needs_refinement[:5]]
        logger.info(f"Found {len(needs_refinement)} goals needing refinement: {goal_titles}")

        # For now, just report - actual refinement happens via conversation
        # Future: Could integrate with agent to auto-refine
        return HandlerResult(
            success=True,
            message=f"Found {len(needs_refinement)} goals needing refinement",
            cost_usd=0.0,
            data={
                "goals_checked": len(all_goals),
                "needs_refinement": len(needs_refinement),
                "goal_ids": [g["goal"].id for g in needs_refinement[:10]],
                "goal_titles": goal_titles,
            }
        )

    except Exception as e:
        logger.error(f"Goal refinement check failed: {e}")
        return HandlerResult(
            success=False,
            message=f"Goal refinement check failed: {e}"
        )
