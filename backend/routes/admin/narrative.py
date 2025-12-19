"""
Admin API - Narrative Coherence Routes (Threads & Open Questions)
Provides visibility into the thread/question system for the admin frontend.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from typing import Optional, Dict, List
from pydantic import BaseModel
import anthropic
import json

from .auth import require_auth
from config import ANTHROPIC_API_KEY

router = APIRouter(tags=["admin-narrative"])

# Module-level references - initialized from parent
_thread_manager = None
_question_manager = None
_memory = None
_conversations = None
_token_tracker = None


def init_managers(thread_manager, question_manager, memory=None, conversations=None, token_tracker=None):
    """Initialize manager references."""
    global _thread_manager, _question_manager, _memory, _conversations, _token_tracker
    _thread_manager = thread_manager
    _question_manager = question_manager
    _memory = memory
    _conversations = conversations
    _token_tracker = token_tracker


def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


# ============== Pydantic Models ==============

class CreateThreadRequest(BaseModel):
    title: str
    description: Optional[str] = None
    thread_type: str = "topic"
    user_id: Optional[str] = None
    importance: float = 0.5


class UpdateThreadRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    importance: Optional[float] = None
    thread_type: Optional[str] = None


class ResolveThreadRequest(BaseModel):
    resolution_summary: str


class CreateQuestionRequest(BaseModel):
    question: str
    context: Optional[str] = None
    question_type: str = "curiosity"
    user_id: Optional[str] = None
    importance: float = 0.5


class ResolveQuestionRequest(BaseModel):
    resolution: str


# ============== Thread Endpoints ==============

@router.get("/narrative/threads")
async def get_threads(
    status: Optional[str] = Query(None, description="Filter by status: active, resolved, dormant"),
    thread_type: Optional[str] = Query(None, description="Filter by type: topic, question, project, relational"),
    user_id: Optional[str] = Query(None, description="Filter by user ID (None for shared threads)"),
    include_shared: bool = Query(True, description="Include daemon-wide shared threads"),
    limit: int = Query(20, le=100),
    user: Dict = Depends(require_auth)
):
    """Get conversation threads for narrative coherence tracking."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        if status == "active":
            threads = _thread_manager.get_active_threads(
                user_id=user_id,
                thread_type=thread_type,
                limit=limit,
                include_shared=include_shared
            )
        else:
            # Get all threads with optional filters
            threads = _thread_manager.get_all_threads(
                user_id=user_id,
                status=status,
                thread_type=thread_type,
                limit=limit,
                include_shared=include_shared
            )

        return {
            "threads": threads,
            "count": len(threads)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/narrative/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    user: Dict = Depends(require_auth)
):
    """Get a specific thread with its linked conversations."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        thread = _thread_manager.get_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Get linked conversations
        linked = _thread_manager.get_linked_conversations(thread_id)

        return {
            **thread,
            "linked_conversations": linked
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative/threads")
async def create_thread(
    request: CreateThreadRequest,
    user: Dict = Depends(require_auth)
):
    """Create a new conversation thread."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        thread = _thread_manager.create_thread(
            title=request.title,
            description=request.description,
            thread_type=request.thread_type,
            user_id=request.user_id,
            importance=request.importance
        )
        return thread
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/narrative/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    request: UpdateThreadRequest,
    user: Dict = Depends(require_auth)
):
    """Update a thread's properties."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        thread = _thread_manager.update_thread(
            thread_id=thread_id,
            title=request.title,
            description=request.description,
            importance=request.importance,
            thread_type=request.thread_type
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative/threads/{thread_id}/resolve")
async def resolve_thread(
    thread_id: str,
    request: ResolveThreadRequest,
    user: Dict = Depends(require_auth)
):
    """Mark a thread as resolved."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        thread = _thread_manager.resolve_thread(
            thread_id=thread_id,
            resolution_summary=request.resolution_summary
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative/threads/{thread_id}/reactivate")
async def reactivate_thread(
    thread_id: str,
    user: Dict = Depends(require_auth)
):
    """Reactivate a resolved or dormant thread."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        thread = _thread_manager.reactivate_thread(thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return thread
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/narrative/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: Dict = Depends(require_auth)
):
    """Delete a thread."""
    if not _thread_manager:
        raise HTTPException(status_code=503, detail="Thread manager not initialized")

    try:
        success = _thread_manager.delete_thread(thread_id)
        if not success:
            raise HTTPException(status_code=404, detail="Thread not found")
        return {"status": "deleted", "id": thread_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Question Endpoints ==============

@router.get("/narrative/questions")
async def get_questions(
    status: Optional[str] = Query(None, description="Filter by status: open, resolved, superseded"),
    question_type: Optional[str] = Query(None, description="Filter by type: curiosity, decision, blocker, philosophical"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    include_shared: bool = Query(True, description="Include daemon-wide shared questions"),
    limit: int = Query(20, le=100),
    user: Dict = Depends(require_auth)
):
    """Get open questions for narrative coherence tracking."""
    if not _question_manager:
        raise HTTPException(status_code=503, detail="Question manager not initialized")

    try:
        if status == "open" or status is None:
            questions = _question_manager.get_open_questions(
                user_id=user_id,
                question_type=question_type,
                limit=limit,
                include_shared=include_shared
            )
        else:
            # For resolved/superseded, use a different query
            questions = _question_manager.get_questions_by_type(
                question_type=question_type or "curiosity",
                user_id=user_id,
                include_resolved=(status != "open"),
                limit=limit
            )
            # Filter by status if specified
            if status:
                questions = [q for q in questions if q.get("status") == status]

        return {
            "questions": questions,
            "count": len(questions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/narrative/questions/{question_id}")
async def get_question(
    question_id: str,
    user: Dict = Depends(require_auth)
):
    """Get a specific question."""
    if not _question_manager:
        raise HTTPException(status_code=503, detail="Question manager not initialized")

    try:
        question = _question_manager.get_question(question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        return question
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative/questions")
async def create_question(
    request: CreateQuestionRequest,
    user: Dict = Depends(require_auth)
):
    """Create a new open question."""
    if not _question_manager:
        raise HTTPException(status_code=503, detail="Question manager not initialized")

    try:
        question = _question_manager.add_question(
            question=request.question,
            context=request.context,
            question_type=request.question_type,
            user_id=request.user_id,
            importance=request.importance
        )
        return question
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/narrative/questions/{question_id}/resolve")
async def resolve_question(
    question_id: str,
    request: ResolveQuestionRequest,
    user: Dict = Depends(require_auth)
):
    """Mark a question as resolved."""
    if not _question_manager:
        raise HTTPException(status_code=503, detail="Question manager not initialized")

    try:
        question = _question_manager.resolve_question(
            question_id=question_id,
            resolution=request.resolution
        )
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")
        return question
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/narrative/questions/{question_id}")
async def delete_question(
    question_id: str,
    user: Dict = Depends(require_auth)
):
    """Delete a question."""
    if not _question_manager:
        raise HTTPException(status_code=503, detail="Question manager not initialized")

    try:
        success = _question_manager.delete_question(question_id)
        if not success:
            raise HTTPException(status_code=404, detail="Question not found")
        return {"status": "deleted", "id": question_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Stats Endpoint ==============

@router.get("/narrative/stats")
async def get_narrative_stats(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    user: Dict = Depends(require_auth)
):
    """Get statistics about narrative coherence system."""
    if not _thread_manager or not _question_manager:
        raise HTTPException(status_code=503, detail="Managers not initialized")

    try:
        # Get thread counts by status
        active_threads = _thread_manager.get_active_threads(user_id=user_id, limit=1000)
        all_threads = _thread_manager.get_all_threads(user_id=user_id, limit=1000)

        thread_stats = {
            "total": len(all_threads),
            "active": len([t for t in all_threads if t.get("status") == "active"]),
            "resolved": len([t for t in all_threads if t.get("status") == "resolved"]),
            "dormant": len([t for t in all_threads if t.get("status") == "dormant"]),
            "by_type": {}
        }

        for t in all_threads:
            ttype = t.get("thread_type", "topic")
            thread_stats["by_type"][ttype] = thread_stats["by_type"].get(ttype, 0) + 1

        # Get question counts by status
        open_questions = _question_manager.get_open_questions(user_id=user_id, limit=1000)

        question_stats = {
            "open": len(open_questions),
            "by_type": {}
        }

        for q in open_questions:
            qtype = q.get("question_type", "curiosity")
            question_stats["by_type"][qtype] = question_stats["by_type"].get(qtype, 0) + 1

        return {
            "threads": thread_stats,
            "questions": question_stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Extraction Endpoint ==============

# Track extraction state
_extraction_status = {"running": False, "last_run": None, "results": None}


async def _run_extraction(source_type: str = "journals"):
    """
    Background task to extract threads and questions from existing data.
    Uses Claude to analyze journals and conversation data.
    """
    global _extraction_status
    _extraction_status["running"] = True
    _extraction_status["results"] = None

    try:
        from database import get_db, get_daemon_id
        daemon_id = get_daemon_id()

        # Gather source content
        content_chunks = []

        if source_type in ("journals", "all"):
            # Get recent journals
            with get_db() as conn:
                cursor = conn.execute("""
                    SELECT date, content FROM journals
                    WHERE daemon_id = ?
                    ORDER BY date DESC
                    LIMIT 20
                """, (daemon_id,))
                for row in cursor.fetchall():
                    content_chunks.append({
                        "type": "journal",
                        "date": row[0],
                        "content": row[1][:2000]  # Truncate for token budget
                    })

        if source_type in ("conversations", "all"):
            # Get recent conversation summaries from messages (looking for significant exchanges)
            with get_db() as conn:
                cursor = conn.execute("""
                    SELECT c.id, c.title, c.created_at,
                           (SELECT GROUP_CONCAT(m.content, ' | ')
                            FROM (SELECT content FROM messages
                                  WHERE conversation_id = c.id
                                  ORDER BY timestamp DESC LIMIT 5) m) as recent_content
                    FROM conversations c
                    WHERE c.daemon_id = ?
                    ORDER BY c.created_at DESC
                    LIMIT 30
                """, (daemon_id,))
                for row in cursor.fetchall():
                    if row[3]:  # Has content
                        content_chunks.append({
                            "type": "conversation",
                            "id": row[0],
                            "title": row[1] or "Untitled",
                            "date": row[2],
                            "content": row[3][:1500]
                        })

        if not content_chunks:
            _extraction_status["results"] = {"threads_created": 0, "questions_created": 0, "error": "No content to analyze"}
            _extraction_status["running"] = False
            return

        # Format for LLM analysis
        formatted_content = ""
        for chunk in content_chunks[:15]:  # Limit to 15 chunks for token budget
            if chunk["type"] == "journal":
                formatted_content += f"\n\n=== JOURNAL ({chunk['date']}) ===\n{chunk['content']}"
            else:
                formatted_content += f"\n\n=== CONVERSATION: {chunk['title']} ({chunk['date']}) ===\n{chunk['content']}"

        # Call LLM to extract threads and questions
        client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        extraction_prompt = f"""Analyze this content from Cass's journals and conversations to extract:

1. **Ongoing Threads** - Topics, projects, questions, or relational dynamics that span multiple entries:
   - topic: Recurring subjects of discussion
   - project: Collaborative work or goals being pursued
   - question: Questions being explored over time
   - relational: Patterns in relationships or interactions

2. **Open Questions** - Unresolved curiosities or decisions:
   - curiosity: Things Cass is curious about
   - decision: Choices that need to be made
   - blocker: Issues preventing progress
   - philosophical: Deep questions being contemplated

For each item, provide:
- A concise title (3-8 words)
- A brief description (1-2 sentences)
- The type (from the categories above)
- Importance: high (0.8), medium (0.5), or low (0.3)

CONTENT TO ANALYZE:
{formatted_content}

Respond with ONLY valid JSON in this exact format:
{{
  "threads": [
    {{"title": "...", "description": "...", "thread_type": "topic|project|question|relational", "importance": 0.5}}
  ],
  "questions": [
    {{"question": "...", "context": "...", "question_type": "curiosity|decision|blocker|philosophical", "importance": 0.5}}
  ]
}}

Extract 3-8 threads and 3-8 questions that seem most significant. Focus on things that are:
- Recurring across multiple entries
- Still active/unresolved
- Important to Cass's growth or relationships"""

        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": extraction_prompt}]
        )

        # Track token usage
        if _token_tracker and response.usage:
            _token_tracker.record(
                category="internal",
                operation="narrative_extraction",
                provider="anthropic",
                model="claude-haiku-4-5-20251001",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens
            )

        # Parse response
        response_text = response.content[0].text.strip()

        # Handle markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        extracted = json.loads(response_text.strip())

        threads_created = 0
        questions_created = 0

        # Get existing threads/questions to avoid duplicates
        existing_threads = _thread_manager.get_all_threads(limit=100) if _thread_manager else []
        existing_thread_titles = {t.get("title", "").lower() for t in existing_threads}

        existing_questions = _question_manager.get_open_questions(limit=100) if _question_manager else []
        existing_question_texts = {q.get("question", "").lower() for q in existing_questions}

        # Create threads
        for thread_data in extracted.get("threads", []):
            title = thread_data.get("title", "")
            if title.lower() not in existing_thread_titles and _thread_manager:
                _thread_manager.create_thread(
                    title=title,
                    description=thread_data.get("description"),
                    thread_type=thread_data.get("thread_type", "topic"),
                    importance=thread_data.get("importance", 0.5)
                )
                threads_created += 1

        # Create questions
        for q_data in extracted.get("questions", []):
            question = q_data.get("question", "")
            if question.lower() not in existing_question_texts and _question_manager:
                _question_manager.add_question(
                    question=question,
                    context=q_data.get("context"),
                    question_type=q_data.get("question_type", "curiosity"),
                    importance=q_data.get("importance", 0.5)
                )
                questions_created += 1

        from datetime import datetime
        _extraction_status["results"] = {
            "threads_created": threads_created,
            "questions_created": questions_created,
            "chunks_analyzed": len(content_chunks)
        }
        _extraction_status["last_run"] = datetime.now().isoformat()

    except Exception as e:
        import traceback
        _extraction_status["results"] = {"error": str(e), "traceback": traceback.format_exc()}
    finally:
        _extraction_status["running"] = False


@router.post("/narrative/extract")
async def extract_from_history(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Source to extract from: journals, conversations, or all"),
    user: Dict = Depends(require_auth)
):
    """
    Extract threads and questions from existing journals and conversations.
    Runs in background and uses LLM to identify narrative threads.
    """
    if _extraction_status["running"]:
        return {"status": "already_running", "message": "Extraction is already in progress"}

    background_tasks.add_task(_run_extraction, source)
    return {"status": "started", "source": source}


@router.get("/narrative/extract/status")
async def get_extraction_status(
    user: Dict = Depends(require_auth)
):
    """Get the status of the last extraction run."""
    return _extraction_status
