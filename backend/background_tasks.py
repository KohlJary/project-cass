"""Extracted from main_sdk.py"""


import asyncio
from datetime import datetime, timedelta

async def github_metrics_task():
    """
    Background task that periodically fetches GitHub metrics.
    Runs every 6 hours to stay well under rate limits.
    """
    # Initial fetch on startup (after a short delay)
    await asyncio.sleep(30)  # Wait for other startup tasks
    try:
        await github_metrics_manager.refresh_metrics()
        logger.info("Initial GitHub metrics fetch completed")
    except Exception as e:
        logger.error(f"Initial GitHub metrics fetch failed: {e}")

    # Then run every 6 hours
    while True:
        await asyncio.sleep(6 * 60 * 60)  # 6 hours
        try:
            await github_metrics_manager.refresh_metrics()
            logger.info("Scheduled GitHub metrics fetch completed")
        except Exception as e:
            logger.error(f"Scheduled GitHub metrics fetch failed: {e}")

async def autonomous_research_task():
    """
    Background task that runs autonomous research based on scheduler mode.

    Modes:
    - supervised: Do nothing (manual control only)
    - batched: Run a batch of tasks at scheduled times (default: 3am)
    - continuous: Run tasks whenever the queue has items
    - triggered: Run when specific conditions are met (e.g., after conversations)
    """
    from routes.wiki import _get_scheduler
    from wiki import SchedulerMode

    # Wait for scheduler to be initialized
    await asyncio.sleep(10)

    scheduler = _get_scheduler()
    if not scheduler:
        print("🔬 Research scheduler not available, autonomous research disabled")
        return

    print(f"🔬 Autonomous research task started (mode: {scheduler.config.mode.value})")

    while True:
        try:
            mode = scheduler.config.mode

            if mode == SchedulerMode.SUPERVISED:
                # In supervised mode, just sleep and check periodically for mode changes
                await asyncio.sleep(300)  # Check every 5 minutes
                continue

            elif mode == SchedulerMode.BATCHED:
                # Run a batch at scheduled time (6am by default)
                now = datetime.now()
                target_hour = 6  # 6am

                if now.hour < target_hour:
                    target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
                else:
                    # Already past 6am today, schedule for tomorrow
                    tomorrow = now + timedelta(days=1)
                    target = tomorrow.replace(hour=target_hour, minute=0, second=0, microsecond=0)

                wait_seconds = (target - now).total_seconds()
                print(f"🔬 Next research batch scheduled in {wait_seconds/3600:.1f} hours (at {target.strftime('%Y-%m-%d %H:%M')})")
                await asyncio.sleep(wait_seconds)

                # Run batched research
                print(f"🔬 Running scheduled research batch...")
                scheduler.refresh_tasks()
                report = await scheduler.run_batch(max_tasks=scheduler.config.max_tasks_per_cycle)

                if report:
                    print(f"   ✓ Completed {report.tasks_completed} tasks, created {len(report.pages_created)} pages")
                    if report.key_insights:
                        print(f"   💡 Key insight: {report.key_insights[0][:80]}...")
                else:
                    print(f"   ℹ No tasks to run")

            elif mode == SchedulerMode.CONTINUOUS:
                # Run tasks continuously with delays between them
                stats = scheduler.queue.get_stats()

                if stats.get("queued", 0) > 0:
                    print(f"🔬 Continuous mode: running next task ({stats.get('queued', 0)} queued)")
                    report = await scheduler.run_single_task()

                    if report and report.tasks_completed > 0:
                        print(f"   ✓ Completed: {report.pages_created[0] if report.pages_created else 'task'}")
                        # Short delay between tasks
                        await asyncio.sleep(scheduler.config.min_delay_between_tasks)
                    else:
                        # Longer delay if nothing was done
                        await asyncio.sleep(60)
                else:
                    # Refresh queue and wait before checking again
                    scheduler.refresh_tasks()
                    await asyncio.sleep(300)  # Check every 5 minutes when queue is empty

            elif mode == SchedulerMode.TRIGGERED:
                # In triggered mode, we wait for external events
                # The scheduler gets triggered by conversation ends, etc.
                # Here we just do periodic maintenance
                await asyncio.sleep(300)  # Check every 5 minutes
                scheduler.refresh_tasks()  # Keep the queue updated

        except Exception as e:
            print(f"   ✗ Autonomous research task error: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(60)  # Wait a bit before retrying
