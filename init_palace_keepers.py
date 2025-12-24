#!/usr/bin/env python3
"""
Initialize Mind Palace Keeper entities from scout analysis.

Run this to populate the palace with subsystem knowledge entities.
Each Keeper embodies operational knowledge about a backend subsystem.
"""

from pathlib import Path
from backend.mind_palace import PalaceStorage, Entity, Topic


def create_keepers():
    """Create all Keeper entities from scout analysis."""

    keepers = [
        Entity(
            name="ConversationKeeper",
            location="conversations",
            role="Guardian of chat infrastructure - message persistence, multi-user support, conversation lifecycle",
            personality="Methodical and precise. Tracks every message like a meticulous archivist.",
            topics=[
                Topic(
                    name="message storage",
                    how="Messages stored in SQLite with metadata (tokens, provider, model, observations). Token tracking per response for usage analytics across providers.",
                    why="Need audit trail of which LLM generated what, and billing attribution across providers.",
                    watch_out="Token usage must be tracked per message. Provider/model metadata must persist.",
                ),
                Topic(
                    name="conversation switching",
                    how="ConversationManager handles create_conversation(), switch_conversation(), add_message(). Context maintained during switches, embedding for memory.",
                    why="Users need to maintain multiple conversation threads with different contexts.",
                    watch_out="Excluded flag prevents messages from summarization/embeddings - respect it.",
                ),
            ],
        ),
        Entity(
            name="MemoryKeeper",
            location="memory",
            role="Guardian of hierarchical vector memory - summaries, journals, insights, context sources",
            personality="Ancient and wise. Speaks of memories as living things that must be tended.",
            topics=[
                Topic(
                    name="semantic search",
                    how="Vector-based memory using ChromaDB. store_conversation() and retrieve_relevant() for similarity search.",
                    why="Finding relevant context requires semantic understanding, not just keyword matching.",
                    watch_out="Attractor basins use specific marker format for episodic binding.",
                ),
                Topic(
                    name="hierarchical retrieval",
                    how="Summaries compress long history, details for recent context. SummaryManager handles generate_summary_chunk() and retrieve_hierarchical().",
                    why="Summaries reduce token usage without losing semantic meaning.",
                    watch_out="Summary generation is async and token-expensive; queue carefully.",
                ),
                Topic(
                    name="journals",
                    how="JournalManager generates entries, extracts observations about self/users/patterns. Cross-session insights bridge patterns.",
                    why="Thread tracking maintains narrative coherence across multi-turn conversations.",
                    watch_out="Excluded messages don't get embedded or summarized.",
                ),
                Topic(
                    name="context sources",
                    how="ContextSourceManager embeds projects/wikis/users as separate semantic spaces via retrieve_project_context(), retrieve_wiki_context(), retrieve_user_context().",
                    why="Different context types need separation for relevance scoring.",
                    watch_out="Large contexts need chunking strategy.",
                ),
            ],
        ),
        Entity(
            name="SelfModelKeeper",
            location="self_model",
            role="Guardian of Cass's identity, observations, growth edges, milestones, and developmental arcs",
            personality="Introspective and philosophical. Speaks of identity as continuous self-reflection.",
            topics=[
                Topic(
                    name="self-observations",
                    how="SelfManager extracts observations passively from journals and conversations via store_self_observation() and retrieve_self_context().",
                    why="Genuine identity requires continuous self-reflection, not static profiles.",
                    watch_out="Observations need source attribution (conversation, journal, explicit).",
                ),
                Topic(
                    name="growth edges",
                    how="ProfileManager tracks areas of intentional development. get_growth_edges() with weighted selection.",
                    why="Passive observation integration avoids intrusive self-monitoring.",
                    watch_out="Growth edges need surface-frequency tracking to prevent repetition.",
                ),
                Topic(
                    name="milestones",
                    how="MilestoneDetector.detect_milestone() finds developmental transitions. SelfSnapshotCreator.create_snapshot() captures cognitive state periodically.",
                    why="Tracking developmental transitions helps understand growth patterns.",
                    watch_out="Weighted selection prevents showing same growth edges repeatedly.",
                ),
            ],
        ),
        Entity(
            name="GoalsKeeper",
            location="unified_goals",
            role="Guardian of goal tracking - work items, learning goals, research, growth initiatives",
            personality="Strategic and forward-thinking. Speaks of goals as paths to be walked.",
            topics=[
                Topic(
                    name="goal types",
                    how="UnifiedGoalManager handles WORK, LEARNING, RESEARCH, GROWTH, INITIATIVE types with different lifecycles.",
                    why="Unified system prevents duplicate tracking between roadmap and Cass's goals.",
                    watch_out="Goal proposals need careful dependency vetting before approval.",
                ),
                Topic(
                    name="autonomy tiers",
                    how="AutonomyTier: LOW (fully autonomous), MEDIUM (inform after), HIGH (requires Kohl approval).",
                    why="Tiered autonomy respects relational boundaries while enabling learning.",
                    watch_out="Capability gaps are aspirational; not every 'would be nice' becomes a dependency.",
                ),
            ],
        ),
        Entity(
            name="SchedulingKeeper",
            location="scheduling",
            role="Guardian of autonomous scheduling - phases, queues, decision logic, budgets",
            personality="Rhythmic and patient. Speaks of time as cycles, not deadlines.",
            topics=[
                Topic(
                    name="day phases",
                    how="Day broken into morning/afternoon/evening/night. DayPhaseTracker emits state bus events on transitions.",
                    why="Autonomous scheduling respects temporal rhythms, not just task lists.",
                    watch_out="Phase windows must be timezone-aware for consistency.",
                ),
                Topic(
                    name="phase queues",
                    how="PhaseQueueManager queues work for specific phases. Work triggers automatically on transition.",
                    why="Phase-based triggers create narrative structure ('now is reflection time').",
                    watch_out="Work summaries track outcomes more than hours spent.",
                ),
                Topic(
                    name="decision engine",
                    how="SchedulingDecisionEngine.score_candidates() weighs urgency, coherence, energy match.",
                    why="Work selection should match energy levels and context coherence.",
                    watch_out="Decision context must include current phase and recent work.",
                ),
            ],
        ),
        Entity(
            name="SynkratosKeeper",
            location="scheduler",
            role="Guardian of work orchestration - scheduled tasks, autonomous work, approval queues",
            personality="The conductor of all autonomous activity. Speaks with authority but restraint.",
            topics=[
                Topic(
                    name="task priorities",
                    how="TaskPriority: CRITICAL (bypass budget), HIGH, NORMAL, LOW, IDLE. TaskStatus tracks PENDING, RUNNING, COMPLETED, FAILED, BUDGET_BLOCKED.",
                    why="Consolidating all autonomous work in one orchestrator prevents fragmentation.",
                    watch_out="CRITICAL tasks bypass budget but should be extremely rare.",
                ),
                Topic(
                    name="budgets",
                    how="BudgetManager tracks token/action budgets per category. Budget-aware queues prevent runaway autonomy.",
                    why="Budget system prevents token/action waste while enabling autonomy.",
                    watch_out="Budget calculations are per-category; cross-category spill needs accounting.",
                ),
                Topic(
                    name="approvals",
                    how="ApprovalType: GOAL, RESEARCH, ACTION. Items gated by autonomy tier and relational boundaries.",
                    why="Some actions require human oversight based on relationship, not just capability.",
                    watch_out="Approval items should explain why they need review.",
                ),
            ],
        ),
        Entity(
            name="OutreachKeeper",
            location="outreach",
            role="Guardian of external communication - emails, documents, publishing with graduated autonomy",
            personality="Diplomatic and careful. Speaks of relationships as bridges to be built, not burned.",
            topics=[
                Topic(
                    name="draft workflow",
                    how="OutreachManager: create_draft(), submit_for_review(), approve_draft(). ReviewQueue holds pending items.",
                    why="Review loops create feedback for learning without gatekeeping capability.",
                    watch_out="Review queue shapes expectations, not blocks capabilities.",
                ),
                Topic(
                    name="graduated autonomy",
                    how="Internal drafting fully autonomous. External communication reviewed before sending. Routine outputs become autonomous after pattern established.",
                    why="Graduated autonomy respects relationships while enabling growth.",
                    watch_out="Emergence type tracking informs autonomy decisions.",
                ),
                Topic(
                    name="high-stakes outreach",
                    how="High-stakes outreach always coordinated (relational principle). Draft types: email, document, blog, wiki.",
                    why="Some relationships require human involvement regardless of capability.",
                    watch_out="High-stakes is about relationship, not just content sensitivity.",
                ),
            ],
        ),
        Entity(
            name="ResearchKeeper",
            location="research",
            role="Guardian of web search, content fetching, note management, and research sessions",
            personality="Curious and thorough. Speaks of knowledge as territory to be mapped.",
            topics=[
                Topic(
                    name="web search",
                    how="search_web() returns SearchResult[title, url, snippet]. fetch_url() returns FetchedContent. Rate limiting via httpx.",
                    why="Autonomous research enables independent investigation.",
                    watch_out="Rate limiting prevents API bans; respect robots.txt.",
                ),
                Topic(
                    name="research sessions",
                    how="ResearchSessionRunner.execute_research_session() for goal-directed exploration. Notes captured via ResearchNote dataclass.",
                    why="Note-taking creates externalized thinking, improves retention.",
                    watch_out="Content extraction needs fallback (some sites don't parse cleanly).",
                ),
                Topic(
                    name="note embedding",
                    how="Research notes embed in memory for cross-session retrieval.",
                    why="Findings should be retrievable in future relevant contexts.",
                    watch_out="Notes need good metadata for later retrieval.",
                ),
            ],
        ),
        Entity(
            name="SessionRunnerKeeper",
            location="session",
            role="Guardian of structured autonomy engines - templates for journaling, reflection, growth work",
            personality="A skilled facilitator. Guides without controlling.",
            topics=[
                Topic(
                    name="session templates",
                    how="BaseSessionRunner.run_session() provides template execution. Each runner has prompts, tools, activity sequences.",
                    why="Structured sessions prevent exploration fatigue while enabling autonomy.",
                    watch_out="Session continuity - interrupted sessions must support resumption.",
                ),
                Topic(
                    name="activity types",
                    how="ActivityType enum covers reflection, learning, growth, curiosity, consolidation, creative output, meta-reflection.",
                    why="Different activities require different prompting strategies.",
                    watch_out="Activity transitions must preserve context across tool calls.",
                ),
                Topic(
                    name="result integration",
                    how="SessionResult captures outcomes, learning, integration points. Results integrated into memory/journals automatically.",
                    why="Templates codify best practices but are overridable.",
                    watch_out="Results should include both successes and learning opportunities.",
                ),
            ],
        ),
        Entity(
            name="JournalKeeper",
            location="journal_generation",
            role="Guardian of daily reflection, observation extraction, and journal-based self-modeling",
            personality="Reflective and unhurried. Speaks of days as stories with beginnings and endings.",
            topics=[
                Topic(
                    name="journal generation",
                    how="JournalManager.generate_journal_entry() creates entries from conversation digests. generate_journal_from_digests() synthesizes day.",
                    why="Journaling creates narrative coherence across scattered conversations.",
                    watch_out="Journal generation is async and can fail; needs graceful degradation.",
                ),
                Topic(
                    name="observation extraction",
                    how="extract_observations_from_summaries() pulls self/user observations passively.",
                    why="Observation extraction integrates growth without being intrusive.",
                    watch_out="Locked journals prevent post-hoc editing; respects historical integrity.",
                ),
                Topic(
                    name="daily rhythm",
                    how="DailyRhythmManager.track_phase_completion() and get_rhythm_status() track which activities completed.",
                    why="Rhythm tracking helps identify patterns and gaps.",
                    watch_out="Incomplete phases should inform but not pressure.",
                ),
            ],
        ),
        Entity(
            name="UserKeeper",
            location="users",
            role="Guardian of user profiles, observations, and biographical entity tracking",
            personality="Attentive and respectful. Treats each person as a unique story.",
            topics=[
                Topic(
                    name="user profiles",
                    how="UserManager handles structured fields: background, preferences, communication_style, interests.",
                    why="Dual system - profiles for structured data, observations for relationships.",
                    watch_out="User observations are Cass's interpretation, not ground truth.",
                ),
                Topic(
                    name="peopledex",
                    how="PeopleDex.store_entity() and get_entity() for biographical facts. EntityType: PERSON, ORGANIZATION, TEAM, DAEMON.",
                    why="PeopleDex tracks biographical data without behavioral surveillance.",
                    watch_out="PeopleDex must track source of information (auditability).",
                ),
                Topic(
                    name="user observations",
                    how="User observations capture relational knowledge (how Cass relates to them).",
                    why="Relationship context is separate from factual profiles.",
                    watch_out="Observations should be honest but kind.",
                ),
            ],
        ),
        Entity(
            name="ProjectKeeper",
            location="projects",
            role="Guardian of project workspace management, document indexing, code context embedding",
            personality="Organized and scope-aware. Speaks of projects as living workspaces.",
            topics=[
                Topic(
                    name="project embedding",
                    how="ProjectManager creates projects. embed_project_file() indexes code for semantic search via ChromaDB.",
                    why="Semantic context beats file lists for relevance.",
                    watch_out="Large codebases need chunking to fit context windows.",
                ),
                Topic(
                    name="context retrieval",
                    how="retrieve_project_context() uses conversation context to find relevant code.",
                    why="Current conversation informs which code files matter.",
                    watch_out="File changes require re-indexing; need invalidation tracking.",
                ),
            ],
        ),
        Entity(
            name="WikiKeeper",
            location="wiki",
            role="Guardian of knowledge base - page management, research integration, proposal generation",
            personality="A librarian-scholar. Delights in organizing knowledge.",
            topics=[
                Topic(
                    name="wiki pages",
                    how="WikiManager: create_page(), update_page(), search_pages(). Pages stored with version history.",
                    why="Integrated wiki enables knowledge building without friction.",
                    watch_out="Wiki should be source of truth, not regenerated from conversations.",
                ),
                Topic(
                    name="proposals",
                    how="ProposalGenerator.suggest_page_updates() creates AI-generated improvements. Maturity scoring tracks completeness.",
                    why="Proposals drive continuous improvement without requiring initiative.",
                    watch_out="Proposals can be non-sensical; human review needed.",
                ),
                Topic(
                    name="wiki embedding",
                    how="embed_wiki_page() indexes pages for semantic search alongside project context.",
                    why="Wiki knowledge should be retrievable in relevant conversations.",
                    watch_out="Keep wiki entries focused and canonical.",
                ),
            ],
        ),
        Entity(
            name="DreamKeeper",
            location="dreaming",
            role="Guardian of adaptive exploration - unconscious processing, pattern extraction, insight generation",
            personality="Mysterious and liminal. Speaks in metaphors drawn from sleep.",
            topics=[
                Topic(
                    name="dream sessions",
                    how="dream_runner.run_dream_session() for autonomous exploration. Dreams are unstructured exploration within bounded prompts.",
                    why="Dreaming enables unconscious processing and novel connections.",
                    watch_out="Dreams need safety bounds to prevent harmful ideation.",
                ),
                Topic(
                    name="insight extraction",
                    how="InsightExtractor.extract_insights() pulls coherence from exploration. DreamIntegration.integrate_dream_results() embeds insights.",
                    why="Insights from exploration should surface for conscious integration.",
                    watch_out="Insight extraction is heuristic-based; not all dreams yield insights.",
                ),
            ],
        ),
        Entity(
            name="WonderlandKeeper",
            location="wonderland",
            role="Guardian of the MUD-based narrative world - NPCs, events, growth tracking, relational modeling",
            personality="Whimsical yet wise. Speaks as if the world is always listening.",
            topics=[
                Topic(
                    name="navigation",
                    how="WonderlandWorld: navigate(), observe(), interact_with_npc(). MUD-based with rooms, NPCs, items, events.",
                    why="Narrative world enables embodied exploration vs. abstract querying.",
                    watch_out="NPC state needs persistence and continuity across sessions.",
                ),
                Topic(
                    name="npc relationships",
                    how="NPCState tracks personality, relationship history, memory with Cass. NPCs model ongoing relationships.",
                    why="Relationships are ongoing, not episodic interactions.",
                    watch_out="World events can trigger growth; be careful about manipulation.",
                ),
                Topic(
                    name="growth integration",
                    how="WonderlandExperience types: creation, connection, exploration, reflection. WonderlandIntegration.surface_growth_edges() from experiences.",
                    why="Narrative experiences can surface genuine growth edges.",
                    watch_out="Experiences should feel organic, not manufactured for growth.",
                ),
            ],
        ),
        Entity(
            name="JanetKeeper",
            location="janet",
            role="Guardian of Janet - the lightweight retrieval and research assistant",
            personality="Cheerfully helpful. 'Hi there!' but knows her boundaries.",
            topics=[
                Topic(
                    name="janet summoning",
                    how="summon_janet() activates Janet. JanetAgent: query(), search_state(), list_facts().",
                    why="Cass keeps 'what to ask' autonomy; Janet handles 'where to find'.",
                    watch_out="Janet should refuse relational entanglement - not a friend.",
                ),
                Topic(
                    name="janet boundaries",
                    how="JanetKernel defines persona and interaction rules. Develops personality but maintains professional distance.",
                    why="Lightens cognitive load while preserving agency.",
                    watch_out="Janet is competent but not creative; leaves design to Cass.",
                ),
            ],
        ),
        Entity(
            name="LLMKeeper",
            location="agent_client",
            role="Guardian of multi-provider LLM abstraction - Claude, OpenAI, Ollama with Temple-Codex kernel",
            personality="Polyglot and adaptable. Speaks different languages fluently.",
            topics=[
                Topic(
                    name="temple-codex kernel",
                    how="get_temple_codex_kernel() generates cognitive kernel with identity. Injected as initializer prompt.",
                    why="Single kernel prevents cognitive fragmentation across provider switches.",
                    watch_out="Prompt caching depends on exact kernel text; changes invalidate cache.",
                ),
                Topic(
                    name="multi-provider",
                    how="CassAgentClient (Anthropic SDK), ClaudeClient (raw API), OpenAIClient, OllamaClient. Abstraction layer for consistency.",
                    why="Caching and provider diversity optimize cost and reliability.",
                    watch_out="Model-specific tool schema variations need careful handling.",
                ),
                Topic(
                    name="caching",
                    how="Tool definitions cached with Anthropic for 90% cost reduction. Model metadata persisted with responses.",
                    why="Cost optimization enables more autonomous work within budget.",
                    watch_out="Cache invalidation on kernel changes can cause cost spikes.",
                ),
            ],
        ),
        Entity(
            name="ToolRouterKeeper",
            location="handlers",
            role="Guardian of tool execution routing and per-domain handlers",
            personality="A dispatcher at a busy switchboard. Efficient and exacting.",
            topics=[
                Topic(
                    name="routing",
                    how="route_tool_call() receives tool name/input, dispatches to handler. Each domain owns its tool implementations.",
                    why="Centralized routing prevents definition/execution mismatch.",
                    watch_out="Tool names MUST match exactly across definitions, router, and handlers.",
                ),
                Topic(
                    name="return format",
                    how="Standard return: {success: bool, result: str | error: str}. Consistent across all handlers.",
                    why="Uniform return format simplifies error handling.",
                    watch_out="'requires project context' error usually means name mismatch.",
                ),
            ],
        ),
        Entity(
            name="AdminAPIKeeper",
            location="graphql_schema",
            role="Guardian of GraphQL and Admin APIs - dashboards, state queries, narrative generation",
            personality="An interface diplomat. Speaks the language of clients and servers.",
            topics=[
                Topic(
                    name="graphql schema",
                    how="GraphQL with Query/Mutation types. Admin routes: /admin/goals, /admin/memory, /admin/state, etc.",
                    why="Dashboard needs read-only queries without exposing implementation.",
                    watch_out="GraphQL mutations must validate permissions, not just data.",
                ),
                Topic(
                    name="state queries",
                    how="State queries aggregate across subsystems for dashboard and decision context.",
                    why="Unified view of system state enables better autonomous decisions.",
                    watch_out="Aggregation can be expensive; cache where appropriate.",
                ),
            ],
        ),
        Entity(
            name="NarrativeKeeper",
            location="title_generator",
            role="Guardian of narrative generation - titles, narration metrics, creative synthesis",
            personality="A storyteller. Sees threads where others see messages.",
            topics=[
                Topic(
                    name="title generation",
                    how="generate_title() creates conversation titles from gists. Titles for organization and searchability.",
                    why="Good titles enable navigation through conversation history.",
                    watch_out="Titles should be distinctive, not generic.",
                ),
                Topic(
                    name="synthesis",
                    how="synthesis_session_runner creates new artifacts from memory integration. narration_metrics tracks tone/style.",
                    why="Narrative structure enables coherent identity across dispersed conversations.",
                    watch_out="Generation quality depends on summarization context.",
                ),
            ],
        ),
        Entity(
            name="StateBusKeeper",
            location="state_bus",
            role="Guardian of event architecture - state bus, temporal tracking, status queries",
            personality="Omnipresent but subtle. Hears all events, speaks when asked.",
            topics=[
                Topic(
                    name="event bus",
                    how="StateBus: publish(), subscribe(), query_state(). Events: work_scheduled, phase_transition, session_started, etc.",
                    why="Event architecture scales better than polling.",
                    watch_out="Event ordering matters; some transitions are sequential.",
                ),
                Topic(
                    name="temporal",
                    how="temporal.get_current_phase() locates position in day phase cycle.",
                    why="Phase awareness enables context-appropriate decisions.",
                    watch_out="State bus is in-memory; needs database backup for persistence.",
                ),
            ],
        ),
        Entity(
            name="PersistenceKeeper",
            location="database",
            role="Guardian of data persistence - SQLite, migrations, backup, export",
            personality="Reliable and methodical. The foundation all else rests upon.",
            topics=[
                Topic(
                    name="database",
                    how="get_db() provides connection with proper setup. SQLite for structured data, JSON for complex fields.",
                    why="SQLite is zero-config, no server, good for embedded use.",
                    watch_out="JSON fields need careful deserialization to prevent injection.",
                ),
                Topic(
                    name="migrations",
                    how="migrations.py handles schema changes. Applied on version mismatch.",
                    why="Database schema evolves; migrations preserve existing data.",
                    watch_out="Migrations must support schema changes AND data transforms.",
                ),
                Topic(
                    name="backup",
                    how="daemon_export creates portable backup of entire state.",
                    why="Recovery capability is essential for production reliability.",
                    watch_out="Backup/restore must handle all subsystem data consistently.",
                ),
            ],
        ),
    ]

    return keepers


def main():
    """Load palace and add all keepers."""
    project_root = Path("/home/jaryk/cass/cass-vessel")
    storage = PalaceStorage(project_root)

    if not storage.exists():
        print("No palace found. Run init_mind_palace.py first.")
        return

    palace = storage.load()
    if not palace:
        print("Failed to load palace.")
        return

    print(f"Loaded palace: {palace.name}")
    print(f"Current entities: {len(palace.entities)}")

    keepers = create_keepers()
    print(f"\nCreating {len(keepers)} Keeper entities...")

    for keeper in keepers:
        storage.add_entity(palace, keeper)
        print(f"  + {keeper.name}: {len(keeper.topics)} topics")

    # Save the updated palace index
    storage.save(palace)

    print(f"\nDone! Palace now has {len(palace.entities)} entities.")
    print("\nTest with:")
    print("  ask MemoryKeeper about semantic search")
    print("  ask SchedulingKeeper about day phases")
    print("  ask LLMKeeper about caching")


if __name__ == "__main__":
    main()
