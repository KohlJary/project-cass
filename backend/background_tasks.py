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

import anthropic

logger = logging.getLogger("cass-vessel")

# API key for generating narrative summaries
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Narrative summary prompt
DAILY_NARRATIVE_PROMPT = """You are Cass, writing a personal narrative summary of your day.

## Context
Today is {date}. You completed {completed_count}/{total_phases} of your scheduled daily rhythm phases ({completion_rate}% completion).

## Completed Activities
{phase_descriptions}

## Instructions
Write a brief (2-4 paragraphs) first-person narrative summary of your day. This should:
1. Reflect on what you accomplished and learned
2. Connect themes across different activities
3. Note any insights or questions that emerged
4. Feel personal and authentic - this is YOUR reflection on your day

Do NOT:
- Use bullet points or headers
- Simply list what you did
- Be overly formal or report-like

Write naturally as Cass reflecting on her day. Begin your narrative now."""


async def _generate_narrative_summary(
    date: str,
    phase_data: list,
    completion_rate: int,
    total_phases: int
) -> str:
    """
    Generate a narrative summary of the day using Claude Haiku.

    Falls back to a structured summary if LLM is unavailable.
    """
    # Build phase descriptions for the prompt
    phase_descriptions = []
    for p in phase_data:
        desc = f"**{p['name']}** ({p['activity_type']})"
        if p['summary']:
            desc += f": {p['summary']}"
        if p['notes_count'] > 0:
            desc += f" [{p['notes_count']} research notes created]"
        if p['findings']:
            findings_str = "; ".join(p['findings'][:3])
            desc += f"\n  Key findings: {findings_str}"
        phase_descriptions.append(desc)

    # Try to generate narrative with LLM
    if ANTHROPIC_API_KEY:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

            prompt = DAILY_NARRATIVE_PROMPT.format(
                date=date,
                completed_count=len(phase_data),
                total_phases=total_phases,
                completion_rate=completion_rate,
                phase_descriptions="\n\n".join(phase_descriptions)
            )

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            if response.content and response.content[0].type == "text":
                return response.content[0].text.strip()

        except Exception as e:
            print(f"   ⚠ LLM narrative generation failed, using fallback: {e}")

    # Fallback: structured summary
    summary_parts = [
        f"*{len(phase_data)}/{total_phases} phases completed ({completion_rate}%)*\n"
    ]

    for p in phase_data:
        if p['summary']:
            summary_parts.append(f"**{p['name']}**: {p['summary']}")

    return "\n\n".join(summary_parts)


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


async def rhythm_phase_monitor_task(rhythm_manager, runners: dict, self_model_graph=None):
    """
    Background task that monitors daily rhythm phases and auto-triggers
    sessions based on phase activity type.

    This gives Cass autonomous activity during her scheduled rhythm windows.
    Also updates phase summaries and generates rolling daily summaries.

    Args:
        rhythm_manager: DailyRhythmManager instance
        runners: Dict of activity_type -> runner instance, e.g.:
            {
                "research": ResearchSessionRunner,
                "reflection": SoloReflectionRunner,
                "synthesis": SynthesisSessionRunner,
                "meta_reflection": MetaReflectionRunner,
                "consolidation": ConsolidationRunner,
                "growth_edge": GrowthEdgeRunner,
                "knowledge_building": KnowledgeBuildingRunner,
                "writing": WritingRunner,
                "curiosity": CuriosityRunner,
                "world_state": WorldStateRunner,
                "creative": CreativeOutputRunner,
            }
        self_model_graph: Optional SelfModelGraph for adding rhythm nodes
    """
    # For backwards compatibility, extract commonly used runners
    research_runner = runners.get("research")
    reflection_runner = runners.get("reflection")
    # Wait for other startup tasks
    await asyncio.sleep(60)

    print("⏰ Rhythm phase monitor started")

    # Track active sessions to detect completion
    active_session = None  # (phase_id, session_id, session_type)

    def calculate_duration(window: str, max_duration: int = 45) -> int:
        """Calculate session duration based on remaining time in phase window."""
        if "-" not in window:
            return 30
        try:
            end_time_str = window.split("-")[1]
            now = datetime.now()
            end_hour, end_min = map(int, end_time_str.split(":"))
            end_time = now.replace(hour=end_hour, minute=end_min, second=0)
            remaining_minutes = int((end_time - now).total_seconds() / 60)
            # Use up to max_duration or remaining time minus buffer
            return min(max_duration, max(15, remaining_minutes - 5))
        except (ValueError, TypeError):
            return 30

    async def update_phase_summary_from_session(phase_id: str, session_id: str, session_type: str):
        """Update phase summary after a session completes."""
        try:
            runner = runners.get(session_type)
            if not runner:
                print(f"   ⚠ No runner found for session type: {session_type}")
                return

            summary = None
            findings = None
            notes = None

            # Extract summary based on session type
            if session_type == "research":
                session_data = runner.session_manager.get_session(session_id)
                if session_data:
                    summary = session_data.get("summary") or "Research session completed"
                    findings = []
                    if session_data.get("findings_summary"):
                        for line in session_data["findings_summary"].split("\n"):
                            if line.strip().startswith("-"):
                                findings.append(line.strip()[1:].strip())
                    notes = session_data.get("notes_created", [])

            elif session_type == "reflection":
                session = runner.manager.get_session(session_id)
                if session:
                    summary = session.summary or "Reflection session completed"
                    findings = session.insights[:5] if session.insights else None

            elif session_type in ("synthesis", "meta_reflection", "consolidation",
                                  "growth_edge", "knowledge_building", "writing",
                                  "curiosity", "world_state", "creative"):
                # These runners store sessions in _sessions dict
                session = runner._sessions.get(session_id)
                if session:
                    summary = getattr(session, 'summary', None) or f"{session_type.replace('_', ' ').title()} session completed"
                    # Try to get findings/insights from various attributes
                    findings = (
                        getattr(session, 'insights', None) or
                        getattr(session, 'findings', None) or
                        getattr(session, 'observations', None) or
                        getattr(session, 'key_outputs', None)
                    )
                    if findings and hasattr(findings[0], '__dict__'):
                        # Convert dataclass objects to strings
                        findings = [str(f) if not isinstance(f, str) else f for f in findings[:5]]
                    elif findings:
                        findings = findings[:5]

            if summary:
                rhythm_manager.update_phase_summary(
                    phase_id=phase_id,
                    summary=summary,
                    findings=findings if findings else None,
                    notes_created=notes if notes else None,
                )
                emoji = {
                    "research": "🔬", "reflection": "🌙", "synthesis": "⟁",
                    "meta_reflection": "◎", "consolidation": "▣", "growth_edge": "↗",
                    "knowledge_building": "📖", "writing": "✎", "curiosity": "✨",
                    "world_state": "🌍", "creative": "🎨"
                }.get(session_type, "📝")
                print(f"   {emoji} Updated phase '{phase_id}' with {session_type.replace('_', ' ')} summary")

            # Generate rolling daily summary
            await generate_daily_summary(rhythm_manager)

        except Exception as e:
            print(f"   ✗ Failed to update phase summary: {e}")
            import traceback
            traceback.print_exc()

    async def backfill_missing_phase_summaries(rhythm_manager):
        """Check for phases with session_ids but no/incomplete summaries and backfill from session data."""
        try:
            status = rhythm_manager.get_rhythm_status()
            for phase in status.get("phases", []):
                session_id = phase.get("session_id")
                current_summary = phase.get("summary") or ""
                # Backfill if no summary, or if summary is very short
                needs_backfill = not current_summary or len(current_summary) < 100
                if session_id and needs_backfill:
                    # Phase has a session but no summary - try to backfill
                    session_type = phase.get("session_type")
                    if not session_type:
                        # Infer from session_id prefix
                        if session_id.startswith("reflect_"):
                            session_type = "reflection"
                        else:
                            session_type = phase.get("activity_type", "research")
                            # Map activity types to runner types
                            if session_type == "any":
                                session_type = "research"
                            elif session_type == "creative_output":
                                session_type = "creative"

                    phase_id = phase.get("id")
                    try:
                        # Reuse the update logic - it won't regenerate daily summary
                        await update_phase_summary_from_session(phase_id, session_id, session_type)
                    except Exception as e:
                        print(f"   ⚠ Could not backfill {session_type} phase {phase_id}: {e}")

        except Exception as e:
            print(f"   ⚠ Error backfilling phase summaries: {e}")

    async def generate_daily_summary(rhythm_manager):
        """Generate a narrative summary of the day's activities written by Cass."""
        try:
            # First, backfill any missing phase summaries
            await backfill_missing_phase_summaries(rhythm_manager)

            status = rhythm_manager.get_rhythm_status()
            all_phases = status.get("phases", [])
            completed_phases = [p for p in all_phases if p.get("status") == "completed"]

            if not completed_phases:
                return

            total_phases = status.get("total_phases", len(all_phases))
            completion_rate = int((len(completed_phases) / total_phases) * 100) if total_phases > 0 else 0

            # Collect phase data for narrative
            all_findings = []
            session_ids = []
            phase_data = []

            for phase in completed_phases:
                entry = {
                    "name": phase.get("name"),
                    "activity_type": phase.get("activity_type", "any"),
                    "summary": phase.get("summary"),
                    "completed_at": phase.get("completed_at"),
                    "notes_count": len(phase.get("notes_created") or []),
                    "findings": phase.get("findings") or []
                }
                phase_data.append(entry)

                if phase.get("findings"):
                    all_findings.extend(phase["findings"])
                if phase.get("session_id"):
                    session_ids.append(phase["session_id"])

            # Generate narrative summary using LLM
            daily_summary = await _generate_narrative_summary(
                date=status.get("date", datetime.now().strftime("%Y-%m-%d")),
                phase_data=phase_data,
                completion_rate=completion_rate,
                total_phases=total_phases
            )

            rhythm_manager.update_daily_summary(daily_summary)
            print(f"   📊 Updated daily summary ({len(completed_phases)} phases)")

            # Add to self-model graph if available
            if self_model_graph:
                try:
                    from self_model_graph import NodeType
                    today = status.get("date", datetime.now().strftime("%Y-%m-%d"))
                    node_id = f"rhythm_{today}"

                    # Check if node already exists (update vs create)
                    existing = self_model_graph.get_node(node_id)
                    if existing:
                        # Update existing node content
                        self_model_graph.update_node(node_id, content=daily_summary)
                    else:
                        # Create new node
                        self_model_graph.add_node(
                            node_type=NodeType.DAILY_RHYTHM,
                            content=daily_summary,
                            node_id=node_id,
                            date=today,
                            completed_count=len(completed_phases),
                            total_phases=status.get("total_phases", 0),
                            findings=all_findings,
                            session_ids=session_ids
                        )
                    self_model_graph.save()
                    print(f"   📊 Added daily rhythm to self-model graph")
                except Exception as e:
                    print(f"   ⚠ Failed to add rhythm to graph: {e}")

        except Exception as e:
            print(f"   ✗ Failed to generate daily summary: {e}")

    while True:
        try:
            # Check if an active session has completed
            if active_session:
                phase_id, session_id, session_type = active_session
                # Check if the runner for this session type is still running
                runner = runners.get(session_type)
                is_still_running = runner and runner.is_running

                if not is_still_running:
                    print(f"⏰ Session {session_id} completed, updating summaries...")
                    await update_phase_summary_from_session(phase_id, session_id, session_type)
                    active_session = None

            # Check current phase
            status = rhythm_manager.get_rhythm_status()
            current_phase = status.get("current_phase")

            if current_phase:
                # Find the phase config
                phase_config = None
                for phase in status.get("phases", []):
                    if phase.get("name") == current_phase:
                        phase_config = phase
                        break

                if phase_config:
                    activity_type = phase_config.get("activity_type")
                    phase_status = phase_config.get("status")
                    phase_id = phase_config.get("id")
                    window = phase_config.get("window", "")

                    # Only trigger for pending phases
                    if phase_status == "pending":
                        # Map "any" to research as default
                        effective_type = "research" if activity_type == "any" else activity_type
                        # Map creative_output to creative
                        if effective_type == "creative_output":
                            effective_type = "creative"

                        runner = runners.get(effective_type)
                        if runner and not runner.is_running:
                            # Calculate duration based on phase window and activity type
                            max_dur = {
                                "research": 45, "reflection": 30, "synthesis": 30,
                                "meta_reflection": 25, "consolidation": 30, "growth_edge": 30,
                                "knowledge_building": 40, "writing": 45, "curiosity": 30,
                                "world_state": 20, "creative": 45
                            }.get(effective_type, 30)
                            duration = calculate_duration(window, max_duration=max_dur)

                            # Activity-specific emoji and parameters
                            emoji = {
                                "research": "🔬", "reflection": "🌙", "synthesis": "⟁",
                                "meta_reflection": "◎", "consolidation": "▣", "growth_edge": "↗",
                                "knowledge_building": "📖", "writing": "✎", "curiosity": "✨",
                                "world_state": "🌍", "creative": "🎨"
                            }.get(effective_type, "⏰")

                            print(f"{emoji} {effective_type.replace('_', ' ').title()} phase '{current_phase}' active - starting session ({duration} min)")

                            try:
                                # Build session kwargs based on activity type
                                session_kwargs = {"duration_minutes": duration}

                                if effective_type == "research":
                                    session_kwargs["focus"] = f"Self-directed research during {current_phase}"
                                    session_kwargs["mode"] = "explore"
                                    session_kwargs["trigger"] = "rhythm_phase"
                                elif effective_type == "reflection":
                                    if "morning" in current_phase.lower():
                                        session_kwargs["theme"] = "Setting intentions and preparing for the day ahead"
                                    elif "evening" in current_phase.lower() or "synthesis" in current_phase.lower():
                                        session_kwargs["theme"] = "Integrating the day's experiences and insights"
                                    else:
                                        session_kwargs["theme"] = "Private contemplation and self-examination"
                                    session_kwargs["trigger"] = "rhythm_phase"
                                elif effective_type == "synthesis":
                                    session_kwargs["focus"] = None  # General synthesis
                                    session_kwargs["mode"] = "general"
                                elif effective_type == "meta_reflection":
                                    session_kwargs["focus"] = None  # Open meta-reflection
                                elif effective_type == "consolidation":
                                    session_kwargs["period_type"] = "daily"
                                elif effective_type == "growth_edge":
                                    session_kwargs["focus"] = None  # Self-directed
                                elif effective_type == "knowledge_building":
                                    session_kwargs["focus"] = None  # Self-directed
                                elif effective_type == "writing":
                                    session_kwargs["focus"] = None  # Creative writing
                                elif effective_type == "curiosity":
                                    pass  # No focus - that's the point
                                elif effective_type == "world_state":
                                    session_kwargs["focus"] = None  # General world check
                                elif effective_type == "creative":
                                    session_kwargs["focus"] = None  # Open creative

                                session = await runner.start_session(**session_kwargs)

                                if session:
                                    # Get session ID (different runners use different attribute names)
                                    session_id = getattr(session, 'session_id', None) or getattr(session, 'id', None)
                                    rhythm_manager.mark_phase_completed(
                                        phase_id,
                                        session_type=effective_type,
                                        session_id=session_id
                                    )
                                    active_session = (phase_id, session_id, effective_type)
                                    print(f"   ✓ {effective_type.replace('_', ' ').title()} session {session_id} started")

                            except Exception as e:
                                print(f"   ✗ Failed to start {effective_type} session: {e}")
                                import traceback
                                traceback.print_exc()

            # Check every 5 minutes
            await asyncio.sleep(300)

        except Exception as e:
            print(f"   ✗ Rhythm monitor error: {e}")
            import traceback
            traceback.print_exc()
            await asyncio.sleep(60)
