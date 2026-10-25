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
    "connection_manager": None,
    "thread_manager": None,
    "question_manager": None,
    "state_bus": None,
    "daemon_id": None,

    # LLM clients
    "agent_client": None,
    "openai_client": None,
    "ollama_client": None,
    "response_processor": None,

    # LLM state
    "current_llm_provider": LLM_PROVIDER_ANTHROPIC,
    "use_agent_sdk": True,

    # TTS state
    "tts_enabled": False,
    "tts_voice": "kirsty",
    "tts_provider": "piper",  # "piper" (fast) or "xtts" (quality)

    # Tool execution
    "tool_executors": None,
    "create_tool_context": None,
    "execute_tool_batch": None,

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
    connection_manager,
    agent_client,
    openai_client,
    ollama_client,
    response_processor,
    tool_executors,
    create_tool_context_fn,
    execute_tool_batch_fn,
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
    _state["connection_manager"] = connection_manager
    _state["agent_client"] = agent_client
    _state["openai_client"] = openai_client
    _state["ollama_client"] = ollama_client
    _state["response_processor"] = response_processor
    _state["tool_executors"] = tool_executors
    _state["create_tool_context"] = create_tool_context_fn
    _state["execute_tool_batch"] = execute_tool_batch_fn
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


def set_tts_state(enabled: bool, voice: str = "kirsty", provider: str = "piper"):
    """Set TTS configuration."""
    _state["tts_enabled"] = enabled
    _state["tts_voice"] = voice
    _state["tts_provider"] = provider


def update_llm_clients(agent_client=None, openai_client=None, ollama_client=None):
    """Update LLM client references (called when clients are re-initialized)."""
    if agent_client is not None:
        _state["agent_client"] = agent_client
    if openai_client is not None:
        _state["openai_client"] = openai_client
    if ollama_client is not None:
        _state["ollama_client"] = ollama_client


# =============================================================================
# Shared chat-turn helpers (used by the websocket loop and the mobile relay)
# =============================================================================

def mark_user_activity() -> None:
    """Tell Synkratos a person is active, so idle-only jobs wait.

    Synkratos treats "no activity for 5 minutes" as idle. Nothing used to
    report activity, so idle-only jobs (e.g. idle summarization) ran even in
    the middle of a conversation. Called once per chat turn.
    """
    try:
        from routes.admin.scheduler import get_scheduler
        scheduler = get_scheduler()
        if scheduler is not None:
            scheduler.record_activity()
    except Exception as e:
        # Never let bookkeeping break a chat turn.
        print(f"[Activity] Could not record activity: {e}")


async def execute_tools_safely(execute_tool_batch, tool_uses, tool_ctx, executors) -> List[Dict]:
    """Run a turn's tool calls; a tool that raises becomes an error result.

    Before, one tool exception escaped the websocket loop, dropped the
    connection and the turn was never saved. Now the model gets an
    is_error tool_result it can react to, and the turn completes.
    Tools run one at a time, as execute_tool_batch already did.
    """
    from strict import report_swallowed

    results = []
    for tool_use in tool_uses:
        try:
            results.extend(await execute_tool_batch([tool_use], tool_ctx, executors))
        except Exception as e:
            results.append({
                "tool_use_id": tool_use["id"],
                "result": f"Tool '{tool_use.get('tool')}' failed: {type(e).__name__}: {e}",
                "is_error": True,
            })
            # Loud in tests (CASS_STRICT=1), a log line in production.
            report_swallowed(e, f"[Tools] {tool_use.get('tool')} raised during a chat turn")
    return results


def extract_generated_images(tool_uses: List[Dict], tool_results: List[Dict]) -> List[Dict]:
    """Pull image metadata out of successful generate_image tool results."""
    import re
    images = []
    for tool_use, result in zip(tool_uses, tool_results):
        # Results from execute_tool_batch carry is_error (not success)
        if tool_use['tool'] != 'generate_image' or result.get('is_error', not result.get('success', False)):
            continue
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
            images.append({
                'url': path_match.group(1),
                'style': style_match.group(1) if style_match else None,
                'purpose': purpose_match.group(1) if purpose_match else None,
                'image_id': image_id_match.group(1) if image_id_match else None,
                'width': int(dims_match.group(1)) if dims_match else None,
                'height': int(dims_match.group(2)) if dims_match else None,
            })
            print(f"[Image] Extracted generated image: {path_match.group(1)}")
    return images


def max_tool_iterations() -> int:
    """Cap on model->tool->model round trips per chat turn (config, env-overridable)."""
    from config import CHAT_MAX_TOOL_ITERATIONS
    return CHAT_MAX_TOOL_ITERATIONS


async def finalize_chat_turn(
    *,
    user_message: str,
    raw_response: str,
    clean_text: str,
    animations: List[Dict],
    conversation_id: Optional[str],
    user_id: Optional[str],
    input_tokens: int,
    output_tokens: int,
    provider: str,
    model: str,
    tool_iterations: int,
    summarize_requested: bool,
    websocket=None,
    cache_read_tokens: int = 0,
    memory_metadata: Optional[Dict[str, Any]] = None,
    generate_title: bool = True,
) -> Dict[str, Any]:
    """Post-turn pipeline shared by every chat entry point.

    Strips and stores marks, symbols, interests and inline tags; stores the
    exchange in ChromaDB and SQLite; records tokens; updates the state bus;
    and kicks off title generation and summarization. The websocket loop
    always did all of this; the mobile relay skipped most of it. Every chat
    entry point reaches it through chat_turn.run_chat_turn.

    Token usage is recorded even without a conversation (an unlinked Discord
    sender has none). generate_title=False skips the background LLM title
    call (Home Assistant and Discord never made one).

    Returns the cleaned text plus everything extracted, for the response frame.
    """
    from markers import parse_marks
    from symbols import parse_symbols, store_extracted_symbols
    from interests import parse_interests, store_extracted_interests

    memory = _state["memory"]
    conversation_manager = _state["conversation_manager"]
    marker_store = _state["marker_store"]
    token_tracker = _state["token_tracker"]
    daemon_id = _state["daemon_id"]
    process_inline_tags = _state["process_inline_tags"]
    get_narration_metrics = _state["get_narration_metrics"]
    generate_conversation_title = _state["generate_conversation_title"]
    generate_and_store_summary = _state["generate_and_store_summary"]
    AUTO_SUMMARY_INTERVAL = _state["auto_summary_interval"]

    # Extract and store recognition-in-flow marks before other processing
    clean_text, marks = parse_marks(clean_text, conversation_id)
    if marks and marker_store:
        stored = marker_store.store_marks(marks)
        if stored > 0:
            print(f"  Stored {stored} recognition-in-flow mark(s)")

    # Extract and store personal symbols
    clean_text, extracted_symbols = parse_symbols(clean_text)
    if extracted_symbols and daemon_id:
        stored_symbols = store_extracted_symbols(
            extracted_symbols,
            daemon_id=daemon_id,
            source_type="conversation",
            source_id=conversation_id
        )
        if stored_symbols > 0:
            print(f"  Stored {stored_symbols} personal symbol(s)")

    # Extract and store personal interests
    clean_text, extracted_interests = parse_interests(clean_text)
    if extracted_interests and daemon_id:
        stored_interests = store_extracted_interests(
            extracted_interests,
            daemon_id=daemon_id,
            source_type="conversation",
            source_id=conversation_id
        )
        if stored_interests > 0:
            print(f"  Stored {stored_interests} personal interest(s)")

    # Process inline XML tags (observations, roadmap items) and strip them
    # Returns dict with cleaned text and all extracted metacognitive tags
    processed_tags = await process_inline_tags(
        text=clean_text,
        conversation_id=conversation_id,
        user_id=user_id
    )
    clean_text = processed_tags["text"]
    extracted = {
        "self_observations": processed_tags["self_observations"],
        "user_observations": processed_tags["user_observations"],
        "holds": processed_tags["holds"],
        "notes": processed_tags["notes"],
        "intentions": processed_tags["intentions"],
        "stakes": processed_tags["stakes"],
        "tests": processed_tags["tests"],
        "narrations": processed_tags["narrations"],
        "milestones": processed_tags["milestones"],
        "feels": processed_tags.get("feels", []),
    }

    # Store in memory (with conversation_id and user_id if provided)
    if memory:
        await memory.store_conversation(
            user_message=user_message,
            assistant_response=raw_response,
            conversation_id=conversation_id,
            user_id=user_id,
            metadata=memory_metadata,
        )

    # Track token usage
    operation = "tool_continuation" if tool_iterations > 0 else "initial_message"
    token_tracker.record(
        category="chat",
        operation=operation,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        conversation_id=conversation_id,
        user_id=user_id
    )

    # Store in conversation if conversation_id provided
    if conversation_id:
        conversation_manager.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            user_id=user_id
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
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider=provider,
            model=model,
            self_observations=extracted["self_observations"] or None,
            user_observations=extracted["user_observations"] or None,
            marks=marks_for_storage,
            narration_metrics=narration_metrics,
            holds=extracted["holds"] or None,
            notes=extracted["notes"] or None,
            intentions=extracted["intentions"] or None,
            stakes=extracted["stakes"] or None,
            tests=extracted["tests"] or None,
            narrations=extracted["narrations"] or None,
            milestones=extracted["milestones"] or None
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
                        "active_user_id": user_id,
                    },
                    reason=f"Chat response with emotes: {[a['name'] for a in animations if a.get('type') == 'emote']}"
                )
                state_bus.write_delta(delta)

        # Auto-generate title on first exchange
        message_count = conversation_manager.get_message_count(conversation_id)
        if generate_title and message_count == 2:  # First user + first assistant message
            asyncio.create_task(generate_conversation_title(
                conversation_id, user_message, clean_text,
                conversation_manager=conversation_manager,
                token_tracker=token_tracker,
                websocket=websocket
            ))

        # Summarize on a <memory:summarize> tag or after the auto-summary threshold
        should_summarize = summarize_requested
        if conversation_manager.needs_auto_summary(conversation_id, AUTO_SUMMARY_INTERVAL):
            should_summarize = True

        if should_summarize:
            # Run summarization in background, pass websocket for status updates
            asyncio.create_task(generate_and_store_summary(
                conversation_id,
                memory=memory,
                conversation_manager=conversation_manager,
                token_tracker=token_tracker,
                websocket=websocket
            ))

    return {"clean_text": clean_text, "marks": marks, **extracted}


async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    """
    WebSocket for real-time bidirectional communication.

    Authentication:
    - Pass token as query parameter: ws://host/ws?token=<jwt>
    - Or send {type: "auth", token: "<jwt>"} as first message
    - Localhost connections fall back to DEFAULT_LOCALHOST_USER_ID
    """
    import os
    from auth import user_id_from_any_token, is_localhost_request
    from tts import synthesize
    from markers import parse_marks
    from symbols import parse_symbols, store_extracted_symbols
    from interests import parse_interests, store_extracted_interests
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
    agent_client = _state["agent_client"]
    openai_client = _state["openai_client"]
    ollama_client = _state["ollama_client"]
    response_processor = _state["response_processor"]
    current_llm_provider = _state["current_llm_provider"]
    USE_AGENT_SDK = _state["use_agent_sdk"]
    tts_enabled = _state["tts_enabled"]
    tts_voice = _state["tts_voice"]
    tts_provider = _state["tts_provider"]
    TOOL_EXECUTORS = _state["tool_executors"]
    create_tool_context = _state["create_tool_context"]
    execute_tool_batch = _state["execute_tool_batch"]
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
        # One verifier for every accepted token format (auth.py).
        connection_user_id = user_id_from_any_token(token)

    # Localhost bypass if no token. Shared helper so relayed/proxied
    # connections (which also arrive from 127.0.0.1) don't get it.
    if not connection_user_id:
        from auth import localhost_bypass_user
        connection_user_id = localhost_bypass_user(websocket)

    await manager.connect(websocket, user_id=connection_user_id)

    await websocket.send_json({
        "type": "connected",
        "message": "Cass vessel connected",
        "sdk_mode": USE_AGENT_SDK,
        "user_id": connection_user_id,
        "timestamp": datetime.now().isoformat()
    })
    print(f"[WebSocket] Sent connected message, entering message loop for user {connection_user_id}")

    # Read by the disconnect handler; must exist even if no chat was sent.
    conversation_id = None

    try:
        while True:
            print("[WebSocket] Waiting for message...")
            data = await websocket.receive_json()
            print(f"[WebSocket] Received message type: {data.get('type')}")

            # Handle auth message (alternative to query param)
            if data.get("type") == "auth":
                auth_token = data.get("token")
                if auth_token:
                    token_user_id = user_id_from_any_token(auth_token)
                    if token_user_id:
                        connection_user_id = token_user_id

                    if token_user_id:
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

            # Everything except auth/ping needs an identified user. Before, an
            # anonymous socket could chat (spending tokens) and run onboarding.
            if data.get("type") not in ("ping",) and not manager.get_user_id(websocket):
                await websocket.send_json({
                    "type": "auth_error",
                    "message": "Authentication required: send {type: 'auth', token} or connect with ?token="
                })
                continue

            if data.get("type") == "chat":
                # Re-read the provider and clients every turn, not once per
                # connection: a provider switch (/settings/llm-provider) or a
                # client re-init must reach sockets that are already open.
                current_llm_provider = _state["current_llm_provider"]
                agent_client = _state["agent_client"]
                openai_client = _state["openai_client"]
                ollama_client = _state["ollama_client"]
                USE_AGENT_SDK = _state["use_agent_sdk"]
                tts_enabled = _state["tts_enabled"]
                tts_voice = _state["tts_voice"]
                tts_provider = _state["tts_provider"]

                # (run_chat_turn marks the user as active.)

                # A running autonomous session (agent_loop lever) ends cleanly.
                from agent_loop.interrupt import entry_point_received_message
                entry_point_received_message(manager.get_user_id(websocket), "websocket")

                # Get connection-local user_id (may have been set via auth message)
                ws_user_id = manager.get_user_id(websocket)

                user_message = data.get("message", "")
                conversation_id = data.get("conversation_id")
                source_device = data.get("source_device")  # e.g., "Embodiment (Emulated)"

                # Prepend source device context if present
                if source_device:
                    user_message = f"[Via: {source_device}]\n{user_message}"

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
                speaker_recognition_data = data.get("speaker_recognition")  # Voice identification

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

                # === The shared chat turn (chat_turn.run_chat_turn) ===
                # Context, the capped tool loop, tags and persistence are the
                # same for every entry point; the socket only relays progress.
                from continuous_context import SpeakerRecognition
                from chat_turn import run_chat_turn

                speaker_recognition = None
                if speaker_recognition_data:
                    speaker_recognition = SpeakerRecognition(
                        user_id=speaker_recognition_data.get("user_id"),
                        display_name=speaker_recognition_data.get("display_name"),
                        confidence=speaker_recognition_data.get("confidence", 0.0),
                        confidence_level=speaker_recognition_data.get("confidence_level", "none"),
                    )
                    print(f"[Voice] Speaker recognition: {speaker_recognition.display_name} ({speaker_recognition.confidence_level})")

                result = await run_chat_turn(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    user_id=ws_user_id,
                    project_id=project_id,
                    image=image_data,
                    image_media_type=image_media_type,
                    speaker_recognition=speaker_recognition,
                    progress=websocket.send_json,
                    extra_send_kwargs=dict(
                        global_state_context=global_state_context,
                        current_activity=current_activity,
                    ),
                    websocket=websocket,
                )
                raw_response = result.raw_response
                animations = result.animations
                tool_uses = result.tool_uses
                generated_images = result.generated_images
                total_input_tokens = result.input_tokens
                total_output_tokens = result.output_tokens
                total_cache_read_tokens = result.cache_read_tokens
                response_provider = result.provider
                response_model = result.model
                clean_text = result.clean_text
                marks = result.marks
                extracted_self_obs = result.extracted["self_observations"]
                extracted_user_obs = result.extracted["user_observations"]
                extracted_holds = result.extracted["holds"]
                extracted_notes = result.extracted["notes"]
                extracted_intentions = result.extracted["intentions"]
                extracted_stakes = result.extracted["stakes"]
                extracted_tests = result.extracted["tests"]
                extracted_narrations = result.extracted["narrations"]
                extracted_milestones = result.extracted["milestones"]
                extracted_feels = result.extracted["feels"]

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
                                lambda: synthesize(raw_response, provider=tts_provider, voice=tts_voice)
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
