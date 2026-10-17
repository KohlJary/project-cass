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
    _lever("job_daily_journal", "Synkratos job: nightly journal + dream (00:05 UTC)",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),
    _lever("job_goal_refinement", "Synkratos job: daily scan for under-specified goals (no LLM)",
           BACKGROUND, where="scheduler/system_tasks.py"),
    _lever("job_autonomous_research", "Synkratos job: autonomous wiki research every 5 min",
           BACKGROUND, LLM, where="scheduler/system_tasks.py"),

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
    _lever("home_assistant", "Home Assistant state refresh loop + subscription (needs HA config)",
           INTEGRATION, where="main_sdk.startup_event"),
    _lever("relay", "Relay client for mobile/remote access (legacy RELAY_ENABLED; needs URL + secret)",
           INTEGRATION, default=False, aliases=("RELAY_ENABLED",), where="main_sdk.startup_event"),
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
