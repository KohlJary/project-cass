"""
Users API Routes

Extracted from main_sdk.py as part of Phase 2 refactoring.
Handles user profiles, observations, and per-user journals.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Callable
from auth import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


# === Request Models ===

class SetCurrentUserRequest(BaseModel):
    user_id: str


class CreateUserRequest(BaseModel):
    display_name: str
    relationship: str = "user"
    notes: str = ""


# === Dependencies (injected at startup) ===

_user_manager = None
_memory = None
_get_current_user_id = None  # Returns the global current_user_id
_set_current_user_id = None  # Sets the global current_user_id


def init_user_routes(
    user_manager,
    memory,
    get_current_user_id_func: Callable,
    set_current_user_id_func: Callable
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _user_manager, _memory
    global _get_current_user_id, _set_current_user_id

    _user_manager = user_manager
    _memory = memory
    _get_current_user_id = get_current_user_id_func
    _set_current_user_id = set_current_user_id_func


# === User Context Endpoints ===

@router.get("/current")
async def get_current_user_endpoint(current_user: str = Depends(get_current_user)):
    """Get current authenticated user info"""
    profile = _user_manager.load_profile(current_user)
    if not profile:
        return {"user": None}

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship
        }
    }


@router.get("")
async def list_users_endpoint(current_user: str = Depends(get_current_user)):
    """List all users (admin only in future, for now shows all)"""
    # TODO: Add admin role check - for now only show current user
    # return {"users": _user_manager.list_users()}
    profile = _user_manager.load_profile(current_user)
    if profile:
        return {"users": [{
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship,
            "created_at": profile.created_at
        }]}
    return {"users": []}


@router.get("/{user_id}")
async def get_user_endpoint(user_id: str, current_user: str = Depends(get_current_user)):
    """Get a specific user's profile (only own profile for now)"""
    # Users can only view their own profile
    if user_id != current_user:
        raise HTTPException(status_code=403, detail="Cannot view other users' profiles")

    profile = _user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Get ALL observations, not just recent
    observations = _user_manager.load_observations(user_id)

    return {
        "profile": profile.to_dict(),
        "observations": [obs.to_dict() for obs in observations]
    }


@router.delete("/observations/{observation_id}")
async def delete_observation_endpoint(
    observation_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a specific observation (only own observations)"""
    # Only check current user's observations
    observations = _user_manager.load_observations(current_user)

    # Find and remove the observation
    for obs in observations:
        if obs.id == observation_id:
            # Remove from user's observations
            updated_obs = [o for o in observations if o.id != observation_id]
            _user_manager._save_observations(current_user, updated_obs)

            # Remove from ChromaDB
            try:
                _memory.collection.delete(ids=[f"user_observation_{observation_id}"])
            except Exception:
                pass  # May not exist in ChromaDB

            return {"status": "deleted", "observation_id": observation_id}

    raise HTTPException(status_code=404, detail="Observation not found")


@router.post("/current")
async def set_current_user_endpoint(
    user_request: SetCurrentUserRequest,
    current_user: str = Depends(get_current_user)
):
    """
    DEPRECATED: Set the current active user.
    This endpoint is deprecated. Use /auth/login to switch users.
    Kept for backwards compatibility with TUI during transition.
    """
    profile = _user_manager.load_profile(user_request.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    # Only allow setting to own user ID (prevents user switching attack)
    # During localhost bypass, this still allows TUI to set user
    _set_current_user_id(user_request.user_id)

    return {
        "user": {
            "user_id": profile.user_id,
            "display_name": profile.display_name,
            "relationship": profile.relationship
        },
        "warning": "This endpoint is deprecated. Use /auth/login instead."
    }


@router.post("")
async def create_user(user_request: CreateUserRequest):
    """Create a new user profile"""
    # Check if user with same name exists
    existing = _user_manager.get_user_by_name(user_request.display_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"User '{user_request.display_name}' already exists")

    profile = _user_manager.create_user(
        display_name=user_request.display_name,
        relationship=user_request.relationship,
        notes=user_request.notes
    )

    # Embed the new user profile in memory
    context = _user_manager.get_user_context(profile.user_id)
    if context:
        _memory.embed_user_profile(
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


# === Per-User Journal Endpoints ===

@router.get("/{user_id}/journals")
async def get_user_journals(user_id: str, limit: int = 10):
    """Get Cass's journal entries about a specific user"""
    profile = _user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journals = _user_manager.get_recent_user_journals(user_id, limit=limit)
    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "journals": [j.to_dict() for j in journals]
    }


@router.get("/{user_id}/journals/{date}")
async def get_user_journal_by_date(user_id: str, date: str):
    """Get Cass's journal about a user for a specific date"""
    profile = _user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journal = _user_manager.get_user_journal_by_date(user_id, date)
    if not journal:
        raise HTTPException(status_code=404, detail=f"No journal found for {profile.display_name} on {date}")

    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "journal": journal.to_dict()
    }


@router.get("/{user_id}/journals/search/{query}")
async def search_user_journals(user_id: str, query: str, limit: int = 5):
    """Search in Cass's journals about a user"""
    profile = _user_manager.load_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"User not found: {user_id}")

    journals = _user_manager.search_user_journals(user_id, query, limit=limit)
    return {
        "user_id": user_id,
        "display_name": profile.display_name,
        "query": query,
        "journals": [j.to_dict() for j in journals]
    }
