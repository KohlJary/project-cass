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
    "review_self_model", "modify_tool_access",
    "reflect_on_user", "record_user_observation", "update_user_profile",
    "review_user_observations", "view_user_model", "view_relationship_model",
    "mark_cross_session_insight", "list_cross_session_insights", "get_insight_stats",
    "remove_cross_session_insight",
    "summon_janet", "janet_feedback", "janet_stats",
    "read_file", "list_directory",
    "lookup_person",
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
    ToolPack("chapter_house", "read what's been said in Chapter House", ("babelr_read",)),
    ToolPack("workspace", "read, write, edit, list and search my workspace, a folder of my own; "
                          "my agenda (AGENDA.md) lives there and carries my threads between moments",
             WORKSPACE_TOOLS),
    ToolPack("find", "find any of my other tools by what I want to do, and use them",
             ("find_tools", "use_tool")),
    ToolPack("session", "end the session when I'm done",
             ("session_complete",)),
]}

# Packs whose tools run through tool_router (her chat handlers), and packs
# the loop answers itself; the rest are session tools (session/tools.py).
ROUTER_PACKS = frozenset({"chat_core", "work", "chapter_house"})
LOOP_PACKS = frozenset({"find", "workspace"})

# Capabilities she has elsewhere but not in any pack the loop offers yet.
# Named so a missing capability is visible rather than silently absent [C3].
NOT_YET_IN_LOOP: Tuple[Tuple[str, str], ...] = (
    ("journal", "my journal is written nightly, not from inside a session yet"),
    ("reach out", "reaching out happens in conversation or on its own schedule"),
)

# Session activity -> the activity's own packs (on top of core + memory).
ACTIVITY_PACKS: Dict[str, Tuple[str, ...]] = {
    "reflection": (),
    "meta_reflection": (),
    "growth_edge": (),
    "user_synthesis": (),
    "synthesis": ("notes",),
    "consolidation": ("notes",),
    "research": ("world", "notes"),
    "knowledge_building": ("world", "notes"),
    "curiosity": ("world", "notes"),
    "world_state": ("world",),
    "creative": ("creative",),
    "writing": ("creative", "notes"),
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
    # Her workspace, agenda included.
    "workspace_write": ("content",),
    "workspace_edit": ("new_text",),
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
    token_budget: int = 12000
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


# Generous for a 10-step session (prompt ~10k tokens a step); it's a backstop
# against a runaway turn, not a target.
SESSION_TOKEN_BUDGET = 500_000


def session_spec(activity: str, max_iterations: int = 10, *, chapter_house: bool = True,
                 promoted: Tuple[str, ...] = ()) -> TurnSpec:
    packs = (("core", "memory") + ACTIVITY_PACKS.get(activity, ()) + ("chat_core", "work")
             + (("chapter_house",) if chapter_house else ()) + ("workspace", "find", "session"))
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


def conversation_spec() -> TurnSpec:
    # Not run through the loop yet (chat isn't cut over); written down so the
    # budget rule and seam text have a home.
    return TurnSpec(
        kind="conversation",
        activity=None,
        packs=("core", "memory"),
        writes=WritePolicy(kept=(
            ("exchange", "this conversation, summarized into my working memory"),
            ("tool_writes", "anything I observe, record, or write here"),
        )),
        where="a conversation",
        model_site="chat",
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
