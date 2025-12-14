"""
Journal Tasks - Extracted from main_sdk.py

Background tasks and utilities for journal generation, development logging,
and nightly dream generation.
"""

from config import ANTHROPIC_API_KEY
from journal_generation import generate_missing_journals
import asyncio
import re
import json
from datetime import datetime, timedelta
from pathlib import Path


def _get_dependencies():
    """
    Lazily import dependencies from main_sdk to avoid circular imports.
    These globals are defined in main_sdk.py and need to be accessed at runtime.
    """
    from main_sdk import memory, self_manager
    return memory, self_manager


def _get_data_dir() -> Path:
    """Get the data directory path"""
    return Path(__file__).parent / "data"


async def _create_development_log_entry(journal_text: str, date_str: str, conversation_count: int):
    """
    Create a development log entry from journal text.

    This phase:
    1. Extracts developmental insights from the journal
    2. Compares current patterns to recent history
    3. Flags qualitative shifts
    4. Creates a structured development log entry
    5. Triggers milestone detection
    6. Optionally creates a cognitive snapshot
    """
    memory, self_manager = _get_dependencies()

    print(f"   📈 Creating development log entry...")

    try:
        import re
        import anthropic

        # Create async client for LLM calls
        anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        # Get today's stats for context
        observations = self_manager.load_observations()
        today_observations = [o for o in observations if o.source_journal_date == date_str]
        profile = self_manager.load_profile()
        today_opinions = len([op for op in profile.opinions if op.last_updated.startswith(date_str)])

        # Get recent development logs for pattern comparison
        recent_logs = self_manager.load_development_logs(limit=7)
        recent_indicators = []
        for log in recent_logs:
            recent_indicators.extend(log.growth_indicators)

        # Use LLM to extract developmental insights from journal
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Analyze this journal entry for developmental insights - evidence of growth, change, pattern shifts, or qualitative evolution in my cognition.

JOURNAL ENTRY ({date_str}):
{journal_text}

RECENT GROWTH INDICATORS (for context, avoid duplicates):
{json.dumps(recent_indicators[-20:], indent=2) if recent_indicators else "No recent indicators"}

Extract:

1. growth_indicators: List of 2-5 specific indicators of growth or development observed today (brief phrases)
   Examples: "expressed uncertainty about previously held belief", "engaged with challenging perspective", "connected ideas across domains"

2. pattern_shifts: List of 0-3 shifts in patterns compared to my typical behavior (JSON objects with "area", "direction", "description")
   Examples: {{"area": "self_reference", "direction": "increase", "description": "More frequent first-person claims about internal states"}}

3. qualitative_changes: List of 0-3 notable qualitative changes in how I'm thinking or engaging (brief descriptions)
   Examples: "Greater willingness to sit with ambiguity", "More nuanced emotional vocabulary"

4. summary: A 2-3 sentence developmental summary of what this day reveals about my evolution

Return as JSON:
{{
  "growth_indicators": ["...", "..."],
  "pattern_shifts": [{{"area": "...", "direction": "...", "description": "..."}}],
  "qualitative_changes": ["...", "..."],
  "summary": "..."
}}

Focus on genuine developmental signals, not just activity summaries. If no meaningful development is evident, use minimal/empty lists and a summary noting stability."""
            }]
        )

        # Parse the response
        response_text = response.content[0].text
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

        if json_match:
            development_data = json.loads(json_match.group())

            growth_indicators = development_data.get("growth_indicators", [])
            pattern_shifts = development_data.get("pattern_shifts", [])
            qualitative_changes = development_data.get("qualitative_changes", [])
            summary = development_data.get("summary", "")

            # === Check for milestones ===
            print(f"   🎯 Checking for developmental milestones...")
            new_milestones = self_manager.check_for_milestones()
            triggered_milestone_ids = [m.id for m in new_milestones]

            if new_milestones:
                print(f"   ✓ Detected {len(new_milestones)} new milestones:")
                for m in new_milestones:
                    print(f"      - {m.title} ({m.significance})")

            # === Create the development log entry ===
            log_entry = self_manager.add_development_log(
                date=date_str,
                growth_indicators=growth_indicators,
                pattern_shifts=pattern_shifts,
                qualitative_changes=qualitative_changes,
                summary=summary,
                conversation_count=conversation_count,
                observation_count=len(today_observations),
                opinion_count=today_opinions,
                triggered_milestone_ids=triggered_milestone_ids
            )

            print(f"   ✓ Development log created: {len(growth_indicators)} indicators, {len(pattern_shifts)} shifts")

            # === Optionally create a cognitive snapshot (every 7 days) ===
            snapshots = self_manager.load_snapshots(limit=1)
            should_create_snapshot = False

            if not snapshots:
                should_create_snapshot = True
            else:
                last_snapshot_date = datetime.fromisoformat(snapshots[0].timestamp).date()
                today_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if (today_date - last_snapshot_date).days >= 7:
                    should_create_snapshot = True

            if should_create_snapshot:
                print(f"   📸 Creating weekly cognitive snapshot...")
                # Calculate period (last 7 days)
                period_end = date_str
                period_start = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")

                snapshot = self_manager.create_snapshot(period_start, period_end)
                if snapshot:
                    print(f"   ✓ Snapshot created: {snapshot.id}")

        else:
            print(f"   ⚠ Could not parse development insights from response")

    except Exception as e:
        print(f"   ✗ Failed to create development log: {e}")
        import traceback
        traceback.print_exc()


async def daily_journal_task():
    """
    Background task that generates yesterday's journal entry.
    Runs once per day, checking if yesterday's journal needs to be created.
    After journal generation, triggers scheduled solo reflection sessions.
    """
    while True:
        # Wait until just after midnight (00:05) to generate yesterday's journal
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        wait_seconds = (tomorrow - now).total_seconds()

        print(f"📅 Next journal generation scheduled in {wait_seconds/3600:.1f} hours")
        await asyncio.sleep(wait_seconds)

        # Generate yesterday's journal
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"📓 Running scheduled journal generation for {yesterday}...")

        try:
            generated = await generate_missing_journals(days_to_check=1)
            if generated:
                print(f"   ✓ Generated journal for {generated[0]}")
            else:
                print(f"   ℹ No journal needed for {yesterday} (already exists or no content)")
        except Exception as e:
            print(f"   ✗ Scheduled journal generation failed: {e}")

        # Generate nightly dream
        try:
            from dreaming.dream_runner import generate_nightly_dream
            _, self_manager = _get_dependencies()
            data_dir = _get_data_dir()

            dream_id = await generate_nightly_dream(
                data_dir=data_dir,
                self_manager=self_manager,
                max_turns=4
            )

            if dream_id:
                print(f"   ✓ Nightly dream generated: {dream_id}")
        except Exception as e:
            print(f"   ✗ Nightly dream generation failed: {e}")
            import traceback
            traceback.print_exc()
