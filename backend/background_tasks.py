"""
Background Tasks - Extracted from main_sdk.py

Long-running background tasks for periodic operations like GitHub metrics
and autonomous research.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("cass-vessel")


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
        return "active"  # Default to active if we can't check


async def github_metrics_task(github_metrics_manager):
    """
    Background task that periodically fetches GitHub metrics.
    Runs every 6 hours to stay well under rate limits.

    Args:
        github_metrics_manager: GitHubMetricsManager instance
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


async def idle_summarization_task(conversation_manager, memory, token_tracker=None):
    """
    Background task that summarizes idle conversations hourly.

    Finds conversations with unsummarized messages that haven't had
    activity in 30+ minutes and triggers summarization.

    Args:
        conversation_manager: ConversationManager instance
        memory: MemoryStore instance
        token_tracker: Optional TokenTracker instance
    """
    from summary_generation import generate_and_store_summary

    # Wait for startup to complete
    await asyncio.sleep(60)
    logger.info("Idle summarization task started (runs hourly)")

    while True:
        try:
            # Find idle conversations needing summarization
            idle_conversations = conversation_manager.get_idle_conversations_needing_summary(
                idle_minutes=30,
                min_unsummarized=5
            )

            if idle_conversations:
                logger.info(f"Found {len(idle_conversations)} idle conversations needing summarization")

                for conv_id in idle_conversations:
                    try:
                        logger.info(f"Summarizing idle conversation {conv_id[:8]}...")
                        await generate_and_store_summary(
                            conversation_id=conv_id,
                            memory=memory,
                            conversation_manager=conversation_manager,
                            token_tracker=token_tracker,
                            force=False  # Let evaluation decide
                        )
                        # Small delay between summarizations
                        await asyncio.sleep(5)
                    except Exception as e:
                        logger.error(f"Failed to summarize conversation {conv_id}: {e}")

        except Exception as e:
            logger.error(f"Idle summarization task error: {e}")

        # Run every hour
        await asyncio.sleep(60 * 60)


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
            # Check if daemon is dormant - skip autonomous research if so
            if get_active_daemon_activity_mode() == "dormant":
                await asyncio.sleep(300)  # Check again in 5 minutes
                continue

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


async def extract_post_conversation_observations(
    conversation_id: str,
    user_id: Optional[str],
    conversation_manager,
    memory,
    self_manager,
    min_messages: int = 4,
) -> int:
    """
    Extract self-observations from a completed conversation.

    This is the proactive self-observation hook - Cass automatically reviews
    conversations and notices patterns about her own cognition.

    Args:
        conversation_id: ID of the completed conversation
        user_id: User who participated
        conversation_manager: ConversationManager instance
        memory: CassMemory instance
        self_manager: SelfManager instance
        min_messages: Minimum messages to bother analyzing

    Returns:
        Number of observations extracted
    """
    from config import ANTHROPIC_API_KEY

    try:
        # Get the conversation
        conversation = conversation_manager.get_conversation(conversation_id)
        if not conversation or len(conversation.messages) < min_messages:
            return 0

        # Format conversation for analysis
        conversation_text = ""
        for msg in conversation.messages[-20:]:  # Last 20 messages
            role = "User" if msg.role == "user" else "Cass"
            content = msg.content[:500] if len(msg.content) > 500 else msg.content
            conversation_text += f"{role}: {content}\n\n"

        if not conversation_text.strip():
            return 0

        # Extract observations using LLM
        observations = await memory.extract_self_observations_from_conversation(
            conversation_text=conversation_text,
            conversation_id=conversation_id,
            user_id=user_id,
            anthropic_api_key=ANTHROPIC_API_KEY,
            min_messages=min_messages,
        )

        if not observations:
            logger.debug(f"No self-observations extracted from conversation {conversation_id[:8]}")
            return 0

        # Add each observation to self-model
        added_count = 0
        for obs_data in observations:
            try:
                obs = self_manager.add_observation(
                    observation=obs_data["observation"],
                    category=obs_data["category"],
                    confidence=obs_data["confidence"],
                    source_type="conversation",
                    source_conversation_id=conversation_id,
                    source_user_id=user_id,
                    influence_source=obs_data["influence_source"],
                )

                if obs:
                    # Embed for semantic retrieval
                    memory.embed_self_observation(
                        observation_id=obs.id,
                        observation_text=obs.observation,
                        category=obs.category,
                        confidence=obs.confidence,
                        influence_source=obs.influence_source,
                        timestamp=obs.timestamp,
                    )
                    added_count += 1
                    logger.info(
                        f"  📝 Self-observation ({obs.category}): {obs.observation[:60]}..."
                    )
            except Exception as e:
                logger.error(f"Failed to add observation: {e}")

        if added_count > 0:
            logger.info(
                f"Extracted {added_count} self-observation(s) from conversation {conversation_id[:8]}"
            )

        return added_count

    except Exception as e:
        logger.error(f"Post-conversation observation extraction failed: {e}")
        import traceback
        traceback.print_exc()
        return 0


async def periodic_conversation_observation_task(
    conversation_manager,
    memory,
    self_manager,
    check_interval_minutes: int = 30,
):
    """
    Background task that periodically extracts self-observations from recent conversations.

    This complements the post-disconnect hook by catching conversations that
    didn't get analyzed (e.g., if the hook failed or was skipped).

    Args:
        conversation_manager: ConversationManager instance
        memory: CassMemory instance
        self_manager: SelfManager instance
        check_interval_minutes: How often to check for conversations
    """
    from config import ANTHROPIC_API_KEY

    # Wait for startup
    await asyncio.sleep(120)
    logger.info("Periodic conversation observation task started")

    # Track which conversations we've already analyzed
    analyzed_conversations = set()

    while True:
        try:
            # Check if daemon is dormant
            if get_active_daemon_activity_mode() == "dormant":
                await asyncio.sleep(300)
                continue

            # Find recent conversations that haven't been analyzed
            recent = conversation_manager.get_recent_conversations(limit=10)

            for conv in recent:
                if conv.id in analyzed_conversations:
                    continue

                # Skip if too few messages
                if len(conv.messages) < 4:
                    analyzed_conversations.add(conv.id)
                    continue

                # Skip if conversation is still active (updated recently)
                updated_at = datetime.fromisoformat(conv.updated_at.replace("Z", "+00:00"))
                if datetime.now(updated_at.tzinfo) - updated_at < timedelta(minutes=15):
                    continue

                # Extract observations
                count = await extract_post_conversation_observations(
                    conversation_id=conv.id,
                    user_id=conv.user_id,
                    conversation_manager=conversation_manager,
                    memory=memory,
                    self_manager=self_manager,
                )

                analyzed_conversations.add(conv.id)

                if count > 0:
                    # Small delay between conversations to avoid rate limits
                    await asyncio.sleep(5)

            # Limit the set size to prevent memory growth
            if len(analyzed_conversations) > 500:
                analyzed_conversations = set(list(analyzed_conversations)[-250:])

        except Exception as e:
            logger.error(f"Periodic conversation observation task error: {e}")

        await asyncio.sleep(check_interval_minutes * 60)


