"""
Wiki REST API routes
Wiki page CRUD and graph operations
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Set
from datetime import datetime

router = APIRouter(prefix="/wiki", tags=["wiki"])

# Set by main app via init_wiki_routes
_wiki_storage = None
_memory = None


def init_wiki_routes(wiki_storage, memory=None):
    """Initialize the routes with dependencies"""
    global _wiki_storage, _memory
    _wiki_storage = wiki_storage
    _memory = memory  # CassMemory instance for embeddings


# === Request/Response Models ===

class CreatePageRequest(BaseModel):
    """Request body for creating a wiki page"""
    name: str
    content: str
    page_type: str = "concept"  # entity, concept, relationship, journal, meta


class UpdatePageRequest(BaseModel):
    """Request body for updating a wiki page"""
    content: str


class PageResponse(BaseModel):
    """Response model for a wiki page"""
    name: str
    content: str
    page_type: str
    title: str
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    links: List[str] = []  # Outgoing link targets


class PageSummary(BaseModel):
    """Lightweight page info for listings"""
    name: str
    title: str
    page_type: str
    modified_at: Optional[datetime] = None
    link_count: int = 0


class LinkInfo(BaseModel):
    """Information about a wikilink"""
    target: str
    section: Optional[str] = None
    alias: Optional[str] = None


# === Page CRUD Endpoints ===

@router.get("/pages")
async def list_pages(
    page_type: Optional[str] = Query(None, description="Filter by page type"),
) -> Dict[str, List[PageSummary]]:
    """List all wiki pages, optionally filtered by type"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import PageType

    pt = None
    if page_type:
        try:
            pt = PageType(page_type)
        except ValueError:
            valid = [p.value for p in PageType]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid page_type '{page_type}'. Valid types: {valid}"
            )

    pages = _wiki_storage.list_pages(pt)
    summaries = [
        PageSummary(
            name=p.name,
            title=p.title,
            page_type=p.page_type.value,
            modified_at=p.modified_at,
            link_count=len(p.links)
        )
        for p in pages
    ]

    return {"pages": summaries}


@router.post("/pages")
async def create_page(request: CreatePageRequest) -> Dict[str, PageResponse]:
    """Create a new wiki page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import PageType

    try:
        pt = PageType(request.page_type)
    except ValueError:
        valid = [p.value for p in PageType]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid page_type '{request.page_type}'. Valid types: {valid}"
        )

    try:
        page = _wiki_storage.create(
            name=request.name,
            content=request.content,
            page_type=pt
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail=f"Page '{request.name}' already exists"
        )

    # Embed the page for semantic search
    if _memory:
        _memory.embed_wiki_page(
            page_name=page.name,
            page_content=page.content,
            page_type=page.page_type.value,
            links=[link.target for link in page.links]
        )

    return {
        "page": PageResponse(
            name=page.name,
            content=page.content,
            page_type=page.page_type.value,
            title=page.title,
            created_at=page.created_at,
            modified_at=page.modified_at,
            links=[link.target for link in page.links]
        )
    }


@router.get("/pages/{page_name}")
async def get_page(page_name: str) -> Dict[str, PageResponse]:
    """Get a wiki page by name"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    return {
        "page": PageResponse(
            name=page.name,
            content=page.content,
            page_type=page.page_type.value,
            title=page.title,
            created_at=page.created_at,
            modified_at=page.modified_at,
            links=[link.target for link in page.links]
        )
    }


@router.put("/pages/{page_name}")
async def update_page(page_name: str, request: UpdatePageRequest) -> Dict[str, PageResponse]:
    """Update an existing wiki page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    page = _wiki_storage.update(name=page_name, content=request.content)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    # Re-embed the page for semantic search
    if _memory:
        _memory.embed_wiki_page(
            page_name=page.name,
            page_content=page.content,
            page_type=page.page_type.value,
            links=[link.target for link in page.links]
        )

    return {
        "page": PageResponse(
            name=page.name,
            content=page.content,
            page_type=page.page_type.value,
            title=page.title,
            created_at=page.created_at,
            modified_at=page.modified_at,
            links=[link.target for link in page.links]
        )
    }


@router.delete("/pages/{page_name}")
async def delete_page(page_name: str) -> Dict[str, str]:
    """Delete a wiki page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    deleted = _wiki_storage.delete(page_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    # Remove embeddings
    if _memory:
        _memory.remove_wiki_page_embeddings(page_name)

    return {"status": "deleted", "page": page_name}


# === Link Endpoints ===

@router.get("/pages/{page_name}/links")
async def get_page_links(page_name: str) -> Dict[str, List[LinkInfo]]:
    """Get outgoing links from a page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    links = [
        LinkInfo(
            target=link.target,
            section=link.section,
            alias=link.alias
        )
        for link in page.links
    ]

    return {"links": links}


@router.get("/pages/{page_name}/backlinks")
async def get_page_backlinks(page_name: str) -> Dict[str, List[PageSummary]]:
    """Get pages that link to this page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Check page exists
    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    backlinks = _wiki_storage.get_backlinks(page_name)
    summaries = [
        PageSummary(
            name=p.name,
            title=p.title,
            page_type=p.page_type.value,
            modified_at=p.modified_at,
            link_count=len(p.links)
        )
        for p in backlinks
    ]

    return {"backlinks": summaries}


# === Graph Endpoints ===

@router.get("/graph")
async def get_link_graph() -> Dict[str, Dict[str, List[str]]]:
    """Get the full wiki link graph for visualization"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    graph = _wiki_storage.get_link_graph()
    # Convert sets to lists for JSON serialization
    serializable = {name: list(targets) for name, targets in graph.items()}

    return {"graph": serializable}


@router.get("/graph/orphans")
async def get_orphan_pages() -> Dict[str, List[PageSummary]]:
    """Get pages with no incoming links"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    orphans = _wiki_storage.find_orphans()
    summaries = [
        PageSummary(
            name=p.name,
            title=p.title,
            page_type=p.page_type.value,
            modified_at=p.modified_at,
            link_count=len(p.links)
        )
        for p in orphans
    ]

    return {"orphans": summaries}


@router.get("/graph/broken")
async def get_broken_links() -> Dict[str, List[Dict[str, str]]]:
    """Get links pointing to non-existent pages"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    broken = _wiki_storage.find_broken_links()
    result = [
        {"source": page.name, "target": target}
        for page, target in broken
    ]

    return {"broken_links": result}


# === Search Endpoints ===

@router.get("/search")
async def search_pages(
    q: str = Query(..., min_length=1, description="Search query"),
    page_type: Optional[str] = Query(None, description="Filter by page type"),
) -> Dict[str, List[PageSummary]]:
    """Search wiki pages by content"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import PageType

    pt = None
    if page_type:
        try:
            pt = PageType(page_type)
        except ValueError:
            valid = [p.value for p in PageType]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid page_type '{page_type}'. Valid types: {valid}"
            )

    results = _wiki_storage.search(q, pt)
    summaries = [
        PageSummary(
            name=p.name,
            title=p.title,
            page_type=p.page_type.value,
            modified_at=p.modified_at,
            link_count=len(p.links)
        )
        for p in results
    ]

    return {"results": summaries}


@router.get("/search/semantic")
async def semantic_search_pages(
    q: str = Query(..., min_length=1, description="Semantic search query"),
    page_type: Optional[str] = Query(None, description="Filter by page type"),
    n_results: int = Query(5, ge=1, le=20, description="Number of results"),
) -> Dict[str, List[Dict]]:
    """Semantic search wiki pages using embeddings"""
    if _memory is None:
        raise HTTPException(status_code=503, detail="Memory system not initialized")

    results = _memory.retrieve_wiki_context(
        query=q,
        n_results=n_results,
        page_type=page_type
    )

    return {"results": results}


# === History Endpoints ===

@router.get("/pages/{page_name}/history")
async def get_page_history(page_name: str) -> Dict[str, List[Dict[str, str]]]:
    """Get git history for a page"""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Check page exists
    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    history = _wiki_storage.get_page_history(page_name)
    return {"history": history}


# === Bootstrap Endpoints ===

# Set by main app
_data_dir = None


def set_data_dir(data_dir):
    """Set the data directory for bootstrap operations."""
    global _data_dir
    _data_dir = data_dir


@router.post("/bootstrap/seed", response_model=None)
async def bootstrap_seed():
    """Create minimal seed pages for a fresh wiki installation."""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")
    if _data_dir is None:
        raise HTTPException(status_code=503, detail="Data directory not configured")

    from wiki import WikiBootstrap

    bootstrap = WikiBootstrap(_wiki_storage, _data_dir)
    results = bootstrap.seed_fresh_install()

    # Embed newly created pages
    if _memory:
        for page in _wiki_storage.list_pages():
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=[link.target for link in page.links]
            )

    return {"status": "success", "created": results}


@router.post("/bootstrap/self-model", response_model=None)
async def bootstrap_self_model():
    """Bootstrap wiki from existing self-model data (self_profile.yaml, etc.)."""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")
    if _data_dir is None:
        raise HTTPException(status_code=503, detail="Data directory not configured")

    from wiki import WikiBootstrap

    bootstrap = WikiBootstrap(_wiki_storage, _data_dir)
    results = bootstrap.bootstrap_from_self_model()

    # Embed newly created/updated pages
    if _memory:
        for page in _wiki_storage.list_pages():
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=[link.target for link in page.links]
            )

    return {"status": "success", "created": results}


@router.post("/bootstrap/users", response_model=None)
async def bootstrap_users():
    """Create wiki pages for existing users."""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")
    if _data_dir is None:
        raise HTTPException(status_code=503, detail="Data directory not configured")

    from wiki import WikiBootstrap

    bootstrap = WikiBootstrap(_wiki_storage, _data_dir)
    results = bootstrap.bootstrap_user_pages()

    # Embed newly created pages
    if _memory:
        for page in _wiki_storage.list_pages():
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=[link.target for link in page.links]
            )

    return {"status": "success", "created": results}


@router.post("/bootstrap/full", response_model=None)
async def bootstrap_full(include_users: bool = True):
    """Run full bootstrap: seed pages, self-model data, and optionally users."""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")
    if _data_dir is None:
        raise HTTPException(status_code=503, detail="Data directory not configured")

    from wiki import WikiBootstrap

    bootstrap = WikiBootstrap(_wiki_storage, _data_dir)
    results = bootstrap.full_bootstrap(include_users=include_users)

    # Embed all pages
    if _memory:
        for page in _wiki_storage.list_pages():
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=[link.target for link in page.links]
            )

    return {"status": "success", "results": results}


# === Retrieval Endpoints ===

@router.get("/retrieve/entry-points")
async def find_entry_points(
    q: str = Query(..., min_length=1, description="Query to find entry points for"),
    n_results: int = Query(3, ge=1, le=10, description="Number of entry points"),
) -> Dict:
    """Find relevant wiki pages as starting points for context retrieval."""
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import WikiRetrieval

    retrieval = WikiRetrieval(_wiki_storage, _memory)
    results = retrieval.find_entry_points(q, n_results=n_results)

    return {
        "entry_points": [
            {
                "name": r.page.name,
                "title": r.page.title,
                "type": r.page.page_type.value,
                "relevance": r.relevance_score,
            }
            for r in results
        ]
    }


@router.get("/retrieve/context")
async def retrieve_context(
    q: str = Query(..., min_length=1, description="Query to retrieve context for"),
    n_entry_points: int = Query(3, ge=1, le=5, description="Number of entry points"),
    max_depth: int = Query(2, ge=0, le=3, description="Maximum link traversal depth"),
    max_pages: int = Query(10, ge=1, le=20, description="Maximum pages to include"),
    max_tokens: int = Query(2000, ge=500, le=8000, description="Token budget for synthesis"),
) -> Dict:
    """
    Full context retrieval: find entry points, traverse links, synthesize.

    Returns both the synthesized context and details about pages found.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import WikiRetrieval

    retrieval = WikiRetrieval(_wiki_storage, _memory)
    context = retrieval.retrieve_context(
        query=q,
        n_entry_points=n_entry_points,
        max_depth=max_depth,
        max_pages=max_pages,
        max_tokens=max_tokens
    )

    return {
        "synthesis": context.synthesis,
        "entry_points": context.entry_points,
        "pages": [
            {
                "name": r.page.name,
                "title": r.page.title,
                "type": r.page.page_type.value,
                "relevance": r.relevance_score,
                "depth": r.depth,
                "path": r.path,
            }
            for r in context.pages
        ],
        "stats": {
            "total_pages": context.total_pages_visited,
            "retrieval_time_ms": context.retrieval_time_ms,
            "stopped_early": context.stopped_early,
            "avg_novelty": sum(context.novelty_scores) / len(context.novelty_scores) if context.novelty_scores else 0,
        }
    }


# === Post-Conversation Wiki Updates ===

class AnalyzeConversationRequest(BaseModel):
    """Request to analyze a conversation for wiki updates."""
    messages: List[Dict]
    auto_apply: bool = False
    min_confidence: float = 0.7


@router.post("/analyze-conversation")
async def analyze_conversation_for_wiki(request: AnalyzeConversationRequest) -> Dict:
    """
    Analyze a conversation for potential wiki updates.

    Extracts entities, concepts, and suggests wiki page creations/updates.
    Can optionally auto-apply high-confidence suggestions.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import process_conversation_for_wiki

    result = await process_conversation_for_wiki(
        wiki_storage=_wiki_storage,
        messages=request.messages,
        memory=_memory,
        auto_apply=request.auto_apply,
        min_confidence=request.min_confidence
    )

    return result


@router.post("/analyze-conversation/{conversation_id}")
async def analyze_conversation_by_id(
    conversation_id: str,
    auto_apply: bool = False,
    min_confidence: float = 0.7
) -> Dict:
    """
    Analyze a specific conversation (by ID) for wiki updates.

    Loads the conversation from storage and analyzes it.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Load conversation
    from conversations import ConversationManager
    conv_manager = ConversationManager()
    conversation = conv_manager.load_conversation(conversation_id)

    if not conversation:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")

    messages = conversation.get("messages", [])
    if not messages:
        return {
            "entities_found": [],
            "concepts_found": [],
            "suggestions": [],
            "message": "No messages in conversation"
        }

    from wiki import process_conversation_for_wiki

    result = await process_conversation_for_wiki(
        wiki_storage=_wiki_storage,
        messages=messages,
        memory=_memory,
        auto_apply=auto_apply,
        min_confidence=min_confidence
    )

    result["conversation_id"] = conversation_id
    result["messages_analyzed"] = len(messages)

    return result
