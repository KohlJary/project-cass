"""
Memory REST API routes
Memory storage, query, and export endpoints
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime

router = APIRouter(prefix="/memory", tags=["memory"])

# Dependencies - set by init_memory_routes
_memory = None


def init_memory_routes(memory):
    """Initialize the routes with dependencies"""
    global _memory
    _memory = memory


def _require_memory():
    """Get memory instance or raise error if not initialized"""
    if _memory is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Memory system initializing, please retry")
    return _memory


# Request models
class MemoryStoreRequest(BaseModel):
    user_message: str
    assistant_response: str
    metadata: Optional[Dict] = None


class MemoryQueryRequest(BaseModel):
    query: str
    n_results: int = 5


# Endpoints

@router.post("/store")
async def store_memory(request: MemoryStoreRequest):
    """Manually store conversation in memory"""
    memory = _require_memory()
    # store_conversation is async; without await nothing was stored and the
    # route returned a coroutine repr as the id.
    entry_id = await memory.store_conversation(
        user_message=request.user_message,
        assistant_response=request.assistant_response,
        metadata=request.metadata
    )
    return {"status": "stored", "id": entry_id}


@router.post("/query")
async def query_memory(request: MemoryQueryRequest):
    """Query memory for relevant entries"""
    memory = _require_memory()
    results = memory.retrieve_relevant(
        query=request.query,
        n_results=request.n_results
    )
    return {"results": results, "count": len(results)}


@router.get("/recent")
async def recent_memories(n: int = 10):
    """Get recent memories"""
    memory = _require_memory()
    return {"memories": memory.get_recent(n)}


@router.get("/export")
async def export_memories():
    """Export all memories"""
    import json
    from config import DATA_DIR

    memory = _require_memory()
    # export_memories() takes no path and returns the data (passing one was a
    # TypeError); write it out ourselves, under DATA_DIR rather than CWD.
    data = memory.export_memories()
    filepath = DATA_DIR / f"memory_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath.write_text(json.dumps(data, indent=2, default=str))
    return {"status": "exported", "filepath": str(filepath), "count": data.get("count", 0)}
