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
from config import ANTHROPIC_API_KEY, DEFAULT_SESSION_MODEL  # Force .env load
USE_STATE_BUS_CONTEXT = os.getenv("USE_STATE_BUS_CONTEXT", "false").lower() == "true"
print(f"[websocket_handlers] USE_STATE_BUS_CONTEXT={USE_STATE_BUS_CONTEXT}")

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

    # Check if essential services are initialized
    if memory is None or conversation_manager is None:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "Server is still initializing. Please try again in a moment."
        })
        await websocket.close()
        return
    user_manager = _state["user_manager"]
    self_manager = _state["self_manager"]
    self_model_graph = _state["self_model_graph"]
    goal_manager = _state["goal_manager"]
    marker_store = _state["marker_store"]
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
    daemon_id = _state["daemon_id"]

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
                # Default to continuous chat mode for authenticated users
                if not conversation_id:
                    if ws_user_id:
                        # Use continuous conversation for this user
                        continuous_conv = conversation_manager.get_or_create_continuous(ws_user_id)
                        conversation_id = continuous_conv.id
                        print(f"[WebSocket] Using continuous conversation {conversation_id} for user {ws_user_id}")
                    else:
                        # No user - create a regular conversation
                        new_conv = conversation_manager.create_conversation(
                            title=None,
                            user_id=ws_user_id
                        )
                        conversation_id = new_conv.id
                        print(f"[WebSocket] Auto-created conversation {conversation_id} (no user)")

                image_data = data.get("image")  # Base64 encoded image
                image_media_type = data.get("image_media_type")  # e.g., "image/png"
                attachment_ids = data.get("attachment_ids", [])  # Uploaded attachment IDs

                if image_data:
                    print(f"[WebSocket] Received image: {image_media_type}, {len(image_data)} chars base64")
                if attachment_ids:
                    print(f"[WebSocket] Received {len(attachment_ids)} attachment IDs: {attachment_ids}")
                if not image_data and not attachment_ids:
                    print("[WebSocket] No image or attachments in message")

                # Check if conversation belongs to a project and if it's continuous
                project_id = None
                is_continuous_chat = False
                if conversation_id:
                    conversation = conversation_manager.load_conversation(conversation_id)
                    if conversation:
                        project_id = conversation.project_id
                        is_continuous_chat = conversation.is_continuous

                # === Global State Bus Integration (A/B Test) ===
                global_state_context = None
                current_activity = None
                state_bus = _state.get("state_bus")

                if USE_STATE_BUS_CONTEXT and state_bus:
                    from state_models import StateDelta, ActivityType

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

                # === Session Initialization (Continuity Awareness) ===
                # Build context that helps Cass "wake up" with awareness of her recent state
                session_init_context = ""
                if conversation_id and self_manager:
                    try:
                        from session_init import (
                            build_session_init_context,
                            should_rebuild_session_context,
                        )

                        # Check if we need to build/rebuild session context
                        # Use a simple heuristic: first message or conversation has few messages
                        conversation = conversation_manager.load_conversation(conversation_id)
                        is_session_start = (
                            conversation and
                            len(conversation.messages) < 3  # First few messages
                        )

                        if is_session_start:
                            session_ctx = await build_session_init_context(
                                conversation_id=conversation_id,
                                user_id=ws_user_id,
                                self_manager=self_manager,
                                memory=memory,
                                conversation_manager=conversation_manager,
                                state_bus=state_bus,
                                profile_manager=profile_manager if 'profile_manager' in dir() else None,
                            )
                            session_init_context = session_ctx.format_for_prompt()
                            if session_init_context:
                                print(f"[Session] Built init context: ~{session_ctx.token_estimate} tokens")
                    except Exception as e:
                        print(f"[Session] Init context failed: {e}")

                # === Unified Context Building ===
                # Always use continuous context system - cleaner, unified, with semantic retrieval
                # Legacy hierarchical context building is now deprecated
                continuous_system_prompt = None
                continuous_messages = None
                if True:  # Always use continuous context (was: if is_continuous_chat)
                    from continuous_context import build_continuous_context, get_recent_messages_for_continuous
                    print(f"[Continuous] Building context with semantic memory retrieval")

                    continuous_ctx = build_continuous_context(
                        user_id=ws_user_id,
                        conversation_id=conversation_id,
                        user_manager=user_manager,
                        thread_manager=thread_manager,
                        question_manager=question_manager,
                        conversation_manager=conversation_manager,
                        daemon_name="Cass",
                        daemon_id=daemon_id,
                        memory=memory,
                        query=user_message,
                    )
                    continuous_system_prompt = continuous_ctx.system_prompt
                    has_semantic = "semantic_memories" in continuous_ctx.context_sections

                    # Get recent message history for conversation continuity
                    continuous_messages = get_recent_messages_for_continuous(
                        conversation_manager=conversation_manager,
                        conversation_id=conversation_id,
                        limit=12  # Last 12 messages (6 exchanges)
                    )
                    print(f"[Continuous] Built system prompt: {continuous_ctx.token_estimate} tokens (estimated), semantic={has_semantic}, messages={len(continuous_messages)}")

                # Initialize context tracking variables for the memory_summary display
                # Actual context is built by continuous_context.build_continuous_context() above
                hierarchical = {}
                context_sizes = {}
                memory_context = ""
                user_context = ""
                user_context_count = 0
                intro_guidance = None
                user_model_context = None
                relationship_context = None
                project_docs_count = 0
                wiki_pages_count = 0
                cross_session_insights_count = 0
                pattern_count = 0
                threads_context = ""
                questions_context = ""
                thread_count = 0
                question_count = 0
                tool_count = 0
                unsummarized_count = 0

                # Send "thinking" status with memory info
                # Context is built by continuous_context.build_continuous_context() above
                context_sizes = {"continuous": len(continuous_system_prompt) if continuous_system_prompt else 0}
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
                    generated_images = []  # Track images generated during this request

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
                    generated_images = []  # Track images generated during this request

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
                        continuous_system_prompt=continuous_system_prompt,
                        continuous_messages=continuous_messages,
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses

                    # Track token usage (accumulates across tool calls)
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens
                    total_cache_read_tokens = getattr(response, 'cache_read_tokens', 0) or 0
                    generated_images = []  # Track images generated during this request

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

                        # Extract any generated images from tool results
                        import re
                        for tool_use, result in zip(tool_uses, all_tool_results):
                            if tool_use['tool'] == 'generate_image' and result.get('success'):
                                result_data = result.get('result', '')
                                # Handle both string and list (content blocks) formats
                                if isinstance(result_data, list):
                                    # Extract text from first content block
                                    result_str = next((b.get('text', '') for b in result_data if b.get('type') == 'text'), '')
                                else:
                                    result_str = result_data
                                path_match = re.search(r'path:\s*"([^"]+)"', result_str)
                                style_match = re.search(r'style:\s*"([^"]+)"', result_str)
                                purpose_match = re.search(r'purpose:\s*"([^"]+)"', result_str)
                                image_id_match = re.search(r'image_id:\s*"([^"]+)"', result_str)
                                dims_match = re.search(r'Dimensions:\s*(\d+)x(\d+)', result_str)
                                if path_match:
                                    generated_images.append({
                                        'url': path_match.group(1),
                                        'style': style_match.group(1) if style_match else None,
                                        'purpose': purpose_match.group(1) if purpose_match else None,
                                        'image_id': image_id_match.group(1) if image_id_match else None,
                                        'width': int(dims_match.group(1)) if dims_match else None,
                                        'height': int(dims_match.group(2)) if dims_match else None,
                                    })
                                    print(f"[Image] Extracted generated image: {path_match.group(1)}")

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
                    generated_images = []  # Legacy mode doesn't support image generation

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
                extracted_feels = processed_tags.get("feels", [])

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
                    response_model = agent_client.model if hasattr(agent_client, 'model') else DEFAULT_SESSION_MODEL
                else:
                    response_provider = "anthropic"
                    response_model = DEFAULT_SESSION_MODEL

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
                    "feels": extracted_feels if extracted_feels else None,
                    "generated_images": generated_images if generated_images else None,
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

        # Proactive self-observation: Extract insights from this conversation
        # Run asynchronously to not block disconnect
        if conversation_id and self_manager and memory and conversation_manager:
            try:
                from background_tasks import extract_post_conversation_observations
                asyncio.create_task(
                    extract_post_conversation_observations(
                        conversation_id=conversation_id,
                        user_id=ws_user_id,
                        conversation_manager=conversation_manager,
                        memory=memory,
                        self_manager=self_manager,
                        min_messages=4,
                    )
                )
            except Exception as obs_error:
                print(f"[WebSocket] Failed to queue observation extraction: {obs_error}")

    except Exception as e:
        print(f"[WebSocket] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        manager.disconnect(websocket)
