"""
Admin API - Stats, GitHub Metrics & Token Usage Routes
Extracted from admin_api.py for better organization.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, Dict
from datetime import datetime
from pydantic import BaseModel

from .auth import require_admin, require_auth

router = APIRouter(tags=["admin-stats"])

# Module-level references
_memory = None
_users = None
_github_metrics_manager = None
_token_usage_tracker = None


def init_managers(memory=None, users=None):
    """Initialize manager references."""
    global _memory, _users
    _memory = memory
    _users = users


def init_github_metrics(manager):
    """Initialize GitHub metrics manager."""
    global _github_metrics_manager
    _github_metrics_manager = manager


def init_token_tracker(tracker):
    """Initialize token usage tracker."""
    global _token_usage_tracker
    _token_usage_tracker = tracker


def get_effective_daemon_id(daemon_id: Optional[str] = None) -> str:
    """Get effective daemon ID."""
    if daemon_id:
        return daemon_id
    from database import get_daemon_id
    return get_daemon_id()


# ============== System Stats Endpoints ==============

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
            if _users:
                user_count = len(_users.list_users())

            # Get memory count (from ChromaDB - not daemon-specific for now)
            memory_count = 0
            if _memory:
                memory_count = _memory.collection.count()

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
    from self_model import SelfManager
    from conversations import ConversationManager

    # Use module-level refs if available, otherwise try to create
    memory = _memory
    users = _users
    conversations = None
    self_manager = None

    try:
        conversations = ConversationManager()
    except:
        pass

    try:
        self_manager = SelfManager()
    except:
        pass

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


# ============== User Endpoints ==============

@router.get("/users")
async def get_all_users(user: Dict = Depends(require_auth)):
    """Get all users with observation counts"""
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        all_users = _users.list_users()  # Returns List[Dict]
        user_list = []

        for u in all_users:
            user_id = u.get("user_id")
            profile = _users.load_profile(user_id)
            observations = _users.load_observations(user_id)

            user_list.append({
                "id": user_id,
                "display_name": u.get("display_name"),
                "observation_count": len(observations) if observations else 0,
                "created_at": u.get("created_at"),
                "is_admin": profile.is_admin if profile else False,
                "has_password": bool(profile.password_hash) if profile else False
            })

        return {"users": user_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}")
async def get_user_detail(user_id: str, user: Dict = Depends(require_auth)):
    """Get detailed user profile and observations"""
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        profile = _users.load_profile(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        observations = _users.load_observations(user_id)
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
async def get_user_observations(user_id: str, user: Dict = Depends(require_auth)):
    """Get observations for a specific user"""
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        observations = _users.load_observations(user_id)
        # Convert UserObservation objects to dicts
        obs_list = [obs.__dict__ if hasattr(obs, '__dict__') else obs for obs in (observations or [])]
        return {"observations": obs_list}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/model")
async def get_user_model(user_id: str, user: Dict = Depends(require_auth)):
    """Get the structured user model for a specific user"""
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        model = _users.load_user_model(user_id)
        if model:
            return {"user_model": model.to_dict()}
        return {"user_model": None}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/relationship")
async def get_relationship_model(user_id: str, user: Dict = Depends(require_auth)):
    """Get the relationship model for a specific user"""
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        model = _users.load_relationship_model(user_id)
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
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        success = _users.set_admin_status(user_id, request.is_admin)
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
    if not _users:
        raise HTTPException(status_code=503, detail="Users not initialized")

    try:
        success = _users.set_admin_password(user_id, request.password)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")

        return {"success": True}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============== GitHub Metrics Endpoints ==============

@router.get("/github/metrics")
async def get_github_metrics():
    """Get current GitHub metrics for all tracked repos"""
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    current = _github_metrics_manager.get_current_metrics()
    if not current:
        # No data yet, try to fetch
        try:
            snapshot = await _github_metrics_manager.refresh_metrics()
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
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    return _github_metrics_manager.get_aggregate_stats()


@router.get("/github/metrics/history")
async def get_github_history(
    days: int = Query(default=30, ge=0),
    repo: Optional[str] = Query(default=None)
):
    """Get historical GitHub metrics. Use days=0 for all time."""
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    # days=0 means all time
    history = _github_metrics_manager.get_historical_metrics(
        days=days if days > 0 else None,
        repo=repo
    )
    return {
        "days": days,
        "repo": repo,
        "data": history,
        "count": len(history)
    }


@router.get("/github/metrics/timeseries/{metric}")
async def get_github_timeseries(
    metric: str,
    days: int = Query(default=14, ge=0),
    repo: Optional[str] = Query(default=None)
):
    """Get time series data for a specific metric. Use days=0 for all time."""
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    valid_metrics = ["clones", "clones_uniques", "views", "views_uniques", "stars", "forks"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Must be one of: {valid_metrics}"
        )

    # days=0 means all time
    series = _github_metrics_manager.get_time_series(
        metric=metric,
        days=days if days > 0 else None,
        repo=repo
    )
    return {
        "metric": metric,
        "days": days,
        "repo": repo,
        "data": series
    }


@router.get("/github/metrics/alltime")
async def get_github_alltime_stats():
    """Get all-time aggregate statistics per repository"""
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    return _github_metrics_manager.get_all_time_repo_stats()


@router.post("/github/metrics/refresh")
async def refresh_github_metrics(admin: Dict = Depends(require_admin)):
    """Force refresh GitHub metrics (admin only)"""
    if not _github_metrics_manager:
        raise HTTPException(status_code=503, detail="GitHub metrics not initialized")

    try:
        snapshot = await _github_metrics_manager.refresh_metrics()
        return {
            "success": True,
            "timestamp": snapshot.timestamp,
            "repos": list(snapshot.repos.keys()),
            "api_calls_remaining": snapshot.api_calls_remaining
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh metrics: {e}")


# ============== Token Usage Endpoints ==============

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
    if not _token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    records = _token_usage_tracker.get_records(
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
    if not _token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

    return _token_usage_tracker.get_summary(start_date=start_dt, end_date=end_dt)


@router.get("/usage/timeseries")
async def get_usage_timeseries(
    metric: str = Query(default="total_tokens", description="Metric: total_tokens, input_tokens, output_tokens, cost, count"),
    days: int = Query(default=14, le=90),
    granularity: str = Query(default="day", description="Granularity: day or hour")
):
    """Get token usage time series data for charting"""
    if not _token_usage_tracker:
        raise HTTPException(status_code=503, detail="Token tracker not initialized")

    valid_metrics = ["total_tokens", "input_tokens", "output_tokens", "cost", "count"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Must be one of: {valid_metrics}"
        )

    if granularity not in ["day", "hour"]:
        raise HTTPException(status_code=400, detail="Granularity must be 'day' or 'hour'")

    series = _token_usage_tracker.get_timeseries(metric=metric, days=days, granularity=granularity)
    return {
        "metric": metric,
        "days": days,
        "granularity": granularity,
        "data": series
    }


# ============== Feedback Endpoints ==============

class FeedbackRequest(BaseModel):
    heard_from: Optional[str] = None
    message: Optional[str] = None


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: Dict = Depends(require_auth)
):
    """Submit user feedback"""
    from database import get_db

    with get_db() as conn:
        conn.execute("""
            INSERT INTO feedback (user_id, username, heard_from, message, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            current_user["user_id"],
            current_user["display_name"],
            request.heard_from,
            request.message,
            datetime.now().isoformat()
        ))
        conn.commit()

    return {"status": "ok", "message": "Thank you for your feedback!"}


@router.get("/feedback")
async def get_feedback(
    admin: Dict = Depends(require_admin)
):
    """Get all feedback (admin only)"""
    from database import get_db

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, user_id, username, heard_from, message, created_at
            FROM feedback
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

    return {
        "feedback": [
            {
                "id": row[0],
                "user_id": row[1],
                "username": row[2],
                "heard_from": row[3],
                "message": row[4],
                "created_at": row[5]
            }
            for row in rows
        ],
        "count": len(rows)
    }
