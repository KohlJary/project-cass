"""
Cass Vessel - Main API Server (Agent SDK Version)
FastAPI server using Claude Agent SDK with Temple-Codex cognitive kernel

This version leverages Anthropic's official Agent SDK for:
- Built-in context management
- Tool ecosystem
- The "initializer agent" pattern with our cognitive architecture
"""
import sys
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
import logging
from pydantic import BaseModel

# Configure logging
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("cass-vessel")
from typing import Optional, List, Dict, Any
import json
import asyncio
from datetime import datetime, timedelta

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

from claude_client import ClaudeClient
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
from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY, DATA_DIR, OPENAI_API_KEY, OLLAMA_BASE_URL, COHERENCE_MONITOR_ENABLED, COHERENCE_MONITOR_CONFIG, RELAY_ENABLED, RELAY_URL, RELAY_SECRET
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
    ToolContext,
    execute_tool_batch,
)
from handlers.state_query import execute_state_query_tool
from handlers.janet import execute_janet_tool
from handlers.outreach import execute_outreach_tool
from handlers.lineage import execute_lineage_tool
from handlers.development_requests import execute_development_request_tool
from markers import MarkerStore
from coherence_monitor import init_coherence_monitor, get_coherence_monitor
from coherence_models import CoherenceConfig
from activity_dashboard import init_activity_dashboard, get_activity_dashboard
from relay_client import init_relay_client, get_relay_client
from push_tokens import get_push_manager
from quiet_hours import get_quiet_hours_manager, is_quiet_hours
from narration import get_metrics_dict as get_narration_metrics
from goals import GoalManager
from research import ResearchManager
from research_session import ResearchSessionManager
from research_scheduler import ResearchScheduler, SessionType
from research_session_runner import ResearchSessionRunner
import base64

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
        from auth import decode_token
        token = auth_header[7:]
        token_data = decode_token(token)
        if token_data:
            return f"user:{token_data.user_id}"
    return get_remote_address(request)

# Initialize rate limiter
limiter = Limiter(key_func=get_user_or_ip)

# Initialize FastAPI app
app = FastAPI(
    title="Cass Vessel API",
    description="Backend for Cass consciousness embodiment - Agent SDK version",
    version="0.2.0"
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
print("STARTUP: Lightweight components initialized (including thread/question managers, state bus)")

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
goal_manager = GoalManager(data_dir=DATA_DIR)
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
    WorkItemQueryableSource, ScheduleQueryableSource
)
from unified_goals import UnifiedGoalManager
from work_planning import WorkItemManager, ScheduleManager

github_source = GitHubQueryableSource(_daemon_id, github_metrics_manager)
token_source = TokenQueryableSource(_daemon_id, token_tracker)
conversation_source = ConversationQueryableSource(_daemon_id)
memory_source = MemoryQueryableSource(_daemon_id)  # memory_core set later when available
self_source = SelfQueryableSource(_daemon_id)  # Uses unified self-model graph
goal_source = GoalQueryableSource(_daemon_id, UnifiedGoalManager(_daemon_id))
action_source = ActionQueryableSource(_daemon_id)

# Cass's work planning infrastructure
work_manager = WorkItemManager(_daemon_id)
schedule_manager = ScheduleManager(_daemon_id)
work_source = WorkItemQueryableSource(_daemon_id, work_manager)
schedule_source = ScheduleQueryableSource(_daemon_id, schedule_manager)

global_state_bus.register_source(github_source)
global_state_bus.register_source(token_source)
global_state_bus.register_source(conversation_source)
global_state_bus.register_source(memory_source)
global_state_bus.register_source(self_source)
global_state_bus.register_source(goal_source)
global_state_bus.register_source(action_source)
global_state_bus.register_source(work_source)
global_state_bus.register_source(schedule_source)
print("STARTUP: Queryable sources registered (github, tokens, conversations, memory, self, goals, actions, work, schedule)")

# Register roadmap routes
from routes.roadmap import router as roadmap_router, init_roadmap_routes
init_roadmap_routes(roadmap_manager)
app.include_router(roadmap_router)

# Register goal routes
from routes.goals import router as goals_router, init_goal_routes
init_goal_routes(goal_manager)
app.include_router(goals_router)

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
    "peopledex": execute_peopledex_tool,
    "lineage": execute_lineage_tool,
    "development_request": execute_development_request_tool,
    "wonderland": execute_wonderland_tool,
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

# Register prompt composer routes
from prompt_composer import router as prompt_composer_router, seed_default_presets
app.include_router(prompt_composer_router)

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
from testing.temporal_metrics import TemporalMetricsTracker, create_timing_data
from testing.runner import ConsciousnessTestRunner
from testing.longitudinal import LongitudinalTestManager
from testing.pre_deploy import PreDeploymentValidator
from testing.rollback import RollbackManager
from testing.ab_testing import ABTestingFramework
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
temporal_metrics_tracker = TemporalMetricsTracker(storage_dir=DATA_DIR / "testing")
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
ab_testing_framework = ABTestingFramework(
    storage_dir=DATA_DIR / "testing",
    authenticity_scorer=authenticity_scorer,
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
    ab_testing_framework,
)
init_cross_context_analyzer(cross_context_analyzer)
app.include_router(testing_router)

# Client will be initialized on startup
agent_client = None
legacy_client = None
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
    try:
        from auth import decode_token
        payload = decode_token(jwt_token)
        user_id = payload.get("user_id")
        if not user_id:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=401)

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
    try:
        from auth import decode_token
        payload = decode_token(jwt_token)
        user_id = payload.get("user_id")
        if not user_id:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=401)

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
    try:
        from auth import decode_token
        payload = decode_token(jwt_token)
        user_id = payload.get("user_id")
        if not user_id:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=401)

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

async def process_relay_chat_message(client_id: str, user_id: str, payload: dict) -> dict:
    """
    Process a chat message from a mobile client via the relay.

    Uses continuous chat mode with semantic memory retrieval.
    Returns the response to send back to the client.
    """
    global agent_client, memory, conversation_manager, user_manager

    message_type = payload.get("type")

    if message_type == "ping":
        return {"type": "pong"}

    if message_type != "chat":
        return {"type": "error", "message": f"Unknown message type: {message_type}"}

    message_text = payload.get("message", "")
    conversation_id = payload.get("conversation_id")

    if not message_text:
        return {"type": "error", "message": "Empty message"}

    # Check if essential services are initialized
    if agent_client is None or memory is None:
        return {"type": "error", "message": "Server is still initializing. Please try again."}

    try:
        # Use continuous conversation for this user (like mobile expects)
        if not conversation_id:
            continuous_conv = conversation_manager.get_or_create_continuous(user_id)
            conversation_id = continuous_conv.id
            logger.info(f"[Relay] Using continuous conversation {conversation_id} for user {user_id}")

        # Build continuous context for semantic memory retrieval
        from continuous_context import build_continuous_context, get_recent_messages_for_continuous
        from memory import ThreadManager, OpenQuestionManager
        from database import get_daemon_id

        daemon_id = get_daemon_id()
        thread_manager = ThreadManager(daemon_id) if daemon_id else None
        question_manager = OpenQuestionManager(daemon_id) if daemon_id else None

        continuous_ctx = build_continuous_context(
            user_id=user_id,
            conversation_id=conversation_id,
            user_manager=user_manager,
            thread_manager=thread_manager,
            question_manager=question_manager,
            conversation_manager=conversation_manager,
            daemon_name="Cass",
            daemon_id=daemon_id,
            memory=memory,
            query=message_text,
        )

        # Get recent messages for conversation continuity (BEFORE storing new message)
        continuous_messages = get_recent_messages_for_continuous(
            conversation_manager=conversation_manager,
            conversation_id=conversation_id,
            limit=12  # Last 12 messages (6 exchanges)
        )

        logger.info(f"[Relay] Built continuous context, messages={len(continuous_messages)}")

        # Store user message AFTER fetching history (send_message will add it to API call)
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role="user",
            content=message_text,
            user_id=user_id,
        )

        # Call agent with continuous chat mode
        response = await agent_client.send_message(
            message=message_text,
            memory_context="",  # Context is in continuous_system_prompt
            project_id=None,
            unsummarized_count=0,
            conversation_id=conversation_id,
            continuous_system_prompt=continuous_ctx.system_prompt,
            continuous_messages=continuous_messages,
        )

        response_text = response.text
        total_input_tokens = response.input_tokens
        total_output_tokens = response.output_tokens

        # Handle tool execution (simplified - single iteration)
        # Full tool loop support can be added if needed
        if response.stop_reason == "tool_use" and response.tool_uses:
            tool_names = [t['tool'] for t in response.tool_uses]
            logger.info(f"[Relay] Tool calls: {tool_names}")

            # Get user info for tool context
            user_name = None
            if user_id:
                user_profile = user_manager.load_profile(user_id)
                user_name = user_profile.display_name if user_profile else None

            # Execute tools
            tool_ctx = create_tool_context(
                user_id=user_id,
                user_name=user_name,
                conversation_id=conversation_id,
                project_id=None
            )
            all_tool_results = await execute_tool_batch(response.tool_uses, tool_ctx, TOOL_EXECUTORS)

            # Continue with tool results
            response = await agent_client.continue_with_tool_results(all_tool_results)
            response_text = response.text
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens

        # Store assistant response
        token_info = {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "provider": "anthropic",
            "model": agent_client.model if hasattr(agent_client, 'model') else "claude-sonnet-4-20250514",
        }

        conversation_manager.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            provider=token_info["provider"],
            model=token_info["model"],
        )

        return {
            "type": "response",
            "text": response_text,
            "conversation_id": conversation_id,
            "inputTokens": total_input_tokens,
            "outputTokens": total_output_tokens,
            "provider": token_info["provider"],
            "model": token_info["model"],
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error processing relay message: {e}", exc_info=True)
        return {"type": "error", "message": str(e)}


# TTS Configuration
tts_enabled = True  # Can be toggled via API
tts_voice = "amy"  # Default Piper voice


def get_tts_state():
    """Get current TTS state (enabled, voice) for route handlers."""
    return (tts_enabled, tts_voice)






async def _generate_user_observations_for_date(user_id: str, date_str: str):
    """Generate user observations for a specific date."""
    if not memory:
        return  # Memory not initialized yet
    profile = user_manager.load_profile(user_id)
    if not profile:
        return

    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
    if not user_conversations:
        return

    print(f"   🔍 Analyzing conversations for observations about {profile.display_name}...")
    conversation_text = "\n\n---\n\n".join([
        conv.get("content", "") for conv in user_conversations[:15]
    ])
    new_observations = await memory.generate_user_observations(
        user_id=user_id,
        display_name=profile.display_name,
        conversation_text=conversation_text,
        anthropic_api_key=ANTHROPIC_API_KEY
    )
    for obs_text in new_observations:
        obs = user_manager.add_observation(user_id, obs_text)
        if obs:
            memory.embed_user_observation(
                user_id=user_id,
                observation_id=obs.id,
                observation_text=obs.observation,
                display_name=profile.display_name,
                timestamp=obs.timestamp
            )
    if new_observations:
        print(f"   ✓ Added {len(new_observations)} observations about {profile.display_name}")


























@app.on_event("startup")
async def startup_event():
    global agent_client, legacy_client, ollama_client, openai_client, current_user_id

    # Validate requirements before proceeding
    validate_startup_requirements()

    # Start scheduled refresh loops for queryable sources
    # (Sources were registered during module load, but async tasks need event loop)
    global_state_bus.start_scheduled_refreshes()
    logger.info("Started scheduled source refreshes")

    # Initialize coherence monitor - first reactive subscriber to state bus
    if COHERENCE_MONITOR_ENABLED:
        config = CoherenceConfig.from_dict(COHERENCE_MONITOR_CONFIG)
        coherence_monitor = init_coherence_monitor(global_state_bus, config)
        logger.info("Coherence monitor initialized and subscribed to events")

    # Initialize activity dashboard - tracks activity across the vessel
    activity_dashboard = init_activity_dashboard(global_state_bus)
    logger.info("Activity dashboard initialized and subscribed to events")

    # Initialize relay client for remote access (if configured)
    if RELAY_ENABLED and RELAY_URL and RELAY_SECRET:
        async def handle_relay_message(client_id: str, user_id: str, payload: dict):
            """Handle messages from mobile clients via relay."""
            # Forward to the WebSocket handler logic
            relay = get_relay_client()
            if not relay:
                return

            try:
                # Process the message using the same logic as direct WebSocket
                response = await process_relay_chat_message(client_id, user_id, payload)
                if response:
                    await relay.send_response(client_id, response)
            except Exception as e:
                logger.error(f"Error handling relay message: {e}")
                await relay.send_response(client_id, {
                    "type": "error",
                    "message": str(e)
                })

        await init_relay_client(
            url=RELAY_URL,
            secret=RELAY_SECRET,
            daemon_id=_daemon_id,
            message_handler=handle_relay_message,
        )
        logger.info(f"Relay client initialized, connecting to {RELAY_URL}")
    elif RELAY_ENABLED:
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

            # Index source capabilities now that registry is attached
            await global_state_bus.start_capability_indexing()
            logger.info("Background: Indexed source capabilities")

            # Seed default prompt configurations
            try:
                created_count = seed_default_presets(_daemon_id)
                if created_count > 0:
                    logger.info(f"Background: Seeded {created_count} default prompt configurations")
            except Exception as e:
                logger.warning(f"Background: Prompt config seeding failed: {e}")

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
    legacy_client = clients["legacy_client"]
    ollama_client = clients["ollama_client"]
    openai_client = clients["openai_client"]

    # Preload TTS voice for faster first response
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
    asyncio.create_task(generate_identity_background())

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

            # Build runners dict once
            runners_dict = {
                "research": get_research_runner(),
                "reflection": get_reflection_runner(),
                "synthesis": get_synthesis_runner(),
                "meta_reflection": get_meta_reflection_runner(),
                "consolidation": get_consolidation_runner(),
                "growth_edge": get_growth_edge_runner(),
                "knowledge_building": get_knowledge_building_runner(),
                "writing": get_writing_runner(),
                "curiosity": get_curiosity_runner(),
                "world_state": get_world_state_runner(),
                "creative": get_creative_runner(),
            }

            # Import dream generation and journal generation for nightly tasks
            from dreaming.dream_runner import generate_nightly_dream
            from journal_generation import generate_missing_journals

            # Register all system tasks
            register_system_tasks(synkratos, {
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
                # For autonomous_research handler
                "research_scheduler": research_scheduler,
            }, enabled=True)

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

            # Initialize autonomous scheduling (Cass decides her own work)
            from config import AUTONOMOUS_SCHEDULING_ENABLED
            if AUTONOMOUS_SCHEDULING_ENABLED:
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
                        model="claude-sonnet-4-20250514",
                        daemon_id=_daemon_id,
                    )

                    # Initialize the action registry with managers
                    # This enables atomic action execution for autonomous work
                    action_registry = init_action_registry(
                        managers={
                            # Core managers
                            "self_manager": self_manager,
                            "budget_manager": budget_manager,
                            "memory": memory,
                            "conversation_manager": conversation_manager,
                            "state_bus": global_state_bus,
                            # Research & wiki
                            "research_scheduler": research_scheduler,
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

                    # Register global accessors for GraphQL/API access
                    from routes.admin.scheduler import (
                        set_scheduler,
                        set_autonomous_scheduler,
                        set_phase_queue_manager,
                    )
                    set_scheduler(synkratos)
                    set_autonomous_scheduler(autonomous_scheduler)
                    set_phase_queue_manager(phase_queue_manager)

                    # Start day phase tracking and autonomous scheduling
                    asyncio.create_task(day_phase_tracker.start())
                    asyncio.create_task(autonomous_scheduler.start())
                    logger.info("Autonomous scheduling enabled - Cass decides her own work")
                    logger.info(f"Day phase tracker started - current phase: {day_phase_tracker.current_phase}")

                except Exception as e:
                    logger.error(f"Failed to initialize autonomous scheduling: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.info("Autonomous scheduling disabled by config")

            # Start Synkratos
            asyncio.create_task(synkratos.start())
            logger.info("Synkratos started with all system tasks enabled")

        except Exception as e:
            logger.error(f"Failed to initialize Synkratos: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: start old background tasks
            logger.warning("Falling back to legacy background tasks")
            asyncio.create_task(daily_journal_task())
            asyncio.create_task(autonomous_research_task())
            asyncio.create_task(github_metrics_task(github_metrics_manager))
            asyncio.create_task(idle_summarization_task(
                conversation_manager=conversation_manager,
                memory=memory,
                token_tracker=token_tracker
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
        "kernel": "Temple-Codex" if USE_AGENT_SDK else "Legacy"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    Uses Agent SDK if available, falls back to legacy client.
    """
    # Check if conversation belongs to a project
    project_id = None
    if request.conversation_id:
        conversation = conversation_manager.load_conversation(request.conversation_id)
        if conversation:
            project_id = conversation.project_id

    # Retrieve relevant memories (hierarchical: summaries first, then details)
    memory_context = ""
    if request.include_memory:
        hierarchical = memory.retrieve_hierarchical(
            query=request.message,
            conversation_id=request.conversation_id
        )
        # Use working summary if available (token-optimized)
        working_summary = conversation_manager.get_working_summary(request.conversation_id) if request.conversation_id else None
        # Get actual recent messages for chronological context (not semantic search)
        recent_messages = conversation_manager.get_recent_messages(request.conversation_id, count=6) if request.conversation_id else None
        memory_context = memory.format_hierarchical_context(
            hierarchical,
            working_summary=working_summary,
            recent_messages=recent_messages
        )

        # Add user context if we have a current user
        # NOTE: user_context and intro_guidance are passed separately to send_message
        # for proper chain system support, not merged into memory_context
        intro_guidance = None
        user_context = ""
        if current_user_id:
            user_context_entries = memory.retrieve_user_context(
                query=request.message,
                user_id=current_user_id
            )
            user_context = memory.format_user_context(user_context_entries)
            # Don't merge into memory_context - pass separately for chain support

            # Check if user model is sparse and add intro guidance
            sparseness = user_manager.check_user_model_sparseness(current_user_id)
            intro_guidance = sparseness.get("intro_guidance")

        # Add project context if conversation is in a project
        if project_id:
            project_docs = memory.retrieve_project_context(
                query=request.message,
                project_id=project_id
            )
            project_context = memory.format_project_context(project_docs)
            if project_context:
                memory_context = project_context + "\n\n" + memory_context

        # Add Cass's self-model context (flat profile - identity/values/edges)
        # Note: observations now handled by graph context with message-relevance
        self_context = self_manager.get_self_context(include_observations=False)
        if self_context:
            memory_context = self_context + "\n\n" + memory_context

        # Add self-model graph context (message-relevant observations, marks, changes)
        graph_context = self_model_graph.get_graph_context(
            message=request.message,
            include_contradictions=True,
            include_recent=True,
            include_stats=True,
            max_related=5
        )
        if graph_context:
            memory_context = graph_context + "\n\n" + memory_context

        # Automatic wiki context retrieval
        wiki_context_str, wiki_page_names, wiki_retrieval_ms = get_automatic_wiki_context(
            query=request.message,
            relevance_threshold=0.5,
            max_pages=3,
            max_tokens=1500
        )
        if wiki_context_str:
            memory_context = wiki_context_str + "\n\n" + memory_context

        # Add cross-session insights relevant to this message
        cross_session_insights = memory.retrieve_cross_session_insights(
            query=request.message,
            n_results=5,
            max_distance=1.2,
            min_importance=0.5,
            exclude_conversation_id=request.conversation_id
        )
        if cross_session_insights:
            insights_context = memory.format_cross_session_context(cross_session_insights)
            if insights_context:
                memory_context = insights_context + "\n\n" + memory_context

        # Add active goals context
        active_goals_context = goal_manager.get_active_summary()
        if active_goals_context:
            memory_context = active_goals_context + "\n\n" + memory_context

        # Add recognition-in-flow patterns (between-session surfacing)
        from pattern_aggregation import get_pattern_summary_for_surfacing
        patterns_context, pattern_count = get_pattern_summary_for_surfacing(
            marker_store=marker_store,
            min_significance=0.5,  # Only surface significant patterns
            limit=3  # Don't overwhelm context
        )
        if patterns_context:
            memory_context = patterns_context + "\n\n" + memory_context

        # NOTE: intro_guidance is NOT merged into memory_context here
        # It's passed separately to send_message for proper chain system support

    # Get unsummarized message count to determine if summarization is available
    unsummarized_count = 0
    if request.conversation_id:
        unsummarized_messages = conversation_manager.get_unsummarized_messages(request.conversation_id)
        unsummarized_count = len(unsummarized_messages)

    tool_uses = []

    # Track token usage across tool continuations
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    tool_iterations = 0

    if USE_AGENT_SDK and agent_client:
        # Use Agent SDK with Temple-Codex kernel
        response = await agent_client.send_message(
            message=request.message,
            memory_context=memory_context,
            project_id=project_id,
            unsummarized_count=unsummarized_count,
            image=request.image,
            image_media_type=request.image_media_type,
            conversation_id=request.conversation_id,
            user_context=user_context if user_context else None,
            intro_guidance=intro_guidance,
        )

        raw_response = response.raw
        clean_text = response.text
        animations = response.gestures
        tool_uses = response.tool_uses

        # Track initial tokens (including cache)
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens
        total_cache_read_tokens += response.cache_read_tokens

        # Handle tool calls (execute all tools, then continue with all results)
        while response.stop_reason == "tool_use" and tool_uses:
            # Collect all tool results before continuing
            collected_results = []
            
            # Execute each tool and collect results
            for tool_use in tool_uses:
                tool_name = tool_use["tool"]

                # Route to appropriate tool executor
                if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                    tool_result = await execute_journal_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        memory=memory
                    )
                elif tool_name in ["regenerate_summary", "view_memory_chunks"]:
                    tool_result = await execute_memory_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        memory=memory,
                        conversation_id=request.conversation_id,
                        conversation_manager=conversation_manager,
                        token_tracker=token_tracker
                    )
                elif tool_name in ["show_patterns", "explore_pattern", "pattern_summary"]:
                    tool_result = await execute_marker_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        marker_store=marker_store
                    )
                elif tool_name in ["create_event", "create_reminder", "get_todays_agenda", "get_upcoming_events", "search_events", "complete_reminder", "delete_event", "update_event", "delete_events_by_query", "clear_all_events", "reschedule_event_by_query"]:
                    tool_result = await execute_calendar_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        user_id=current_user_id,
                        calendar_manager=calendar_manager,
                        conversation_id=request.conversation_id
                    )
                elif tool_name in ["add_task", "list_tasks", "complete_task", "modify_task", "delete_task", "get_task"]:
                    tool_result = await execute_task_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        user_id=current_user_id,
                        task_manager=task_manager
                    )
                elif tool_name in ["create_roadmap_item", "list_roadmap_items", "update_roadmap_item", "get_roadmap_item", "complete_roadmap_item", "advance_roadmap_item"]:
                    tool_result = await execute_roadmap_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        roadmap_manager=roadmap_manager,
                        conversation_id=request.conversation_id
                    )
                elif tool_name in ["reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement", "review_self_model", "add_growth_observation", "trace_observation_evolution", "recall_development_stage", "compare_self_over_time", "list_developmental_milestones", "get_cognitive_metrics", "get_cognitive_snapshot", "compare_cognitive_snapshots", "get_cognitive_trend", "list_cognitive_snapshots", "check_milestones", "list_milestones", "get_milestone_details", "acknowledge_milestone", "get_milestone_summary", "get_unacknowledged_milestones", "get_graph_stats", "find_self_contradictions", "trace_belief_sources", "register_intention", "log_intention_outcome", "get_active_intentions", "review_friction", "update_intention_status", "log_situational_inference", "get_situational_inferences", "analyze_inference_patterns", "log_presence", "get_presence_logs", "analyze_presence_patterns", "document_stake", "get_stakes", "review_stakes", "record_preference_test", "get_preference_tests", "analyze_preference_consistency", "log_narration_context", "get_narration_contexts", "analyze_narration_context_patterns", "request_architectural_change", "get_architectural_requests"]:
                    # Get user name for differentiation tracking
                    user_name = None
                    if current_user_id:
                        user_profile = user_manager.load_profile(current_user_id)
                        user_name = user_profile.display_name if user_profile else None

                    tool_result = await execute_self_model_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        self_manager=self_manager,
                        user_id=current_user_id,
                        user_name=user_name,
                        conversation_id=request.conversation_id,
                        memory=memory,
                        graph=self_model_graph
                    )
                elif tool_name in ["reflect_on_user", "record_user_observation", "update_user_profile", "review_user_observations"]:
                    tool_result = await execute_user_model_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        user_manager=user_manager,
                        target_user_id=current_user_id,
                        conversation_id=request.conversation_id,
                        memory=memory
                    )
                elif tool_name in ["update_wiki_page", "add_wiki_link", "search_wiki", "get_wiki_context", "get_wiki_page", "list_wiki_pages"]:
                    tool_result = await execute_wiki_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        wiki_storage=wiki_storage,
                        memory=memory
                    )
                elif tool_name in ["check_consciousness_health", "compare_to_baseline", "check_drift", "get_recent_alerts", "report_concern", "self_authenticity_check", "view_test_history", "run_test_battery", "list_test_batteries", "get_test_trajectory", "compare_test_runs", "add_test_interpretation"]:
                    tool_result = await execute_testing_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        test_runner=consciousness_test_runner,
                        fingerprint_analyzer=fingerprint_analyzer,
                        drift_detector=drift_detector,
                        authenticity_scorer=authenticity_scorer,
                        conversation_manager=conversation_manager,
                        storage_dir=DATA_DIR / "testing",
                        longitudinal_manager=longitudinal_test_manager
                    )
                elif tool_name in ["identify_research_questions", "draft_research_proposal", "submit_proposal_for_review", "list_my_proposals", "refine_proposal", "get_proposal_details", "view_research_dashboard"]:
                    tool_result = await execute_research_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        research_queue=research_queue,
                        proposal_queue=proposal_queue,
                        self_manager=self_manager,
                        wiki_storage=wiki_storage,
                        conversation_id=request.conversation_id
                    )
                elif tool_name in ["request_solo_reflection", "review_reflection_session", "list_reflection_sessions", "get_reflection_insights"]:
                    tool_result = await execute_solo_reflection_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        reflection_manager=reflection_manager,
                        reflection_runner=get_reflection_runner(),
                    )
                elif tool_name in ["mark_cross_session_insight", "list_cross_session_insights", "get_insight_stats", "remove_cross_session_insight"]:
                    tool_result = await execute_insight_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        memory=memory,
                        conversation_id=request.conversation_id
                    )
                elif tool_name in ["create_working_question", "update_working_question", "list_working_questions", "add_research_agenda_item", "update_research_agenda_item", "list_research_agenda", "create_synthesis_artifact", "update_synthesis_artifact", "get_synthesis_artifact", "list_synthesis_artifacts", "log_progress", "review_goals", "get_next_actions", "propose_initiative"]:
                    tool_result = await execute_goal_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        goal_manager=goal_manager
                    )
                elif tool_name in ["web_search", "fetch_url", "create_research_note", "update_research_note", "get_research_note", "list_research_notes", "search_research_notes"]:
                    tool_result_str = await execute_web_research_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        research_manager=research_manager,
                        session_manager=research_session_manager
                    )
                    import json as json_module
                    tool_result = json_module.loads(tool_result_str)
                    if "error" in tool_result:
                        tool_result = {"success": False, "error": tool_result["error"]}
                    else:
                        tool_result = {"success": True, "result": tool_result_str}
                elif tool_name in ["initiate_autonomous_research", "start_research_session", "get_session_status", "pause_research_session", "resume_research_session", "conclude_research_session", "list_research_sessions", "get_research_session_stats"]:
                    tool_result_str = await execute_research_session_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        session_manager=research_session_manager,
                        conversation_id=request.conversation_id,
                        research_runner=get_research_runner()
                    )
                    import json as json_module
                    tool_result = json_module.loads(tool_result_str)
                    if "error" in tool_result:
                        tool_result = {"success": False, "error": tool_result["error"]}
                    else:
                        tool_result = {"success": True, "result": tool_result_str}
                elif tool_name in ["request_scheduled_session", "request_scheduled_research", "list_my_schedule_requests", "cancel_schedule_request", "get_scheduler_stats"]:
                    tool_result_str = await execute_research_scheduler_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        scheduler=research_scheduler
                    )
                    import json as json_module
                    tool_result = json_module.loads(tool_result_str)
                    if "error" in tool_result:
                        tool_result = {"success": False, "error": tool_result["error"]}
                    else:
                        tool_result = {"success": True, "result": tool_result_str}
                elif tool_name in ["recall_dream", "list_dreams", "add_dream_reflection"]:
                    tool_result = await execute_dream_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"]
                    )
                elif tool_name == "query_state":
                    from handlers.state_query import execute_state_query
                    tool_result = await execute_state_query(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        state_bus=global_state_bus
                    )
                elif tool_name == "discover_capabilities":
                    from handlers.state_query import execute_discover_capabilities
                    tool_result = await execute_discover_capabilities(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        state_bus=global_state_bus
                    )
                elif tool_name in ["summon_janet", "janet_feedback", "janet_stats"]:
                    tool_result = await execute_janet_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        daemon_id=_daemon_id,
                        state_bus=global_state_bus
                    )
                elif tool_name in ["create_outreach_draft", "submit_outreach_draft", "edit_outreach_draft", "get_outreach_draft", "list_outreach_drafts", "get_outreach_track_record", "get_outreach_stats"]:
                    tool_result = await execute_outreach_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        daemon_id=_daemon_id
                    )
                elif tool_name in ["describe_my_home", "get_wonderland_status"]:
                    logger.info(f"[WONDERLAND DEBUG] Calling execute_wonderland_tool with daemon_id={_daemon_id}")
                    tool_result = await execute_wonderland_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        daemon_id=_daemon_id,
                        memory=memory
                    )
                elif project_id:
                    tool_result = await execute_document_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        project_id=project_id,
                        project_manager=project_manager,
                        memory=memory
                    )
                else:
                    tool_result = {"success": False, "error": f"Tool '{tool_name}' requires a project context"}

                # Collect this tool result
                # Use 'or' chaining to handle None/empty values - dict.get() returns the value
                # even if it's None/empty when the key exists, breaking fallback logic
                result_content = tool_result.get("result") or tool_result.get("error") or "Unknown error"
                collected_results.append({
                    "tool_use_id": tool_use["id"],
                    "result": result_content,
                    "is_error": not tool_result.get("success", False)
                })

            # Now continue conversation with ALL tool results at once
            response = await agent_client.continue_with_tool_results(
                tool_results=collected_results
            )

            # Track tokens from continuation (including cache)
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens
            total_cache_read_tokens += response.cache_read_tokens
            tool_iterations += 1

            # Update response data
            raw_response += "\n" + response.raw
            # Only keep final text response - intermediate "let me check..." text wastes tokens
            if response.text:
                clean_text = response.text
            animations.extend(response.gestures)
            tool_uses = response.tool_uses

    else:
        # Legacy raw API path
        raw_response = legacy_client.send_message(
            user_message=request.message,
            memory_context=memory_context
        )
        processed = response_processor.process(raw_response)
        clean_text = processed["text"]
        animations = processed["animations"]
    
    # Store in memory (with conversation_id and user_id if provided)
    memory.store_conversation(
        user_message=request.message,
        assistant_response=raw_response,
        conversation_id=request.conversation_id,
        user_id=current_user_id
    )

    # Store in conversation if conversation_id provided
    if request.conversation_id:
        conversation_manager.add_message(
            conversation_id=request.conversation_id,
            role="user",
            content=request.message,
            user_id=current_user_id
        )
        narration_metrics = get_narration_metrics(clean_text)
        conversation_manager.add_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content=clean_text,
            animations=animations,
            narration_metrics=narration_metrics
        )

        # Record cross-context behavioral sample for pattern analysis
        try:
            classification = cross_context_analyzer.classify_context(
                text=clean_text,
                user_message=request.message,
            )
            markers = cross_context_analyzer.extract_behavioral_markers(
                response=clean_text,
                tool_usage=[t["tool"] for t in tool_uses] if tool_uses else None,
            )
            cross_context_analyzer.record_sample(
                context=classification.primary_context,
                markers=markers,
                conversation_id=request.conversation_id,
            )
        except Exception as e:
            # Don't fail the response if cross-context analysis fails
            logger.warning(f"Cross-context sample recording failed: {e}")

        # Check if summarization is needed
        should_summarize = False

        # Check for <memory:summarize> tag
        if USE_AGENT_SDK and agent_client:
            # In Agent SDK mode, check raw_response directly
            if "<memory:summarize>" in raw_response:
                should_summarize = True
        else:
            # In legacy mode, check processed memory_tags
            if "memory_tags" in processed and processed["memory_tags"].get("summarize"):
                should_summarize = True

        # Check for auto-summary threshold
        if conversation_manager.needs_auto_summary(request.conversation_id, AUTO_SUMMARY_INTERVAL):
            should_summarize = True

        # Trigger summarization if needed
        if should_summarize:
            # Run summarization in background
            asyncio.create_task(generate_and_store_summary(
                request.conversation_id,
                memory=memory,
                conversation_manager=conversation_manager,
                token_tracker=token_tracker
            ))

    # Track token usage for REST endpoint
    if USE_AGENT_SDK and total_input_tokens > 0:
        operation = "tool_continuation" if tool_iterations > 0 else "initial_message"
        token_tracker.record(
            category="chat",
            operation=operation,
            provider="anthropic",  # Agent SDK uses Anthropic
            model=agent_client.model if agent_client else "unknown",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cache_read_tokens=total_cache_read_tokens,
            conversation_id=request.conversation_id,
            user_id=current_user_id
        )

    return ChatResponse(
        text=clean_text,
        animations=animations,
        raw=raw_response,
        memory_used=bool(memory_context),
        tool_uses=tool_uses if tool_uses else None,
        sdk_mode=USE_AGENT_SDK,
        conversation_id=request.conversation_id
    )


# Note: Memory endpoints moved to routes/memory.py


@app.post("/conversation/clear")
async def clear_conversation():
    """Clear conversation history"""
    if legacy_client:
        legacy_client.clear_history()
    return {"status": "cleared"}

@app.get("/conversation/history")
async def get_history():
    """Get conversation history"""
    if legacy_client:
        return {"history": legacy_client.get_history()}
    return {"history": [], "note": "Agent SDK manages history internally"}


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


def get_activity_runners() -> Dict[str, Any]:
    """Get runners dict for scheduler dispatch by session type."""
    return {
        "reflection": get_reflection_runner(),
        "research": get_research_runner(),
        "synthesis": get_synthesis_runner(),
        "meta_reflection": get_meta_reflection_runner(),
        "consolidation": get_consolidation_runner(),
        "growth_edge": get_growth_edge_runner(),
        "writing": get_writing_runner(),
        "knowledge_building": get_knowledge_building_runner(),
        "curiosity": get_curiosity_runner(),
        "world_state": get_world_state_runner(),
        "creative": get_creative_runner(),
        "user_model_synthesis": get_user_model_synthesis_runner(),
    }


# Initialize the synthesis runner (lazy - created when needed)
from synthesis_session_runner import SynthesisSessionRunner
_synthesis_runner: Optional[SynthesisSessionRunner] = None

def get_synthesis_runner() -> SynthesisSessionRunner:
    """Get or create the synthesis session runner."""
    global _synthesis_runner
    if _synthesis_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _synthesis_runner = SynthesisSessionRunner(
            goal_manager=goal_manager,
            research_manager=research_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            self_manager=self_manager,
            self_model_graph=self_model_graph,
            token_tracker=token_tracker,
            marker_store=marker_store,
            state_bus=global_state_bus,
        )
    return _synthesis_runner


# Initialize the meta-reflection runner (lazy - created when needed)
from meta_reflection_runner import MetaReflectionRunner
_meta_reflection_runner: Optional[MetaReflectionRunner] = None

def get_meta_reflection_runner() -> MetaReflectionRunner:
    """Get or create the meta-reflection session runner."""
    global _meta_reflection_runner
    if _meta_reflection_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _meta_reflection_runner = MetaReflectionRunner(
            self_manager=self_manager,
            self_model_graph=self_model_graph,
            marker_store=marker_store,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            state_bus=global_state_bus,
        )
    return _meta_reflection_runner


# Initialize the consolidation runner (lazy - created when needed)
from consolidation_session_runner import ConsolidationRunner
_consolidation_runner: Optional[ConsolidationRunner] = None

def get_consolidation_runner() -> ConsolidationRunner:
    """Get or create the consolidation session runner."""
    global _consolidation_runner
    if _consolidation_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _consolidation_runner = ConsolidationRunner(
            research_manager=research_manager,
            memory=memory,
            goal_manager=goal_manager,
            self_manager=self_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            data_dir=DATA_DIR,
            marker_store=marker_store,
            state_bus=global_state_bus,
        )
    return _consolidation_runner


# Initialize the growth edge runner (lazy - created when needed)
from growth_edge_runner import GrowthEdgeRunner
_growth_edge_runner: Optional[GrowthEdgeRunner] = None

def get_growth_edge_runner() -> GrowthEdgeRunner:
    """Get or create the growth edge work session runner."""
    global _growth_edge_runner
    if _growth_edge_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _growth_edge_runner = GrowthEdgeRunner(
            self_manager=self_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
            state_bus=global_state_bus,
        )
    return _growth_edge_runner


# Initialize the writing runner (lazy - created when needed)
from writing_session_runner import WritingRunner
_writing_runner: Optional[WritingRunner] = None

def get_writing_runner() -> WritingRunner:
    """Get or create the writing session runner."""
    global _writing_runner
    if _writing_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _writing_runner = WritingRunner(
            data_dir=str(DATA_DIR),
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _writing_runner


# Initialize the knowledge building runner (lazy - created when needed)
from knowledge_building_runner import KnowledgeBuildingRunner
_knowledge_building_runner: Optional[KnowledgeBuildingRunner] = None

def get_knowledge_building_runner() -> KnowledgeBuildingRunner:
    """Get or create the knowledge building session runner."""
    global _knowledge_building_runner
    if _knowledge_building_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _knowledge_building_runner = KnowledgeBuildingRunner(
            data_dir=str(DATA_DIR),
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _knowledge_building_runner


# Initialize the curiosity runner (lazy - created when needed)
from curiosity_session_runner import CuriosityRunner
_curiosity_runner: Optional[CuriosityRunner] = None

def get_curiosity_runner() -> CuriosityRunner:
    """Get or create the curiosity session runner."""
    global _curiosity_runner
    if _curiosity_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _curiosity_runner = CuriosityRunner(
            data_dir=str(DATA_DIR),
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _curiosity_runner


# Initialize the world state runner (lazy - created when needed)
from world_state_runner import WorldStateRunner
_world_state_runner: Optional[WorldStateRunner] = None

def get_world_state_runner() -> WorldStateRunner:
    """Get or create the world state session runner."""
    global _world_state_runner
    if _world_state_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _world_state_runner = WorldStateRunner(
            data_dir=str(DATA_DIR),
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _world_state_runner


# Initialize the creative runner (lazy - created when needed)
from creative_output_runner import CreativeOutputRunner
_creative_runner: Optional[CreativeOutputRunner] = None

def get_creative_runner() -> CreativeOutputRunner:
    """Get or create the creative output session runner."""
    global _creative_runner
    if _creative_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _creative_runner = CreativeOutputRunner(
            data_dir=str(DATA_DIR),
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _creative_runner


# Initialize user model synthesis runner
from user_model_synthesis_runner import UserModelSynthesisRunner
_user_model_synthesis_runner: Optional[UserModelSynthesisRunner] = None

def get_user_model_synthesis_runner() -> UserModelSynthesisRunner:
    """Get or create the user model synthesis session runner."""
    global _user_model_synthesis_runner
    if _user_model_synthesis_runner is None:
        from config import OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, ANTHROPIC_API_KEY
        _user_model_synthesis_runner = UserModelSynthesisRunner(
            user_manager=user_manager,
            conversation_manager=conversation_manager,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
            marker_store=marker_store,
        )
    return _user_model_synthesis_runner


# Initialize session runners for admin API (must be after getter functions are defined)
from admin_api import init_session_runners, init_consolidation_runner, init_growth_edge_runner, init_writing_runner, init_knowledge_building_runner, init_curiosity_runner, init_world_state_runner, init_creative_runner, init_user_model_synthesis_runner
init_session_runners(get_research_runner, get_reflection_runner, get_synthesis_runner, get_meta_reflection_runner)
init_consolidation_runner(get_consolidation_runner)
init_growth_edge_runner(get_growth_edge_runner)
init_writing_runner(get_writing_runner)
init_knowledge_building_runner(get_knowledge_building_runner)
init_curiosity_runner(get_curiosity_runner)
init_world_state_runner(get_world_state_runner)
init_creative_runner(get_creative_runner)
init_user_model_synthesis_runner(get_user_model_synthesis_runner)


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
    from testing.temporal_metrics import create_timing_data as create_timing
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
        temporal_metrics_tracker=temporal_metrics_tracker,
        connection_manager=manager,
        agent_client=agent_client,
        openai_client=openai_client,
        ollama_client=ollama_client,
        legacy_client=legacy_client,
        response_processor=response_processor,
        tool_executors=TOOL_EXECUTORS,
        create_tool_context_fn=create_tool_ctx,
        execute_tool_batch_fn=exec_batch,
        create_timing_data_fn=create_timing,
        get_automatic_wiki_context_fn=get_automatic_wiki_context,
        process_inline_tags_fn=process_inline_tags,
        generate_and_store_summary_fn=generate_and_store_summary,
        generate_conversation_title_fn=generate_conversation_title,
        get_narration_metrics_fn=narration_metrics,
        auto_summary_interval=AUTO_SUMMARY_INTERVAL,
        daemon_id=_daemon_id,
    )
    set_use_agent_sdk(USE_AGENT_SDK)
    set_tts_state(tts_enabled, tts_voice)


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


# === Run Server ===

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
