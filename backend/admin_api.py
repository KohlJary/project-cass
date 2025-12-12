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


# ============== Daily Rhythm Endpoints ==============

daily_rhythm_manager = None
goal_manager = None


def init_daily_rhythm_manager(manager):
    """Initialize daily rhythm manager from main app"""
    global daily_rhythm_manager
    daily_rhythm_manager = manager


def init_goal_manager(manager):
    """Initialize goal manager from main app"""
    global goal_manager
    goal_manager = manager


# Session runner getters (functions that return the runner instances)
research_runner_getter = None
reflection_runner_getter = None


def init_session_runners(research_getter, reflection_getter):
    """Initialize session runner getters from main app"""
    global research_runner_getter, reflection_runner_getter
    research_runner_getter = research_getter
    reflection_runner_getter = reflection_getter


async def _backfill_phase_summaries(rhythm_manager, reflection_runner, research_runner):
    """Check for phases with session_ids but no/incomplete summaries and backfill from session data."""
    try:
        status = rhythm_manager.get_rhythm_status()
        for phase in status.get("phases", []):
            session_id = phase.get("session_id")
            current_summary = phase.get("summary") or ""
            # Backfill if no summary, or if summary is very short (likely just the theme)
            needs_backfill = not current_summary or len(current_summary) < 100

            if session_id and needs_backfill:
                # Detect session type from session_id prefix if not explicitly set
                session_type = phase.get("session_type")
                if not session_type:
                    session_type = "reflection" if session_id.startswith("reflect_") else "research"
                phase_id = phase.get("id")

                if session_type == "research":
                    try:
                        session_data = research_runner.session_manager.get_session(session_id)
                        if session_data:
                            # Use narrative summary, not findings_summary
                            summary = session_data.get("summary") or "Research session completed"
                            # Extract findings from findings_summary (bullet points)
                            findings = []
                            if session_data.get("findings_summary"):
                                for line in session_data["findings_summary"].split("\n"):
                                    if line.strip().startswith("-"):
                                        findings.append(line.strip()[1:].strip())
                            notes = session_data.get("notes_created", [])
                            rhythm_manager.update_phase_summary(
                                phase_id=phase_id,
                                summary=summary,
                                findings=findings if findings else None,
                                notes_created=notes if notes else None,
                            )
                            print(f"   📝 Backfilled phase '{phase_id}' from research session {session_id}")
                    except Exception as e:
                        print(f"   ⚠ Could not backfill research phase {phase_id}: {e}")

                elif session_type == "reflection":
                    try:
                        session_data = reflection_runner.manager.get_session(session_id)
                        if session_data:
                            summary = None
                            if hasattr(session_data, 'summary') and session_data.summary:
                                summary = session_data.summary
                            elif hasattr(session_data, 'insights') and session_data.insights:
                                summary = "Key insights: " + "; ".join(session_data.insights[:3])
                            else:
                                # Fallback to thought stream
                                thoughts = session_data.thought_stream if hasattr(session_data, 'thought_stream') else []
                                if thoughts:
                                    summary_thoughts = [t.content for t in thoughts[-2:] if hasattr(t, 'content')]
                                    summary = " ".join(summary_thoughts) if summary_thoughts else None

                            if summary:
                                rhythm_manager.update_phase_summary(
                                    phase_id=phase_id,
                                    summary=summary,
                                )
                                print(f"   📝 Backfilled phase '{phase_id}' from reflection session {session_id}")
                    except Exception as e:
                        print(f"   ⚠ Could not backfill reflection phase {phase_id}: {e}")
    except Exception as e:
        print(f"   ⚠ Error backfilling phase summaries: {e}")


class UpdateRhythmPhasesRequest(BaseModel):
    phases: List[Dict]


class TriggerPhaseRequest(BaseModel):
    duration_minutes: Optional[int] = None
    focus: Optional[str] = None
    theme: Optional[str] = None
    force: Optional[bool] = False  # Allow re-triggering completed phases
    agenda_item_id: Optional[str] = None  # Research agenda item to work on


@router.get("/rhythm/phases")
async def get_rhythm_phases():
    """Get configured daily rhythm phases"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    return {"phases": daily_rhythm_manager.get_phases()}


@router.put("/rhythm/phases")
async def update_rhythm_phases(
    request: UpdateRhythmPhasesRequest,
    admin: Dict = Depends(require_admin)
):
    """Update daily rhythm phase configuration"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    result = daily_rhythm_manager.update_phases(request.phases)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.get("/rhythm/status")
async def get_rhythm_status(date: Optional[str] = Query(default=None, description="Date in YYYY-MM-DD format")):
    """Get rhythm status for a specific date (or today if not specified)"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    return daily_rhythm_manager.get_rhythm_status(date=date)


@router.get("/rhythm/dates")
async def get_rhythm_dates():
    """Get list of dates that have rhythm records"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    # List all JSON files in the records directory
    records_dir = daily_rhythm_manager.records_dir
    dates = []
    for f in sorted(records_dir.glob("*.json"), reverse=True):
        # Extract date from filename (YYYY-MM-DD.json)
        date_str = f.stem
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            dates.append(date_str)

    return {"dates": dates}


@router.get("/rhythm/stats")
async def get_rhythm_stats(days: int = Query(default=7, le=30)):
    """Get rhythm statistics over recent days"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    return daily_rhythm_manager.get_stats(days=days)


@router.post("/rhythm/phases/{phase_id}/complete")
async def mark_phase_complete(
    phase_id: str,
    session_id: Optional[str] = None,
    session_type: Optional[str] = None
):
    """Mark a rhythm phase as completed"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    result = daily_rhythm_manager.mark_phase_completed(
        phase_id=phase_id,
        session_id=session_id,
        session_type=session_type
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.post("/rhythm/phases/{phase_id}/trigger")
async def trigger_phase(
    phase_id: str,
    request: TriggerPhaseRequest = None
):
    """
    Manually trigger a rhythm phase (research or reflection session).

    This allows triggering missed phases or re-running phases outside their normal window.
    The phase will be marked as completed once the session starts.
    """
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")
    if not research_runner_getter or not reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Session runners not initialized")

    # Get phase configuration
    phases = daily_rhythm_manager.get_phases()
    phase_config = next((p for p in phases if p["id"] == phase_id), None)

    if not phase_config:
        raise HTTPException(status_code=404, detail=f"Phase '{phase_id}' not found")

    activity_type = phase_config.get("activity_type", "any")
    phase_name = phase_config.get("name", phase_id)

    # Check current status
    status = daily_rhythm_manager.get_rhythm_status()
    phase_status = next(
        (p for p in status.get("phases", []) if p["id"] == phase_id),
        {}
    ).get("status")

    # Parse request or use defaults
    req = request or TriggerPhaseRequest()

    if phase_status == "completed" and not req.force:
        raise HTTPException(
            status_code=400,
            detail=f"Phase '{phase_name}' already completed today. Use force=true to re-run."
        )
    duration = req.duration_minutes or 30

    try:
        # Start appropriate session based on activity type
        if activity_type in ("research", "any"):
            runner = research_runner_getter()
            if runner.is_running:
                raise HTTPException(
                    status_code=409,
                    detail="A research session is already running"
                )

            # Determine focus - from agenda item, explicit focus, or default
            focus_item_id = None
            if req.agenda_item_id and goal_manager:
                agenda_item = goal_manager.get_research_agenda_item(req.agenda_item_id)
                if agenda_item:
                    # Build rich focus description from agenda item
                    focus_parts = [f"Research agenda item: {agenda_item['topic']}"]
                    if agenda_item.get('why'):
                        focus_parts.append(f"Why: {agenda_item['why']}")
                    if agenda_item.get('key_findings'):
                        findings = [f.get('finding', f) if isinstance(f, dict) else f
                                    for f in agenda_item['key_findings'][:3]]
                        if findings:
                            focus_parts.append(f"Prior findings: {'; '.join(findings)}")
                    focus = '\n'.join(focus_parts)
                    focus_item_id = req.agenda_item_id
                    # Mark agenda item as in progress
                    goal_manager.update_research_agenda_item(
                        req.agenda_item_id,
                        set_status="in_progress"
                    )
                else:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Agenda item not found: {req.agenda_item_id}"
                    )
            else:
                focus = req.focus or f"Self-directed research during {phase_name}"

            session = await runner.start_session(
                duration_minutes=duration,
                focus=focus,
                focus_item_id=focus_item_id,
                mode="explore",
                trigger="manual_rhythm_trigger"
            )

            if session:
                daily_rhythm_manager.mark_phase_completed(
                    phase_id,
                    session_type="research",
                    session_id=session.session_id
                )
                return {
                    "success": True,
                    "phase_id": phase_id,
                    "session_type": "research",
                    "session_id": session.session_id,
                    "duration_minutes": duration,
                    "message": f"Started research session for '{phase_name}'"
                }

        elif activity_type == "reflection":
            runner = reflection_runner_getter()
            if runner.is_running:
                raise HTTPException(
                    status_code=409,
                    detail="A reflection session is already running"
                )

            # Generate theme based on phase name or use provided
            if req.theme:
                theme = req.theme
            elif "morning" in phase_name.lower():
                theme = "Setting intentions and preparing for the day ahead"
            elif "evening" in phase_name.lower() or "synthesis" in phase_name.lower():
                theme = "Integrating the day's experiences and insights"
            else:
                theme = "Private contemplation and self-examination"

            session = await runner.start_session(
                duration_minutes=duration,
                theme=theme,
                trigger="manual_rhythm_trigger"
            )

            if session:
                daily_rhythm_manager.mark_phase_completed(
                    phase_id,
                    session_type="reflection",
                    session_id=session.session_id
                )
                return {
                    "success": True,
                    "phase_id": phase_id,
                    "session_type": "reflection",
                    "session_id": session.session_id,
                    "duration_minutes": duration,
                    "message": f"Started reflection session for '{phase_name}'"
                }

        raise HTTPException(
            status_code=500,
            detail="Failed to start session"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error triggering phase: {str(e)}"
        )


@router.post("/rhythm/regenerate-summary")
async def regenerate_daily_summary():
    """Regenerate the daily summary as a narrative written by Cass."""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    from background_tasks import _generate_narrative_summary
    from datetime import datetime

    # Backfill any missing phase summaries from session data
    if reflection_runner_getter and research_runner_getter:
        reflection_runner = reflection_runner_getter()
        research_runner = research_runner_getter()
        await _backfill_phase_summaries(daily_rhythm_manager, reflection_runner, research_runner)

    status = daily_rhythm_manager.get_rhythm_status()
    all_phases = status.get("phases", [])
    completed_phases = [p for p in all_phases if p.get("status") == "completed"]

    if not completed_phases:
        raise HTTPException(status_code=400, detail="No completed phases to summarize")

    total_phases = status.get("total_phases", len(all_phases))
    completion_rate = int((len(completed_phases) / total_phases) * 100) if total_phases > 0 else 0

    # Build phase data
    phase_data = []
    for phase in completed_phases:
        entry = {
            "name": phase.get("name"),
            "activity_type": phase.get("activity_type", "any"),
            "summary": phase.get("summary"),
            "completed_at": phase.get("completed_at"),
            "notes_count": len(phase.get("notes_created") or []),
            "findings": phase.get("findings") or []
        }
        phase_data.append(entry)

    # Generate narrative summary
    narrative = await _generate_narrative_summary(
        date=status.get("date", datetime.now().strftime("%Y-%m-%d")),
        phase_data=phase_data,
        completion_rate=completion_rate,
        total_phases=total_phases
    )

    # Update the manager
    daily_rhythm_manager.update_daily_summary(narrative)

    return {
        "success": True,
        "summary": narrative,
        "phases_included": len(completed_phases)
    }


# ============== Research Notes Endpoints ==============

research_manager = None


def init_research_manager(manager):
    """Initialize research manager from main app"""
    global research_manager
    research_manager = manager


@router.get("/research/notes")
async def list_research_notes(
    limit: int = Query(default=50, le=200),
    session_id: Optional[str] = None
):
    """List research notes, optionally filtered by session"""
    if not research_manager:
        raise HTTPException(status_code=503, detail="Research manager not initialized")

    notes = research_manager.list_research_notes()

    # Filter by session if specified
    if session_id:
        notes = [n for n in notes if n.get("session_id") == session_id]

    # Sort by created_at descending and limit
    notes = sorted(notes, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]

    return {"notes": notes, "count": len(notes)}


@router.get("/research/notes/{note_id}")
async def get_research_note(note_id: str):
    """Get a specific research note by ID"""
    if not research_manager:
        raise HTTPException(status_code=503, detail="Research manager not initialized")

    note = research_manager.get_research_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    return note


@router.get("/research/notes/session/{session_id}")
async def get_notes_for_session(session_id: str):
    """Get all research notes created during a specific session"""
    if not research_manager:
        raise HTTPException(status_code=503, detail="Research manager not initialized")

    notes = research_manager.list_research_notes()
    session_notes = [n for n in notes if n.get("session_id") == session_id]
    session_notes = sorted(session_notes, key=lambda x: x.get("created_at", ""))

    return {"notes": session_notes, "count": len(session_notes), "session_id": session_id}


# ============== GitHub Metrics Endpoints ==============

github_metrics_manager = None


def init_github_metrics(manager):
    """Initialize GitHub metrics manager - called from main_sdk.py"""
    global github_metrics_manager
    github_metrics_manager = manager


@router.get("/github/metrics")
async def get_github_metrics():
    """Get current GitHub metrics for all tracked repos"""
    if not github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    current = github_metrics_manager.get_current_metrics()
    if not current:
        # No data yet, try to fetch
        try:
            snapshot = await github_metrics_manager.refresh_metrics()
            return {
                "timestamp": snapshot.timestamp,
                "repos": snapshot.repos,
                "api_calls_remaining": snapshot.api_calls_remaining
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {e}")

    return current


@router.get("/github/metrics/stats")
async def get_github_stats():
    """Get aggregate statistics for GitHub metrics"""
    if not github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    return github_metrics_manager.get_aggregate_stats()


@router.get("/github/metrics/history")
async def get_github_history(
    days: int = Query(default=30, le=180),
    repo: Optional[str] = Query(default=None)
):
    """Get historical GitHub metrics"""
    if not github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    history = github_metrics_manager.get_historical_metrics(days=days, repo=repo)
    return {
        "days": days,
        "repo": repo,
        "data": history,
        "count": len(history)
    }


@router.get("/github/metrics/timeseries/{metric}")
async def get_github_timeseries(
    metric: str,
    days: int = Query(default=14, le=90),
    repo: Optional[str] = Query(default=None)
):
    """Get time series data for a specific metric"""
    if not github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    valid_metrics = ["clones", "clones_uniques", "views", "views_uniques", "stars", "forks"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Must be one of: {valid_metrics}"
        )

    series = github_metrics_manager.get_time_series(metric=metric, days=days, repo=repo)
    return {
        "metric": metric,
        "days": days,
        "repo": repo,
        "data": series
    }


@router.post("/github/metrics/refresh")
async def refresh_github_metrics(admin: Dict = Depends(require_admin)):
    """Force refresh GitHub metrics (admin only)"""
    if not github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    try:
        snapshot = await github_metrics_manager.refresh_metrics()
        return {
            "success": True,
            "timestamp": snapshot.timestamp,
            "repos": list(snapshot.repos.keys()),
            "api_calls_remaining": snapshot.api_calls_remaining
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh metrics: {e}")


# ============== Token Usage Endpoints ==============

token_usage_tracker = None


def init_token_tracker(tracker):
    """Initialize token usage tracker - called from main_sdk.py"""
    global token_usage_tracker
    token_usage_tracker = tracker


@router.get("/usage")
async def get_token_usage(
    start_date: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)"),
    category: Optional[str] = Query(default=None),
    operation: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=1000)
):
    """Get token usage records with optional filters"""
    if not token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    records = token_usage_tracker.get_records(
        start_date=start_dt,
        end_date=end_dt,
        category=category,
        operation=operation,
        provider=provider,
        limit=limit
    )

    return {
        "records": records,
        "count": len(records),
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "category": category,
            "operation": operation,
            "provider": provider
        }
    }


@router.get("/usage/summary")
async def get_usage_summary(
    start_date: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)")
):
    """Get aggregated token usage summary"""
    if not token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    return token_usage_tracker.get_summary(start_date=start_dt, end_date=end_dt)


@router.get("/usage/timeseries")
async def get_usage_timeseries(
    metric: str = Query(default="total_tokens", description="Metric: total_tokens, input_tokens, output_tokens, cost, count"),
    days: int = Query(default=14, le=90),
    granularity: str = Query(default="day", description="Granularity: day or hour")
):
    """Get token usage time series data for charting"""
    if not token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    valid_metrics = ["total_tokens", "input_tokens", "output_tokens", "cost", "count"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Must be one of: {valid_metrics}"
        )

    if granularity not in ["day", "hour"]:
        raise HTTPException(status_code=400, detail="Granularity must be 'day' or 'hour'")

    series = token_usage_tracker.get_timeseries(metric=metric, days=days, granularity=granularity)
    return {
        "metric": metric,
        "days": days,
        "granularity": granularity,
        "data": series
    }
