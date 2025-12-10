"""Extracted from main_sdk.py"""


from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY, DATA_DIR
from journal_generation import generate_missing_journals, _generate_per_user_journal_for_date, _evaluate_and_store_growth_edges, _reflect_and_store_open_questions, _generate_research_journal
import asyncio
import re
import json
from datetime import datetime, timedelta

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

        journal_generated = False
        try:
            generated = await generate_missing_journals(days_to_check=1)
            if generated:
                print(f"   ✓ Generated journal for {generated[0]}")
                journal_generated = True
            else:
                print(f"   ℹ No journal needed for {yesterday} (already exists or no content)")
        except Exception as e:
            print(f"   ✗ Scheduled journal generation failed: {e}")

        # Trigger scheduled solo reflection sessions after journal generation
        if journal_generated:
            await run_scheduled_reflections(yesterday)

async def run_scheduled_reflections(journal_date: str):
    """
    Run scheduled solo reflection sessions after daily journal generation.

    Extracts themes from the journal and runs:
    - 2 themed reflections based on journal content
    - 1 unthemed open reflection
    """
    print(f"🧘 Starting scheduled solo reflections...")

    try:
        runner = get_reflection_runner()

        # Get themes from the journal we just generated
        themes = await extract_reflection_themes_from_journal(journal_date)

        sessions_run = 0

        # Run themed reflections (up to 2)
        for i, theme in enumerate(themes[:2]):
            print(f"   🧘 Starting themed reflection {i+1}: {theme[:50]}...")
            try:
                session = await runner.start_session(
                    duration_minutes=10,
                    theme=theme,
                    trigger="scheduled",
                )
                # Wait for session to complete
                if runner._current_task:
                    await runner._current_task
                sessions_run += 1
                print(f"      ✓ Completed themed reflection: {session.thought_count} thoughts")
            except Exception as e:
                print(f"      ✗ Themed reflection failed: {e}")

            # Small delay between sessions
            await asyncio.sleep(30)

        # Run one unthemed open reflection
        print(f"   🧘 Starting open reflection...")
        try:
            session = await runner.start_session(
                duration_minutes=15,
                theme=None,  # Unthemed - follow curiosity
                trigger="scheduled",
            )
            # Wait for session to complete
            if runner._current_task:
                await runner._current_task
            sessions_run += 1
            print(f"      ✓ Completed open reflection: {session.thought_count} thoughts")
        except Exception as e:
            print(f"      ✗ Open reflection failed: {e}")

        print(f"🧘 Scheduled reflections complete: {sessions_run} sessions")

    except Exception as e:
        print(f"   ✗ Scheduled reflections failed: {e}")
        import traceback
        traceback.print_exc()

async def extract_reflection_themes_from_journal(date_str: str) -> list:
    """
    Extract potential reflection themes from a journal entry.

    Looks for:
    - Questions raised in the journal
    - Growth edges mentioned
    - Patterns or tensions noted
    - New concepts encountered
    """
    themes = []

    try:
        # Load journal from memory (ChromaDB)
        journal = memory.get_journal_entry(date_str)
        if not journal:
            return ["What patterns have I noticed in recent conversations?"]

        journal_text = journal.get("content", "")

        # Use local LLM to extract themes
        from config import OLLAMA_ENABLED, OLLAMA_BASE_URL, OLLAMA_MODEL
        if not OLLAMA_ENABLED:
            return ["What emerged in today's conversations that deserves deeper thought?"]

        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"""Based on this journal entry, suggest 3 themes for solo reflection.
Each theme should be a specific question or topic that emerged from the day's experiences.
Focus on: growth edges, open questions, tensions, or new understanding.

Journal entry:
{journal_text[:2000]}

Return ONLY a JSON array of 3 theme strings, nothing else. Example:
["What does my response to X reveal about my values?", "How is my understanding of Y evolving?", "What tension do I notice between A and B?"]""",
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 256}
                }
            )
            response.raise_for_status()
            result = response.json()

            # Parse the themes from LLM response
            import re
            text = result.get("response", "")
            # Try to extract JSON array
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                themes = json.loads(match.group())
                if isinstance(themes, list):
                    themes = [t for t in themes if isinstance(t, str)]

    except Exception as e:
        print(f"   ⚠ Theme extraction failed: {e}, using defaults")

    # Fallback themes if extraction failed
    if not themes:
        themes = [
            "What patterns have I noticed in recent conversations?",
            "How are my growth edges evolving?",
        ]

    return themes
