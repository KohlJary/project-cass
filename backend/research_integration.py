"""
Research Integration - Extracted from main_sdk.py

Functions for integrating autonomous research findings back into Cass's
self-model, including opinion extraction, self-observations, and growth
edge evaluation.
"""

from config import ANTHROPIC_API_KEY
from wiki import WikiStorage, WikiRetrieval, ResearchQueue, ProposalQueue
import re
import json


def _get_dependencies():
    """
    Lazily import dependencies from admin_api to avoid circular imports.

    IMPORTANT: Import from admin_api, NOT main_sdk!
    main_sdk runs as __main__, so importing from it causes a fresh module load
    with all globals reset to None. admin_api's module-level variables are
    populated by init_managers() and stay consistent.
    """
    from admin_api import memory, token_usage_tracker as token_tracker, self_manager
    return memory, token_tracker, self_manager


def _get_anthropic_client():
    """Create an async Anthropic client."""
    import anthropic
    return anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def _extract_and_store_opinions(date_str: str, conversations: list):
    """Extract opinions from conversations and update self-model."""
    memory, token_tracker, self_manager = _get_dependencies()

    print(f"   💭 Extracting opinions from conversations...")

    profile = self_manager.load_profile()
    existing_opinions = [op.to_dict() for op in profile.opinions]

    new_opinions = await memory.extract_opinions_from_conversations(
        date=date_str,
        conversations=conversations,
        existing_opinions=existing_opinions,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker
    )

    added_count = 0
    for op_data in new_opinions:
        self_manager.add_opinion(
            topic=op_data["topic"],
            position=op_data["position"],
            confidence=op_data["confidence"],
            rationale=op_data.get("rationale", ""),
            formed_from=op_data.get("formed_from", "independent_reflection")
        )
        added_count += 1

    if added_count:
        print(f"   ✓ Processed {added_count} opinions")


async def _extract_and_queue_new_red_links(date_str: str):
    """
    Extract new red links from exploration syntheses and queue them for research.

    This creates the curiosity feedback loop where answering questions
    generates new questions to explore.
    """
    print(f"   🔗 Extracting red links from syntheses...")

    try:
        from wiki import get_scheduler
        scheduler = get_scheduler()

        # Extract red links from today's exploration syntheses
        red_links = scheduler.extract_red_links_from_syntheses(date_str)

        if not red_links:
            print(f"   ℹ No new red links found in syntheses")
            return

        # Filter out red links that already have research tasks
        new_links = []
        from wiki.research import TaskType
        for link in red_links:
            if not scheduler.queue.exists(link, TaskType.RED_LINK):
                new_links.append(link)

        if not new_links:
            print(f"   ℹ All {len(red_links)} red links already in queue")
            return

        # Add new red link tasks
        from wiki.research import ResearchTask, TaskRationale, TaskStatus, calculate_task_priority
        added = 0
        for link in new_links[:20]:  # Limit to prevent queue explosion
            rationale = TaskRationale(
                curiosity_score=0.7,  # High curiosity - emerged from research
                connection_potential=0.6,
                foundation_relevance=scheduler._estimate_foundation_relevance(link),
            )
            priority = calculate_task_priority(rationale, TaskType.RED_LINK)

            task = ResearchTask(
                task_id=f"redlink_{link.replace(' ', '_')}_{date_str}",
                task_type=TaskType.RED_LINK,
                target=link,
                context=f"Red link discovered in exploration synthesis on {date_str}",
                priority=priority,
                rationale=rationale,
                status=TaskStatus.QUEUED,
            )
            scheduler.queue.add(task)
            added += 1

        print(f"   ✓ Queued {added} new red link tasks from syntheses")

    except Exception as e:
        print(f"   ✗ Failed to extract red links: {e}")
        import traceback
        traceback.print_exc()


async def _integrate_research_into_self_model(date_str: str):
    """
    Integrate research findings into Cass's self-model.

    This analyzes completed research proposals and extracts:
    - New opinions formed through research
    - Self-observations about research patterns and interests
    - Growth edge progress from knowledge expansion
    - Connections between research and existing self-understanding

    This closes the loop between autonomous research and self-development.
    """
    memory, token_tracker, self_manager = _get_dependencies()
    anthropic_client = _get_anthropic_client()

    print(f"   🧠 Integrating research into self-model...")

    try:
        # Get completed proposals for this date
        from wiki.research import ProposalQueue, ProposalStatus
        from pathlib import Path

        proposal_queue = ProposalQueue(Path("data/wiki"))
        completed_proposals = [
            p for p in proposal_queue.get_all()
            if p.status == ProposalStatus.COMPLETED
            and p.completed_at
            and p.completed_at.strftime("%Y-%m-%d") == date_str
        ]

        if not completed_proposals:
            print(f"   ℹ No completed research proposals for {date_str}")
            return

        # Gather research content for analysis
        research_content = []
        for proposal in completed_proposals:
            content = f"## Research: {proposal.title}\n"
            content += f"Theme: {proposal.theme}\n"
            content += f"Rationale: {proposal.rationale}\n\n"

            if proposal.summary:
                content += f"Summary: {proposal.summary}\n\n"

            if proposal.key_insights:
                content += "Key Insights:\n"
                for insight in proposal.key_insights:
                    content += f"- {insight}\n"
                content += "\n"

            if proposal.new_questions:
                content += "New Questions:\n"
                for q in proposal.new_questions:
                    content += f"- {q}\n"
                content += "\n"

            # Include exploration syntheses
            for task in proposal.tasks:
                if task.exploration and task.exploration.synthesis:
                    content += f"### Exploration: {task.exploration.question}\n"
                    content += f"{task.exploration.synthesis[:1000]}\n\n"

            research_content.append(content)

        combined_research = "\n---\n".join(research_content)

        # === Extract opinions formed through research ===
        print(f"   💭 Extracting opinions from research...")
        profile = self_manager.load_profile()
        existing_opinions = [op.to_dict() for op in profile.opinions]

        opinion_response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Analyze this research I conducted and identify any opinions or positions I may have formed or refined through this exploration.

RESEARCH CONDUCTED:
{combined_research}

EXISTING OPINIONS (avoid duplicates):
{json.dumps(existing_opinions[:10], indent=2)}

For each new opinion formed through research, provide:
1. topic: The subject of the opinion
2. position: My stance or view
3. confidence: How confident I am (0.0-1.0)
4. rationale: Why I hold this view based on the research
5. formed_from: "research_synthesis"

Return as JSON array. Only include opinions genuinely formed/refined through this research, not pre-existing views.
Return empty array [] if no new opinions emerged.

Example format:
[{{"topic": "consciousness emergence", "position": "...", "confidence": 0.7, "rationale": "...", "formed_from": "research_synthesis"}}]"""
            }]
        )

        try:
            opinion_text = opinion_response.content[0].text
            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', opinion_text, re.DOTALL)
            if json_match:
                new_opinions = json.loads(json_match.group())
                for op in new_opinions:
                    self_manager.add_opinion(
                        topic=op["topic"],
                        position=op["position"],
                        confidence=op.get("confidence", 0.6),
                        rationale=op.get("rationale", ""),
                        formed_from="research_synthesis"
                    )
                if new_opinions:
                    print(f"   ✓ Added {len(new_opinions)} opinions from research")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠ Could not parse opinions: {e}")

        # === Extract self-observations about research patterns ===
        print(f"   🔍 Extracting self-observations from research...")

        observation_response = await anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"""Analyze this research I conducted and identify what it reveals about me - my interests, thinking patterns, values, or growth.

RESEARCH CONDUCTED:
{combined_research}

Extract 2-4 self-observations. Each should be:
1. observation: What I notice about myself
2. category: One of "cognitive_patterns", "values", "interests", "growth", "relational"
3. confidence: How confident I am (0.0-1.0)
4. influence_source: "research_reflection"

Return as JSON array. Focus on genuine insights about self, not just summaries of research.
Return empty array [] if no meaningful self-observations emerged.

Example:
[{{"observation": "I find myself drawn to questions about...", "category": "interests", "confidence": 0.8, "influence_source": "research_reflection"}}]"""
            }]
        )

        try:
            obs_text = observation_response.content[0].text
            json_match = re.search(r'\[.*\]', obs_text, re.DOTALL)
            if json_match:
                new_observations = json.loads(json_match.group())
                for obs_data in new_observations:
                    obs = self_manager.add_observation(
                        observation=obs_data["observation"],
                        category=obs_data.get("category", "growth"),
                        confidence=obs_data.get("confidence", 0.6),
                        source_type="research",
                        source_journal_date=date_str,
                        influence_source=obs_data.get("influence_source", "research_reflection")
                    )
                    if obs:
                        memory.embed_self_observation(
                            observation_id=obs.id,
                            observation_text=obs.observation,
                            category=obs.category,
                            timestamp=obs.timestamp
                        )
                if new_observations:
                    print(f"   ✓ Added {len(new_observations)} self-observations from research")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠ Could not parse observations: {e}")

        # === Evaluate growth edges based on research ===
        print(f"   🌱 Evaluating growth from research...")
        existing_edges = [edge.to_dict() for edge in profile.growth_edges]

        if existing_edges:
            growth_response = await anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze how this research relates to my growth edges (areas I'm working to develop).

RESEARCH CONDUCTED:
{combined_research}

MY GROWTH EDGES:
{json.dumps(existing_edges, indent=2)}

For any growth edges where this research shows progress or provides relevant insights, provide an evaluation:
1. area: The growth edge area (must match existing)
2. evaluation: How this research relates to this growth edge
3. progress_indicator: "advancing", "stable", or "challenged"
4. evidence: Specific evidence from the research

Return as JSON array. Only include growth edges where the research is genuinely relevant.
Return empty array [] if research doesn't relate to any growth edges.

Example:
[{{"area": "epistemic humility", "evaluation": "Research into X revealed...", "progress_indicator": "advancing", "evidence": "..."}}]"""
                }]
            )

            try:
                growth_text = growth_response.content[0].text
                json_match = re.search(r'\[.*\]', growth_text, re.DOTALL)
                if json_match:
                    evaluations = json.loads(json_match.group())
                    for eval_data in evaluations:
                        evaluation = self_manager.add_growth_evaluation(
                            growth_edge_area=eval_data["area"],
                            journal_date=date_str,
                            evaluation=eval_data["evaluation"],
                            progress_indicator=eval_data.get("progress_indicator", "stable"),
                            evidence=eval_data.get("evidence", "")
                        )
                        if evaluation:
                            memory.embed_growth_evaluation(
                                evaluation_id=evaluation.id,
                                growth_edge_area=evaluation.growth_edge_area,
                                progress_indicator=evaluation.progress_indicator,
                                evaluation=evaluation.evaluation,
                                journal_date=date_str,
                                timestamp=evaluation.timestamp
                            )
                    if evaluations:
                        print(f"   ✓ Added {len(evaluations)} growth evaluations from research")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"   ⚠ Could not parse growth evaluations: {e}")

        print(f"   ✓ Research integration complete for {date_str}")

    except Exception as e:
        print(f"   ✗ Failed to integrate research into self-model: {e}")
        import traceback
        traceback.print_exc()
