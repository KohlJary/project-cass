"""
Admin API - Memory, Journal & Conversation Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict, List
from pydantic import BaseModel

from .auth import require_admin, require_auth

router = APIRouter(tags=["admin-memory"])

# Module-level references - initialized from parent
_memory = None
_conversations = None
_users = None


def init_managers(memory, conversations, users):
    """Initialize manager references."""
    global _memory, _conversations, _users
    _memory = memory
    _conversations = conversations
    _users = users


def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


# ============== Pydantic Models ==============

class AssignUserRequest(BaseModel):
    user_id: Optional[str] = None


# ============== Memory Endpoints ==============

@router.get("/memory")
async def get_memories(
    type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    user: Dict = Depends(require_auth)
):
    """Get all memories, optionally filtered by type"""
    if not _memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        # Query ChromaDB
        collection = _memory.collection

        where_filter = {"type": type} if type else None

        results = collection.get(
            where=where_filter,
            include=["documents", "metadatas"],
            limit=limit,
            offset=offset
        )

        memories = []
        for i, doc_id in enumerate(results["ids"]):
            memories.append({
                "id": doc_id,
                "content": results["documents"][i] if results["documents"] else None,
                "metadata": results["metadatas"][i] if results["metadatas"] else {},
                "type": results["metadatas"][i].get("type") if results["metadatas"] else None,
                "timestamp": results["metadatas"][i].get("timestamp") if results["metadatas"] else None
            })

        # Sort by timestamp descending
        memories.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        return {"memories": memories, "count": len(memories)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/search")
async def search_memories(
    query: str,
    limit: int = Query(default=10, le=50),
    user: Dict = Depends(require_auth)
):
    """Semantic search across memories"""
    if not _memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        results = _memory.collection.query(
            query_texts=[query],
            n_results=limit,
            include=["documents", "metadatas", "distances"]
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # Convert distance to similarity (ChromaDB uses L2 distance)
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 / (1 + distance)  # Convert to 0-1 range

                search_results.append({
                    "id": doc_id,
                    "content": results["documents"][0][i] if results["documents"] else None,
                    "type": results["metadatas"][0][i].get("type") if results["metadatas"] else None,
                    "similarity": similarity,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {}
                })

        return {"results": search_results, "query": query}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/vectors")
async def get_memory_vectors(
    limit: int = Query(default=100, le=500),
    type: Optional[str] = None,
    user: Dict = Depends(require_auth)
):
    """Get memory embeddings for visualization (2D projection via PCA)"""
    if not _memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        import numpy as np

        collection = _memory.collection
        where_filter = {"type": type} if type else None

        results = collection.get(
            where=where_filter,
            include=["documents", "metadatas", "embeddings"],
            limit=limit
        )

        # Check if we have embeddings (handle both None and empty list cases)
        if results["embeddings"] is None or len(results["embeddings"]) < 2:
            return {"vectors": [], "message": "Not enough data for visualization"}

        embeddings = np.array(results["embeddings"])

        # Simple PCA for 2D projection
        # Center the data
        centered = embeddings - np.mean(embeddings, axis=0)
        # Compute covariance matrix
        cov = np.cov(centered.T)
        # Get eigenvectors
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        # Sort by eigenvalue descending
        idx = np.argsort(eigenvalues)[::-1]
        eigenvectors = eigenvectors[:, idx]
        # Project to 2D
        projection = centered @ eigenvectors[:, :2]

        # Normalize to 0-1 range for visualization
        x_min, x_max = projection[:, 0].min(), projection[:, 0].max()
        y_min, y_max = projection[:, 1].min(), projection[:, 1].max()

        vectors = []
        for i, doc_id in enumerate(results["ids"]):
            x = (projection[i, 0] - x_min) / (x_max - x_min + 1e-8)
            y = (projection[i, 1] - y_min) / (y_max - y_min + 1e-8)

            vectors.append({
                "id": doc_id,
                "x": float(x),
                "y": float(y),
                "type": results["metadatas"][i].get("type") if results["metadatas"] else None,
                "preview": (results["documents"][i][:100] + "...") if results["documents"] and len(results["documents"][i]) > 100 else results["documents"][i],
            })

        return {"vectors": vectors, "count": len(vectors)}

    except ImportError:
        raise HTTPException(status_code=500, detail="NumPy not available for vector visualization")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/stats")
async def get_memory_stats(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch stats for"),
    admin: Dict = Depends(require_admin)
):
    """Get memory statistics for a daemon"""
    from database import get_db

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get journal count from database
            journal_cursor = conn.execute("""
                SELECT COUNT(*) FROM journals WHERE daemon_id = ?
            """, (effective_daemon_id,))
            journal_count = journal_cursor.fetchone()[0] or 0

            # Get self-observation count from database
            obs_cursor = conn.execute("""
                SELECT COUNT(*) FROM self_observations WHERE daemon_id = ?
            """, (effective_daemon_id,))
            self_obs_count = obs_cursor.fetchone()[0] or 0

            # Get dream count from database
            dream_cursor = conn.execute("""
                SELECT COUNT(*) FROM dreams WHERE daemon_id = ?
            """, (effective_daemon_id,))
            dream_count = dream_cursor.fetchone()[0] or 0

            # ChromaDB stats (not daemon-filtered currently)
            chromadb_total = 0
            type_counts = {}
            if _memory:
                collection = _memory.collection
                chromadb_total = collection.count()

                for mem_type in ["summary", "observation", "user_observation", "per_user_journal", "attractor_marker", "project_document"]:
                    try:
                        results = collection.get(where={"type": mem_type}, include=[])
                        type_counts[mem_type] = len(results["ids"])
                    except:
                        type_counts[mem_type] = 0

            type_counts["journal"] = journal_count
            type_counts["self_observation"] = self_obs_count
            type_counts["dream"] = dream_count

            return {
                "total_memories": chromadb_total + self_obs_count + journal_count + dream_count,
                "by_type": type_counts,
                "journals": journal_count
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Journal Endpoints ==============

@router.get("/journals")
async def get_all_journals(
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID"),
    limit: int = Query(default=30, le=100),
    user: Dict = Depends(require_auth)
):
    """Get all journal entries"""
    from database import get_db

    try:
        effective_daemon_id = get_effective_daemon_id(daemon_id)

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT date, content, themes_json, created_at
                FROM journals
                WHERE daemon_id = ?
                ORDER BY date DESC
                LIMIT ?
            """, (effective_daemon_id, limit))

            journal_list = []
            for row in cursor.fetchall():
                # Generate a summary from first ~100 chars of content
                content = row[1] or ""
                summary = content[:100] + "..." if len(content) > 100 else content

                journal_list.append({
                    "date": row[0],
                    "summary": summary,
                    "locked": False  # Could add locked column later
                })

        return {"journals": journal_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journals/{date}")
async def get_journal_by_date(
    date: str,
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID"),
    user: Dict = Depends(require_auth)
):
    """Get a specific journal entry by date"""
    from database import get_db

    try:
        effective_daemon_id = get_effective_daemon_id(daemon_id)

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, date, content, themes_json, created_at
                FROM journals
                WHERE daemon_id = ? AND date = ?
            """, (effective_daemon_id, date))

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Journal not found")

            return {
                "date": row[1],
                "content": row[2],
                "metadata": {
                    "themes": row[3],
                    "created_at": row[4]
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journals/calendar")
async def get_journal_calendar(
    year: int = Query(...),
    month: int = Query(...),
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID"),
    user: Dict = Depends(require_auth)
):
    """Get journal dates for a specific month (for calendar view)"""
    from database import get_db

    try:
        effective_daemon_id = get_effective_daemon_id(daemon_id)
        month_str = f"{year}-{month:02d}"

        with get_db() as conn:
            cursor = conn.execute("""
                SELECT date FROM journals
                WHERE daemon_id = ? AND date LIKE ?
                ORDER BY date
            """, (effective_daemon_id, f"{month_str}%"))

            dates_with_journals = [row[0] for row in cursor.fetchall()]

        return {
            "year": year,
            "month": month,
            "dates": dates_with_journals
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Conversation Endpoints ==============

@router.get("/conversations")
async def get_all_conversations(
    user_id: Optional[str] = None,
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID"),
    limit: int = Query(default=50, le=200),
    user: Dict = Depends(require_auth)
):
    """Get all conversations"""
    from database import get_db

    try:
        effective_daemon_id = get_effective_daemon_id(daemon_id)

        with get_db() as conn:
            # Build query with optional user filter
            query = """
                SELECT c.id, c.title, c.created_at, c.updated_at, c.user_id,
                       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as message_count
                FROM conversations c
                WHERE c.daemon_id = ?
            """
            params = [effective_daemon_id]

            if user_id:
                query += " AND c.user_id = ?"
                params.append(user_id)

            query += " ORDER BY c.updated_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            columns = ["id", "title", "created_at", "updated_at", "user_id", "message_count"]
            conv_list = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return {"conversations": conv_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/system")
async def get_system_conversations(limit: int = Query(default=50, le=200), user: Dict = Depends(require_auth)):
    """Get conversations from system users (like Daedalus).

    Returns conversations where user_id belongs to a user with relationship='system'.
    This allows admins to view Daedalus-Cass communication history.
    """
    if not _conversations or not _users:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        # Get system user IDs
        all_users = _users.list_users()
        system_user_ids = set()
        for u in all_users:
            profile = _users.load_profile(u.get("user_id"))
            if profile and profile.relationship == "system":
                system_user_ids.add(u.get("user_id"))

        if not system_user_ids:
            return {"conversations": [], "system_users": []}

        # Get conversations for system users
        all_convs = _conversations.list_conversations()
        conv_list = []
        for conv in all_convs:
            if conv.get("user_id") in system_user_ids:
                conv_list.append({
                    "id": conv.get("id"),
                    "title": conv.get("title"),
                    "message_count": conv.get("message_count", 0),
                    "created_at": conv.get("created_at"),
                    "updated_at": conv.get("updated_at"),
                    "user_id": conv.get("user_id")
                })

        # Sort by updated_at descending
        conv_list.sort(key=lambda x: x.get("updated_at") or "", reverse=True)

        # Get system user info
        system_users_info = []
        for uid in system_user_ids:
            profile = _users.load_profile(uid)
            if profile:
                system_users_info.append({
                    "user_id": uid,
                    "display_name": profile.display_name
                })

        return {
            "conversations": conv_list[:limit],
            "system_users": system_users_info
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    user: Dict = Depends(require_auth)
):
    """Get conversation details"""
    if not _conversations:
        raise HTTPException(status_code=503, detail="Conversations not initialized")

    try:
        conv = _conversations.load_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conv.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/conversations/{conversation_id}/user")
async def assign_conversation_user(
    conversation_id: str,
    request: AssignUserRequest,
    admin: Dict = Depends(require_admin)
):
    """Assign a conversation to a different user (admin action)"""
    if not _conversations:
        raise HTTPException(status_code=503, detail="Conversations not initialized")

    try:
        conv = _conversations.load_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        success = _conversations.assign_to_user(conversation_id, request.user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update conversation")
        return {"status": "updated", "id": conversation_id, "user_id": request.user_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user: Dict = Depends(require_auth)
):
    """Get all messages in a conversation"""
    from database import get_db
    import json

    try:
        with get_db() as conn:
            # Get messages directly from database
            cursor = conn.execute("""
                SELECT role, content, timestamp, provider, model,
                       input_tokens, output_tokens, user_id
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id,))

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "role": row[0],
                    "content": row[1],
                    "timestamp": row[2],
                    "provider": row[3],
                    "model": row[4],
                    "input_tokens": row[5],
                    "output_tokens": row[6],
                    "user_id": row[7]
                })

            if not messages:
                raise HTTPException(status_code=404, detail="Conversation not found")

            return {"messages": messages}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/summaries")
async def get_conversation_summaries(conversation_id: str, user: Dict = Depends(require_auth)):
    """Get summaries generated for a conversation"""
    if not _memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        # Query for summaries with this conversation ID
        results = _memory.collection.get(
            where={
                "$and": [
                    {"type": "summary"},
                    {"conversation_id": conversation_id}
                ]
            },
            include=["documents", "metadatas"]
        )

        summaries = []
        for i, doc_id in enumerate(results["ids"]):
            summaries.append({
                "id": doc_id,
                "content": results["documents"][i] if results["documents"] else None,
                "timestamp": results["metadatas"][i].get("timestamp") if results["metadatas"] else None
            })

        summaries.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        return {"summaries": summaries}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/observations")
async def get_conversation_observations(
    conversation_id: str,
    user: Dict = Depends(require_auth)
):
    """Get all observations (user and self) and marks made during a conversation"""
    import sys
    from users import UserManager
    from self_model import SelfManager

    user_manager = UserManager()
    self_manager = SelfManager()

    # Get marker_store from main_sdk module (same pattern as chain_api.py)
    main_sdk_module = sys.modules.get("main_sdk")
    marker_store = main_sdk_module.marker_store if main_sdk_module else None

    # Get user observations for this conversation (across all users)
    user_observations = []
    # Get the conversation to find its user_id
    from database import get_db
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT user_id FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        row = cursor.fetchone()
        if row and row["user_id"]:
            all_user_obs = user_manager.load_observations(row["user_id"])
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
