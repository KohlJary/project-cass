"""
Journal Generation - Extracted from main_sdk.py

Handles daily journal generation including per-user journals, opinion extraction,
growth edge evaluation, and research integration.
"""

from datetime import datetime, timedelta
from config import ANTHROPIC_API_KEY


def _get_dependencies():
    """
    Lazily import dependencies from main_sdk to avoid circular imports.
    These globals are defined in main_sdk.py and need to be accessed at runtime.
    """
    from main_sdk import memory, token_tracker, self_manager, user_manager
    return memory, token_tracker, self_manager, user_manager


async def generate_missing_journals(days_to_check: int = 7):
    """
    Check for and generate any missing journal entries from recent days.
    Enhanced with per-user journals, opinion extraction, growth edge evaluation,
    open question reflection, and research integration.

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
    """
    # Get dependencies at runtime
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    # Import these functions which may also need dependencies
    from journal_tasks import _create_development_log_entry
    from research_integration import (
        _integrate_research_into_self_model,
        _extract_and_store_opinions,
        _extract_and_queue_new_red_links
    )

    generated = []
    today = datetime.now().date()

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
                if date:
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

        # Check if journal already exists (use cache if available)
        if _all_journals_cache is not None:
            if date_str in _all_journals_cache:
                continue
        else:
            existing = memory.get_journal_entry(date_str)
            if existing:
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
            # Build self-model context for journal generation
            self_context = None
            if self_manager:
                self_context = self_manager.get_self_context(include_observations=True)

            # === PHASE 1: Main Journal (existing) ===
            journal_text = await memory.generate_journal_entry(
                date=date_str,
                anthropic_api_key=ANTHROPIC_API_KEY,
                token_tracker=token_tracker,
                self_context=self_context
            )

            if not journal_text:
                print(f"   ✗ Failed to generate main journal for {date_str}")
                continue

            await memory.store_journal_entry(
                date=date_str,
                journal_text=journal_text,
                summary_count=len(summaries),
                conversation_count=len(conversations)
            )
            generated.append(date_str)
            print(f"   ✓ Journal created for {date_str}")

            # Get users who had conversations that day
            user_ids_for_date = memory.get_user_ids_by_date(date_str)

            # === PHASE 2: Per-User Journals (NEW) ===
            for user_id in user_ids_for_date:
                await _generate_per_user_journal_for_date(user_id, date_str)

            # === PHASE 3: Self-Observations (existing) ===
            print(f"   🔍 Extracting self-observations from journal...")
            self_observations = await memory.extract_self_observations_from_journal(
                journal_text=journal_text,
                journal_date=date_str,
                anthropic_api_key=ANTHROPIC_API_KEY
            )
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
            if self_observations:
                print(f"   ✓ Added {len(self_observations)} self-observations")

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

        except Exception as e:
            print(f"   ✗ Failed to generate journal for {date_str}: {e}")
            import traceback
            traceback.print_exc()

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


async def _generate_user_observations_for_date(user_id: str, date_str: str):
    """Generate user observations from conversations for a specific date."""
    memory, token_tracker, self_manager, user_manager = _get_dependencies()

    profile = user_manager.load_profile(user_id)
    if not profile:
        return

    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
    if not user_conversations:
        return

    print(f"   👤 Extracting observations about {profile.display_name}...")

    observations = await memory.extract_user_observations(
        user_id=user_id,
        display_name=profile.display_name,
        conversations=user_conversations,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker
    )

    added = 0
    for obs_data in observations:
        obs = user_manager.add_observation(
            user_id=user_id,
            observation=obs_data["observation"],
            category=obs_data.get("category", "general"),
            confidence=obs_data.get("confidence", 0.7),
            source="journal_extraction"
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
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
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

        # Track token usage
        if token_tracker and response.usage:
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
            token_tracker.record(
                category="internal",
                operation="research_journal",
                provider="anthropic",
                model="claude-sonnet-4-20250514",
                input_tokens=response.usage.input_tokens + cache_read,
                output_tokens=response.usage.output_tokens,
                cache_read_tokens=cache_read,
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
            conversation_count=0
        )

        print(f"   ✓ Research journal created ({summary['tasks_completed']} tasks reflected on)")

    except Exception as e:
        print(f"   ✗ Failed to generate research journal: {e}")
        import traceback
        traceback.print_exc()
