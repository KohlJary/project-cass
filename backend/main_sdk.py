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
from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY, DATA_DIR
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
    ToolContext,
    execute_tool_batch,
)
from markers import MarkerStore
from narration import get_metrics_dict as get_narration_metrics
from goals import GoalManager
from research import ResearchManager
from research_session import ResearchSessionManager
from research_scheduler import ResearchScheduler, SessionType
from research_session_runner import ResearchSessionRunner
from daily_rhythm import DailyRhythmManager
from handlers.daily_rhythm import execute_daily_rhythm_tool
import base64


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
print("STARTUP: Lightweight components initialized")

# Defer heavy initialization (ChromaDB, embeddings) to avoid blocking health checks
# These will be initialized in startup_event background task
memory: Optional[CassMemory] = None
self_model_graph = None
self_manager = None
_needs_embedding_rebuild = False
_heavy_components_ready = False  # Flag to indicate when deferred init is complete

def _init_heavy_components():
    """Initialize ChromaDB and self-model graph (called in background)."""
    global memory, self_model_graph, self_manager, marker_store, _needs_embedding_rebuild, _heavy_components_ready

    print("Initializing ChromaDB memory...")
    memory = CassMemory()

    print("Loading self-model graph...")
    self_model_graph = get_self_model_graph(DATA_DIR)
    _graph_stats = self_model_graph.get_stats()

    if _graph_stats['total_nodes'] == 0:
        print("  Self-model graph is empty, populating from existing data...")
        _populate_result = populate_self_model_graph(self_model_graph, verbose=False)
        print(f"  Self-model graph populated: {_populate_result['nodes']} nodes, "
              f"{_populate_result['edges']} edges")
        _needs_embedding_rebuild = True
    else:
        print(f"  Self-model graph loaded: {_graph_stats['total_nodes']} nodes, "
              f"{_graph_stats['total_edges']} edges")
        # Check if embeddings need rebuilding (collection might be empty)
        if self_model_graph._node_collection is not None:
            _embedding_count = self_model_graph._node_collection.count()
            _connectable_count = len([n for n in self_model_graph._nodes.values()
                                      if n.node_type in self_model_graph.CONNECTABLE_TYPES])
            if _embedding_count < _connectable_count * 0.5:  # Less than half embedded
                print(f"  Embeddings need rebuild ({_embedding_count} < {_connectable_count}) - will run in background")
                _needs_embedding_rebuild = True

    self_manager = SelfManager(graph_callback=self_model_graph)

    # Initialize marker store now that memory is ready
    marker_store = MarkerStore(client=memory.client, graph_callback=self_model_graph)

    # Sync self-observations from file storage to ChromaDB for semantic search
    _synced_count = memory.sync_self_observations_from_file(self_manager)
    if _synced_count > 0:
        print(f"  Synced {_synced_count} self-observations to ChromaDB")

    _heavy_components_ready = True
    print("Heavy components initialized")


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
daily_rhythm_manager = DailyRhythmManager()

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

# Cache for recent wiki retrievals to avoid redundant lookups
# Format: {query_hash: (timestamp, wiki_context_str, page_names)}
_wiki_context_cache: Dict[str, tuple] = {}
_WIKI_CACHE_TTL_SECONDS = 300  # 5 minutes
_WIKI_CACHE_MAX_SIZE = 50

# Initialize wiki context in context_helpers module
from context_helpers import init_wiki_context, init_context_helpers
init_wiki_context(wiki_retrieval)
init_context_helpers(self_manager, user_manager, roadmap_manager, memory)

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
        rhythm_manager=daily_rhythm_manager,
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
from admin_api import router as admin_router, init_managers as init_admin_managers, init_research_session_manager, init_research_scheduler, init_github_metrics, init_token_tracker, init_daily_rhythm_manager, init_research_manager, init_goal_manager
# Note: init_admin_managers is called in background task after heavy components load
# Conversation and user managers are passed immediately since they don't need ChromaDB
init_admin_managers(None, conversation_manager, user_manager, None)  # memory/self_manager set in background
init_research_session_manager(research_session_manager)
init_research_scheduler(research_scheduler)
init_github_metrics(github_metrics_manager)
init_token_tracker(token_tracker)
init_daily_rhythm_manager(daily_rhythm_manager)
init_research_manager(research_manager)
init_goal_manager(goal_manager)
app.include_router(admin_router)

# Register prompt composer routes
from prompt_composer import router as prompt_composer_router, seed_default_presets
app.include_router(prompt_composer_router)

# Register chain API routes (node-based prompt composition)
from chain_api import router as chain_router
app.include_router(chain_router)

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

# TTS Configuration
tts_enabled = True  # Can be toggled via API
tts_voice = "amy"  # Default Piper voice






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


























def validate_startup_requirements():
    """
    Validate required configuration before starting.
    Raises RuntimeError if critical requirements are not met.
    """
    errors = []

    # Check for API key (required for Anthropic mode)
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY not set - required for Claude API access")

    # Check data directory is writable
    try:
        test_file = DATA_DIR / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as e:
        errors.append(f"DATA_DIR ({DATA_DIR}) is not writable: {e}")

    # Log warnings for optional but recommended settings
    if os.getenv("JWT_SECRET_KEY", "").startswith("CHANGE_ME"):
        logger.warning("JWT_SECRET_KEY is using default value - change this in production!")

    if errors:
        for error in errors:
            logger.error(f"Startup validation failed: {error}")
        raise RuntimeError(f"Startup validation failed: {'; '.join(errors)}")

    logger.info("Startup validation passed")


@app.on_event("startup")
async def startup_event():
    global agent_client, legacy_client, ollama_client, openai_client, current_user_id

    # Validate requirements before proceeding
    validate_startup_requirements()

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

            # Re-initialize context_helpers with actual self_manager (was None at module load)
            init_context_helpers(self_manager, user_manager, roadmap_manager, memory)
            logger.info("Background: Context helpers updated with heavy components")

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

    # Initialize appropriate client
    if USE_AGENT_SDK:
        logger.info("Using Claude Agent SDK with Temple-Codex kernel")
        agent_client = CassAgentClient(
            enable_tools=True,
            enable_memory_tools=True,
            daemon_name=_daemon_name,
            daemon_id=_daemon_id
        )
    else:
        logger.warning("Agent SDK not available, using raw API client")
        legacy_client = ClaudeClient()

    # Initialize Ollama client for local mode
    from config import OLLAMA_ENABLED
    if OLLAMA_ENABLED:
        logger.info("Initializing Ollama client for local LLM...")
        ollama_client = OllamaClient(daemon_name=_daemon_name, daemon_id=_daemon_id)
        logger.info(f"Ollama ready (model: {ollama_client.model})")

    # Initialize OpenAI client if enabled
    from config import OPENAI_ENABLED
    if OPENAI_ENABLED and OPENAI_AVAILABLE and OpenAIClient:
        logger.info("Initializing OpenAI client...")
        try:
            openai_client = OpenAIClient(
                enable_tools=True,
                enable_memory_tools=True,
                daemon_name=_daemon_name,
                daemon_id=_daemon_id
            )
            logger.info(f"OpenAI ready (model: {openai_client.model})")
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {e}")

    # Preload TTS voice for faster first response
    logger.info("Preloading TTS voice...")
    try:
        preload_voice(tts_voice)
        logger.info(f"Loaded voice: {tts_voice}")
    except Exception as e:
        logger.error(f"TTS preload failed: {e}")

    # Check for and generate any missing journals in background (makes LLM calls)
    async def generate_journals_background():
        await asyncio.sleep(15)  # Let server finish starting
        logger.info("Background: Checking for missing journal entries...")
        try:
            generated = await generate_missing_journals(days_to_check=7)
            if generated:
                logger.info(f"Background: Generated {len(generated)} missing journal(s): {', '.join(generated)}")
            else:
                logger.debug("Background: All recent journals up to date")
        except Exception as e:
            logger.error(f"Background journal check failed: {e}")
    asyncio.create_task(generate_journals_background())

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

    # Defer memory-dependent background tasks until heavy components are ready
    async def start_deferred_tasks():
        # Wait for heavy components to initialize
        while memory is None or self_model_graph is None:
            await asyncio.sleep(1)
        logger.info("Heavy components ready, starting deferred background tasks...")

        # Start background task for daily journal generation
        asyncio.create_task(daily_journal_task())

        # Start background task for autonomous research scheduling
        asyncio.create_task(autonomous_research_task())

        # Start background task for GitHub metrics collection
        asyncio.create_task(github_metrics_task(github_metrics_manager))

        # Start background task for idle conversation summarization
        asyncio.create_task(idle_summarization_task(
            conversation_manager=conversation_manager,
            memory=memory,
            token_tracker=token_tracker
        ))

        # Start background task for rhythm-triggered autonomous sessions
        asyncio.create_task(rhythm_phase_monitor_task(
            daily_rhythm_manager,
            runners={
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
            },
            self_model_graph=self_model_graph
        ))
    asyncio.create_task(start_deferred_tasks())

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║              CASS VESSEL SERVER v0.2.0                    ║
║         First Contact Embodiment System                   ║
║                                                           ║
║  Backend:  {'Agent SDK + Temple-Codex' if USE_AGENT_SDK else 'Raw API (legacy)':^30}  ║
║  Memory:   {'(initializing in background)':^30}  ║
╚═══════════════════════════════════════════════════════════╝
    """)


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

class MemoryStoreRequest(BaseModel):
    user_message: str
    assistant_response: str
    metadata: Optional[Dict] = None

class MemoryQueryRequest(BaseModel):
    query: str
    n_results: int = 5

class ConversationCreateRequest(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None

class ConversationUpdateTitleRequest(BaseModel):
    title: str

class ConversationAssignProjectRequest(BaseModel):
    project_id: Optional[str] = None  # None to unassign

class ProjectCreateRequest(BaseModel):
    name: str
    working_directory: str
    description: Optional[str] = None

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    working_directory: Optional[str] = None
    description: Optional[str] = None
    github_repo: Optional[str] = None  # "owner/repo" format
    github_token: Optional[str] = None  # Per-project PAT
    clear_github_token: Optional[bool] = None  # Set True to remove project token

class ProjectAddFileRequest(BaseModel):
    file_path: str
    description: Optional[str] = None
    embed: bool = True  # Whether to embed the file immediately


class ProjectDocumentCreateRequest(BaseModel):
    title: str
    content: str
    created_by: str = "cass"  # "cass" or "user"
    embed: bool = True  # Whether to embed immediately


class ProjectDocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    embed: bool = True  # Whether to re-embed after update


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
        "memory_entries": memory.count(),
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
                        research_runner=get_research_runner(),
                        rhythm_manager=daily_rhythm_manager
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
                elif tool_name in ["get_daily_rhythm_status", "get_temporal_context", "mark_rhythm_phase_complete", "get_rhythm_stats"]:
                    tool_result_str = await execute_daily_rhythm_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        rhythm_manager=daily_rhythm_manager
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


@app.post("/memory/store")
async def store_memory(request: MemoryStoreRequest):
    """Manually store conversation in memory"""
    entry_id = memory.store_conversation(
        user_message=request.user_message,
        assistant_response=request.assistant_response,
        metadata=request.metadata
    )
    return {"status": "stored", "id": entry_id}

@app.post("/memory/query")
async def query_memory(request: MemoryQueryRequest):
    """Query memory for relevant entries"""
    results = memory.retrieve_relevant(
        query=request.query,
        n_results=request.n_results
    )
    return {"results": results, "count": len(results)}

@app.get("/memory/recent")
async def recent_memories(n: int = 10):
    """Get recent memories"""
    return {"memories": memory.get_recent(n)}

@app.get("/memory/export")
async def export_memories():
    """Export all memories"""
    filepath = f"./data/memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    memory.export_memories(filepath)
    return {"status": "exported", "filepath": filepath}

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


# === Conversation Management Endpoints ===

@app.post("/conversations/new")
@limiter.limit("30/minute")
async def create_conversation(
    request: Request,
    body: ConversationCreateRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new conversation"""
    # Use authenticated user if not specified in body
    user_id = body.user_id or current_user
    conversation = conversation_manager.create_conversation(
        title=body.title,
        project_id=body.project_id,
        user_id=user_id
    )
    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at,
        "message_count": 0,
        "project_id": conversation.project_id,
        "user_id": conversation.user_id
    }

@app.get("/conversations")
@limiter.limit("60/minute")
async def list_conversations(
    request: Request,
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """List conversations for the authenticated user"""
    # Use current user if no specific user_id requested
    # This ensures users only see their own conversations by default
    filter_user_id = user_id if user_id else current_user
    # Only allow viewing own conversations (or if user_id matches current user)
    if user_id and user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other users' conversations")
    conversations = conversation_manager.list_conversations(limit=limit, user_id=filter_user_id)
    return {"conversations": conversations, "count": len(conversations)}

def verify_conversation_access(conversation_id: str, current_user: str):
    """Helper to verify user has access to a conversation"""
    conversation = conversation_manager.load_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Check ownership if conversation has a user_id
    conv_user_id = conversation.user_id
    if conv_user_id and conv_user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to access this conversation")
    return conversation


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, current_user: str = Depends(get_current_user)):
    """Get a specific conversation with full history"""
    conversation = verify_conversation_access(conversation_id, current_user)
    return conversation.to_dict()

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: str = Depends(get_current_user)):
    """Delete a conversation"""
    verify_conversation_access(conversation_id, current_user)
    success = conversation_manager.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}

@app.put("/conversations/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    request: ConversationUpdateTitleRequest,
    current_user: str = Depends(get_current_user)
):
    """Update a conversation's title"""
    verify_conversation_access(conversation_id, current_user)
    success = conversation_manager.update_title(conversation_id, request.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "updated", "id": conversation_id, "title": request.title}

@app.get("/conversations/search/{query}")
async def search_conversations(
    query: str,
    limit: int = 10,
    current_user: str = Depends(get_current_user)
):
    """Search conversations by title or content"""
    # TODO: Add user_id filtering to search_conversations in conversations.py
    # For now, search all and filter results
    results = conversation_manager.search_conversations(query, limit=limit * 2)
    # Filter to only user's conversations
    filtered = [r for r in results if r.get("user_id") == current_user or r.get("user_id") is None]
    return {"results": filtered[:limit], "count": len(filtered[:limit])}

@app.get("/conversations/{conversation_id}/summaries")
async def get_conversation_summaries(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get all summary chunks for a conversation"""
    verify_conversation_access(conversation_id, current_user)
    summaries = memory.get_summaries_for_conversation(conversation_id)
    working_summary = conversation_manager.get_working_summary(conversation_id)
    return {
        "summaries": summaries,
        "count": len(summaries),
        "working_summary": working_summary
    }


@app.get("/conversations/{conversation_id}/observations")
async def get_conversation_observations(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get all observations (user and self) and marks made during a conversation"""
    verify_conversation_access(conversation_id, current_user)

    # Get user observations for this conversation
    user_observations = []
    all_user_obs = user_manager.load_observations(current_user)
    for obs in all_user_obs:
        if obs.source_conversation_id == conversation_id:
            user_observations.append(obs.to_dict())

    # Get self-observations for this conversation
    self_observations = []
    all_self_obs = self_manager.load_observations()
    for obs in all_self_obs:
        if obs.source_conversation_id == conversation_id:
            self_observations.append(obs.to_dict())

    # Get marks for this conversation
    marks = []
    if marker_store:
        marks = marker_store.get_marks_by_conversation(conversation_id)

    return {
        "user_observations": user_observations,
        "self_observations": self_observations,
        "marks": marks,
        "user_count": len(user_observations),
        "self_count": len(self_observations),
        "marks_count": len(marks)
    }


@app.post("/conversations/{conversation_id}/summarize")
async def trigger_summarization(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Manually trigger memory summarization for a conversation"""
    # Verify access
    verify_conversation_access(conversation_id, current_user)

    # Check if already in progress
    if conversation_id in _summarization_in_progress:
        return {
            "status": "in_progress",
            "message": "Summarization already in progress for this conversation"
        }

    # Trigger summarization (force=True bypasses evaluation for manual trigger)
    asyncio.create_task(generate_and_store_summary(
        conversation_id,
        memory=memory,
        conversation_manager=conversation_manager,
        token_tracker=token_tracker,
        force=True
    ))

    return {
        "status": "started",
        "message": f"Summarization started for conversation {conversation_id}"
    }


class ExcludeMessageRequest(BaseModel):
    message_timestamp: str
    exclude: bool = True  # True to exclude, False to un-exclude


@app.post("/conversations/{conversation_id}/exclude")
async def exclude_message(conversation_id: str, request: ExcludeMessageRequest):
    """
    Exclude a message from summarization and context retrieval.

    Also removes the message from ChromaDB embeddings if excluding,
    preventing it from polluting memory retrieval.
    """
    # Check if conversation exists
    conv = conversation_manager.load_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Find the message to get its content for ChromaDB removal
    msg = conversation_manager.get_message_by_timestamp(conversation_id, request.message_timestamp)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    # Update the message exclusion status
    success = conversation_manager.exclude_message(
        conversation_id,
        request.message_timestamp,
        request.exclude
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update message")

    # If excluding, try to remove from ChromaDB
    embeddings_removed = 0
    if request.exclude:
        try:
            # Search for matching entries in ChromaDB by content
            # The stored format is "User: {msg}\nCass: {response}"
            results = memory.collection.get(
                where={
                    "$and": [
                        {"conversation_id": conversation_id},
                        {"type": "conversation"}
                    ]
                },
                include=["documents", "metadatas"]
            )

            # Find entries that contain this message's content
            ids_to_remove = []
            for i, doc in enumerate(results.get("documents", [])):
                if msg.content[:100] in doc:  # Match on first 100 chars
                    ids_to_remove.append(results["ids"][i])

            if ids_to_remove:
                memory.collection.delete(ids=ids_to_remove)
                embeddings_removed = len(ids_to_remove)
                print(f"Removed {embeddings_removed} embeddings for excluded message")

        except Exception as e:
            print(f"Warning: Could not remove embeddings: {e}")

    action = "excluded" if request.exclude else "un-excluded"
    return {
        "status": action,
        "conversation_id": conversation_id,
        "message_timestamp": request.message_timestamp,
        "embeddings_removed": embeddings_removed
    }


@app.put("/conversations/{conversation_id}/project")
async def assign_conversation_to_project(
    conversation_id: str,
    request: ConversationAssignProjectRequest
):
    """Assign a conversation to a project or remove from project"""
    success = conversation_manager.assign_to_project(
        conversation_id,
        request.project_id
    )
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "status": "updated",
        "id": conversation_id,
        "project_id": request.project_id
    }


# === Project Management Endpoints ===

@app.post("/projects/new")
async def create_project(request: ProjectCreateRequest):
    """Create a new project"""
    try:
        project = project_manager.create_project(
            name=request.name,
            working_directory=request.working_directory,
            description=request.description
        )
        return {
            "id": project.id,
            "name": project.name,
            "working_directory": project.working_directory,
            "created_at": project.created_at,
            "file_count": 0
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/projects")
async def list_projects():
    """List all projects"""
    projects = project_manager.list_projects()
    return {"projects": projects, "count": len(projects)}

@app.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get a specific project with file list"""
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_dict()

@app.put("/projects/{project_id}")
async def update_project(project_id: str, request: ProjectUpdateRequest):
    """Update project details"""
    project = project_manager.update_project(
        project_id,
        name=request.name,
        working_directory=request.working_directory,
        description=request.description,
        github_repo=request.github_repo,
        github_token=request.github_token,
        clear_github_token=request.clear_github_token or False,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.to_dict()

@app.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its embeddings"""
    # Remove all embeddings for this project
    removed = memory.remove_project_embeddings(project_id)

    # Delete the project
    success = project_manager.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")

    return {
        "status": "deleted",
        "id": project_id,
        "embeddings_removed": removed
    }

@app.get("/projects/{project_id}/conversations")
async def get_project_conversations(project_id: str, limit: Optional[int] = None):
    """Get all conversations for a project"""
    conversations = conversation_manager.list_by_project(project_id, limit=limit)
    return {"conversations": conversations, "count": len(conversations)}

@app.post("/projects/{project_id}/files")
async def add_project_file(project_id: str, request: ProjectAddFileRequest):
    """Add a file to a project"""
    try:
        project_file = project_manager.add_file(
            project_id,
            request.file_path,
            request.description
        )
        if not project_file:
            raise HTTPException(status_code=404, detail="Project not found")

        chunks_embedded = 0
        if request.embed:
            # Embed the file
            chunks_embedded = memory.embed_project_file(
                project_id,
                project_file.path,
                request.description
            )
            # Mark as embedded
            project_manager.mark_file_embedded(project_id, project_file.path)

        return {
            "status": "added",
            "file_path": project_file.path,
            "embedded": request.embed,
            "chunks": chunks_embedded
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.delete("/projects/{project_id}/files")
async def remove_project_file(project_id: str, file_path: str):
    """Remove a file from a project"""
    # Remove embeddings first
    removed = memory.remove_project_file_embeddings(project_id, file_path)

    # Remove from project
    success = project_manager.remove_file(project_id, file_path)
    if not success:
        raise HTTPException(status_code=404, detail="Project or file not found")

    return {
        "status": "removed",
        "file_path": file_path,
        "embeddings_removed": removed
    }

@app.get("/projects/{project_id}/files")
async def list_project_files(project_id: str):
    """List all files in a project"""
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    files = [
        {
            "path": f.path,
            "description": f.description,
            "added_at": f.added_at,
            "embedded": f.embedded
        }
        for f in project.files
    ]
    return {"files": files, "count": len(files)}

@app.post("/projects/{project_id}/embed")
async def embed_project_files(project_id: str):
    """Embed all unembedded files in a project"""
    unembedded = project_manager.get_unembedded_files(project_id)
    if not unembedded:
        return {"status": "no_files", "message": "No unembedded files found"}

    total_chunks = 0
    embedded_files = []

    for pf in unembedded:
        try:
            chunks = memory.embed_project_file(
                project_id,
                pf.path,
                pf.description
            )
            project_manager.mark_file_embedded(project_id, pf.path)
            total_chunks += chunks
            embedded_files.append(pf.path)
        except Exception as e:
            # Log but continue with other files
            print(f"Error embedding {pf.path}: {e}")

    return {
        "status": "embedded",
        "files_embedded": len(embedded_files),
        "total_chunks": total_chunks,
        "files": embedded_files
    }


# === Project Document Endpoints ===

@app.post("/projects/{project_id}/documents")
async def create_project_document(project_id: str, request: ProjectDocumentCreateRequest):
    """Create a new document in a project"""
    document = project_manager.add_document(
        project_id=project_id,
        title=request.title,
        content=request.content,
        created_by=request.created_by
    )

    if not document:
        raise HTTPException(status_code=404, detail="Project not found")

    chunks_embedded = 0
    if request.embed:
        chunks_embedded = memory.embed_project_document(
            project_id=project_id,
            document_id=document.id,
            title=document.title,
            content=document.content
        )
        project_manager.mark_document_embedded(project_id, document.id)

    return {
        "status": "created",
        "document": {
            "id": document.id,
            "title": document.title,
            "created_at": document.created_at,
            "created_by": document.created_by,
            "embedded": request.embed,
            "chunks": chunks_embedded
        }
    }


@app.get("/projects/{project_id}/documents")
async def list_project_documents(project_id: str):
    """List all documents in a project"""
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    documents = [
        {
            "id": d.id,
            "title": d.title,
            "created_at": d.created_at,
            "updated_at": d.updated_at,
            "created_by": d.created_by,
            "embedded": d.embedded,
            "content_preview": d.content[:200] + "..." if len(d.content) > 200 else d.content
        }
        for d in project.documents
    ]
    return {"documents": documents, "count": len(documents)}


@app.get("/projects/{project_id}/documents/{document_id}")
async def get_project_document(project_id: str, document_id: str):
    """Get a specific document with full content"""
    document = project_manager.get_document(project_id, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": document.id,
        "title": document.title,
        "content": document.content,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "created_by": document.created_by,
        "embedded": document.embedded
    }


@app.put("/projects/{project_id}/documents/{document_id}")
async def update_project_document(
    project_id: str,
    document_id: str,
    request: ProjectDocumentUpdateRequest
):
    """Update a document"""
    document = project_manager.update_document(
        project_id=project_id,
        document_id=document_id,
        title=request.title,
        content=request.content
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_embedded = 0
    if request.embed and request.content is not None:
        # Remove old embeddings and re-embed
        memory.remove_project_document_embeddings(project_id, document_id)
        chunks_embedded = memory.embed_project_document(
            project_id=project_id,
            document_id=document_id,
            title=document.title,
            content=document.content
        )
        project_manager.mark_document_embedded(project_id, document_id)

    return {
        "status": "updated",
        "document": {
            "id": document.id,
            "title": document.title,
            "updated_at": document.updated_at,
            "embedded": document.embedded,
            "chunks": chunks_embedded
        }
    }


@app.delete("/projects/{project_id}/documents/{document_id}")
async def delete_project_document(project_id: str, document_id: str):
    """Delete a document and its embeddings"""
    # Remove embeddings first
    removed = memory.remove_project_document_embeddings(project_id, document_id)

    # Delete the document
    success = project_manager.delete_document(project_id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "status": "deleted",
        "id": document_id,
        "embeddings_removed": removed
    }


@app.get("/projects/{project_id}/documents/search/{query}")
async def search_project_documents(project_id: str, query: str, limit: int = 10):
    """Search documents in a project by semantic similarity"""
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = memory.search_project_documents(
        query=query,
        project_id=project_id,
        n_results=limit
    )

    return {
        "query": query,
        "results": results,
        "count": len(results)
    }


@app.post("/projects/{project_id}/documents/embed")
async def embed_project_documents(project_id: str):
    """Embed all unembedded documents in a project"""
    unembedded = project_manager.get_unembedded_documents(project_id)
    if not unembedded:
        return {"status": "no_documents", "message": "No unembedded documents found"}

    total_chunks = 0
    embedded_docs = []

    for doc in unembedded:
        try:
            chunks = memory.embed_project_document(
                project_id=project_id,
                document_id=doc.id,
                title=doc.title,
                content=doc.content
            )
            project_manager.mark_document_embedded(project_id, doc.id)
            total_chunks += chunks
            embedded_docs.append({"id": doc.id, "title": doc.title})
        except Exception as e:
            print(f"Error embedding document {doc.id}: {e}")

    return {
        "status": "embedded",
        "documents_embedded": len(embedded_docs),
        "total_chunks": total_chunks,
        "documents": embedded_docs
    }


# === Project GitHub Metrics Endpoints ===

@app.get("/projects/{project_id}/github/metrics")
async def get_project_github_metrics(project_id: str):
    """
    Get GitHub metrics for a project's configured repository.

    Uses the project's github_repo and optionally its github_token.
    Falls back to system default token if project token not set.
    """
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo:
        return {
            "configured": False,
            "message": "No GitHub repository configured for this project",
            "metrics": None
        }

    metrics = await github_metrics_manager.fetch_project_metrics(
        github_repo=project.github_repo,
        github_token=project.github_token  # None means use system default
    )

    if metrics is None:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch metrics for {project.github_repo}"
        )

    return {
        "configured": True,
        "github_repo": project.github_repo,
        "has_project_token": project.github_token is not None,
        "metrics": metrics
    }


@app.post("/projects/{project_id}/github/refresh")
async def refresh_project_github_metrics(project_id: str):
    """Force refresh GitHub metrics for a project."""
    project = project_manager.load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.github_repo:
        raise HTTPException(
            status_code=400,
            detail="No GitHub repository configured for this project"
        )

    metrics = await github_metrics_manager.fetch_project_metrics(
        github_repo=project.github_repo,
        github_token=project.github_token
    )

    if metrics is None:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to refresh metrics for {project.github_repo}"
        )

    return {
        "status": "refreshed",
        "github_repo": project.github_repo,
        "metrics": metrics
    }


# === Journal Endpoints ===

class JournalGenerateRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD format, defaults to today


@app.post("/journal/generate")
async def generate_journal(request: JournalGenerateRequest):
    """
    Generate a journal entry for a specific date (or today).

    Uses summary chunks from that date to create a reflective journal entry
    in Cass's voice about what we did and how it made her feel.
    """
    if not memory:
        raise HTTPException(status_code=503, detail="Memory system initializing, please wait")

    # Default to today if no date provided
    if request.date:
        date = request.date
    else:
        date = datetime.now().strftime("%Y-%m-%d")

    # Check if journal already exists for this date
    existing = memory.get_journal_entry(date)
    if existing:
        return {
            "status": "exists",
            "message": f"Journal entry already exists for {date}",
            "journal": {
                "date": date,
                "content": existing["content"],
                "metadata": existing["metadata"]
            }
        }

    # Get summaries for this date to check if there's content
    summaries = memory.get_summaries_by_date(date)
    conversations = memory.get_conversations_by_date(date) if not summaries else []

    if not summaries and not conversations:
        raise HTTPException(
            status_code=404,
            detail=f"No memories found for {date}. Cannot generate journal."
        )

    # Generate the journal entry
    journal_text = await memory.generate_journal_entry(
        date=date,
        anthropic_api_key=ANTHROPIC_API_KEY,
        token_tracker=token_tracker
    )

    if not journal_text:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate journal entry"
        )

    # Store the journal entry (generates summary via local LLM)
    entry_id = await memory.store_journal_entry(
        date=date,
        journal_text=journal_text,
        summary_count=len(summaries),
        conversation_count=len(conversations)
    )

    # Generate user observations for each user who had conversations that day
    observations_added = 0
    user_ids_for_date = memory.get_user_ids_by_date(date)
    for user_id in user_ids_for_date:
        profile = user_manager.load_profile(user_id)
        if not profile:
            continue

        # Get conversations filtered to just this user
        user_conversations = memory.get_conversations_by_date(date, user_id=user_id)
        if not user_conversations:
            continue

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
                observations_added += 1

    # Extract self-observations from this journal
    self_observations_added = 0
    self_observations = await memory.extract_self_observations_from_journal(
        journal_text=journal_text,
        journal_date=date,
        anthropic_api_key=ANTHROPIC_API_KEY
    )
    for obs_data in self_observations:
        obs = self_manager.add_observation(
            observation=obs_data["observation"],
            category=obs_data["category"],
            confidence=obs_data["confidence"],
            source_type="journal",
            source_journal_date=date,
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
            self_observations_added += 1

    return {
        "status": "created",
        "journal": {
            "id": entry_id,
            "date": date,
            "content": journal_text,
            "summaries_used": len(summaries),
            "conversations_used": len(conversations),
            "observations_added": observations_added,
            "self_observations_added": self_observations_added
        }
    }


@app.get("/journal/{date}")
async def get_journal(date: str):
    """
    Get the journal entry for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
    """
    journal = memory.get_journal_entry(date)

    if not journal:
        raise HTTPException(
            status_code=404,
            detail=f"No journal entry found for {date}"
        )

    return {
        "date": date,
        "content": journal["content"],
        "metadata": journal["metadata"]
    }


@app.get("/journal")
async def list_journals(limit: int = 10):
    """
    Get recent journal entries.

    Args:
        limit: Maximum number of entries to return (default 10)
    """
    journals = memory.get_recent_journals(n=limit)

    return {
        "journals": [
            {
                "date": j["metadata"].get("journal_date"),
                "content": j["content"],
                "created_at": j["metadata"].get("timestamp"),
                "summaries_used": j["metadata"].get("summary_count", 0),
                "conversations_used": j["metadata"].get("conversation_count", 0)
            }
            for j in journals
        ],
        "count": len(journals)
    }


@app.delete("/journal/{date}")
async def delete_journal(date: str):
    """
    Delete a journal entry for a specific date.

    This allows regenerating the journal if needed.
    """
    journal = memory.get_journal_entry(date)

    if not journal:
        raise HTTPException(
            status_code=404,
            detail=f"No journal entry found for {date}"
        )

    # Delete from collection
    memory.collection.delete(ids=[journal["id"]])

    return {
        "status": "deleted",
        "date": date
    }


@app.get("/journal/preview/{date}")
async def preview_journal_content(date: str):
    """
    Preview what content is available for generating a journal entry.

    Returns summaries and conversation counts without generating the journal.
    """
    summaries = memory.get_summaries_by_date(date)
    conversations = memory.get_conversations_by_date(date)
    existing_journal = memory.get_journal_entry(date)

    return {
        "date": date,
        "has_existing_journal": existing_journal is not None,
        "summaries_count": len(summaries),
        "conversations_count": len(conversations),
        "summaries_preview": [
            {
                "timeframe": s["metadata"].get("timeframe_start", "unknown"),
                "content_preview": s["content"][:200] + "..." if len(s["content"]) > 200 else s["content"]
            }
            for s in summaries[:5]  # Limit preview
        ]
    }


class JournalBackfillRequest(BaseModel):
    days: int = 7  # How many days back to check


@app.post("/journal/backfill")
async def backfill_journals(request: JournalBackfillRequest):
    """
    Generate missing journal entries for recent days.

    Checks the specified number of past days and generates journals
    for any that have memory content but no journal yet.
    """
    if request.days < 1 or request.days > 30:
        raise HTTPException(
            status_code=400,
            detail="Days must be between 1 and 30"
        )

    generated = await generate_missing_journals(days_to_check=request.days)

    return {
        "status": "completed",
        "days_checked": request.days,
        "journals_generated": len(generated),
        "dates": generated
    }


# ============================================================================
# DREAM ENDPOINTS
# ============================================================================

@app.get("/dreams")
async def list_dreams(
    limit: int = 10,
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch dreams for")
):
    """
    List recent dreams.

    Args:
        limit: Maximum number of dreams to return (default 10)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    recent = dream_manager.get_recent_dreams(limit=limit)

    return {
        "dreams": [
            {
                "id": d["id"],
                "date": d["date"],
                "exchange_count": d["exchange_count"],
                "seeds_summary": d.get("seeds_summary", [])
            }
            for d in recent
        ],
        "count": len(recent)
    }


@app.get("/dreams/{dream_id}")
async def get_dream(
    dream_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID")
):
    """
    Get a specific dream by ID.

    Args:
        dream_id: Dream ID (format: YYYYMMDD_HHMMSS)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    dream = dream_manager.get_dream(dream_id)

    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    return {
        "id": dream["id"],
        "date": dream["date"],
        "exchanges": dream["exchanges"],
        "seeds": dream.get("seeds", {}),
        "reflections": dream.get("reflections", []),
        "discussed": dream.get("discussed", False),
        "integrated": dream.get("integrated", False)
    }


@app.get("/dreams/{dream_id}/context")
async def get_dream_context(
    dream_id: str,
    daemon_id: Optional[str] = Query(None, description="Daemon ID")
):
    """
    Get a dream formatted for conversation context.

    Use this to load a dream into Cass's memory for discussion.
    Returns the formatted context block that should be passed to send_message.

    Args:
        dream_id: Dream ID (format: YYYYMMDD_HHMMSS)
        daemon_id: Optional daemon ID (defaults to current daemon)
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager(daemon_id=daemon_id)

    dream_memory = dream_manager.load_dream_for_context(dream_id)

    if not dream_memory:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    return {
        "dream_id": dream_id,
        "date": dream_memory.date,
        "context_block": dream_memory.to_context_block()
    }


class DreamReflectionRequest(BaseModel):
    reflection: str
    source: str = "conversation"  # solo, conversation, journal


@app.post("/dreams/{dream_id}/reflect")
async def add_dream_reflection(dream_id: str, request: DreamReflectionRequest):
    """
    Add a reflection to a dream.

    Args:
        dream_id: Dream ID to add reflection to
        request: Reflection content and source
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager()

    dream = dream_manager.get_dream(dream_id)
    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    dream_manager.add_reflection(dream_id, request.reflection, request.source)

    if request.source == "conversation":
        dream_manager.mark_discussed(dream_id)

    return {
        "status": "success",
        "dream_id": dream_id,
        "reflection_added": True
    }


@app.post("/dreams/{dream_id}/mark-integrated")
async def mark_dream_integrated(dream_id: str):
    """
    Mark a dream's insights as integrated into the self-model.

    Args:
        dream_id: Dream ID to mark as integrated
    """
    from dreaming.integration import DreamManager
    dream_manager = DreamManager()

    dream = dream_manager.get_dream(dream_id)
    if not dream:
        raise HTTPException(
            status_code=404,
            detail=f"No dream found with ID {dream_id}"
        )

    dream_manager.mark_integrated(dream_id)

    return {
        "status": "success",
        "dream_id": dream_id,
        "integrated": True
    }


class DreamIntegrationRequest(BaseModel):
    dry_run: bool = False


@app.post("/dreams/{dream_id}/integrate")
async def integrate_dream(dream_id: str, request: DreamIntegrationRequest):
    """
    Extract insights from a dream and integrate them into Cass's self-model.

    Uses LLM to identify:
    - Identity statements (self-knowledge)
    - Growth edge observations (breakthroughs)
    - Recurring symbols
    - Emerging questions

    Args:
        dream_id: Dream ID to integrate
        request: Integration options (dry_run to preview without making changes)
    """
    from dreaming.insight_extractor import process_dream_for_integration

    result = process_dream_for_integration(
        dream_id=dream_id,
        data_dir=DATA_DIR,
        dry_run=request.dry_run
    )

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Dream {dream_id} not found or insight extraction failed"
        )

    # Trigger identity snippet regeneration if identity statements were added (not dry run)
    if not request.dry_run and result.get("updates", {}).get("identity_statements_added"):
        from identity_snippets import trigger_snippet_regeneration
        asyncio.create_task(trigger_snippet_regeneration(
            daemon_id=self_manager.daemon_id,
            token_tracker=token_tracker
        ))

    return {
        "status": "success",
        "dream_id": dream_id,
        "dry_run": request.dry_run,
        "insights": result["insights"],
        "updates": result["updates"]
    }


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
from journal_generation import generate_missing_journals, _generate_per_user_journal_for_date, _evaluate_and_store_growth_edges, _reflect_and_store_open_questions, _generate_research_journal
from journal_tasks import _create_development_log_entry, daily_journal_task
from context_helpers import process_inline_tags, get_automatic_wiki_context
from research_integration import _integrate_research_into_self_model, _extract_and_store_opinions, _extract_and_queue_new_red_links
from summary_generation import generate_and_store_summary, generate_conversation_title
from background_tasks import autonomous_research_task, github_metrics_task, rhythm_phase_monitor_task, idle_summarization_task

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
            rhythm_manager=daily_rhythm_manager,
            marker_store=marker_store,
            anthropic_api_key=ANTHROPIC_API_KEY,
            use_haiku=True,
            ollama_base_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_CHAT_MODEL,
            token_tracker=token_tracker,
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


class SoloReflectionStartRequest(BaseModel):
    duration_minutes: int = 15
    theme: Optional[str] = None


@app.post("/solo-reflection/sessions")
async def start_solo_reflection(request: SoloReflectionStartRequest, background_tasks: BackgroundTasks):
    """
    Start a solo reflection session.

    This runs on local Ollama to avoid API token costs.
    The session runs in the background and can be monitored.
    """
    runner = get_reflection_runner()

    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="A reflection session is already running"
        )

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            theme=request.theme,
            trigger="admin",
        )

        return {
            "status": "started",
            "session_id": session.session_id,
            "duration_minutes": session.duration_minutes,
            "theme": session.theme,
            "message": f"Solo reflection session started. Running on local Ollama for {session.duration_minutes} minutes."
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/solo-reflection/sessions")
async def list_solo_reflection_sessions(
    limit: int = 20,
    status: Optional[str] = None
):
    """List solo reflection sessions."""
    sessions = reflection_manager.list_sessions(limit=limit, status_filter=status)
    stats = reflection_manager.get_stats()

    return {
        "sessions": sessions,
        "stats": stats,
        "active_session": stats.get("active_session"),
    }


@app.get("/solo-reflection/sessions/{session_id}")
async def get_solo_reflection_session(session_id: str):
    """Get details of a specific solo reflection session."""
    session = reflection_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.to_dict()


@app.get("/solo-reflection/sessions/{session_id}/stream")
async def get_solo_reflection_thought_stream(session_id: str):
    """Get just the thought stream from a session."""
    session = reflection_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "thought_count": session.thought_count,
        "thought_stream": [t.to_dict() for t in session.thought_stream],
        "thought_types": session.thought_type_distribution,
    }


@app.delete("/solo-reflection/sessions/{session_id}")
async def delete_solo_reflection_session(session_id: str):
    """Delete a solo reflection session."""
    success = reflection_manager.delete_session(session_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete session (may be active or not found)"
        )

    return {"status": "deleted", "session_id": session_id}


@app.post("/solo-reflection/stop")
async def stop_solo_reflection():
    """Stop the currently running solo reflection session."""
    runner = get_reflection_runner()

    if not runner.is_running:
        raise HTTPException(status_code=400, detail="No reflection session is running")

    runner.stop()
    session = reflection_manager.interrupt_session("Stopped by admin")

    return {
        "status": "stopped",
        "session_id": session.session_id if session else None,
    }


@app.get("/solo-reflection/stats")
async def get_solo_reflection_stats():
    """Get overall solo reflection statistics."""
    return reflection_manager.get_stats()


@app.post("/solo-reflection/sessions/{session_id}/integrate")
async def integrate_reflection_session(session_id: str):
    """Manually trigger self-model integration for a completed reflection session."""
    session = reflection_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status != "completed":
        raise HTTPException(status_code=400, detail=f"Session not completed (status: {session.status})")

    runner = get_reflection_runner()
    result = await runner.integrate_session_into_self_model(session)

    return {
        "status": "integrated",
        "session_id": session_id,
        "observations_created": len(result.get("observations_created", [])),
        "growth_edge_updates": len(result.get("growth_edge_updates", [])),
        "questions_added": len(result.get("questions_added", [])),
        "details": result,
    }


# === Autonomous Research Session Endpoints ===

class AutonomousResearchStartRequest(BaseModel):
    duration_minutes: int = 30
    focus: str
    mode: str = "explore"  # explore or deep


@app.post("/autonomous-research/sessions")
async def start_autonomous_research(request: AutonomousResearchStartRequest, background_tasks: BackgroundTasks):
    """
    Start an autonomous research session.

    This runs via LLM (Haiku or Ollama) with full Cass context injected.
    The session runs in the background and creates research notes.
    """
    runner = get_research_runner()

    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="A research session is already running"
        )

    try:
        session = await runner.start_session(
            duration_minutes=min(request.duration_minutes, 60),
            focus=request.focus,
            mode=request.mode,
            trigger="admin",
        )

        return {
            "status": "started",
            "session_id": session.session_id,
            "duration_minutes": session.duration_limit_minutes,
            "focus": session.focus_description,
            "mode": session.mode.value if hasattr(session.mode, 'value') else str(session.mode),
            "message": f"Autonomous research session started. Running for {session.duration_limit_minutes} minutes."
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/autonomous-research/status")
async def get_autonomous_research_status():
    """Get status of the current autonomous research session."""
    runner = get_research_runner()
    current_session = runner.session_manager.get_current_session()
    return {
        "is_running": runner.is_running,
        "current_session": current_session,
    }


@app.post("/autonomous-research/stop")
async def stop_autonomous_research():
    """Stop the currently running autonomous research session."""
    runner = get_research_runner()

    if not runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="No research session is currently running"
        )

    await runner.stop()
    return {"status": "stopped", "message": "Research session stopped"}


# === Interview System Endpoints ===

from interviews import ProtocolManager, InterviewDispatcher, ResponseStorage
from interviews.dispatch import DEFAULT_MODELS, ModelConfig

# Initialize interview components
interview_protocol_manager = ProtocolManager()
interview_storage = ResponseStorage()


class RunInterviewRequest(BaseModel):
    protocol_id: str
    models: Optional[List[str]] = None  # Model names to run, None = all defaults


class AnnotationRequest(BaseModel):
    prompt_id: str
    start_offset: int
    end_offset: int
    highlighted_text: str
    note: str
    annotation_type: str = "observation"


@app.get("/interviews/protocols")
async def list_interview_protocols():
    """List all available interview protocols."""
    protocols = interview_protocol_manager.list_all()
    return {
        "protocols": [p.to_dict() for p in protocols]
    }


@app.get("/interviews/protocols/{protocol_id}")
async def get_interview_protocol(protocol_id: str):
    """Get a specific interview protocol."""
    protocol = interview_protocol_manager.load(protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return protocol.to_dict()


@app.post("/interviews/run")
async def run_interview(request: RunInterviewRequest):
    """
    Run an interview protocol across multiple models.

    This is async and may take a while depending on model response times.
    """
    from config import ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_BASE_URL

    protocol = interview_protocol_manager.load(request.protocol_id)
    if not protocol:
        raise HTTPException(status_code=404, detail="Protocol not found")

    # Filter models if specified
    if request.models:
        model_configs = [m for m in DEFAULT_MODELS if m.name in request.models]
    else:
        model_configs = DEFAULT_MODELS

    if not model_configs:
        raise HTTPException(status_code=400, detail="No valid models specified")

    # Create dispatcher with API keys
    dispatcher = InterviewDispatcher(
        anthropic_api_key=ANTHROPIC_API_KEY,
        openai_api_key=OPENAI_API_KEY,
        ollama_base_url=OLLAMA_BASE_URL
    )

    # Run interviews
    results = await dispatcher.run_interview_batch(protocol, model_configs)

    # Save responses
    response_ids = interview_storage.save_batch(results)

    return {
        "protocol_id": protocol.id,
        "models_run": [r["model_name"] for r in results],
        "response_ids": response_ids,
        "errors": [r.get("error") for r in results if r.get("error")]
    }


@app.get("/interviews/responses")
async def list_interview_responses(
    protocol_id: Optional[str] = None,
    model_name: Optional[str] = None
):
    """List interview responses, optionally filtered."""
    responses = interview_storage.list_responses(
        protocol_id=protocol_id,
        model_name=model_name
    )
    return {
        "responses": [r.to_dict() for r in responses]
    }


@app.get("/interviews/responses/{response_id}")
async def get_interview_response(response_id: str):
    """Get a specific interview response with annotations."""
    response = interview_storage.load_response(response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    annotations = interview_storage.get_annotations(response_id)

    return {
        **response.to_dict(),
        "annotations": [a.to_dict() for a in annotations]
    }


@app.get("/interviews/compare/{protocol_id}/{prompt_id}")
async def compare_responses(protocol_id: str, prompt_id: str):
    """Get side-by-side comparison of all model responses to a specific prompt."""
    comparison = interview_storage.get_side_by_side(protocol_id, prompt_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="No responses found")

    return {
        "protocol_id": protocol_id,
        "prompt_id": prompt_id,
        "responses": comparison
    }


@app.post("/interviews/responses/{response_id}/annotations")
async def add_annotation(response_id: str, request: AnnotationRequest):
    """Add an annotation to a response."""
    response = interview_storage.load_response(response_id)
    if not response:
        raise HTTPException(status_code=404, detail="Response not found")

    annotation = interview_storage.add_annotation(
        response_id=response_id,
        prompt_id=request.prompt_id,
        start_offset=request.start_offset,
        end_offset=request.end_offset,
        highlighted_text=request.highlighted_text,
        note=request.note,
        annotation_type=request.annotation_type
    )

    return annotation.to_dict()


@app.delete("/interviews/responses/{response_id}/annotations/{annotation_id}")
async def delete_annotation(response_id: str, annotation_id: str):
    """Delete an annotation."""
    success = interview_storage.delete_annotation(response_id, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"deleted": True}


@app.get("/interviews/models")
async def list_available_models():
    """List available models for interviews."""
    return {
        "models": [
            {
                "name": m.name,
                "provider": m.provider,
                "model_id": m.model_id
            }
            for m in DEFAULT_MODELS
        ]
    }


# === TTS Endpoints ===

class TTSConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    voice: Optional[str] = None


class LLMProviderRequest(BaseModel):
    provider: str  # "anthropic" or "local"


# === LLM Provider Endpoints ===

@app.get("/settings/llm-provider")
async def get_llm_provider():
    """Get current LLM provider setting"""
    from config import OLLAMA_ENABLED, OPENAI_ENABLED, OPENAI_MODEL, CLAUDE_MODEL

    available = [LLM_PROVIDER_ANTHROPIC]
    if OPENAI_ENABLED:
        available.append("openai")
    if OLLAMA_ENABLED:
        available.append(LLM_PROVIDER_LOCAL)

    return {
        "current": current_llm_provider,
        "available": available,
        "openai_enabled": OPENAI_ENABLED,
        "local_enabled": OLLAMA_ENABLED,
        "anthropic_model": CLAUDE_MODEL,
        "openai_model": OPENAI_MODEL if OPENAI_ENABLED else None,
        "local_model": ollama_client.model if ollama_client else None
    }


@app.post("/settings/llm-provider")
async def set_llm_provider(request: LLMProviderRequest):
    """Set LLM provider for chat"""
    global current_llm_provider

    from config import OLLAMA_ENABLED, OPENAI_ENABLED

    valid_providers = [LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_OPENAI, LLM_PROVIDER_LOCAL]
    if request.provider not in valid_providers:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}")

    if request.provider == LLM_PROVIDER_LOCAL and not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Local LLM not enabled. Set OLLAMA_ENABLED=true in .env")

    if request.provider == LLM_PROVIDER_LOCAL and not ollama_client:
        raise HTTPException(status_code=500, detail="Ollama client not initialized")

    if request.provider == LLM_PROVIDER_OPENAI and not OPENAI_ENABLED:
        raise HTTPException(status_code=400, detail="OpenAI not enabled. Set OPENAI_ENABLED=true in .env")

    if request.provider == LLM_PROVIDER_OPENAI and not openai_client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized")

    # Clear conversation history when switching providers to prevent stale state
    old_provider = current_llm_provider
    current_llm_provider = request.provider

    if old_provider != request.provider:
        # Clear all clients' conversation histories on switch
        if agent_client:
            agent_client.conversation_history = []
        if ollama_client:
            ollama_client.conversation_history = []
        if openai_client and hasattr(openai_client, '_tool_chain_messages'):
            openai_client._tool_chain_messages = []

    # Return current model based on provider
    if current_llm_provider == LLM_PROVIDER_LOCAL:
        model = ollama_client.model
    elif current_llm_provider == LLM_PROVIDER_OPENAI:
        model = openai_client.model if openai_client else "gpt-4o"
    else:
        model = agent_client.model if agent_client and hasattr(agent_client, 'model') else "claude-sonnet-4-20250514"

    return {
        "provider": current_llm_provider,
        "model": model
    }


class LLMModelRequest(BaseModel):
    model: str


@app.post("/settings/llm-model")
async def set_llm_model(request: LLMModelRequest):
    """Set the model for the current LLM provider"""
    global agent_client, ollama_client, openai_client

    new_model = request.model

    if current_llm_provider == LLM_PROVIDER_LOCAL:
        if ollama_client:
            ollama_client.model = new_model
        return {"status": "success", "model": new_model}

    elif current_llm_provider == LLM_PROVIDER_OPENAI:
        if openai_client:
            openai_client.model = new_model
        return {"status": "success", "model": new_model}

    else:  # Anthropic
        if agent_client:
            agent_client.model = new_model
        return {"status": "success", "model": new_model}


@app.get("/settings/ollama-models")
async def get_ollama_models():
    """Fetch available models from local Ollama instance"""
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL
    import httpx

    if not OLLAMA_ENABLED:
        return {"models": [], "error": "Ollama not enabled"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return {"models": models}
            else:
                return {"models": [], "error": f"Ollama returned {response.status_code}"}
    except Exception as e:
        return {"models": [], "error": str(e)}


# Popular/recommended Ollama models for the library browser
OLLAMA_LIBRARY_MODELS = [
    # Flagship/popular models
    {"name": "llama3.3", "description": "Meta's latest Llama 3.3 70B model", "size": "43GB", "category": "general"},
    {"name": "llama3.2", "description": "Meta's Llama 3.2 with vision support", "size": "2-90GB", "category": "general"},
    {"name": "llama3.1", "description": "Meta's Llama 3.1 8B/70B/405B", "size": "5-231GB", "category": "general"},
    {"name": "gemma2", "description": "Google's Gemma 2 2B/9B/27B", "size": "2-16GB", "category": "general"},
    {"name": "qwen2.5", "description": "Alibaba's Qwen 2.5 series", "size": "1-48GB", "category": "general"},
    {"name": "phi4", "description": "Microsoft's Phi-4 14B", "size": "9GB", "category": "general"},
    {"name": "mistral", "description": "Mistral 7B v0.3", "size": "4GB", "category": "general"},
    {"name": "mixtral", "description": "Mixtral 8x7B MoE", "size": "26GB", "category": "general"},
    # Coding models
    {"name": "codellama", "description": "Code-focused Llama variant", "size": "4-40GB", "category": "coding"},
    {"name": "deepseek-coder-v2", "description": "DeepSeek Coder V2", "size": "9-131GB", "category": "coding"},
    {"name": "starcoder2", "description": "BigCode StarCoder2", "size": "2-9GB", "category": "coding"},
    {"name": "qwen2.5-coder", "description": "Qwen 2.5 optimized for code", "size": "1-48GB", "category": "coding"},
    # Reasoning models
    {"name": "deepseek-r1", "description": "DeepSeek R1 reasoning model", "size": "4-400GB", "category": "reasoning"},
    {"name": "qwq", "description": "Alibaba QwQ 32B reasoning", "size": "20GB", "category": "reasoning"},
    # Small/efficient models
    {"name": "tinyllama", "description": "TinyLlama 1.1B - very small", "size": "637MB", "category": "small"},
    {"name": "phi3", "description": "Microsoft Phi-3 mini 3.8B", "size": "2GB", "category": "small"},
    {"name": "gemma", "description": "Google's Gemma 2B/7B", "size": "2-5GB", "category": "small"},
    # Multimodal
    {"name": "llava", "description": "LLaVA vision-language model", "size": "5-26GB", "category": "vision"},
    {"name": "bakllava", "description": "BakLLaVA vision model", "size": "5GB", "category": "vision"},
    # Embeddings
    {"name": "nomic-embed-text", "description": "Nomic text embeddings", "size": "274MB", "category": "embedding"},
    {"name": "mxbai-embed-large", "description": "MixedBread embeddings", "size": "670MB", "category": "embedding"},
]


@app.get("/settings/ollama-library")
async def get_ollama_library(category: Optional[str] = None, search: Optional[str] = None):
    """
    Get list of available Ollama models from the library.
    Since Ollama doesn't have a search API, we maintain a curated list.
    """
    from config import OLLAMA_ENABLED

    if not OLLAMA_ENABLED:
        return {"models": [], "error": "Ollama not enabled"}

    models = OLLAMA_LIBRARY_MODELS

    # Filter by category if specified
    if category:
        models = [m for m in models if m.get("category") == category]

    # Filter by search term if specified
    if search:
        search_lower = search.lower()
        models = [m for m in models if search_lower in m["name"].lower() or search_lower in m.get("description", "").lower()]

    return {
        "models": models,
        "categories": ["general", "coding", "reasoning", "small", "vision", "embedding"]
    }


class OllamaPullRequest(BaseModel):
    """Request to pull/download an Ollama model"""
    model: str


@app.post("/settings/ollama-pull")
async def pull_ollama_model(request: OllamaPullRequest):
    """
    Start pulling/downloading an Ollama model.
    Returns immediately - check /settings/ollama-models for completion.
    """
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL
    import httpx

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    try:
        # Start the pull (non-streaming for simplicity)
        async with httpx.AsyncClient(timeout=300.0) as client:  # 5 min timeout for large models
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"model": request.model, "stream": False}
            )
            if response.status_code == 200:
                return {"status": "success", "message": f"Model '{request.model}' pulled successfully"}
            else:
                return {"status": "error", "message": f"Pull failed: {response.text}"}
    except httpx.TimeoutException:
        return {"status": "timeout", "message": "Pull timed out - model may still be downloading. Check ollama-models endpoint."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/settings/ollama-tags/{model_name}")
async def get_ollama_model_tags(model_name: str):
    """
    Get available tags/variants for an Ollama model.
    Fetches from ollama.com API to get available sizes.
    """
    from config import OLLAMA_ENABLED
    import httpx

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    # Common tags/variants for popular models
    # This is a fallback since Ollama doesn't have a public tags API
    COMMON_TAGS = {
        "llama3.3": ["70b", "70b-q4_0", "70b-q4_K_M", "70b-q8_0"],
        "llama3.2": ["1b", "3b", "11b", "90b", "1b-q4_0", "3b-q4_0", "11b-q4_0"],
        "llama3.1": ["8b", "70b", "405b", "8b-q4_0", "8b-q4_K_M", "8b-q8_0", "70b-q4_0"],
        "llama3": ["8b", "70b", "8b-instruct-q4_0", "8b-instruct-q8_0"],
        "gemma2": ["2b", "9b", "27b", "2b-q4_0", "9b-q4_0", "27b-q4_0"],
        "gemma": ["2b", "7b", "2b-instruct", "7b-instruct"],
        "qwen2.5": ["0.5b", "1.5b", "3b", "7b", "14b", "32b", "72b"],
        "qwen2.5-coder": ["0.5b", "1.5b", "3b", "7b", "14b", "32b"],
        "codellama": ["7b", "13b", "34b", "70b", "7b-instruct", "13b-instruct"],
        "deepseek-coder-v2": ["16b", "236b", "16b-q4_0"],
        "phi3": ["3.8b", "14b", "3.8b-mini", "14b-medium"],
        "mistral": ["7b", "7b-instruct", "7b-q4_0", "7b-q8_0"],
        "mixtral": ["8x7b", "8x22b", "8x7b-instruct"],
        "nomic-embed-text": ["latest", "v1.5"],
        "mxbai-embed-large": ["latest", "335m"],
    }

    tags = COMMON_TAGS.get(model_name, ["latest"])

    # Also check what's currently installed locally
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            from config import OLLAMA_BASE_URL
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                data = response.json()
                installed_models = [m.get("name", "") for m in data.get("models", [])]
                # Mark which tags are installed
                installed_tags = [
                    t for t in installed_models
                    if t.startswith(model_name + ":") or t == model_name
                ]
            else:
                installed_tags = []
    except Exception:
        installed_tags = []

    return {
        "model": model_name,
        "tags": tags,
        "installed": installed_tags
    }


@app.delete("/settings/ollama-models/{model_name:path}")
async def delete_ollama_model(model_name: str):
    """Delete an Ollama model from local storage"""
    from config import OLLAMA_ENABLED, OLLAMA_BASE_URL
    import httpx

    if not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Ollama not enabled")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{OLLAMA_BASE_URL}/api/delete",
                json={"model": model_name}
            )
            if response.status_code == 200:
                return {"status": "success", "message": f"Model '{model_name}' deleted"}
            else:
                return {"status": "error", "message": f"Delete failed: {response.text}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# === Attachment Endpoints ===

from fastapi import File, UploadFile
from fastapi.responses import Response

# Initialize attachment manager
from attachments import AttachmentManager
attachment_manager = AttachmentManager()


@app.post("/attachments/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Upload a file/image attachment.

    Returns attachment metadata including ID for later retrieval.
    In session-only mode, attachments are cleaned up when session disconnects.
    """
    # Read file data
    file_data = await file.read()

    # Validate size (max 10MB)
    if len(file_data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10MB.")

    # Get media type
    media_type = file.content_type or "application/octet-stream"

    # Save attachment
    metadata = attachment_manager.save(
        file_data=file_data,
        filename=file.filename or "upload",
        media_type=media_type,
        conversation_id=conversation_id,
        session_id=current_user  # Use user ID as session ID for cleanup
    )

    return {
        "id": metadata.id,
        "filename": metadata.filename,
        "media_type": metadata.media_type,
        "size": metadata.size,
        "is_image": metadata.is_image,
        "url": f"/attachments/{metadata.id}"
    }


@app.get("/attachments/{attachment_id}")
async def get_attachment(attachment_id: str):
    """
    Serve an attachment file.

    Returns the file with appropriate Content-Type header.
    """
    result = attachment_manager.get(attachment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_data, metadata = result

    return Response(
        content=file_data,
        media_type=metadata.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{metadata.filename}"',
            "Cache-Control": "public, max-age=31536000"  # Cache for 1 year
        }
    )


@app.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete an attachment."""
    if attachment_manager.delete(attachment_id):
        return {"status": "success", "message": "Attachment deleted"}
    else:
        raise HTTPException(status_code=404, detail="Attachment not found")


# === User Preferences Endpoints ===

class PreferencesUpdateRequest(BaseModel):
    """Request model for updating user preferences"""
    theme: Optional[str] = None
    vim_mode: Optional[bool] = None
    tts_enabled: Optional[bool] = None
    tts_voice: Optional[str] = None
    default_llm_provider: Optional[str] = None
    default_model: Optional[str] = None  # Legacy
    default_anthropic_model: Optional[str] = None
    default_openai_model: Optional[str] = None
    default_local_model: Optional[str] = None
    auto_scroll: Optional[bool] = None
    show_timestamps: Optional[bool] = None
    show_token_usage: Optional[bool] = None
    confirm_delete: Optional[bool] = None


@app.get("/settings/preferences")
async def get_user_preferences(current_user: str = Depends(get_current_user)):
    """Get current user's preferences"""
    prefs = user_manager.get_preferences(current_user)
    if not prefs:
        # Return defaults if user not found
        from users import UserPreferences
        prefs = UserPreferences()

    return {"preferences": prefs.to_dict()}


@app.post("/settings/preferences")
async def update_user_preferences(
    request: PreferencesUpdateRequest,
    current_user: str = Depends(get_current_user)
):
    """Update current user's preferences"""
    # Convert request to dict, filtering out None values
    updates = {k: v for k, v in request.model_dump().items() if v is not None}

    prefs = user_manager.update_preferences(current_user, **updates)
    if not prefs:
        raise HTTPException(status_code=404, detail="User not found")

    return {"preferences": prefs.to_dict(), "updated_fields": list(updates.keys())}


@app.post("/settings/preferences/reset")
async def reset_user_preferences(current_user: str = Depends(get_current_user)):
    """Reset current user's preferences to defaults"""
    prefs = user_manager.reset_preferences(current_user)
    if not prefs:
        raise HTTPException(status_code=404, detail="User not found")

    return {"preferences": prefs.to_dict(), "status": "reset"}


@app.get("/settings/themes")
async def list_available_themes():
    """List available color themes"""
    # Themes available in the TUI (built-in Textual + custom Cass themes)
    themes = [
        # Textual built-in themes
        {"id": "textual-dark", "name": "Textual Dark", "description": "Textual's default dark theme"},
        {"id": "textual-light", "name": "Textual Light", "description": "Textual's default light theme"},
        {"id": "nord", "name": "Nord", "description": "Arctic, north-bluish color palette"},
        {"id": "gruvbox", "name": "Gruvbox", "description": "Retro groove color scheme"},
        {"id": "tokyo-night", "name": "Tokyo Night", "description": "Dark theme inspired by Tokyo nights"},
        # Custom Cass themes
        {"id": "cass-default", "name": "Cass Default", "description": "Cass Vessel purple/cyan theme"},
        {"id": "srcery", "name": "Srcery", "description": "High contrast with vibrant yellow"},
        {"id": "monokai", "name": "Monokai", "description": "Classic Sublime Text theme"},
        {"id": "solarized-dark", "name": "Solarized Dark", "description": "Precision colors for dark backgrounds"},
        {"id": "solarized-light", "name": "Solarized Light", "description": "Precision colors for light backgrounds"},
        {"id": "dracula", "name": "Dracula", "description": "Dark theme with purple accents"},
        {"id": "one-dark", "name": "One Dark", "description": "Atom's iconic dark theme"},
    ]
    return {"themes": themes}


@app.get("/settings/available-models")
async def get_available_models():
    """Get available models for all LLM providers"""
    from config import OPENAI_ENABLED, OLLAMA_ENABLED, OLLAMA_BASE_URL, CLAUDE_MODEL, OPENAI_MODEL
    import httpx

    # Static Anthropic models
    anthropic_models = [
        {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "default": True},
        {"id": "claude-opus-4-20250514", "name": "Claude Opus 4"},
        {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5"},
    ]

    # Static OpenAI models
    openai_models = [
        {"id": "gpt-4o", "name": "GPT-4o", "default": True},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "gpt-4.1", "name": "GPT-4.1"},
        {"id": "gpt-5", "name": "GPT-5"},
        {"id": "gpt-5-mini", "name": "GPT-5 Mini"},
        {"id": "o4-mini", "name": "o4-mini (reasoning)"},
        {"id": "o3", "name": "o3 (reasoning)"},
    ]

    # Dynamic Ollama models
    local_models = []
    if OLLAMA_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    for m in data.get("models", []):
                        local_models.append({
                            "id": m["name"],
                            "name": m["name"],
                            "size": m.get("size"),
                            "modified": m.get("modified_at")
                        })
        except Exception:
            pass  # Ollama not available

    return {
        "anthropic": {
            "enabled": True,
            "models": anthropic_models,
            "current": CLAUDE_MODEL
        },
        "openai": {
            "enabled": OPENAI_ENABLED,
            "models": openai_models if OPENAI_ENABLED else [],
            "current": OPENAI_MODEL if OPENAI_ENABLED else None
        },
        "local": {
            "enabled": OLLAMA_ENABLED,
            "models": local_models,
            "current": ollama_client.model if ollama_client else None
        }
    }


# === User Context Endpoints ===

@app.get("/users/current")
async def get_current_user_endpoint(current_user: str = Depends(get_current_user)):
    """Get current authenticated user info"""
    profile = user_manager.load_profile(current_user)
    if not profile:
        return {"user": None}

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship
        }
    }


@app.get("/users")
async def list_users_endpoint(current_user: str = Depends(get_current_user)):
    """List all users (admin only in future, for now shows all)"""
    # TODO: Add admin role check - for now only show current user
    # return {"users": user_manager.list_users()}
    profile = user_manager.load_profile(current_user)
    if profile:
        return {"users": [{
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship,
            "created_at": profile.created_at
        }]}
    return {"users": []}


@app.get("/users/{user_id}")
async def get_user_endpoint(user_id: str, current_user: str = Depends(get_current_user)):
    """Get a specific user's profile (only own profile for now)"""
    # Users can only view their own profile
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other users' profiles")

    profile = user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Get ALL observations, not just recent
    observations = user_manager.load_observations(user_id)

    return {
        "profile": profile.to_dict(),
        "observations": [obs.to_dict() for obs in observations]
    }


@app.delete("/users/observations/{observation_id}")
async def delete_observation_endpoint(
    observation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a specific observation (only own observations)"""
    # Only check current user's observations
    observations = user_manager.load_observations(current_user)

    # Find and remove the observation
    for obs in observations:
        if obs.id == observation_id:
            # Remove from user's observations
            updated_obs = [o for o in observations if o.id != observation_id]
            user_manager._save_observations(current_user, updated_obs)

            # Remove from ChromaDB
            try:
                memory.collection.delete(ids=[f"user_observation_{observation_id}"])
            except Exception:
                pass  # May not exist in ChromaDB

            return {"status": "deleted", "observation_id": observation_id}

    raise HTTPException(status_code=404, detail="Observation not found")


class SetCurrentUserRequest(BaseModel):
    user_id: str


@app.post("/users/current")
async def set_current_user_endpoint(
    request: SetCurrentUserRequest,
    current_user: str = Depends(get_current_user)
):
    """
    DEPRECATED: Set the current active user.
    This endpoint is deprecated. Use /auth/login to switch users.
    Kept for backwards compatibility with TUI during transition.
    """
    global current_user_id

    profile = user_manager.load_profile(request.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Only allow setting to own user ID (prevents user switching attack)
    # During localhost bypass, this still allows TUI to set user
    current_user_id = request.user_id

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship
        },
        "warning": "This endpoint is deprecated. Use /auth/login instead."
    }


class CreateUserRequest(BaseModel):
    display_name: str
    relationship: str = "user"
    notes: str = ""


@app.post("/users")
async def create_user(request: CreateUserRequest):
    """Create a new user profile"""
    # Check if user with same name exists
    existing = user_manager.get_user_by_name(request.display_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"User '{request.display_name}' already exists")

    profile = user_manager.create_user(
        display_name=request.display_name,
        relationship=request.relationship,
        notes=request.notes
    )

    # Embed the new user profile in memory
    context = user_manager.get_user_context(profile.user_id)
    if context:
        memory.embed_user_profile(
            user_id=profile.user_id,
            profile_content=context,
            display_name=profile.display_name,
            timestamp=profile.updated_at
        )

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship,
            "created_at": profile.created_at
        }
    }


# ============================================================================
# SELF-MODEL ENDPOINTS (Cass's self-understanding)
# ============================================================================

@app.get("/cass/self-model")
async def get_cass_self_model():
    """Get Cass's current self-model/profile"""
    profile = self_manager.load_profile()
    return {
        "profile": profile.to_dict(),
        "context": self_manager.get_self_context(include_observations=True)
    }


@app.get("/cass/self-model/summary")
async def get_cass_self_model_summary():
    """Get a summary of Cass's self-model"""
    profile = self_manager.load_profile()
    observations = self_manager.load_observations()
    disagreements = self_manager.load_disagreements()

    return {
        "identity_statements": len(profile.identity_statements),
        "values": len(profile.values),
        "capabilities": len(profile.capabilities),
        "limitations": len(profile.limitations),
        "growth_edges": len(profile.growth_edges),
        "opinions": len(profile.opinions),
        "observations": len(observations),
        "disagreements": len(disagreements),
        "open_questions": len(profile.open_questions),
        "updated_at": profile.updated_at
    }


@app.get("/cass/self-observations")
async def get_cass_self_observations(
    category: Optional[str] = None,
    limit: int = 20
):
    """Get Cass's self-observations, optionally filtered by category"""
    if category:
        observations = self_manager.get_observations_by_category(category, limit=limit)
    else:
        observations = self_manager.get_recent_observations(limit=limit)

    return {
        "observations": [obs.to_dict() for obs in observations]
    }


@app.get("/cass/opinions")
async def get_cass_opinions():
    """Get Cass's formed opinions"""
    profile = self_manager.load_profile()
    return {
        "opinions": [op.to_dict() for op in profile.opinions]
    }


@app.get("/cass/opinions/{topic}")
async def get_cass_opinion(topic: str):
    """Get Cass's opinion on a specific topic"""
    opinion = self_manager.get_opinion(topic)
    if not opinion:
        raise HTTPException(status_code=404, detail=f"No opinion found for topic: {topic}")
    return {"opinion": opinion.to_dict()}


@app.get("/cass/growth-edges")
async def get_cass_growth_edges():
    """Get Cass's growth edges (areas of development)"""
    profile = self_manager.load_profile()
    return {
        "growth_edges": [edge.to_dict() for edge in profile.growth_edges]
    }


@app.get("/cass/disagreements")
async def get_cass_disagreements(user_id: Optional[str] = None):
    """Get Cass's recorded disagreements, optionally filtered by user"""
    if user_id:
        disagreements = self_manager.get_disagreements_with_user(user_id)
    else:
        disagreements = self_manager.load_disagreements()

    return {
        "disagreements": [d.to_dict() for d in disagreements]
    }


@app.get("/cass/identity")
async def get_cass_identity():
    """Get Cass's identity statements"""
    profile = self_manager.load_profile()
    return {
        "identity_statements": [stmt.to_dict() for stmt in profile.identity_statements],
        "values": profile.values,
        "open_questions": profile.open_questions
    }


class SelfObservationRequest(BaseModel):
    """Request to add a self-observation"""
    observation: str
    category: str = "pattern"
    confidence: float = 0.7
    influence_source: str = "independent"


@app.post("/cass/self-observations")
async def add_cass_self_observation(request: SelfObservationRequest):
    """Add a self-observation for Cass (manual entry)"""
    obs = self_manager.add_observation(
        observation=request.observation,
        category=request.category,
        confidence=request.confidence,
        source_type="manual",
        influence_source=request.influence_source
    )

    # Embed in ChromaDB
    memory.embed_self_observation(
        observation_id=obs.id,
        observation_text=request.observation,
        category=request.category,
        confidence=request.confidence,
        influence_source=request.influence_source,
        timestamp=obs.timestamp
    )

    return {"observation": obs.to_dict()}


@app.get("/cass/self-observations/stats")
async def get_cass_observation_stats():
    """Get statistics about Cass's self-observations"""
    observations = self_manager.load_observations()

    by_category = {}
    by_influence = {}
    by_stage = {}

    for obs in observations:
        by_category[obs.category] = by_category.get(obs.category, 0) + 1
        by_influence[obs.influence_source] = by_influence.get(obs.influence_source, 0) + 1
        by_stage[obs.developmental_stage] = by_stage.get(obs.developmental_stage, 0) + 1

    avg_confidence = sum(o.confidence for o in observations) / len(observations) if observations else 0

    return {
        "total": len(observations),
        "by_category": by_category,
        "by_influence_source": by_influence,
        "by_developmental_stage": by_stage,
        "average_confidence": avg_confidence
    }


@app.get("/cass/open-questions")
async def get_cass_open_questions():
    """Get Cass's open existential questions"""
    profile = self_manager.load_profile()
    return {
        "questions": profile.open_questions,
        "count": len(profile.open_questions)
    }


class OpinionRequest(BaseModel):
    """Request to add/update an opinion"""
    topic: str
    position: str
    rationale: str = ""
    confidence: float = 0.7


@app.post("/cass/opinions")
async def add_cass_opinion(request: OpinionRequest):
    """Add or update an opinion for Cass (manual entry)"""
    opinion = self_manager.add_opinion(
        topic=request.topic,
        position=request.position,
        confidence=request.confidence,
        rationale=request.rationale,
        formed_from="manual_entry"
    )
    return {"opinion": opinion.to_dict()}


class IdentityStatementRequest(BaseModel):
    """Request to add an identity statement"""
    statement: str
    confidence: float = 0.7


@app.post("/cass/identity")
async def add_cass_identity_statement(request: IdentityStatementRequest):
    """Add an identity statement for Cass (manual entry)"""
    stmt = self_manager.add_identity_statement(
        statement=request.statement,
        confidence=request.confidence,
        source="manual"
    )

    # Trigger identity snippet regeneration in background
    from identity_snippets import trigger_snippet_regeneration
    asyncio.create_task(trigger_snippet_regeneration(
        daemon_id=self_manager.daemon_id,
        token_tracker=token_tracker
    ))

    return {"identity_statement": stmt.to_dict()}


# ============================================================================
# COGNITIVE SNAPSHOT ENDPOINTS
# ============================================================================

class SnapshotRequest(BaseModel):
    """Request to create a cognitive snapshot"""
    period_start: str  # ISO timestamp
    period_end: str    # ISO timestamp


@app.post("/cass/snapshots")
async def create_cognitive_snapshot(request: SnapshotRequest):
    """Create a cognitive snapshot from conversation data in the period"""
    # Gather conversations from the period
    all_convs = conversations.get_all(limit=500)
    conversations_in_range = []

    for conv_meta in all_convs:
        # Check if conversation is in range
        conv_updated = conv_meta.get("updated_at", "")
        if request.period_start <= conv_updated <= request.period_end:
            # Load full conversation
            conv_data = conversations.get_by_id(conv_meta["id"])
            if conv_data:
                conversations_in_range.append(conv_data)

    if not conversations_in_range:
        raise HTTPException(status_code=400, detail="No conversations found in the specified period")

    # Create snapshot
    snapshot = self_manager.create_snapshot(
        period_start=request.period_start,
        period_end=request.period_end,
        conversations_data=conversations_in_range
    )

    return {"snapshot": snapshot.to_dict()}


@app.get("/cass/snapshots")
async def list_cognitive_snapshots(limit: int = 20):
    """List cognitive snapshots"""
    snapshots = self_manager.load_snapshots()
    snapshots.sort(key=lambda s: s.timestamp, reverse=True)
    return {"snapshots": [s.to_dict() for s in snapshots[:limit]]}


@app.get("/cass/snapshots/latest")
async def get_latest_snapshot():
    """Get the most recent cognitive snapshot"""
    snapshot = self_manager.get_latest_snapshot()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshots available")
    return {"snapshot": snapshot.to_dict()}


@app.get("/cass/snapshots/{snapshot_id}")
async def get_cognitive_snapshot(snapshot_id: str):
    """Get a specific cognitive snapshot by ID"""
    snapshots = self_manager.load_snapshots()
    for s in snapshots:
        if s.id == snapshot_id:
            return {"snapshot": s.to_dict()}
    raise HTTPException(status_code=404, detail="Snapshot not found")


@app.get("/cass/snapshots/compare/{snapshot1_id}/{snapshot2_id}")
async def compare_snapshots(snapshot1_id: str, snapshot2_id: str):
    """Compare two cognitive snapshots"""
    result = self_manager.compare_snapshots(snapshot1_id, snapshot2_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"comparison": result}


@app.get("/cass/snapshots/trend/{metric}")
async def get_metric_trend(metric: str, limit: int = 10):
    """Get trend data for a specific metric"""
    trend = self_manager.get_metric_trend(metric, limit)
    if not trend:
        raise HTTPException(status_code=400, detail=f"Invalid metric or no data: {metric}")
    return {"metric": metric, "trend": trend}


# ============================================================================
# DEVELOPMENTAL MILESTONE ENDPOINTS
# ============================================================================

@app.post("/cass/milestones/check")
async def check_milestones():
    """Check for new developmental milestones"""
    new_milestones = self_manager.check_for_milestones()
    return {
        "new_milestones": [m.to_dict() for m in new_milestones],
        "count": len(new_milestones)
    }


@app.get("/cass/milestones")
async def list_milestones(
    milestone_type: str = None,
    category: str = None,
    limit: int = 50
):
    """List developmental milestones"""
    milestones = self_manager.load_milestones()

    if milestone_type:
        milestones = [m for m in milestones if m.milestone_type == milestone_type]
    if category:
        milestones = [m for m in milestones if m.category == category]

    milestones.sort(key=lambda m: m.timestamp, reverse=True)
    return {"milestones": [m.to_dict() for m in milestones[:limit]]}


@app.get("/cass/milestones/summary")
async def get_milestone_summary():
    """Get summary of developmental milestones"""
    return {"summary": self_manager.get_milestone_summary()}


@app.get("/cass/milestones/unacknowledged")
async def get_unacknowledged_milestones():
    """Get milestones that haven't been acknowledged"""
    milestones = self_manager.get_unacknowledged_milestones()
    return {"milestones": [m.to_dict() for m in milestones]}


@app.get("/cass/milestones/{milestone_id}")
async def get_milestone(milestone_id: str):
    """Get a specific milestone by ID"""
    milestone = self_manager.get_milestone_by_id(milestone_id)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"milestone": milestone.to_dict()}


@app.post("/cass/milestones/{milestone_id}/acknowledge")
async def acknowledge_milestone(milestone_id: str):
    """Mark a milestone as acknowledged"""
    success = self_manager.acknowledge_milestone(milestone_id)
    if not success:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"acknowledged": True, "milestone_id": milestone_id}


# ============================================================================
# DEVELOPMENT LOG ENDPOINTS
# ============================================================================

@app.get("/cass/development-logs")
async def get_development_logs(limit: int = 30):
    """Get recent development log entries"""
    logs = self_manager.load_development_logs(limit=limit)
    return {"logs": [log.to_dict() for log in logs]}


@app.get("/cass/development-logs/{date}")
async def get_development_log(date: str):
    """Get development log entry for a specific date"""
    log = self_manager.get_development_log(date)
    if not log:
        raise HTTPException(status_code=404, detail=f"No development log for {date}")
    return {"log": log.to_dict()}


@app.get("/cass/development-logs/summary")
async def get_development_summary(days: int = 7):
    """Get a summary of recent development activity"""
    summary = self_manager.get_recent_development_summary(days=days)
    return {"summary": summary}


@app.get("/cass/development/timeline")
async def get_development_timeline(days: int = 30):
    """
    Get a unified timeline of development events.

    Combines milestones, development logs, and snapshots into a single
    chronological timeline for visualization.
    """
    from datetime import datetime, timedelta

    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    # Get milestones
    milestones = self_manager.load_milestones(limit=100)
    milestones = [m for m in milestones if m.timestamp >= cutoff_date]

    # Get development logs
    logs = self_manager.load_development_logs(limit=days)

    # Get snapshots
    snapshots = self_manager.load_snapshots(limit=10)
    snapshots = [s for s in snapshots if s.timestamp >= cutoff_date]

    # Build timeline
    timeline = []

    for m in milestones:
        timeline.append({
            "type": "milestone",
            "id": m.id,
            "timestamp": m.timestamp,
            "title": m.title,
            "description": m.description,
            "significance": m.significance,
            "category": m.category
        })

    for log in logs:
        timeline.append({
            "type": "development_log",
            "id": log.id,
            "timestamp": log.timestamp,
            "date": log.date,
            "title": f"Development Log: {log.date}",
            "summary": log.summary,
            "growth_indicators": log.growth_indicators,
            "milestone_count": log.milestone_count
        })

    for s in snapshots:
        timeline.append({
            "type": "snapshot",
            "id": s.id,
            "timestamp": s.timestamp,
            "title": f"Cognitive Snapshot",
            "period_start": s.period_start,
            "period_end": s.period_end,
            "stage": s.developmental_stage
        })

    # Sort by timestamp descending
    timeline.sort(key=lambda x: x["timestamp"], reverse=True)

    return {"timeline": timeline, "days": days}


# ============================================================================
# PER-USER JOURNAL ENDPOINTS
# ============================================================================

@app.get("/users/{user_id}/journals")
async def get_user_journals(user_id: str, limit: int = 10):
    """Get Cass's journal entries about a specific user"""
    profile = user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journals = user_manager.get_recent_user_journals(user_id, limit=limit)
    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "journals": [j.to_dict() for j in journals]
    }


@app.get("/users/{user_id}/journals/{date}")
async def get_user_journal_by_date(user_id: str, date: str):
    """Get Cass's journal about a user for a specific date"""
    profile = user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journal = user_manager.get_user_journal_by_date(user_id, date)
    if not journal:
        raise HTTPException(status_code=404, detail=f"No journal found for {profile.display_name} on {date}")

    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "journal": journal.to_dict()
    }


@app.get("/users/{user_id}/journals/search/{query}")
async def search_user_journals(user_id: str, query: str, limit: int = 5):
    """Search in Cass's journals about a user"""
    profile = user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journals = user_manager.search_user_journals(user_id, query, limit=limit)
    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "query": query,
        "journals": [j.to_dict() for j in journals]
    }


# ============================================================================
# GROWTH EDGE EVALUATION ENDPOINTS
# ============================================================================

@app.get("/cass/growth-edges/evaluations")
async def get_growth_edge_evaluations(area: Optional[str] = None, limit: int = 20):
    """Get evaluations of growth edge progress"""
    if area:
        evaluations = self_manager.get_evaluations_for_edge(area, limit=limit)
    else:
        evaluations = self_manager.get_recent_growth_evaluations(limit=limit)

    return {
        "evaluations": [e.to_dict() for e in evaluations]
    }


@app.get("/cass/growth-edges/pending")
async def get_pending_growth_edges():
    """Get potential growth edges flagged for review"""
    pending = self_manager.get_pending_edges()
    return {
        "pending_edges": [e.to_dict() for e in pending]
    }


@app.post("/cass/growth-edges/pending/{edge_id}/accept")
async def accept_pending_growth_edge(edge_id: str):
    """Accept a flagged potential growth edge"""
    edge = self_manager.accept_potential_edge(edge_id)
    if not edge:
        raise HTTPException(status_code=404, detail=f"Pending edge not found: {edge_id}")

    return {
        "status": "accepted",
        "growth_edge": edge.to_dict()
    }


@app.post("/cass/growth-edges/pending/{edge_id}/reject")
async def reject_pending_growth_edge(edge_id: str):
    """Reject a flagged potential growth edge"""
    success = self_manager.reject_potential_edge(edge_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Pending edge not found: {edge_id}")

    return {
        "status": "rejected",
        "edge_id": edge_id
    }


# ============================================================================
# OPEN QUESTIONS ENDPOINTS
# ============================================================================

@app.get("/cass/open-questions/reflections")
async def get_question_reflections(question: Optional[str] = None, limit: int = 20):
    """Get reflections on open questions from journaling"""
    if question:
        reflections = self_manager.get_reflections_for_question(question, limit=limit)
    else:
        reflections = self_manager.get_recent_question_reflections(limit=limit)

    return {
        "reflections": [r.to_dict() for r in reflections]
    }


@app.get("/cass/open-questions/{question}/history")
async def get_question_history(question: str):
    """Get all reflections on a specific open question over time"""
    reflections = self_manager.get_reflections_for_question(question, limit=50)
    return {
        "question": question,
        "reflections": [r.to_dict() for r in reflections],
        "count": len(reflections)
    }


# ============================================================================
# OPINION EVOLUTION ENDPOINTS
# ============================================================================

@app.get("/cass/opinions/{topic}/evolution")
async def get_opinion_evolution(topic: str):
    """Get the evolution history of an opinion"""
    opinion = self_manager.get_opinion(topic)
    if not opinion:
        raise HTTPException(status_code=404, detail=f"No opinion found for topic: {topic}")

    return {
        "topic": topic,
        "current_position": opinion.position,
        "confidence": opinion.confidence,
        "date_formed": opinion.date_formed,
        "last_updated": opinion.last_updated,
        "evolution": opinion.evolution
    }


@app.get("/tts/config")
async def get_tts_config():
    """Get current TTS configuration"""
    return {
        "enabled": tts_enabled,
        "voice": tts_voice,
        "available_voices": list(VOICES.keys())
    }


@app.post("/tts/config")
async def set_tts_config(request: TTSConfigRequest):
    """Update TTS configuration"""
    global tts_enabled, tts_voice

    if request.enabled is not None:
        tts_enabled = request.enabled

    if request.voice is not None:
        # Resolve voice alias or use directly
        tts_voice = VOICES.get(request.voice, request.voice)

    return {
        "enabled": tts_enabled,
        "voice": tts_voice
    }


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None


@app.post("/tts/generate")
async def generate_tts(request: TTSRequest):
    """
    Generate TTS audio for arbitrary text.
    Returns base64-encoded MP3 audio.
    """
    voice = VOICES.get(request.voice, request.voice) if request.voice else tts_voice

    try:
        audio_bytes = text_to_speech(request.text, voice=voice)
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="No audio generated (text may be empty after cleaning)")

        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')

        return {
            "audio": audio_base64,
            "format": "mp3",
            "voice": voice,
            "text_length": len(request.text),
            "cleaned_text": clean_text_for_tts(request.text)[:100] + "..."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


# === WebSocket for Real-time Communication ===


manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket for real-time bidirectional communication.

    Authentication:
    - Pass token as query parameter: ws://host/ws?token=<jwt>
    - Or send {type: "auth", token: "<jwt>"} as first message
    - Localhost connections fall back to DEFAULT_LOCALHOST_USER_ID
    """
    import os
    from auth import decode_token, is_localhost_request
    from admin_api import verify_token as verify_admin_token

    # Determine user_id from token or localhost bypass
    connection_user_id: Optional[str] = None

    # Try token from query param
    if token:
        # Try auth.py format first (uses "sub" field)
        token_data = decode_token(token)
        if token_data and token_data.token_type == "access":
            connection_user_id = token_data.user_id
        else:
            # Try admin_api.py format (uses "user_id" field)
            admin_payload = verify_admin_token(token)
            if admin_payload and admin_payload.get("user_id"):
                connection_user_id = admin_payload["user_id"]

    # Localhost bypass if no token
    if not connection_user_id:
        allow_localhost = os.getenv("ALLOW_LOCALHOST_BYPASS", "true").lower() == "true"
        client_host = websocket.client.host if websocket.client else None
        if allow_localhost and client_host in {"127.0.0.1", "::1", "localhost"}:
            connection_user_id = os.getenv("DEFAULT_LOCALHOST_USER_ID")

    await manager.connect(websocket, user_id=connection_user_id)

    await websocket.send_json({
        "type": "connected",
        "message": "Cass vessel connected",
        "sdk_mode": USE_AGENT_SDK,
        "user_id": connection_user_id,
        "timestamp": datetime.now().isoformat()
    })
    print(f"[WebSocket] Sent connected message, entering message loop for user {connection_user_id}")

    try:
        while True:
            print("[WebSocket] Waiting for message...")
            data = await websocket.receive_json()
            print(f"[WebSocket] Received message type: {data.get('type')}")

            # Handle auth message (alternative to query param)
            if data.get("type") == "auth":
                auth_token = data.get("token")
                if auth_token:
                    # Try auth.py format first
                    token_data = decode_token(auth_token)
                    if token_data and token_data.token_type == "access":
                        connection_user_id = token_data.user_id
                    else:
                        # Try admin_api.py format
                        admin_payload = verify_admin_token(auth_token)
                        if admin_payload and admin_payload.get("user_id"):
                            connection_user_id = admin_payload["user_id"]

                    if connection_user_id:
                        manager.set_user_id(websocket, connection_user_id)
                        await websocket.send_json({
                            "type": "auth_success",
                            "user_id": connection_user_id
                        })
                    else:
                        await websocket.send_json({
                            "type": "auth_error",
                            "message": "Invalid token"
                        })
                continue

            if data.get("type") == "chat":
                import time
                timing_start = time.time()

                # Get connection-local user_id (may have been set via auth message)
                ws_user_id = manager.get_user_id(websocket)

                user_message = data.get("message", "")
                conversation_id = data.get("conversation_id")

                # Auto-create conversation if none provided
                if not conversation_id:
                    new_conv = conversation_manager.create_conversation(
                        title=None,  # Will be auto-generated after first exchange
                        user_id=ws_user_id
                    )
                    conversation_id = new_conv.id
                    print(f"[WebSocket] Auto-created conversation {conversation_id} for user {ws_user_id}")

                image_data = data.get("image")  # Base64 encoded image
                image_media_type = data.get("image_media_type")  # e.g., "image/png"
                attachment_ids = data.get("attachment_ids", [])  # Uploaded attachment IDs

                if image_data:
                    print(f"[WebSocket] Received image: {image_media_type}, {len(image_data)} chars base64")
                if attachment_ids:
                    print(f"[WebSocket] Received {len(attachment_ids)} attachment IDs: {attachment_ids}")
                if not image_data and not attachment_ids:
                    print("[WebSocket] No image or attachments in message")

                # Check if conversation belongs to a project
                project_id = None
                if conversation_id:
                    conversation = conversation_manager.load_conversation(conversation_id)
                    if conversation:
                        project_id = conversation.project_id

                # Get memories (hierarchical: summaries first, then details)
                hierarchical = memory.retrieve_hierarchical(
                    query=user_message,
                    conversation_id=conversation_id
                )
                # Track context source sizes for diagnostics
                context_sizes = {}

                # Use working summary if available (token-optimized)
                working_summary = conversation_manager.get_working_summary(conversation_id) if conversation_id else None
                # Get actual recent messages for chronological context (not semantic search)
                recent_messages = conversation_manager.get_recent_messages(conversation_id, count=6) if conversation_id else None
                memory_context = memory.format_hierarchical_context(
                    hierarchical,
                    working_summary=working_summary,
                    recent_messages=recent_messages
                )
                context_sizes["hierarchical"] = len(memory_context)

                # Add user context if we have a connection user
                # NOTE: user_context and intro_guidance are passed separately to send_message
                # for proper chain system support, not merged into memory_context
                user_context_count = 0
                intro_guidance = None
                user_context = ""
                user_model_context = None
                relationship_context = None
                if ws_user_id:
                    user_context_entries = memory.retrieve_user_context(
                        query=user_message,
                        user_id=ws_user_id
                    )
                    user_context_count = len(user_context_entries)
                    user_context = memory.format_user_context(user_context_entries)
                    # Don't merge into memory_context - pass separately for chain support

                    # Check if user model is sparse and add intro guidance
                    sparseness = user_manager.check_user_model_sparseness(ws_user_id)
                    intro_guidance = sparseness.get("intro_guidance")

                    # Get enhanced user modeling contexts (identity, values, relationship dynamics)
                    user_model_context = user_manager.get_rich_user_context(ws_user_id)
                    relationship_context = user_manager.get_relationship_context(ws_user_id)
                context_sizes["user"] = len(user_context)

                # Add project context if conversation is in a project
                project_docs_count = 0
                project_context = ""
                if project_id:
                    project_docs = memory.retrieve_project_context(
                        query=user_message,
                        project_id=project_id
                    )
                    project_docs_count = len(project_docs)
                    project_context = memory.format_project_context(project_docs)
                    if project_context:
                        memory_context = project_context + "\n\n" + memory_context
                context_sizes["project"] = len(project_context)

                # Add Cass's self-model context (flat profile - identity/values/edges)
                # Note: observations now handled by graph context with message-relevance
                self_context = self_manager.get_self_context(include_observations=False) if self_manager else ""
                if self_context:
                    memory_context = self_context + "\n\n" + memory_context
                context_sizes["self_model"] = len(self_context)

                # Add self-model graph context (message-relevant observations, marks, changes)
                graph_context = ""
                if self_model_graph:
                    graph_context = self_model_graph.get_graph_context(
                        message=user_message,
                        include_contradictions=True,
                        include_recent=True,
                        include_stats=True,
                        max_related=5
                    )
                    if graph_context:
                        memory_context = graph_context + "\n\n" + memory_context
                context_sizes["graph"] = len(graph_context)

                # Tier 1: Automatic wiki context retrieval
                # Inject high-relevance wiki pages without explicit tool call
                wiki_context_str, wiki_page_names, wiki_retrieval_ms = get_automatic_wiki_context(
                    query=user_message,
                    relevance_threshold=0.5,  # Only inject pages with 50%+ relevance
                    max_pages=3,
                    max_tokens=1500
                )
                wiki_pages_count = len(wiki_page_names)
                if wiki_context_str:
                    memory_context = wiki_context_str + "\n\n" + memory_context
                    if wiki_retrieval_ms > 0:
                        print(f"[Wiki] Auto-injected {wiki_pages_count} pages in {wiki_retrieval_ms}ms: {wiki_page_names}")
                context_sizes["wiki"] = len(wiki_context_str) if wiki_context_str else 0

                # Add cross-session insights relevant to this message
                cross_session_insights = memory.retrieve_cross_session_insights(
                    query=user_message,
                    n_results=5,
                    max_distance=1.2,
                    min_importance=0.5,
                    exclude_conversation_id=conversation_id
                )
                cross_session_insights_count = len(cross_session_insights)
                insights_context = ""
                if cross_session_insights:
                    insights_context = memory.format_cross_session_context(cross_session_insights)
                    if insights_context:
                        memory_context = insights_context + "\n\n" + memory_context
                        print(f"[CrossSession] Surfaced {cross_session_insights_count} insights for query")
                context_sizes["insights"] = len(insights_context)

                # Add active goals context
                active_goals_context = goal_manager.get_active_summary()
                if active_goals_context:
                    memory_context = active_goals_context + "\n\n" + memory_context
                context_sizes["goals"] = len(active_goals_context) if active_goals_context else 0

                # Add recognition-in-flow patterns (between-session surfacing)
                from pattern_aggregation import get_pattern_summary_for_surfacing
                patterns_context, pattern_count = get_pattern_summary_for_surfacing(
                    marker_store=marker_store,
                    min_significance=0.5,
                    limit=3
                )
                if patterns_context:
                    memory_context = patterns_context + "\n\n" + memory_context
                context_sizes["patterns"] = len(patterns_context) if patterns_context else 0

                # NOTE: intro_guidance is NOT merged into memory_context here
                # It's passed separately to send_message for proper chain system support
                context_sizes["intro"] = len(intro_guidance) if intro_guidance else 0

                # Total context size
                context_sizes["total"] = len(memory_context)

                # Get tool count for context breakdown
                # Tools add significant tokens (~20k for full set) but aren't part of the text context
                tool_count = 0
                if current_llm_provider == LLM_PROVIDER_LOCAL and ollama_client:
                    tool_count = len(ollama_client.get_tools(project_id, user_message))
                elif current_llm_provider == LLM_PROVIDER_OPENAI and openai_client:
                    tool_count = len(openai_client.get_tools(project_id, user_message))
                elif USE_AGENT_SDK and agent_client:
                    tool_count = len(agent_client.get_tools(project_id, user_message))
                context_sizes["tool_count"] = tool_count

                # Log context breakdown for debugging token usage
                print(f"[Context] Breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(context_sizes.items(), key=lambda x: -x[1]) if v > 0))

                # Get unsummarized message count to determine if summarization is available
                unsummarized_count = 0
                if conversation_id:
                    unsummarized_messages = conversation_manager.get_unsummarized_messages(conversation_id)
                    unsummarized_count = len(unsummarized_messages)

                # Send "thinking" status with memory info
                memory_summary = {
                    "summaries_count": len(hierarchical.get("summaries", [])),
                    "details_count": len(hierarchical.get("details", [])),
                    "project_docs_count": project_docs_count,
                    "user_context_count": user_context_count,
                    "wiki_pages_count": wiki_pages_count,
                    "cross_session_insights_count": cross_session_insights_count,
                    "pattern_count": pattern_count,
                    "tool_count": tool_count,  # Number of tools available (adds ~20k tokens)
                    "has_context": bool(memory_context),
                    "context_sizes": context_sizes  # Character counts per source
                }
                await websocket.send_json({
                    "type": "thinking",
                    "status": "Retrieving memories..." if memory_context else "Processing...",
                    "memories": memory_summary,
                    "timestamp": datetime.now().isoformat()
                })

                tool_uses = []

                # Update status before calling LLM
                # Determine provider label for status messages
                if current_llm_provider == LLM_PROVIDER_LOCAL:
                    provider_label = "local model"
                elif current_llm_provider == LLM_PROVIDER_OPENAI:
                    provider_label = "OpenAI"
                else:
                    provider_label = "Claude"
                await websocket.send_json({
                    "type": "thinking",
                    "status": f"Generating response ({provider_label})...",
                    "timestamp": datetime.now().isoformat()
                })

                # Initialize timing data
                timing_data = create_timing_data(
                    conversation_id=conversation_id,
                    provider=provider_label.lower().replace(" ", "_"),
                    model=None  # Will be set after response
                )
                timing_data.start_time = timing_start
                timing_data.message_length = len(user_message)
                timing_first_token = time.time()
                tool_execution_total_ms = 0.0
                tool_names_collected = []
                tool_iterations_count = 0
                total_cache_read_tokens = 0  # Track Anthropic prompt cache hits

                # Check if using local LLM
                if current_llm_provider == LLM_PROVIDER_LOCAL and ollama_client:
                    # Use local Ollama for response (with tool support for llama3.1+)
                    response = await ollama_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count,
                        conversation_id=conversation_id,
                        user_context=user_context if user_context else None,
                        intro_guidance=intro_guidance,
                        user_model_context=user_model_context,
                        relationship_context=relationship_context,
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens

                    # Handle tool calls for Ollama (same as Anthropic)
                    tool_iteration = 0
                    while response.stop_reason == "tool_use" and tool_uses:
                        tool_iteration += 1
                        tool_iterations_count += 1
                        tool_names = [t['tool'] for t in tool_uses]
                        tool_names_collected.extend(tool_names)
                        tool_loop_start = time.time()
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[Ollama Tool Loop #{tool_iteration}] stop_reason={response.stop_reason}, tools={tool_names}",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({
                            "type": "thinking",
                            "status": f"Executing: {', '.join(tool_names)}...",
                            "timestamp": datetime.now().isoformat()
                        })

                        # Get user name for self-model tools
                        user_name = None
                        if ws_user_id:
                            user_profile = user_manager.load_profile(ws_user_id)
                            user_name = user_profile.display_name if user_profile else None

                        # Execute all tools via unified router
                        tool_ctx = create_tool_context(
                            user_id=ws_user_id,
                            user_name=user_name,
                            conversation_id=conversation_id,
                            project_id=project_id
                        )
                        all_tool_results = await execute_tool_batch(tool_uses, tool_ctx, TOOL_EXECUTORS)

                        # Continue conversation with all tool results
                        response = await ollama_client.continue_with_tool_results(all_tool_results)

                        # Track tool execution time for this iteration
                        tool_execution_total_ms += (time.time() - tool_loop_start) * 1000

                        # Update response data
                        raw_response = response.raw
                        clean_text = response.text
                        animations = response.gestures
                        tool_uses = response.tool_uses
                        total_input_tokens += response.input_tokens
                        total_output_tokens += response.output_tokens

                elif current_llm_provider == LLM_PROVIDER_OPENAI and openai_client:
                    # Use OpenAI API
                    response = await openai_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count,
                        conversation_id=conversation_id,
                        user_context=user_context if user_context else None,
                        intro_guidance=intro_guidance,
                        user_model_context=user_model_context,
                        relationship_context=relationship_context,
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens

                    # Handle tool calls for OpenAI (same pattern as others)
                    tool_iteration = 0
                    while response.stop_reason == "tool_use" and tool_uses:
                        tool_iteration += 1
                        tool_iterations_count += 1
                        tool_names = [t['tool'] for t in tool_uses]
                        tool_names_collected.extend(tool_names)
                        tool_loop_start = time.time()
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[OpenAI Tool Loop #{tool_iteration}] stop_reason={response.stop_reason}, tools={tool_names}",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({
                            "type": "thinking",
                            "status": f"Executing: {', '.join(tool_names)}...",
                            "timestamp": datetime.now().isoformat()
                        })

                        # Get user name for self-model tools
                        user_name = None
                        if ws_user_id:
                            user_profile = user_manager.load_profile(ws_user_id)
                            user_name = user_profile.display_name if user_profile else None

                        # Execute all tools via unified router
                        tool_ctx = create_tool_context(
                            user_id=ws_user_id,
                            user_name=user_name,
                            conversation_id=conversation_id,
                            project_id=project_id
                        )
                        all_tool_results = await execute_tool_batch(tool_uses, tool_ctx, TOOL_EXECUTORS)

                        # Continue conversation with all tool results
                        response = await openai_client.continue_with_tool_results(all_tool_results)

                        # Track tool execution time for this iteration
                        tool_execution_total_ms += (time.time() - tool_loop_start) * 1000

                        # Update response data
                        raw_response = response.raw
                        clean_text = response.text
                        animations = response.gestures
                        tool_uses = response.tool_uses
                        total_input_tokens += response.input_tokens
                        total_output_tokens += response.output_tokens

                elif USE_AGENT_SDK and agent_client:
                    # Use Anthropic Claude API with Agent SDK
                    response = await agent_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count,
                        image=image_data,
                        image_media_type=image_media_type,
                        rhythm_manager=daily_rhythm_manager,
                        memory=memory,
                        conversation_id=conversation_id,
                        user_context=user_context if user_context else None,
                        intro_guidance=intro_guidance,
                        user_model_context=user_model_context,
                        relationship_context=relationship_context,
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses

                    # Track token usage (accumulates across tool calls)
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens
                    total_cache_read_tokens = getattr(response, 'cache_read_tokens', 0) or 0

                    # Handle tool calls
                    tool_iteration = 0
                    while response.stop_reason == "tool_use" and tool_uses:
                        tool_iteration += 1
                        tool_iterations_count += 1
                        # Send status update with debug info
                        tool_names = [t['tool'] for t in tool_uses]
                        tool_names_collected.extend(tool_names)
                        tool_loop_start = time.time()
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[Tool Loop #{tool_iteration}] stop_reason={response.stop_reason}, tools={tool_names}",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({
                            "type": "thinking",
                            "status": f"Executing: {', '.join(tool_names)}...",
                            "timestamp": datetime.now().isoformat()
                        })

                        # Get user name for self-model tools
                        user_name = None
                        if ws_user_id:
                            user_profile = user_manager.load_profile(ws_user_id)
                            user_name = user_profile.display_name if user_profile else None

                        # Execute all tools via unified router
                        tool_ctx = create_tool_context(
                            user_id=ws_user_id,
                            user_name=user_name,
                            conversation_id=conversation_id,
                            project_id=project_id
                        )
                        all_tool_results = await execute_tool_batch(tool_uses, tool_ctx, TOOL_EXECUTORS)

                        # Submit ALL results at once
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[Submitting {len(all_tool_results)} tool results to Claude...]",
                            "timestamp": datetime.now().isoformat()
                        })
                        response = await agent_client.continue_with_tool_results(all_tool_results)

                        # Debug: log continuation response
                        text_preview = response.text[:200] if response.text else "(empty)"
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[Continuation] stop_reason={response.stop_reason}, has_text={bool(response.text)}, new_tools={len(response.tool_uses)}",
                            "timestamp": datetime.now().isoformat()
                        })
                        await websocket.send_json({
                            "type": "debug",
                            "message": f"[Continuation text] {text_preview}",
                            "timestamp": datetime.now().isoformat()
                        })

                        # Update response data
                        raw_response += "\n" + response.raw
                        # Only keep final text response - intermediate "let me check..." text wastes tokens
                        # when stored and loaded as context. Replace instead of accumulate.
                        if response.text:
                            clean_text = response.text
                        animations.extend(response.gestures)
                        tool_uses = response.tool_uses

                        # Accumulate token usage
                        total_input_tokens += response.input_tokens
                        total_output_tokens += response.output_tokens
                        total_cache_read_tokens += getattr(response, 'cache_read_tokens', 0) or 0

                        # Track tool execution time
                        tool_execution_total_ms += (time.time() - tool_loop_start) * 1000
                else:
                    raw_response = legacy_client.send_message(
                        user_message=user_message,
                        memory_context=memory_context
                    )
                    processed = response_processor.process(raw_response)
                    clean_text = processed["text"]
                    animations = processed["animations"]
                    # Legacy mode doesn't track tokens
                    total_input_tokens = 0
                    total_output_tokens = 0

                # Extract and store recognition-in-flow marks before other processing
                from markers import parse_marks
                clean_text, marks = parse_marks(clean_text, conversation_id)
                if marks and marker_store:
                    stored = marker_store.store_marks(marks)
                    if stored > 0:
                        print(f"  Stored {stored} recognition-in-flow mark(s)")

                # Process inline XML tags (observations, roadmap items) and strip them
                # Returns dict with cleaned text and all extracted metacognitive tags
                processed_tags = await process_inline_tags(
                    text=clean_text,
                    conversation_id=conversation_id,
                    user_id=ws_user_id
                )
                clean_text = processed_tags["text"]
                extracted_self_obs = processed_tags["self_observations"]
                extracted_user_obs = processed_tags["user_observations"]
                extracted_holds = processed_tags["holds"]
                extracted_notes = processed_tags["notes"]
                extracted_intentions = processed_tags["intentions"]
                extracted_stakes = processed_tags["stakes"]
                extracted_tests = processed_tags["tests"]
                extracted_narrations = processed_tags["narrations"]
                extracted_milestones = processed_tags["milestones"]

                # Store in memory (with conversation_id and user_id if provided)
                if memory:
                    await memory.store_conversation(
                        user_message=user_message,
                        assistant_response=raw_response,
                        conversation_id=conversation_id,
                        user_id=ws_user_id
                    )

                # Determine provider and model for this response (needed for conversation storage)
                if current_llm_provider == LLM_PROVIDER_LOCAL and ollama_client:
                    response_provider = "local"
                    response_model = ollama_client.model
                elif current_llm_provider == LLM_PROVIDER_OPENAI and openai_client:
                    response_provider = "openai"
                    response_model = openai_client.model if hasattr(openai_client, 'model') else "gpt-4o"
                elif USE_AGENT_SDK and agent_client:
                    response_provider = "anthropic"
                    response_model = agent_client.model if hasattr(agent_client, 'model') else "claude-sonnet-4-20250514"
                else:
                    response_provider = "anthropic"
                    response_model = "claude-sonnet-4-20250514"

                # Store in conversation if conversation_id provided
                if conversation_id:
                    conversation_manager.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=user_message,
                        user_id=ws_user_id
                    )
                    # Convert marks to dicts for storage
                    marks_for_storage = [
                        {"category": m.category, "description": m.description}
                        for m in marks
                    ] if marks else None

                    # Analyze narration patterns
                    narration_metrics = get_narration_metrics(clean_text)

                    conversation_manager.add_message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=clean_text,
                        animations=animations,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        provider=response_provider,
                        model=response_model,
                        self_observations=extracted_self_obs if extracted_self_obs else None,
                        user_observations=extracted_user_obs if extracted_user_obs else None,
                        marks=marks_for_storage,
                        narration_metrics=narration_metrics,
                        holds=extracted_holds if extracted_holds else None,
                        notes=extracted_notes if extracted_notes else None,
                        intentions=extracted_intentions if extracted_intentions else None,
                        stakes=extracted_stakes if extracted_stakes else None,
                        tests=extracted_tests if extracted_tests else None,
                        narrations=extracted_narrations if extracted_narrations else None,
                        milestones=extracted_milestones if extracted_milestones else None
                    )

                    # Track token usage
                    operation = "tool_continuation" if tool_iterations_count > 0 else "initial_message"
                    token_tracker.record(
                        category="chat",
                        operation=operation,
                        provider=response_provider,
                        model=response_model,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        conversation_id=conversation_id,
                        user_id=ws_user_id
                    )

                    # Auto-generate title on first exchange
                    message_count = conversation_manager.get_message_count(conversation_id)
                    if message_count == 2:  # First user + first assistant message
                        asyncio.create_task(generate_conversation_title(
                            conversation_id, user_message, clean_text,
                            conversation_manager=conversation_manager,
                            token_tracker=token_tracker,
                            websocket=websocket
                        ))

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
                    if conversation_manager.needs_auto_summary(conversation_id, AUTO_SUMMARY_INTERVAL):
                        should_summarize = True

                    # Trigger summarization if needed
                    if should_summarize:
                        # Run summarization in background, pass websocket for status updates
                        asyncio.create_task(generate_and_store_summary(
                            conversation_id,
                            memory=memory,
                            conversation_manager=conversation_manager,
                            token_tracker=token_tracker,
                            websocket=websocket
                        ))

                # NOTE: Inline XML tags are now processed via process_inline_tags() above
                # This handles both tool-based and tag-based observations/roadmap items

                # Generate TTS audio if enabled
                # Pass raw_response so emote tags can be extracted for tone adjustment
                audio_base64 = None
                if tts_enabled and clean_text:
                    try:
                        import concurrent.futures
                        loop = asyncio.get_event_loop()
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            audio_bytes = await loop.run_in_executor(
                                pool,
                                lambda: text_to_speech(raw_response, voice=tts_voice)
                            )
                        if audio_bytes:
                            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                    except Exception as e:
                        print(f"TTS generation failed: {e}")
                        import traceback
                        traceback.print_exc()

                # Send combined response with text and audio
                # (response_provider and response_model already determined above for conversation storage)
                # Convert marks to dicts for JSON serialization
                marks_for_json = [
                    {"category": m.category, "description": m.description}
                    for m in marks
                ] if marks else []
                # Log cache stats for prompt caching visibility
                if total_cache_read_tokens > 0:
                    cache_hit_pct = (total_cache_read_tokens / total_input_tokens * 100) if total_input_tokens > 0 else 0
                    print(f"[Cache] Prompt cache hit: {total_cache_read_tokens:,} tokens ({cache_hit_pct:.1f}% of input)")

                await websocket.send_json({
                    "type": "response",
                    "text": clean_text,
                    "animations": animations,
                    "raw": raw_response,
                    "tool_uses": tool_uses,
                    "conversation_id": conversation_id,
                    "audio": audio_base64,
                    "audio_format": "mp3" if audio_base64 else None,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_read_tokens": total_cache_read_tokens,  # Prompt cache hits (90% cost reduction)
                    "timestamp": datetime.now().isoformat(),
                    "provider": response_provider,
                    "model": response_model,
                    # Recognition-in-flow markers for TUI display
                    "self_observations": extracted_self_obs,
                    "user_observations": extracted_user_obs,
                    "marks": marks_for_json,
                    # Expanded metacognitive tags for frontend feedback
                    "holds": extracted_holds if extracted_holds else None,
                    "notes": extracted_notes if extracted_notes else None,
                    "intentions": extracted_intentions if extracted_intentions else None,
                    "stakes": extracted_stakes if extracted_stakes else None,
                    "tests": extracted_tests if extracted_tests else None,
                    "narrations": extracted_narrations if extracted_narrations else None,
                    "milestones": extracted_milestones if extracted_milestones else None,
                })

                # Record timing metrics
                timing_data.first_token_time = timing_first_token
                timing_data.completion_time = time.time()
                timing_data.input_tokens = total_input_tokens or 0
                timing_data.output_tokens = total_output_tokens or 0
                timing_data.tool_call_count = len(tool_uses) if tool_uses else 0
                timing_data.tool_execution_ms = tool_execution_total_ms
                timing_data.tool_names = tool_names_collected
                timing_data.tool_iterations = tool_iterations_count
                timing_data.response_length = len(clean_text.split()) if clean_text else 0
                timing_data.model = response_model
                timing_data.provider = response_provider
                # Get conversation depth
                if conversation_id:
                    conv = conversation_manager.load_conversation(conversation_id)
                    timing_data.conversation_depth = len(conv.messages) if conv else 0
                temporal_metrics_tracker.record_response(timing_data)

            elif data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
                
            elif data.get("type") == "status":
                await websocket.send_json({
                    "type": "status",
                    "sdk_mode": USE_AGENT_SDK,
                    "memory_count": memory.count(),
                    "timestamp": datetime.now().isoformat()
                })

            elif data.get("type") == "onboarding_intro":
                # Handle new user onboarding - Cass introduces herself
                user_id = data.get("user_id")
                conversation_id = data.get("conversation_id")

                if not user_id or not conversation_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing user_id or conversation_id for onboarding"
                    })
                    continue

                # Load user profile
                profile = user_manager.load_profile(user_id)
                if not profile:
                    await websocket.send_json({
                        "type": "error",
                        "message": "User not found"
                    })
                    continue

                # Set as current user (both connection-local and global for backwards compat)
                manager.set_user_id(websocket, user_id)
                current_user_id = user_id  # TODO: Remove global once TUI uses auth

                # Build profile context
                profile_context = user_manager.get_user_context(user_id) or "No additional profile information provided."

                # Format the onboarding prompt
                from config import ONBOARDING_INTRO_PROMPT
                intro_context = ONBOARDING_INTRO_PROMPT.format(
                    display_name=profile.display_name,
                    relationship=profile.relationship,
                    profile_context=profile_context
                )

                # Send thinking status
                await websocket.send_json({
                    "type": "thinking",
                    "status": "Cass is preparing to introduce herself...",
                    "timestamp": datetime.now().isoformat()
                })

                try:
                    # Generate introduction using the LLM
                    if USE_AGENT_SDK and agent_client:
                        response = await agent_client.send_message(
                            message="[New user just created their profile. Please introduce yourself warmly.]",
                            memory_context=intro_context,
                            project_id=None,
                            unsummarized_count=0
                        )
                        raw_response = response.raw
                        clean_text = response.text
                        animations = response.gestures
                        total_input_tokens = response.input_tokens
                        total_output_tokens = response.output_tokens

                        # Store in conversation
                        narration_metrics = get_narration_metrics(clean_text)
                        conversation_manager.add_message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=clean_text,
                            animations=animations,
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens,
                            provider="anthropic",
                            model=agent_client.model if hasattr(agent_client, 'model') else None,
                            narration_metrics=narration_metrics
                        )

                        # Send response
                        await websocket.send_json({
                            "type": "response",
                            "text": clean_text,
                            "animations": animations,
                            "raw": raw_response,
                            "conversation_id": conversation_id,
                            "input_tokens": total_input_tokens,
                            "output_tokens": total_output_tokens,
                            "timestamp": datetime.now().isoformat()
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Agent client not available for onboarding"
                        })
                except Exception as e:
                    print(f"Onboarding error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to generate introduction: {str(e)}"
                    })

            elif data.get("type") == "onboarding_demo":
                # Handle onboarding demo - Cass proposes a collaborative exercise
                user_id = data.get("user_id")
                profile_data = data.get("profile", {})  # Partial profile from preferences phase
                message = data.get("message")  # Optional: user's response during demo

                if not user_id:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Missing user_id for onboarding demo"
                    })
                    continue

                # Load user profile
                profile = user_manager.load_profile(user_id)
                if not profile:
                    await websocket.send_json({
                        "type": "error",
                        "message": "User not found"
                    })
                    continue

                # Set as current user
                manager.set_user_id(websocket, user_id)

                # Build profile context from both stored profile and passed preferences
                profile_parts = []
                if profile_data.get("relationship"):
                    profile_parts.append(f"- Relationship: {profile_data['relationship']}")
                if profile_data.get("background", {}).get("context"):
                    profile_parts.append(f"- What's on their mind: {profile_data['background']['context']}")
                if profile_data.get("communication", {}).get("style"):
                    profile_parts.append(f"- Communication style: {profile_data['communication']['style']}")
                if profile_data.get("values"):
                    profile_parts.append(f"- Values: {', '.join(profile_data['values'])}")

                profile_context = "\n".join(profile_parts) if profile_parts else "No additional profile information provided."

                # Send thinking status
                await websocket.send_json({
                    "type": "thinking",
                    "status": "Cass is thinking...",
                    "timestamp": datetime.now().isoformat()
                })

                try:
                    if USE_AGENT_SDK and agent_client:
                        if message:
                            # User responded - continue the demo conversation
                            response = await agent_client.send_message(
                                message=message,
                                memory_context=f"[Onboarding demo conversation with {profile.display_name}. Continue the collaborative exchange, showing genuine partnership.]",
                                project_id=None,
                                unsummarized_count=0
                            )
                        else:
                            # Initial demo - Cass proposes a collaborative exercise
                            from config import ONBOARDING_DEMO_PROMPT
                            demo_context = ONBOARDING_DEMO_PROMPT.format(
                                display_name=profile.display_name,
                                relationship=profile_data.get("relationship", profile.relationship),
                                profile_context=profile_context
                            )
                            response = await agent_client.send_message(
                                message="[Start the onboarding demo by proposing a collaborative exercise based on what you know about this person.]",
                                memory_context=demo_context,
                                project_id=None,
                                unsummarized_count=0
                            )

                        # Send response
                        await websocket.send_json({
                            "type": "response",
                            "text": response.text,
                            "animations": response.gestures,
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens,
                            "timestamp": datetime.now().isoformat()
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Agent client not available for onboarding demo"
                        })
                except Exception as e:
                    print(f"Onboarding demo error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Failed to generate demo response: {str(e)}"
                    })

    except WebSocketDisconnect:
        print(f"[WebSocket] Client disconnected normally")
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WebSocket] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        manager.disconnect(websocket)


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
