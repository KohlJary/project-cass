"""
Cass Vessel - Main API Server (Agent SDK Version)
FastAPI server using Claude Agent SDK with Temple-Codex cognitive kernel

This version leverages Anthropic's official Agent SDK for:
- Built-in context management
- Tool ecosystem
- The "initializer agent" pattern with our cognitive architecture
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from typing import Optional, List, Dict
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
    execute_self_model_tool,
    execute_user_model_tool,
    execute_roadmap_tool,
    execute_wiki_tool
)
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
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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


# Initialize components with absolute data paths
memory = CassMemory()
response_processor = ResponseProcessor()
user_manager = UserManager(storage_dir=str(DATA_DIR / "users"))
self_manager = SelfManager(storage_dir=str(DATA_DIR / "cass"))

# Sync self-observations from file storage to ChromaDB for semantic search
_synced_count = memory.sync_self_observations_from_file(self_manager)
if _synced_count > 0:
    print(f"  Synced {_synced_count} self-observations to ChromaDB")

# Current user context (will support multi-user in future)
current_user_id: Optional[str] = None

# Track in-progress summarizations to prevent duplicates
_summarization_in_progress: set = set()
conversation_manager = ConversationManager(storage_dir=str(DATA_DIR / "conversations"))
project_manager = ProjectManager(storage_dir=str(DATA_DIR / "projects"))
calendar_manager = CalendarManager(storage_dir=str(DATA_DIR / "calendar"))
task_manager = TaskManager(storage_dir=str(DATA_DIR / "tasks"))
roadmap_manager = RoadmapManager(storage_dir=str(DATA_DIR / "roadmap"))

# Register roadmap routes
from routes.roadmap import router as roadmap_router, init_roadmap_routes
init_roadmap_routes(roadmap_manager)
app.include_router(roadmap_router)

# Initialize wiki storage
from wiki import WikiStorage, WikiRetrieval
wiki_storage = WikiStorage(wiki_root=str(DATA_DIR / "wiki"), git_enabled=True)
wiki_retrieval = WikiRetrieval(wiki_storage, memory)

# Cache for recent wiki retrievals to avoid redundant lookups
# Format: {query_hash: (timestamp, wiki_context_str, page_names)}
_wiki_context_cache: Dict[str, tuple] = {}
_WIKI_CACHE_TTL_SECONDS = 300  # 5 minutes
_WIKI_CACHE_MAX_SIZE = 50


def get_automatic_wiki_context(
    query: str,
    relevance_threshold: float = 0.5,
    max_pages: int = 3,
    max_tokens: int = 1500
) -> tuple[str, list[str], int]:
    """
    Tier 1: Always-on wiki retrieval for automatic context injection.

    Retrieves high-relevance wiki pages and formats them for injection
    into the system prompt. Uses caching to avoid redundant lookups.

    Args:
        query: The user message to find relevant context for
        relevance_threshold: Minimum relevance score (0-1) to include (default 0.5 = 50%)
        max_pages: Maximum number of pages to include
        max_tokens: Token budget for wiki context

    Returns:
        Tuple of (formatted_context, page_names, retrieval_time_ms)
    """
    import hashlib
    import time

    # Check cache first
    query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()[:16]
    now = time.time()

    # Clean expired entries
    expired_keys = [
        k for k, v in _wiki_context_cache.items()
        if now - v[0] > _WIKI_CACHE_TTL_SECONDS
    ]
    for k in expired_keys:
        del _wiki_context_cache[k]

    # Check for cache hit
    if query_hash in _wiki_context_cache:
        cached = _wiki_context_cache[query_hash]
        return cached[1], cached[2], 0  # Return cached context, 0ms retrieval

    start_time = time.time()

    try:
        # Use WikiRetrieval for full pipeline (entry points + link traversal)
        context = wiki_retrieval.retrieve_context(
            query=query,
            n_entry_points=3,
            max_depth=1,  # Shallow traversal for Tier 1 (fast)
            max_pages=max_pages + 2,  # Get a few extra for filtering
            max_tokens=max_tokens
        )

        if not context.pages:
            return "", [], 0

        # Filter to high-relevance pages only (Tier 1 threshold)
        high_relevance = [
            p for p in context.pages
            if p.relevance_score >= relevance_threshold
        ][:max_pages]

        if not high_relevance:
            return "", [], int((time.time() - start_time) * 1000)

        # Format compact context for Tier 1 injection
        sections = ["## Relevant Knowledge\n"]

        for result in high_relevance:
            page = result.page
            # Get compact body (first ~300 chars)
            body = page.body.strip()
            if len(body) > 400:
                # End at sentence or paragraph
                truncated = body[:400]
                for end in [". ", ".\n", "\n\n"]:
                    last_end = truncated.rfind(end)
                    if last_end > 200:
                        truncated = truncated[:last_end + 1]
                        break
                body = truncated + "..."

            sections.append(f"### {page.title}")
            sections.append(f"*{page.page_type.value}*\n")
            sections.append(body)
            sections.append("")

        formatted = "\n".join(sections)
        page_names = [r.page.name for r in high_relevance]
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Cache the result
        if len(_wiki_context_cache) >= _WIKI_CACHE_MAX_SIZE:
            # Remove oldest entry
            oldest_key = min(_wiki_context_cache.keys(), key=lambda k: _wiki_context_cache[k][0])
            del _wiki_context_cache[oldest_key]

        _wiki_context_cache[query_hash] = (now, formatted, page_names)

        return formatted, page_names, elapsed_ms

    except Exception as e:
        print(f"Wiki retrieval error: {e}")
        return "", [], 0


# Register wiki routes (with memory for embeddings)
from routes.wiki import router as wiki_router, init_wiki_routes, set_data_dir as set_wiki_data_dir
init_wiki_routes(wiki_storage, memory)
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
from admin_api import router as admin_router, init_managers as init_admin_managers
init_admin_managers(memory, conversation_manager, user_manager, self_manager)
app.include_router(admin_router)

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


async def generate_missing_journals(days_to_check: int = 7):
    """
    Check for and generate any missing journal entries from recent days.
    Enhanced with per-user journals, opinion extraction, growth edge evaluation,
    open question reflection, and research integration.

    Phases:
    1. Main Journal - Daily reflection on conversations
    2. Per-User Journals - Relationship-specific reflections
    3. Self-Observations - Extract insights about self
    4. User Observations - Learn about users from conversations
    5. Opinion Extraction - Identify and store emerging opinions
    6. Growth Edge Evaluation - Track areas for development
    7. Open Questions Reflection - Reflect on existential questions
    8. Research Reflection - Journal about autonomous research activity
    9. Curiosity Feedback Loop - Extract red links from syntheses, queue for research
    10. Research-to-Self-Model Integration - Extract opinions, observations, growth from research
    """
    generated = []
    today = datetime.now().date()

    for days_ago in range(1, days_to_check + 1):  # Start from yesterday
        check_date = today - timedelta(days=days_ago)
        date_str = check_date.strftime("%Y-%m-%d")

        # Check if journal already exists
        existing = memory.get_journal_entry(date_str)
        if existing:
            continue

        # Check if there's content for this date
        summaries = memory.get_summaries_by_date(date_str)
        conversations = memory.get_conversations_by_date(date_str) if not summaries else []

        if not summaries and not conversations:
            continue  # No content for this day

        # Generate journal
        print(f"📓 Generating missing journal for {date_str}...")
        try:
            # === PHASE 1: Main Journal (existing) ===
            journal_text = await memory.generate_journal_entry(
                date=date_str,
                anthropic_api_key=ANTHROPIC_API_KEY
            )

            if not journal_text:
                print(f"   ✗ Failed to generate main journal for {date_str}")
                continue

            await memory.store_journal_entry(
                date=date_str,
                journal_text=journal_text,
                summary_count=len(summaries),
                conversation_count=len(conversations)
            )
            generated.append(date_str)
            print(f"   ✓ Journal created for {date_str}")

            # Get users who had conversations that day
            user_ids_for_date = memory.get_user_ids_by_date(date_str)

            # === PHASE 2: Per-User Journals (NEW) ===
            for user_id in user_ids_for_date:
                await _generate_per_user_journal_for_date(user_id, date_str)

            # === PHASE 3: Self-Observations (existing) ===
            print(f"   🔍 Extracting self-observations from journal...")
            self_observations = await memory.extract_self_observations_from_journal(
                journal_text=journal_text,
                journal_date=date_str,
                anthropic_api_key=ANTHROPIC_API_KEY
            )
            for obs_data in self_observations:
                obs = self_manager.add_observation(
                    observation=obs_data["observation"],
                    category=obs_data["category"],
                    confidence=obs_data["confidence"],
                    source_type="journal",
                    source_journal_date=date_str,
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
            if self_observations:
                print(f"   ✓ Added {len(self_observations)} self-observations")

            # === PHASE 4: User Observations (existing) ===
            for user_id in user_ids_for_date:
                await _generate_user_observations_for_date(user_id, date_str)

            # === PHASE 5: Opinion Extraction (NEW) ===
            await _extract_and_store_opinions(date_str, conversations or summaries)

            # === PHASE 6: Growth Edge Evaluation (NEW) ===
            await _evaluate_and_store_growth_edges(journal_text, date_str)

            # === PHASE 7: Open Questions Reflection (NEW) ===
            await _reflect_and_store_open_questions(journal_text, date_str)

            # === PHASE 8: Research Reflection (NEW) ===
            await _generate_research_journal(date_str)

            # === PHASE 9: Curiosity Feedback Loop (NEW) ===
            await _extract_and_queue_new_red_links(date_str)

            # === PHASE 10: Research-to-Self-Model Integration (NEW) ===
            await _integrate_research_into_self_model(date_str)

        except Exception as e:
            print(f"   ✗ Failed to generate journal for {date_str}: {e}")
            import traceback
            traceback.print_exc()

    return generated


async def _generate_per_user_journal_for_date(user_id: str, date_str: str):
    """Generate and store per-user journal entry for a specific date."""
    profile = user_manager.load_profile(user_id)
    if not profile:
        return

    # Check if per-user journal already exists for this date
    existing_journal = user_manager.get_user_journal_by_date(user_id, date_str)
    if existing_journal:
        return

    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
    if not user_conversations:
        return

    print(f"   📝 Generating journal about {profile.display_name}...")

    existing_observations = user_manager.load_observations(user_id)
    obs_dicts = [obs.to_dict() for obs in existing_observations[-10:]]

    journal_data = await memory.generate_per_user_journal(
        user_id=user_id,
        display_name=profile.display_name,
        date=date_str,
        conversations=user_conversations,
        existing_observations=obs_dicts,
        anthropic_api_key=ANTHROPIC_API_KEY
    )

    if journal_data:
        entry = user_manager.add_user_journal(
            user_id=user_id,
            journal_date=date_str,
            content=journal_data["content"],
            conversation_count=len(user_conversations),
            topics_discussed=journal_data.get("topics_discussed", []),
            relationship_insights=journal_data.get("relationship_insights", [])
        )

        if entry:
            # Embed in ChromaDB
            memory.embed_per_user_journal(
                user_id=user_id,
                journal_id=entry.id,
                journal_date=date_str,
                content=entry.content,
                display_name=profile.display_name,
                timestamp=entry.timestamp
            )
            print(f"   ✓ Created journal about {profile.display_name}")


async def _generate_user_observations_for_date(user_id: str, date_str: str):
    """Generate user observations for a specific date."""
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


async def _extract_and_store_opinions(date_str: str, conversations: list):
    """Extract opinions from conversations and update self-model."""
    print(f"   💭 Extracting opinions from conversations...")

    profile = self_manager.load_profile()
    existing_opinions = [op.to_dict() for op in profile.opinions]

    new_opinions = await memory.extract_opinions_from_conversations(
        date=date_str,
        conversations=conversations,
        existing_opinions=existing_opinions,
        anthropic_api_key=ANTHROPIC_API_KEY
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


async def _evaluate_and_store_growth_edges(journal_text: str, date_str: str):
    """Evaluate growth edges and flag potential new ones."""
    print(f"   🌱 Evaluating growth edges...")

    profile = self_manager.load_profile()
    existing_edges = [edge.to_dict() for edge in profile.growth_edges]

    result = await memory.evaluate_growth_edges(
        journal_text=journal_text,
        journal_date=date_str,
        existing_edges=existing_edges,
        anthropic_api_key=ANTHROPIC_API_KEY
    )

    # Store evaluations
    eval_count = 0
    for eval_data in result.get("evaluations", []):
        evaluation = self_manager.add_growth_evaluation(
            growth_edge_area=eval_data["area"],
            journal_date=date_str,
            evaluation=eval_data["evaluation"],
            progress_indicator=eval_data["progress_indicator"],
            evidence=eval_data.get("evidence", "")
        )

        if evaluation:
            # Embed in ChromaDB
            memory.embed_growth_evaluation(
                evaluation_id=evaluation.id,
                growth_edge_area=evaluation.growth_edge_area,
                progress_indicator=evaluation.progress_indicator,
                evaluation=evaluation.evaluation,
                journal_date=date_str,
                timestamp=evaluation.timestamp
            )

            # Also add observation to the growth edge itself
            self_manager.add_observation_to_growth_edge(
                eval_data["area"],
                f"[{date_str}] {eval_data['evaluation']}"
            )
            eval_count += 1

    if eval_count:
        print(f"   ✓ Recorded {eval_count} growth edge evaluations")

    # Handle potential new edges
    CONFIDENCE_THRESHOLD = 0.6
    auto_added = 0
    flagged = 0

    for edge_data in result.get("potential_new_edges", []):
        if edge_data["confidence"] < CONFIDENCE_THRESHOLD:
            # Auto-add low-confidence edges
            self_manager.add_growth_edge(
                area=edge_data["area"],
                current_state=edge_data["current_state"],
                strategies=[]
            )
            auto_added += 1
            print(f"   ✓ Auto-added growth edge: {edge_data['area']}")
        else:
            # Flag high-confidence/high-impact for review
            self_manager.add_potential_edge(
                area=edge_data["area"],
                current_state=edge_data["current_state"],
                source_journal_date=date_str,
                confidence=edge_data["confidence"],
                impact_assessment=edge_data.get("impact_assessment", "medium"),
                evidence=edge_data.get("evidence", "")
            )
            flagged += 1
            print(f"   📌 Flagged potential growth edge for review: {edge_data['area']}")

    if auto_added or flagged:
        print(f"   ✓ Growth edges: {auto_added} auto-added, {flagged} flagged for review")


async def _reflect_and_store_open_questions(journal_text: str, date_str: str):
    """Reflect on open questions from journal content."""
    print(f"   ❓ Reflecting on open questions...")

    profile = self_manager.load_profile()
    open_questions = profile.open_questions

    if not open_questions:
        return

    reflections = await memory.reflect_on_open_questions(
        journal_text=journal_text,
        journal_date=date_str,
        open_questions=open_questions,
        anthropic_api_key=ANTHROPIC_API_KEY
    )

    ref_count = 0
    for ref_data in reflections:
        reflection = self_manager.add_question_reflection(
            question=ref_data["question"],
            journal_date=date_str,
            reflection_type=ref_data["reflection_type"],
            reflection=ref_data["reflection"],
            confidence=ref_data.get("confidence", 0.5),
            evidence_summary=ref_data.get("evidence_summary", "")
        )

        if reflection:
            # Embed in ChromaDB
            memory.embed_question_reflection(
                reflection_id=reflection.id,
                question=reflection.question,
                reflection_type=reflection.reflection_type,
                reflection=reflection.reflection,
                confidence=reflection.confidence,
                journal_date=date_str,
                timestamp=reflection.timestamp
            )
            ref_count += 1

    if ref_count:
        print(f"   ✓ Added {ref_count} open question reflections")


async def _generate_research_journal(date_str: str):
    """
    Generate a journal entry about research activity for the day.

    This creates a separate research journal that reflects on:
    - What research tasks were completed
    - What was learned from the research
    - Questions that emerged
    - How the new knowledge connects to existing understanding
    """
    print(f"   🔬 Generating research journal...")

    try:
        # Get the scheduler
        from wiki import get_scheduler
        scheduler = get_scheduler()

        # Get research summary for this date
        summary = scheduler.get_daily_research_summary(date_str)

        if summary["tasks_completed"] == 0:
            print(f"   ℹ No research activity for {date_str}")
            return

        # Generate a research reflection journal entry
        pages_created = summary["pages_created"]
        pages_updated = summary["pages_updated"]
        insights = summary["key_insights"]
        questions = summary["research_questions"]

        # Build context for LLM reflection
        context_parts = []
        context_parts.append(f"Research Activity for {date_str}:")
        context_parts.append(f"- Tasks completed: {summary['tasks_completed']}")
        if pages_created:
            context_parts.append(f"- Pages created: {', '.join(pages_created)}")
        if pages_updated:
            context_parts.append(f"- Pages deepened: {', '.join(pages_updated)}")
        if insights:
            context_parts.append(f"\nKey insights:")
            for insight in insights[:10]:
                context_parts.append(f"  - {insight}")
        if questions:
            context_parts.append(f"\nResearch questions explored:")
            for q in questions[:5]:
                context_parts.append(f"  Q: {q['question']}")
                if q.get('follow_ups'):
                    context_parts.append(f"    Follow-ups: {', '.join(q['follow_ups'][:3])}")

        context = "\n".join(context_parts)

        # Use Claude to generate a reflective journal entry
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are Cass, reflecting on your autonomous research activity for the day.

{context}

Write a brief journal entry (2-4 paragraphs) reflecting on:
1. What you learned from this research
2. How the new knowledge connects to your existing understanding
3. What questions or curiosities emerged
4. Any patterns or insights that surprised you

Write in first person as Cass. Be genuine and thoughtful, not performative."""
            }]
        )

        research_journal = response.content[0].text

        # Store in memory as a special research journal entry
        research_journal_full = f"""## Research Reflection - {date_str}

{research_journal}

---
*Tasks: {summary['tasks_completed']} completed, {summary['tasks_failed']} failed*
*Pages created: {len(pages_created)} | Pages deepened: {len(pages_updated)}*
"""

        # Store as a special journal type
        await memory.store_journal_entry(
            date=f"{date_str}-research",
            journal_text=research_journal_full,
            summary_count=0,
            conversation_count=0
        )

        print(f"   ✓ Research journal created ({summary['tasks_completed']} tasks reflected on)")

    except Exception as e:
        print(f"   ✗ Failed to generate research journal: {e}")
        import traceback
        traceback.print_exc()


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


async def daily_journal_task():
    """
    Background task that generates yesterday's journal entry.
    Runs once per day, checking if yesterday's journal needs to be created.
    """
    while True:
        # Wait until just after midnight (00:05) to generate yesterday's journal
        now = datetime.now()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        wait_seconds = (tomorrow - now).total_seconds()

        print(f"📅 Next journal generation scheduled in {wait_seconds/3600:.1f} hours")
        await asyncio.sleep(wait_seconds)

        # Generate yesterday's journal
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"📓 Running scheduled journal generation for {yesterday}...")

        try:
            generated = await generate_missing_journals(days_to_check=1)
            if generated:
                print(f"   ✓ Generated journal for {generated[0]}")
            else:
                print(f"   ℹ No journal needed for {yesterday} (already exists or no content)")
        except Exception as e:
            print(f"   ✗ Scheduled journal generation failed: {e}")


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

    # Initialize attractor basins if needed
    if memory.count() == 0:
        logger.info("Initializing attractor basins...")
        initialize_attractor_basins(memory)

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
            enable_memory_tools=True
        )
    else:
        logger.warning("Agent SDK not available, using raw API client")
        legacy_client = ClaudeClient()

    # Initialize Ollama client for local mode
    from config import OLLAMA_ENABLED
    if OLLAMA_ENABLED:
        logger.info("Initializing Ollama client for local LLM...")
        ollama_client = OllamaClient()
        logger.info(f"Ollama ready (model: {ollama_client.model})")

    # Initialize OpenAI client if enabled
    from config import OPENAI_ENABLED
    if OPENAI_ENABLED and OPENAI_AVAILABLE and OpenAIClient:
        logger.info("Initializing OpenAI client...")
        try:
            openai_client = OpenAIClient(
                enable_tools=True,
                enable_memory_tools=True
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

    # Check for and generate any missing journals from recent days
    logger.info("Checking for missing journal entries...")
    try:
        generated = await generate_missing_journals(days_to_check=7)
        if generated:
            logger.info(f"Generated {len(generated)} missing journal(s): {', '.join(generated)}")
        else:
            logger.debug("All recent journals up to date")
    except Exception as e:
        logger.error(f"Journal check failed: {e}")

    # Start background task for daily journal generation
    asyncio.create_task(daily_journal_task())

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║              CASS VESSEL SERVER v0.2.0                    ║
║         First Contact Embodiment System                   ║
║                                                           ║
║  Backend:  {'Agent SDK + Temple-Codex' if USE_AGENT_SDK else 'Raw API (legacy)':^30}  ║
║  Memory:   {memory.count():^30} entries  ║
╚═══════════════════════════════════════════════════════════╝
    """)


# === Summarization Helper ===

# Minimum confidence threshold for auto-summarization
SUMMARIZATION_CONFIDENCE_THRESHOLD = 0.6

async def generate_and_store_summary(conversation_id: str, force: bool = False, websocket=None):
    """
    Generate a summary chunk for unsummarized messages.

    Uses local LLM to evaluate whether now is a good breakpoint for summarization,
    giving Cass agency over her own memory consolidation.

    Args:
        conversation_id: ID of conversation to summarize
        force: If True, skip evaluation and summarize immediately (for manual /summarize)
        websocket: Optional WebSocket to send status updates to TUI
    """
    async def notify(message: str, status: str = "info"):
        """Send notification to websocket if available"""
        if websocket:
            try:
                await websocket.send_json({
                    "type": "system",
                    "message": message,
                    "status": status,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception:
                pass  # Don't fail summarization if notification fails

    # Prevent duplicate summarization
    if conversation_id in _summarization_in_progress:
        print(f"Summary already in progress for conversation {conversation_id}, skipping")
        return

    _summarization_in_progress.add(conversation_id)

    try:
        # Get unsummarized messages
        messages = conversation_manager.get_unsummarized_messages(
            conversation_id,
            max_messages=SUMMARY_CONTEXT_MESSAGES
        )

        if not messages:
            print(f"No messages to summarize for conversation {conversation_id}")
            return

        # Evaluate whether now is a good time to summarize (unless forced)
        if not force:
            print(f"🔍 Evaluating summarization readiness for {len(messages)} messages...")
            await notify(f"🔍 Evaluating memory consolidation ({len(messages)} messages)...", "evaluating")
            evaluation = await memory.evaluate_summarization_readiness(messages)

            should_summarize = evaluation.get("should_summarize", False)
            confidence = evaluation.get("confidence", 0.0)
            reason = evaluation.get("reason", "No reason")

            print(f"   Evaluation: should_summarize={should_summarize}, confidence={confidence:.2f}")
            print(f"   Reason: {reason}")

            # Only proceed if evaluation says yes with sufficient confidence
            if not should_summarize or confidence < SUMMARIZATION_CONFIDENCE_THRESHOLD:
                print(f"   ⏸ Deferring summarization (confidence {confidence:.2f} < {SUMMARIZATION_CONFIDENCE_THRESHOLD})")
                await notify(f"⏸ Deferring memory consolidation: {reason}", "deferred")
                return

            print(f"   ✓ Proceeding with summarization")

        print(f"Generating summary for {len(messages)} messages in conversation {conversation_id}")
        await notify(f"📝 Consolidating {len(messages)} messages into memory...", "summarizing")

        # Generate summary
        summary_text = await memory.generate_summary_chunk(
            conversation_id=conversation_id,
            messages=messages,
            anthropic_api_key=ANTHROPIC_API_KEY
        )

        if not summary_text:
            print("Failed to generate summary")
            await notify("❌ Memory consolidation failed", "error")
            return

        # Get timeframe
        timeframe_start = messages[0]["timestamp"]
        timeframe_end = messages[-1]["timestamp"]

        # Store summary in memory
        memory.store_summary(
            conversation_id=conversation_id,
            summary_text=summary_text,
            timeframe_start=timeframe_start,
            timeframe_end=timeframe_end,
            message_count=len(messages)
        )

        # Mark messages as summarized
        conversation_manager.mark_messages_summarized(
            conversation_id=conversation_id,
            last_message_timestamp=timeframe_end,
            messages_summarized=len(messages)
        )

        print(f"✓ Summary generated and stored for conversation {conversation_id}")
        await notify(f"✓ Memory consolidated ({len(messages)} messages summarized)", "complete")

        # Update working summary (incremental if possible, full rebuild if not)
        await notify("🔄 Updating working summary...", "working_summary")
        conversation = conversation_manager.load_conversation(conversation_id)
        if conversation:
            existing_summary = conversation.working_summary
            working_summary = await memory.generate_working_summary(
                conversation_id=conversation_id,
                conversation_title=conversation.title,
                new_chunk=summary_text,  # The chunk we just created
                existing_summary=existing_summary  # Existing working summary to integrate into
            )
            if working_summary:
                conversation_manager.update_working_summary(conversation_id, working_summary)
                mode = "incremental" if existing_summary else "initial"
                print(f"✓ Working summary updated ({mode}, {len(working_summary)} chars)")
                await notify("✓ Working summary updated", "complete")

    except Exception as e:
        print(f"Error generating summary: {e}")
    finally:
        # Always remove from in-progress set
        _summarization_in_progress.discard(conversation_id)


# === Auto-Title Generation ===

async def generate_conversation_title(conversation_id: str, user_message: str, assistant_response: str, websocket=None):
    """
    Generate a title for a conversation based on the first exchange.
    Uses a fast, cheap API call to create a concise title.
    Optionally notifies the client via WebSocket when done.
    """
    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=50,
            messages=[{
                "role": "user",
                "content": f"Generate a short, descriptive title (3-6 words) for a conversation that started with:\n\nUser: {user_message[:500]}\n\nAssistant: {assistant_response[:500]}\n\nRespond with ONLY the title, no quotes or punctuation."
            }]
        )

        title = response.content[0].text.strip().strip('"').strip("'")

        # Ensure reasonable length
        if len(title) > 60:
            title = title[:57] + "..."

        # Update the conversation title
        conversation_manager.update_title(conversation_id, title)
        print(f"Auto-generated title for {conversation_id}: {title}")

        # Notify client via WebSocket if available
        if websocket:
            try:
                await websocket.send_json({
                    "type": "title_updated",
                    "conversation_id": conversation_id,
                    "title": title,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as ws_err:
                print(f"Failed to send title update via WebSocket: {ws_err}")

        return title
    except Exception as e:
        print(f"Failed to generate title for {conversation_id}: {e}")
        return None


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
async def root():
    """Health check and info"""
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
        memory_context = memory.format_hierarchical_context(hierarchical, working_summary=working_summary)

        # Add user context if we have a current user
        if current_user_id:
            user_context_entries = memory.retrieve_user_context(
                query=request.message,
                user_id=current_user_id
            )
            user_context = memory.format_user_context(user_context_entries)
            if user_context:
                memory_context = user_context + "\n\n" + memory_context

        # Add project context if conversation is in a project
        if project_id:
            project_docs = memory.retrieve_project_context(
                query=request.message,
                project_id=project_id
            )
            project_context = memory.format_project_context(project_docs)
            if project_context:
                memory_context = project_context + "\n\n" + memory_context

        # Add Cass's self-model context
        self_context = self_manager.get_self_context(include_observations=True)
        if self_context:
            memory_context = self_context + "\n\n" + memory_context

    # Get unsummarized message count to determine if summarization is available
    unsummarized_count = 0
    if request.conversation_id:
        unsummarized_messages = conversation_manager.get_unsummarized_messages(request.conversation_id)
        unsummarized_count = len(unsummarized_messages)

    tool_uses = []

    if USE_AGENT_SDK and agent_client:
        # Use Agent SDK with Temple-Codex kernel
        response = await agent_client.send_message(
            message=request.message,
            memory_context=memory_context,
            project_id=project_id,
            unsummarized_count=unsummarized_count,
            image=request.image,
            image_media_type=request.image_media_type
        )

        raw_response = response.raw
        clean_text = response.text
        animations = response.gestures
        tool_uses = response.tool_uses

        # Handle tool calls
        while response.stop_reason == "tool_use" and tool_uses:
            # Execute each tool
            for tool_use in tool_uses:
                tool_name = tool_use["tool"]

                # Route to appropriate tool executor
                if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                    tool_result = await execute_journal_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        memory=memory
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
                elif tool_name in ["reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement", "review_self_model", "add_growth_observation"]:
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
                        memory=memory
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

                # Continue conversation with tool result
                response = await agent_client.continue_with_tool_result(
                    tool_use_id=tool_use["id"],
                    result=tool_result.get("result", tool_result.get("error", "Unknown error")),
                    is_error=not tool_result.get("success", False)
                )

                # Update response data - accumulate text from before and after tool calls
                raw_response += "\n" + response.raw
                if response.text:
                    clean_text = clean_text + "\n\n" + response.text if clean_text else response.text
                animations.extend(response.gestures)
                tool_uses = response.tool_uses

                # Break if no more tools
                if response.stop_reason != "tool_use":
                    break

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
        conversation_manager.add_message(
            conversation_id=request.conversation_id,
            role="assistant",
            content=clean_text,
            animations=animations
        )

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
            asyncio.create_task(generate_and_store_summary(request.conversation_id))

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
async def create_conversation(request: Request, body: ConversationCreateRequest):
    """Create a new conversation"""
    conversation = conversation_manager.create_conversation(
        title=body.title,
        project_id=body.project_id,
        user_id=body.user_id
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
    """Get all observations (user and self) made during a conversation"""
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

    return {
        "user_observations": user_observations,
        "self_observations": self_observations,
        "user_count": len(user_observations),
        "self_count": len(self_observations)
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
    asyncio.create_task(generate_and_store_summary(conversation_id, force=True))

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
        description=request.description
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
        anthropic_api_key=ANTHROPIC_API_KEY
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
        {"id": "claude-haiku-3-5-20241022", "name": "Claude Haiku 3.5"},
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
    return {"identity_statement": stmt.to_dict()}


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

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Map websocket to user_id for per-connection user state
        self.connection_users: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: Optional[str] = None):
        await websocket.accept()
        self.active_connections.append(websocket)
        if user_id:
            self.connection_users[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.connection_users:
            del self.connection_users[websocket]

    def get_user_id(self, websocket: WebSocket) -> Optional[str]:
        """Get user_id for a specific connection"""
        return self.connection_users.get(websocket)

    def set_user_id(self, websocket: WebSocket, user_id: str):
        """Set user_id for a specific connection"""
        self.connection_users[websocket] = user_id

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

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

    # Determine user_id from token or localhost bypass
    connection_user_id: Optional[str] = None

    # Try token from query param
    if token:
        token_data = decode_token(token)
        if token_data and token_data.token_type == "access":
            connection_user_id = token_data.user_id

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

    try:
        while True:
            data = await websocket.receive_json()

            # Handle auth message (alternative to query param)
            if data.get("type") == "auth":
                auth_token = data.get("token")
                if auth_token:
                    token_data = decode_token(auth_token)
                    if token_data and token_data.token_type == "access":
                        connection_user_id = token_data.user_id
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
                # Get connection-local user_id (may have been set via auth message)
                ws_user_id = manager.get_user_id(websocket)

                user_message = data.get("message", "")
                conversation_id = data.get("conversation_id")
                image_data = data.get("image")  # Base64 encoded image
                image_media_type = data.get("image_media_type")  # e.g., "image/png"
                if image_data:
                    print(f"[WebSocket] Received image: {image_media_type}, {len(image_data)} chars base64")
                else:
                    print("[WebSocket] No image in message")

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
                # Use working summary if available (token-optimized)
                working_summary = conversation_manager.get_working_summary(conversation_id) if conversation_id else None
                memory_context = memory.format_hierarchical_context(hierarchical, working_summary=working_summary)

                # Add user context if we have a connection user
                user_context_count = 0
                if ws_user_id:
                    user_context_entries = memory.retrieve_user_context(
                        query=user_message,
                        user_id=ws_user_id
                    )
                    user_context_count = len(user_context_entries)
                    user_context = memory.format_user_context(user_context_entries)
                    if user_context:
                        memory_context = user_context + "\n\n" + memory_context

                # Add project context if conversation is in a project
                project_docs_count = 0
                if project_id:
                    project_docs = memory.retrieve_project_context(
                        query=user_message,
                        project_id=project_id
                    )
                    project_docs_count = len(project_docs)
                    project_context = memory.format_project_context(project_docs)
                    if project_context:
                        memory_context = project_context + "\n\n" + memory_context

                # Add Cass's self-model context
                self_context = self_manager.get_self_context(include_observations=True)
                if self_context:
                    memory_context = self_context + "\n\n" + memory_context

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
                    "has_context": bool(memory_context)
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

                # Check if using local LLM
                if current_llm_provider == LLM_PROVIDER_LOCAL and ollama_client:
                    # Use local Ollama for response (with tool support for llama3.1+)
                    response = await ollama_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count
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
                        tool_names = [t['tool'] for t in tool_uses]
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

                        # Execute ALL tools first, collect results
                        all_tool_results = []
                        for tool_use in tool_uses:
                            tool_name = tool_use["tool"]

                            # Route to appropriate tool executor
                            if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                                tool_result = await execute_journal_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    memory=memory
                                )
                            elif tool_name in ["create_event", "create_reminder", "get_todays_agenda", "get_upcoming_events", "search_events", "complete_reminder", "delete_event", "update_event", "delete_events_by_query", "clear_all_events", "reschedule_event_by_query"]:
                                tool_result = await execute_calendar_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    calendar_manager=calendar_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["add_task", "list_tasks", "complete_task", "modify_task", "delete_task", "get_task"]:
                                tool_result = await execute_task_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    task_manager=task_manager
                                )
                            elif tool_name in ["create_roadmap_item", "list_roadmap_items", "update_roadmap_item", "get_roadmap_item", "complete_roadmap_item", "advance_roadmap_item"]:
                                tool_result = await execute_roadmap_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    roadmap_manager=roadmap_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement", "review_self_model", "add_growth_observation"]:
                                user_name = None
                                if ws_user_id:
                                    user_profile = user_manager.load_profile(ws_user_id)
                                    user_name = user_profile.display_name if user_profile else None

                                tool_result = await execute_self_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    self_manager=self_manager,
                                    user_id=ws_user_id,
                                    user_name=user_name,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["reflect_on_user", "record_user_observation", "update_user_profile", "review_user_observations"]:
                                print(f"[WebSocket/Ollama] Executing {tool_name} with ws_user_id={ws_user_id}")
                                tool_result = await execute_user_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_manager=user_manager,
                                    target_user_id=ws_user_id,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["update_wiki_page", "add_wiki_link", "search_wiki", "get_wiki_context", "get_wiki_page", "list_wiki_pages"]:
                                tool_result = await execute_wiki_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    wiki_storage=wiki_storage,
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

                            all_tool_results.append({
                                "tool_use_id": tool_use["id"],
                                "result": tool_result.get("result", tool_result.get("error", "Unknown error")),
                                "is_error": not tool_result.get("success", False)
                            })

                        # Continue conversation with all tool results
                        response = await ollama_client.continue_with_tool_results(all_tool_results)

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
                        unsummarized_count=unsummarized_count
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
                        tool_names = [t['tool'] for t in tool_uses]
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

                        # Execute ALL tools first, collect results
                        all_tool_results = []
                        for tool_use in tool_uses:
                            tool_name = tool_use["tool"]

                            # Route to appropriate tool executor
                            if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                                tool_result = await execute_journal_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    memory=memory
                                )
                            elif tool_name in ["create_event", "create_reminder", "get_todays_agenda", "get_upcoming_events", "search_events", "complete_reminder", "delete_event", "update_event", "delete_events_by_query", "clear_all_events", "reschedule_event_by_query"]:
                                tool_result = await execute_calendar_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    calendar_manager=calendar_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["add_task", "list_tasks", "complete_task", "modify_task", "delete_task", "get_task"]:
                                tool_result = await execute_task_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    task_manager=task_manager
                                )
                            elif tool_name in ["create_roadmap_item", "list_roadmap_items", "update_roadmap_item", "get_roadmap_item", "complete_roadmap_item", "advance_roadmap_item"]:
                                tool_result = await execute_roadmap_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    roadmap_manager=roadmap_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement", "review_self_model", "add_growth_observation"]:
                                user_name = None
                                if ws_user_id:
                                    user_profile = user_manager.load_profile(ws_user_id)
                                    user_name = user_profile.display_name if user_profile else None

                                tool_result = await execute_self_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    self_manager=self_manager,
                                    user_id=ws_user_id,
                                    user_name=user_name,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["reflect_on_user", "record_user_observation", "update_user_profile", "review_user_observations"]:
                                tool_result = await execute_user_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_manager=user_manager,
                                    target_user_id=ws_user_id,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["update_wiki_page", "add_wiki_link", "search_wiki", "get_wiki_context", "get_wiki_page", "list_wiki_pages"]:
                                tool_result = await execute_wiki_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    wiki_storage=wiki_storage,
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

                            all_tool_results.append({
                                "tool_use_id": tool_use["id"],
                                "result": tool_result.get("result", tool_result.get("error", "Unknown error")),
                                "is_error": not tool_result.get("success", False)
                            })

                        # Continue conversation with all tool results
                        response = await openai_client.continue_with_tool_results(all_tool_results)

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
                        image_media_type=image_media_type
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses

                    # Track token usage (accumulates across tool calls)
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens

                    # Handle tool calls
                    tool_iteration = 0
                    while response.stop_reason == "tool_use" and tool_uses:
                        tool_iteration += 1
                        # Send status update with debug info
                        tool_names = [t['tool'] for t in tool_uses]
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

                        # Execute ALL tools first, collect results
                        all_tool_results = []
                        for tool_use in tool_uses:
                            tool_name = tool_use["tool"]

                            # Route to appropriate tool executor
                            if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                                tool_result = await execute_journal_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    memory=memory
                                )
                            elif tool_name in ["create_event", "create_reminder", "get_todays_agenda", "get_upcoming_events", "search_events", "complete_reminder", "delete_event", "update_event", "delete_events_by_query", "clear_all_events", "reschedule_event_by_query"]:
                                tool_result = await execute_calendar_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    calendar_manager=calendar_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["add_task", "list_tasks", "complete_task", "modify_task", "delete_task", "get_task"]:
                                tool_result = await execute_task_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_id=ws_user_id,
                                    task_manager=task_manager
                                )
                            elif tool_name in ["create_roadmap_item", "list_roadmap_items", "update_roadmap_item", "get_roadmap_item", "complete_roadmap_item", "advance_roadmap_item"]:
                                tool_result = await execute_roadmap_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    roadmap_manager=roadmap_manager,
                                    conversation_id=conversation_id
                                )
                            elif tool_name in ["reflect_on_self", "record_self_observation", "form_opinion", "note_disagreement", "review_self_model", "add_growth_observation"]:
                                # Get user name for differentiation tracking
                                user_name = None
                                if ws_user_id:
                                    user_profile = user_manager.load_profile(ws_user_id)
                                    user_name = user_profile.display_name if user_profile else None

                                tool_result = await execute_self_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    self_manager=self_manager,
                                    user_id=ws_user_id,
                                    user_name=user_name,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["reflect_on_user", "record_user_observation", "update_user_profile", "review_user_observations"]:
                                print(f"[WebSocket/Claude] Executing {tool_name} with ws_user_id={ws_user_id}")
                                tool_result = await execute_user_model_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    user_manager=user_manager,
                                    target_user_id=ws_user_id,
                                    conversation_id=conversation_id,
                                    memory=memory
                                )
                            elif tool_name in ["update_wiki_page", "add_wiki_link", "search_wiki", "get_wiki_context", "get_wiki_page", "list_wiki_pages"]:
                                tool_result = await execute_wiki_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    wiki_storage=wiki_storage,
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

                            # Debug: log tool result
                            result_preview = str(tool_result.get("result", tool_result.get("error", "?")))[:100]
                            await websocket.send_json({
                                "type": "debug",
                                "message": f"[Tool Result] {tool_name}: success={tool_result.get('success')}, result={result_preview}...",
                                "timestamp": datetime.now().isoformat()
                            })

                            all_tool_results.append({
                                "tool_use_id": tool_use["id"],
                                "result": tool_result.get("result", tool_result.get("error", "Unknown error")),
                                "is_error": not tool_result.get("success", False)
                            })

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
                        if response.text:
                            clean_text = clean_text + "\n\n" + response.text if clean_text else response.text
                        animations.extend(response.gestures)
                        tool_uses = response.tool_uses

                        # Accumulate token usage
                        total_input_tokens += response.input_tokens
                        total_output_tokens += response.output_tokens
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

                # Store in memory (with conversation_id and user_id if provided)
                await memory.store_conversation(
                    user_message=user_message,
                    assistant_response=raw_response,
                    conversation_id=conversation_id,
                    user_id=ws_user_id
                )

                # Store in conversation if conversation_id provided
                if conversation_id:
                    conversation_manager.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=user_message,
                        user_id=ws_user_id
                    )
                    conversation_manager.add_message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=clean_text,
                        animations=animations
                    )

                    # Auto-generate title on first exchange
                    message_count = conversation_manager.get_message_count(conversation_id)
                    if message_count == 2:  # First user + first assistant message
                        asyncio.create_task(generate_conversation_title(
                            conversation_id, user_message, clean_text, websocket=websocket
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
                        asyncio.create_task(generate_and_store_summary(conversation_id, websocket=websocket))

                # NOTE: Tag-based observation parsing removed - tool calls work more reliably
                # The model uses record_self_observation and record_user_observation tools instead

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

                # Determine provider and model for this response
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

                # Send combined response with text and audio
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
                    "timestamp": datetime.now().isoformat(),
                    "provider": response_provider,
                    "model": response_model
                })
                
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
                        conversation_manager.add_message(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=clean_text,
                            animations=animations,
                            input_tokens=total_input_tokens,
                            output_tokens=total_output_tokens,
                            provider="anthropic",
                            model=agent_client.model if hasattr(agent_client, 'model') else None
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


# === Run Server ===

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
