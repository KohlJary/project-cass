"""
Conversation REST API routes
Conversation CRUD and management endpoints
"""
import asyncio
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

# Import auth dependency directly - it's already configured
from auth import get_current_user

router = APIRouter(tags=["conversations"])

# Dependencies - set by init_conversation_routes
_conversation_manager = None
_memory = None
_user_manager = None
_self_manager = None
_marker_store = None
_token_tracker = None
_summarization_in_progress: set = None
_generate_and_store_summary = None


def init_conversation_routes(
    conversation_manager,
    memory,
    user_manager,
    self_manager,
    marker_store,
    token_tracker,
    summarization_in_progress: set,
    generate_and_store_summary
):
    """Initialize the routes with dependencies"""
    global _conversation_manager, _memory, _user_manager, _self_manager
    global _marker_store, _token_tracker
    global _summarization_in_progress, _generate_and_store_summary

    _conversation_manager = conversation_manager
    _memory = memory
    _user_manager = user_manager
    _self_manager = self_manager
    _marker_store = marker_store
    _token_tracker = token_tracker
    _summarization_in_progress = summarization_in_progress
    _generate_and_store_summary = generate_and_store_summary


# Request models
class ConversationCreateRequest(BaseModel):
    title: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None


class ConversationUpdateTitleRequest(BaseModel):
    title: str


class ConversationAssignProjectRequest(BaseModel):
    project_id: Optional[str] = None  # None to unassign


class ExcludeMessageRequest(BaseModel):
    message_timestamp: str
    exclude: bool = True  # True to exclude, False to un-exclude


# Helper functions

def _verify_conversation_access(conversation_id: str, current_user: str):
    """Helper to verify user has access to a conversation"""
    conversation = _conversation_manager.load_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Check ownership if conversation has a user_id
    conv_user_id = conversation.user_id
    if conv_user_id and conv_user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized to access this conversation")
    return conversation


# Endpoints

@router.post("/conversations/new")
async def create_conversation(
    request: Request,
    body: ConversationCreateRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new conversation"""
    user_id = body.user_id or current_user
    conversation = _conversation_manager.create_conversation(
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


@router.get("/conversations")
async def list_conversations(
    request: Request,
    limit: Optional[int] = None,
    user_id: Optional[str] = None,
    current_user: str = Depends(get_current_user)
):
    """List conversations for the authenticated user"""
    # Rate limiting: 60/minute
    filter_user_id = user_id if user_id else current_user
    if user_id and user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other users' conversations")
    conversations = _conversation_manager.list_conversations(limit=limit, user_id=filter_user_id)
    return {"conversations": conversations, "count": len(conversations)}


@router.get("/conversations/search/{query}")
async def search_conversations(
    query: str,
    limit: int = 10,
    current_user: str = Depends(get_current_user)
):
    """Search conversations by title or content"""
    results = _conversation_manager.search_conversations(query, limit=limit * 2)
    filtered = [r for r in results if r.get("user_id") == current_user or r.get("user_id") is None]
    return {"results": filtered[:limit], "count": len(filtered[:limit])}


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get a specific conversation with full history"""
    conversation = _verify_conversation_access(conversation_id, current_user)
    return conversation.to_dict()


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a conversation"""
    _verify_conversation_access(conversation_id, current_user)
    success = _conversation_manager.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}


@router.put("/conversations/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    request: ConversationUpdateTitleRequest,
    current_user: str = Depends(get_current_user)
):
    """Update a conversation's title"""
    _verify_conversation_access(conversation_id, current_user)
    success = _conversation_manager.update_title(conversation_id, request.title)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "updated", "id": conversation_id, "title": request.title}


@router.get("/conversations/{conversation_id}/summaries")
async def get_conversation_summaries(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get all summary chunks for a conversation"""
    _verify_conversation_access(conversation_id, current_user)
    if _memory is None:
        raise HTTPException(status_code=503, detail="Memory system initializing")
    summaries = _memory.get_summaries_for_conversation(conversation_id)
    working_summary = _conversation_manager.get_working_summary(conversation_id)
    return {
        "summaries": summaries,
        "count": len(summaries),
        "working_summary": working_summary
    }


@router.get("/conversations/{conversation_id}/observations")
async def get_conversation_observations(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get all observations (user and self) and marks made during a conversation"""
    _verify_conversation_access(conversation_id, current_user)

    # Get user observations for this conversation
    user_observations = []
    if _user_manager:
        all_user_obs = _user_manager.load_observations(current_user)
        for obs in all_user_obs:
            if obs.source_conversation_id == conversation_id:
                user_observations.append(obs.to_dict())

    # Get self-observations for this conversation
    self_observations = []
    if _self_manager:
        all_self_obs = _self_manager.load_observations()
        for obs in all_self_obs:
            if obs.source_conversation_id == conversation_id:
                self_observations.append(obs.to_dict())

    # Get marks for this conversation
    marks = []
    if _marker_store:
        marks = _marker_store.get_marks_by_conversation(conversation_id)

    return {
        "user_observations": user_observations,
        "self_observations": self_observations,
        "marks": marks,
        "user_count": len(user_observations),
        "self_count": len(self_observations),
        "marks_count": len(marks)
    }


@router.post("/conversations/{conversation_id}/summarize")
async def trigger_summarization(
    conversation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Manually trigger memory summarization for a conversation"""
    _verify_conversation_access(conversation_id, current_user)

    if _summarization_in_progress is None:
        raise HTTPException(status_code=503, detail="Summarization system not initialized")

    if conversation_id in _summarization_in_progress:
        return {
            "status": "in_progress",
            "message": "Summarization already in progress for this conversation"
        }

    if _memory is None:
        raise HTTPException(status_code=503, detail="Memory system initializing")

    asyncio.create_task(_generate_and_store_summary(
        conversation_id,
        memory=_memory,
        conversation_manager=_conversation_manager,
        token_tracker=_token_tracker,
        force=True
    ))

    return {
        "status": "started",
        "message": f"Summarization started for conversation {conversation_id}"
    }


@router.post("/conversations/{conversation_id}/exclude")
async def exclude_message(conversation_id: str, request: ExcludeMessageRequest):
    """
    Exclude a message from summarization and context retrieval.
    Also removes the message from ChromaDB embeddings if excluding.
    """
    conv = _conversation_manager.load_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg = _conversation_manager.get_message_by_timestamp(conversation_id, request.message_timestamp)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    success = _conversation_manager.exclude_message(
        conversation_id,
        request.message_timestamp,
        request.exclude
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update message")

    embeddings_removed = 0
    if request.exclude and _memory is not None:
        try:
            results = _memory.collection.get(
                where={
                    "$and": [
                        {"conversation_id": conversation_id},
                        {"type": "conversation"}
                    ]
                },
                include=["documents", "metadatas"]
            )

            ids_to_remove = []
            for i, doc in enumerate(results.get("documents", [])):
                if msg.content[:100] in doc:
                    ids_to_remove.append(results["ids"][i])

            if ids_to_remove:
                _memory.collection.delete(ids=ids_to_remove)
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


@router.put("/conversations/{conversation_id}/project")
async def assign_conversation_to_project(
    conversation_id: str,
    request: ConversationAssignProjectRequest
):
    """Assign a conversation to a project or remove from project"""
    success = _conversation_manager.assign_to_project(
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
