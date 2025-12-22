"""
WebSocket handlers extracted from main_sdk.py

This module handles real-time WebSocket communication including:
- Chat messages with multi-LLM support (Claude, OpenAI, Ollama)
- Authentication (token-based and localhost bypass)
- Tool execution loops
- Context building (memory, wiki, self-model, user model)
- Post-processing (marks, inline tags, TTS)
- Onboarding flows
- Global State Bus integration for "Locus of Self" awareness
"""

from fastapi import WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import asyncio
import base64
import os
import time

# LLM Provider constants
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_LOCAL = "local"

# A/B Test: Global State Bus integration
# Set USE_STATE_BUS_CONTEXT=true to enable state bus context in prompts
USE_STATE_BUS_CONTEXT = os.getenv("USE_STATE_BUS_CONTEXT", "false").lower() == "true"

# Module-level state (injected by main_sdk.py via init functions)
_state = {
    # Core managers
    "memory": None,
    "conversation_manager": None,
    "user_manager": None,
    "self_manager": None,
    "self_model_graph": None,
    "goal_manager": None,
    "marker_store": None,
    "daily_rhythm_manager": None,
    "token_tracker": None,
    "temporal_metrics_tracker": None,
    "connection_manager": None,
    "thread_manager": None,
    "question_manager": None,
    "state_bus": None,
    "daemon_id": None,

    # LLM clients
    "agent_client": None,
    "openai_client": None,
    "ollama_client": None,
    "legacy_client": None,
    "response_processor": None,

    # LLM state
    "current_llm_provider": LLM_PROVIDER_ANTHROPIC,
    "use_agent_sdk": True,

    # TTS state
    "tts_enabled": False,
    "tts_voice": "kirsty",

    # Tool execution
    "tool_executors": None,
    "create_tool_context": None,
    "execute_tool_batch": None,
    "create_timing_data": None,

    # Context helpers
    "get_automatic_wiki_context": None,
    "process_inline_tags": None,
    "generate_and_store_summary": None,
    "generate_conversation_title": None,
    "get_narration_metrics": None,

    # Config
    "auto_summary_interval": 10,
}


def init_websocket_state(
    memory,
    conversation_manager,
    user_manager,
    self_manager,
    self_model_graph,
    goal_manager,
    marker_store,
    daily_rhythm_manager,
    token_tracker,
    temporal_metrics_tracker,
    connection_manager,
    agent_client,
    openai_client,
    ollama_client,
    legacy_client,
    response_processor,
    tool_executors,
    create_tool_context_fn,
    execute_tool_batch_fn,
    create_timing_data_fn,
    get_automatic_wiki_context_fn,
    process_inline_tags_fn,
    generate_and_store_summary_fn,
    generate_conversation_title_fn,
    get_narration_metrics_fn,
    auto_summary_interval: int = 10,
    daemon_id: str = None,
):
    """Initialize all dependencies for websocket handlers."""
    from memory import ThreadManager, OpenQuestionManager

    _state["memory"] = memory
    _state["conversation_manager"] = conversation_manager
    _state["user_manager"] = user_manager
    _state["self_manager"] = self_manager
    _state["self_model_graph"] = self_model_graph
    _state["goal_manager"] = goal_manager
    _state["marker_store"] = marker_store
    _state["daily_rhythm_manager"] = daily_rhythm_manager
    _state["token_tracker"] = token_tracker
    _state["temporal_metrics_tracker"] = temporal_metrics_tracker
    _state["connection_manager"] = connection_manager
    _state["agent_client"] = agent_client
    _state["openai_client"] = openai_client
    _state["ollama_client"] = ollama_client
    _state["legacy_client"] = legacy_client
    _state["response_processor"] = response_processor
    _state["tool_executors"] = tool_executors
    _state["create_tool_context"] = create_tool_context_fn
    _state["execute_tool_batch"] = execute_tool_batch_fn
    _state["create_timing_data"] = create_timing_data_fn
    _state["get_automatic_wiki_context"] = get_automatic_wiki_context_fn
    _state["process_inline_tags"] = process_inline_tags_fn
    _state["generate_and_store_summary"] = generate_and_store_summary_fn
    _state["generate_conversation_title"] = generate_conversation_title_fn
    _state["get_narration_metrics"] = get_narration_metrics_fn
    _state["auto_summary_interval"] = auto_summary_interval
    _state["daemon_id"] = daemon_id

    # Initialize thread and question managers for narrative coherence
    if daemon_id:
        _state["thread_manager"] = ThreadManager(daemon_id)
        _state["question_manager"] = OpenQuestionManager(daemon_id)
        print(f"[WebSocket] Initialized ThreadManager and OpenQuestionManager for daemon {daemon_id}")

    # Initialize global state bus
    if daemon_id:
        from state_bus import get_state_bus
        _state["state_bus"] = get_state_bus(daemon_id)
        print(f"[WebSocket] Initialized GlobalStateBus for daemon {daemon_id}")


def set_llm_provider(provider: str):
    """Set the current LLM provider."""
    _state["current_llm_provider"] = provider


def get_llm_provider() -> str:
    """Get the current LLM provider."""
    return _state["current_llm_provider"]


def set_use_agent_sdk(use_sdk: bool):
    """Set whether to use Agent SDK."""
    _state["use_agent_sdk"] = use_sdk


def set_tts_state(enabled: bool, voice: str = "kirsty"):
    """Set TTS configuration."""
    _state["tts_enabled"] = enabled
    _state["tts_voice"] = voice


def update_llm_clients(agent_client=None, openai_client=None, ollama_client=None):
    """Update LLM client references (called when clients are re-initialized)."""
    if agent_client is not None:
        _state["agent_client"] = agent_client
    if openai_client is not None:
        _state["openai_client"] = openai_client
    if ollama_client is not None:
        _state["ollama_client"] = ollama_client


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
    from tts import text_to_speech
    from markers import parse_marks
    from pattern_aggregation import get_pattern_summary_for_surfacing
    from config import ONBOARDING_INTRO_PROMPT, ONBOARDING_DEMO_PROMPT

    # Get state references
    manager = _state["connection_manager"]
    memory = _state["memory"]
    conversation_manager = _state["conversation_manager"]
    user_manager = _state["user_manager"]
    self_manager = _state["self_manager"]
    self_model_graph = _state["self_model_graph"]
    goal_manager = _state["goal_manager"]
    marker_store = _state["marker_store"]
    daily_rhythm_manager = _state["daily_rhythm_manager"]
    token_tracker = _state["token_tracker"]
    temporal_metrics_tracker = _state["temporal_metrics_tracker"]
    agent_client = _state["agent_client"]
    openai_client = _state["openai_client"]
    ollama_client = _state["ollama_client"]
    legacy_client = _state["legacy_client"]
    response_processor = _state["response_processor"]
    current_llm_provider = _state["current_llm_provider"]
    USE_AGENT_SDK = _state["use_agent_sdk"]
    tts_enabled = _state["tts_enabled"]
    tts_voice = _state["tts_voice"]
    TOOL_EXECUTORS = _state["tool_executors"]
    create_tool_context = _state["create_tool_context"]
    execute_tool_batch = _state["execute_tool_batch"]
    create_timing_data = _state["create_timing_data"]
    get_automatic_wiki_context = _state["get_automatic_wiki_context"]
    process_inline_tags = _state["process_inline_tags"]
    generate_and_store_summary = _state["generate_and_store_summary"]
    generate_conversation_title = _state["generate_conversation_title"]
    get_narration_metrics = _state["get_narration_metrics"]
    AUTO_SUMMARY_INTERVAL = _state["auto_summary_interval"]
    thread_manager = _state["thread_manager"]
    question_manager = _state["question_manager"]

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

                # === Global State Bus Integration (A/B Test) ===
                global_state_context = None
                current_activity = None
                state_bus = _state.get("state_bus")

                if USE_STATE_BUS_CONTEXT and state_bus:
                    from state_models import StateDelta, ActivityType
                    from datetime import datetime

                    # Emit chat_started event and update activity state
                    # Note: No active_session_id - conversations are artifacts, not cognition units
                    state_bus.write_delta(StateDelta(
                        source="websocket_chat",
                        activity_delta={
                            "current_activity": ActivityType.CHAT.value,
                            "active_user_id": ws_user_id,
                            "contact_started_at": datetime.now().isoformat(),
                        },
                        event="chat_started",
                        event_data={
                            "user_id": ws_user_id,
                            "project_id": project_id,
                        },
                        reason="User message received, contact with user active",
                    ))

                    # Read state snapshot for prompt context
                    global_state_context = state_bus.get_context_snapshot()
                    state = state_bus.read_state()
                    current_activity = state.activity.current_activity.value if state.activity else None
                    print(f"[StateBus] Context: {global_state_context}")

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
                    print(f"[Context] User model context: {len(user_model_context) if user_model_context else 0} chars")
                    print(f"[Context] Relationship context: {len(relationship_context) if relationship_context else 0} chars")
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
                patterns_context, pattern_count = get_pattern_summary_for_surfacing(
                    marker_store=marker_store,
                    min_significance=0.5,
                    limit=3
                )
                if patterns_context:
                    memory_context = patterns_context + "\n\n" + memory_context
                context_sizes["patterns"] = len(patterns_context) if patterns_context else 0

                # Add narrative coherence context (threads + open questions)
                # This is GUARANTEED BASELINE - always included if available
                # NOTE: threads_context and questions_context are passed separately to send_message
                # for proper chain system support (they get their own NARRATIVE AWARENESS section)
                threads_context = ""
                questions_context = ""
                thread_count = 0
                question_count = 0

                if thread_manager:
                    threads_context = thread_manager.format_threads_context(
                        user_id=ws_user_id,
                        limit=5
                    )
                    if threads_context:
                        thread_count = len(thread_manager.get_active_threads(user_id=ws_user_id, limit=5))
                context_sizes["threads"] = len(threads_context) if threads_context else 0

                if question_manager:
                    questions_context = question_manager.format_questions_context(
                        user_id=ws_user_id,
                        limit=5
                    )
                    if questions_context:
                        question_count = len(question_manager.get_open_questions(user_id=ws_user_id, limit=5))
                context_sizes["questions"] = len(questions_context) if questions_context else 0

                if thread_count > 0 or question_count > 0:
                    print(f"[NarrativeCoherence] {thread_count} threads, {question_count} questions ready for injection")

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
                    "thread_count": thread_count,  # Active conversation threads
                    "question_count": question_count,  # Open questions
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
                        global_state_context=global_state_context,
                        current_activity=current_activity,
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
                        global_state_context=global_state_context,
                        current_activity=current_activity,
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
                        threads_context=threads_context if threads_context else None,
                        questions_context=questions_context if questions_context else None,
                        global_state_context=global_state_context,
                        current_activity=current_activity,
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

                    # Update global state bus with emotional state from emotes
                    state_bus = _state.get("state_bus")
                    if state_bus and animations:
                        from gestures import extract_emotional_state, should_write_emotional_delta
                        from state_models import StateDelta

                        emotional_delta = extract_emotional_state(animations)
                        if should_write_emotional_delta(emotional_delta):
                            delta = StateDelta(
                                source="chat",
                                emotional_delta=emotional_delta,
                                activity_delta={
                                    "current_activity": "chat",
                                    "active_user_id": ws_user_id,
                                },
                                reason=f"Chat response with emotes: {[a['name'] for a in animations if a.get('type') == 'emote']}"
                            )
                            state_bus.write_delta(delta)

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

                # Build profile context
                profile_context = user_manager.get_user_context(user_id) or "No additional profile information provided."

                # Format the onboarding prompt
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
