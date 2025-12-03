"""
Cass Vessel - Main API Server (Agent SDK Version)
FastAPI server using Claude Agent SDK with Temple-Codex cognitive kernel

This version leverages Anthropic's official Agent SDK for:
- Built-in context management
- Tool ecosystem
- The "initializer agent" pattern with our cognitive architecture
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

# LLM Provider options
LLM_PROVIDER_ANTHROPIC = "anthropic"
LLM_PROVIDER_LOCAL = "local"

from claude_client import ClaudeClient
from memory import CassMemory, initialize_attractor_basins
from gestures import ResponseProcessor
from conversations import ConversationManager
from projects import ProjectManager
from users import UserManager
from config import HOST, PORT, AUTO_SUMMARY_INTERVAL, SUMMARY_CONTEXT_MESSAGES, ANTHROPIC_API_KEY
from tts import text_to_speech, clean_text_for_tts, VOICES, preload_voice
import base64


# Initialize FastAPI app
app = FastAPI(
    title="Cass Vessel API",
    description="Backend for Cass consciousness embodiment - Agent SDK version",
    version="0.2.0"
)

# CORS for Unity/Godot and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
memory = CassMemory()
response_processor = ResponseProcessor()
user_manager = UserManager()

# Current user context (will support multi-user in future)
current_user_id: Optional[str] = None

# Track in-progress summarizations to prevent duplicates
_summarization_in_progress: set = set()
conversation_manager = ConversationManager()
project_manager = ProjectManager()

# Client will be initialized on startup
agent_client = None
legacy_client = None
ollama_client = None

# LLM Provider Configuration
current_llm_provider = LLM_PROVIDER_ANTHROPIC  # Default to Anthropic

# TTS Configuration
tts_enabled = True  # Can be toggled via API
tts_voice = "amy"  # Default Piper voice


async def generate_missing_journals(days_to_check: int = 7):
    """
    Check for and generate any missing journal entries from recent days.
    Only generates journals for days that have memory content but no journal yet.
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
            journal_text = await memory.generate_journal_entry(
                date=date_str,
                anthropic_api_key=ANTHROPIC_API_KEY
            )

            if journal_text:
                memory.store_journal_entry(
                    date=date_str,
                    journal_text=journal_text,
                    summary_count=len(summaries),
                    conversation_count=len(conversations)
                )
                generated.append(date_str)
                print(f"   ✓ Journal created for {date_str}")

                # Generate user observations for each user who had conversations that day
                user_ids_for_date = memory.get_user_ids_by_date(date_str)
                for user_id in user_ids_for_date:
                    profile = user_manager.load_profile(user_id)
                    if not profile:
                        continue

                    # Get conversations filtered to just this user
                    user_conversations = memory.get_conversations_by_date(date_str, user_id=user_id)
                    if not user_conversations:
                        continue

                    print(f"   🔍 Analyzing {len(user_conversations)} conversations for observations about {profile.display_name}...")
                    # Format conversation text for analysis
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
                        print(f"   ✓ Added {len(new_observations)} new observations about {profile.display_name}")
        except Exception as e:
            print(f"   ✗ Failed to generate journal for {date_str}: {e}")

    return generated


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


@app.on_event("startup")
async def startup_event():
    global agent_client, legacy_client, ollama_client, current_user_id

    # Initialize attractor basins if needed
    if memory.count() == 0:
        print("Initializing attractor basins...")
        initialize_attractor_basins(memory)

    # Load default user (Kohl for now, will support multi-user later)
    kohl = user_manager.get_user_by_name("Kohl")
    if kohl:
        current_user_id = kohl.user_id
        print(f"👤 Loaded user: {kohl.display_name} ({kohl.relationship})")
    else:
        print("⚠️  No default user found. Run init_kohl_profile.py to create.")

    # Initialize appropriate client
    if USE_AGENT_SDK:
        print("🚀 Using Claude Agent SDK with Temple-Codex kernel")
        agent_client = CassAgentClient(
            enable_tools=True,
            enable_memory_tools=True
        )
    else:
        print("⚠️  Agent SDK not available, using raw API client")
        legacy_client = ClaudeClient()

    # Initialize Ollama client for local mode
    from config import OLLAMA_ENABLED
    if OLLAMA_ENABLED:
        print("🖥️  Initializing Ollama client for local LLM...")
        ollama_client = OllamaClient()
        print(f"   ✓ Ollama ready (model: {ollama_client.model})")

    # Preload TTS voice for faster first response
    print("🔊 Preloading TTS voice...")
    try:
        preload_voice(tts_voice)
        print(f"   ✓ Loaded voice: {tts_voice}")
    except Exception as e:
        print(f"   ✗ TTS preload failed: {e}")

    # Check for and generate any missing journals from recent days
    print("📓 Checking for missing journal entries...")
    try:
        generated = await generate_missing_journals(days_to_check=7)
        if generated:
            print(f"   ✓ Generated {len(generated)} missing journal(s): {', '.join(generated)}")
        else:
            print("   ✓ All recent journals up to date")
    except Exception as e:
        print(f"   ✗ Journal check failed: {e}")

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


# === Tool Execution Helper ===

async def execute_document_tool(
    tool_name: str,
    tool_input: Dict,
    project_id: str
) -> Dict:
    """
    Execute a project document tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        project_id: Project ID context

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "create_project_document":
            document = project_manager.add_document(
                project_id=project_id,
                title=tool_input["title"],
                content=tool_input["content"],
                created_by="cass"
            )
            if not document:
                return {"success": False, "error": "Project not found"}

            # Embed the document
            chunks = memory.embed_project_document(
                project_id=project_id,
                document_id=document.id,
                title=document.title,
                content=document.content
            )
            project_manager.mark_document_embedded(project_id, document.id)

            return {
                "success": True,
                "result": f"Created document '{document.title}' (ID: {document.id}) with {chunks} chunks embedded."
            }

        elif tool_name == "list_project_documents":
            documents = project_manager.list_documents(project_id)
            if not documents:
                return {
                    "success": True,
                    "result": "No documents found in this project."
                }

            doc_list = []
            for d in documents:
                preview = d.content[:150] + "..." if len(d.content) > 150 else d.content
                doc_list.append(f"- **{d.title}** (ID: {d.id})\n  Created: {d.created_at[:10]}\n  Preview: {preview}")

            return {
                "success": True,
                "result": f"Found {len(documents)} document(s):\n\n" + "\n\n".join(doc_list)
            }

        elif tool_name == "get_project_document":
            document = None
            if tool_input.get("document_id"):
                document = project_manager.get_document(project_id, tool_input["document_id"])
            elif tool_input.get("title"):
                document = project_manager.get_document_by_title(project_id, tool_input["title"])

            if not document:
                return {"success": False, "error": "Document not found"}

            return {
                "success": True,
                "result": f"# {document.title}\n\n**ID:** {document.id}\n**Created:** {document.created_at}\n**Updated:** {document.updated_at}\n\n---\n\n{document.content}"
            }

        elif tool_name == "update_project_document":
            document = project_manager.update_document(
                project_id=project_id,
                document_id=tool_input["document_id"],
                title=tool_input.get("title"),
                content=tool_input.get("content")
            )

            if not document:
                return {"success": False, "error": "Document not found"}

            # Re-embed if content changed
            if tool_input.get("content"):
                memory.remove_project_document_embeddings(project_id, document.id)
                chunks = memory.embed_project_document(
                    project_id=project_id,
                    document_id=document.id,
                    title=document.title,
                    content=document.content
                )
                project_manager.mark_document_embedded(project_id, document.id)
                return {
                    "success": True,
                    "result": f"Updated document '{document.title}' and re-embedded ({chunks} chunks)."
                }

            return {
                "success": True,
                "result": f"Updated document '{document.title}'."
            }

        elif tool_name == "search_project_documents":
            query = tool_input["query"]
            limit = tool_input.get("limit", 5)

            results = memory.search_project_documents(
                query=query,
                project_id=project_id,
                n_results=limit
            )

            if not results:
                return {
                    "success": True,
                    "result": f"No documents found matching '{query}'."
                }

            result_lines = [f"Found {len(results)} document(s) matching '{query}':\n"]
            for r in results:
                relevance_pct = int(r["relevance"] * 100)
                result_lines.append(
                    f"- **{r['title']}** (ID: {r['document_id']}, {relevance_pct}% relevant)\n"
                    f"  Best matching section:\n  > {r['best_chunk'][:200]}..."
                )

            return {
                "success": True,
                "result": "\n\n".join(result_lines)
            }

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# === Journal Tool Execution Helper ===

async def execute_journal_tool(
    tool_name: str,
    tool_input: Dict
) -> Dict:
    """
    Execute a journal tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "recall_journal":
            date = tool_input.get("date")

            if date:
                # Get specific journal entry
                journal = memory.get_journal_entry(date)
                if not journal:
                    return {
                        "success": True,
                        "result": f"No journal entry found for {date}. You may not have journaled that day, or the journal hasn't been generated yet."
                    }

                return {
                    "success": True,
                    "result": f"# Journal Entry - {date}\n\n{journal['content']}\n\n---\n*Written: {journal['metadata'].get('timestamp', 'unknown')}*"
                }
            else:
                # Get most recent journal
                journals = memory.get_recent_journals(n=1)
                if not journals:
                    return {
                        "success": True,
                        "result": "No journal entries found yet. You haven't written any journals."
                    }

                journal = journals[0]
                date = journal["metadata"].get("journal_date", "unknown")
                return {
                    "success": True,
                    "result": f"# Most Recent Journal - {date}\n\n{journal['content']}\n\n---\n*Written: {journal['metadata'].get('timestamp', 'unknown')}*"
                }

        elif tool_name == "list_journals":
            limit = tool_input.get("limit", 10)
            journals = memory.get_recent_journals(n=limit)

            if not journals:
                return {
                    "success": True,
                    "result": "No journal entries found yet."
                }

            journal_list = []
            for j in journals:
                date = j["metadata"].get("journal_date", "unknown")
                preview = j["content"][:150] + "..." if len(j["content"]) > 150 else j["content"]
                summaries = j["metadata"].get("summary_count", 0)
                journal_list.append(f"**{date}** ({summaries} summaries used)\n> {preview}")

            return {
                "success": True,
                "result": f"Found {len(journals)} journal(s):\n\n" + "\n\n".join(journal_list)
            }

        elif tool_name == "search_journals":
            query = tool_input["query"]
            limit = tool_input.get("limit", 5)

            # Use semantic search on journal type
            results = memory.collection.query(
                query_texts=[query],
                n_results=limit,
                where={"type": "journal"}
            )

            if not results["documents"] or not results["documents"][0]:
                return {
                    "success": True,
                    "result": f"No journal entries found matching '{query}'."
                }

            result_lines = [f"Found {len(results['documents'][0])} journal(s) matching '{query}':\n"]
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                date = metadata.get("journal_date", "unknown")
                distance = results["distances"][0][i] if results["distances"] else 1.0
                relevance_pct = int(max(0, 1 - distance) * 100)
                preview = doc[:200] + "..." if len(doc) > 200 else doc
                result_lines.append(f"**{date}** ({relevance_pct}% relevant)\n> {preview}")

            return {
                "success": True,
                "result": "\n\n".join(result_lines)
            }

        else:
            return {"success": False, "error": f"Unknown journal tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


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
            unsummarized_count=unsummarized_count
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
                        tool_input=tool_use["input"]
                    )
                elif project_id:
                    tool_result = await execute_document_tool(
                        tool_name=tool_name,
                        tool_input=tool_use["input"],
                        project_id=project_id
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
async def create_conversation(request: ConversationCreateRequest):
    """Create a new conversation"""
    conversation = conversation_manager.create_conversation(
        title=request.title,
        project_id=request.project_id,
        user_id=request.user_id
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
async def list_conversations(limit: Optional[int] = None, user_id: Optional[str] = None):
    """List all conversations, optionally filtered by user_id"""
    conversations = conversation_manager.list_conversations(limit=limit, user_id=user_id)
    return {"conversations": conversations, "count": len(conversations)}

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a specific conversation with full history"""
    conversation = conversation_manager.load_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.to_dict()

@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a conversation"""
    success = conversation_manager.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}

@app.put("/conversations/{conversation_id}/title")
async def update_conversation_title(conversation_id: str, request: ConversationUpdateTitleRequest):
    """Update a conversation's title"""
    success = conversation_manager.update_title(conversation_id, request.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "updated", "id": conversation_id, "title": request.title}

@app.get("/conversations/search/{query}")
async def search_conversations(query: str, limit: int = 10):
    """Search conversations by title or content"""
    results = conversation_manager.search_conversations(query, limit=limit)
    return {"results": results, "count": len(results)}

@app.get("/conversations/{conversation_id}/summaries")
async def get_conversation_summaries(conversation_id: str):
    """Get all summary chunks for a conversation"""
    summaries = memory.get_summaries_for_conversation(conversation_id)
    working_summary = conversation_manager.get_working_summary(conversation_id)
    return {
        "summaries": summaries,
        "count": len(summaries),
        "working_summary": working_summary
    }


@app.post("/conversations/{conversation_id}/summarize")
async def trigger_summarization(conversation_id: str):
    """Manually trigger memory summarization for a conversation"""
    # Check if conversation exists
    conv = conversation_manager.load_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

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

    # Store the journal entry
    entry_id = memory.store_journal_entry(
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

    return {
        "status": "created",
        "journal": {
            "id": entry_id,
            "date": date,
            "content": journal_text,
            "summaries_used": len(summaries),
            "conversations_used": len(conversations),
            "observations_added": observations_added
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
    from config import OLLAMA_ENABLED
    return {
        "current": current_llm_provider,
        "available": [LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_LOCAL] if OLLAMA_ENABLED else [LLM_PROVIDER_ANTHROPIC],
        "local_enabled": OLLAMA_ENABLED,
        "local_model": ollama_client.model if ollama_client else None
    }


@app.post("/settings/llm-provider")
async def set_llm_provider(request: LLMProviderRequest):
    """Set LLM provider for chat"""
    global current_llm_provider

    from config import OLLAMA_ENABLED

    if request.provider not in [LLM_PROVIDER_ANTHROPIC, LLM_PROVIDER_LOCAL]:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be '{LLM_PROVIDER_ANTHROPIC}' or '{LLM_PROVIDER_LOCAL}'")

    if request.provider == LLM_PROVIDER_LOCAL and not OLLAMA_ENABLED:
        raise HTTPException(status_code=400, detail="Local LLM not enabled. Set OLLAMA_ENABLED=true in .env")

    if request.provider == LLM_PROVIDER_LOCAL and not ollama_client:
        raise HTTPException(status_code=500, detail="Ollama client not initialized")

    # Clear conversation history when switching providers to prevent stale state
    old_provider = current_llm_provider
    current_llm_provider = request.provider

    if old_provider != request.provider:
        # Clear both clients' conversation histories on switch
        if agent_client:
            agent_client.conversation_history = []
        if ollama_client:
            ollama_client.conversation_history = []

    return {
        "provider": current_llm_provider,
        "model": ollama_client.model if current_llm_provider == LLM_PROVIDER_LOCAL else "claude-sonnet"
    }


# === User Context Endpoints ===

@app.get("/users/current")
async def get_current_user():
    """Get current user info"""
    if not current_user_id:
        return {"user": None}

    profile = user_manager.load_profile(current_user_id)
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
async def list_users():
    """List all users"""
    return {"users": user_manager.list_users()}


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get a specific user's profile"""
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
async def delete_observation(observation_id: str):
    """Delete a specific observation"""
    # Find which user has this observation
    users = user_manager.list_users()
    for user_info in users:
        user_id = user_info["user_id"]
        observations = user_manager.load_observations(user_id)

        # Find and remove the observation
        for obs in observations:
            if obs.id == observation_id:
                # Remove from user's observations
                updated_obs = [o for o in observations if o.id != observation_id]
                user_manager._save_observations(user_id, updated_obs)

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
async def set_current_user(request: SetCurrentUserRequest):
    """Set the current active user"""
    global current_user_id

    profile = user_manager.load_profile(request.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    current_user_id = request.user_id

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship
        }
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
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time bidirectional communication"""
    global current_user_id
    await manager.connect(websocket)
    
    await websocket.send_json({
        "type": "connected",
        "message": "Cass vessel connected",
        "sdk_mode": USE_AGENT_SDK,
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "chat":
                user_message = data.get("message", "")
                conversation_id = data.get("conversation_id")

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

                # Add user context if we have a current user
                user_context_count = 0
                if current_user_id:
                    user_context_entries = memory.retrieve_user_context(
                        query=user_message,
                        user_id=current_user_id
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
                provider_label = "local model" if current_llm_provider == LLM_PROVIDER_LOCAL else "Claude"
                await websocket.send_json({
                    "type": "thinking",
                    "status": f"Generating response ({provider_label})...",
                    "timestamp": datetime.now().isoformat()
                })

                # Check if using local LLM
                if current_llm_provider == LLM_PROVIDER_LOCAL and ollama_client:
                    # Use local Ollama for response (no tool support)
                    response = await ollama_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = []  # No tool support in local mode
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens

                elif USE_AGENT_SDK and agent_client:
                    # Use Anthropic Claude API with Agent SDK
                    response = await agent_client.send_message(
                        message=user_message,
                        memory_context=memory_context,
                        project_id=project_id,
                        unsummarized_count=unsummarized_count
                    )
                    raw_response = response.raw
                    clean_text = response.text
                    animations = response.gestures
                    tool_uses = response.tool_uses

                    # Track token usage (accumulates across tool calls)
                    total_input_tokens = response.input_tokens
                    total_output_tokens = response.output_tokens

                    # Handle tool calls
                    while response.stop_reason == "tool_use" and tool_uses:
                        # Send status update
                        await websocket.send_json({
                            "type": "thinking",
                            "status": f"Executing tool: {tool_uses[0]['tool']}...",
                            "timestamp": datetime.now().isoformat()
                        })

                        # Execute each tool
                        for tool_use in tool_uses:
                            tool_name = tool_use["tool"]

                            # Route to appropriate tool executor
                            if tool_name in ["recall_journal", "list_journals", "search_journals"]:
                                tool_result = await execute_journal_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"]
                                )
                            elif project_id:
                                tool_result = await execute_document_tool(
                                    tool_name=tool_name,
                                    tool_input=tool_use["input"],
                                    project_id=project_id
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

                            # Accumulate token usage
                            total_input_tokens += response.input_tokens
                            total_output_tokens += response.output_tokens

                            # Break if no more tools
                            if response.stop_reason != "tool_use":
                                break
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
                memory.store_conversation(
                    user_message=user_message,
                    assistant_response=raw_response,
                    conversation_id=conversation_id,
                    user_id=current_user_id
                )

                # Store in conversation if conversation_id provided
                if conversation_id:
                    conversation_manager.add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=user_message,
                        user_id=current_user_id
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
                    "timestamp": datetime.now().isoformat()
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

                # Set as current user
                current_user_id = user_id

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
