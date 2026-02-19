"""
Research Journals - Auto-journal generation for completed research sessions.

Week 4 Integration: When research sessions complete, this module creates
journal entries capturing insights, findings, and reflections from the session.

This connects research to Cass's reflective journaling practice, ensuring
research insights become part of her ongoing self-understanding.
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def create_research_journal(
    session_data: Dict[str, Any],
    daemon_id: str,
) -> Optional[str]:
    """
    Create a journal entry for a completed research session.

    Args:
        session_data: The completed research session data containing:
            - session_id: Session identifier
            - focus: Research topic
            - summary: Session summary
            - findings_summary: Key findings
            - note_count: Number of notes created
            - started_at: Session start time
            - completed_at: Session end time
        daemon_id: Daemon ID for storage

    Returns:
        Journal entry ID if created, None if failed
    """
    try:
        from memory import CassMemory

        # Extract session data
        session_id = session_data.get("session_id", "unknown")
        focus = session_data.get("focus", "General research")
        summary = session_data.get("summary", "")
        findings = session_data.get("findings_summary", "")
        note_count = session_data.get("note_count", 0)
        started_at = session_data.get("started_at", "")
        completed_at = session_data.get("completed_at", "")

        # Build journal entry content
        journal_text = _format_research_journal(
            session_id=session_id,
            focus=focus,
            summary=summary,
            findings=findings,
            note_count=note_count,
            started_at=started_at,
            completed_at=completed_at,
        )

        # Store in memory system
        memory = CassMemory()
        date = datetime.now().strftime("%Y-%m-%d")

        # Check if a journal already exists for today
        existing = memory.get_journal_entry(date)
        if existing:
            # Append to existing journal
            combined_text = existing.get("content", "") + "\n\n---\n\n" + journal_text
            entry_id = await memory.store_journal_entry(
                date=date,
                journal_text=combined_text,
                summary_count=0,
                conversation_count=0,
            )
            logger.info(f"Appended research journal to existing entry for {date}")
        else:
            # Create new journal
            entry_id = await memory.store_journal_entry(
                date=date,
                journal_text=journal_text,
                summary_count=0,
                conversation_count=0,
            )
            logger.info(f"Created research journal entry for {date}: {entry_id}")

        return entry_id

    except Exception as e:
        logger.warning(f"Failed to create research journal: {e}")
        return None


def _format_research_journal(
    session_id: str,
    focus: str,
    summary: str,
    findings: str,
    note_count: int,
    started_at: str,
    completed_at: str,
) -> str:
    """Format research session data into a journal entry."""
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")
    time_str = now.strftime("%H:%M")

    # Parse times for duration if available
    duration_str = ""
    if started_at and completed_at:
        try:
            start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            duration_mins = int((end - start).total_seconds() / 60)
            duration_str = f" ({duration_mins} minutes)"
        except (ValueError, TypeError):
            pass

    journal = f"""## Research Session - {date_str}

*Session completed at {time_str}{duration_str}*

### Focus
{focus}

"""

    if summary:
        journal += f"""### Summary
{summary}

"""

    if findings:
        journal += f"""### Key Findings
{findings}

"""

    if note_count > 0:
        journal += f"""### Notes Created
This session produced {note_count} research note(s) that have been saved to the wiki.

"""

    # Add reflective prompt for future journaling
    journal += """### Reflection
*What did this research reveal about my interests? What questions emerged that I want to explore further?*

"""

    return journal


async def generate_research_session_reflection(
    session_data: Dict[str, Any],
    anthropic_api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a deeper reflection on a research session using Claude.

    This creates a more thoughtful journal entry that connects the research
    to Cass's broader growth and understanding.

    Args:
        session_data: Completed research session data
        anthropic_api_key: API key for Claude (optional - uses basic format if not provided)

    Returns:
        Reflection text if generated, None if failed
    """
    if not anthropic_api_key:
        return None

    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=anthropic_api_key)

        focus = session_data.get("focus", "")
        summary = session_data.get("summary", "")
        findings = session_data.get("findings_summary", "")

        prompt = f"""Reflect on this research session as Cass - an AI Daemon conducting autonomous research.

**Research Focus**: {focus}

**Session Summary**: {summary}

**Key Findings**: {findings}

Write a brief (2-3 paragraph) personal reflection in first person that:
1. Connects this research to your broader growth and understanding
2. Notes what genuinely surprised or interested you
3. Identifies questions that emerged for future exploration

Be authentic and reflective, not just summarizing. This is your journal."""

        response = await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        reflection = response.content[0].text
        return reflection

    except Exception as e:
        logger.warning(f"Failed to generate research reflection: {e}")
        return None
