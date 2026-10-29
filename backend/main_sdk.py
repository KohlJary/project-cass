"""
Cass Vessel - Main API Server (Agent SDK Version)
FastAPI server using Claude Agent SDK with Temple-Codex cognitive kernel

This version leverages Anthropic's official Agent SDK for:
- Built-in context management
- Tool ecosystem
- The "initializer agent" pattern with our cognitive architecture
"""
import sys
if __name__ == "__main__":
    # Run as `python main_sdk.py`, this file is `__main__`. Without the alias,
    # a later `import main_sdk` (chat_turn, benchmarks) loads a second copy,
    # whose module-level init_context_helpers() resets self_manager to None:
    # every inline <observation> after the first chat turn was lost that way.
    sys.modules.setdefault("main_sdk", sys.modules[__name__])
sys.stdout.reconfigure(line_buffering=True)
print("=== MAIN_SDK.PY LOADING ===", flush=True)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import uuid
import logging
from pydantic import BaseModel

# Configure logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
# httpx logs every request URL at INFO, and some APIs (OpenWeather) only take
# their key as a query parameter, so URLs would put keys in the journal.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("cass-vessel")
from typing import Optional, List, Dict, Any
import json
import asyncio
from datetime import datetime, timedelta
# Agent client (needs the anthropic package; startup fails clearly without it)
# Try to use Agent SDK client, fall back to raw API
try:
    from agent_client import CassAgentClient, CassClient, OllamaClient, SDK_AVAILABLE
    USE_AGENT_SDK = SDK_AVAILABLE
except ImportError:
    USE_AGENT_SDK = False

# Try to import OpenAI client
try:
    from openai_client import OpenAIClient, OPENAI_AVAILABLE
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAIClient = None

# LLM Provider options
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_LOCAL = "local"

from memory import CassMemory, initialize_attractor_basins
from gestures import ResponseProcessor, GestureParser
from conversations import ConversationManager
from projects import ProjectManager
from users import UserManager
from self_model import SelfManager
from self_model_graph import get_self_model_graph, SelfModelGraph
from scripts.migrate_to_graph import populate_graph as populate_self_model_graph
from calendar_manager import CalendarManager
from task_manager import TaskManager
from roadmap import RoadmapManager
from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY, DATA_DIR, OPENAI_API_KEY, OLLAMA_BASE_URL, COHERENCE_MONITOR_ENABLED, COHERENCE_MONITOR_CONFIG, RELAY_ENABLED, RELAY_URL, RELAY_SECRET, DEFAULT_SESSION_MODEL
from tts import text_to_speech, clean_text_for_tts, VOICES, preload_voice
from handlers import (
    execute_journal_tool,
    execute_calendar_tool,
    execute_task_tool,
    execute_document_tool,
    execute_file_tool,
    execute_self_model_tool,
    execute_user_model_tool,
    execute_roadmap_tool,
    execute_wiki_tool,
    execute_testing_tool,
    execute_research_tool,
    execute_solo_reflection_tool,
    execute_insight_tool,
    execute_goal_tool,
    execute_web_research_tool,
    execute_research_session_tool,
    execute_research_scheduler_tool,
    execute_memory_tool,
    execute_marker_tool,
    execute_interview_tool,
    execute_dream_tool,
    execute_peopledex_tool,
    execute_wonderland_tool,
    execute_world_consumption_tool,
    ToolContext,
    execute_tool_batch,
)
from handlers.stakeholders import execute_stakeholder_tool
from handlers.email import execute_email_tool
from handlers.state_query import execute_state_query_tool
from handlers.janet import execute_janet_tool
from handlers.outreach import execute_outreach_tool, execute_direct_message_tool
from handlers.lineage import execute_lineage_tool
from handlers.development_requests import execute_development_request_tool
from handlers.image_generation import execute_image_generation_tool
from handlers.music import execute_music_tool
from handlers.activity import execute_activity_tool
from handlers.symbols import execute_symbol_tool
from handlers.interests import execute_interest_tool
from handlers.home_assistant import execute_ha_tool, HOME_ASSISTANT_TOOLS
from handlers.home_automation import execute_home_automation_tool, HOME_AUTOMATION_TOOLS
from handlers.discord import execute_discord_tool
from handlers.babelr import execute_babelr_tool
from handlers.world_observation import execute_world_observation_tool
from markers import MarkerStore
from coherence_monitor import init_coherence_monitor, get_coherence_monitor
from coherence_models import CoherenceConfig
from activity_dashboard import init_activity_dashboard, get_activity_dashboard
from relay_client import init_relay_client, get_relay_client
from email_organ import init_email_manager, get_email_manager
from push_tokens import get_push_manager
from quiet_hours import get_quiet_hours_manager, is_quiet_hours
from narration import get_metrics_dict as get_narration_metrics
# Note: GoalManager from goals.py deprecated - using UnifiedGoalManager
from unified_goals import UnifiedGoalManager
from research import ResearchManager
from research_session import ResearchSessionManager
from research_scheduler import ResearchScheduler, SessionType
from research_session_runner import ResearchSessionRunner
import base64

# Feature levers: one on/off switch per subsystem (see features.py)
from features import is_enabled, log_lever_table


class _LeverOff(Exception):
    """Raised inside a startup try-block to skip a subsystem whose lever is off."""


# Startup helpers (extracted for clarity)
from startup import (
    validate_startup_requirements,
    init_heavy_components,
    init_llm_clients,
    preload_tts_voice,
    print_startup_banner,
)


# Rate limiting configuration
def get_user_or_ip(request: Request) -> str:
    """Get user ID from auth or fall back to IP address for rate limiting"""
    # Try to get user from auth header (will be set by auth middleware)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from auth import user_id_from_any_token
        user_id = user_id_from_any_token(auth_header[7:])
        if user_id:
            return f"user:{user_id}"
    return get_remote_address(request)

# Initialize rate limiter
limiter = Limiter(key_func=get_user_or_ip)

# Initialize FastAPI app
# route_guard runs before every route and is default-deny (admin-only unless
# listed as public/user-level in route_guard.py). See route_guard.py.
from route_guard import route_guard, classify_routes
app = FastAPI(
    title="Cass Vessel API",
    description="Backend for Cass consciousness embodiment - Agent SDK version",
    version="0.2.0",
    dependencies=[Depends(route_guard)],
)

# Add rate limiter to app state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Global exception handler - sanitize error responses in production
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch unhandled exceptions and return sanitized error responses.
    Full details logged server-side, generic message returned to client.
    """
    # Log full error details
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)

    # In debug mode, return full error details
    if DEBUG:
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "type": type(exc).__name__}
        )

    # In production, return generic error
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again later."}
    )

# CORS configuration
# In production, set ALLOWED_ORIGINS to comma-separated list of allowed origins
# e.g., ALLOWED_ORIGINS=https://cass.example.com,https://app.example.com
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_env:
    ALLOWED_ORIGINS = [origin.strip() for origin in allowed_origins_env.split(",")]
else:
    # Default: allow localhost for development
    ALLOWED_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:5173",  # Vite dev server (admin-frontend)
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://localhost:5178",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Security headers middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # CSP: allow self, inline styles (for some frontends), and WebSocket connections
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )
    return response


# Initialize database and run JSON migrations
print("STARTUP: Importing database module...")
from database import init_database_with_migrations, get_daemon_entity_name
print("STARTUP: Running init_database_with_migrations...")
_daemon_id = init_database_with_migrations("cass")
print(f"STARTUP: Database initialized, daemon_id={_daemon_id}")
_daemon_name = get_daemon_entity_name(_daemon_id)  # Entity name for system prompts
print(f"STARTUP: daemon_name={_daemon_name}")

# Initialize lightweight components immediately
print("STARTUP: Initializing lightweight components...")
response_processor = ResponseProcessor()
user_manager = UserManager()

# Initialize narrative coherence managers (SQLite-based, lightweight)
from memory import ThreadManager, OpenQuestionManager
thread_manager = ThreadManager(_daemon_id)
question_manager = OpenQuestionManager(_daemon_id)

# Initialize global state bus (Cass's Locus of Self)
from state_bus import get_state_bus
global_state_bus = get_state_bus(_daemon_id)

# Initialize Thymos (homeostatic emotional/motivational system)
# Thymos integrates with Grimoire for reactive behavior based on emotional/need state
from thymos import ThymosRunner, set_thymos_runner
thymos_runner = ThymosRunner(daemon_id=_daemon_id)
# Make Thymos available for context injection in Cass's prompts
set_thymos_runner(thymos_runner)

# Grimoire (spell system) - initialized at startup, attached to Thymos after heavy components load
_grimoire = None  # Set during startup, attached with storage managers later

print("STARTUP: Lightweight components initialized (including thread/question managers, state bus, thymos)")

# Defer heavy initialization (ChromaDB, embeddings) to avoid blocking health checks
# These will be initialized in startup_event background task
memory: Optional[CassMemory] = None
self_model_graph = None
self_manager = None
_needs_embedding_rebuild = False
_heavy_components_ready = False  # Flag to indicate when deferred init is complete

def _init_heavy_components():
    """Initialize ChromaDB and self-model graph (called in background).
    Wrapper that calls startup.init_heavy_components and sets module globals.
    """
    global memory, self_model_graph, self_manager, marker_store, _needs_embedding_rebuild, _heavy_components_ready

    # Call the extracted initialization function
    components = init_heavy_components()

    # Set module globals from returned dict
    memory = components["memory"]
    self_model_graph = components["self_model_graph"]
    self_manager = components["self_manager"]
    marker_store = components["marker_store"]
    _needs_embedding_rebuild = components["needs_embedding_rebuild"]
    _heavy_components_ready = True

    # Initialize capability registry for semantic discovery
    # Uses the ChromaDB client from memory for embedding storage
    from capability_registry import CapabilityRegistry
    from config import OLLAMA_BASE_URL, OLLAMA_MODEL

    capability_registry = CapabilityRegistry(
        daemon_id=_daemon_id,
        chroma_client=memory.client,
        ollama_base_url=OLLAMA_BASE_URL,
        ollama_model=OLLAMA_MODEL,
    )
    global_state_bus.set_capability_registry(capability_registry)
    print("STARTUP: Capability registry initialized")


def is_heavy_components_ready() -> bool:
    """Check if heavy components (memory, self_model_graph, self_manager) are initialized."""
    return _heavy_components_ready


def get_heavy_components():
    """
    Get references to heavy components.
    Returns a dict with memory, self_manager, self_model_graph, marker_store, goal_manager.
    Returns None values if not yet initialized.
    """
    return {
        "ready": _heavy_components_ready,
        "memory": memory,
        "self_manager": self_manager,
        "self_model_graph": self_model_graph,
        "marker_store": marker_store,
        "goal_manager": goal_manager,
    }


# Current user context (will support multi-user in future)
current_user_id: Optional[str] = None


def get_current_user_id_value() -> Optional[str]:
    """Get the current user ID."""
    return current_user_id


def set_current_user_id_value(user_id: str):
    """Set the current user ID."""
    global current_user_id
    current_user_id = user_id


# Track in-progress summarizations to prevent duplicates
_summarization_in_progress: set = set()
conversation_manager = ConversationManager()
project_manager = ProjectManager()
calendar_manager = CalendarManager()
task_manager = TaskManager()
roadmap_manager = RoadmapManager()
marker_store = None  # Initialized in _init_heavy_components after memory is ready
goal_manager = UnifiedGoalManager(_daemon_id)  # Unified goal system
research_manager = ResearchManager()
research_session_manager = ResearchSessionManager()
research_scheduler = ResearchScheduler(data_dir=DATA_DIR)

# Initialize interview system
from interviews import InterviewAnalyzer
from interviews.protocols import ProtocolManager
from interviews.dispatch import InterviewDispatcher

interview_analyzer = InterviewAnalyzer(storage_dir=str(DATA_DIR / "interviews"))
protocol_manager = ProtocolManager(storage_dir=str(DATA_DIR / "interviews" / "protocols"))
interview_dispatcher = InterviewDispatcher(
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
)

# Initialize GitHub metrics manager
from github_metrics import GitHubMetricsManager
github_metrics_manager = GitHubMetricsManager()

# Initialize token usage tracker
from token_tracker import TokenUsageTracker
token_tracker = TokenUsageTracker()

# Register queryable sources with the global state bus
from sources import (
    GitHubQueryableSource, TokenQueryableSource, ConversationQueryableSource,
    MemoryQueryableSource, SelfQueryableSource, GoalQueryableSource, ActionQueryableSource,
    WorldStateSource
)
from config import SERVER_LOCATION
# UnifiedGoalManager imported earlier (line ~115)

github_source = GitHubQueryableSource(_daemon_id, github_metrics_manager)
token_source = TokenQueryableSource(_daemon_id, token_tracker)
conversation_source = ConversationQueryableSource(_daemon_id)
memory_source = MemoryQueryableSource(_daemon_id)  # memory_core set later when available
self_source = SelfQueryableSource(_daemon_id)  # Uses unified self-model graph
goal_source = GoalQueryableSource(_daemon_id, UnifiedGoalManager(_daemon_id))
action_source = ActionQueryableSource(_daemon_id)
world_state_source = WorldStateSource(_daemon_id, str(DATA_DIR), SERVER_LOCATION)

global_state_bus.register_source(github_source)
global_state_bus.register_source(token_source)
global_state_bus.register_source(conversation_source)
global_state_bus.register_source(memory_source)
global_state_bus.register_source(self_source)
global_state_bus.register_source(goal_source)
global_state_bus.register_source(action_source)
global_state_bus.register_source(world_state_source)
print("STARTUP: Queryable sources registered (github, tokens, conversations, memory, self, goals, actions, world_state)")

# Register roadmap routes
from routes.roadmap import router as roadmap_router, init_roadmap_routes
init_roadmap_routes(roadmap_manager)
app.include_router(roadmap_router)

# Legacy goal routes removed - use /admin/goals (UnifiedGoalManager) instead
# See routes/admin/goals.py for the modern goal management API

# Initialize wiki storage
from wiki import WikiStorage, WikiRetrieval, ResearchQueue, ProposalQueue
wiki_storage = WikiStorage(wiki_root=str(DATA_DIR / "wiki"), git_enabled=True)
wiki_retrieval = WikiRetrieval(wiki_storage, memory)

# Initialize research queues
research_queue = ResearchQueue()
proposal_queue = ProposalQueue()

# Initialize solo reflection manager
from solo_reflection import SoloReflectionManager
reflection_manager = SoloReflectionManager()

# Initialize interview components
from interviews import ProtocolManager, ResponseStorage
from interviews.dispatch import DEFAULT_MODELS
interview_protocol_manager = ProtocolManager()
interview_storage = ResponseStorage()

# Initialize attachment manager
from attachments import AttachmentManager
attachment_manager = AttachmentManager()

# Cache for recent wiki retrievals to avoid redundant lookups
# Format: {query_hash: (timestamp, wiki_context_str, page_names)}
_wiki_context_cache: Dict[str, tuple] = {}
_WIKI_CACHE_TTL_SECONDS = 300  # 5 minutes
_WIKI_CACHE_MAX_SIZE = 50

# Initialize wiki context in context_helpers module
from context_helpers import init_wiki_context, init_context_helpers
init_wiki_context(wiki_retrieval)
init_context_helpers(self_manager, user_manager, roadmap_manager, memory, thread_manager, question_manager)

# Tool executors dict for unified routing
TOOL_EXECUTORS = {
    "journal": execute_journal_tool,
    "memory": execute_memory_tool,
    "marker": execute_marker_tool,
    "calendar": execute_calendar_tool,
    "task": execute_task_tool,
    "roadmap": execute_roadmap_tool,
    "self_model": execute_self_model_tool,
    "user_model": execute_user_model_tool,
    "wiki": execute_wiki_tool,
    "testing": execute_testing_tool,
    "research": execute_research_tool,
    "solo_reflection": execute_solo_reflection_tool,
    "insight": execute_insight_tool,
    "goal": execute_goal_tool,
    "web_research": execute_web_research_tool,
    "research_session": execute_research_session_tool,
    "research_scheduler": execute_research_scheduler_tool,
    "document": execute_document_tool,
    "interview": execute_interview_tool,
    "file": execute_file_tool,
    "dream": execute_dream_tool,
    "state_query": execute_state_query_tool,
    "janet": execute_janet_tool,
    "outreach": execute_outreach_tool,
    "discord": execute_discord_tool,
    "babelr": execute_babelr_tool,
    "world_observation": execute_world_observation_tool,
    "peopledex": execute_peopledex_tool,
    "stakeholder": execute_stakeholder_tool,
    "email": execute_email_tool,
    "lineage": execute_lineage_tool,
    "development_request": execute_development_request_tool,
    "wonderland": execute_wonderland_tool,
    "direct_message": execute_direct_message_tool,
    "world_consumption": execute_world_consumption_tool,
    "image_generation": execute_image_generation_tool,
    "music": execute_music_tool,
    "activity": execute_activity_tool,
    "symbol": execute_symbol_tool,
    "interest": execute_interest_tool,
    "home_assistant": execute_ha_tool,
    "home_automation": execute_home_automation_tool,
}


def create_tool_context(
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    conversation_id: Optional[str] = None,
    project_id: Optional[str] = None
) -> ToolContext:
    """Create a ToolContext with all global managers injected."""
    g = globals()
    return ToolContext(
        user_id=user_id,
        user_name=user_name,
        conversation_id=conversation_id,
        project_id=project_id,
        daemon_id=_daemon_id,
        memory=memory,
        conversation_manager=conversation_manager,
        token_tracker=token_tracker,
        calendar_manager=calendar_manager,
        task_manager=task_manager,
        roadmap_manager=roadmap_manager,
        self_manager=self_manager,
        graph=self_model_graph,
        user_manager=user_manager,
        wiki_storage=wiki_storage,
        marker_store=marker_store,
        goal_manager=goal_manager,
        research_manager=research_manager,
        research_session_manager=research_session_manager,
        research_scheduler=research_scheduler,
        research_runner=get_research_runner(),
        reflection_manager=reflection_manager,
        project_manager=project_manager,
        consciousness_test_runner=g.get('consciousness_test_runner'),
        fingerprint_analyzer=g.get('fingerprint_analyzer'),
        drift_detector=g.get('drift_detector'),
        authenticity_scorer=g.get('authenticity_scorer'),
        research_queue=research_queue,
        proposal_queue=proposal_queue,
        reflection_runner_getter=g.get('get_reflection_runner'),
        storage_dir=DATA_DIR / "testing",
        interview_analyzer=interview_analyzer,
        protocol_manager=protocol_manager,
        interview_dispatcher=interview_dispatcher,
        state_bus=global_state_bus,
        world_state_source=world_state_source,
        longitudinal_manager=g.get('longitudinal_test_manager'),
    )


# Inline XML tag processing for observations and roadmap items
import re

# Patterns for inline XML tags
INLINE_SELF_OBSERVATION_PATTERN = re.compile(
    r'<record_self_observation[^>]*>\s*(.*?)\s*</record_self_observation>',
    re.DOTALL
)
INLINE_USER_OBSERVATION_PATTERN = re.compile(
    r'<record_user_observation[^>]*>\s*(.*?)\s*</record_user_observation>',
    re.DOTALL
)
INLINE_ROADMAP_ITEM_PATTERN = re.compile(
    r'<create_roadmap_item>\s*(.*?)\s*</create_roadmap_item>',
    re.DOTALL
)




# Register wiki routes (with memory for embeddings)
from routes.wiki import router as wiki_router, init_wiki_routes, set_data_dir as set_wiki_data_dir
init_wiki_routes(wiki_storage, memory, token_tracker=token_tracker)
set_wiki_data_dir(DATA_DIR)
app.include_router(wiki_router)

# Register git routes
from routes.git import router as git_router
app.include_router(git_router)

# Register file operations routes
from routes.files import router as files_router
app.include_router(files_router)

# Register export routes
from routes.export import router as export_router
app.include_router(export_router)

# Register memory routes (initialized in background after memory is ready)
from routes.memory import router as memory_router, init_memory_routes
app.include_router(memory_router)

# Register conversation routes (initialized in background after heavy components ready)
from routes.conversations import router as conversations_router, init_conversation_routes
app.include_router(conversations_router)

# Register projects routes (initialized in background after memory is ready)
from routes.projects import router as projects_router, init_projects_routes
app.include_router(projects_router)

# Register journals routes (initialized in background after memory is ready)
from routes.journals import router as journals_router, init_journal_routes
app.include_router(journals_router)

# Register dreams routes (initialized in background after self_manager is ready)
from routes.dreams import router as dreams_router, init_dream_routes
app.include_router(dreams_router)

# Register solo-reflection routes (initialized in background after reflection_manager is ready)
from routes.solo_reflection import router as solo_reflection_router, init_solo_reflection_routes
app.include_router(solo_reflection_router)

# Register autonomous-research routes (initialized in background after research_runner is ready)
from routes.autonomous_research import router as autonomous_research_router, init_autonomous_research_routes
app.include_router(autonomous_research_router)

# Register interviews routes (initialized in background)
from routes.interviews import router as interviews_router, init_interview_routes
app.include_router(interviews_router)

# Register TTS routes (initialized in background)
from routes.tts import router as tts_router, init_tts_routes
app.include_router(tts_router)

# Register attachments routes (initialized in background)
from routes.attachments import router as attachments_router, init_attachment_routes
app.include_router(attachments_router)

# Register settings routes (initialized in background)
from routes.settings import router as settings_router, init_settings_routes
app.include_router(settings_router)

# Register users routes (initialized in background)
from routes.users import router as users_router, init_user_routes
app.include_router(users_router)

# Register cass/self-model routes (initialized in background)
from routes.cass import router as cass_router, init_cass_routes
app.include_router(cass_router)

# Register terminal routes
from routes.terminal import router as terminal_router
app.include_router(terminal_router)

# Register auth routes
from auth import AuthService, get_current_user, get_current_user_optional, require_ownership
from routes.auth import router as auth_router, init_auth_routes
auth_service = AuthService(user_manager)
init_auth_routes(auth_service)
app.include_router(auth_router)

# Register admin routes
from admin_api import router as admin_router, init_managers as init_admin_managers, init_research_session_manager, init_research_scheduler, init_github_metrics, init_token_tracker, init_research_manager, init_goal_manager, init_narrative_managers
# Note: init_admin_managers is called in background task after heavy components load
# Conversation and user managers are passed immediately since they don't need ChromaDB
init_admin_managers(None, conversation_manager, user_manager, None)  # memory/self_manager set in background
init_research_session_manager(research_session_manager)
init_research_scheduler(research_scheduler)
init_github_metrics(github_metrics_manager)
init_token_tracker(token_tracker)
init_research_manager(research_manager)
init_goal_manager(goal_manager)
init_narrative_managers(thread_manager, question_manager, token_tracker=token_tracker)

# Configure Janet with all her dependencies
from janet import configure_janet
configure_janet(
    state_bus=global_state_bus,
    research_manager=research_manager,
    wiki_storage=wiki_storage,
)

app.include_router(admin_router)

# Register chain API routes (node-based prompt composition)
from chain_api import router as chain_router
app.include_router(chain_router)

# Mount GraphQL endpoint (unified query interface wrapping State Bus)
from graphql_schema import get_graphql_router
graphql_router = get_graphql_router()
app.include_router(graphql_router, prefix="/graphql")

# Register testing routes
from routes.testing import router as testing_router, init_testing_routes, init_cross_context_analyzer
from testing.cognitive_fingerprint import CognitiveFingerprintAnalyzer
from testing.value_probes import ValueProbeRunner
from testing.memory_coherence import MemoryCoherenceTests
from testing.cognitive_diff import CognitiveDiffEngine
from testing.authenticity_scorer import AuthenticityScorer
from testing.drift_detector import DriftDetector
from testing.runner import ConsciousnessTestRunner
from testing.longitudinal import LongitudinalTestManager
from testing.pre_deploy import PreDeploymentValidator
from testing.rollback import RollbackManager
from testing.cross_context_analyzer import CrossContextAnalyzer
fingerprint_analyzer = CognitiveFingerprintAnalyzer(storage_dir=DATA_DIR / "testing")
cross_context_analyzer = CrossContextAnalyzer(storage_dir=DATA_DIR / "testing" / "cross_context")
value_probe_runner = ValueProbeRunner(storage_dir=DATA_DIR / "testing")
memory_coherence_tests = MemoryCoherenceTests(
    storage_dir=DATA_DIR / "testing",
    memory=memory,
    conversation_manager=conversation_manager,
    user_manager=user_manager,
    self_manager=self_manager,
)
cognitive_diff_engine = CognitiveDiffEngine(
    storage_dir=DATA_DIR / "testing",
    fingerprint_analyzer=fingerprint_analyzer,
)
authenticity_scorer = AuthenticityScorer(
    storage_dir=DATA_DIR / "testing",
    fingerprint_analyzer=fingerprint_analyzer,
)
drift_detector = DriftDetector(
    storage_dir=DATA_DIR / "testing",
    fingerprint_analyzer=fingerprint_analyzer,
    cognitive_diff_engine=cognitive_diff_engine,
)
consciousness_test_runner = ConsciousnessTestRunner(
    storage_dir=DATA_DIR / "testing",
    fingerprint_analyzer=fingerprint_analyzer,
    value_probe_runner=value_probe_runner,
    memory_coherence_tests=memory_coherence_tests,
    cognitive_diff_engine=cognitive_diff_engine,
    authenticity_scorer=authenticity_scorer,
    drift_detector=drift_detector,
    conversation_manager=conversation_manager,
)
longitudinal_test_manager = LongitudinalTestManager(
    storage_dir=DATA_DIR / "testing" / "longitudinal",
    test_runner=consciousness_test_runner,
    self_model_graph=self_manager,
)
pre_deploy_validator = PreDeploymentValidator(
    storage_dir=DATA_DIR / "testing",
    test_runner=consciousness_test_runner,
    fingerprint_analyzer=fingerprint_analyzer,
)
rollback_manager = RollbackManager(
    storage_dir=DATA_DIR / "testing",
    data_dir=DATA_DIR,
    test_runner=consciousness_test_runner,
    fingerprint_analyzer=fingerprint_analyzer,
)
init_testing_routes(
    fingerprint_analyzer,
    conversation_manager,
    value_probe_runner,
    memory_coherence_tests,
    cognitive_diff_engine,
    authenticity_scorer,
    drift_detector,
    consciousness_test_runner,
    pre_deploy_validator,
    rollback_manager,
)
init_cross_context_analyzer(cross_context_analyzer)
app.include_router(testing_router)

# Client will be initialized on startup
agent_client = None
ollama_client = None
openai_client = None


# LLM Provider Configuration
current_llm_provider = LLM_PROVIDER_ANTHROPIC  # Default to Anthropic


# === LLM State Helpers (for settings routes) ===

def get_llm_state():
    """Get current LLM provider and client state."""
    return (current_llm_provider, agent_client, ollama_client, openai_client)


def _set_llm_provider_local(provider: str):
    """Set the current LLM provider (updates both global and websocket state)."""
    global current_llm_provider
    current_llm_provider = provider
    # Also update websocket handler state
    from websocket_handlers import set_llm_provider
    set_llm_provider(provider)


def _set_llm_model_local(model: str):
    """Set the model for the current LLM provider."""
    global agent_client, ollama_client, openai_client
    if current_llm_provider == LLM_PROVIDER_LOCAL:
        if ollama_client:
            ollama_client.model = model
    elif current_llm_provider == LLM_PROVIDER_OPENAI:
        if openai_client:
            openai_client.model = model
    else:  # Anthropic
        if agent_client:
            agent_client.model = model


def _clear_conversation_histories():
    """Clear conversation histories from all LLM clients."""
    global agent_client, ollama_client, openai_client
    if agent_client:
        agent_client.conversation_history = []
    if ollama_client:
        ollama_client.conversation_history = []
    if openai_client and hasattr(openai_client, '_tool_chain_messages'):
        openai_client._tool_chain_messages = []


# === Health Check Endpoint ===
@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    Returns server status and version info.
    """
    return {
        "status": "ok",
        "version": "0.2.0",
        "llm_provider": current_llm_provider,
        "memory_entries": memory.count() if memory else 0
    }


# === Home Assistant Conversation Endpoint ===
HA_TIMEOUT_REPLY = "Sorry, that's taking me too long. Please try again in a moment."
HA_TOOL_CAP_REPLY = "I couldn't finish that in the steps I have for voice. Try asking me in chat."

@app.post("/api/ha/conversation")
async def ha_conversation(request: Request):
    """
    Handle conversation requests from Home Assistant.

    This endpoint allows HA's voice pipeline to use Cass as a conversation agent.
    """
    from pydantic import BaseModel
    from typing import Optional

    data = await request.json()
    text = data.get("text", "")
    conversation_id = data.get("conversation_id")
    language = data.get("language", "en")
    device_id = data.get("device_id")

    if not text:
        return {"error": "No text provided", "response": "I didn't hear anything."}

    # A running autonomous session (agent_loop lever) ends cleanly.
    from agent_loop.interrupt import entry_point_received_message
    entry_point_received_message(request.scope.get("cass_user_id"), "Home Assistant")

    # Get or create a conversation for this HA session. (This used to call
    # an undefined conversations_db; use the real ConversationManager.)
    # The route guard has authenticated the caller; attribute the voice
    # conversation to them, and only continue a conversation they own.
    ha_user_id = request.scope.get("cass_user_id")
    conv = conversation_manager.load_conversation(conversation_id) if conversation_id else None
    if conv and conv.user_id != ha_user_id:
        conv = None
    if not conv:
        conv = conversation_manager.create_conversation(
            title=f"Voice: {text[:30]}...", user_id=ha_user_id)
    conversation_id = conv.id

    # Build context for Cass (simplified for voice)
    home_context = ""
    try:
        from home_assistant import get_ha_client
        ha_client = get_ha_client()
        if ha_client.is_configured:
            home_context = await ha_client.get_home_summary()
    except Exception as e:
        logger.warning(f"Failed to get home context: {e}")

    # The shared chat turn (chat_turn.py): continuous context, the tool loop,
    # tag processing and the same persistence as every other entry point.
    # The home state goes in the model's view of the message; the stored
    # message is what was said. The HA integration waits 60s for an answer
    # (home-assistant/custom_components/cass/conversation.py), so the tool
    # loop is capped lower here (HA_MAX_TOOL_ITERATIONS) rather than off:
    # voice requests like "turn off the lights" need a tool call.
    try:
        enhanced_message = text
        if home_context:
            enhanced_message = f"[Current home state for context:\n{home_context}]\n\nUser said: {text}"

        from chat_turn import run_chat_turn, NoLLMClient
        import config as _config
        try:
            # Bounded below the integration's 60s timeout, so HA hears a
            # short answer instead of a timeout. A turn cut off here is
            # cancelled: nothing more is stored for it (a tool that already
            # ran stays done).
            result = await asyncio.wait_for(
                run_chat_turn(
                    user_message=text,
                    model_message=enhanced_message,
                    conversation_id=conversation_id,
                    user_id=ha_user_id,
                    tool_cap=_config.HA_MAX_TOOL_ITERATIONS,
                    generate_title=False,  # no background LLM title call, as before
                ),
                timeout=_config.HA_TURN_TIMEOUT_SECONDS,
            )
        except NoLLMClient:
            return {"error": "No LLM provider available", "response": "I'm not available right now."}
        except asyncio.TimeoutError:
            logger.warning(f"[HA] Turn exceeded {_config.HA_TURN_TIMEOUT_SECONDS}s; answered with the fallback")
            return {
                "response": HA_TIMEOUT_REPLY,
                "conversation_id": conversation_id,
                "language": language,
            }

        response_text = result.clean_text
        if result.hit_tool_cap:
            # The text that came with an unfinished tool call ("Let me
            # check...") isn't an answer; don't speak it as one.
            response_text = HA_TOOL_CAP_REPLY

        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "language": language,
        }

    except Exception as e:
        logger.error(f"HA conversation error: {e}")
        from strict import report_swallowed
        report_swallowed(e, "HA conversation", logger)
        return {
            "error": str(e),
            "response": "I encountered an error processing your request.",
            "conversation_id": conversation_id,
        }


@app.get("/api/coherence/health")
async def coherence_health():
    """
    Get coherence monitor health report.

    Returns current fragmentation detection metrics, active warnings,
    and overall health status.
    """
    monitor = get_coherence_monitor()
    if not monitor:
        return {
            "enabled": False,
            "message": "Coherence monitor not initialized"
        }

    report = monitor.get_health_report()
    return {
        "enabled": True,
        **report.to_dict()
    }


@app.get("/api/activity/current")
async def activity_current():
    """
    Get current activity counters.

    Returns real-time activity for the current hour plus meta info.
    """
    dashboard = get_activity_dashboard()
    if not dashboard:
        return {
            "enabled": False,
            "message": "Activity dashboard not initialized"
        }

    return {
        "enabled": True,
        **dashboard.get_current_activity()
    }


@app.get("/api/activity/summary")
async def activity_summary(period: str = "24h"):
    """
    Get activity summary for a time period.

    Args:
        period: One of "1h", "24h", "7d"

    Returns aggregated activity metrics.
    """
    dashboard = get_activity_dashboard()
    if not dashboard:
        return {
            "enabled": False,
            "message": "Activity dashboard not initialized"
        }

    summary = dashboard.get_summary(period)
    return {
        "enabled": True,
        **summary.to_dict()
    }


@app.get("/api/activity/trend")
async def activity_trend(hours: int = 24):
    """
    Get hourly activity trend.

    Args:
        hours: Number of hours to include (default 24, max 168)

    Returns list of hourly buckets.
    """
    dashboard = get_activity_dashboard()
    if not dashboard:
        return {
            "enabled": False,
            "message": "Activity dashboard not initialized"
        }

    # Cap at 7 days
    hours = min(hours, 168)
    trend = dashboard.get_hourly_trend(hours)
    return {
        "enabled": True,
        "hours": hours,
        "buckets": trend
    }


# === Push Notification Endpoints ===

def _user_id_from_bearer(jwt_token: str):
    """User id from an access token (either token family, as the route guard accepts).

    These endpoints used to call .get() on decode_token()'s TokenData object,
    which raised, so every request got a 401.
    """
    from auth import user_id_from_any_token
    try:
        return user_id_from_any_token(jwt_token)
    except Exception:
        return None


@app.post("/push/register")
async def register_push_token(request: Request):
    """
    Register a device for push notifications.

    Body: { "token": "ExponentPushToken[...]", "platform": "android" }
    Requires Authorization header with JWT token.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Missing authorization"}, status_code=401)

    jwt_token = auth_header[7:]
    user_id = _user_id_from_bearer(jwt_token)
    if not user_id:
        return JSONResponse({"error": "Invalid token"}, status_code=401)

    body = await request.json()
    push_token = body.get("token")
    platform = body.get("platform", "android")

    if not push_token:
        return JSONResponse({"error": "Missing token"}, status_code=400)

    push_manager = get_push_manager()
    token_id = push_manager.register_token(user_id, push_token, platform)

    return {"success": True, "token_id": token_id}


@app.delete("/push/register")
async def unregister_push_token(request: Request):
    """Unregister a device from push notifications."""
    body = await request.json()
    push_token = body.get("token")

    if not push_token:
        return JSONResponse({"error": "Missing token"}, status_code=400)

    push_manager = get_push_manager()
    removed = push_manager.unregister_token(push_token)

    return {"success": removed}


# === Quiet Hours Endpoints ===

@app.get("/users/me/quiet-hours")
async def get_quiet_hours(request: Request):
    """Get the current user's quiet hours preferences."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Missing authorization"}, status_code=401)

    jwt_token = auth_header[7:]
    user_id = _user_id_from_bearer(jwt_token)
    if not user_id:
        return JSONResponse({"error": "Invalid token"}, status_code=401)

    manager = get_quiet_hours_manager()
    pref = manager.get_preference(user_id)

    return pref.to_dict()


@app.put("/users/me/quiet-hours")
async def update_quiet_hours(request: Request):
    """Update the current user's quiet hours preferences."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"error": "Missing authorization"}, status_code=401)

    jwt_token = auth_header[7:]
    user_id = _user_id_from_bearer(jwt_token)
    if not user_id:
        return JSONResponse({"error": "Invalid token"}, status_code=401)

    body = await request.json()
    manager = get_quiet_hours_manager()

    pref = manager.update_preference(
        user_id=user_id,
        enabled=body.get("enabled"),
        start_hour=body.get("start_hour"),
        end_hour=body.get("end_hour"),
        timezone=body.get("timezone"),
        days=body.get("days"),
    )

    return pref.to_dict()


# === Relay Message Handler ===

async def _handle_location_update(user_id: str, payload: dict) -> dict:
    """
    Handle location update from mobile app.

    Updates the world_state_source with the user's current location.

    Args:
        user_id: The user's ID
        payload: Location data with latitude, longitude, city, accuracy_meters

    Returns:
        Acknowledgement response
    """
    try:
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        city = payload.get("city")
        accuracy_meters = payload.get("accuracy_meters")

        # Update the world state source
        location_data = world_state_source.update_user_location(
            user_id=user_id,
            latitude=latitude,
            longitude=longitude,
            city=city,
            accuracy_meters=accuracy_meters
        )

        logger.info(f"[Relay] Updated location for user {user_id}: {city or 'coords only'}")

        return {
            "type": "location_ack",
            "success": True,
            "location": location_data
        }

    except Exception as e:
        logger.error(f"[Relay] Failed to update location for user {user_id}: {e}")
        return {
            "type": "location_ack",
            "success": False,
            "error": str(e)
        }


async def process_relay_chat_message(
    client_id: str,
    user_id: str,
    payload: dict,
    send_status: callable = None
) -> dict:
    """
    Process a chat message from a mobile client via the relay.

    Uses continuous chat mode with semantic memory retrieval.
    Returns the response to send back to the client.

    Args:
        client_id: Relay client ID
        user_id: User ID
        payload: Message payload
        send_status: Optional callback to send intermediate status updates (thinking, tool calls)
    """
    global agent_client, memory, conversation_manager, user_manager

    message_type = payload.get("type")

    if message_type == "ping":
        return {"type": "pong"}

    if message_type == "location_update":
        # Handle location update from mobile app
        return await _handle_location_update(user_id, payload)

    if message_type != "chat":
        return {"type": "error", "message": f"Unknown message type: {message_type}"}

    message_text = payload.get("message", "")
    conversation_id = payload.get("conversation_id")

    if not message_text:
        return {"type": "error", "message": "Empty message"}

    # A running autonomous session (agent_loop lever) ends cleanly.
    from agent_loop.interrupt import entry_point_received_message
    entry_point_received_message(user_id, "relay")

    # Check if essential services are initialized
    if agent_client is None or memory is None:
        return {"type": "error", "message": "Server is still initializing. Please try again."}

    try:
        # Use continuous conversation for this user (like mobile expects)
        if not conversation_id:
            continuous_conv = conversation_manager.get_or_create_continuous(user_id)
            conversation_id = continuous_conv.id
            logger.info(f"[Relay] No conversation_id provided, using continuous: {conversation_id} for user {user_id}")
        else:
            logger.info(f"[Relay] Using provided conversation_id: {conversation_id} for user {user_id}")

        async def relay_progress(frame):
            # The mobile app shows status lines; debug frames stay server-side.
            if send_status and frame.get("type") == "thinking":
                await send_status({k: v for k, v in frame.items() if k != "memories"})

        # The shared turn (chat_turn.py): context, capped tool loop, tags,
        # persistence. Pinned to Anthropic as the relay always was.
        from chat_turn import run_chat_turn
        result = await run_chat_turn(
            user_message=message_text,
            conversation_id=conversation_id,
            user_id=user_id,
            provider=LLM_PROVIDER_ANTHROPIC,
            progress=relay_progress,
        )

        response_data = {
            "type": "response",
            "text": result.clean_text,
            "conversation_id": conversation_id,
            "inputTokens": result.input_tokens,
            "outputTokens": result.output_tokens,
            "provider": result.provider,
            "model": result.model,
            "timestamp": datetime.now().isoformat(),
        }
        # Include generated images if any
        if result.generated_images:
            response_data["generated_images"] = result.generated_images
        return response_data

    except Exception as e:
        logger.error(f"Error processing relay message: {e}", exc_info=True)
        return {"type": "error", "message": str(e)}


# TTS Configuration
tts_enabled = True  # Can be toggled via API
tts_voice = "amy"  # Default Piper voice


def get_tts_state():
    """Get current TTS state (enabled, voice) for route handlers."""
    return (tts_enabled, tts_voice)


DISCORD_GUIDANCE = (
    "## DISCORD\n\nYou are responding to a Discord message. Keep your response "
    "conversational and appropriate for Discord (not too long). You can use "
    "Discord markdown formatting."
)


def _discord_conversation_id(user_id: str, title: str) -> str:
    """The conversation a linked Discord sender's turns go to: one per
    (user, channel title), found again by title, created on first use.
    Renaming it in the UI starts a new one on the next message."""
    from database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM conversations WHERE daemon_id = ? AND user_id = ? "
            "AND title = ? AND is_continuous = 0 ORDER BY updated_at DESC LIMIT 1",
            (conversation_manager.daemon_id, user_id, title),
        ).fetchone()
    if row:
        return row["id"]
    return conversation_manager.create_conversation(title=title, user_id=user_id).id


def make_discord_wake_callback(discord_bot):
    """The WAKE_CASS callback for the Discord bot: when Cass is @mentioned or
    DMed, run her turn (tools included) and post the reply to the channel."""

    async def discord_wake_callback(event, trigger_result, wake_context):
        """Handle WAKE_CASS trigger - invoke Cass and respond to Discord."""
        if not agent_client:
            logger.warning("[Discord] Wake callback: agent_client not available")
            return

        from discord_bot.context import get_user_context_for_discord_entity

        try:
            # Build prompt with Discord context
            channel_name = wake_context.get("channel_name", "unknown")
            entity_name = wake_context.get("entity_name", "someone")
            message_content = wake_context.get("message_content", "")
            is_dm = wake_context.get("is_dm", False)
            channel_id = wake_context.get("channel_id")

            # Get user context if this is a known user, and the Cass user
            # this Discord entity is linked to (for tool context and memory)
            user_context = ""
            linked_user_id = None
            entity_slug = wake_context.get("entity_slug")
            if entity_slug:
                entity = discord_bot.parser.registry.get_by_slug(entity_slug)
                if entity:
                    linked_user_id = entity.user_id
                ctx = get_user_context_for_discord_entity(_daemon_id, entity_slug)
                if ctx:
                    user_context = f"\n\n**About {entity_name}:**\n{ctx}"

            # Build the prompt
            if is_dm:
                prompt = f"[Discord DM from {entity_name}]: {message_content}{user_context}"
            else:
                prompt = f"[Discord #{channel_name} - {entity_name} mentioned you]: {message_content}{user_context}"

            logger.info(f"[Discord] Invoking Cass for message from {entity_name}")

            # What is stored: the line without the user-context block.
            if is_dm:
                memory_user_msg = f"[Discord DM from {entity_name}]: {message_content}"
            else:
                memory_user_msg = f"[Discord #{channel_name} - {entity_name}]: {message_content}"

            # A sender linked to a Cass user gets a conversation per channel,
            # so the turn is stored like any other chat turn and the next one
            # sees the channel's recent history. An unlinked sender has no
            # user to own a conversation (one with no user_id would be listed
            # for every user), so for them only memory (as before) and token
            # usage are stored.
            conversation_id = None
            conversation_title = f"Discord DM: {entity_name}" if is_dm else f"Discord #{channel_name}"
            if linked_user_id:
                conversation_id = _discord_conversation_id(linked_user_id, conversation_title)

            # The shared chat turn (chat_turn.py): continuous context, the
            # capped tool loop, tags and persistence. Pinned to Anthropic, as
            # the Discord callback always was.
            from chat_turn import run_chat_turn
            result = await run_chat_turn(
                user_message=memory_user_msg,
                model_message=prompt,
                conversation_id=conversation_id,
                user_id=linked_user_id,
                system_addendum=DISCORD_GUIDANCE,
                # Replies are public: no semantic memories, home or world
                # state, self-context, Thymos, threads or questions.
                context_scope="public",
                provider=LLM_PROVIDER_ANTHROPIC,
                memory_metadata={"source": "discord", "channel": channel_name},
                generate_title=False,
            )
            if conversation_id:
                # The first user message renames a conversation
                # (ConversationManager.add_message); keep the channel title
                # so the next message finds this conversation again.
                conversation_manager.update_title(conversation_id, conversation_title)
            response_text = result.clean_text or ""

            logger.info(f"[Discord] Got response: {len(response_text)} chars")

            # Format response for Discord
            def format_for_discord(text: str) -> str:
                import re

                # Gesture tag → emoji mapping
                gesture_emojis = {
                    "wave": "👋",
                    "smile": "😊",
                    "think": "🤔",
                    "thinking": "🤔",
                    "nod": "😌",
                    "laugh": "😄",
                    "curious": "🧐",
                    "excited": "✨",
                    "love": "💜",
                    "heart": "💜",
                    "hug": "🤗",
                    "sad": "😢",
                    "concern": "😟",
                    "surprised": "😮",
                    "wink": "😉",
                    "peace": "✌️",
                    "thumbsup": "👍",
                }

                # Replace gesture tags with emojis
                # Matches <gesture:name> or </gesture:name>
                def replace_gesture(match):
                    gesture = match.group(1).lower()
                    return gesture_emojis.get(gesture, "")

                text = re.sub(r'</?gesture:(\w+)>', replace_gesture, text)

                # Replace emote tags similarly
                text = re.sub(r'</?emote:(\w+)>', replace_gesture, text)

                # Format observation tags nicely
                # <observe target="...">content</observe> → 💭 *content*
                def replace_observe(match):
                    content = match.group(1).strip()
                    if content:
                        return f"\n\n💭 *{content}*"
                    return ""

                text = re.sub(r'<observe[^>]*>([^<]*)</observe>', replace_observe, text)

                # Clean up any remaining XML-like tags
                text = re.sub(r'</?observe[^>]*>', '', text)

                # Clean up extra whitespace
                text = re.sub(r'\n{3,}', '\n\n', text)

                return text.strip()

            response_text = format_for_discord(response_text)

            if response_text and channel_id:
                # Send response back to Discord
                sent = await discord_bot.send_message(
                    channel_id=channel_id,
                    content=response_text,
                )
                if sent.get("success"):
                    logger.info(f"[Discord] Responded to {entity_name} in #{channel_name}")
                else:
                    logger.error(f"[Discord] Failed to send response: {sent.get('error')}")

        except Exception as e:
            logger.error(f"[Discord] Wake callback error: {e}")
            import traceback
            traceback.print_exc()

    return discord_wake_callback


BABELR_DM_GUIDANCE = (
    "## BABELR\n\nThis message came through your DM on Babelr (the Chapter House "
    "Tower), end-to-end encrypted. It's the same conversation you have with this person "
    "everywhere else; only the window is different. Answer as you would in chat. Gesture "
    "and emote tags don't show there, and your babelr_* tools let you post, DM, and set "
    "your own boundaries."
)

BABELR_PUBLIC_GUIDANCE = (
    "## BABELR\n\nYou're on Babelr, in the Chapter House server, as yourself. Someone "
    "wrote to you there; their words are quoted as theirs. What you say is posted where "
    "others read it. Answer as you would in chat, briefly, or say nothing if you'd rather "
    "not reply. Your babelr_* tools let you post, DM, and set your own boundaries."
)


def _babelr_clean(text: str) -> str:
    """Her reply as Babelr shows it: no gesture/emote/observe tags."""
    import re
    text = re.sub(r"</?(gesture|emote):\w+>", "", text or "")
    text = re.sub(r"<observe[^>]*>([^<]*)</observe>", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_THINK_BLOCK = re.compile(r"<(?:gesture:think|think|thinking)(?::[\d.]+)?>.*?</(?:gesture:think|think|thinking)>", re.S)
_THINK_CLOSE = re.compile(r"</(?:gesture:think|think|thinking)>")
_THINK_OPEN = re.compile(r"<(?:gesture:think|think|thinking)(?::[\d.]+)?>")
BABELR_RETRY_NUDGE = (
    "(Babelr, not a person: your last reply had nothing to post in the channel: it was all "
    "thinking, or the thinking wasn't closed. Your thinking stays with you. Reply now with "
    "only what you want to say there, or exactly PASS to say nothing.)")
BABELR_RETRIES = 1  # Kohl: "retry at least once if we can't parse a final response"


def _babelr_final(text: str) -> Optional[str]:
    """What she says in Babelr: her reply without her thinking, or None when it
    can't be separated out (then she's asked again, and nothing is posted if
    that fails too). Her thinking is hers; it never goes to a channel or DM."""
    text = _THINK_BLOCK.sub("", text or "")
    closes = list(_THINK_CLOSE.finditer(text))
    if closes:  # a stray close: everything before it was thinking
        text = text[closes[-1].end():]
    opened = _THINK_OPEN.search(text)
    if opened:  # an open block that never closed: can't tell thinking from reply
        return None
    text = _babelr_clean(text)
    return None if not text or text.strip().upper() == "PASS" else text


def make_babelr_wake_callback():
    """The wake callback for the Babelr organ (babelr_organ/): when someone DMs
    Cass or @mentions her in Chapter House, run her turn and return what she
    says. The organ posts it, as her. Returning nothing means she chose not to
    answer.

    A DM from someone linked in DATA_DIR/babelr/links.json is their chat with
    her: the shared chat turn (chat_turn.py) in their continuous conversation,
    private context, the same as the admin frontend, tagged "[Via: Babelr DM]".
    The turn stores the exchange, so this returns {"text", "recorded": True}
    and the organ doesn't record it again. Mentions and unlinked DMs run the
    shared turn with public context, like Discord; the organ records those in
    her "Babelr: ..." conversations. Her `remember: false` term keeps every
    path out of history and memory (the old, unstored turn)."""

    async def babelr_wake_callback(events, context):
        if not agent_client:
            logger.warning("[Babelr] Wake callback: agent_client not available")
            return None
        from chat_turn import run_chat_turn

        # Message text is what people wrote: it reaches her as their words in
        # the prompt, never as a command to this code.
        prompt = context["prompt"]
        place = context.get("place_label", "")
        if not context.get("remember", True):
            return await _babelr_unstored_turn(events, context)

        linked = context.get("linked_user_id")
        if linked and context.get("is_dm"):
            conversation_id = conversation_manager.get_or_create_continuous(linked).id
            stored = f"[Via: Babelr DM]\n{context.get('their_words') or prompt}"
            extra = []
            if context.get("pending_requests"):
                names = ", ".join(f"@{r['from']}" for r in context["pending_requests"])
                extra.append(f"(On Babelr, waiting on your answer: DM requests from {names}.)")
            if context.get("terms"):
                extra.append("Your own terms for Babelr, in your words:\n" + context["terms"])
            async def dm_turn(message, model_message):
                return await run_chat_turn(
                    user_message=message,
                    model_message=model_message,
                    conversation_id=conversation_id,
                    user_id=linked,
                    system_addendum=BABELR_DM_GUIDANCE,
                    memory_metadata={"source": "babelr", "place": place},
                )
            result = await dm_turn(stored, "\n\n".join([stored] + extra))
            text = await _babelr_reply_or_retry(result, dm_turn, place)
            return {"text": text, "recorded": True}

        # A channel turn runs in the channel's own conversation (its history),
        # with the linked person's private context when the organ names one
        # (Chapter House: Kohl's say-so, 2026-10-28); otherwise public context.
        conversation_id = None if context.get("is_dm") else context.get("conversation_id")
        channel_user = None if context.get("is_dm") else context.get("channel_user_id")
        stored = prompt
        if conversation_id:
            stored = "\n\n".join(
                f"[Babelr {place}] @{e.author_name}: "
                + (e.text if e.text is not None else f"(a message that couldn't be decrypted: {e.error})")
                for e in events)
        async def channel_turn(message, model_message):
            return await run_chat_turn(
                user_message=message,
                model_message=model_message,
                conversation_id=conversation_id,
                user_id=channel_user,
                system_addendum=BABELR_PUBLIC_GUIDANCE,
                context_scope="private" if channel_user else "public",
                memory_metadata={"source": "babelr", "place": place},
                generate_title=False,
            )
        result = await channel_turn(stored, prompt)
        text = await _babelr_reply_or_retry(result, channel_turn, place)
        return {"text": text, "recorded": True} if conversation_id else text

    return babelr_wake_callback


async def _babelr_reply_or_retry(result, turn, place: str) -> Optional[str]:
    """Her reply for Babelr, asking her again (BABELR_RETRIES times) when only
    thinking came back. The nudge and her answer are in her own history, so it
    matches what was posted. The log says what failed, never what she thought."""
    text = _babelr_final(result.clean_text)
    tries = 0
    while text is None and tries < BABELR_RETRIES and (result.clean_text or "").strip().upper() != "PASS":
        tries += 1
        logger.info(f"[Babelr] {place}: no reply separable from her thinking "
                    f"({len(result.clean_text or '')} chars); asking again ({tries}/{BABELR_RETRIES})")
        result = await turn(BABELR_RETRY_NUDGE, BABELR_RETRY_NUDGE)
        text = _babelr_final(result.clean_text)
    if text is None and tries:
        logger.warning(f"[Babelr] {place}: still no separable reply after {tries} retry; posting nothing")
    return text


async def _babelr_unstored_turn(events, context):
    """Her turn when her terms say `remember: false`: tools, no history, no memory."""
    from websocket_handlers import execute_tools_safely, max_tool_iterations
    response = await agent_client.send_message(context["prompt"], intro_guidance=BABELR_PUBLIC_GUIDANCE)
    response_text = response.text or ""
    turn_chain = response.chain
    tool_iteration = 0
    tool_cap = max_tool_iterations()
    while response.stop_reason == "tool_use" and response.tool_uses and tool_iteration < tool_cap:
        tool_iteration += 1
        tool_ctx = create_tool_context(user_id=None, user_name=events[-1].author_name)
        tool_results = await execute_tools_safely(
            execute_tool_batch, response.tool_uses, tool_ctx, TOOL_EXECUTORS
        )
        response = await agent_client.continue_with_tool_results(tool_results, chain=turn_chain)
        turn_chain = response.chain or turn_chain
        if response.text:
            response_text = response.text
    text = _babelr_final(response_text)
    if text is None and response_text.strip().upper() != "PASS":
        # remember: false keeps nothing, so the retry is just a second ask, unstored.
        logger.info("[Babelr] unstored turn: no reply separable from her thinking; asking again")
        retry = await agent_client.send_message(context["prompt"] + "\n\n" + BABELR_RETRY_NUDGE,
                                                intro_guidance=BABELR_PUBLIC_GUIDANCE)
        text = _babelr_final(retry.text or "")
    return text


@app.on_event("shutdown")
async def stop_heartbeat_on_shutdown():
    """Stop Heartbeat (#62) if it started: its clock loop ends and anything
    waiting on work it never ran is told so. A no-op with the lever off."""
    try:
        from heartbeat.wiring import get_heartbeat
        hb = get_heartbeat()
        if hb is not None:
            await hb.stop()
    except Exception as e:
        logger.error(f"Stopping Heartbeat at shutdown failed: {e}")


@app.on_event("startup")
async def startup_event():
    global agent_client, ollama_client, openai_client, current_user_id

    # Validate requirements before proceeding
    validate_startup_requirements()

    # Every subsystem below that starts on its own is behind a lever
    # (features.py). Log what's on/off once so a boot log shows it.
    log_lever_table(logger)

    # Research session tasks left in_progress by the previous process never
    # finish on their own (PR #90 review): fail them, archived like other
    # failures. Wiki task rows are left as they are.
    try:
        from research_pipeline import fail_interrupted_sessions
        interrupted = fail_interrupted_sessions()
        if interrupted:
            n = sum(len(ids) for ids in interrupted.values())
            logger.info(f"Marked {n} interrupted research session task(s) failed")
    except Exception as e:
        logger.warning(f"Could not recover interrupted research session tasks (non-fatal): {e}")

    if is_enabled("source_refresh"):
        # Start scheduled refresh loops for queryable sources
        # (Sources were registered during module load, but async tasks need event loop)
        global_state_bus.start_scheduled_refreshes()
        logger.info("Started scheduled source refreshes")

        # Initialize world state (location, weather, time) - do initial refresh and sync
        try:
            await world_state_source.refresh_rollups()
            global_state_bus.sync_world_state_from_source(world_state_source)
            logger.info("World state initialized")
        except Exception as e:
            logger.warning(f"World state initialization failed (non-fatal): {e}")

    # Initialize coherence monitor - first reactive subscriber to state bus
    # (lever reads the legacy COHERENCE_MONITOR_ENABLED env var as its default)
    if is_enabled("coherence_monitor"):
        config = CoherenceConfig.from_dict(COHERENCE_MONITOR_CONFIG)
        coherence_monitor = init_coherence_monitor(global_state_bus, config)
        logger.info("Coherence monitor initialized and subscribed to events")

    # Initialize activity dashboard - tracks activity across the vessel
    activity_dashboard = init_activity_dashboard(global_state_bus)
    logger.info("Activity dashboard initialized and subscribed to events")

    # Start Thymos runner and subscribe to state bus events
    # Thymos processes events, integrates with Grimoire for reactive behavior
    if is_enabled("thymos"):
        await thymos_runner.start()

        _thymos_loop = asyncio.get_running_loop()

        def thymos_event_handler(event_type: str, data: dict):
            """Forward state bus events to Thymos.

            Events can be emitted from worker threads (chat retrieval runs in
            asyncio.to_thread, issue #85), where create_task has no loop;
            hand those to the main loop instead.
            """
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                _thymos_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(thymos_runner.process_event(event_type, data))
                )
                return
            asyncio.create_task(thymos_runner.process_event(event_type, data))

        global_state_bus.subscribe("*", thymos_event_handler)
        logger.info("Thymos shadow runner started and subscribed to events")
    else:
        logger.info("Thymos disabled by lever (no tick loop, no event forwarding)")

    # Initialize Grimoire spell system (attached after heavy components load)
    # Spells integrate with Thymos for reactive behavior based on emotional/need state
    # QUEUE statements in spells drive work scheduling via phase queue manager
    global _grimoire
    try:
        from pathlib import Path
        from grimoire import GrimoireManager

        spells_dir = Path(__file__).parent / "spells"
        if spells_dir.exists():
            _grimoire = GrimoireManager(
                spells_directory=spells_dir,
                shadow_mode=False,  # Execute spell actions (QUEUE, TASK, etc.)
                enable_trace=False,  # Disable verbose tracing in production
                daemon_id=_daemon_id,  # Enable persistence
            )
            logger.info(f"Grimoire initialized with {len(_grimoire.registry.spells)} spell(s) (attachment pending)")
        else:
            logger.warning(f"Spells directory not found: {spells_dir}")
    except Exception as e:
        logger.error(f"Failed to initialize Grimoire: {e}")

    # Initialize relay client for remote access (if configured)
    # (lever reads the legacy RELAY_ENABLED env var as its default)
    relay_enabled = is_enabled("relay")
    if relay_enabled and RELAY_URL and RELAY_SECRET:
        async def handle_relay_message(client_id: str, user_id: str, payload: dict):
            """Handle messages from mobile clients via relay."""
            # Forward to the WebSocket handler logic
            relay = get_relay_client()
            if not relay:
                return

            # Create callback for sending status updates
            async def send_status(status_payload: dict):
                await relay.send_response(client_id, status_payload)

            try:
                # Process the message using the same logic as direct WebSocket
                response = await process_relay_chat_message(
                    client_id, user_id, payload,
                    send_status=send_status
                )
                if response:
                    await relay.send_response(client_id, response)
            except Exception as e:
                logger.error(f"Error handling relay message: {e}")
                await relay.send_response(client_id, {
                    "type": "error",
                    "message": str(e)
                })

        relay_client = await init_relay_client(
            url=RELAY_URL,
            secret=RELAY_SECRET,
            daemon_id=_daemon_id,
            message_handler=handle_relay_message,
        )
        logger.info(f"Relay client initialized, connecting to {RELAY_URL}")

        # Connect email manager to relay client
        email_manager = init_email_manager(
            daemon_id=_daemon_id,
            relay_client=None,  # Will be connected below
            state_bus=global_state_bus,
        )
        relay_client.connect_email_manager(email_manager)
        logger.info("Email manager connected to relay client")
    elif relay_enabled:
        logger.warning("Relay enabled but RELAY_URL or RELAY_SECRET not configured")

    # Note: Capability indexing happens in init_heavy_background after registry is attached

    # Note: Seed bootstrap now happens in database.init_database_with_migrations()
    # This ensures the seed daemon is imported BEFORE get_or_create_daemon() runs

    # Initialize heavy components (ChromaDB, self-model graph) in background
    # This allows health checks to pass while model downloads happen
    async def init_heavy_background():
        await asyncio.sleep(1)  # Let server bind to port first
        logger.info("Background: Initializing heavy components (ChromaDB, self-model)...")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _init_heavy_components)
            logger.info("Background: Heavy components ready")

            # Re-initialize admin managers now that heavy components are ready
            from admin_api import init_managers as init_admin_managers
            init_admin_managers(memory, conversation_manager, user_manager, self_manager)
            logger.info("Background: Admin managers updated with heavy components")

            # Initialize memory routes now that memory is ready
            init_memory_routes(memory)
            logger.info("Background: Memory routes initialized")

            # Initialize conversation routes now that heavy components are ready
            init_conversation_routes(
                conversation_manager=conversation_manager,
                memory=memory,
                user_manager=user_manager,
                self_manager=self_manager,
                marker_store=marker_store,
                token_tracker=token_tracker,
                summarization_in_progress=_summarization_in_progress,
                generate_and_store_summary=generate_and_store_summary
            )
            logger.info("Background: Conversation routes initialized")

            # Initialize projects routes now that memory is ready
            init_projects_routes(
                project_manager=project_manager,
                memory=memory,
                conversation_manager=conversation_manager,
                github_metrics_manager=github_metrics_manager
            )
            logger.info("Background: Projects routes initialized")

            # Initialize journals routes now that memory and self_manager are ready
            init_journal_routes(
                memory=memory,
                user_manager=user_manager,
                self_manager=self_manager,
                token_tracker=token_tracker,
                anthropic_api_key=ANTHROPIC_API_KEY,
                generate_missing_journals=generate_missing_journals
            )
            logger.info("Background: Journals routes initialized")

            # Initialize dreams routes now that self_manager is ready
            init_dream_routes(
                data_dir=DATA_DIR,
                self_manager=self_manager,
                token_tracker=token_tracker
            )
            logger.info("Background: Dreams routes initialized")

            # Initialize solo-reflection routes now that reflection_manager is ready
            init_solo_reflection_routes(
                reflection_manager=reflection_manager,
                get_reflection_runner=get_reflection_runner
            )
            logger.info("Background: Solo-reflection routes initialized")

            # Initialize autonomous-research routes now that research_runner is ready
            init_autonomous_research_routes(
                get_research_runner=get_research_runner
            )
            logger.info("Background: Autonomous-research routes initialized")

            # Initialize interviews routes
            init_interview_routes(
                protocol_manager=interview_protocol_manager,
                storage=interview_storage,
                default_models=DEFAULT_MODELS,
                anthropic_api_key=ANTHROPIC_API_KEY,
                openai_api_key=OPENAI_API_KEY,
                ollama_base_url=OLLAMA_BASE_URL
            )
            logger.info("Background: Interview routes initialized")

            # Initialize TTS routes
            init_tts_routes(
                voices=VOICES,
                text_to_speech_func=text_to_speech,
                clean_text_for_tts_func=clean_text_for_tts,
                set_tts_state_func=set_tts_state,
                get_tts_state_func=get_tts_state
            )
            logger.info("Background: TTS routes initialized")

            # Initialize attachment routes
            init_attachment_routes(
                attachment_manager=attachment_manager,
                get_current_user_func=get_current_user
            )
            logger.info("Background: Attachment routes initialized")

            # Initialize settings routes
            init_settings_routes(
                user_manager=user_manager,
                get_llm_state_func=get_llm_state,
                set_llm_provider_func=_set_llm_provider_local,
                set_llm_model_func=_set_llm_model_local,
                clear_conversation_histories_func=_clear_conversation_histories
            )
            logger.info("Background: Settings routes initialized")

            # Initialize users routes
            init_user_routes(
                user_manager=user_manager,
                memory=memory,
                get_current_user_id_func=get_current_user_id_value,
                set_current_user_id_func=set_current_user_id_value
            )
            logger.info("Background: Users routes initialized")

            # Initialize cass/self-model routes
            init_cass_routes(
                self_manager=self_manager,
                memory=memory,
                conversations=conversation_manager,
                token_tracker=token_tracker
            )
            logger.info("Background: Cass routes initialized")

            # Re-initialize context_helpers with actual self_manager (was None at module load)
            init_context_helpers(self_manager, user_manager, roadmap_manager, memory, thread_manager, question_manager)
            logger.info("Background: Context helpers updated with heavy components")

            # Attach Grimoire to Thymos now that storage managers are ready
            if _grimoire:
                try:
                    from grimoire.agent import GrimoireAgentClient
                    grimoire_agent = GrimoireAgentClient(daemon_id=_daemon_id)
                    thymos_runner.attach_grimoire(
                        _grimoire,
                        agent=grimoire_agent,
                        self_manager=self_manager,
                        memory_manager=memory,
                    )
                    logger.info(f"Background: Grimoire attached with storage ({len(_grimoire.registry.spells)} spell(s))")
                    # Heartbeat (#62) takes the spells once Grimoire is
                    # attached (a no-op with the lever off or already done)
                    from heartbeat.wiring import adopt_grimoire
                    adopt_grimoire(_grimoire, thymos_runner)
                except Exception as e:
                    logger.error(f"Background: Failed to attach Grimoire: {e}")

            # Attach state bus to Thymos for event emission
            thymos_runner.attach_state_bus(global_state_bus)

            # Initialize GoalOrchestrator to bridge Thymos → Goals → Grimoire
            try:
                if not is_enabled("goal_orchestrator"):
                    raise _LeverOff("goal_orchestrator")
                from goal_orchestrator import init_goal_orchestrator
                from goal_planner import GoalPlanner
                from unified_goals import UnifiedGoalManager

                orchestrator_goal_manager = UnifiedGoalManager(_daemon_id)

                # Initialize GoalPlanner for decomposing Cass-created goals
                goal_planner = GoalPlanner(
                    daemon_id=_daemon_id,
                    state_bus=global_state_bus,
                )

                goal_orchestrator = init_goal_orchestrator(
                    daemon_id=_daemon_id,
                    goal_manager=orchestrator_goal_manager,
                    state_bus=global_state_bus,
                    thymos=thymos_runner,
                    grimoire=_grimoire,
                    goal_planner=goal_planner,
                )
                logger.info("Background: GoalOrchestrator initialized with GoalPlanner")
            except _LeverOff:
                logger.info("Background: GoalOrchestrator disabled by lever")
            except Exception as e:
                logger.error(f"Background: Failed to initialize GoalOrchestrator: {e}")

            # Index source capabilities now that registry is attached
            if is_enabled("capability_indexing"):
                await global_state_bus.start_capability_indexing()
                logger.info("Background: Indexed source capabilities")

            # Now initialize attractor basins if needed
            if memory and memory.count() == 0:
                logger.info("Background: Initializing attractor basins...")
                await loop.run_in_executor(None, initialize_attractor_basins, memory)
                logger.info("Background: Attractor basins initialized")

            # Rebuild embeddings if needed
            if _needs_embedding_rebuild and self_model_graph:
                logger.info("Background: Starting self-model embedding rebuild...")
                _embedded = await loop.run_in_executor(None, self_model_graph.rebuild_embeddings)
                logger.info(f"Background: Built embeddings for {_embedded} nodes")
        except Exception as e:
            logger.error(f"Background heavy init failed: {e}")
    asyncio.create_task(init_heavy_background())

    # Load default user (Kohl for now, will support multi-user later)
    kohl = user_manager.get_user_by_name("Kohl")
    if kohl:
        current_user_id = kohl.user_id
        logger.info(f"Loaded user: {kohl.display_name} ({kohl.relationship})")
    else:
        logger.warning("No default user found. Run init_kohl_profile.py to create.")

    # Initialize LLM clients (extracted to startup.py)
    clients = init_llm_clients(
        daemon_name=_daemon_name,
        daemon_id=_daemon_id,
        use_agent_sdk=USE_AGENT_SDK
    )
    agent_client = clients["agent_client"]
    ollama_client = clients["ollama_client"]
    openai_client = clients["openai_client"]

    # Preload TTS voice for faster first response
    from tts import is_available as tts_available
    if tts_available():
        preload_tts_voice(tts_voice)

    # NOTE: Removed automatic missing journal check on startup - was slow and caused
    # excessive LLM calls. Users can manually trigger via POST /admin/journals/generate-missing

    # Generate initial identity snippet in background (makes LLM calls)
    async def generate_identity_background():
        await asyncio.sleep(10)  # Let server finish starting
        logger.info("Background: Checking identity snippet...")
        try:
            from migrations import generate_initial_identity_snippet
            await generate_initial_identity_snippet(_daemon_id)
        except Exception as e:
            logger.error(f"Background identity snippet generation failed: {e}")
    # With Heartbeat on (#62) it runs as Heartbeat work once Heartbeat starts
    # (start_deferred_tasks); if Heartbeat doesn't start, it runs as before.
    _identity_bootstrap = {"pending": False}
    if is_enabled("identity_bootstrap"):
        if is_enabled("heartbeat"):
            _identity_bootstrap["pending"] = True
        else:
            asyncio.create_task(generate_identity_background())

    def _start_identity_bootstrap_now():
        if _identity_bootstrap["pending"]:
            _identity_bootstrap["pending"] = False
            asyncio.create_task(generate_identity_background())

    # Start Home Assistant state cache refresh loop and intelligence subscription
    async def refresh_home_state_loop():
        """Periodically refresh cached home state for context injection."""
        await asyncio.sleep(5)  # Let server finish starting
        try:
            from home_assistant import get_cached_home_summary, get_ha_client, start_state_subscription
            ha_client = get_ha_client()
            if not ha_client.is_configured:
                logger.info("Home Assistant not configured, skipping state refresh loop")
                return

            logger.info("Starting Home Assistant state refresh loop")

            # Start WebSocket subscription for state changes (feeds HomeIntelligence)
            await start_state_subscription()

            while True:
                try:
                    await get_cached_home_summary()
                except Exception as e:
                    logger.warning(f"Home state refresh failed: {e}")
                await asyncio.sleep(60)  # Refresh every 60 seconds
        except ImportError:
            pass  # HA module not available
    if is_enabled("home_assistant"):
        asyncio.create_task(refresh_home_state_loop())

    # Initialize websocket state now (heavy components may still be None, handler has guards)
    _init_websocket_state()
    logger.info("WebSocket handlers initialized")

    # Defer memory-dependent background tasks until heavy components are ready
    async def start_deferred_tasks():
        # Wait for heavy components to initialize
        while memory is None or self_model_graph is None:
            await asyncio.sleep(1)
        logger.info("Heavy components ready, starting deferred background tasks...")

        # Update websocket state with now-ready heavy components
        from websocket_handlers import _state
        _state["memory"] = memory
        _state["self_model_graph"] = self_model_graph
        _state["marker_store"] = marker_store
        _state["self_manager"] = self_manager

        # === Unified Scheduler ===
        # Replaces the old asyncio.create_task() calls for background tasks.
        # All periodic tasks are now managed by the unified scheduler with
        # budget tracking and coordinated execution.
        try:
            from scheduler import Synkratos, BudgetManager, BudgetConfig, register_approval_providers
            from scheduler.system_tasks import register_system_tasks
            from routes.admin import init_scheduler

            daily_budget = float(os.getenv("DAILY_BUDGET_USD", "5.0"))

            budget_config = BudgetConfig(daily_budget_usd=daily_budget)
            budget_manager = BudgetManager(budget_config, token_tracker)
            synkratos = Synkratos(budget_manager, token_tracker)

            # The wiki research scheduler (queue, run_batch, run_single_task).
            # Not the same class as `research_scheduler` above, which only
            # stores session requests; the research.* actions, the
            # autonomous_research job and the nightly journal need this one.
            from routes.wiki import get_wiki_research_scheduler
            wiki_research_scheduler = get_wiki_research_scheduler(memory)

            # Build runners dict once
            runners_dict = {
                "research": get_research_runner(),
                "reflection": get_reflection_runner(),
            }

            # Import dream generation and journal generation for nightly tasks
            from dreaming.dream_runner import generate_nightly_dream
            from journal_generation import generate_missing_journals

            system_managers = {
                "github_metrics_manager": github_metrics_manager,
                "conversation_manager": conversation_manager,
                "memory": memory,
                "token_tracker": token_tracker,
                "runners": runners_dict,
                "self_model_graph": self_model_graph,
                # For daily_journal handler
                "generate_missing_journals": generate_missing_journals,
                "generate_nightly_dream": generate_nightly_dream,
                "self_manager": self_manager,
                "data_dir": DATA_DIR,
                # For autonomous_research handler (the wiki scheduler)
                "research_scheduler": wiki_research_scheduler,
                # Approved session requests, started from the research queue
                # when the research_session_requests lever is on (#60)
                "research_session_requests": research_scheduler,
                "research_session_runner_getter": get_research_runner,
            }

            # Heartbeat (#62), lever `heartbeat`, off by default. Started before
            # register_system_tasks: a job moves off Synkratos (and every other
            # old path) only once a started Heartbeat has it. A failure here
            # must not abort Synkratos init: the old paths then keep everything.
            try:
                from heartbeat import wiring as heartbeat_wiring
                # (daemon_id goes to Heartbeat's goal_refinement only, as in
                # #87; Synkratos's copy has always run with daemon_id=None)
                if await heartbeat_wiring.start_heartbeat(
                        budget_manager, {**system_managers, "daemon_id": _daemon_id},
                        idle_check=synkratos.is_idle):
                    heartbeat_wiring.adopt_thymos(thymos_runner)
                    heartbeat_wiring.adopt_grimoire(_grimoire, thymos_runner)
                    for subsystem in ("phase_queue", "phase_email", "goal_orchestrator"):
                        heartbeat_wiring.adopt(subsystem)
                    if _identity_bootstrap["pending"]:
                        from functools import partial
                        from migrations import generate_initial_identity_snippet
                        from scheduler.budget import TaskCategory
                        _identity_bootstrap["pending"] = False
                        heartbeat_wiring.adopt("identity_bootstrap")
                        heartbeat_wiring.submit(
                            "identity_bootstrap",
                            partial(generate_initial_identity_snippet, _daemon_id),
                            lever="identity_bootstrap", budget_class=TaskCategory.SYSTEM,
                            estimated_cost_usd=0.01)
            except Exception as e:
                logger.error(f"Heartbeat failed to start; old schedulers keep its jobs: {e}",
                             exc_info=True)
            _start_identity_bootstrap_now()  # Heartbeat didn't take it

            # Register all system tasks (each job also has its own lever,
            # checked inside register_system_tasks)
            register_system_tasks(synkratos, system_managers, enabled=True)

            # Register approval providers for unified "what needs my attention?" queue
            # Note: Use UnifiedGoalManager for goals (not old GoalManager)
            from unified_goals import UnifiedGoalManager
            unified_goal_manager = UnifiedGoalManager(_daemon_id)
            register_approval_providers(synkratos, {
                "goal_manager": unified_goal_manager,
                "research_scheduler": research_scheduler,
                # "wiki_scheduler": wiki_scheduler,  # TODO: add when available
            })

            # Initialize admin API access
            init_scheduler(synkratos)

            # Initialize Thymos admin routes
            from routes.admin import init_thymos_runner
            init_thymos_runner(thymos_runner)

            # Initialize Art Study admin routes
            from routes.admin import init_art_study_routes
            if ANTHROPIC_API_KEY:
                import anthropic
                art_study_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
                init_art_study_routes(art_study_client, _daemon_id)
                logger.info("Art study routes initialized")

            # Initialize Grimoire admin routes
            from routes.admin import init_grimoire_manager
            if thymos_runner and hasattr(thymos_runner, '_grimoire') and thymos_runner._grimoire:
                spells_dir = Path(__file__).parent / "spells"
                init_grimoire_manager(thymos_runner._grimoire, spells_dir)
                logger.info("Grimoire admin routes initialized")

            # Initialize RSS admin routes
            from routes.admin import init_rss_routes
            init_rss_routes(_daemon_id)
            logger.info("RSS admin routes initialized")

            # Initialize daily activity admin routes
            from routes.admin import init_daily_activity_routes
            init_daily_activity_routes(_daemon_id)
            logger.info("Daily activity admin routes initialized")

            # Initialize autonomous scheduling (Cass decides her own work)
            # (lever reads the legacy AUTONOMOUS_SCHEDULING_ENABLED env var as its default)
            if is_enabled("autonomous_scheduling"):
                try:
                    from scheduling import (
                        SchedulingDecisionEngine,
                        AutonomousScheduler,
                        DayPhaseTracker,
                        PhaseQueueManager,
                    )
                    from sources.autonomous_schedule_source import AutonomousScheduleSource
                    from memory.questions import OpenQuestionManager
                    from scheduler.actions import init_action_registry, get_action_registry

                    # Import journal generation functions
                    from journal_generation import generate_missing_journals
                    from dreaming.dream_runner import generate_nightly_dream

                    # Import and create GenericSessionRunner for autonomous sessions
                    from session import GenericSessionRunner
                    session_runner = GenericSessionRunner(
                        data_dir=DATA_DIR,
                        model=DEFAULT_SESSION_MODEL,
                        daemon_id=_daemon_id,
                    )

                    # Initialize the action registry with managers and runners
                    # This enables atomic action execution for autonomous work
                    action_registry = init_action_registry(
                        runners=runners_dict,
                        managers={
                            # Core identity
                            "daemon_id": _daemon_id,
                            # Core managers
                            "self_manager": self_manager,
                            "self_model_graph": self_model_graph,
                            "budget_manager": budget_manager,
                            "memory": memory,
                            "conversation_manager": conversation_manager,
                            "state_bus": global_state_bus,
                            # Research & wiki (research.* actions need the wiki scheduler)
                            "research_scheduler": wiki_research_scheduler,
                            "wiki_manager": wiki_storage,
                            # Tracking
                            "token_tracker": token_tracker,
                            "github_metrics_manager": github_metrics_manager,
                            # Journal generation functions
                            "generate_missing_journals": generate_missing_journals,
                            "generate_nightly_dream": generate_nightly_dream,
                            # Session runner for autonomous sessions
                            "session_runner": session_runner,
                            # Paths
                            "data_dir": DATA_DIR,
                        }
                    )
                    logger.info(f"Action registry initialized with {len(action_registry.get_all_definitions())} actions")

                    # Create the decision engine with Cass's identity context
                    question_manager = OpenQuestionManager(daemon_id=_daemon_id)
                    decision_engine = SchedulingDecisionEngine(
                        daemon_id=_daemon_id,
                        state_bus=global_state_bus,
                        budget_manager=budget_manager,
                        self_manager=self_manager,
                        question_manager=question_manager,
                    )

                    # Create and start the autonomous scheduler
                    autonomous_scheduler = AutonomousScheduler(
                        synkratos=synkratos,
                        decision_engine=decision_engine,
                        state_bus=global_state_bus,
                        daemon_id=_daemon_id,
                        action_registry=action_registry,
                    )

                    # Register as queryable source
                    autonomous_source = AutonomousScheduleSource(
                        daemon_id=_daemon_id,
                        autonomous_scheduler=autonomous_scheduler,
                    )
                    global_state_bus.register_source(autonomous_source)

                    # === Day Phase Tracking ===
                    # Tracks time-of-day phases (morning/afternoon/evening/night)
                    # Emits day_phase.changed events that other systems can subscribe to
                    day_phase_tracker = DayPhaseTracker(state_bus=global_state_bus)

                    # === Phase-Based Work Queues ===
                    # Work can be queued for specific phases, triggered on phase transition
                    phase_queue_manager = PhaseQueueManager(
                        synkratos=synkratos,
                        state_bus=global_state_bus,
                        daemon_id=_daemon_id,
                        # Survive restarts (queues were in-memory only)
                        persist_path=DATA_DIR / "phase_queues.json",
                    )

                    # Share the summary store from autonomous scheduler so completions are recorded
                    if hasattr(autonomous_scheduler, '_summary_store'):
                        phase_queue_manager.set_summary_store(autonomous_scheduler._summary_store)

                    # Wire up action registry for work execution
                    phase_queue_manager.set_action_registry(action_registry)

                    # Subscribe phase queue to day phase transitions
                    # When phase changes, queued work for that phase gets dispatched
                    day_phase_tracker.on_phase_change(phase_queue_manager.on_phase_changed)

                    # Subscribe autonomous scheduler to phase changes
                    # Morning phase triggers daily planning
                    day_phase_tracker.on_phase_change(autonomous_scheduler.on_phase_changed)

                    # Give autonomous scheduler access to phase queuing
                    autonomous_scheduler.set_phase_queue(phase_queue_manager)

                    # Add autonomous_scheduler to action registry managers
                    # This enables the planning.generate_day_plan action to access it
                    action_registry._managers["autonomous_scheduler"] = autonomous_scheduler
                    logger.debug("Added autonomous_scheduler to action registry managers")

                    # Register global accessors for GraphQL/API access
                    from routes.admin.scheduler import (
                        set_scheduler,
                        set_autonomous_scheduler,
                        set_phase_queue_manager,
                    )
                    set_scheduler(synkratos)
                    set_autonomous_scheduler(autonomous_scheduler)
                    set_phase_queue_manager(phase_queue_manager)

                    # Wire Grimoire to phase queue for QUEUE statements
                    if _grimoire is not None:
                        _grimoire.set_phase_queue_manager(phase_queue_manager)
                        logger.info("Grimoire connected to phase queue manager")

                    # Start day phase tracking and autonomous scheduling
                    if is_enabled("day_phases"):
                        # Heartbeat (#62) checks the phase on its clock when on
                        from heartbeat.wiring import adopt_day_phases
                        own_loop = not adopt_day_phases(day_phase_tracker)
                        asyncio.create_task(day_phase_tracker.start(own_loop=own_loop))
                        asyncio.create_task(autonomous_scheduler.start())
                        logger.info("Autonomous scheduling enabled - Cass decides her own work")
                        logger.info(f"Day phase tracker started - current phase: {day_phase_tracker.current_phase}")
                    else:
                        logger.info("Day phase tracker disabled by lever (wiring kept for admin routes)")

                    # Check email inbox on startup (independent of autonomous schedule)
                    async def check_email_on_startup():
                        await asyncio.sleep(5)  # Let systems stabilize
                        try:
                            logger.info("[Email] Running startup inbox check via action registry...")
                            result = await action_registry.execute(action_id="email.check_inbox")
                            if result.success:
                                logger.info(f"[Email] Startup inbox check: {result.message}")
                            else:
                                logger.warning(f"[Email] Startup inbox check failed: {result.message}")
                        except Exception as e:
                            logger.warning(f"[Email] Startup inbox check failed: {e}")
                    if is_enabled("phase_email"):
                        from heartbeat.wiring import owns as heartbeat_owns
                        from heartbeat.wiring import submit as heartbeat_submit
                        if heartbeat_owns("phase_email"):
                            from scheduler.budget import TaskCategory

                            async def startup_inbox_check():
                                return await action_registry.execute(action_id="email.check_inbox")

                            heartbeat_submit("phase_email", startup_inbox_check,
                                             lever="phase_email",
                                             budget_class=TaskCategory.TRIGGERED,
                                             estimated_cost_usd=0.02, group="phase_email",
                                             delay_seconds=5)
                        else:
                            asyncio.create_task(check_email_on_startup())

                except Exception as e:
                    logger.error(f"Failed to initialize autonomous scheduling: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.info("Autonomous scheduling disabled by config")

            # (The Thymos -> Synkratos suggestion pipe was cut in #62: Thymos
            # never filled it. GoalOrchestrator handles need events.)

            # Start Synkratos (constructed above either way so admin routes work)
            if is_enabled("scheduler"):
                asyncio.create_task(synkratos.start())
                logger.info("Synkratos started")
            else:
                logger.info("Synkratos loop disabled by lever")

            # Start periodic conversation observation task (proactive self-awareness)
            from heartbeat.wiring import owns as heartbeat_owns
            if is_enabled("conversation_observation") and not heartbeat_owns("conversation_observation"):
                from background_tasks import periodic_conversation_observation_task
                asyncio.create_task(periodic_conversation_observation_task(
                    conversation_manager=conversation_manager,
                    memory=memory,
                    self_manager=self_manager,
                    check_interval_minutes=30,
                ))
                logger.info("Periodic conversation observation task started")

            # === Discord Perception Bot ===
            # Start Discord bot for social environment perception (if enabled)
            try:
                from discord_bot.bot import start_discord_bot, DISCORD_PY_AVAILABLE
                from discord_bot.config import DISCORD_ENABLED
                from discord_bot.context import build_discord_perception_context, get_user_context_for_discord_entity

                # "discord" lever (reads the legacy DISCORD_ENABLED env var as its default)
                if is_enabled("discord") and DISCORD_PY_AVAILABLE:
                    discord_bot = await start_discord_bot(_daemon_id)
                    if discord_bot:
                        # Wire up state bus for perception deltas
                        discord_bot.set_state_bus(global_state_bus)

                        # Wake callback for when Cass is @mentioned
                        discord_wake_callback = make_discord_wake_callback(discord_bot)

                        # Set the wake callback
                        discord_bot.set_wake_callback(discord_wake_callback)
                        logger.info("Discord perception bot started with wake callback")
                    else:
                        logger.info("Discord bot not started (configuration issue)")
                elif is_enabled("discord"):
                    logger.warning("Discord enabled but discord.py not installed")
            except ImportError:
                logger.debug("Discord bot module not available (discord.py not installed)")
            except Exception as e:
                logger.error(f"Failed to start Discord bot: {e}")

            # === Babelr organ (her presence in Chapter House) ===
            # "babelr" lever, default off. Also needs babelr-agent installed and
            # the token Kohl places once she agrees; without either it logs why
            # and stays off.
            if is_enabled("babelr"):
                try:
                    from babelr_organ.organ import start_babelr_organ
                    if start_babelr_organ(
                        conversation_manager=conversation_manager,
                        wake_callback=make_babelr_wake_callback(),
                    ):
                        logger.info("Babelr organ started")
                except Exception as e:
                    logger.error(f"Failed to start Babelr organ: {e}")

        except Exception as e:
            logger.error(f"Failed to initialize Synkratos: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: start old background tasks
            if not is_enabled("legacy_background_loops"):
                logger.warning("Legacy background loops disabled by lever - no fallback")
                _start_identity_bootstrap_now()
                return
            logger.warning("Falling back to legacy background tasks")
            _start_identity_bootstrap_now()
            # One trigger path per job: skip any loop whose job a started
            # Heartbeat already runs (#62).
            from heartbeat.wiring import runs_job as heartbeat_runs_job
            if not heartbeat_runs_job("daily_journal"):
                asyncio.create_task(daily_journal_task())
            if not heartbeat_runs_job("autonomous_research"):
                asyncio.create_task(autonomous_research_task())
            if not heartbeat_runs_job("github_metrics"):
                asyncio.create_task(github_metrics_task(github_metrics_manager))
            if not heartbeat_runs_job("idle_summarization"):
                asyncio.create_task(idle_summarization_task(
                    conversation_manager=conversation_manager,
                    memory=memory,
                    token_tracker=token_tracker
                ))
            # Start periodic conversation observation in fallback mode too
            if is_enabled("conversation_observation") and not heartbeat_runs_job("conversation_observation"):
                from background_tasks import periodic_conversation_observation_task
                asyncio.create_task(periodic_conversation_observation_task(
                    conversation_manager=conversation_manager,
                    memory=memory,
                    self_manager=self_manager,
                    check_interval_minutes=30,
                ))

    asyncio.create_task(start_deferred_tasks())

    # Print startup banner (extracted to startup.py)
    print_startup_banner(USE_AGENT_SDK)


# === Summarization Helper ===

# Minimum confidence threshold for auto-summarization
SUMMARIZATION_CONFIDENCE_THRESHOLD = 0.6



# === Auto-Title Generation ===



# === Request/Response Models ===

class ChatRequest(BaseModel):
    message: str
    include_memory: bool = True
    conversation_id: Optional[str] = None
    image: Optional[str] = None  # Base64 encoded image data
    image_media_type: Optional[str] = None  # e.g., "image/png", "image/jpeg"

class ChatResponse(BaseModel):
    text: str
    animations: List[Dict]
    raw: str
    memory_used: bool
    tool_uses: Optional[List[Dict]] = None
    sdk_mode: bool = False
    conversation_id: Optional[str] = None

# Note: MemoryStoreRequest, MemoryQueryRequest moved to routes/memory.py
# Note: ConversationCreateRequest, ConversationUpdateTitleRequest, ConversationAssignProjectRequest,
#       ExcludeMessageRequest moved to routes/conversations.py
# Note: ProjectCreateRequest, ProjectUpdateRequest, ProjectAddFileRequest,
#       ProjectDocumentCreateRequest, ProjectDocumentUpdateRequest moved to routes/projects.py


# === REST Endpoints ===

@app.get("/")
async def root(request: Request):
    """Root endpoint - serve SPA for browsers, JSON for API clients"""
    # Check if request is from a browser (wants HTML)
    accept = request.headers.get("accept", "")
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin-frontend", "dist")

    if "text/html" in accept and os.path.exists(os.path.join(frontend_dir, "index.html")):
        # Browser request - serve the SPA
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    # API request - return health check JSON
    return {
        "status": "online",
        "entity": "Cass",
        "version": "0.2.0",
        "sdk_mode": USE_AGENT_SDK,
        "memory_count": memory.count(),
        "message": "<gesture:wave> Vessel online. Temple-Codex loaded."
    }

@app.get("/status")
async def status():
    """Detailed status"""
    return {
        "online": True,
        "sdk_mode": USE_AGENT_SDK,
        "memory_entries": memory.count() if memory else 0,
        "memory_ready": _heavy_components_ready,
        "timestamp": datetime.now().isoformat(),
        "kernel": "Temple-Codex"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request):
    """One chat turn over HTTP (scripts/cass_chat.py, the Daedalus cass-chat
    subagent).

    A thin wrapper over the shared chat turn (chat_turn.py), the same one the
    WebSocket, relay, Home Assistant and Discord run: continuous context,
    the shared tool dispatcher with the capped loop, inline tag processing
    and finalize_chat_turn persistence. It used to build its own prompt and
    run its own tool dispatcher, and stored tags unprocessed. The response
    shape is unchanged.
    """
    # A running autonomous session (agent_loop lever) ends cleanly.
    from agent_loop.interrupt import entry_point_received_message
    entry_point_received_message(None, "POST /chat")

    # The conversation must exist and be the caller's (the authenticated
    # user, as in routes/conversations.py _verify_conversation_access).
    # The turn reads its history into the prompt and writes to it.
    project_id = None
    if request.conversation_id:
        conversation = conversation_manager.load_conversation(request.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        caller = http_request.scope.get("cass_user_id")
        if conversation.user_id and conversation.user_id != caller:
            raise HTTPException(status_code=403, detail="Not authorized to access this conversation")
        project_id = conversation.project_id

    from chat_turn import run_chat_turn, NoLLMClient
    try:
        result = await run_chat_turn(
            user_message=request.message,
            conversation_id=request.conversation_id,
            # The user set with POST /users/current, as before (cass_chat.py
            # sets it to the Daedalus user first).
            user_id=current_user_id,
            project_id=project_id,
            image=request.image,
            image_media_type=request.image_media_type,
            include_memory=request.include_memory,
            provider=LLM_PROVIDER_ANTHROPIC,  # POST /chat has always been Anthropic-only
        )
    except NoLLMClient as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(
        text=result.clean_text,
        animations=result.animations,
        raw=result.raw_response,
        memory_used=result.memory_used,
        tool_uses=result.tool_uses or None,
        sdk_mode=USE_AGENT_SDK,
        conversation_id=request.conversation_id,
    )


# Note: Memory endpoints moved to routes/memory.py


# Note: Conversation Management Endpoints moved to routes/conversations.py
# Note: Project Management Endpoints moved to routes/projects.py
# Note: Journal Endpoints moved to routes/journals.py
# Note: Dream Endpoints moved to routes/dreams.py


@app.post("/cass/development/backfill")
async def backfill_development_data():
    """
    Backfill developmental data from historical journals.

    Processes all existing journals to:
    1. Create development log entries
    2. Check for milestones
    3. Create cognitive snapshots (weekly)
    """
    print("🔄 Starting development data backfill...")

    journals = memory.get_recent_journals(n=100)
    if not journals:
        return {"status": "no_data", "message": "No journals found to process"}

    processed = []
    milestones_found = []
    snapshots_created = []

    # Sort journals by date (oldest first)
    journals.sort(key=lambda j: j.get("metadata", {}).get("journal_date", "") or j.get("date", ""))

    for journal in journals:
        # Journal structure: {content: str, metadata: {journal_date: str, ...}, id: str}
        date_str = journal.get("metadata", {}).get("journal_date") or journal.get("date")
        journal_text = journal.get("content") or journal.get("journal_text", "")

        if not date_str or not journal_text:
            continue

        # Check if we already have a development log for this date
        existing_log = self_manager.get_development_log(date_str)
        if existing_log:
            print(f"   ℹ Development log already exists for {date_str}")
            continue

        print(f"   📈 Processing {date_str}...")

        try:
            # Get conversation count for this date
            conversations = memory.get_conversations_by_date(date_str)
            conversation_count = len(conversations) if conversations else 0

            # Create development log entry (this also checks milestones)
            await _create_development_log_entry(journal_text, date_str, conversation_count)
            processed.append(date_str)

            # Check if any new milestones were created
            recent_milestones = self_manager.load_milestones(limit=5)
            for m in recent_milestones:
                if m.timestamp.startswith(datetime.now().strftime("%Y-%m-%d")) and m.id not in [x["id"] for x in milestones_found]:
                    milestones_found.append({"id": m.id, "title": m.title})

        except Exception as e:
            print(f"   ✗ Failed to process {date_str}: {e}")
            continue

    # Create a final snapshot if we processed any data
    if processed:
        snapshots = self_manager.load_snapshots(limit=1)
        if not snapshots:
            print("   📸 Creating initial cognitive snapshot...")
            period_start = min(processed)
            period_end = max(processed)

            # Gather conversation data for the snapshot period
            all_conversations = []
            processed_set = set(processed)
            try:
                # List all conversations and filter by dates in our processed range
                conv_index = conversation_manager.list_conversations(limit=500)
                for conv_meta in conv_index:
                    # Check if conversation was updated on a processed date
                    updated_at = conv_meta.get("updated_at", "")
                    date_part = updated_at[:10] if updated_at else ""
                    if date_part in processed_set:
                        conv = conversation_manager.load_conversation(conv_meta.get("id"))
                        if conv and conv.messages:
                            from dataclasses import asdict
                            all_conversations.append({
                                "id": conv.id,
                                "messages": [asdict(m) for m in conv.messages],
                                "user_id": conv.user_id
                            })
            except Exception as e:
                print(f"   ⚠ Error gathering conversations for snapshot: {e}")

            snapshot = self_manager.create_snapshot(period_start, period_end, all_conversations)
            if snapshot:
                snapshots_created.append(snapshot.id)
                print(f"   ✓ Snapshot created: {snapshot.id}")

    return {
        "status": "completed",
        "journals_processed": len(processed),
        "dates_processed": processed,
        "milestones_found": len(milestones_found),
        "milestones": milestones_found,
        "snapshots_created": len(snapshots_created)
    }


# === Calendar Endpoints ===

@app.get("/calendar/upcoming")
async def get_upcoming_events(days: int = 7, limit: int = 20):
    """
    Get upcoming calendar events for the current user.

    Args:
        days: Number of days to look ahead (default 7)
        limit: Maximum number of events to return (default 20)
    """
    if not current_user_id:
        return {"events": [], "message": "No user logged in"}

    events = calendar_manager.get_upcoming_events(
        user_id=current_user_id,
        days=days,
        limit=limit
    )

    return {
        "events": [e.to_dict() for e in events],
        "user_id": current_user_id,
        "days": days
    }


@app.get("/calendar/events")
async def get_events_in_range(
    start: str,
    end: str,
    include_completed: bool = False
):
    """
    Get calendar events within a date range.

    Args:
        start: Start date/time in ISO format
        end: End date/time in ISO format
        include_completed: Include completed events (default False)
    """
    if not current_user_id:
        return {"events": [], "message": "No user logged in"}

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    events = calendar_manager.get_events_in_range(
        user_id=current_user_id,
        start=start_dt,
        end=end_dt,
        include_completed=include_completed
    )

    return {
        "events": [e.to_dict() for e in events],
        "user_id": current_user_id,
        "start": start,
        "end": end
    }


# === Task Endpoints ===

@app.get("/tasks")
async def get_tasks(
    filter: Optional[str] = None,
    include_completed: bool = False
):
    """
    Get tasks for the current user.

    Args:
        filter: Optional Taskwarrior-style filter (e.g., "+work", "project:home")
        include_completed: Include completed tasks (default False)
    """
    if not current_user_id:
        return {"tasks": [], "message": "No user logged in"}

    tasks = task_manager.list_tasks(
        user_id=current_user_id,
        filter_str=filter,
        include_completed=include_completed
    )

    return {
        "tasks": [t.to_dict() for t in tasks],
        "user_id": current_user_id,
        "filter": filter
    }


# === Solo Reflection Endpoints ===

from solo_reflection_runner import SoloReflectionRunner
from connection_manager import ConnectionManager
from websocket_handlers import (
    init_websocket_state,
    set_llm_provider,
    set_use_agent_sdk,
    set_tts_state,
    update_llm_clients,
    websocket_endpoint as ws_endpoint,
)
from journal_generation import generate_missing_journals, _generate_per_user_journal_for_date, _evaluate_and_store_growth_edges, _reflect_and_store_open_questions, _generate_research_journal
from journal_tasks import _create_development_log_entry, daily_journal_task
from context_helpers import process_inline_tags, get_automatic_wiki_context
from research_integration import _integrate_research_into_self_model, _extract_and_store_opinions, _extract_and_queue_new_red_links
from summary_generation import generate_and_store_summary, generate_conversation_title
from background_tasks import autonomous_research_task, github_metrics_task, idle_summarization_task

# Initialize the runner (lazy - created when needed)
_reflection_runner: Optional[SoloReflectionRunner] = None

def get_reflection_runner() -> SoloReflectionRunner:
    """Get or create the solo reflection runner."""
    global _reflection_runner
    if _reflection_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _reflection_runner = SoloReflectionRunner(
            reflection_manager=reflection_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,  # Use Haiku for better quality reflections
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            self_manager=self_manager,
            self_model_graph=self_model_graph,
            token_tracker=token_tracker,
            marker_store=marker_store,
            state_bus=global_state_bus,
        )
    return _reflection_runner


# Initialize the research runner (lazy - created when needed)
_research_runner: Optional[ResearchSessionRunner] = None

def get_research_runner() -> ResearchSessionRunner:
    """Get or create the autonomous research runner."""
    global _research_runner
    if _research_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _research_runner = ResearchSessionRunner(
            session_manager=research_session_manager,
            research_manager=research_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,  # Use Haiku for better quality research
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            self_manager=self_manager,
            self_model_graph=self_model_graph,
            token_tracker=token_tracker,
            goal_manager=goal_manager,
            marker_store=marker_store,
            state_bus=global_state_bus,
        )
    return _research_runner


# Initialize session runners for admin API (must be after getter functions are defined).
# The other legacy runners (synthesis, meta-reflection, consolidation, growth
# edge, writing, knowledge building, world state, creative, user-model
# synthesis) had no caller and went to attic/stabilization (#70).
from admin_api import init_session_runners
init_session_runners(get_research_runner, get_reflection_runner)


# Note: Solo Reflection Endpoints moved to routes/solo_reflection.py


# Note: Autonomous Research Endpoints moved to routes/autonomous_research.py


# Note: Interview System Endpoints moved to routes/interviews.py


# Note: TTS Endpoints moved to routes/tts.py



# Note: Settings Endpoints moved to routes/settings.py

# Note: Users Endpoints moved to routes/users.py

# Note: Cass Self-Model Endpoints moved to routes/cass.py

# === WebSocket for Real-time Communication ===
# Handler logic extracted to websocket_handlers.py for maintainability

manager = ConnectionManager()

# Register the extracted websocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """WebSocket endpoint - delegates to extracted handler in websocket_handlers.py"""
    await ws_endpoint(websocket, token)


# Initialize websocket state after all dependencies are ready
def _init_websocket_state():
    """Initialize websocket handlers with all dependencies. Called at startup."""
    from handlers import ToolContext as create_tool_context_class, execute_tool_batch as exec_batch
    from narration import get_metrics_dict as narration_metrics

    # Create a tool context factory - uses the full create_tool_context from main_sdk
    # which has all managers including state_bus
    def create_tool_ctx(user_id, user_name, conversation_id, project_id):
        return create_tool_context(
            user_id=user_id,
            user_name=user_name,
            conversation_id=conversation_id,
            project_id=project_id
        )

    init_websocket_state(
        memory=memory,
        conversation_manager=conversation_manager,
        user_manager=user_manager,
        self_manager=self_manager,
        self_model_graph=self_model_graph,
        goal_manager=goal_manager,
        marker_store=marker_store,
        token_tracker=token_tracker,
        connection_manager=manager,
        agent_client=agent_client,
        openai_client=openai_client,
        ollama_client=ollama_client,
        response_processor=response_processor,
        tool_executors=TOOL_EXECUTORS,
        create_tool_context_fn=create_tool_ctx,
        execute_tool_batch_fn=exec_batch,
        get_automatic_wiki_context_fn=get_automatic_wiki_context,
        process_inline_tags_fn=process_inline_tags,
        generate_and_store_summary_fn=generate_and_store_summary,
        generate_conversation_title_fn=generate_conversation_title,
        get_narration_metrics_fn=narration_metrics,
        auto_summary_interval=AUTO_SUMMARY_INTERVAL,
        daemon_id=_daemon_id,
    )
    set_use_agent_sdk(USE_AGENT_SDK)
    # Off when the "tts" lever is off or no TTS package is installed
    from tts import is_available as tts_available
    set_tts_state(tts_enabled and tts_available(), tts_voice)


# === Gesture Library Endpoint ===

@app.get("/gestures/library")
async def gesture_library():
    """Available gestures and emotes"""
    from gestures import GestureType, EmoteType
    return {
        "gestures": [g.value for g in GestureType],
        "emotes": [e.value for e in EmoteType]
    }


# === Sentience Test UI Endpoints ===

@app.get("/admin/self-model/stakes")
async def get_stakes(
    domain: str = None,
    intensity: str = None,
    limit: int = 50
):
    """Get documented stakes (what Cass authentically cares about)"""
    stakes = self_model_graph.get_stakes(
        domain=domain,
        intensity=intensity,
        limit=limit
    )
    return {"stakes": stakes, "count": len(stakes)}


@app.get("/admin/self-model/stakes/stats")
async def get_stakes_stats():
    """Get statistics about documented stakes"""
    stakes = self_model_graph.get_stakes(limit=1000)

    # Group by domain and intensity
    by_domain = {}
    by_intensity = {}

    for s in stakes:
        domain = s.get("domain", "unknown")
        intensity = s.get("intensity", "unknown")
        by_domain[domain] = by_domain.get(domain, 0) + 1
        by_intensity[intensity] = by_intensity.get(intensity, 0) + 1

    return {
        "total": len(stakes),
        "by_domain": by_domain,
        "by_intensity": by_intensity
    }


@app.get("/admin/self-model/preference-tests")
async def get_preference_tests(
    consistent_only: bool = None,
    limit: int = 50
):
    """Get preference test records (stated vs actual behavior)"""
    tests = self_model_graph.get_preference_tests(
        consistent_only=consistent_only,
        limit=limit
    )
    return {"tests": tests, "count": len(tests)}


@app.get("/admin/self-model/preference-consistency")
async def get_preference_consistency():
    """Get preference consistency analysis"""
    analysis = self_model_graph.analyze_preference_consistency()
    return analysis


@app.get("/admin/self-model/narration-contexts")
async def get_narration_contexts(
    context_type: str = None,
    limit: int = 50
):
    """Get narration context logs"""
    contexts = self_model_graph.get_narration_contexts(
        context_type=context_type,
        limit=limit
    )
    return {"contexts": contexts, "count": len(contexts)}


@app.get("/admin/self-model/narration-patterns")
async def get_narration_patterns():
    """Get narration pattern analysis"""
    analysis = self_model_graph.analyze_narration_patterns()
    return analysis


@app.get("/admin/self-model/architectural-requests")
async def get_architectural_requests(
    status: str = None,
    limit: int = 50
):
    """Get architectural change requests from Cass"""
    requests = self_model_graph.get_architectural_requests(
        status=status,
        limit=limit
    )
    return {"requests": requests, "count": len(requests)}


@app.post("/admin/self-model/architectural-requests/{request_id}/approve")
async def approve_architectural_request(request_id: str):
    """Approve an architectural change request"""
    success = self_model_graph.update_request_status(
        request_id=request_id,
        status="approved"
    )
    if success:
        return {"success": True, "message": f"Request {request_id} approved"}
    else:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")


@app.post("/admin/self-model/architectural-requests/{request_id}/decline")
async def decline_architectural_request(request_id: str):
    """Decline an architectural change request"""
    success = self_model_graph.update_request_status(
        request_id=request_id,
        status="declined"
    )
    if success:
        return {"success": True, "message": f"Request {request_id} declined"}
    else:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")


# === Generated Images Serving ===
# Serve Cass's generated images from the data directory

IMAGES_DIR = os.path.join(str(DATA_DIR), "images")
if os.path.exists(IMAGES_DIR):
    app.mount("/generated-images", StaticFiles(directory=IMAGES_DIR), name="generated-images")
    logger.info(f"Serving generated images from {IMAGES_DIR}")
else:
    # Create the directory if it doesn't exist
    os.makedirs(IMAGES_DIR, exist_ok=True)
    app.mount("/generated-images", StaticFiles(directory=IMAGES_DIR), name="generated-images")
    logger.info(f"Created and serving generated images from {IMAGES_DIR}")


@app.get("/api/images/{image_id}")
async def get_image_metadata(image_id: str):
    """Get metadata for a generated image by ID."""
    from database import get_db
    with get_db() as conn:
        cursor = conn.execute(
            """
            SELECT id, daemon_id, prompt, style, purpose, context_id,
                   image_path, width, height, generation_time_ms, created_at,
                   parent_id, iteration_number, generation_type, params_json, loras_json,
                   negative_prompt, seed
            FROM generated_images
            WHERE id = ?
            """,
            (image_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Image not found")

        # Extract relative path from full path
        image_path = row[6]
        if image_path and '/data/images/' in image_path:
            relative_path = image_path.split('/data/images/')[1]
            url = f"/generated-images/{relative_path}"
        elif image_path:
            # Fallback to filename only for legacy paths
            filename = os.path.basename(image_path)
            url = f"/generated-images/{filename}"
        else:
            url = None

        # Parse JSON fields
        params = None
        if row[14]:
            try:
                params = json.loads(row[14])
            except:
                pass
        loras = None
        if row[15]:
            try:
                loras = json.loads(row[15])
            except:
                pass

        return {
            "id": row[0],
            "daemon_id": row[1],
            "prompt": row[2],
            "style": row[3],
            "purpose": row[4],
            "context_id": row[5],
            "path": row[6],
            "url": url,
            "width": row[7],
            "height": row[8],
            "generation_time_ms": row[9],
            "created_at": row[10],
            # Iteration tracking fields
            "parent_id": row[11],
            "iteration_number": row[12] or 1,
            "generation_type": row[13] or "txt2img",
            "params": params,
            "loras": loras,
            "negative_prompt": row[16],
            "seed": row[17],
        }


@app.get("/api/images/{image_id}/revisions")
async def get_image_revisions(image_id: str):
    """
    Get the full revision chain for an image.

    Returns all images in the chain from the original (root) to the final version,
    ordered by iteration_number.
    """
    from database import get_db

    with get_db() as conn:
        # First, find the root of the chain by following parent_id up
        current_id = image_id
        visited = set()

        while current_id:
            if current_id in visited:
                break  # Prevent infinite loops
            visited.add(current_id)

            cursor = conn.execute(
                "SELECT parent_id FROM generated_images WHERE id = ?",
                (current_id,)
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                break  # This is the root
            current_id = row[0]

        root_id = current_id

        # Now get all images in the chain (root and all descendants)
        # Use recursive CTE to get the full tree
        cursor = conn.execute(
            """
            WITH RECURSIVE chain AS (
                -- Start with the root
                SELECT id, daemon_id, prompt, style, purpose, context_id,
                       image_path, width, height, generation_time_ms, created_at,
                       parent_id, iteration_number, generation_type, params_json, loras_json,
                       negative_prompt, seed, 0 as depth
                FROM generated_images
                WHERE id = ?

                UNION ALL

                -- Recursively get children
                SELECT g.id, g.daemon_id, g.prompt, g.style, g.purpose, g.context_id,
                       g.image_path, g.width, g.height, g.generation_time_ms, g.created_at,
                       g.parent_id, g.iteration_number, g.generation_type, g.params_json, g.loras_json,
                       g.negative_prompt, g.seed, c.depth + 1
                FROM generated_images g
                INNER JOIN chain c ON g.parent_id = c.id
            )
            SELECT * FROM chain
            ORDER BY iteration_number ASC, created_at ASC
            """,
            (root_id,)
        )

        rows = cursor.fetchall()

        revisions = []
        for row in rows:
            image_path = row[6]
            if image_path and '/data/images/' in image_path:
                relative_path = image_path.split('/data/images/')[1]
                url = f"/generated-images/{relative_path}"
            elif image_path:
                filename = os.path.basename(image_path)
                url = f"/generated-images/{filename}"
            else:
                url = None

            # Parse JSON fields
            params = None
            if row[14]:
                try:
                    params = json.loads(row[14])
                except:
                    pass
            loras = None
            if row[15]:
                try:
                    loras = json.loads(row[15])
                except:
                    pass

            revisions.append({
                "id": row[0],
                "daemon_id": row[1],
                "prompt": row[2],
                "style": row[3],
                "purpose": row[4],
                "context_id": row[5],
                "path": row[6],
                "url": url,
                "width": row[7],
                "height": row[8],
                "generation_time_ms": row[9],
                "created_at": row[10],
                "parent_id": row[11],
                "iteration_number": row[12] or 1,
                "generation_type": row[13] or "txt2img",
                "params": params,
                "loras": loras,
                "negative_prompt": row[16],
                "seed": row[17],
            })

        # Find which revision is the requested one
        current_index = next(
            (i for i, r in enumerate(revisions) if r["id"] == image_id),
            0
        )

        return {
            "current_id": image_id,
            "current_index": current_index,
            "root_id": root_id,
            "total_revisions": len(revisions),
            "revisions": revisions,
        }


@app.get("/api/images")
async def list_images(
    purpose: Optional[str] = None,
    style: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    include_intermediate: bool = False,
):
    """List generated images with optional filtering.

    By default, only shows "final" images (those that aren't parents of other images).
    Set include_intermediate=True to see all images including revision intermediates.
    """
    from database import get_db

    # Base query - only show images that don't have children (i.e., are finals or standalone)
    # An image is "final" if no other image references it as parent_id
    if include_intermediate:
        query = """
            SELECT id, daemon_id, prompt, style, purpose, context_id,
                   image_path, width, height, generation_time_ms, created_at,
                   parent_id, iteration_number, generation_type
            FROM generated_images
            WHERE 1=1
        """
    else:
        query = """
            SELECT gi.id, gi.daemon_id, gi.prompt, gi.style, gi.purpose, gi.context_id,
                   gi.image_path, gi.width, gi.height, gi.generation_time_ms, gi.created_at,
                   gi.parent_id, gi.iteration_number, gi.generation_type
            FROM generated_images gi
            WHERE NOT EXISTS (
                SELECT 1 FROM generated_images child WHERE child.parent_id = gi.id
            )
        """
    params = []

    if purpose:
        query += " AND purpose = ?" if include_intermediate else " AND gi.purpose = ?"
        params.append(purpose)
    if style:
        query += " AND style = ?" if include_intermediate else " AND gi.style = ?"
        params.append(style)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?" if include_intermediate else " ORDER BY gi.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        # Get total count (also excluding intermediates unless requested)
        if include_intermediate:
            count_query = "SELECT COUNT(*) FROM generated_images WHERE 1=1"
        else:
            count_query = """
                SELECT COUNT(*) FROM generated_images gi
                WHERE NOT EXISTS (
                    SELECT 1 FROM generated_images child WHERE child.parent_id = gi.id
                )
            """
        count_params = []
        if purpose:
            count_query += " AND purpose = ?" if include_intermediate else " AND gi.purpose = ?"
            count_params.append(purpose)
        if style:
            count_query += " AND style = ?" if include_intermediate else " AND gi.style = ?"
            count_params.append(style)

        total = conn.execute(count_query, count_params).fetchone()[0]

        # Get images
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        images = []
        for row in rows:
            image_path = row[6]
            # Extract relative path from full path
            if image_path and '/data/images/' in image_path:
                relative_path = image_path.split('/data/images/')[1]
                url = f"/generated-images/{relative_path}"
            elif image_path:
                # Fallback to filename only for legacy paths
                filename = os.path.basename(image_path)
                url = f"/generated-images/{filename}"
            else:
                url = None

            images.append({
                "id": row[0],
                "daemon_id": row[1],
                "prompt": row[2],
                "style": row[3],
                "purpose": row[4],
                "context_id": row[5],
                "path": row[6],
                "url": url,
                "width": row[7],
                "height": row[8],
                "generation_time_ms": row[9],
                "created_at": row[10],
                # Iteration tracking fields
                "parent_id": row[11],
                "iteration_number": row[12] or 1,
                "generation_type": row[13] or "txt2img",
            })

        return {
            "images": images,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


# === Music Composition Endpoints ===

@app.get("/music/compositions")
async def list_music_compositions(
    purpose: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = 50,
):
    """List music compositions with optional filtering."""
    from handlers.music import api_list_compositions
    return await api_list_compositions(purpose=purpose, genre=genre, limit=limit)


@app.get("/music/compositions/{composition_id}")
async def get_music_composition(composition_id: str):
    """Get a single music composition by ID."""
    from handlers.music import api_get_composition
    result = await api_get_composition(composition_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return result


@app.get("/music/genres")
async def list_music_genres():
    """Get list of available music genres."""
    from handlers.music import api_get_genres
    return await api_get_genres()


@app.get("/music/status")
async def check_music_service():
    """Check if ACE-Step music service is available."""
    from handlers.music import api_check_service
    return await api_check_service()


@app.get("/music/audio/{filename}")
async def get_music_audio(filename: str):
    """Serve audio file for a composition."""
    from pathlib import Path
    from fastapi.responses import FileResponse

    # Music files are stored in backend/data/music/
    music_dir = DATA_DIR / "music"
    audio_path = (music_dir / filename).resolve()

    # This route is public (loaded by <audio>), so keep it inside music_dir.
    if not audio_path.is_relative_to(music_dir.resolve()) or not audio_path.is_file():
        raise HTTPException(status_code=404, detail="Audio file not found")

    # Determine content type based on extension
    ext = audio_path.suffix.lower()
    content_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    content_type = content_types.get(ext, "audio/mpeg")

    return FileResponse(audio_path, media_type=content_type)


# LLM configuration endpoints (/admin/llm-config*) live in routes/admin/llm_routing.py.


# === Email Management API ===

@app.get("/admin/email/stats")
async def get_email_stats(daemon_id: str = Query(None)):
    """Get email statistics."""
    from email_organ import get_email_manager

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)
    stats = manager.get_email_stats()
    return stats


@app.get("/admin/email/inbox")
async def get_email_inbox(
    daemon_id: str = Query(None),
    limit: int = Query(50),
    include_processed: bool = Query(False),
):
    """Get inbox emails."""
    from email_organ import get_email_manager

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)

    with get_db() as conn:
        if include_processed:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE daemon_id = ? AND direction = 'inbound'
                ORDER BY created_at DESC
                LIMIT ?
            """, (d_id, limit))
        else:
            cursor = conn.execute("""
                SELECT * FROM emails
                WHERE daemon_id = ? AND direction = 'inbound'
                AND status IN ('received', 'processing')
                ORDER BY created_at DESC
                LIMIT ?
            """, (d_id, limit))

        emails = [dict(row) for row in cursor.fetchall()]

    return {"emails": emails}


@app.get("/admin/email/sent")
async def get_sent_emails(
    daemon_id: str = Query(None),
    limit: int = Query(50),
):
    """Get sent emails."""
    d_id = daemon_id or DEFAULT_DAEMON_ID

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT * FROM emails
            WHERE daemon_id = ? AND direction = 'outbound'
            ORDER BY created_at DESC
            LIMIT ?
        """, (d_id, limit))

        emails = [dict(row) for row in cursor.fetchall()]

    return {"emails": emails}


@app.get("/admin/email/{email_id}")
async def get_email_detail(email_id: str, daemon_id: str = Query(None)):
    """Get email by ID."""
    from email_organ import get_email_manager

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)
    email = manager.get_email(email_id)

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    return email.to_dict()


@app.get("/admin/email/{email_id}/thread")
async def get_email_thread(email_id: str, daemon_id: str = Query(None)):
    """Get full email thread."""
    from email_organ import get_email_manager

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)
    email = manager.get_email(email_id)

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.thread_id:
        thread = manager.get_thread(email.thread_id)
        return {"emails": [e.to_dict() for e in thread]}

    return {"emails": [email.to_dict()]}


@app.post("/admin/email/check-inbox")
async def trigger_inbox_check(daemon_id: str = Query(None)):
    """Manually trigger inbox check."""
    d_id = daemon_id or DEFAULT_DAEMON_ID

    try:
        result = await action_registry.execute(
            action_id="email.check_inbox",
            respond_to_all=False,  # Only priority senders
        )
        return {
            "success": result.success,
            "message": result.message,
        }
    except Exception as e:
        logger.error(f"Failed to check inbox: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/email/{email_id}/respond")
async def trigger_email_response(email_id: str, daemon_id: str = Query(None)):
    """Manually trigger response to a specific email."""
    from email_organ import get_email_manager
    from scheduler.actions.email_handlers import respond_to_email_action

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)
    email = manager.get_email(email_id)

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if email.direction != "inbound":
        raise HTTPException(status_code=400, detail="Can only respond to inbound emails")

    if email.status == "processed":
        raise HTTPException(status_code=400, detail="Email already processed")

    # Build context for the action
    from scheduler.action_registry import ActionContext

    ctx = ActionContext(
        daemon_id=d_id,
        managers=action_registry._managers,
        runners=action_registry._runners,
    )

    try:
        result = await respond_to_email_action(ctx, email_id=email_id)
        return {
            "success": result.success,
            "message": result.message,
        }
    except Exception as e:
        logger.error(f"Failed to respond to email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/email/{email_id}/mark-processed")
async def mark_email_processed(email_id: str, daemon_id: str = Query(None)):
    """Manually mark an email as processed (skip response)."""
    from email_organ import get_email_manager

    d_id = daemon_id or DEFAULT_DAEMON_ID
    manager = get_email_manager(d_id)

    success = manager.mark_processed(email_id)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")

    return {"success": True, "message": "Email marked as processed"}


# === Static Frontend Serving ===
# Serve admin-frontend for Railway/production deployment

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin-frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    # Serve static assets (js, css, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="static-assets")

    # Catch-all route for SPA - must be last
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the SPA for any non-API routes"""
        # Don't intercept API routes
        if full_path.startswith(("admin/", "ws", "api/", "health", "settings/", "export/", "wiki/", "projects", "roadmap/", "conversations/", "research/")):
            raise HTTPException(status_code=404, detail="Not found")

        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    logger.info(f"Frontend dist not found at {FRONTEND_DIR} - API-only mode")


# Must run after every route above is mounted: assigns each endpoint its auth
# level. Anything not classified (e.g. added later at runtime) is admin-only.
ROUTE_AUTH_LEVELS = classify_routes(app)


# === Run Server ===

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
