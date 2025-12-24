"""
Journal API Routes

Extracted from main_sdk.py as part of Phase 1 refactoring.
Handles journal generation, retrieval, and backfilling.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/journal", tags=["journals"])


# === Request Models ===

class JournalGenerateRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD format, defaults to today


class JournalBackfillRequest(BaseModel):
    days: int = 7  # How many days back to check


# === Dependencies (injected at startup) ===

_memory = None
_user_manager = None
_self_manager = None
_token_tracker = None
_anthropic_api_key = None
_generate_missing_journals = None


def init_journal_routes(
    memory,
    user_manager,
    self_manager,
    token_tracker,
    anthropic_api_key,
    generate_missing_journals
):
    """Initialize route dependencies. Called from main_sdk.py startup."""
    global _memory, _user_manager, _self_manager, _token_tracker
    global _anthropic_api_key, _generate_missing_journals
    _memory = memory
    _user_manager = user_manager
    _self_manager = self_manager
    _token_tracker = token_tracker
    _anthropic_api_key = anthropic_api_key
    _generate_missing_journals = generate_missing_journals


# === Journal Endpoints ===

@router.post("/generate")
async def generate_journal(request: JournalGenerateRequest):
    """
    Generate a journal entry for a specific date (or today).

    Uses summary chunks from that date to create a reflective journal entry
    in Cass's voice about what we did and how it made her feel.
    """
    if not _memory:
        raise HTTPException(status_code=503, detail="Memory system initializing, please wait")

    # Default to today if no date provided
    if request.date:
        date = request.date
    else:
        date = datetime.now().strftime("%Y-%m-%d")

    # Check if journal already exists for this date
    existing = _memory.get_journal_entry(date)
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
    summaries = _memory.get_summaries_by_date(date)
    conversations = _memory.get_conversations_by_date(date) if not summaries else []

    if not summaries and not conversations:
        raise HTTPException(
            status_code=404,
            detail=f"No memories found for {date}. Cannot generate journal."
        )

    # Generate the journal entry
    journal_text = await _memory.generate_journal_entry(
        date=date,
        anthropic_api_key=_anthropic_api_key,
        token_tracker=_token_tracker
    )

    if not journal_text:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate journal entry"
        )

    # Store the journal entry (generates summary via local LLM)
    entry_id = await _memory.store_journal_entry(
        date=date,
        journal_text=journal_text,
        summary_count=len(summaries),
        conversation_count=len(conversations)
    )

    # Generate user observations for each user who had conversations that day
    observations_added = 0
    user_ids_for_date = _memory.get_user_ids_by_date(date)
    for user_id in user_ids_for_date:
        profile = _user_manager.load_profile(user_id)
        if not profile:
            continue

        # Get conversations filtered to just this user
        user_conversations = _memory.get_conversations_by_date(date, user_id=user_id)
        if not user_conversations:
            continue

        conversation_text = "\n\n---\n\n".join([
            conv.get("content", "") for conv in user_conversations[:15]
        ])
        new_observations = await _memory.generate_user_observations(
            user_id=user_id,
            display_name=profile.display_name,
            conversation_text=conversation_text,
            anthropic_api_key=_anthropic_api_key
        )
        for obs_text in new_observations:
            obs = _user_manager.add_observation(user_id, obs_text)
            if obs:
                _memory.embed_user_observation(
                    user_id=user_id,
                    observation_id=obs.id,
                    observation_text=obs.observation,
                    display_name=profile.display_name,
                    timestamp=obs.timestamp
                )
                observations_added += 1

    # Extract self-observations from this journal
    self_observations_added = 0
    self_observations = await _memory.extract_self_observations_from_journal(
        journal_text=journal_text,
        journal_date=date,
        anthropic_api_key=_anthropic_api_key
    )
    for obs_data in self_observations:
        obs = _self_manager.add_observation(
            observation=obs_data["observation"],
            category=obs_data["category"],
            confidence=obs_data["confidence"],
            source_type="journal",
            source_journal_date=date,
            influence_source=obs_data["influence_source"]
        )
        if obs:
            _memory.embed_self_observation(
                observation_id=obs.id,
                observation_text=obs.observation,
                category=obs.category,
                confidence=obs.confidence,
                influence_source=obs.influence_source,
                timestamp=obs.timestamp
            )
            self_observations_added += 1

    return {
        "status": "created",
        "journal": {
            "id": entry_id,
            "date": date,
            "content": journal_text,
            "summaries_used": len(summaries),
            "conversations_used": len(conversations),
            "observations_added": observations_added,
            "self_observations_added": self_observations_added
        }
    }


@router.get("/{date}")
async def get_journal(date: str):
    """
    Get the journal entry for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
    """
    journal = _memory.get_journal_entry(date)

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


@router.get("")
async def list_journals(limit: int = 10):
    """
    Get recent journal entries.

    Args:
        limit: Maximum number of entries to return (default 10)
    """
    journals = _memory.get_recent_journals(n=limit)

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


@router.delete("/{date}")
async def delete_journal(date: str):
    """
    Delete a journal entry for a specific date.

    This allows regenerating the journal if needed.
    """
    journal = _memory.get_journal_entry(date)

    if not journal:
        raise HTTPException(
            status_code=404,
            detail=f"No journal entry found for {date}"
        )

    # Delete from collection
    _memory.collection.delete(ids=[journal["id"]])

    return {
        "status": "deleted",
        "date": date
    }


@router.get("/preview/{date}")
async def preview_journal_content(date: str):
    """
    Preview what content is available for generating a journal entry.

    Returns summaries and conversation counts without generating the journal.
    """
    summaries = _memory.get_summaries_by_date(date)
    conversations = _memory.get_conversations_by_date(date)
    existing_journal = _memory.get_journal_entry(date)

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


@router.post("/backfill")
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

    generated = await _generate_missing_journals(days_to_check=request.days)

    return {
        "status": "completed",
        "days_checked": request.days,
        "journals_generated": len(generated),
        "dates": generated
    }
