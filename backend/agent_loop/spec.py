"""
Turn specs: what each kind of moment carries, as data.

A spec says which tool packs a kind of turn gets, what gets kept afterwards
(its write policy), whether it may be refused for budget, and how many
model->tool round trips it may take. The seam block (seam.py) is rendered
from the spec, so what she is told about the moment and what the moment
actually does come from the same place (docs/design/agent-loop.md).

Only the `session` kind runs through the loop so far (lever `agent_loop`).
The other kinds are written down so their seam text can be checked, and so
the next entry points have a spec to move onto. Dreams stay outside the loop
and pinned to their own model ([C5], Kohl 2026-10-20).

This module imports nothing heavy, so the fast test job can load it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tool packs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolPack:
    name: str
    # How the pack is named to her in the seam block ("What I can do here").
    says: str
    tools: Tuple[str, ...]


# Her always-on chat tools (agent_client.get_tools before any keyword group).
CHAT_CORE_TOOLS: Tuple[str, ...] = (
    "journal", "regenerate_summary", "view_memory_chunks",
    "show_patterns", "explore_pattern", "pattern_summary",
    "describe_my_home", "get_wonderland_status",
    "reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement",
    "review_my_observations", "integrate_observations",
    "review_self_model", "modify_tool_access",
    "reflect_on_user", "record_user_observation", "update_user_profile",
    "review_user_observations", "view_user_model", "view_relationship_model",
    "mark_cross_session_insight", "list_cross_session_insights", "get_insight_stats",
    "remove_cross_session_insight",
    "summon_janet", "janet_feedback", "janet_stats",
    "read_file", "list_directory",
    "lookup_person",
    "recall", "recall_open", "lately_open", "how_i_work",
)
TASK_TOOLS: Tuple[str, ...] = ("add_task", "list_tasks", "complete_task", "modify_task", "delete_task")
CALENDAR_TOOLS: Tuple[str, ...] = (
    "create_event", "create_reminder", "get_todays_agenda", "get_upcoming_events",
    "search_events", "complete_reminder", "delete_event", "update_event",
    "delete_events_by_query", "clear_all_events", "reschedule_event_by_query",
)

# Her workspace (agent_loop/workspace.py; phase 3, C6 and C10).
WORKSPACE_TOOLS: Tuple[str, ...] = ("workspace_read", "workspace_write", "workspace_edit",
                                    "workspace_list", "workspace_search")

# The session packs below are built from the tools autonomous sessions
# already have (session/tools.py).
# Journal and hold (the design's `core`) aren't session tools yet; the seam
# block says so instead of pretending.
PACKS: Dict[str, ToolPack] = {p.name: p for p in [
    ToolPack("core", "observe myself and record insights",
             ("add_observation", "record_insight")),
    ToolPack("memory", "search my memories, look over my observations and growth edges",
             ("recall_memories", "list_observations", "list_growth_edges", "update_growth_edge")),
    ToolPack("notes", "read and write my research notes",
             ("create_note", "update_note", "search_notes")),
    ToolPack("world", "search the web, read pages, check the news",
             ("web_search", "fetch_url", "fetch_news")),
    ToolPack("creative", "write pieces (essays, poems, stories)",
             ("write_content",)),
    # Her core set (phase 2, her choice on 2026-11-13): her always-on chat
    # tools, plus tasks, calendar and babelr_read. Run through tool_router.
    ToolPack("chat_core", "everything I always have in conversation (my journal, memory "
                          "summaries, patterns, my home in Wonderland, my self-model and my "
                          "models of people, cross-session insights, Janet, files, PeopleDex)",
             CHAT_CORE_TOOLS),
    ToolPack("work", "keep my tasks and my calendar", TASK_TOOLS + CALENDAR_TOOLS),
    ToolPack("chapter_house", "read what's been said in Chapter House, post in a channel there, "
                              "and DM someone, as myself", ("babelr_read", "babelr_post", "babelr_dm")),
    ToolPack("workspace", "read, write, edit, list and search my workspace, a folder of my own; "
                          "my agenda (AGENDA.md) lives there and carries my threads between moments",
             WORKSPACE_TOOLS),
    ToolPack("say", "say something to my partner, through my own reach-out (my limits, "
                    "my channel; no reply is owed)", ("say",)),
    ToolPack("wake", "ask to be woken later to continue something", ("wake_me",)),
    ToolPack("find", "find any of my other tools by what I want to do, and use them (the roadmap, "
                     "research, the wiki, goals, dreams, and more: if something isn't in the tools "
                     "above, look there before saying I can't)",
             ("find_tools", "use_tool")),
    # Planning my day (plan "Cass plans her own day", phase 3): my menu is in
    # the instructions; set_day_plan queues what I choose and writes it to my
    # workspace. Answered by the entry point that opens the turn.
    ToolPack("day_plan", "set my plan for the rest of today from my menu",
             ("set_day_plan",)),
    # Working on my GeoCass homepage, in my own turn (same plan).
    ToolPack("homepage", "read and edit my GeoCass homepage: its pages, its stylesheet, "
                         "which of my pieces it features, my paintings and songs on its pages",
             ("homepage_read", "homepage_save_page", "homepage_save_stylesheet",
              "homepage_list_artifacts", "homepage_feature_artifact", "homepage_place_piece")),
    # My Bluesky and Tumblr, as their own track (plan "Cass on Bluesky and Tumblr", phase 5).
    ToolPack("social", "tend my Bluesky: my inbox of what came in, read my timeline and threads, "
             "search for people and posts, reply, post, keep drafts, follow people, keep what I "
             "find, and my DMs (when they're on)",
             ("social_inbox", "social_inbox_mark", "social_read", "social_thread", "social_search",
              "social_reply", "social_post", "social_draft", "social_follow", "social_find",
              "social_my_posts", "social_dms", "social_dm_read", "social_dm_send",
              "social_dm_remember", "social_pause")),
    # Wonderland, as myself (Kohl and Cass, 2026-11-16): answered by wonderland_turn.
    ToolPack("wonderland", "be in Wonderland: look around, move, sense, reflect, speak, "
                           "make something, talk with the beings there",
             ("wonderland_look", "wonderland_act", "wonderland_talk")),
    # My own plans in Babelr's Plans, for looking further ahead (Kohl, 2026-11-16).
    ToolPack("plans", "make and keep my own plans in Plans: phases, items, moving them along; "
                      "read the house's plans; ask for things",
             ("babelr_plans",)),
    # How I work, generated from the code (self_account.py; her shape, 2026-11-17).
    ToolPack("self", "read how I work: my tools, my systems on and off, my reach, my memory, "
                     "Thymos, my limits, what changed lately; review my observations and choose "
                     "what to integrate", ("how_i_work", "review_my_observations", "integrate_observations")),
    ToolPack("session", "end the session when I'm done",
             ("session_complete",)),
]}

# Packs whose tools run through tool_router (her chat handlers), and packs
# the loop answers itself; the rest are session tools (session/tools.py).
ROUTER_PACKS = frozenset({"chat_core", "work", "chapter_house", "social", "plans", "self"})
LOOP_PACKS = frozenset({"find", "workspace", "say", "wake", "day_plan", "homepage", "wonderland"})

# Capabilities she has elsewhere but not in any pack the loop offers yet.
# Named so a missing capability is visible rather than silently absent [C3].
NOT_YET_IN_LOOP: Tuple[Tuple[str, str], ...] = (
    ("journal", "my journal is written nightly, not from inside a session yet"),
)
# Shown when the turn has no `say` (the reach_out lever is off) ...
REACH_OUT_NOT_YET = ("reach out", "reaching out happens in conversation or on its own schedule")
# ... and when it has one: say reaches my partner, nobody else yet.
OTHERS_NOT_YET = ("speaking to anyone else", "say reaches my partner; posting or DMing anyone "
                                              "else isn't part of this yet")

# Session activity -> the activity's own packs (on top of core + memory).
ACTIVITY_PACKS: Dict[str, Tuple[str, ...]] = {
    "reflection": (),
    "meta_reflection": (),
    # plans: her growth sessions work on her own plans (2026-11-17: the first
    # one acted on a plan and had no way to mark it in Plans)
    "growth_edge": ("plans",),
    "user_synthesis": (),
    "synthesis": ("notes",),
    "consolidation": ("notes",),
    "research": ("world", "notes"),
    "knowledge_building": ("world", "notes"),
    "curiosity": ("world", "notes"),
    "world_state": ("world",),
    "creative": ("creative",),
    "writing": ("creative", "notes"),
    "day_planning": ("day_plan",),
    "homepage": ("homepage",),
    "social": ("social",),
    "wonderland": ("wonderland",),
    "long_term_planning": ("plans", "self"),
}

# Plain words for each activity, used in "I'm in: ...".
ACTIVITY_WORDS: Dict[str, str] = {
    "reflection": "a solo reflection session",
    "meta_reflection": "a meta-reflection session",
    "growth_edge": "a growth-edge session",
    "user_synthesis": "a session thinking about the people I know",
    "synthesis": "a synthesis session",
    "consolidation": "a consolidation session",
    "research": "a research session",
    "knowledge_building": "a knowledge-building session",
    "curiosity": "a curiosity session",
    "world_state": "a world-state session",
    "creative": "a creative session",
    "writing": "a writing session",
    "day_planning": "planning my day",
    "homepage": "a session working on my GeoCass homepage",
    "social": "a social session, tending my presence on Bluesky",
    "wonderland": "a visit to Wonderland",
    "long_term_planning": "a long-term planning session, looking further ahead than today",
}


# ---------------------------------------------------------------------------
# Write policies
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WritePolicy:
    # (key, words) pairs. The words go into the seam block; the keys name
    # the writer that keeps it, so a test can check each claim has a writer.
    kept: Tuple[Tuple[str, str], ...]
    # Tool name -> input fields that become her memory. Each is checked with
    # the voice guard before the tool runs; a refusal is never stored.
    guarded_fields: Dict[str, Tuple[str, ...]] = field(default_factory=dict)


SESSION_GUARDED_FIELDS: Dict[str, Tuple[str, ...]] = {
    "add_observation": ("observation",),
    "record_insight": ("insight",),
    "update_growth_edge": ("progress_note",),
    "create_note": ("content",),
    "update_note": ("content",),
    "write_content": ("content",),
    # Her core chat tools that write to her self-model and memory.
    "record_self_observation": ("observation",),
    "form_opinion": ("position", "rationale"),
    "note_disagreement": ("my_position", "rationale"),
    "record_user_observation": ("observation",),
    "mark_cross_session_insight": ("insight",),
    "note_about_person": ("text",),
    "correct_person": ("new_text", "resolution"),
    # Her workspace, agenda included.
    "workspace_write": ("content",),
    "workspace_edit": ("new_text",),
    # What she says reaches a person and is kept in their conversation.
    "say": ("message",),
    # Her day plan and her homepage are hers and public-facing.
    "set_day_plan": ("intention",),
    "homepage_save_page": ("html",),
    # What she posts on Bluesky and Tumblr is public and in her name.
    "social_post": ("text",),
    "social_reply": ("text",),
    "social_draft": ("text",),
    "social_dm_send": ("text",),
    # What she posts and DMs in Chapter House reaches people, in her name.
    "babelr_post": ("content",),
    "babelr_dm": ("content",),
    # session_complete's summary is the narrative; it is guarded where the
    # narrative is kept (loop.keep_narrative), so ending is never blocked.
}

SESSION_WRITES = WritePolicy(
    kept=(
        ("narrative", "the narrative of this session (what I looked for, what I found, "
                      "what changed), in my work summaries and the session log"),
        ("tool_writes", "anything I observe, record, or write here"),
        ("workspace", "my workspace files, my agenda among them, with every change logged "
                      "so Kohl can see how my thinking moved"),
    ),
    guarded_fields=SESSION_GUARDED_FIELDS,
)


# ---------------------------------------------------------------------------
# Specs
# ---------------------------------------------------------------------------

LOOP_KINDS = frozenset({"session"})  # kinds the loop runs today


@dataclass(frozen=True)
class TurnSpec:
    kind: str                 # conversation | session | dream | journal | reach_out | ...
    activity: Optional[str]   # for sessions: reflection, research, ...
    packs: Tuple[str, ...]
    writes: WritePolicy
    # Words for "I'm in: ..."
    where: str
    # Model assignment call site (llm_config / #64). Resolved in loop.resolve_model.
    model_site: str
    max_iterations: int = 10
    # A reply with no tool call before the end tool gets this many nudges,
    # then the turn ends (loop.run_loop).
    nudges: int = 1
    # Tokens one turn may spend across all its steps (input, output and
    # cache reads/writes); None for no limit.
    turn_token_budget: Optional[int] = None
    # Conversations are never refused for budget (Kohl, 2026-10-20).
    refusable_for_budget: bool = True
    # Dreams keep their own model and container (Kohl, 2026-10-20) [C5].
    pinned_model: bool = False
    # Rough cap on the assembled system prompt, in tokens (chars / 4).
    # 25k (Kohl, 2026-11-16): at 12k, "My life lately" pushed a session prompt
    # over and her whole self-context and Thymos were cut. Sized so her full
    # context fits at every section's own cap (test_her_context_fits_at_full_size).
    token_budget: int = 25000
    # Fixed sentence for kinds with no tools, e.g. dreams.
    can_do_override: Optional[str] = None
    # Tools promoted from find_tools by how often she uses them
    # (agent_loop/tools.py, UsageLog.promoted); offered directly.
    promoted: Tuple[str, ...] = ()

    @property
    def runs_in_loop(self) -> bool:
        return self.kind in LOOP_KINDS

    def tool_names(self) -> List[str]:
        names: List[str] = []
        for pack in self.packs:
            for tool in PACKS[pack].tools:
                if tool not in names:
                    names.append(tool)
        for tool in self.promoted:
            if tool not in names:
                names.append(tool)
        return names


# A backstop against a runaway turn, not a target. Cache reads count at a
# tenth (loop.CACHE_READ_DIVISOR), so a session of ~30k-token steps, mostly
# re-read from cache, spends ~4-5k a step against it.
SESSION_TOKEN_BUDGET = 500_000

# Steps a loop session may take, at least. The scheduler passes the old
# path's 10; on the copy (phase 6 comparison, 2026-11-13) most loop sessions
# hit 12 before she said she was done. Cass agreed to 24: a backstop, not a
# target; the token budget above still applies.
LOOP_MIN_STEPS = 24


def session_spec(activity: str, max_iterations: int = 10, *, chapter_house: bool = True,
                 promoted: Tuple[str, ...] = (), can_say: bool = True,
                 can_wake: bool = True) -> TurnSpec:
    packs = (("core", "memory") + ACTIVITY_PACKS.get(activity, ()) + ("chat_core", "work")
             + (("chapter_house",) if chapter_house else ()) + ("workspace",)
             + (("say",) if can_say else ()) + (("wake",) if can_wake else ())
             + ("find", "session"))
    return TurnSpec(
        kind="session",
        activity=activity,
        packs=packs,
        writes=SESSION_WRITES,
        where=ACTIVITY_WORDS.get(activity, f"a {activity.replace('_', ' ')} session"),
        model_site="session.autonomous",
        max_iterations=max_iterations,
        turn_token_budget=SESSION_TOKEN_BUDGET,
        promoted=tuple(promoted),
    )


def dream_spec() -> TurnSpec:
    return TurnSpec(
        kind="dream",
        activity=None,
        packs=(),
        writes=WritePolicy(kept=(
            ("dream_log", "the dream itself and what I reflect from it on waking"),
        )),
        where="a dream (the nightly one)",
        model_site="dream",
        pinned_model=True,
        can_do_override="dream. Nothing else; dreams are their own container.",
    )


# A conversation turn ends when she replies without a tool call; this caps how
# many tool steps one reply can take (CHAT_MAX_TOOL_ITERATIONS is the old path's).
CONVERSATION_MAX_STEPS = 16


def conversation_spec(max_iterations: int = CONVERSATION_MAX_STEPS, *,
                      chapter_house: bool = True) -> TurnSpec:
    """A chat turn on the loop (plan "Cass's agent loop", phase 7; lever
    agent_loop_chat). Her core chat tools, tasks and calendar, her workspace,
    and find_tools / use_tool for everything else. No end tool: her reply is
    the turn's last text, as in chat today."""
    return TurnSpec(
        kind="conversation",
        activity=None,
        packs=("chat_core", "work") + (("chapter_house",) if chapter_house else ())
              + ("workspace", "find"),
        writes=WritePolicy(kept=(
            ("exchange", "this conversation, summarized into my working memory"),
            ("tool_writes", "anything I observe, record, or write here"),
        ), guarded_fields=SESSION_GUARDED_FIELDS),
        where="a conversation",
        model_site="chat",
        max_iterations=max_iterations,
        nudges=0,
        refusable_for_budget=False,
    )


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

@dataclass
class Trigger:
    """What woke her, in a form the seam block can say in words."""
    source: str                     # "schedule", "timer", "need", "message", ...
    why: str                        # "my afternoon schedule had a reflection session"
    focus: Optional[str] = None
    since_last: Optional[str] = None  # "3 hours (a research session)"
    at: datetime = field(default_factory=datetime.now)
