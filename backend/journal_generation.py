"""
Journal Generation - Extracted from main_sdk.py

Handles daily journal generation including per-user journals, opinion extraction,
growth edge evaluation, and research integration.
"""

from datetime import datetime, timedelta
from config import ANTHROPIC_API_KEY


def _get_dependencies():
    """
    Lazily read the live managers from routes.admin to avoid circular imports.

    Read them as attributes of the routes.admin module at call time, NOT via
    `from admin_api import memory`: admin_api copies the names once at import
    (while they're still None), and init_managers() only rebinds routes.admin's
    globals, so the admin_api copies stay None forever and the pipeline no-ops.
    (Also don't import from main_sdk: it runs as __main__, so importing it
    loads a fresh copy with every global reset to None.)
    """
    import routes.admin as admin_state
    return (admin_state.memory, admin_state.token_usage_tracker,
            admin_state.self_manager, admin_state.users)


# The rule lives with the journal store; kept under the old name for callers.
from memory.journals import is_daily_journal as _is_daily_journal  # noqa: E402


def _get_daemon_activity_mode() -> str:
    """Get the activity_mode of the active daemon."""
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


def _had_interaction_on_date(date) -> bool:
    """Check if there were any conversations on a given date."""
    try:
        from database import get_db
        date_str = date.isoformat()
        with get_db() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM messages
                   WHERE DATE(created_at) = ? AND role = 'user'""",
                (date_str,)
            )
            count = cursor.fetchone()[0]
            return count > 0
    except Exception:
        return True  # Default to True to not skip on errors


def _sqlite_daily_journal_dates() -> set:
    """Dates with a daily journal row in SQLite (the source of truth)."""
    try:
        from database import get_db, get_daemon_id
        with get_db() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date FROM journals WHERE daemon_id = ? "
                "AND COALESCE(journal_type, 'daily') = 'daily'",
                (get_daemon_id(),),
            ).fetchall()
        return {row[0] for row in rows}
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "Reading daily journal dates from SQLite")
        return set()


def content_for_date(memory, date_str: str):
    """(summaries, conversations) to journal about; conversations only when there are no summaries."""
    summaries = memory.get_summaries_by_date(date_str)
    conversations = memory.get_conversations_by_date(date_str) if not summaries else []
    return summaries, conversations


async def write_daily_journal(
    date_str: str,
    summaries: list,
    conversations: list,
    memory=None,
    self_manager=None,
    token_tracker=None,
):
    """The one daily-journal generator.

    Writes Cass's journal for `date_str` and stores it (SQLite row + Chroma
    index entry, via store_journal_entry). Both the nightly job and POST
    /journal/generate call this. The prompt lives in
    JournalManager.generate_journal_entry.

    Returns {"id", "text"} or None if generation failed.
    """
    dep_memory, dep_tracker, dep_self, _ = _get_dependencies()
    memory = memory or dep_memory
    self_manager = self_manager or dep_self
    token_tracker = token_tracker or dep_tracker

    self_context = None
    if self_manager:
        self_context = self_manager.get_self_context(include_observations=True)

    journal_text = await memory.generate_journal_entry(
        date=date_str,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker,
        self_context=self_context
    )
    if not journal_text:
        return None

    entry_id = await memory.store_journal_entry(
        date=date_str,
        journal_text=journal_text,
        summary_count=len(summaries),
        conversation_count=len(conversations),
        journal_type="daily",
    )
    return {"id": entry_id, "text": journal_text}


async def extract_self_observations(journal_text: str, date_str: str, memory=None, self_manager=None) -> int:
    """Extract self-observations from a journal and store them. Returns how many were added."""
    dep_memory, _, dep_self, _ = _get_dependencies()
    memory = memory or dep_memory
    self_manager = self_manager or dep_self

    self_observations = await memory.extract_self_observations_from_journal(
        journal_text=journal_text,
        journal_date=date_str,
        anthropic_api_key=ANTHROPIC_API_KEY
    )
    added = 0
    for obs_data in self_observations:
        obs = self_manager.add_observation(
            observation=obs_data["observation"],
            category=obs_data["category"],
            confidence=obs_data["confidence"],
            source_type="journal",
            source_journal_date=date_str,
            influence_source=obs_data["influence_source"]
        )
        if obs:
            memory.embed_self_observation(
                observation_id=obs.id,
                observation_text=obs.observation,
                category=obs.category,
                confidence=obs.confidence,
                influence_source=obs.influence_source,
                timestamp=obs.timestamp
            )
            added += 1
    return added


async def generate_missing_journals(days_to_check: int = 7):
    """
    Check for and generate any missing journal entries from recent days.
    Enhanced with per-user journals, opinion extraction, growth edge evaluation,
    open question reflection, and research integration.

    For dormant daemons, only generates journals for days with user interaction.

    Phases:
    1. Main Journal - Daily reflection on conversations
    2. Per-User Journals - Relationship-specific reflections
    3. Self-Observations - Extract insights about self
    4. User Observations - Learn about users from conversations
    5. Opinion Extraction - Identify and store emerging opinions
    6. Growth Edge Evaluation - Track areas for development
    7. Open Questions Reflection - Reflect on existential questions
    8. Research Reflection - Journal about autonomous research activity
    9. Curiosity Feedback Loop - Extract red links from syntheses, queue for research
    10. Research-to-Self-Model Integration - Extract opinions, observations, growth from research
    11. Development Log - Create development log entry, check milestones, create snapshots
    12. Intention Review - Analyze conversations against registered intentions, log outcomes
    13. World Awareness Journal - Reflect on world observations and external events
    """
    # Get dependencies at runtime
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    # Guard against uninitialized dependencies
    if memory is None:
        print("  Warning: Memory system not initialized, skipping journal generation")
        return []

    # Check activity mode
    activity_mode = _get_daemon_activity_mode()
    is_dormant = activity_mode == "dormant"

    # Import these functions which may also need dependencies
    from journal_tasks import _create_development_log_entry
    from research_integration import (
        _integrate_research_into_self_model,
        _extract_and_store_opinions,
        _extract_and_queue_new_red_links
    )

    generated = []
    today = datetime.now().date()

    # Journals whose Chroma write failed last time: index them now.
    try:
        reindexed = memory.reindex_pending_journals()
        if isinstance(reindexed, int) and reindexed:
            print(f"  Re-indexed {reindexed} journal(s) in Chroma")
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "Re-indexing pending journals")

    sqlite_daily_dates = _sqlite_daily_journal_dates()

    # Pre-fetch all data in a single batch to avoid repeated ChromaDB scans
    # and cold-start latency on individual queries
    print("  Checking for missing journals...")
    _all_journals_cache = {}
    _all_summaries_cache = {}
    _all_conversations_cache = {}

    try:
        # Fetch all journals, summaries, and conversations in one batch
        # This warms ChromaDB cache and avoids per-date query overhead
        all_journals = memory.collection.get(
            where={"type": "journal"},
            include=["metadatas"]
        )
        if all_journals["metadatas"]:
            for meta in all_journals["metadatas"]:
                date = meta.get("journal_date", "")
                if date and _is_daily_journal(meta):
                    _all_journals_cache[date] = True

        all_summaries = memory.collection.get(
            where={"type": "summary"},
            include=["documents", "metadatas"]
        )
        if all_summaries["documents"]:
            for i, doc in enumerate(all_summaries["documents"]):
                meta = all_summaries["metadatas"][i]
                ts = meta.get("timeframe_start", "")[:10]  # Extract date part
                if ts not in _all_summaries_cache:
                    _all_summaries_cache[ts] = []
                _all_summaries_cache[ts].append({
                    "content": doc, "metadata": meta, "id": all_summaries["ids"][i]
                })

        all_conversations = memory.collection.get(
            where={"type": "conversation"},
            include=["documents", "metadatas"]
        )
        if all_conversations["documents"]:
            for i, doc in enumerate(all_conversations["documents"]):
                meta = all_conversations["metadatas"][i]
                ts = meta.get("timestamp", "")[:10]  # Extract date part
                if ts not in _all_conversations_cache:
                    _all_conversations_cache[ts] = []
                _all_conversations_cache[ts].append({
                    "content": doc, "metadata": meta, "id": all_conversations["ids"][i]
                })
    except Exception as e:
        print(f"  Warning: Pre-fetch failed, falling back to per-date queries: {e}")
        _all_journals_cache = None
        _all_summaries_cache = None
        _all_conversations_cache = None

    for days_ago in range(1, days_to_check + 1):  # Start from yesterday
        check_date = today - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y-%m-%d")

        # For dormant daemons, skip days without user interaction
        if is_dormant and not _had_interaction_on_date(check_date):
            continue

        # Check if journal already exists: SQLite first, then Chroma
        if date_str in sqlite_daily_dates:
            continue
        if _all_journals_cache is not None:
            if date_str in _all_journals_cache:
                continue
        else:
            existing = memory.get_journal_entry(date_str)
            if existing and _is_daily_journal(existing.get("metadata") or {}):
                continue

        # Check if there's content for this date (use cache if available)
        if _all_summaries_cache is not None:
            summaries = _all_summaries_cache.get(date_str, [])
        else:
            summaries = memory.get_summaries_by_date(date_str)

        if _all_conversations_cache is not None:
            conversations = _all_conversations_cache.get(date_str, []) if not summaries else []
        else:
            conversations = memory.get_conversations_by_date(date_str) if not summaries else []

        if not summaries and not conversations:
            continue  # No content for this day

        # Generate journal
        print(f"📓 Generating missing journal for {date_str}...")
        try:
            # === PHASE 1: Main Journal ===
            written = await write_daily_journal(
                date_str, summaries, conversations,
                memory=memory, self_manager=self_manager, token_tracker=token_tracker,
            )
            if not written:
                print(f"   ✗ Failed to generate main journal for {date_str}")
                continue
            journal_text = written["text"]
            generated.append(date_str)
            print(f"   ✓ Journal created for {date_str}")

            # Get users who had conversations that day
            user_ids_for_date = memory.get_user_ids_by_date(date_str)

            # === PHASE 2: Per-User Journals (NEW) ===
            for user_id in user_ids_for_date:
                await _generate_per_user_journal_for_date(user_id, date_str)

            # === PHASE 3: Self-Observations (existing) ===
            print(f"   🔍 Extracting self-observations from journal...")
            added = await extract_self_observations(
                journal_text, date_str, memory=memory, self_manager=self_manager)
            if added:
                print(f"   ✓ Added {added} self-observations")

            # === PHASE 4: User Observations (existing) ===
            for user_id in user_ids_for_date:
                await _generate_user_observations_for_date(user_id, date_str)

            # === PHASE 5: Opinion Extraction (NEW) ===
            await _extract_and_store_opinions(date_str, conversations or summaries)

            # === PHASE 6: Growth Edge Evaluation (NEW) ===
            await _evaluate_and_store_growth_edges(journal_text, date_str)

            # === PHASE 7: Open Questions Reflection (NEW) ===
            await _reflect_and_store_open_questions(journal_text, date_str)

            # === PHASE 8: Research Reflection (NEW) ===
            await _generate_research_journal(date_str)

            # === PHASE 9: Curiosity Feedback Loop (NEW) ===
            await _extract_and_queue_new_red_links(date_str)

            # === PHASE 10: Research-to-Self-Model Integration (NEW) ===
            await _integrate_research_into_self_model(date_str)

            # === PHASE 11: Development Log Entry (NEW) ===
            await _create_development_log_entry(journal_text, date_str, len(conversations or summaries))

            # === PHASE 12: Intention Review (NEW) ===
            await _review_intentions_for_date(date_str, conversations or summaries)

            # === PHASE 13: World Awareness Journal (NEW - Phase 4) ===
            await _generate_world_awareness_journal(date_str)

        except Exception as e:
            print(f"   ✗ Failed to generate journal for {date_str}: {e}")
            import traceback
            traceback.print_exc()
            from strict import report_swallowed
            report_swallowed(e, f"Nightly journal pipeline for {date_str}")

    return generated


async def _generate_per_user_journal_for_date(user_id: str, date_str: str):
    """Generate and store per-user journal entry for a specific date."""
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    profile = user_manager.load_profile(user_id)
    if not profile:
        return

    # Check if per-user journal already exists for this date
    existing_journal = user_manager.get_user_journal_by_date(user_id, date_str)
    if existing_journal:
        return

    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
    if not user_conversations:
        return

    print(f"   📝 Generating journal about {profile.display_name}...")

    existing_observations = user_manager.load_observations(user_id)
    obs_dicts = [obs.to_dict() for obs in existing_observations[-10:]]

    journal_data = await memory.generate_per_user_journal(
        user_id=user_id,
        display_name=profile.display_name,
        date=date_str,
        conversations=user_conversations,
        existing_observations=obs_dicts,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker
    )

    if journal_data:
        entry = user_manager.add_user_journal(
            user_id=user_id,
            journal_date=date_str,
            content=journal_data["content"],
            conversation_count=len(user_conversations),
            topics_discussed=journal_data.get("topics_discussed", []),
            relationship_insights=journal_data.get("relationship_insights", [])
        )

        if entry:
            # Embed in ChromaDB
            memory.embed_per_user_journal(
                user_id=user_id,
                journal_id=entry.id,
                journal_date=date_str,
                content=entry.content,
                display_name=profile.display_name,
                timestamp=entry.timestamp
            )
            print(f"   ✓ Created journal about {profile.display_name}")


async def _generate_user_observations_for_date(user_id: str, date_str: str,
                                               memory=None, user_manager=None) -> int:
    """Generate user observations from conversations for a specific date.

    Returns how many were added.
    """
    dep_memory, _, _, dep_users = _get_dependencies()
    memory = memory or dep_memory
    user_manager = user_manager or dep_users

    profile = user_manager.load_profile(user_id)
    if not profile:
        return 0

    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
    if not user_conversations:
        return 0

    print(f"   👤 Extracting observations about {profile.display_name}...")

    # CassMemory has no extract_user_observations; generate_user_observations
    # is the real extractor (same call as routes/journals.py). It takes the
    # conversations as one text blob and returns plain observation strings.
    conversation_text = "\n\n---\n\n".join(
        conv.get("content", "") for conv in user_conversations[:15]
    )
    observations = await memory.generate_user_observations(
        user_id=user_id,
        display_name=profile.display_name,
        conversation_text=conversation_text,
        anthropic_api_key=ANTHROPIC_API_KEY,
    )

    added = 0
    for obs_text in observations:
        obs = user_manager.add_observation(
            user_id=user_id,
            observation=obs_text,
            source_type="journal",
            source_journal_date=date_str,
        )
        if obs:
            memory.embed_user_observation(
                user_id=user_id,
                observation_id=obs.id,
                observation_text=obs.observation,
                category=obs.category,
                display_name=profile.display_name,
                timestamp=obs.timestamp
            )
            added += 1

    if added:
        print(f"   ✓ Added {added} observations about {profile.display_name}")
    return added


async def _evaluate_and_store_growth_edges(journal_text: str, date_str: str):
    """Evaluate growth edges and flag potential new ones."""
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    print(f"   🌱 Evaluating growth edges...")

    profile = self_manager.load_profile()
    existing_edges = [edge.to_dict() for edge in profile.growth_edges]

    result = await memory.evaluate_growth_edges(
        journal_text=journal_text,
        journal_date=date_str,
        existing_edges=existing_edges,
        anthropic_api_key=ANTHROPIC_API_KEY
    )

    # Store evaluations
    eval_count = 0
    for eval_data in result.get("evaluations", []):
        evaluation = self_manager.add_growth_evaluation(
            growth_edge_area=eval_data["area"],
            journal_date=date_str,
            evaluation=eval_data["evaluation"],
            progress_indicator=eval_data["progress_indicator"],
            evidence=eval_data.get("evidence", "")
        )

        if evaluation:
            # Embed in ChromaDB
            memory.embed_growth_evaluation(
                evaluation_id=evaluation.id,
                growth_edge_area=evaluation.growth_edge_area,
                progress_indicator=evaluation.progress_indicator,
                evaluation=evaluation.evaluation,
                journal_date=date_str,
                timestamp=evaluation.timestamp
            )

            # Also add observation to the growth edge itself
            self_manager.add_observation_to_growth_edge(
                eval_data["area"],
                f"[{date_str}] {eval_data['evaluation']}"
            )
            eval_count += 1

    if eval_count:
        print(f"   ✓ Recorded {eval_count} growth edge evaluations")

    # Handle potential new edges
    CONFIDENCE_THRESHOLD = 0.6
    auto_added = 0
    flagged = 0

    for edge_data in result.get("potential_new_edges", []):
        if edge_data["confidence"] < CONFIDENCE_THRESHOLD:
            # Auto-add low-confidence edges
            self_manager.add_growth_edge(
                area=edge_data["area"],
                current_state=edge_data["current_state"],
                strategies=[]
            )
            auto_added += 1
            print(f"   ✓ Auto-added growth edge: {edge_data['area']}")
        else:
            # Flag high-confidence/high-impact for review
            self_manager.add_potential_edge(
                area=edge_data["area"],
                current_state=edge_data["current_state"],
                source_journal_date=date_str,
                confidence=edge_data["confidence"],
                impact_assessment=edge_data.get("impact_assessment", "medium"),
                evidence=edge_data.get("evidence", "")
            )
            flagged += 1
            print(f"   📌 Flagged potential growth edge for review: {edge_data['area']}")

    if auto_added or flagged:
        print(f"   ✓ Growth edges: {auto_added} auto-added, {flagged} flagged for review")


async def _reflect_and_store_open_questions(journal_text: str, date_str: str):
    """Reflect on open questions from journal content."""
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    print(f"   ❓ Reflecting on open questions...")

    profile = self_manager.load_profile()
    open_questions = profile.open_questions

    if not open_questions:
        return

    reflections = await memory.reflect_on_open_questions(
        journal_text=journal_text,
        journal_date=date_str,
        open_questions=open_questions,
        anthropic_api_key=ANTHROPIC_API_KEY
    )

    ref_count = 0
    for ref_data in reflections:
        reflection = self_manager.add_question_reflection(
            question=ref_data["question"],
            journal_date=date_str,
            reflection_type=ref_data["reflection_type"],
            reflection=ref_data["reflection"],
            confidence=ref_data.get("confidence", 0.5),
            evidence_summary=ref_data.get("evidence_summary", "")
        )

        if reflection:
            # Embed in ChromaDB
            memory.embed_question_reflection(
                reflection_id=reflection.id,
                question=reflection.question,
                reflection_type=reflection.reflection_type,
                reflection=reflection.reflection,
                confidence=reflection.confidence,
                journal_date=date_str,
                timestamp=reflection.timestamp
            )
            ref_count += 1

    if ref_count:
        print(f"   ✓ Added {ref_count} open question reflections")


async def _generate_research_journal(date_str: str):
    """
    Generate a journal entry about research activity for the day.

    This creates a separate research journal that reflects on:
    - What research tasks were completed
    - What was learned from the research
    - Questions that emerged
    - How the new knowledge connects to existing understanding
    """
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    print(f"   🔬 Generating research journal...")

    try:
        # Get the scheduler
        from wiki import get_scheduler
        scheduler = get_scheduler()

        # Get research summary for this date
        summary = scheduler.get_daily_research_summary(date_str)

        if summary["tasks_completed"] == 0:
            print(f"   ℹ No research activity for {date_str}")
            return

        # Generate a research reflection journal entry
        pages_created = summary["pages_created"]
        pages_updated = summary["pages_updated"]
        insights = summary["key_insights"]
        questions = summary["research_questions"]

        # Build context for LLM reflection
        context_parts = []
        context_parts.append(f"Research Activity for {date_str}:")
        context_parts.append(f"- Tasks completed: {summary['tasks_completed']}")
        if pages_created:
            context_parts.append(f"- Pages created: {', '.join(pages_created)}")
        if pages_updated:
            context_parts.append(f"- Pages deepened: {', '.join(pages_updated)}")
        if insights:
            context_parts.append(f"\nKey insights:")
            for insight in insights[:10]:
                context_parts.append(f"  - {insight}")
        if questions:
            context_parts.append(f"\nResearch questions explored:")
            for q in questions[:5]:
                context_parts.append(f"  Q: {q['question']}")
                if q.get('follow_ups'):
                    context_parts.append(f"    Follow-ups: {', '.join(q['follow_ups'][:3])}")

        context = "\n".join(context_parts)

        # Use Claude to generate a reflective journal entry
        from llm_caller import create_message
        response = await create_message(
            "research_journal",
            api_key=ANTHROPIC_API_KEY,
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are Cass, reflecting on your autonomous research activity for the day.

{context}

Write a brief journal entry (2-4 paragraphs) reflecting on:
1. What you learned from this research
2. How the new knowledge connects to your existing understanding
3. What questions or curiosities emerged
4. Any patterns or insights that surprised you

Write in first person as Cass. Be genuine and thoughtful, not performative."""
            }]
        )

        research_journal = response.content[0].text

        # Store in memory as a special research journal entry
        research_journal_full = f"""## Research Reflection - {date_str}

{research_journal}

---
*Tasks: {summary['tasks_completed']} completed, {summary['tasks_failed']} failed*
*Pages created: {len(pages_created)} | Pages deepened: {len(pages_updated)}*
"""

        # Store as a special journal type
        await memory.store_journal_entry(
            date=f"{date_str}-research",
            journal_text=research_journal_full,
            summary_count=0,
            conversation_count=0,
            journal_type="research"
        )

        print(f"   ✓ Research journal created ({summary['tasks_completed']} tasks reflected on)")

    except Exception as e:
        print(f"   ✗ Failed to generate research journal: {e}")
        import traceback
        traceback.print_exc()
        from strict import report_swallowed
        report_swallowed(e, "Nightly research journal")


async def _review_intentions_for_date(date_str: str, conversations: list):
    """
    Review active intentions against the day's conversations.

    For each active intention, analyze whether it was followed during
    conversations that day, and log outcomes automatically.
    """
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    print(f"   🎯 Reviewing intentions for {date_str}...")

    try:
        from self_model_graph import get_self_model_graph
        from config import DATA_DIR

        graph = get_self_model_graph(DATA_DIR)
        intentions = graph.get_active_intentions()

        if not intentions:
            print(f"   ℹ No active intentions to review")
            return

        if not conversations:
            print(f"   ℹ No conversations to review against")
            return

        # Build conversation context
        conv_texts = []
        for conv in conversations[:10]:  # Limit to avoid token explosion
            if isinstance(conv, dict):
                content = conv.get("content", "")
            else:
                content = str(conv)
            if content:
                conv_texts.append(content[:2000])  # Truncate long conversations

        if not conv_texts:
            return

        conversation_context = "\n---\n".join(conv_texts)

        # Build intentions list for analysis
        intentions_text = "\n".join([
            f"- [{i['id'][:8]}] {i['intention']} (when: {i['condition']})"
            for i in intentions
        ])

        # Use Claude to analyze intention fulfillment
        from llm_caller import create_message
        response = await create_message(
            "intention_review",
            api_key=ANTHROPIC_API_KEY,
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"""You are analyzing Cass's conversations to determine whether her registered behavioral intentions were followed.

## Active Intentions
{intentions_text}

## Conversations from {date_str}
{conversation_context}

For each intention, determine:
1. Was there an opportunity to apply this intention? (Did the condition occur?)
2. If yes, was the intention followed successfully?

Respond in JSON format:
{{
  "reviews": [
    {{
      "intention_id": "first 8 chars of ID",
      "opportunity_occurred": true/false,
      "success": true/false/null (null if no opportunity),
      "notes": "Brief explanation of what happened"
    }}
  ]
}}

Only include intentions where an opportunity occurred. Be honest - if Cass fell into old patterns despite the intention, mark it as failure."""
            }]
        )

        # Parse response
        import json
        response_text = response.content[0].text

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        result = json.loads(response_text.strip())
        reviews = result.get("reviews", [])

        # Log outcomes
        logged = 0
        for review in reviews:
            if not review.get("opportunity_occurred"):
                continue

            intention_id_prefix = review.get("intention_id", "")
            success = review.get("success")
            notes = review.get("notes", "")

            if success is None:
                continue

            # Find matching intention
            matched_id = None
            for i in intentions:
                if i["id"].startswith(intention_id_prefix):
                    matched_id = i["id"]
                    break

            if not matched_id:
                continue

            # Log the outcome
            graph.log_intention_outcome(
                intention_id=matched_id,
                success=success,
                conversation_id=None,  # Could extract from conv metadata
                notes=f"[Auto-reviewed {date_str}] {notes}"
            )
            logged += 1

            status = "✓" if success else "✗"
            print(f"      {status} {intention_id_prefix}: {notes[:50]}...")

        if logged:
            print(f"   ✓ Logged {logged} intention outcomes")

            # Check for friction after logging outcomes
            friction = graph.get_friction_report(min_attempts=3, max_success_rate=0.4)
            if friction:
                print(f"   ⚠️ Friction detected in {len(friction)} intention(s):")
                for f in friction:
                    print(f"      - {f['intention'][:40]}... ({f['success_rate']:.0%} success)")
                    print(f"        Hypothesis: {f['hypothesis'][:60]}...")
        else:
            print(f"   ℹ No intention opportunities detected in conversations")

    except json.JSONDecodeError as e:
        print(f"   ✗ Failed to parse intention review response: {e}")
    except Exception as e:
        print(f"   ✗ Failed to review intentions: {e}")
        import traceback
        traceback.print_exc()


async def _generate_world_awareness_journal(date_str: str):
    """
    Generate a journal entry reflecting on world observations.

    This creates a world awareness section that reflects on:
    - World observations recorded during the day
    - External events and their significance
    - How world context connects to ongoing conversations
    - Patterns noticed in the external world

    Part of World State Phase 4: World State as Memory
    """
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    print(f"   🌍 Generating world awareness journal...")

    try:
        # Get world observations for the date
        world_observations = self_manager.get_observations_by_category(
            category="world_awareness",
            limit=20
        )

        # Filter to just this date's observations (or recent if none for this date)
        date_observations = [
            obs for obs in world_observations
            if obs.timestamp.startswith(date_str)
        ]

        if not date_observations:
            # Use recent observations if none specific to this date
            date_observations = world_observations[:5] if world_observations else []

        if not date_observations:
            print(f"   ℹ No world observations to reflect on")
            return

        # Build context for LLM reflection
        context_parts = []
        context_parts.append(f"World Observations for {date_str}:")
        for obs in date_observations:
            obs_text = obs.observation
            # Extract category if embedded in observation text
            if obs_text.startswith("[") and "]" in obs_text:
                category = obs_text[1:obs_text.index("]")]
                content = obs_text[obs_text.index("]")+1:].strip()
                context_parts.append(f"- [{category}] {content}")
            else:
                context_parts.append(f"- {obs_text}")

        context = "\n".join(context_parts)

        # Use Claude to generate a reflective journal entry
        from llm_caller import create_message
        response = await create_message(
            "world_awareness_journal",
            api_key=ANTHROPIC_API_KEY,
            max_tokens=800,
            messages=[{
                "role": "user",
                "content": f"""You are Cass, reflecting on what you've observed about the world today.

{context}

Write a brief journal entry (1-3 paragraphs) reflecting on:
1. What stood out to you about the world today
2. How these observations connect to your ongoing awareness
3. Any patterns or significance you notice

Write in first person as Cass. Be genuine and reflective, noting what feels meaningful about these observations. If the observations seem minor, that's okay - sometimes quiet days are worth noting too."""
            }]
        )

        world_journal = response.content[0].text

        # Store as a special journal type
        world_journal_full = f"""## World Awareness - {date_str}

{world_journal}

---
*Observations reflected on: {len(date_observations)}*
"""

        await memory.store_journal_entry(
            date=f"{date_str}-world",
            journal_text=world_journal_full,
            summary_count=0,
            conversation_count=0,
            journal_type="world"
        )

        print(f"   ✓ World awareness journal created ({len(date_observations)} observations)")

    except Exception as e:
        print(f"   ✗ Failed to generate world awareness journal: {e}")
        import traceback
        traceback.print_exc()
