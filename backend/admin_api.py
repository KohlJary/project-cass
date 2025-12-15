"""
Cass Vessel - Admin API Router
Endpoints for the admin dashboard to explore memory, users, conversations, and system stats.
"""
from fastapi import APIRouter, HTTPException, Query, Depends, Header, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
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
from config import DATA_DIR, DEMO_MODE

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
    """Dependency that requires valid admin authentication.

    In demo mode, returns a demo user without requiring authentication.
    """
    # Demo mode bypasses authentication
    if DEMO_MODE:
        return {
            "user_id": "demo",
            "display_name": "Demo User",
            "demo_mode": True
        }

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
        "display_name": admin["display_name"],
        "demo_mode": admin.get("demo_mode", False)
    }


@router.get("/auth/status")
async def auth_status():
    """Get authentication status (public endpoint).

    Returns whether demo mode is enabled so the frontend can skip login.
    """
    return {
        "demo_mode": DEMO_MODE
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


# ============== Daemon Endpoints ==============

def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID - uses provided one or falls back to global default."""
    if daemon_id:
        return daemon_id
    # Import here to avoid circular dependency
    from database import get_daemon_id
    return get_daemon_id()


@router.get("/daemons")
async def list_daemons(admin: Dict = Depends(require_admin)):
    """List all available daemons."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, label, name, created_at, kernel_version, status
            FROM daemons
            ORDER BY label
        """)

        columns = ["id", "label", "name", "created_at", "kernel_version", "status"]
        daemons = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return {"daemons": daemons}


@router.get("/daemons/{daemon_id}")
async def get_daemon(daemon_id: str, admin: Dict = Depends(require_admin)):
    """Get details for a specific daemon."""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, label, name, created_at, kernel_version, status
            FROM daemons
            WHERE id = ?
        """, (daemon_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Daemon not found")

        columns = ["id", "label", "name", "created_at", "kernel_version", "status"]
        daemon = dict(zip(columns, row))

        # Get some stats for this daemon
        stats_cursor = conn.execute("""
            SELECT
                (SELECT COUNT(*) FROM conversations WHERE daemon_id = ?) as conversations,
                (SELECT COUNT(*) FROM wiki_pages WHERE daemon_id = ?) as wiki_pages,
                (SELECT COUNT(*) FROM journals WHERE daemon_id = ?) as journals,
                (SELECT COUNT(*) FROM dreams WHERE daemon_id = ?) as dreams
        """, (daemon_id, daemon_id, daemon_id, daemon_id))

        stats_row = stats_cursor.fetchone()
        daemon["stats"] = {
            "conversations": stats_row[0] or 0,
            "wiki_pages": stats_row[1] or 0,
            "journals": stats_row[2] or 0,
            "dreams": stats_row[3] or 0,
        }

    return daemon


@router.get("/daemons/exports/seeds")
async def list_seed_exports(admin: Dict = Depends(require_admin)):
    """List available .anima exports from seed folder."""
    from daemon_export import list_seed_exports

    exports = list_seed_exports()
    return {"exports": exports}


@router.post("/daemons/{daemon_id}/export")
async def export_daemon_endpoint(
    daemon_id: str,
    admin: Dict = Depends(require_admin)
):
    """Export a daemon to downloadable .anima file."""
    from daemon_export import export_daemon, ANIMA_EXTENSION
    from fastapi.responses import FileResponse
    from pathlib import Path
    import tempfile

    # Export to temp file
    with tempfile.NamedTemporaryFile(suffix=ANIMA_EXTENSION, delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        result = export_daemon(daemon_id, tmp_path)
        daemon_label = result["daemon_label"]
        timestamp = result.get("stats", {}).get("exported_at", "export")

        # Return as file download
        from fastapi.responses import FileResponse
        return FileResponse(
            path=str(tmp_path),
            filename=f"{daemon_label}_{timestamp[:10] if len(timestamp) >= 10 else 'export'}{ANIMA_EXTENSION}",
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={daemon_label}{ANIMA_EXTENSION}"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Clean up temp file on error
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/daemons/import")
async def import_daemon_endpoint(
    file: UploadFile = File(...),
    daemon_name: Optional[str] = Form(None),
    skip_embeddings: bool = Form(False),
    admin: Dict = Depends(require_admin)
):
    """Import a daemon from uploaded .anima file."""
    from daemon_export import import_daemon, ANIMA_EXTENSION
    from pathlib import Path
    import tempfile
    import shutil

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ANIMA_EXTENSION
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        result = import_daemon(
            tmp_path,
            new_daemon_name=daemon_name,
            skip_embeddings=skip_embeddings
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/daemons/import/preview")
async def preview_daemon_import_endpoint(
    file: UploadFile = File(...),
    admin: Dict = Depends(require_admin)
):
    """Preview daemon import without applying."""
    from daemon_export import preview_daemon_import, ANIMA_EXTENSION
    from pathlib import Path
    import tempfile
    import shutil

    # Save uploaded file to temp location
    suffix = Path(file.filename).suffix if file.filename else ANIMA_EXTENSION
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        preview = preview_daemon_import(tmp_path)
        return preview
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/daemons/import/seed/{filename}")
async def import_seed_daemon(
    filename: str,
    daemon_name: Optional[str] = None,
    skip_embeddings: bool = False,
    admin: Dict = Depends(require_admin)
):
    """Import a daemon from a seed file by filename."""
    from daemon_export import import_daemon, list_seed_exports
    from pathlib import Path

    # Find the seed file
    exports = list_seed_exports()
    seed_file = next((e for e in exports if e["filename"] == filename), None)

    if not seed_file:
        raise HTTPException(status_code=404, detail=f"Seed file '{filename}' not found")

    if "error" in seed_file:
        raise HTTPException(status_code=400, detail=f"Seed file has errors: {seed_file['error']}")

    try:
        result = import_daemon(
            Path(seed_file["path"]),
            new_daemon_name=daemon_name,
            skip_embeddings=skip_embeddings
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            if memory:
                collection = memory.collection
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


@router.get("/users/{user_id}/model")
async def get_user_model(user_id: str):
    """Get the structured user model for a specific user"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        model = users.load_user_model(user_id)
        if model:
            return {"user_model": model.to_dict()}
        return {"user_model": None}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/relationship")
async def get_relationship_model(user_id: str):
    """Get the relationship model for a specific user"""
    if not users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        model = users.load_relationship_model(user_id)
        if model:
            return {"relationship_model": model.to_dict()}
        return {"relationship_model": None}

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
async def get_all_journals(
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID"),
    limit: int = Query(default=30, le=100)
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
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID")
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
    daemon_id: Optional[str] = Query(None, description="Filter by daemon ID")
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
    limit: int = Query(default=50, le=200)
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
async def get_conversation_messages(
    conversation_id: str,
    admin: Dict = Depends(require_admin)
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
async def get_system_stats(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch stats for"),
    admin: Dict = Depends(require_admin)
):
    """Get system-wide statistics for a daemon"""
    from database import get_db

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get conversation count
            conv_cursor = conn.execute("""
                SELECT COUNT(*) FROM conversations WHERE daemon_id = ?
            """, (effective_daemon_id,))
            conv_count = conv_cursor.fetchone()[0] or 0

            # Get journal count
            journal_cursor = conn.execute("""
                SELECT COUNT(*) FROM journals WHERE daemon_id = ?
            """, (effective_daemon_id,))
            journal_count = journal_cursor.fetchone()[0] or 0

            # Get user count (global - not daemon-specific)
            user_count = 0
            if users:
                user_count = len(users.list_users())

            # Get memory count (from ChromaDB - not daemon-specific for now)
            memory_count = 0
            if memory:
                memory_count = memory.collection.count()

            return {
                "users": user_count,
                "conversations": conv_count,
                "memories": memory_count,
                "journals": journal_count
            }

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
async def get_self_model(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch self-model for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's self-model (profile)"""
    from database import get_db
    import json

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get daemon profile
            cursor = conn.execute("""
                SELECT identity_statements_json, values_json, communication_patterns_json,
                       capabilities_json, limitations_json, open_questions_json, notes
                FROM daemon_profiles WHERE daemon_id = ?
            """, (effective_daemon_id,))
            row = cursor.fetchone()

            if not row:
                return {}

            # Get growth edges
            edges_cursor = conn.execute("""
                SELECT area, current_state, desired_state, observations_json,
                       strategies_json, first_noticed, last_updated
                FROM growth_edges WHERE daemon_id = ?
            """, (effective_daemon_id,))
            growth_edges = [
                {
                    "area": r[0],
                    "current_state": r[1],
                    "desired_state": r[2],
                    "observations": json.loads(r[3]) if r[3] else [],
                    "strategies": json.loads(r[4]) if r[4] else [],
                    "first_noticed": r[5],
                    "last_updated": r[6]
                }
                for r in edges_cursor.fetchall()
            ]

            # Get opinions
            opinions_cursor = conn.execute("""
                SELECT topic, position, confidence, rationale, formed_from,
                       evolution_json, date_formed, last_updated
                FROM opinions WHERE daemon_id = ?
            """, (effective_daemon_id,))
            opinions = [
                {
                    "topic": r[0],
                    "position": r[1],
                    "confidence": r[2],
                    "rationale": r[3],
                    "formed_from": r[4],
                    "evolution": json.loads(r[5]) if r[5] else [],
                    "date_formed": r[6],
                    "last_updated": r[7]
                }
                for r in opinions_cursor.fetchall()
            ]

            return {
                "identity_statements": json.loads(row[0]) if row[0] else [],
                "values": json.loads(row[1]) if row[1] else [],
                "communication_patterns": json.loads(row[2]) if row[2] else [],
                "capabilities": json.loads(row[3]) if row[3] else [],
                "limitations": json.loads(row[4]) if row[4] else [],
                "open_questions": json.loads(row[5]) if row[5] else [],
                "notes": row[6] or "",
                "growth_edges": growth_edges,
                "opinions": opinions
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/growth-edges")
async def get_growth_edges(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch growth edges for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's growth edges"""
    from database import get_db
    import json

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT area, current_state, desired_state, observations_json,
                       strategies_json, first_noticed, last_updated
                FROM growth_edges WHERE daemon_id = ?
                ORDER BY first_noticed DESC
            """, (effective_daemon_id,))

            edges = [
                {
                    "area": r[0],
                    "current_state": r[1],
                    "desired_state": r[2],
                    "observations": json.loads(r[3]) if r[3] else [],
                    "strategies": json.loads(r[4]) if r[4] else [],
                    "first_noticed": r[5],
                    "last_updated": r[6]
                }
                for r in cursor.fetchall()
            ]

            return {"edges": edges}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/self-model/questions")
async def get_open_questions(
    daemon_id: Optional[str] = Query(None, description="Daemon ID to fetch questions for"),
    admin: Dict = Depends(require_admin)
):
    """Get Cass's open questions"""
    from database import get_db
    import json

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    try:
        with get_db() as conn:
            # Get open questions from daemon_profiles
            cursor = conn.execute("""
                SELECT open_questions_json
                FROM daemon_profiles WHERE daemon_id = ?
            """, (effective_daemon_id,))
            row = cursor.fetchone()

            questions = []
            if row and row[0]:
                open_qs = json.loads(row[0])
                questions = [{"question": q} for q in open_qs]

            return {"questions": questions}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== Identity Snippet Endpoints ==============

@router.get("/self-model/identity-snippet")
async def get_identity_snippet(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    admin: Dict = Depends(require_admin)
):
    """Get the active identity snippet for a daemon."""
    from identity_snippets import get_active_snippet

    effective_daemon_id = get_effective_daemon_id(daemon_id)
    snippet = get_active_snippet(effective_daemon_id)

    if not snippet:
        return {"snippet": None, "message": "No identity snippet generated yet"}

    return {"snippet": snippet}


@router.get("/self-model/identity-snippet/history")
async def get_identity_snippet_history(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    limit: int = Query(10, description="Number of versions to return"),
    admin: Dict = Depends(require_admin)
):
    """Get the version history of identity snippets."""
    from identity_snippets import get_snippet_history

    effective_daemon_id = get_effective_daemon_id(daemon_id)
    history = get_snippet_history(effective_daemon_id, limit=limit)

    return {"history": history, "count": len(history)}


@router.post("/self-model/identity-snippet/regenerate")
async def regenerate_identity_snippet(
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    force: bool = Query(False, description="Force regeneration even if unchanged"),
    admin: Dict = Depends(require_admin)
):
    """Manually trigger identity snippet regeneration."""
    from identity_snippets import trigger_snippet_regeneration

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    result = await trigger_snippet_regeneration(
        daemon_id=effective_daemon_id,
        force=force
    )

    if result:
        return {
            "status": "regenerated",
            "snippet": result
        }
    else:
        return {
            "status": "unchanged",
            "message": "Identity statements unchanged, no regeneration needed (use force=true to override)"
        }


class RollbackRequest(BaseModel):
    version: int


@router.post("/self-model/identity-snippet/rollback")
async def rollback_identity_snippet(
    request: RollbackRequest,
    daemon_id: Optional[str] = Query(None, description="Daemon ID"),
    admin: Dict = Depends(require_admin)
):
    """Rollback to a previous identity snippet version."""
    from identity_snippets import rollback_to_version

    effective_daemon_id = get_effective_daemon_id(daemon_id)

    result = rollback_to_version(effective_daemon_id, request.version)

    if result:
        return {
            "status": "rolled_back",
            "snippet": result
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Version {request.version} not found for this daemon"
        )


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


# ============== Synthesis Session Endpoints ==============

class StartSynthesisRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None
    mode: str = "general"  # general, focused, contradiction-resolution


@router.get("/synthesis/status")
async def get_synthesis_status():
    """Get the current synthesis session status"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
            "artifacts_created": state.artifacts_created,
        }
    else:
        return {"running": False}


@router.post("/synthesis/start")
async def start_synthesis_session(request: StartSynthesisRequest):
    """Start a new synthesis session"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A synthesis session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
            mode=request.mode,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "mode": request.mode,
            "message": "Synthesis session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/synthesis/stop")
async def stop_synthesis_session():
    """Stop the current synthesis session"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Synthesis runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No synthesis session running"}

    runner.stop()
    return {"success": True, "message": "Synthesis session stop requested"}


@router.get("/synthesis/sessions")
async def list_synthesis_sessions(limit: int = Query(default=20, le=100)):
    """List past synthesis sessions"""
    if not synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="Synthesis runner not initialized")

    runner = synthesis_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    # Get sessions from runner's internal storage
    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus": s.focus,
                "mode": s.mode,
                "artifacts_created": s.artifacts_created,
                "artifacts_updated": s.artifacts_updated,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Meta-Reflection Session Endpoints ==============

class StartMetaReflectionRequest(BaseModel):
    duration_minutes: int = 20
    focus: Optional[str] = None  # Optional focus area (e.g., "growth_edges", "coherence")


@router.get("/meta-reflection/status")
async def get_meta_reflection_status():
    """Get the current meta-reflection session status"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/meta-reflection/start")
async def start_meta_reflection_session(request: StartMetaReflectionRequest):
    """Start a new meta-reflection session"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A meta-reflection session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Meta-reflection session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/meta-reflection/stop")
async def stop_meta_reflection_session():
    """Stop the current meta-reflection session"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No meta-reflection session running"}

    runner.stop()
    return {"success": True, "message": "Meta-reflection session stop requested"}


@router.get("/meta-reflection/sessions")
async def list_meta_reflection_sessions(limit: int = Query(default=20, le=100)):
    """List past meta-reflection sessions"""
    if not meta_reflection_runner_getter:
        raise HTTPException(status_code=503, detail="Meta-reflection runner not initialized")

    runner = meta_reflection_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    # Get sessions from runner's internal storage
    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus": s.focus,
                "insights_recorded": len(s.insights_recorded),
                "contradictions_found": s.contradictions_found,
                "patterns_identified": len(s.patterns_identified),
                "summary": s.summary,
                "key_findings": s.key_findings,
                "recommended_actions": s.recommended_actions,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Consolidation Session Endpoints ==============

class StartConsolidationRequest(BaseModel):
    duration_minutes: int = 25
    period_type: str = "weekly"  # daily, weekly, monthly, quarterly
    period_start: Optional[str] = None  # YYYY-MM-DD
    period_end: Optional[str] = None  # YYYY-MM-DD


consolidation_runner_getter = None


def init_consolidation_runner(getter):
    """Initialize consolidation runner getter"""
    global consolidation_runner_getter
    consolidation_runner_getter = getter


@router.get("/consolidation/status")
async def get_consolidation_status():
    """Get the current consolidation session status"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/consolidation/start")
async def start_consolidation_session(request: StartConsolidationRequest):
    """Start a new consolidation session"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A consolidation session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            period_type=request.period_type,
            period_start=request.period_start,
            period_end=request.period_end,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "period_type": request.period_type,
            "period_start": session.period_start,
            "period_end": session.period_end,
            "message": f"Consolidation session started ({request.period_type})"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/consolidation/stop")
async def stop_consolidation_session():
    """Stop the current consolidation session"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Consolidation runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No consolidation session running"}

    runner.stop()
    return {"success": True, "message": "Consolidation session stop requested"}


@router.get("/consolidation/sessions")
async def list_consolidation_sessions(limit: int = Query(default=20, le=100)):
    """List past consolidation sessions"""
    if not consolidation_runner_getter:
        raise HTTPException(status_code=503, detail="Consolidation runner not initialized")

    runner = consolidation_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    # Get sessions from runner's internal storage
    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "period_type": s.period_type,
                "period_start": s.period_start,
                "period_end": s.period_end,
                "items_reviewed": s.items_reviewed,
                "summaries_created": s.summaries_created,
                "items_archived": s.items_archived,
                "themes_identified": s.themes_identified,
                "key_learnings": s.key_learnings[:5],  # Limit for API response
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Growth Edge Work Endpoints ==============

class StartGrowthEdgeRequest(BaseModel):
    duration_minutes: int = 20
    focus: Optional[str] = None  # Specific growth edge area to focus on


growth_edge_runner_getter = None


def init_growth_edge_runner(getter):
    """Initialize growth edge runner getter"""
    global growth_edge_runner_getter
    growth_edge_runner_getter = getter


@router.get("/growth-edge/status")
async def get_growth_edge_status():
    """Get the current growth edge work session status"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/growth-edge/start")
async def start_growth_edge_session(request: StartGrowthEdgeRequest):
    """Start a new growth edge work session"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A growth edge session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Growth edge work session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/growth-edge/stop")
async def stop_growth_edge_session():
    """Stop the current growth edge work session"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Growth edge runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No growth edge session running"}

    runner.stop()
    return {"success": True, "message": "Growth edge session stop requested"}


@router.get("/growth-edge/sessions")
async def list_growth_edge_sessions(limit: int = Query(default=20, le=100)):
    """List past growth edge work sessions"""
    if not growth_edge_runner_getter:
        raise HTTPException(status_code=503, detail="Growth edge runner not initialized")

    runner = growth_edge_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus_edge": s.focus_edge,
                "exercises_designed": len(s.exercises_designed),
                "observations_recorded": len(s.observations_recorded),
                "evaluations_made": s.evaluations_made,
                "strategies_updated": s.strategies_updated,
                "summary": s.summary,
                "next_steps": s.next_steps[:3],
                "commitments": s.commitments[:3],
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== Writing Session Endpoints ==============

class StartWritingRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None  # Specific project ID or description to focus on


writing_runner_getter = None


def init_writing_runner(getter):
    """Initialize writing runner getter"""
    global writing_runner_getter
    writing_runner_getter = getter


@router.get("/writing/status")
async def get_writing_status():
    """Get the current writing session status"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/writing/start")
async def start_writing_session(request: StartWritingRequest):
    """Start a new writing session"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A writing session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Writing session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/writing/stop")
async def stop_writing_session():
    """Stop the current writing session"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Writing runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No writing session running"}

    runner.stop()
    return {"success": True, "message": "Writing session stop requested"}


@router.get("/writing/sessions")
async def list_writing_sessions(limit: int = Query(default=20, le=100)):
    """List past writing sessions"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus_project": s.focus_project,
                "projects_created": s.projects_created,
                "projects_updated": s.projects_updated,
                "words_written": s.words_written,
                "critiques_done": s.critiques_done,
                "summary": s.summary,
                "satisfaction": s.satisfaction,
                "next_intentions": s.next_intentions,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/writing/projects")
async def list_writing_projects(status: str = "all", project_type: str = "all"):
    """List all writing projects"""
    if not writing_runner_getter:
        raise HTTPException(status_code=503, detail="Writing runner not initialized")

    runner = writing_runner_getter()
    if not runner:
        return {"projects": [], "count": 0}

    projects = list(runner._projects.values())

    if status != "all":
        projects = [p for p in projects if p.status == status]
    if project_type != "all":
        projects = [p for p in projects if p.project_type == project_type]

    projects.sort(key=lambda p: p.updated_at, reverse=True)

    return {
        "projects": [
            {
                "id": p.id,
                "title": p.title,
                "project_type": p.project_type,
                "status": p.status,
                "word_count": p.word_count,
                "description": p.description[:100] if p.description else None,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
                "completed_at": p.completed_at,
            }
            for p in projects
        ],
        "count": len(projects)
    }


# ============== Knowledge Building Session Endpoints ==============

class StartKnowledgeBuildingRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None  # Specific reading item ID or topic to focus on


knowledge_building_runner_getter = None


def init_knowledge_building_runner(getter):
    """Initialize knowledge building runner getter"""
    global knowledge_building_runner_getter
    knowledge_building_runner_getter = getter


@router.get("/knowledge-building/status")
async def get_knowledge_building_status():
    """Get the current knowledge building session status"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/knowledge-building/start")
async def start_knowledge_building_session(request: StartKnowledgeBuildingRequest):
    """Start a new knowledge building session"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A knowledge building session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Knowledge building session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/knowledge-building/stop")
async def stop_knowledge_building_session():
    """Stop the current knowledge building session"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Knowledge building runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No knowledge building session running"}

    runner.stop()
    return {"success": True, "message": "Knowledge building session stop requested"}


@router.get("/knowledge-building/sessions")
async def list_knowledge_building_sessions(limit: int = Query(default=20, le=100)):
    """List past knowledge building sessions"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "focus_item": s.focus_item,
                "items_worked_on": s.items_worked_on,
                "notes_created": s.notes_created,
                "concepts_extracted": s.concepts_extracted,
                "connections_made": s.connections_made,
                "summary": s.summary,
                "key_insights": s.key_insights[:5],
                "next_focus": s.next_focus,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/knowledge-building/reading-queue")
async def list_reading_queue(
    status: str = "all",
    source_type: str = "all",
    priority: str = "all"
):
    """List all reading queue items"""
    if not knowledge_building_runner_getter:
        raise HTTPException(status_code=503, detail="Knowledge building runner not initialized")

    runner = knowledge_building_runner_getter()
    if not runner:
        return {"items": [], "count": 0}

    items = runner.get_all_items()

    if status != "all":
        items = [i for i in items if i.get("status") == status]
    if source_type != "all":
        items = [i for i in items if i.get("source_type") == source_type]
    if priority != "all":
        items = [i for i in items if i.get("priority") == priority]

    # Sort by priority then added_at
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda i: (priority_order.get(i.get("priority", "medium"), 1), i.get("added_at", "")))

    return {
        "items": items,
        "count": len(items)
    }


# ============== Curiosity Session Endpoints ==============

class StartCuriosityRequest(BaseModel):
    duration_minutes: int = 20
    # No focus parameter - that's the point of curiosity sessions


curiosity_runner_getter = None


def init_curiosity_runner(getter):
    """Initialize curiosity runner getter"""
    global curiosity_runner_getter
    curiosity_runner_getter = getter


@router.get("/curiosity/status")
async def get_curiosity_status():
    """Get the current curiosity session status"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/curiosity/start")
async def start_curiosity_session(request: StartCuriosityRequest):
    """Start a new curiosity session - pure self-directed exploration"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A curiosity session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "message": "Curiosity session started - no focus, pure exploration"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/curiosity/stop")
async def stop_curiosity_session():
    """Stop the current curiosity session"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Curiosity runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No curiosity session running"}

    runner.stop()
    return {"success": True, "message": "Curiosity session stop requested"}


@router.get("/curiosity/sessions")
async def list_curiosity_sessions(limit: int = Query(default=20, le=100)):
    """List past curiosity sessions"""
    if not curiosity_runner_getter:
        raise HTTPException(status_code=503, detail="Curiosity runner not initialized")

    runner = curiosity_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "directions_count": len(s.directions_chosen),
                "discoveries_count": len(s.discoveries),
                "questions_count": len(s.questions_captured),
                "threads_followed": len(s.threads_followed),
                "territories_explored": s.territories_explored,
                "best_discoveries": s.best_discoveries[:3],
                "satisfaction": s.satisfaction,
                "energy": s.energy,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


# ============== World State Session Endpoints ==============

class StartWorldStateRequest(BaseModel):
    duration_minutes: int = 15
    focus: Optional[str] = None  # Optional topic focus (e.g., "technology news")


world_state_runner_getter = None


def init_world_state_runner(getter):
    """Initialize world state runner getter"""
    global world_state_runner_getter
    world_state_runner_getter = getter


@router.get("/world-state/status")
async def get_world_state_status():
    """Get the current world state session status"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/world-state/start")
async def start_world_state_session(request: StartWorldStateRequest):
    """Start a new world state consumption session"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A world state session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "World state session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/world-state/stop")
async def stop_world_state_session():
    """Stop the current world state session"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="World state runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No world state session running"}

    runner.stop()
    return {"success": True, "message": "World state session stop requested"}


@router.get("/world-state/sessions")
async def list_world_state_sessions(limit: int = Query(default=20, le=100)):
    """List past world state sessions"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "news_items_count": len(s.news_items),
                "observations_count": len(s.observations),
                "connections_count": len(s.interest_connections),
                "summary": s.summary,
                "overall_feeling": s.overall_feeling,
                "follow_up_needed": s.follow_up_needed[:3],
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/world-state/observations")
async def list_world_observations(limit: int = Query(default=50, le=200)):
    """List recent world observations"""
    if not world_state_runner_getter:
        raise HTTPException(status_code=503, detail="World state runner not initialized")

    runner = world_state_runner_getter()
    if not runner:
        return {"observations": [], "count": 0}

    observations = runner._all_observations[-limit:]
    observations.reverse()  # Most recent first

    return {
        "observations": observations,
        "count": len(observations)
    }


# ============== Creative Output Session Endpoints ==============

class StartCreativeRequest(BaseModel):
    duration_minutes: int = 30
    focus: Optional[str] = None  # Optional focus (e.g., "visual concepts" or specific project)


creative_runner_getter = None


def init_creative_runner(getter):
    """Initialize creative runner getter"""
    global creative_runner_getter
    creative_runner_getter = getter


@router.get("/creative/status")
async def get_creative_status():
    """Get the current creative session status"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

    state = runner._current_state
    if state and runner.is_running:
        elapsed = (datetime.now() - state.started_at).total_seconds()
        return {
            "running": True,
            "session_id": state.session_id,
            "focus": state.focus,
            "started_at": state.started_at.isoformat(),
            "duration_minutes": state.duration_minutes,
            "elapsed_seconds": int(elapsed),
            "remaining_seconds": max(0, int(state.duration_minutes * 60 - elapsed)),
            "iteration_count": state.iteration_count,
            "tool_calls": len(state.tool_calls),
        }
    else:
        return {"running": False}


@router.post("/creative/start")
async def start_creative_session(request: StartCreativeRequest):
    """Start a new creative output session"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

    if runner.is_running:
        raise HTTPException(status_code=409, detail="A creative session is already running")

    try:
        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            focus=request.focus,
        )

        return {
            "success": True,
            "session_id": session.id,
            "duration_minutes": request.duration_minutes,
            "focus": request.focus,
            "message": "Creative session started"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/creative/stop")
async def stop_creative_session():
    """Stop the current creative session"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        raise HTTPException(status_code=503, detail="Creative runner not available")

    if not runner.is_running:
        return {"success": False, "message": "No creative session running"}

    runner.stop()
    return {"success": True, "message": "Creative session stop requested"}


@router.get("/creative/sessions")
async def list_creative_sessions(limit: int = Query(default=20, le=100)):
    """List past creative sessions"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "duration_minutes": s.duration_minutes,
                "projects_touched": s.projects_touched,
                "new_projects": s.new_projects,
                "artifacts_created": s.artifacts_created,
                "summary": s.summary,
                "creative_energy": s.creative_energy,
                "next_focus": s.next_focus,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


@router.get("/creative/projects")
async def list_creative_projects(
    status: str = "all",
    medium: str = "all"
):
    """List all creative projects"""
    if not creative_runner_getter:
        raise HTTPException(status_code=503, detail="Creative runner not initialized")

    runner = creative_runner_getter()
    if not runner:
        return {"projects": [], "count": 0}

    projects = runner.get_all_projects()

    if status != "all":
        projects = [p for p in projects if p.get("status") == status]
    if medium != "all":
        projects = [p for p in projects if p.get("medium") == medium]

    # Sort by updated_at
    projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)

    return {
        "projects": projects,
        "count": len(projects)
    }


# ============== User Model Synthesis Endpoints ==============

class StartUserModelSynthesisRequest(BaseModel):
    duration_minutes: int = 30
    target_user_id: str  # Required - which user to synthesize
    target_user_name: str = ""  # Display name for logging


user_model_synthesis_runner_getter = None


def init_user_model_synthesis_runner(getter):
    """Initialize user model synthesis runner getter"""
    global user_model_synthesis_runner_getter
    user_model_synthesis_runner_getter = getter


@router.get("/user-model-synthesis/status")
async def get_user_model_synthesis_status():
    """Get the current user model synthesis session status"""
    if not user_model_synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="User model synthesis runner not initialized")

    runner = user_model_synthesis_runner_getter()
    return {
        "is_running": runner.is_running,
        "session_type": "user_model_synthesis"
    }


@router.post("/user-model-synthesis/start")
async def start_user_model_synthesis_session(request: StartUserModelSynthesisRequest):
    """Start a new user model synthesis session"""
    if not user_model_synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="User model synthesis runner not initialized")

    runner = user_model_synthesis_runner_getter()
    if runner.is_running:
        raise HTTPException(status_code=409, detail="A user model synthesis session is already running")

    try:
        # Get user info to check if foundational
        user_manager = runner.user_manager
        rel_model = user_manager.load_relationship_model(request.target_user_id)
        is_foundational = rel_model.is_foundational if rel_model else False

        session = await runner.start_session(
            duration_minutes=request.duration_minutes,
            target_user_id=request.target_user_id,
            target_user_name=request.target_user_name,
            is_foundational=is_foundational,
            focus=f"Synthesizing understanding of {request.target_user_name or request.target_user_id}"
        )

        return {
            "status": "started",
            "session_type": "user_model_synthesis",
            "session_id": session.id,
            "target_user_id": request.target_user_id,
            "is_foundational": is_foundational,
            "duration_minutes": request.duration_minutes,
            "message": f"Started user model synthesis session for {request.target_user_name or 'user'}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {str(e)}")


@router.post("/user-model-synthesis/stop")
async def stop_user_model_synthesis_session():
    """Stop the current user model synthesis session"""
    if not user_model_synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="User model synthesis runner not initialized")

    runner = user_model_synthesis_runner_getter()
    if not runner.is_running:
        raise HTTPException(status_code=404, detail="No user model synthesis session is currently running")

    runner.stop()
    return {"status": "stopped", "message": "User model synthesis session stopped"}


@router.get("/user-model-synthesis/sessions")
async def list_user_model_synthesis_sessions(limit: int = Query(default=20, le=100)):
    """List past user model synthesis sessions"""
    if not user_model_synthesis_runner_getter:
        raise HTTPException(status_code=503, detail="User model synthesis runner not initialized")

    runner = user_model_synthesis_runner_getter()
    if not runner:
        return {"sessions": [], "count": 0}

    sessions = list(runner._sessions.values())
    sessions.sort(key=lambda s: s.started_at, reverse=True)

    return {
        "sessions": [
            {
                "id": s.id,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_minutes": s.duration_minutes,
                "target_user_id": s.target_user_id,
                "target_user_name": s.target_user_name,
                "is_foundational": s.is_foundational,
                "status": s.status,
                "observations_reviewed": s.observations_reviewed,
                "understandings_added": s.understandings_added,
                "patterns_identified": s.patterns_identified,
                "contradictions_flagged": s.contradictions_flagged,
                "questions_raised": s.questions_raised,
                "summary": s.summary,
            }
            for s in sessions[:limit]
        ],
        "count": len(sessions)
    }


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


# Session runner registry - maps session types to their runner getters
# Each entry: runner_getter, session_id_attr (how to get session ID from returned session)
_session_runners: Dict[str, Any] = {}


def register_session_runner(session_type: str, runner_getter, session_id_attr: str = "session_id"):
    """Register a session runner for a given session type."""
    _session_runners[session_type] = {
        "getter": runner_getter,
        "session_id_attr": session_id_attr,
    }


def init_session_runners(research_getter, reflection_getter, synthesis_getter=None, meta_reflection_getter=None):
    """Initialize session runner getters from main app (legacy compatibility)"""
    if research_getter:
        register_session_runner("research", research_getter, "session_id")
    if reflection_getter:
        register_session_runner("reflection", reflection_getter, "session_id")
    if synthesis_getter:
        register_session_runner("synthesis", synthesis_getter, "id")
    if meta_reflection_getter:
        register_session_runner("meta_reflection", meta_reflection_getter, "id")


def get_session_runner(session_type: str):
    """Get the runner for a session type, or None if not registered."""
    entry = _session_runners.get(session_type)
    if entry and entry["getter"]:
        return entry["getter"](), entry["session_id_attr"]
    return None, None


# Activity type to session type mapping (what session type handles each activity)
ACTIVITY_SESSION_MAP = {
    "research": "research",
    "reflection": "reflection",
    "synthesis": "synthesis",
    "meta_reflection": "meta_reflection",
    "consolidation": "consolidation",
    "growth_edge": "growth_edge",
    "writing": "writing",
    "knowledge_building": "knowledge_building",
    "curiosity": "curiosity",
    "world_state": "world_state",
    "creative": "creative",
    "any": "research",  # Default to research for "any" activity type
}


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

    dates = daily_rhythm_manager.get_dates_with_records()
    return {"dates": dates}


@router.get("/rhythm/stats")
async def get_rhythm_stats(days: int = Query(default=7, le=30)):
    """Get rhythm statistics over recent days"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    return daily_rhythm_manager.get_stats(days=days)


@router.get("/rhythm/weekly")
async def get_weekly_schedule():
    """Get weekly schedule showing which phases apply to which days"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    return daily_rhythm_manager.get_weekly_schedule()


class MarkPhaseCompleteRequest(BaseModel):
    session_id: Optional[str] = None
    session_type: Optional[str] = None
    summary: Optional[str] = None
    findings: Optional[List[str]] = None
    notes_created: Optional[List[str]] = None


@router.post("/rhythm/phases/{phase_id}/complete")
async def mark_phase_complete(
    phase_id: str,
    request: MarkPhaseCompleteRequest = None
):
    """Mark a rhythm phase as completed"""
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    req = request or MarkPhaseCompleteRequest()
    result = daily_rhythm_manager.mark_phase_completed(
        phase_id=phase_id,
        session_id=req.session_id,
        session_type=req.session_type,
        summary=req.summary,
        findings=req.findings,
        notes_created=req.notes_created,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


def _infer_session_params(session_type: str, phase_name: str, req) -> dict:
    """
    Infer session parameters based on session type and phase name.

    Returns dict with keys: focus, theme, mode, period_type (as applicable)
    """
    params = {"focus": req.focus if req else None}
    phase_lower = phase_name.lower()

    if session_type == "research":
        if not params["focus"]:
            if "wiki" in phase_lower:
                params["focus"] = "wiki"
            elif "world" in phase_lower or "state" in phase_lower:
                params["focus"] = "world_state"
        params["mode"] = "explore"

    elif session_type == "reflection":
        if "morning" in phase_lower:
            params["theme"] = "Setting intentions and preparing for the day ahead"
        elif "evening" in phase_lower or "synthesis" in phase_lower:
            params["theme"] = "Integrating the day's experiences and insights"
        elif "contemplative" in phase_lower:
            params["theme"] = "Deep contemplation and self-examination"
        else:
            params["theme"] = "Private contemplation and self-examination"

    elif session_type == "synthesis":
        if not params["focus"]:
            if "research" in phase_lower:
                params["focus"] = "research"
            elif "growth" in phase_lower:
                params["focus"] = "growth"
        params["mode"] = "integrate"

    elif session_type == "meta_reflection":
        if not params["focus"]:
            if "coherence" in phase_lower:
                params["focus"] = "coherence"
            elif "growth" in phase_lower:
                params["focus"] = "growth_edges"

    elif session_type == "consolidation":
        params["period_type"] = "weekly"  # default
        if "daily" in phase_lower:
            params["period_type"] = "daily"
        elif "monthly" in phase_lower:
            params["period_type"] = "monthly"
        elif "quarterly" in phase_lower:
            params["period_type"] = "quarterly"

    elif session_type == "growth_edge":
        # Focus from phase name if not specified
        pass

    elif session_type == "writing":
        if not params["focus"]:
            if "exploratory" in phase_lower:
                params["focus"] = "exploratory"
            elif "sunday" in phase_lower:
                params["focus"] = "weekly_synthesis"

    elif session_type == "world_state":
        # World state sessions don't need special params
        pass

    elif session_type == "curiosity":
        # Curiosity sessions intentionally have no focus
        params["focus"] = None

    return params


async def _start_session(session_type: str, runner, duration: int, params: dict):
    """
    Start a session with the given runner and parameters.

    Returns the session object or None.
    """
    # Build kwargs based on what the runner accepts
    kwargs = {"duration_minutes": duration}

    if session_type == "research":
        if params.get("focus"):
            kwargs["focus"] = params["focus"]
        if params.get("mode"):
            kwargs["mode"] = params["mode"]
        kwargs["trigger"] = "manual_rhythm_trigger"

    elif session_type == "reflection":
        if params.get("theme"):
            kwargs["theme"] = params["theme"]
        kwargs["trigger"] = "manual_rhythm_trigger"

    elif session_type == "synthesis":
        if params.get("focus"):
            kwargs["focus"] = params["focus"]
        if params.get("mode"):
            kwargs["mode"] = params["mode"]

    elif session_type == "meta_reflection":
        if params.get("focus"):
            kwargs["focus"] = params["focus"]

    elif session_type == "consolidation":
        if params.get("period_type"):
            kwargs["period_type"] = params["period_type"]

    elif session_type in ("growth_edge", "writing", "knowledge_building", "world_state", "creative"):
        if params.get("focus"):
            kwargs["focus"] = params["focus"]

    elif session_type == "curiosity":
        # No focus for curiosity - that's the point
        kwargs.pop("focus", None)

    return await runner.start_session(**kwargs)


@router.post("/rhythm/phases/{phase_id}/trigger")
async def trigger_phase(
    phase_id: str,
    request: TriggerPhaseRequest = None
):
    """
    Manually trigger a rhythm phase session.

    This allows triggering missed phases or re-running phases outside their normal window.
    The phase will be marked as in_progress when the session starts, and completed when it ends.
    """
    if not daily_rhythm_manager:
        raise HTTPException(status_code=503, detail="Daily rhythm manager not initialized")

    # Get phase configuration
    phases = daily_rhythm_manager.get_phases()
    phase_config = next((p for p in phases if p["id"] == phase_id), None)

    if not phase_config:
        raise HTTPException(status_code=404, detail=f"Phase '{phase_id}' not found")

    activity_type = phase_config.get("activity_type", "any")
    phase_name = phase_config.get("name", phase_id)

    # Map activity type to session type
    session_type = ACTIVITY_SESSION_MAP.get(activity_type, "research")

    # Get the runner for this session type
    runner, session_id_attr = get_session_runner(session_type)
    if not runner:
        raise HTTPException(
            status_code=503,
            detail=f"No runner registered for session type '{session_type}'"
        )

    # Check if already running
    if runner.is_running:
        raise HTTPException(
            status_code=409,
            detail=f"A {session_type} session is already running"
        )

    # Check current status
    status = daily_rhythm_manager.get_rhythm_status()
    phase_status = next(
        (p for p in status.get("phases", []) if p["id"] == phase_id),
        {}
    ).get("status")

    req = request or TriggerPhaseRequest()

    if phase_status == "completed" and not req.force:
        raise HTTPException(
            status_code=400,
            detail=f"Phase '{phase_name}' already completed today. Use force=true to re-run."
        )

    if phase_status == "in_progress":
        raise HTTPException(
            status_code=409,
            detail=f"Phase '{phase_name}' is already in progress."
        )

    duration = req.duration_minutes or 30

    try:
        # Infer session parameters from phase name and request
        params = _infer_session_params(session_type, phase_name, req)

        # Start the session
        session = await _start_session(session_type, runner, duration, params)

        if session:
            # Get session ID using the configured attribute
            session_id = getattr(session, session_id_attr, None)

            # Mark phase as in_progress (will be marked completed when session ends)
            daily_rhythm_manager.mark_phase_in_progress(
                phase_id,
                session_type=session_type,
                session_id=session_id
            )

            return {
                "success": True,
                "phase_id": phase_id,
                "session_type": session_type,
                "session_id": session_id,
                "duration_minutes": duration,
                "message": f"Started {session_type} session for '{phase_name}'"
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


# ============================================================================
# Unified Session Endpoint
# ============================================================================

# Map session types to their data directories
SESSION_TYPE_DIRS = {
    "reflection": "solo_reflections",
    "research": "research/sessions",
    "curiosity": "curiosity",
    "world_state": "world_state",
    "creative_output": "creative",
    "creative": "creative",  # alias
    "consolidation": "consolidation",
    "knowledge_building": "knowledge_building",
    "writing": "writing",
    "synthesis": "synthesis",
    "meta_reflection": "meta_reflection",
    "growth_edge": "growth_edge",
}


def _try_load_session_result(session_type: str, session_id: str) -> Optional[Dict[str, Any]]:
    """
    Try to load a session using the new standardized SessionResult format.

    Returns the session dict if found in new format, None otherwise.
    This allows graceful fallback to legacy loaders.
    """
    import json

    subdir = SESSION_TYPE_DIRS.get(session_type.lower())
    if not subdir:
        return None

    session_dir = DATA_DIR / subdir

    # Try new standard naming first: session_{id}.json
    session_file = session_dir / f"session_{session_id}.json"
    if not session_file.exists():
        # Try without prefix for legacy
        session_file = session_dir / f"{session_id}.json"

    if not session_file.exists():
        return None

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Check if this is the new SessionResult format (has session_type field)
    if "session_type" in data and "artifacts" in data:
        # It's the new format - normalize field names for frontend
        return {
            "session_id": data.get("session_id"),
            "session_type": data.get("session_type"),
            "started_at": data.get("started_at"),
            "ended_at": data.get("completed_at"),
            "duration_minutes": data.get("duration_minutes"),
            "status": data.get("status", "completed"),
            "summary": data.get("summary"),
            "findings": data.get("findings", []),
            "artifacts": data.get("artifacts", []),
            "metadata": data.get("metadata", {}),
            "focus": data.get("focus"),
        }

    # Not new format, return None to use legacy loader
    return None


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    session_type: str = Query(..., description="Session type: reflection, research, synthesis, meta_reflection, consolidation, growth_edge, knowledge_building, writing, curiosity, world_state, creative_output")
):
    """
    Get unified session result for any activity type.

    Returns a standardized format regardless of session type:
    - session_id, session_type, started_at, ended_at, duration_minutes, status
    - summary: Main session summary
    - findings: Key findings/insights as a list
    - artifacts: Type-specific artifacts (thoughts, notes, discoveries, etc.)
    - metadata: Additional type-specific data
    """
    session_type_lower = session_type.lower()

    # Handle alias
    if session_type_lower == "creative":
        session_type_lower = "creative_output"

    try:
        # First, try loading using new SessionResult format
        result = _try_load_session_result(session_type_lower, session_id)
        if result:
            return result

        # Fall back to legacy loaders
        if session_type_lower == "reflection":
            return await _load_reflection_session(session_id)
        elif session_type_lower == "research":
            return await _load_research_session(session_id)
        elif session_type_lower == "curiosity":
            return await _load_curiosity_session(session_id)
        elif session_type_lower == "world_state":
            return await _load_world_state_session(session_id)
        elif session_type_lower == "creative_output":
            return await _load_creative_session(session_id)
        elif session_type_lower == "consolidation":
            return await _load_consolidation_session(session_id)
        elif session_type_lower == "knowledge_building":
            return await _load_knowledge_building_session(session_id)
        elif session_type_lower == "writing":
            return await _load_writing_session(session_id)
        elif session_type_lower == "synthesis":
            return await _load_synthesis_session(session_id)
        elif session_type_lower == "meta_reflection":
            return await _load_meta_reflection_session(session_id)
        elif session_type_lower == "growth_edge":
            return await _load_growth_edge_session(session_id)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown session type: {session_type}. Valid types: reflection, research, synthesis, meta_reflection, consolidation, growth_edge, knowledge_building, writing, curiosity, world_state, creative_output"
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading session: {str(e)}")


async def _load_reflection_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a reflection session."""
    import json
    session_file = DATA_DIR / "solo_reflections" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Reflection session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Extract thoughts as artifacts
    artifacts = []
    for thought in data.get("thought_stream", []):
        artifacts.append({
            "type": "thought",
            "content": thought.get("content"),
            "thought_type": thought.get("thought_type"),
            "confidence": thought.get("confidence"),
            "related_concepts": thought.get("related_concepts", []),
            "timestamp": thought.get("timestamp")
        })

    return {
        "session_id": data.get("session_id"),
        "session_type": "reflection",
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": data.get("status", "completed"),
        "summary": data.get("summary"),
        "findings": data.get("insights", []),
        "artifacts": artifacts,
        "metadata": {
            "theme": data.get("theme"),
            "trigger": data.get("trigger"),
            "questions_raised": data.get("questions_raised", []),
            "model_used": data.get("model_used"),
            "thought_count": len(artifacts)
        }
    }


async def _load_research_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a research session."""
    import json
    session_file = DATA_DIR / "research" / "sessions" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Research session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Notes as artifacts
    artifacts = []
    for note_id in data.get("notes_created", []):
        artifacts.append({
            "type": "research_note",
            "note_id": note_id
        })

    # Progress entries as artifacts
    for entry in data.get("progress_entries", []):
        artifacts.append({
            "type": "progress",
            "content": entry.get("entry"),
            "timestamp": entry.get("timestamp")
        })

    return {
        "session_id": data.get("session_id"),
        "session_type": "research",
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
        "duration_minutes": data.get("duration_limit_minutes"),
        "status": data.get("status", "completed"),
        "summary": data.get("summary") or data.get("findings_summary"),
        "findings": [data.get("findings_summary")] if data.get("findings_summary") else [],
        "artifacts": artifacts,
        "metadata": {
            "mode": data.get("mode"),
            "focus": data.get("focus_description"),
            "focus_item_id": data.get("focus_item_id"),
            "searches_performed": data.get("searches_performed", 0),
            "urls_fetched": data.get("urls_fetched", 0),
            "notes_created": data.get("notes_created", []),
            "next_steps": data.get("next_steps"),
            "message_count": data.get("message_count", 0)
        }
    }


async def _load_curiosity_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a curiosity session."""
    import json
    session_file = DATA_DIR / "curiosity" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Curiosity session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Discoveries as artifacts
    artifacts = []
    for disc in data.get("discoveries", []):
        artifacts.append({
            "type": "discovery",
            "content": disc.get("what"),
            "significance": disc.get("significance"),
            "surprise_level": disc.get("surprise_level"),
            "leads_to": disc.get("leads_to"),
            "source": disc.get("source"),
            "timestamp": disc.get("timestamp")
        })

    # Questions as artifacts
    for q in data.get("questions_captured", []):
        artifacts.append({
            "type": "question",
            "content": q
        })

    return {
        "session_id": data.get("id"),
        "session_type": "curiosity",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary"),
        "findings": data.get("best_discoveries", []),
        "artifacts": artifacts,
        "metadata": {
            "directions_chosen": data.get("directions_chosen", []),
            "threads_followed": data.get("threads_followed", []),
            "threads_to_continue": data.get("threads_to_continue", []),
            "interest_patterns": data.get("interest_patterns", []),
            "territories_explored": data.get("territories_explored", []),
            "flagged_for_agenda": data.get("flagged_for_agenda", []),
            "satisfaction": data.get("satisfaction"),
            "energy": data.get("energy")
        }
    }


async def _load_world_state_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a world state session."""
    import json
    session_file = DATA_DIR / "world_state" / f"session_{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"World state session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Observations as artifacts
    artifacts = []
    for obs in data.get("observations", []):
        artifacts.append({
            "type": "world_observation",
            "content": obs.get("observation"),
            "category": obs.get("category"),
            "significance": obs.get("significance"),
            "topics": obs.get("topics", []),
            "timestamp": obs.get("timestamp")
        })

    return {
        "session_id": data.get("id"),
        "session_type": "world_state",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary"),
        "findings": data.get("follow_up_needed", []),  # Topics to follow up on
        "artifacts": artifacts,
        "metadata": {
            "news_items_count": data.get("news_items_count", 0),
            "interest_connections": data.get("interest_connections", []),
            "world_summary": data.get("world_summary"),
            "overall_feeling": data.get("overall_feeling")
        }
    }


async def _load_creative_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a creative output session."""
    import json
    session_file = DATA_DIR / "creative" / f"session_{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Creative session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Load artifacts from projects touched during this session
    artifacts = []
    projects_touched = data.get("projects_touched", [])
    if projects_touched:
        projects_file = DATA_DIR / "creative" / "projects.json"
        if projects_file.exists():
            try:
                with open(projects_file, 'r') as f:
                    projects_data = json.load(f)
                projects_list = projects_data.get("projects", [])
                for project in projects_list:
                    if project.get("id") in projects_touched:
                        # Get artifacts from this project
                        for art in project.get("artifacts", []):
                            artifacts.append({
                                "type": "creative_artifact",
                                "content": art.get("content"),
                                "artifact_type": art.get("type"),
                                "project_id": project.get("id"),
                                "project_title": project.get("title"),
                                "notes": art.get("notes"),
                                "iteration": art.get("iteration"),
                                "timestamp": art.get("created_at")
                            })
                        # Also include developments as artifacts
                        for dev in project.get("developments", []):
                            artifacts.append({
                                "type": "development",
                                "content": dev.get("development"),
                                "new_elements": dev.get("new_elements", []),
                                "open_questions": dev.get("open_questions", []),
                                "project_id": project.get("id"),
                                "project_title": project.get("title"),
                                "timestamp": dev.get("timestamp")
                            })
            except Exception:
                pass  # If we can't load projects, just return empty artifacts

    return {
        "session_id": data.get("id"),
        "session_type": "creative_output",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary"),
        "findings": [],  # Creative sessions don't have findings in the same way
        "artifacts": artifacts,
        "metadata": {
            "projects_touched": data.get("projects_touched", []),
            "new_projects": data.get("new_projects", []),
            "artifacts_created": data.get("artifacts_created", 0),
            "creative_energy": data.get("creative_energy"),
            "next_focus": data.get("next_focus")
        }
    }


async def _load_consolidation_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a consolidation session."""
    import json
    session_file = DATA_DIR / "consolidation" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Consolidation session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Learnings and themes as artifacts
    artifacts = []
    for learning in data.get("key_learnings", []):
        artifacts.append({
            "type": "learning",
            "content": learning
        })

    for theme in data.get("themes_identified", []):
        artifacts.append({
            "type": "theme",
            "content": theme
        })

    return {
        "session_id": data.get("id"),
        "session_type": "consolidation",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary") or data.get("period_summary"),
        "findings": data.get("key_learnings", []),
        "artifacts": artifacts,
        "metadata": {
            "period_type": data.get("period_type"),
            "period_start": data.get("period_start"),
            "period_end": data.get("period_end"),
            "material_reviewed": data.get("material_reviewed", {}),
            "items_archived": data.get("items_archived", []),
            "agenda_updates": data.get("agenda_updates", [])
        }
    }


async def _load_knowledge_building_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a knowledge building session."""
    import json
    session_file = DATA_DIR / "knowledge" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Knowledge building session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Reading notes as artifacts
    artifacts = []
    for note in data.get("notes_created", []):
        artifacts.append({
            "type": "reading_note",
            "content": note.get("content"),
            "note_type": note.get("type"),
            "source_title": note.get("source_title"),
            "timestamp": note.get("timestamp")
        })

    for concept in data.get("concepts_extracted", []):
        artifacts.append({
            "type": "concept",
            "content": concept.get("name"),
            "definition": concept.get("definition"),
            "connections": concept.get("connections", [])
        })

    return {
        "session_id": data.get("id"),
        "session_type": "knowledge_building",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary"),
        "findings": data.get("key_insights", []),
        "artifacts": artifacts,
        "metadata": {
            "focus": data.get("focus"),
            "sources_read": data.get("sources_read", []),
            "reading_progress": data.get("reading_progress", {}),
            "connections_made": data.get("connections_made", 0),
            "understanding_level": data.get("understanding_level")
        }
    }


async def _load_writing_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a writing session."""
    import json
    session_file = DATA_DIR / "writing" / f"{session_id}.json"
    if not session_file.exists():
        raise FileNotFoundError(f"Writing session {session_id} not found")

    with open(session_file, 'r') as f:
        data = json.load(f)

    # Writing artifacts
    artifacts = []
    for draft in data.get("drafts_created", []):
        artifacts.append({
            "type": "draft",
            "project_id": draft.get("project_id"),
            "title": draft.get("title"),
            "word_count": draft.get("word_count")
        })

    for note in data.get("revision_notes", []):
        artifacts.append({
            "type": "revision_note",
            "content": note
        })

    return {
        "session_id": data.get("id"),
        "session_type": "writing",
        "started_at": data.get("started_at"),
        "ended_at": data.get("completed_at"),
        "duration_minutes": data.get("duration_minutes"),
        "status": "completed" if data.get("completed_at") else "in_progress",
        "summary": data.get("summary"),
        "findings": data.get("key_outputs", []),
        "artifacts": artifacts,
        "metadata": {
            "focus": data.get("focus"),
            "projects_worked": data.get("projects_worked", []),
            "words_written": data.get("words_written", 0),
            "pieces_completed": data.get("pieces_completed", []),
            "creative_state": data.get("creative_state")
        }
    }


async def _load_synthesis_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a synthesis session."""
    # Synthesis sessions are kept in memory, check if runner has it
    if synthesis_runner_getter:
        runner = synthesis_runner_getter()
        if hasattr(runner, '_sessions') and session_id in runner._sessions:
            session = runner._sessions[session_id]
            return {
                "session_id": session.id,
                "session_type": "synthesis",
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.completed_at.isoformat() if session.completed_at else None,
                "duration_minutes": session.duration_minutes,
                "status": "completed" if session.completed_at else "in_progress",
                "summary": session.summary,
                "findings": [],
                "artifacts": [
                    {"type": "artifact_created", "id": a} for a in session.artifacts_created
                ] + [
                    {"type": "artifact_updated", "id": a} for a in session.artifacts_updated
                ],
                "metadata": {
                    "mode": session.mode,
                    "focus": session.focus,
                    "contradictions_addressed": session.contradictions_addressed,
                    "next_steps": session.next_steps
                }
            }
    raise FileNotFoundError(f"Synthesis session {session_id} not found")


async def _load_meta_reflection_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a meta-reflection session."""
    # Meta-reflection sessions are kept in memory
    if meta_reflection_runner_getter:
        runner = meta_reflection_runner_getter()
        if hasattr(runner, '_sessions') and session_id in runner._sessions:
            session = runner._sessions[session_id]
            artifacts = []
            for insight in getattr(session, 'insights_recorded', []):
                artifacts.append({
                    "type": "meta_insight",
                    "content": insight.get("content"),
                    "category": insight.get("category"),
                    "timestamp": insight.get("timestamp")
                })
            return {
                "session_id": session.id,
                "session_type": "meta_reflection",
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.completed_at.isoformat() if getattr(session, 'completed_at', None) else None,
                "duration_minutes": session.duration_minutes,
                "status": "completed" if getattr(session, 'completed_at', None) else "in_progress",
                "summary": getattr(session, 'summary', None),
                "findings": getattr(session, 'key_findings', []),
                "artifacts": artifacts,
                "metadata": {
                    "focus": session.focus,
                    "analyses_performed": getattr(session, 'analyses_performed', []),
                    "patterns_found": getattr(session, 'patterns_found', [])
                }
            }
    raise FileNotFoundError(f"Meta-reflection session {session_id} not found")


async def _load_growth_edge_session(session_id: str) -> Dict[str, Any]:
    """Load and normalize a growth edge session."""
    # Growth edge sessions are kept in memory
    if growth_edge_runner_getter:
        runner = growth_edge_runner_getter()
        if hasattr(runner, '_sessions') and session_id in runner._sessions:
            session = runner._sessions[session_id]
            artifacts = []
            for obs in getattr(session, 'observations', []):
                artifacts.append({
                    "type": "practice_observation",
                    "content": obs.get("observation"),
                    "edge_id": obs.get("edge_id"),
                    "timestamp": obs.get("timestamp")
                })
            for exercise in getattr(session, 'exercises_designed', []):
                artifacts.append({
                    "type": "practice_exercise",
                    "content": exercise.get("description"),
                    "exercise_type": exercise.get("type")
                })
            return {
                "session_id": session.id,
                "session_type": "growth_edge",
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "ended_at": session.completed_at.isoformat() if getattr(session, 'completed_at', None) else None,
                "duration_minutes": session.duration_minutes,
                "status": "completed" if getattr(session, 'completed_at', None) else "in_progress",
                "summary": getattr(session, 'summary', None),
                "findings": getattr(session, 'progress_notes', []),
                "artifacts": artifacts,
                "metadata": {
                    "focus": session.focus,
                    "edges_worked": getattr(session, 'edges_worked', []),
                    "progress_evaluations": getattr(session, 'progress_evaluations', [])
                }
            }
    raise FileNotFoundError(f"Growth edge session {session_id} not found")



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
    """Get all research notes created during a specific session (full content)"""
    if not research_manager:
        raise HTTPException(status_code=503, detail="Research manager not initialized")

    # Use full_content=True since we're displaying these notes in detail view
    notes = research_manager.list_research_notes(full_content=True)
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
