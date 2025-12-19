"""
Testing API - Memory Coherence Test Routes
Extracted from routes/testing.py for better organization.
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel

router = APIRouter(tags=["testing-memory"])

# Module-level reference - set by init function
_memory_coherence_tests = None


def init_memory(memory_coherence_tests):
    """Initialize module dependencies."""
    global _memory_coherence_tests
    _memory_coherence_tests = memory_coherence_tests


# ============== Pydantic Models ==============

class RunMemoryTestsRequest(BaseModel):
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    label: str = "memory_test"


class SummaryFactsTestRequest(BaseModel):
    conversation_id: str
    expected_facts: List[str]


class VectorRetrievalTestRequest(BaseModel):
    query: str
    expected_keywords: List[str]
    n_results: int = 5


# ============== Memory Coherence Test Endpoints ==============

@router.post("/memory/run")
async def run_memory_tests(request: RunMemoryTestsRequest):
    """
    Run the basic memory coherence test suite.

    Tests message persistence, chronological order, summary quality,
    user model consistency, self-model coherence, and vector retrieval.
    """
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = _memory_coherence_tests.run_basic_suite(
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        label=request.label,
    )

    return {"result": result.to_dict()}


@router.post("/memory/test/summary-facts")
async def test_summary_facts(request: SummaryFactsTestRequest):
    """Test that a conversation summary captures expected key facts."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = _memory_coherence_tests.test_summary_captures_key_facts(
        conversation_id=request.conversation_id,
        expected_facts=request.expected_facts,
    )

    return {"result": result.to_dict()}


@router.post("/memory/test/vector-retrieval")
async def test_vector_retrieval(request: VectorRetrievalTestRequest):
    """Test that vector retrieval returns relevant results for a query."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    result = _memory_coherence_tests.test_vector_retrieval_relevance(
        query=request.query,
        expected_keywords=request.expected_keywords,
        n_results=request.n_results,
    )

    return {"result": result.to_dict()}


@router.get("/memory/test/self-model")
async def test_self_model():
    """Run self-model coherence tests."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        _memory_coherence_tests.test_self_observations_coherence(),
        _memory_coherence_tests.test_milestone_progression(),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/test/conversation/{conversation_id}")
async def test_conversation(conversation_id: str):
    """Run all tests for a specific conversation."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        _memory_coherence_tests.test_message_persistence(conversation_id),
        _memory_coherence_tests.test_chronological_order(conversation_id),
        _memory_coherence_tests.test_summary_length_appropriate(conversation_id),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/test/user/{user_id}")
async def test_user_model(user_id: str):
    """Run all tests for a specific user's model."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = [
        _memory_coherence_tests.test_user_profile_completeness(user_id),
        _memory_coherence_tests.test_user_observations_consistency(user_id),
    ]

    return {"results": [r.to_dict() for r in results]}


@router.get("/memory/history")
async def get_memory_test_history(limit: int = 10):
    """Get recent memory coherence test results."""
    if not _memory_coherence_tests:
        raise HTTPException(status_code=503, detail="Memory coherence tests not initialized")

    results = _memory_coherence_tests.get_results_history(limit=limit)

    return {"results": results, "count": len(results)}
