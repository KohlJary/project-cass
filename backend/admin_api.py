"""
Cass Vessel - Admin API Router
Endpoints for the admin dashboard to explore memory, users, conversations, and system stats.
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
import os
import jwt
import secrets

from dataclasses import asdict
from memory import CassMemory
from conversations import ConversationManager
from users import UserManager
from self_model import SelfManager
from config import DATA_DIR

router = APIRouter(prefix="/admin", tags=["admin"])

# JWT Configuration
JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str
    display_name: str
    expires_at: str

# Initialize managers (these will be replaced by dependency injection from main app)
memory: Optional[CassMemory] = None
conversations: Optional[ConversationManager] = None
users: Optional[UserManager] = None
self_manager: Optional[SelfManager] = None


def init_managers(
    mem: CassMemory,
    conv: ConversationManager,
    usr: UserManager,
    self_mgr: SelfManager
):
    """Initialize managers from main app"""
    global memory, conversations, users, self_manager
    memory = mem
    conversations = conv
    users = usr
    self_manager = self_mgr


# ============== Authentication ==============

def create_token(user_id: str, display_name: str) -> tuple[str, datetime]:
    """Create a JWT token for an admin user"""
    expires = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "user_id": user_id,
        "display_name": display_name,
        "exp": expires,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires


def verify_token(token: str) -> Optional[Dict]:
    """Verify a JWT token and return payload if valid"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict:
    """Dependency that requires valid admin authentication"""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = verify_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Verify user still has admin access
    if users:
        profile = users.load_profile(payload["user_id"])
        if not profile or not profile.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin access revoked"
            )

    return payload


@router.post("/auth/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest):
    """Login to admin dashboard"""
    if not users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    profile = users.authenticate_admin(request.username, request.password)
    if not profile:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, expires = create_token(profile.user_id, profile.display_name)

    return LoginResponse(
        token=token,
        user_id=profile.user_id,
        display_name=profile.display_name,
        expires_at=expires.isoformat()
    )


@router.get("/auth/verify")
async def verify_admin(admin: Dict = Depends(require_admin)):
    """Verify current token is valid"""
    return {
        "valid": True,
        "user_id": admin["user_id"],
        "display_name": admin["display_name"]
    }


@router.post("/auth/set-password")
async def set_admin_password(
    user_id: str,
    password: str,
    admin: Dict = Depends(require_admin)
):
    """Set password for an admin user (requires existing admin)"""
    if not users:
        raise HTTPException(status_code=503, detail="User manager not initialized")

    success = users.set_admin_password(user_id, password)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True}


# ============== Memory Endpoints ==============

@router.get("/memory")
async def get_memories(
    type: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0
):
    """Get all memories, optionally filtered by type"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        # Query ChromaDB
        collection = memory.collection

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
    limit: int = Query(default=10, le=50)
):
    """Semantic search across memories"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        results = memory.collection.query(
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
    type: Optional[str] = None
):
    """Get memory embeddings for visualization (2D projection via PCA)"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        import numpy as np

        collection = memory.collection
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
async def get_memory_stats():
    """Get memory statistics"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        collection = memory.collection

        # Get total count from ChromaDB
        total = collection.count()

        # Get counts by type from ChromaDB
        type_counts = {}
        for mem_type in ["summary", "journal", "observation", "user_observation", "per_user_journal", "attractor_marker", "project_document"]:
            try:
                results = collection.get(where={"type": mem_type}, include=[])
                type_counts[mem_type] = len(results["ids"])
            except:
                type_counts[mem_type] = 0

        # Add file-based self-observations from SelfManager
        self_obs_count = 0
        if self_manager:
            try:
                self_obs = self_manager.load_observations()
                self_obs_count = len(self_obs) if self_obs else 0
            except:
                pass
        type_counts["self_observation"] = self_obs_count

        return {
            "total_memories": total + self_obs_count,
            "by_type": type_counts,
            "journals": type_counts.get("journal", 0)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== User Endpoints ==============

@router.get("/users")
async def get_all_users():
    """Get all users with observation counts"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        all_users = users.list_users()  # Returns List[Dict]
        user_list = []

        for user in all_users:
            user_id = user.get("user_id")
            profile = users.load_profile(user_id)
            observations = users.load_observations(user_id)

            user_list.append({
                "id": user_id,
                "display_name": user.get("display_name"),
                "observation_count": len(observations) if observations else 0,
                "created_at": user.get("created_at"),
                "is_admin": profile.is_admin if profile else False,
                "has_password": bool(profile.password_hash) if profile else False
            })

        return {"users": user_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str):
    """Get detailed user profile and observations"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        profile = users.load_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        observations = users.load_observations(user_id)
        # Convert to dicts
        obs_list = [obs.__dict__ if hasattr(obs, '__dict__') else obs for obs in (observations or [])]
        profile_dict = profile.__dict__ if hasattr(profile, '__dict__') else profile

        return {
            "profile": profile_dict,
            "observations": obs_list
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/observations")
async def get_user_observations(user_id: str):
    """Get observations for a specific user"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        observations = users.load_observations(user_id)
        # Convert UserObservation objects to dicts
        obs_list = [obs.__dict__ if hasattr(obs, '__dict__') else obs for obs in (observations or [])]
        return {"observations": obs_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AdminStatusRequest(BaseModel):
    is_admin: bool


class SetPasswordRequest(BaseModel):
    password: str


@router.post("/users/{user_id}/admin-status")
async def set_user_admin_status(
    user_id: str,
    request: AdminStatusRequest,
    admin: Dict = Depends(require_admin)
):
    """Set admin status for a user (requires admin auth)"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        success = users.set_admin_status(user_id, request.is_admin)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"success": True, "is_admin": request.is_admin}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/set-password")
async def set_user_password(
    user_id: str,
    request: SetPasswordRequest,
    admin: Dict = Depends(require_admin)
):
    """Set password for a user (requires admin auth)"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        success = users.set_admin_password(user_id, request.password)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Journal Endpoints ==============

@router.get("/journals")
async def get_all_journals(limit: int = Query(default=30, le=100)):
    """Get all journal entries"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        journals = memory.get_recent_journals(n=limit)

        journal_list = []
        for j in journals:
            journal_list.append({
                "date": j["metadata"].get("journal_date"),
                "summary": j["metadata"].get("summary"),
                "locked": j["metadata"].get("locked", False)
            })

        return {"journals": journal_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journals/{date}")
async def get_journal_by_date(date: str):
    """Get a specific journal entry by date"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        journal = memory.get_journal_entry(date)
        if not journal:
            raise HTTPException(status_code=404, detail="Journal not found")

        return {
            "date": date,
            "content": journal["content"],
            "metadata": journal["metadata"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/journals/calendar")
async def get_journal_calendar(
    year: int = Query(...),
    month: int = Query(...)
):
    """Get journal dates for a specific month (for calendar view)"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        # Get all journals and filter by month
        journals = memory.get_recent_journals(n=100)

        month_str = f"{year}-{month:02d}"
        dates_with_journals = []

        for j in journals:
            journal_date = j["metadata"].get("journal_date", "")
            if journal_date.startswith(month_str):
                dates_with_journals.append(journal_date)

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
    limit: int = Query(default=50, le=200)
):
    """Get all conversations"""
    if not conversations:
        raise HTTPException(status_code=503, detail="Conversations not initialized")

    try:
        all_convs = conversations.list_conversations()

        conv_list = []
        for conv in all_convs[:limit]:
            conv_list.append({
                "id": conv.get("id"),
                "title": conv.get("title"),
                "message_count": conv.get("message_count", 0),
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
                "user_id": conv.get("user_id")
            })

        # Filter by user if specified
        if user_id:
            conv_list = [c for c in conv_list if c.get("user_id") == user_id]

        return {"conversations": conv_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/system")
async def get_system_conversations(limit: int = Query(default=50, le=200)):
    """Get conversations from system users (like Daedalus).

    Returns conversations where user_id belongs to a user with relationship='system'.
    This allows admins to view Daedalus-Cass communication history.
    """
    if not conversations or not users:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        # Get system user IDs
        all_users = users.list_users()
        system_user_ids = set()
        for user in all_users:
            profile = users.load_profile(user.get("user_id"))
            if profile and profile.relationship == "system":
                system_user_ids.add(user.get("user_id"))

        if not system_user_ids:
            return {"conversations": [], "system_users": []}

        # Get conversations for system users
        all_convs = conversations.list_conversations()
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
            profile = users.load_profile(uid)
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
async def get_conversation_detail(conversation_id: str):
    """Get conversation details"""
    if not conversations:
        raise HTTPException(status_code=503, detail="Conversations not initialized")

    try:
        conv = conversations.load_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conv.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get all messages in a conversation"""
    if not conversations:
        raise HTTPException(status_code=503, detail="Conversations not initialized")

    try:
        conv = conversations.load_conversation(conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = [asdict(m) for m in conv.messages]

        return {"messages": messages}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}/summaries")
async def get_conversation_summaries(conversation_id: str):
    """Get summaries generated for a conversation"""
    if not memory:
        raise HTTPException(status_code=503, detail="Memory not initialized")

    try:
        # Query for summaries with this conversation ID
        results = memory.collection.get(
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


# ============== System Endpoints ==============

@router.get("/system/stats")
async def get_system_stats():
    """Get system-wide statistics"""
    try:
        stats = {
            "users": 0,
            "conversations": 0,
            "memories": 0,
            "journals": 0
        }

        if users:
            all_users = users.list_users()
            stats["users"] = len(all_users)

        if conversations:
            all_convs = conversations.list_conversations()
            stats["conversations"] = len(all_convs)

        if memory:
            stats["memories"] = memory.collection.count()
            journals = memory.get_recent_journals(n=1000)
            stats["journals"] = len(journals)

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/health")
async def get_system_health():
    """Get system health status"""
    health = {
        "status": "healthy",
        "components": {
            "memory": memory is not None,
            "conversations": conversations is not None,
            "users": users is not None,
            "self_model": self_manager is not None
        }
    }

    if not all(health["components"].values()):
        health["status"] = "degraded"

    return health


# ============== Self-Model Endpoints ==============

@router.get("/self-model")
async def get_self_model():
    """Get Cass's self-model (profile)"""
    if not self_manager:
        raise HTTPException(status_code=503, detail="Self-model not initialized")

    try:
        profile = self_manager.load_profile()
        return profile.to_dict() if profile else {}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/growth-edges")
async def get_growth_edges():
    """Get Cass's growth edges"""
    if not self_manager:
        raise HTTPException(status_code=503, detail="Self-model not initialized")

    try:
        profile = self_manager.load_profile()
        edges = [e.to_dict() for e in profile.growth_edges] if profile and profile.growth_edges else []
        return {"edges": edges}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/questions")
async def get_open_questions():
    """Get Cass's open questions"""
    if not self_manager:
        raise HTTPException(status_code=503, detail="Self-model not initialized")

    try:
        profile = self_manager.load_profile()
        questions = [{"question": q} for q in profile.open_questions] if profile and profile.open_questions else []
        # Also get question reflections for more detail
        reflections = self_manager.load_question_reflections()
        for r in reflections:
            questions.append({
                "question": r.question,
                "provisional_answer": r.reflection,
                "confidence": r.confidence,
                "created_at": r.timestamp if r.timestamp else None
            })
        return {"questions": questions}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Research Session Endpoints ==============

# Research session manager - initialized from main app
research_session_manager = None


def init_research_session_manager(manager):
    """Initialize research session manager from main app"""
    global research_session_manager
    research_session_manager = manager


class StartSessionRequest(BaseModel):
    duration_minutes: int = 30
    mode: str = "explore"
    focus_item_id: Optional[str] = None
    focus_description: Optional[str] = None


@router.get("/research/sessions/current")
async def get_current_research_session():
    """Get the current research session status"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    session = research_session_manager.get_current_session()
    return {"session": session, "active": session is not None and session.get("status") == "active"}


@router.post("/research/sessions/start")
async def start_research_session(
    request: StartSessionRequest,
    admin: Dict = Depends(require_admin)
):
    """Start a new research session (admin only)"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.start_session(
        duration_minutes=min(request.duration_minutes, 60),
        mode=request.mode,
        focus_item_id=request.focus_item_id,
        focus_description=request.focus_description
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/pause")
async def pause_current_session(
    admin: Dict = Depends(require_admin)
):
    """Pause the current research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.pause_session()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/resume")
async def resume_current_session(
    admin: Dict = Depends(require_admin)
):
    """Resume a paused research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.resume_session()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/sessions/current/stop")
async def stop_current_session(
    admin: Dict = Depends(require_admin)
):
    """Force-stop the current research session"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    result = research_session_manager.terminate_session("Stopped by admin")
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/research/sessions")
async def list_research_sessions(
    limit: int = Query(default=20, le=100),
    status: Optional[str] = None
):
    """List past research sessions"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    sessions = research_session_manager.list_sessions(limit=limit, status=status)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/research/sessions/stats")
async def get_research_session_stats():
    """Get aggregate research session statistics"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    return research_session_manager.get_session_stats()


@router.get("/research/sessions/{session_id}")
async def get_research_session(session_id: str):
    """Get a specific research session by ID"""
    if not research_session_manager:
        raise HTTPException(status_code=503, detail="Research session manager not initialized")

    session = research_session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"session": session}


# ============== Research Scheduler Endpoints ==============

# Research scheduler - initialized from main app
research_scheduler = None


def init_research_scheduler(scheduler):
    """Initialize research scheduler from main app"""
    global research_scheduler
    research_scheduler = scheduler


class ApproveScheduleRequest(BaseModel):
    adjust_time: Optional[str] = None  # HH:MM format
    adjust_duration: Optional[int] = None
    notes: Optional[str] = None


class RejectScheduleRequest(BaseModel):
    reason: str


@router.get("/research/schedules")
async def list_research_schedules(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=100)
):
    """List all research schedule requests"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    schedules = research_scheduler.list_schedules(status=status, limit=limit)
    pending_count = research_scheduler.get_pending_count()
    return {
        "schedules": schedules,
        "count": len(schedules),
        "pending_approval": pending_count
    }


@router.get("/research/schedules/pending")
async def get_pending_schedules():
    """Get schedules pending approval"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    schedules = research_scheduler.list_schedules(status="pending_approval")
    return {"schedules": schedules, "count": len(schedules)}


@router.get("/research/schedules/stats")
async def get_scheduler_stats():
    """Get scheduler statistics"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    return research_scheduler.get_stats()


@router.get("/research/schedules/{schedule_id}")
async def get_schedule(schedule_id: str):
    """Get a specific schedule"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    schedule = research_scheduler.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {"schedule": schedule}


@router.post("/research/schedules/{schedule_id}/approve")
async def approve_schedule(
    schedule_id: str,
    request: ApproveScheduleRequest,
    admin: Dict = Depends(require_admin)
):
    """Approve a pending schedule request"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    result = research_scheduler.approve_schedule(
        schedule_id=schedule_id,
        approved_by=admin.get("user_id", "admin"),
        adjust_time=request.adjust_time,
        adjust_duration=request.adjust_duration,
        notes=request.notes
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/schedules/{schedule_id}/reject")
async def reject_schedule(
    schedule_id: str,
    request: RejectScheduleRequest,
    admin: Dict = Depends(require_admin)
):
    """Reject a pending schedule request"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    result = research_scheduler.reject_schedule(
        schedule_id=schedule_id,
        rejected_by=admin.get("user_id", "admin"),
        reason=request.reason
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/schedules/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    admin: Dict = Depends(require_admin)
):
    """Pause an approved schedule"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    result = research_scheduler.pause_schedule(schedule_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/research/schedules/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: str,
    admin: Dict = Depends(require_admin)
):
    """Resume a paused schedule"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    result = research_scheduler.resume_schedule(schedule_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.delete("/research/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    admin: Dict = Depends(require_admin)
):
    """Delete a schedule"""
    if not research_scheduler:
        raise HTTPException(status_code=503, detail="Research scheduler not initialized")

    result = research_scheduler.delete_schedule(schedule_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result
