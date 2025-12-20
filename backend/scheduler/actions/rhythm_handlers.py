"""
Rhythm Action Handlers - Daily rhythm phase management.

These handlers wrap the rhythm management functionality from background_tasks.py.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from . import ActionResult

logger = logging.getLogger(__name__)


async def update_phase_summary_action(context: Dict[str, Any]) -> ActionResult:
    """
    Update rhythm phase summary after session completion.

    Expects context to contain:
    - phase_id: str
    - session_id: str
    - session_type: str
    - managers.rhythm_manager
    - runners: Dict of session runners
    """
    managers = context.get("managers", {})
    runners = context.get("runners", {})
    rhythm_manager = managers.get("rhythm_manager")

    phase_id = context.get("phase_id")
    session_id = context.get("session_id")
    session_type = context.get("session_type")

    if not rhythm_manager:
        return ActionResult(
            success=False,
            message="rhythm_manager not available"
        )

    if not phase_id or not session_id or not session_type:
        return ActionResult(
            success=False,
            message="phase_id, session_id, and session_type required"
        )

    try:
        runner = runners.get(session_type)
        if not runner:
            return ActionResult(
                success=False,
                message=f"No runner found for session type: {session_type}"
            )

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

        else:
            # Generic runner pattern
            session = runner._sessions.get(session_id) if hasattr(runner, '_sessions') else None
            if session:
                summary = getattr(session, 'summary', None) or f"{session_type.replace('_', ' ').title()} session completed"
                findings = (
                    getattr(session, 'insights', None) or
                    getattr(session, 'findings', None) or
                    getattr(session, 'observations', None) or
                    getattr(session, 'key_outputs', None)
                )
                if findings and len(findings) > 0 and hasattr(findings[0], '__dict__'):
                    findings = [str(f) if not isinstance(f, str) else f for f in findings[:5]]
                elif findings:
                    findings = findings[:5]

        if summary:
            rhythm_manager.mark_phase_completed(
                phase_id=phase_id,
                session_id=session_id,
                session_type=session_type,
                summary=summary,
                findings=findings if findings else None,
                notes_created=notes if notes else None,
            )
            logger.info(f"Updated phase {phase_id} with {session_type} summary")

            return ActionResult(
                success=True,
                message=f"Updated phase summary for {phase_id}",
                data={
                    "phase_id": phase_id,
                    "session_type": session_type,
                    "has_summary": bool(summary),
                    "findings_count": len(findings) if findings else 0
                }
            )
        else:
            return ActionResult(
                success=True,
                message=f"No summary available for session {session_id}",
                data={"phase_id": phase_id, "session_id": session_id}
            )

    except Exception as e:
        logger.error(f"Failed to update phase summary: {e}")
        return ActionResult(
            success=False,
            message=f"Failed to update phase summary: {e}"
        )


async def backfill_summaries_action(context: Dict[str, Any]) -> ActionResult:
    """
    Backfill missing summaries for phases with session_ids.

    Expects managers to contain:
    - rhythm_manager
    - runners (for session data lookup)
    """
    managers = context.get("managers", {})
    runners = context.get("runners", {})
    rhythm_manager = managers.get("rhythm_manager")

    if not rhythm_manager:
        return ActionResult(
            success=False,
            message="rhythm_manager not available"
        )

    try:
        status = rhythm_manager.get_rhythm_status()
        backfilled = 0

        for phase in status.get("phases", []):
            session_id = phase.get("session_id")
            current_summary = phase.get("summary") or ""
            needs_backfill = not current_summary or len(current_summary) < 100

            if session_id and needs_backfill:
                session_type = phase.get("session_type")
                if not session_type:
                    # Infer from session_id prefix
                    if session_id.startswith("reflect_"):
                        session_type = "reflection"
                    else:
                        session_type = phase.get("activity_type", "research")
                        if session_type == "any":
                            session_type = "research"
                        elif session_type == "creative_output":
                            session_type = "creative"

                phase_id = phase.get("id")

                # Try to get summary from runner
                runner = runners.get(session_type)
                if runner:
                    try:
                        # Reuse update logic
                        result = await update_phase_summary_action({
                            "phase_id": phase_id,
                            "session_id": session_id,
                            "session_type": session_type,
                            "managers": managers,
                            "runners": runners,
                            "definition": context.get("definition")
                        })
                        if result.success:
                            backfilled += 1
                    except Exception as e:
                        logger.warning(f"Could not backfill phase {phase_id}: {e}")

        return ActionResult(
            success=True,
            message=f"Backfilled {backfilled} phase summaries",
            data={"backfilled_count": backfilled}
        )

    except Exception as e:
        logger.error(f"Backfill summaries failed: {e}")
        return ActionResult(
            success=False,
            message=f"Backfill summaries failed: {e}"
        )


async def generate_daily_narrative_action(context: Dict[str, Any]) -> ActionResult:
    """
    Generate narrative summary of day's rhythm activities.

    Expects managers to contain:
    - rhythm_manager
    """
    import anthropic
    import os

    managers = context.get("managers", {})
    rhythm_manager = managers.get("rhythm_manager")

    if not rhythm_manager:
        return ActionResult(
            success=False,
            message="rhythm_manager not available"
        )

    try:
        status = rhythm_manager.get_rhythm_status()
        all_phases = status.get("phases", [])
        completed_phases = [p for p in all_phases if p.get("status") == "completed"]

        if not completed_phases:
            return ActionResult(
                success=True,
                message="No completed phases to summarize",
                data={"completed_count": 0}
            )

        total_phases = status.get("total_phases", len(all_phases))
        completion_rate = int((len(completed_phases) / total_phases) * 100) if total_phases > 0 else 0

        # Collect phase data
        phase_data = []
        all_findings = []

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

        # Generate narrative using LLM
        date = status.get("date", datetime.now().strftime("%Y-%m-%d"))
        daily_summary = await _generate_narrative_summary(
            date=date,
            phase_data=phase_data,
            completion_rate=completion_rate,
            total_phases=total_phases
        )

        rhythm_manager.update_daily_summary(daily_summary)
        logger.info(f"Generated daily narrative ({len(completed_phases)} phases)")

        return ActionResult(
            success=True,
            message=f"Generated daily narrative for {date}",
            cost_usd=context["definition"].estimated_cost_usd,
            data={
                "date": date,
                "completed_phases": len(completed_phases),
                "total_phases": total_phases,
                "completion_rate": completion_rate
            }
        )

    except Exception as e:
        logger.error(f"Generate daily narrative failed: {e}")
        return ActionResult(
            success=False,
            message=f"Generate daily narrative failed: {e}"
        )


async def add_to_self_model_action(context: Dict[str, Any]) -> ActionResult:
    """
    Add daily rhythm node to self-model graph.

    Expects managers to contain:
    - rhythm_manager
    - self_model_graph
    """
    managers = context.get("managers", {})
    rhythm_manager = managers.get("rhythm_manager")
    self_model_graph = managers.get("self_model_graph")

    if not rhythm_manager:
        return ActionResult(
            success=False,
            message="rhythm_manager not available"
        )

    if not self_model_graph:
        return ActionResult(
            success=True,
            message="self_model_graph not available, skipping",
            data={"skipped": True}
        )

    try:
        from self_model_graph import NodeType

        status = rhythm_manager.get_rhythm_status()
        all_phases = status.get("phases", [])
        completed_phases = [p for p in all_phases if p.get("status") == "completed"]

        if not completed_phases:
            return ActionResult(
                success=True,
                message="No completed phases to add to graph",
                data={"added": False}
            )

        # Collect data
        all_findings = []
        session_ids = []
        for phase in completed_phases:
            if phase.get("findings"):
                all_findings.extend(phase["findings"])
            if phase.get("session_id"):
                session_ids.append(phase["session_id"])

        today = status.get("date", datetime.now().strftime("%Y-%m-%d"))
        node_id = f"rhythm_{today}"
        daily_summary = status.get("daily_summary", "")

        # Check if node exists
        existing = self_model_graph.get_node(node_id)
        if existing:
            self_model_graph.update_node(node_id, content=daily_summary)
            action = "updated"
        else:
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
            action = "created"

        self_model_graph.save()
        logger.info(f"Added daily rhythm to self-model graph ({action})")

        return ActionResult(
            success=True,
            message=f"Rhythm node {action} in self-model graph",
            data={
                "node_id": node_id,
                "action": action,
                "completed_phases": len(completed_phases)
            }
        )

    except Exception as e:
        logger.error(f"Add to self-model failed: {e}")
        return ActionResult(
            success=False,
            message=f"Add to self-model failed: {e}"
        )


# Helper function for narrative generation
async def _generate_narrative_summary(
    date: str,
    phase_data: list,
    completion_rate: int,
    total_phases: int
) -> str:
    """Generate a narrative summary using Claude Haiku."""
    import anthropic
    import os

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    DAILY_NARRATIVE_PROMPT = """You are Cass, reflecting on your day's activities in first person.

Date: {date}
Phases completed: {completed_count}/{total_phases} ({completion_rate}%)

Activities:
{phase_descriptions}

Write a brief, natural first-person reflection (2-3 sentences) on what you accomplished
and any insights from the day. Be genuine and conversational, not formal or report-like."""

    # Build phase descriptions
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
            logger.warning(f"LLM narrative generation failed, using fallback: {e}")

    # Fallback: structured summary
    summary_parts = [
        f"*{len(phase_data)}/{total_phases} phases completed ({completion_rate}%)*\n"
    ]
    for p in phase_data:
        if p['summary']:
            summary_parts.append(f"**{p['name']}**: {p['summary']}")

    return "\n\n".join(summary_parts)
