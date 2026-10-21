"""
LLM Configuration System

The single place that decides which model runs each LLM call site.

Every call site has a name (e.g. "memory.summary_chunk") registered in
CALL_SITES below with a *default policy*: a function that returns exactly the
provider/model that call site used before routing existed (some depend on env
config such as OLLAMA_ENABLED or SUMMARIZER_PROVIDER, so they are evaluated per
call). An admin can set an *override* for a call site (admin API / page); the
override is stored in DATA_DIR/llm_config.json and wins over the default.
Without an override nothing changes: the default is today's model.

Calls are made through llm_caller (call_llm / create_message), which resolves
the model here and records usage in the token_usage_records ledger with the
call site name.
"""

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
import threading

logger = logging.getLogger("cass-vessel")

try:
    from config import DATA_DIR as _DATA_DIR
except Exception:  # pragma: no cover - config always importable in the app
    _DATA_DIR = Path(__file__).parent / "data"

# Overrides file. Under the default DATA_DIR (backend/data -> ../data) this is
# the same file the old code used (<repo>/data/llm_config.json).
CONFIG_PATH = Path(os.environ.get("LLM_CONFIG_PATH") or (Path(_DATA_DIR) / "llm_config.json"))

# Format 1 files (no "version" key) stored every assignment, but only the
# Grimoire call sites ever read them. Honour only those from a format-1 file so
# loading an old file cannot change which model any other subsystem runs.
_LEGACY_HONOURED = {
    "grimoire.ask_yes_no", "grimoire.choose", "grimoire.rate",
    "grimoire.generate", "grimoire.reflect",
}
CONFIG_VERSION = 2


class Provider(Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass
class ModelAssignment:
    """Assignment of a model to a call site."""
    provider: str  # "anthropic", "ollama", "openai"
    model_id: str  # e.g., "claude-haiku-4-5-20251001", "llama3.1:8b-instruct-q8_0"
    fallback_provider: Optional[str] = None
    fallback_model_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "fallback_provider": self.fallback_provider,
            "fallback_model_id": self.fallback_model_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelAssignment":
        # Saved configs can name models the API has since retired; map them on
        # read so a stored assignment never silently 404s (see RETIRED_MODELS).
        fallback = data.get("fallback_model_id")
        return cls(
            provider=data.get("provider", "anthropic"),
            model_id=current_model_id(data.get("model_id", "claude-haiku-4-5-20251001")),
            fallback_provider=data.get("fallback_provider"),
            fallback_model_id=current_model_id(fallback) if fallback else fallback,
        )


# Model IDs the Anthropic API no longer serves (404 not_found_error), mapped to
# the closest living model in the same line. Checked 2026-10-16 against
# GET /v1/models. claude-sonnet-4-20250514 began returning 404 for her nightly
# dream on 2026-06-16 (art creative sessions used it too); her API credit ran
# out from 2026-06-24, which hid the 404 until credit returned in October.
RETIRED_MODELS: dict[str, str] = {
    "claude-sonnet-4-20250514": "claude-sonnet-4-6",
    "claude-opus-4-20250514": "claude-opus-4-8",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-6",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
    "claude-3-5-haiku-latest": "claude-haiku-4-5-20251001",
    "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
}


def current_model_id(model_id: str) -> str:
    """Return a model ID the API still serves (retired IDs map to successors)."""
    return RETIRED_MODELS.get(model_id, model_id)


# ---------------------------------------------------------------------------
# Default policies: each returns exactly what a call site ran before routing.
# A policy returns None when the call site used to skip the call entirely
# (e.g. local-only work with Ollama disabled).
# ---------------------------------------------------------------------------

DefaultPolicy = Callable[[], Optional[ModelAssignment]]

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


def _cfg(name: str, fallback=None):
    import config
    return getattr(config, name, fallback)


def fixed(provider: str, model_id: str) -> DefaultPolicy:
    """Always this model."""
    def policy():
        return ModelAssignment(provider=provider, model_id=model_id)
    policy.describe = f"{provider}:{model_id}"
    return policy


def claude(model_id: str = HAIKU) -> DefaultPolicy:
    return fixed("anthropic", model_id)


def claude_internal() -> DefaultPolicy:
    """config.CLAUDE_INTERNAL_MODEL (Haiku)."""
    def policy():
        return ModelAssignment("anthropic", _cfg("CLAUDE_INTERNAL_MODEL", HAIKU))
    policy.describe = "anthropic:CLAUDE_INTERNAL_MODEL"
    return policy


def local_first(claude_attr: str = "CLAUDE_INTERNAL_MODEL", fallback: bool = True) -> DefaultPolicy:
    """Ollama (config.OLLAMA_MODEL) when OLLAMA_ENABLED, else Claude.

    With fallback=True a failed Ollama call falls back to the Claude model.
    """
    def policy():
        claude_model = _cfg(claude_attr, HAIKU)
        if _cfg("OLLAMA_ENABLED", False):
            return ModelAssignment(
                "ollama", _cfg("OLLAMA_MODEL"),
                fallback_provider="anthropic" if fallback else None,
                fallback_model_id=claude_model if fallback else None,
            )
        return ModelAssignment("anthropic", claude_model)
    policy.describe = (f"ollama:OLLAMA_MODEL if OLLAMA_ENABLED"
                       f"{' (falls back to ' + claude_attr + ')' if fallback else ''}, else anthropic:{claude_attr}")
    return policy


def local_only() -> DefaultPolicy:
    """Ollama (config.OLLAMA_MODEL) when OLLAMA_ENABLED; otherwise the call is skipped."""
    def policy():
        if _cfg("OLLAMA_ENABLED", False):
            return ModelAssignment("ollama", _cfg("OLLAMA_MODEL"))
        return None
    policy.describe = "ollama:OLLAMA_MODEL if OLLAMA_ENABLED, else skipped"
    return policy


def ollama_env() -> DefaultPolicy:
    """Ollama OLLAMA_MODEL, no OLLAMA_ENABLED check and no fallback (wiki)."""
    def policy():
        return ModelAssignment("ollama", os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0"))
    policy.describe = "ollama:OLLAMA_MODEL (no fallback)"
    return policy


def summarizer() -> DefaultPolicy:
    """config.SUMMARIZER_PROVIDER: ollama (with Haiku fallback), haiku, or sonnet."""
    def policy():
        provider = (_cfg("SUMMARIZER_PROVIDER", "haiku") or "haiku").lower()
        haiku = _cfg("SUMMARIZER_MODEL_HAIKU", HAIKU)
        if provider == "ollama" and _cfg("OLLAMA_ENABLED", False):
            return ModelAssignment("ollama", _cfg("OLLAMA_MODEL"), "anthropic", haiku)
        if provider == "haiku":
            return ModelAssignment("anthropic", haiku)
        # Anything else ran Sonnet, including "ollama" with Ollama disabled.
        return ModelAssignment("anthropic", _cfg("SUMMARIZER_MODEL_SONNET", SONNET))
    policy.describe = "SUMMARIZER_PROVIDER (ollama -> Haiku fallback, haiku, else sonnet)"
    return policy


def from_caller(note: str, typical: Optional[str] = None) -> DefaultPolicy:
    """The call site passes its own default (e.g. a constructor's model argument)."""
    def policy():
        if typical:
            provider, _, model_id = typical.partition(":")
            return ModelAssignment(provider, model_id)
        return None
    policy.describe = f"set by caller: {note}"
    policy.from_caller = True
    return policy


@dataclass
class CallSite:
    name: str
    default: DefaultPolicy
    label: str
    description: str = ""
    frequency: str = ""
    category: Optional[str] = None   # ledger category (kept from pre-routing records)
    pinned: bool = False             # admin overrides refused/ignored
    pinned_reason: str = ""
    text_only: bool = True           # False: uses tools/images; only Claude can run it
    # False: with the default policy, a fallback runs only when the first
    # provider answers with an error status, not when it can't be reached
    # (as these call sites behaved before routing).
    fallback_on_exception: bool = True
    priority: str = "medium"


def _sites(*sites: CallSite) -> dict[str, CallSite]:
    return {s.name: s for s in sites}


DREAM_PIN = "Dreams stay on their current model until Kohl decides otherwise."
INTERVIEW_PIN = "The model is the variable under study; the interview names it."
CHAT_PIN = ("Chat uses each user's model setting; routing chat through llm_config "
            "waits on the agent-loop work (#70).")

# Every LLM call site in the backend. tests/test_llm_routing.py fails if code
# calls a call site that is not listed here, or calls a model client directly.
CALL_SITES: dict[str, CallSite] = _sites(
    # --- chat ---------------------------------------------------------------
    # Listed so its spend shows next to the rest. Chat turns run on each
    # user's model setting (Settings); the chat clients record usage
    # themselves (websocket_handlers), and routing them through here waits on
    # the agent-loop work (#70).
    CallSite("chat", from_caller("each user's chat model (Settings)"), "Chat",
             "Conversation turns (CassAgentClient, OpenAIClient, OllamaClient)", "per message",
             pinned=True, pinned_reason=CHAT_PIN, text_only=False, priority="low"),

    # --- conversation helpers -------------------------------------------
    CallSite("title_generation", claude(HAIKU), "Conversation Title",
             "3-6 word title for a new conversation", "per conversation", category="internal", priority="high"),
    CallSite("agent.generate", from_caller("CassAgentClient.model (chat model)"), "Agent generate",
             "CassAgentClient.generate(), callers without their own call site", "on demand"),
    CallSite("agent.generate_simple", from_caller("CassAgentClient.model (chat model)"), "Agent generate (simple)",
             "CassAgentClient.generate_simple(), callers without their own call site", "on demand"),
    CallSite("homepage.generate", from_caller("CassAgentClient.model (chat model)"), "Homepage",
             "Homepage page/reflection generation", "on demand"),
    CallSite("genesis.generate", from_caller("CassAgentClient.model (chat model)"), "Genesis dream",
             "Genesis dream naming and profile generation", "per genesis"),
    CallSite("identity_snippet", claude(HAIKU), "Identity snippet",
             "Regenerate the identity snippet from the self-model", "on change", category="internal"),
    CallSite("reach_out.compose", claude(HAIKU), "Reach-out",
             "Cass composes an outreach message", "per reach-out"),
    CallSite("narrative.extraction", claude(HAIKU), "Narrative extraction",
             "Extract threads/questions from conversations (admin)", "on demand", category="internal"),
    CallSite("janet.summon", from_caller("JANET_MODEL env (default Haiku)", f"anthropic:{HAIKU}"), "Janet",
             "Janet retrieval assistant", "per summon", text_only=False),

    # --- Grimoire ---------------------------------------------------------
    CallSite("grimoire.ask_yes_no", claude(HAIKU), "Grimoire Yes/No",
             "Binary classification for spell conditions", "per spell", priority="high"),
    CallSite("grimoire.choose", claude(HAIKU), "Grimoire Choose",
             "Select option from list for spell branching", "per spell", priority="high"),
    CallSite("grimoire.rate", claude(HAIKU), "Grimoire Rate",
             "Score 0.0-1.0 for spell thresholds", "per spell", priority="high"),
    CallSite("grimoire.generate", claude(HAIKU), "Grimoire Generate",
             "Generate text content for spells", "per spell"),
    CallSite("grimoire.reflect", claude(HAIKU), "Grimoire Reflect",
             "Generate introspective reflection", "per spell"),

    # --- memory -----------------------------------------------------------
    CallSite("memory.summary_readiness", local_first("SUMMARIZER_MODEL_HAIKU", fallback=False), "Summary readiness",
             "Decide whether now is a good point to summarize", "per message batch"),
    CallSite("memory.summary_chunk", summarizer(), "Summary chunk",
             "Summarize a conversation segment into memory", "per segment", category="summarization", fallback_on_exception=False),
    CallSite("memory.working_summary", summarizer(), "Working summary",
             "Rebuild/update the conversation's working memory", "per segment", category="summarization", fallback_on_exception=False),
    CallSite("memory.gist", local_only(), "Message gist",
             "Short gist of a long message for retrieval", "per long message"),
    CallSite("memory.journal_summary", local_only(), "Journal summary",
             "1-2 sentence summary of a journal entry", "daily"),
    CallSite("memory.journal_entry", local_first(), "Daily journal",
             "Daily journal entry from summaries", "daily", category="internal", fallback_on_exception=False),
    CallSite("memory.observation_extraction", local_first(fallback=False), "Observation extraction",
             "Observations about users from summaries", "daily", category="internal"),
    CallSite("self_observation_extraction", local_first(), "Self Observations (journal)",
             "Self-observations from a journal entry", "daily", priority="high", fallback_on_exception=False),
    CallSite("self_observation_extraction.conversation", local_first(), "Self Observations (conversation)",
             "Self-observations from a finished conversation", "per conversation", priority="high", fallback_on_exception=False),
    CallSite("user_observation_extraction", local_first(), "User Observations",
             "Observations about a user from a journal", "per user per day", priority="high", fallback_on_exception=False),
    CallSite("per_user_journal", claude_internal(), "Per-User Journal",
             "Journal about relationship with user", "per user per day", category="internal"),
    CallSite("opinion_extraction", local_first(fallback=False), "Opinion Extraction",
             "Extract opinions from conversations", "daily", category="internal"),
    CallSite("growth_edge_evaluation", claude_internal(), "Growth Evaluation",
             "Evaluate progress on growth edges", "daily"),
    CallSite("open_question_reflection", claude_internal(), "Question Reflection",
             "Reflect on open questions", "daily"),
    CallSite("bootstrap.self_model", claude_internal(), "Self-model bootstrap",
             "One-time self-model bootstrap from journals (script)", "one-off"),

    # --- journals -----------------------------------------------------------
    CallSite("research_journal", claude_internal(), "Research Journal",
             "Daily reflection on research activity", "daily", category="internal", priority="high"),
    CallSite("world_awareness_journal", claude_internal(), "World Journal",
             "Reflection on world observations", "daily", category="internal", priority="high"),
    CallSite("intention_review", claude_internal(), "Intention Review",
             "Analyze if intentions were followed", "daily", category="internal"),
    CallSite("development_log_entry", claude_internal(), "Development Log",
             "Extract developmental insights", "daily"),
    CallSite("research_session_reflection", claude(HAIKU), "Research session reflection",
             "Reflection after a research session", "per session"),

    # --- research -----------------------------------------------------------
    CallSite("research.integration.observations", claude_internal(), "Research -> observations",
             "Self-observations from research notes", "per research"),
    CallSite("research.integration.opinions", claude_internal(), "Research -> opinions",
             "Opinions from research notes", "per research"),
    CallSite("research.integration.growth", claude_internal(), "Research -> growth edges",
             "Growth-edge evidence from research notes", "per research"),
    CallSite("rss.triage", from_caller("RSS_TRIAGE_MODEL env (default llama3.2:3b)", "ollama:llama3.2:3b"), "RSS triage",
             "Keep/drop decision for feed items", "per feed item"),
    CallSite("query_constructor", local_only(), "Query constructor",
             "Natural-language to structured query", "per query"),
    CallSite("capability.summary", from_caller("CapabilityRegistry ollama model"), "Capability summary",
             "Summary line for a capability metric", "per metric"),

    # --- planning / scheduling --------------------------------------------
    CallSite("goal_planner.subgoals", from_caller("GoalPlanner model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "Goal planning", "Break a goal into subgoals", "per goal"),
    CallSite("scheduling.plan_day", from_caller("DecisionEngine model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "Day Planning", "Plan full day's autonomous work", "daily"),
    CallSite("scheduling.decide_next_work", from_caller("DecisionEngine model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "Work Selection", "Decide which work to pursue", "per scheduling cycle"),

    # --- sessions -----------------------------------------------------------
    CallSite("session.generic", from_caller("DEFAULT_SESSION_MODEL or the session's model", f"anthropic:{HAIKU}"),
             "Autonomous sessions", "GenericSessionRunner tool loop (research, reflection, ...)", "per session turn",
             text_only=False),
    CallSite("session.legacy", from_caller("BaseSessionRunner haiku/ollama model", f"anthropic:{HAIKU}"),
             "Legacy session runner", "BaseSessionRunner tool loop", "per session turn", category="autonomous",
             text_only=False),

    # --- dreams -----------------------------------------------------------
    CallSite("dreaming.the_dreaming", claude(SONNET), "Dream Narration",
             "Generate dreamscape narration", "nightly", pinned=True, pinned_reason=DREAM_PIN, priority="low"),
    CallSite("dreaming.cass_voice", claude(SONNET), "Dream Participation",
             "Cass's responses in dreams", "nightly", pinned=True, pinned_reason=DREAM_PIN, priority="low"),
    CallSite("dreaming.insight_extraction", claude(SONNET), "Dream Insights",
             "Extract insights from dreams", "nightly", pinned=True, pinned_reason=DREAM_PIN, priority="low"),

    # --- art ----------------------------------------------------------------
    CallSite("art_choice.choose_subject", claude_internal(), "Art subject choice",
             "Cass picks what to paint", "per painting", category="internal"),
    CallSite("art_choice.see_painting", claude_internal(), "Seeing a painting",
             "Cass looks at a painting (vision)", "per painting", category="internal", text_only=False),
    CallSite("art_study.biographical_summary", claude_internal(), "Art Bio Summary",
             "Summarize artist biographical info", "per study", priority="high"),
    CallSite("art_study.observation_extraction", claude_internal(), "Art Observations",
             "Observations about an artist", "per study", priority="high"),
    CallSite("art_study.deep_analysis", claude(SONNET), "Art Deep Analysis",
             "Deep aesthetic analysis of an artwork (vision)", "per artwork", text_only=False, priority="low"),
    CallSite("art_study.artist_synthesis", claude(SONNET), "Artist synthesis",
             "Synthesize understanding of an artist", "per study", priority="low"),
    CallSite("art_study.house_style_extraction", claude_internal(), "Style Extraction",
             "Extract style elements from synthesis", "per synthesis", priority="high"),
    CallSite("art_study.house_style_generation", claude(SONNET), "House Style Gen",
             "Generate house style document", "on demand", priority="low"),
    CallSite("art_study.creative_session", claude(SONNET), "Creative Session",
             "Compose creative vision", "on demand", priority="low"),
    CallSite("art_study.house_style_vision", claude(SONNET), "House style vision",
             "Compose house-style creative vision", "on demand", priority="low"),
    CallSite("art_study.evaluate_creation", claude(SONNET), "Evaluate creation",
             "Evaluate a generated image (vision)", "per iteration", text_only=False, priority="low"),
    CallSite("art_study.plan_refinement", claude(SONNET), "Plan refinement",
             "Plan an image refinement", "per iteration", priority="low"),

    # --- Wonderland / world ----------------------------------------------
    CallSite("wonderland.decide_action", from_caller("ExplorationAgent model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "Wonderland action", "Exploration agent picks an action", "per step"),
    CallSite("wonderland.conversation_response", from_caller("ExplorationAgent model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "Wonderland reply", "Exploration agent replies to an NPC", "per step"),
    CallSite("wonderland.self_observations", claude_internal(), "Wonderland observations",
             "Self-observations from an exploration", "per exploration"),
    CallSite("wonderland.npc_response", from_caller("NPCConversationHandler model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "NPC response", "NPC dialogue", "per exchange"),
    CallSite("wonderland.npc_greeting", from_caller("NPCConversationHandler model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "NPC greeting", "NPC opening line", "per conversation"),
    CallSite("wonderland.npc_memory", from_caller("NPCConversationHandler model (CLAUDE_INTERNAL_MODEL)", f"anthropic:{HAIKU}"),
             "NPC memory", "Summarize a conversation for the NPC", "per conversation"),
    CallSite("world.content_analysis", from_caller("ContentAnalyzer model (Haiku)", f"anthropic:{HAIKU}"),
             "World content analysis", "Analyze fetched world content", "per item"),

    # --- wiki (Ollama only today; #25) -------------------------------------
    CallSite("wiki.enrich_page", ollama_env(), "Wiki enrich page", "Enrich a wiki page", "per page"),
    CallSite("wiki.research_and_create", ollama_env(), "Wiki research page", "Create a page from research", "per page"),
    CallSite("wiki.proposal_metadata", ollama_env(), "Wiki proposal metadata", "Title/summary for a proposal", "per proposal"),
    CallSite("wiki.resynthesis", ollama_env(), "Wiki resynthesis", "Resynthesize a page", "per page", category="internal"),
    CallSite("wiki.resynthesis_validation", ollama_env(), "Wiki validation", "Validate a resynthesis", "per page", category="internal"),
    CallSite("wiki.exploration_synthesis", ollama_env(), "Wiki exploration", "Synthesize an exploration", "per exploration"),
    CallSite("wiki.page_content", ollama_env(), "Wiki page content", "Generate page content", "per page"),
    CallSite("wiki.generate_page", ollama_env(), "Wiki generate page (API)", "Generate a page on request", "on demand"),
    CallSite("wiki.execute_proposal", ollama_env(), "Wiki execute proposal", "Write pages for a proposal", "on demand"),
    CallSite("wiki.proposal_summary", ollama_env(), "Wiki proposal summary", "Regenerate a proposal summary", "on demand"),

    # --- research tools ---------------------------------------------------
    CallSite("interviews.dispatch", from_caller("the interview's model"), "Model interviews",
             "Interview protocol sent to a named model", "on demand", pinned=True, pinned_reason=INTERVIEW_PIN),
)


def _assignment_for_display(site: CallSite) -> Optional[ModelAssignment]:
    try:
        return site.default()
    except Exception:
        return None


# Back-compat views (older code and the admin UI read these names).
DEFAULT_ASSIGNMENTS: dict[str, ModelAssignment] = {
    name: a for name, a in ((n, _assignment_for_display(s)) for n, s in CALL_SITES.items()) if a is not None
}
CALL_SITE_METADATA = {
    name: {
        "name": s.label,
        "description": s.description,
        "priority": s.priority,
        "frequency": s.frequency,
        "default": getattr(s.default, "describe", ""),
        "pinned": s.pinned,
        "pinned_reason": s.pinned_reason,
        "text_only": s.text_only,
    }
    for name, s in CALL_SITES.items()
}


class UnknownCallSite(KeyError):
    pass


class PinnedCallSite(ValueError):
    pass


class LLMConfigManager:
    """
    Model assignment per call site: default policy + admin overrides.

    Thread-safe singleton. Overrides are persisted to CONFIG_PATH.
    """

    _instance: Optional["LLMConfigManager"] = None
    _lock = threading.RLock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._overrides: dict[str, ModelAssignment] = {}
        self._path = CONFIG_PATH
        self._load()
        self._initialized = True

    @classmethod
    def reset_instance(cls):
        """Forget the singleton (tests, or after CONFIG_PATH changes)."""
        with cls._lock:
            cls._instance = None

    def _load(self):
        if not self._path.exists():
            return
        try:
            with open(self._path) as f:
                data = json.load(f)
            legacy = data.get("version") is None
            for call_site, assignment_data in (data.get("assignments") or {}).items():
                if legacy and call_site not in _LEGACY_HONOURED:
                    continue
                self._overrides[call_site] = ModelAssignment.from_dict(assignment_data)
            if legacy and data.get("assignments"):
                logger.info("llm_config: read format-1 file; kept only Grimoire assignments "
                            "(the only ones the old code applied)")
        except Exception as e:
            logger.warning(f"Error loading LLM config {self._path}: {e}; using defaults")
            self._overrides = {}

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": CONFIG_VERSION,
            "assignments": {k: v.to_dict() for k, v in sorted(self._overrides.items())},
        }
        tmp = self._path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self._path)

    # --- resolution ---------------------------------------------------------

    def default_for(self, call_site: str, default: Optional[ModelAssignment] = None) -> Optional[ModelAssignment]:
        """What the call site runs with no override: caller's default, else its policy."""
        if default is not None:
            return default
        site = CALL_SITES.get(call_site)
        if site is not None:
            return site.default()
        return None

    def resolve(self, call_site: str, default: Optional[ModelAssignment] = None) -> Optional[ModelAssignment]:
        """The model this call should use. None means: skip the call (no model).

        A pinned call site with a fixed policy (the dreams) runs that model
        whatever the caller passes and whatever the overrides file says. A
        pinned site whose model is the caller's by design (chat, interviews)
        runs the caller's model and ignores overrides.
        """
        site = CALL_SITES.get(call_site)
        if site is not None and site.pinned:
            if getattr(site.default, "from_caller", False):
                return default if default is not None else site.default()
            return site.default()
        override = self._overrides.get(call_site)
        if override is not None:
            return override
        return self.default_for(call_site, default)

    def override_for(self, call_site: str) -> Optional[ModelAssignment]:
        return self._overrides.get(call_site)

    def get(self, call_site: str) -> ModelAssignment:
        """Back-compat: effective assignment, Haiku if nothing applies."""
        return self.resolve(call_site) or ModelAssignment(provider="anthropic", model_id=HAIKU)

    # --- overrides ------------------------------------------------------------

    def set(self, call_site: str, assignment: ModelAssignment, *, allow_unknown: bool = False):
        site = CALL_SITES.get(call_site)
        if site is None and not allow_unknown:
            raise UnknownCallSite(call_site)
        if site is not None and site.pinned:
            raise PinnedCallSite(f"{call_site} is pinned: {site.pinned_reason}")
        with self._lock:
            self._overrides[call_site] = assignment
            self._save()

    def clear(self, call_site: str):
        """Remove an override; the call site goes back to its default."""
        with self._lock:
            if self._overrides.pop(call_site, None) is not None:
                self._save()

    def set_many(self, assignments: dict[str, ModelAssignment]):
        for call_site, assignment in assignments.items():
            self.set(call_site, assignment)

    def reset_to_defaults(self):
        with self._lock:
            self._overrides = {}
            self._save()

    def get_all(self) -> dict[str, ModelAssignment]:
        """Effective assignment for every registered call site that has one."""
        out = {}
        for name in CALL_SITES:
            a = self.resolve(name)
            if a is not None:
                out[name] = a
        return out

    def list_call_sites(self) -> list[str]:
        return sorted(CALL_SITES)


def get_model_for(call_site: str) -> ModelAssignment:
    """Back-compat: the model assignment for a call site."""
    return LLMConfigManager().get(call_site)


def resolve_model(call_site: str, default: Optional[ModelAssignment] = None) -> Optional[ModelAssignment]:
    return LLMConfigManager().resolve(call_site, default)


# Available models for the UI
AVAILABLE_MODELS = [
    # Anthropic
    {"provider": "anthropic", "model_id": "claude-haiku-4-5-20251001", "name": "Haiku 4.5", "local": False},
    {"provider": "anthropic", "model_id": "claude-sonnet-4-6", "name": "Sonnet 4", "local": False},

    # Ollama - common models
    {"provider": "ollama", "model_id": "llama3.1:8b-instruct-q8_0", "name": "Llama 3.1 8B", "local": True},
    {"provider": "ollama", "model_id": "llama3.1:70b-instruct-q4_K_M", "name": "Llama 3.1 70B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:latest", "name": "Qwen 2.5 7B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:14b", "name": "Qwen 2.5 14B", "local": True},
    {"provider": "ollama", "model_id": "qwen2.5:72b-instruct-q4_K_M", "name": "Qwen 2.5 72B", "local": True},
    {"provider": "ollama", "model_id": "mistral:7b-instruct-v0.3-q8_0", "name": "Mistral 7B", "local": True},
    {"provider": "ollama", "model_id": "gemma2:9b-instruct-q8_0", "name": "Gemma 2 9B", "local": True},
    {"provider": "ollama", "model_id": "deepseek-r1:7b", "name": "DeepSeek R1 7B", "local": True},

    # OpenAI
    {"provider": "openai", "model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "local": False},
]


