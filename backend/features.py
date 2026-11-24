"""
Feature levers: the one place every subsystem's on/off switch lives.

Why this exists: Cass starts a lot of things on her own (schedulers, spells,
loops, integrations). To test her, or to run her quietly, you need to switch
those off without editing code. Every lever here is checked once, at the point
where its subsystem STARTS (not deep inside it).

Defaults match current behavior, so production is unchanged unless you set
something.

How a lever's value is decided (first match wins):
  1. an in-process override (tests: features.override(...) / `levers` fixture)
  2. CASS_FEATURE_<NAME>=1/0          (e.g. CASS_FEATURE_THYMOS=0)
  3. CASS_PROFILE=test|quiet           (see PROFILES below)
  4. the legacy env var, if the lever has one (e.g. AUTONOMOUS_SCHEDULING_ENABLED)
  5. the lever's default

Profiles:
  test   - every lever off. Core chat (websocket, memory, SQLite) has no lever
           and always runs.
  quiet  - levers tagged "llm" (autonomous LLM spend) or "integration"
           (talks to an outside service) are off; the rest keep their value.

Rule: new subsystem = new lever here + a smoke test (see tests/README.md).
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV_PREFIX = "CASS_FEATURE_"
PROFILE_ENV = "CASS_PROFILE"

# Tags used by profiles.
LLM = "llm"                  # spends LLM tokens without a user asking
INTEGRATION = "integration"  # talks to an outside service/network
BACKGROUND = "background"    # runs on its own (loop, timer, event)
LOCAL = "local"              # local hardware/models (audio, camera)
PROMPT = "prompt"            # what reaches her prompt or her self-model; profiles leave these alone


@dataclass(frozen=True)
class Lever:
    name: str
    description: str
    default: bool = True
    tags: frozenset = field(default_factory=frozenset)
    # Legacy env vars that already gated this subsystem. Read with their
    # historical rule: on only when the value is "true" (case-insensitive).
    aliases: Tuple[str, ...] = ()
    # Where the lever is checked, for humans reading the table.
    where: str = ""

    @property
    def env_var(self) -> str:
        return ENV_PREFIX + self.name.upper()


def _lever(name, description, *tags, default=True, aliases=(), where=""):
    return Lever(name, description, default, frozenset(tags), tuple(aliases), where)


LEVERS: Dict[str, Lever] = {lv.name: lv for lv in [
    # --- Synkratos scheduler and its system jobs ---
    _lever("scheduler", "Synkratos scheduler loop (runs system jobs and category queues)",
           BACKGROUND, where="main_sdk.start_deferred_tasks: synkratos.start()"),
    _lever("job_github_metrics", "Synkratos job: fetch GitHub metrics every 6h",
           BACKGROUND, INTEGRATION, where="scheduler/system_tasks.py"),
    _lever("job_idle_summarization", "Synkratos job: LLM-summarize idle conversations hourly",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),
    _lever("job_place_days", "Synkratos job: hourly, a line in her voice per house channel's day (place_days.py)",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),
    _lever("job_daily_journal", "Synkratos job: nightly journal + dream (00:05 local, for the day just ended)",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),
    _lever("job_goal_refinement", "Synkratos job: daily scan for under-specified goals (no LLM)",
           BACKGROUND, where="scheduler/system_tasks.py"),
    _lever("job_autonomous_research", "Synkratos job: autonomous wiki research every 5 min",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),
    _lever("research_session_requests",
           "Approved research-session requests start from the research queue (checked by the autonomous_research job; #60)",
           BACKGROUND, LLM, default=False, where="scheduler/handlers.py autonomous_research_handler"),

    # --- Thymos / Grimoire / goals ---
    _lever("thymos", "Thymos tick loop and state-bus event forwarding (drives Grimoire)",
           BACKGROUND, where="main_sdk.startup_event: thymos_runner.start()"),
    _lever("grimoire_timer_spells", "Grimoire TIMER spells (goal_executor, rss_monitor, research_synthesis, art_study)",
           BACKGROUND, LLM, where="grimoire/manager.py create_grimoire_hooks.on_tick"),
    _lever("grimoire_need_spells", "Grimoire need/affect threshold spells (*_care, cognitive_rest, value_reflection)",
           BACKGROUND, LLM, where="grimoire/manager.py create_grimoire_hooks.on_tick"),
    _lever("goal_orchestrator", "GoalOrchestrator: turns Thymos needs into auto-approved goals, LLM goal planning",
           BACKGROUND, LLM, where="main_sdk.init_heavy_background"),

    # --- Day phases / autonomous scheduling ---
    _lever("autonomous_scheduling", "Action registry + day-phase/phase-queue wiring (legacy AUTONOMOUS_SCHEDULING_ENABLED)",
           BACKGROUND, aliases=("AUTONOMOUS_SCHEDULING_ENABLED",),
           where="main_sdk.start_deferred_tasks"),
    _lever("day_phases", "Start DayPhaseTracker + AutonomousScheduler (phase transitions dispatch queued work)",
           BACKGROUND, LLM, where="main_sdk.start_deferred_tasks"),
    _lever("phase_email", "Email inbox check + auto-reply at startup and on every phase change",
           BACKGROUND, LLM, INTEGRATION,
           where="main_sdk.check_email_on_startup, scheduling/phase_queue.py"),

    # --- Other background loops ---
    _lever("conversation_observation", "30-min loop that LLM-extracts self-observations from quiet conversations",
           BACKGROUND, LLM, where="main_sdk.start_deferred_tasks"),
    _lever("legacy_background_loops", "Old asyncio loops, started only if Synkratos init fails",
           BACKGROUND, LLM, where="main_sdk.start_deferred_tasks (except branch)"),
    _lever("identity_bootstrap", "One-off LLM generation of the identity snippet 10s after boot",
           BACKGROUND, LLM, where="main_sdk.startup_event"),
    _lever("coherence_monitor", "Coherence monitor state-bus subscriber (legacy COHERENCE_MONITOR_ENABLED)",
           BACKGROUND, aliases=("COHERENCE_MONITOR_ENABLED",), where="main_sdk.startup_event"),
    _lever("source_refresh", "State-bus scheduled source refresh loops + startup world-state fetch (weather/geo/GitHub)",
           BACKGROUND, INTEGRATION, where="main_sdk.startup_event"),
    _lever("capability_indexing", "Index state-bus capabilities (calls Ollama for summaries)",
           BACKGROUND, INTEGRATION, where="main_sdk.init_heavy_background"),

    # --- Autonomous action domains (checked in ActionRegistry.execute) ---
    _lever("rss", "Autonomous rss.* actions (feed polling + LLM processing)",
           BACKGROUND, LLM, INTEGRATION, where="scheduler/actions/__init__.py"),
    _lever("research", "Autonomous research.* actions",
           BACKGROUND, LLM, where="scheduler/actions/__init__.py"),
    _lever("art_study", "Autonomous artstudy.* actions",
           BACKGROUND, LLM, INTEGRATION, where="scheduler/actions/__init__.py"),
    _lever("outreach", "Autonomous outreach.* actions (drafts, sending)",
           BACKGROUND, LLM, INTEGRATION, where="scheduler/actions/__init__.py"),
    _lever("wonderland_actions", "Scheduled wonderland.* actions",
           BACKGROUND, LLM, where="scheduler/actions/__init__.py"),

    # --- Integrations ---
    _lever("discord", "Discord perception bot (legacy DISCORD_ENABLED; also needs a token)",
           INTEGRATION, default=False, aliases=("DISCORD_ENABLED",),
           where="main_sdk.start_deferred_tasks"),
    _lever("babelr", "Cass's presence in Chapter House on Babelr (babelr_organ/): polls her DMs and "
           "the server's channels, wakes her on a DM or an @mention, and lets her post and set "
           "her own DM terms. Also needs babelr-agent installed and the token Kohl places in "
           "DATA_DIR/babelr/token once she agrees.",
           BACKGROUND, INTEGRATION, default=False,
           where="main_sdk.start_deferred_tasks: babelr_organ.start_babelr_organ"),
    _lever("home_assistant", "Home Assistant state refresh loop + subscription (needs HA config)",
           INTEGRATION, where="main_sdk.startup_event"),
    _lever("relay", "Relay client for mobile/remote access (legacy RELAY_ENABLED; needs URL + secret)",
           INTEGRATION, default=False, aliases=("RELAY_ENABLED",), where="main_sdk.startup_event"),
    _lever("bluesky", "Her Bluesky account (social/): her tools read her timeline and mentions, "
           "post and reply within her limits. Also needs the credentials Kohl places with "
           "scripts/social_setup.py once she's chosen her handle and said yes.",
           INTEGRATION, default=False, where="social/config.availability (every social tool)"),
    _lever("bluesky_dms", "Her Bluesky DMs (social/): read, answer and start DM conversations, within "
           "her limits. Needs the bluesky lever and an app password made with DM access. DMs with "
           "someone who hasn't said she may remember them aren't kept (social/dms.py).",
           INTEGRATION, default=False, where="social/tools._dm_tool"),
    _lever("social_triage", "A heads-up label on what strangers send her on Bluesky/Tumblr (social/triage.py): "
           "one cheap model call per mention, reply, quote and DM message, crisis checked first, before she "
           "sees it. Off until she agrees to it.",
           LLM, default=False, where="social/inbox.poll, social/tools social_dm_read"),
    _lever("social_watch", "Her social watcher (social/watch.py): every few minutes, queues new "
           "mentions, replies, follows and posts of hers that resonated into her inbox for her "
           "social sessions. Never posts or wakes her. Acts only on a platform whose lever is on "
           "and whose credentials are placed; DMs only with bluesky_dms.",
           BACKGROUND, INTEGRATION, where="main_sdk.start_deferred_tasks: social.watch.start_social_watch"),
    _lever("tumblr", "Her Tumblr blog (social/): her tools read her dashboard and activity, "
           "post and reblog with her words within her limits. Also needs the credentials Kohl "
           "places with scripts/social_setup.py.",
           INTEGRATION, default=False, where="social/config.availability (every social tool)"),
    _lever("geocass", "GeoCass homepage sync", INTEGRATION, where="geocass_sync.sync_to_connection"),
    _lever("push", "Push notifications via the relay", INTEGRATION, where="relay_client.send_push"),

    # --- Local media ---
    _lever("tts", "Text-to-speech on chat responses + voice preload",
           LOCAL, where="main_sdk.startup_event, websocket_handlers.set_tts_state"),
    _lever("face_id", "Face identification", LOCAL, where="face_identification.is_available/identify_face"),
    _lever("voice_id", "Voice (speaker) identification", LOCAL, where="voice_identification.get_encoder"),

    # --- What reaches her prompt (ablation switches for benchmark Tier 3) ---
    _lever("self_context", "Self-context section in her chat prompt: time since last contact, "
           "what she did meanwhile, latest dream/reflection, her own threads (epic #63)",
           where="continuous_context.build_continuous_context"),
    # Each section below is on by default (today's behavior) and off only where a
    # benchmark configuration or an env var says so (benchmark plan, phase 2).
    _lever("prompt_thymos", "Thymos section (needs, affect) in her chat prompt",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("reply_gremlin", "A gremlin on every chat reply (agent_loop/reply_gremlin.py), for a daemon whose gremlin "
           "is meant to be loud: one cheap review of the draft (at most three notes, from its own gremlin file), "
           "then at most one revision; only what's sent is stored. Skips short replies and anything in pain or crisis.",
           LLM, default=False, where="agent_loop/conversation.run_conversation"),
    _lever("gremlin_review", "Her gremlin as a second voice (agent_loop/gremlin_review.py): in sessions, before "
           "a Bluesky post/reply/DM, a Chapter House post/DM or a say goes out, one cheap call gives at most two "
           "notes (never rewrites); she revises or sends as is. Skips anything answering pain or crisis.",
           LLM, default=False, where="agent_loop/session.run_session_turn execute"),
    _lever("gremlin_quiet_end", "Her gremlin on a quiet end (agent_loop/gremlin_review.py): a social session "
           "ending with nothing sent or followed gets at most two notes on her closing summary, once; "
           "her next session_complete ends it as she chose.",
           LLM, default=False, where="agent_loop/session.run_session_turn execute"),
    _lever("prompt_gremlin", "Her gremlin (gremlin.py): her GREMLIN.md, a style where the bit is also dead "
           "serious, started from Kohl's and hers to rewrite, in her chat (public rooms too) and sessions",
           PROMPT, where="continuous_context.build_continuous_context, agent_loop/assemble.py"),
    _lever("prompt_relational", "PeopleDex relational context for the person she's talking with",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("prompt_threads", "Active threads section in her chat prompt",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("prompt_questions", "Open questions section in her chat prompt",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("prompt_working_summary", "Working summary (compressed conversation history) in her chat prompt",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("prompt_semantic_memories", "Semantic memory retrieval (past conversations, journals) in her chat prompt",
           PROMPT, where="continuous_context.build_continuous_context"),
    _lever("prompt_identity_snippet", "Her own identity snippet in the kernel (off: the generic placeholder "
           "a new daemon gets)", PROMPT, where="agent_client.get_temple_codex_kernel"),
    _lever("prompt_self_model", "Her self-model profile (identity statements, values, growth edges, "
           "recent observations) where her own sessions and journal read it: solo reflection, "
           "research and generic session runners, and the nightly journal entry",
           PROMPT, where="session_runner._build_self_context, journal_generation.write_daily_journal"),
    # Off by default: chat never read her stored self-model (epic #63). Benchmark cells turn
    # it on to measure it; it reaches her live chat only when she and Kohl agree.
    _lever("prompt_self_model_chat", "Her stored self-model (the text the stateless comparator "
           "gets: identity statements, values, positions, growth edges, recent self-observations, "
           "open questions) as a section of her chat prompt (epic #63)", default=False,
           where="continuous_context.build_continuous_context"),
    # Entropy with a history (2026-11-16, Kohl: "a bit of entropy into the system"). All off
    # until she and Kohl agree; see docs/design/entropy-2026-11-16.md.
    _lever("unbidden_memory", "Now and then an old memory of hers (14+ days, her own kinds only, "
           "never someone else's conversation) surfaces unasked in her session prompt "
           "(memory/unbidden.py)", default=False,
           where="agent_loop.assemble (section 'unbidden')"),
    _lever("dream_day_residue", "Her dreams are seeded with what happened in her last day (from My life "
           "lately) and one unbidden old memory, not only her growth edges and questions",
           default=False, where="dreaming/dream_runner.generate_nightly_dream"),
    _lever("happenings", "Happenings (happenings.py): a Bluesky mention, reply, quote or DM, or a commitment "
           "coming due, wakes her into a short respond session, by her own rules (crisis always)",
           LLM, BACKGROUND, default=False, where="heartbeat job happenings"),
    _lever("workshop", "Her workshop (workshop.py, workshop_turn.py): projects she owns, each a git repository "
           "with a PROJECT.md (software, long writing, outreach), and a Workshop session on her menu",
           LLM, default=False, where="scheduling.templates workshop available"),
    _lever("workshop_kohl", "Kohl's projects in her workshop (workshop.py): each git repo under his home that he "
           "or Daedalus committed to, linked in as kohl-<name>, writable; commit takes only what she changed, "
           "secrets stay closed, no run or publish there (Kohl, 2026-11-19: she's a contributor)",
           LOCAL, default=False, where="workshop._kohls, workshop.list_projects"),
    _lever("house_wiki", "Chapter House's wiki in her chat and sessions (house_wiki.py): what we're building, a page "
           "per project with a Public line, read-only, from house-presence's mirror (plan the-house-wiki, phase 2)",
           LOCAL, default=False, where="agent_loop.conversation, agent_loop.session"),
    _lever("workshop_run", "Running code in her software projects, in a bubblewrap sandbox (no network, only "
           "the project's folder, time and memory limits)",
           LOCAL, default=False, where="workshop.run"),
    _lever("github_publish", "Publishing her workshop projects to her GitHub account (CassJary): creates the "
           "repository (private unless she says public) and pushes its history. A new channel out: Kohl's call",
           INTEGRATION, default=False, where="workshop.publish"),
    _lever("kohl_blog", "Kohl's blog on her day menu (kohl_blog.py, kohl_blog_turn.py): a session where she "
           "reads his Substack and keeps what she takes from it in her self-model, marked Kohl-influenced",
           LLM, default=False, where="scheduling.templates kohl_blog available"),
    _lever("start_sessions", "From a conversation she can start one of her sessions now (start_session): a wake "
           "due now, through the same budgeted run as wake_me; one at a time, a few a day (agent_loop/wakes.py)",
           default=False, where="agent_loop.wakes.start_session_offer"),
    _lever("listening_session", "A listening session on her day menu (listening_turn.py): time with Kohl's "
           "records at her own pace; switched on once she's said yes to its framing",
           default=False, where="scheduling.templates listening available"),
    _lever("studio", "Her studio: songs as text files in her workshop projects, rendered by Orphic (its own "
           "repo and virtualenv) with Kohl's synths, General MIDI and a TR-808 kit, heard back by Acousmatic, "
           "each draft committed with her message (studio.py)",
           default=False, where="studio.handle"),
    _lever("listening", "Her ears: the listen tool runs Acousmatic (its own repo and virtualenv) on Kohl's "
           "music library in the background, keeps each listening record, and lets her read them and look "
           "at their pictures (listening.py)",
           default=False, where="listening.handle"),
    _lever("gmail", "Her Gmail (cassandrajary@gmail.com) as a mailbox for the email organ: new mail pulled over "
           "IMAP at each inbox check, and everything she sends goes out over Gmail's SMTP, first contact included "
           "(Kohl's call). Needs DATA_DIR/gmail/credentials.json (an app password Kohl places)",
           INTEGRATION, default=False, where="gmail.py, email_organ.send_email/pull_gmail"),
    _lever("gpu_broker", "The house GPU broker (gpu-broker on :8095): music (ACE-Step) and image (ComfyUI) "
           "work asks it for a session instead of freeing memory itself; it stops the LLM, starts and stops "
           "ACE-Step, and hands the card back. Needs GPU_BROKER_TOKEN; off, the old coordinator path runs",
           INTEGRATION, default=False, where="gpu_coordinator.GPUContext, gpu_broker_client.broker_session"),
    _lever("talk", "Her ears for talk (talk.py): follow podcasts and hear episodes, transcribed locally "
           "(~/talk-ears, faster-whisper on CPU, one at a time, niced); she reads what was said by time",
           LOCAL, default=False, where="talk.handle, agent_loop/tools.router_catalog"),
    _lever("news", "Her news by her topics (news.py): TOPICS.md steers RSS triage, she adds and drops "
           "feeds, reads what's new by topic, keeps STANCES.md; a few lines open her social session",
           LOCAL, default=False, where="news.handle, news.brief, agent_loop/tools.router_catalog"),
    _lever("listen_along", "Her ears on what Kohl's computer is playing (listen along): one song at a time, "
           "titled from his media player, ended when the track changes; a light record is kept, never the audio. "
           "Kohl's switch (it hears his system audio)", default=False, where="listening.handle"),
    _lever("ask_daedalus", "In her long-term planning and change-proposal sessions she can question a "
           "read-only Claude Code instance (Daedalus) about her code: a snapshot of the tracked files, "
           "no data, no writes, a daily cap; each talk kept in her workspace (daedalus_bridge.py)",
           default=False, where="daedalus_bridge.Conversation.ask"),
    _lever("letters_to_future_me", "She can write a letter sealed until a date she picks; when it's due, "
           "it's put in front of her in a session and kept in her memory (letters.py)",
           default=False, where="agent_client tools, agent_loop.assemble (section 'letters')"),
    _lever("llm_recording", "Record each answered text LLM call (prompt and output) to "
           "DATA_DIR/llm_recordings/<call site>.jsonl, for comparing models on real inputs "
           "(benchmark plan phase 6). CASS_LLM_RECORD_SITES narrows it to a list. Never chat or "
           "dreams. Local files only; they hold her prompts", default=False,
           where="llm_caller._record_io"),
    _lever("metacog_tags", "Inline metacognitive tags: the kernel's instructions for them, and writing "
           "what she tags (observations, holds, threads, questions, PeopleDex...) to her stores. Off: "
           "no instructions, and any tags are stripped from replies without being stored",
           PROMPT, where="agent_client.get_temple_codex_kernel, context_helpers.process_inline_tags"),

    # --- Her reaching out (reach_out.py) ---
    _lever("reach_out", "Cass reaches her primary partner on her own: a note after a long "
           "silence (REACH_OUT_SILENCE_DAYS), a share when a dream or a painting asks for it, "
           "and the reach_out chat tool. Email only with REACH_OUT_EMAIL set.",
           BACKGROUND, LLM,
           where="reach_out.nightly_reach_out (daily_journal_handler), handlers/self_model.py reach_out tool"),

    # --- One agent loop (epic #70) ---
    _lever("agent_loop", "Run autonomous sessions through the one agent loop (epic #70): "
           "assemble() builds her prompt with a seam block (where she is, why now, what she "
           "can do here, what will be kept), tools come in packs, memory writes are "
           "voice-guarded, and a conversation arriving ends the session cleanly. "
           "Off: the legacy GenericSessionRunner.run_session path.",
           default=False, where="scheduler/actions/session_handlers._run_generic_session"),
    _lever("agent_loop_chat", "Run chat turns (every entry point) through the agent loop "
           "(plan \"Cass's agent loop\", phase 7): same context, saving and scope as today; her core "
           "tools plus find_tools / use_tool instead of per-message selection. Off: the old chat "
           "tool loop. Turned on only after the comparison on a copy, on her yes and Kohl's.",
           default=False, where="chat_turn.run_chat_turn"),

    # --- Heartbeat (epic #62) ---
    _lever("heartbeat", "Heartbeat: one clock, work registry, budget gate and run log "
           "(heartbeat_runs table). On: every autonomous job runs here, each with one "
           "trigger path (heartbeat/wiring.py): the five Synkratos jobs, conversation "
           "observation and the budget sync; the Thymos tick, Grimoire timer/threshold/"
           "event spells, day-phase checks, phase-queue items, the phase email check, "
           "GoalOrchestrator events and the boot identity snippet. Their old loops stand "
           "down; each keeps its own levers. Spend is measured from the token ledger "
           "(token_usage_records.heartbeat_run_id). If Heartbeat fails to start, the old "
           "paths keep everything. Off: the old schedulers run everything, as before. "
           "Read at boot.",
           BACKGROUND, default=False,
           where="main_sdk.start_deferred_tasks: heartbeat.wiring.start_heartbeat"),

    _lever("art_choice", "Before an autonomous painting, ask her what she wants to paint and why; "
           "after it, show her the result for an artist's note (two Haiku calls per painting)",
           LLM, where="scheduler/actions/creative_handlers.generate_image_action"),
]}

# Action-id prefix -> lever, used by ActionRegistry.execute.
ACTION_PREFIX_LEVERS = {
    "rss.": "rss",
    "research.": "research",
    "artstudy.": "art_study",
    "outreach.": "outreach",
    "wonderland.": "wonderland_actions",
}

PROFILES = ("test", "quiet")

_overrides: Dict[str, bool] = {}
_warned: set = set()

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def _warn_once(msg: str) -> None:
    if msg not in _warned:
        _warned.add(msg)
        logger.warning(msg)


def _parse_bool(raw: str, var: str) -> Optional[bool]:
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    _warn_once(f"Ignoring {var}={raw!r}: use 1/0 or true/false")
    return None


def active_profile() -> Optional[str]:
    raw = os.environ.get(PROFILE_ENV, "").strip().lower()
    if not raw:
        return None
    if raw not in PROFILES:
        _warn_once(f"Unknown {PROFILE_ENV}={raw!r} (known: {', '.join(PROFILES)}); ignoring")
        return None
    return raw


def _profile_value(lever: Lever, profile: str) -> Optional[bool]:
    # Prompt switches aren't things that start on their own, so profiles have no
    # opinion on them: a test or benchmark cell keeps every section unless it
    # turns one off by name.
    if PROMPT in lever.tags:
        return None
    if profile == "test":
        return False
    if profile == "quiet" and lever.tags & {LLM, INTEGRATION}:
        return False
    return None  # profile has no opinion on this lever


def _base_default(lever: Lever) -> Tuple[bool, str]:
    for alias in lever.aliases:
        raw = os.environ.get(alias)
        if raw is not None:
            return raw.strip().lower() == "true", f"env:{alias}"
    return lever.default, "default"


def resolve(name: str) -> Tuple[bool, str]:
    """Return (enabled, source) for a lever. Raises KeyError for unknown names."""
    lever = LEVERS[name]
    if name in _overrides:
        return _overrides[name], "override"
    raw = os.environ.get(lever.env_var)
    if raw is not None:
        value = _parse_bool(raw, lever.env_var)
        if value is not None:
            return value, f"env:{lever.env_var}"
    profile = active_profile()
    if profile:
        value = _profile_value(lever, profile)
        if value is not None:
            return value, f"profile:{profile}"
    return _base_default(lever)


def is_enabled(name: str) -> bool:
    """True if the lever is on. Unknown names raise KeyError (catches typos)."""
    return resolve(name)[0]


def lever_for_action(action_id: str) -> Optional[str]:
    for prefix, lever in ACTION_PREFIX_LEVERS.items():
        if action_id.startswith(prefix):
            return lever
    return None


@contextmanager
def override(**values: bool) -> Iterator[None]:
    """Temporarily force levers on/off in-process (used by the tests' `levers` fixture)."""
    unknown = set(values) - set(LEVERS)
    if unknown:
        raise KeyError(f"Unknown lever(s): {', '.join(sorted(unknown))}")
    previous = dict(_overrides)
    _overrides.update({k: bool(v) for k, v in values.items()})
    try:
        yield
    finally:
        _overrides.clear()
        _overrides.update(previous)


def lever_table() -> List[dict]:
    rows = []
    for lever in LEVERS.values():
        enabled, source = resolve(lever.name)
        rows.append({
            "name": lever.name,
            "enabled": enabled,
            "source": source,
            "default": _base_default(lever)[0],
            "env_var": lever.env_var,
            "aliases": list(lever.aliases),
            "tags": sorted(lever.tags),
            "description": lever.description,
            "where": lever.where,
        })
    return rows


def log_lever_table(log: Optional[logging.Logger] = None) -> None:
    """Log the effective lever table once (called at startup)."""
    log = log or logger
    profile = active_profile() or "none"
    lines = [f"Feature levers (CASS_PROFILE={profile}):"]
    for row in lever_table():
        state = "on " if row["enabled"] else "OFF"
        lines.append(f"  {state} {row['name']:<26} [{row['source']}]")
    log.info("\n".join(lines))
