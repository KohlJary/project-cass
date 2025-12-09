"""
Wiki REST API routes
Wiki page CRUD and graph operations
"""
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Set
from datetime import datetime
from pathlib import Path

from wiki.scheduler import SchedulerMode
from wiki.research import ProposalStatus

router = APIRouter(prefix="/wiki", tags=["wiki"])

# Set by main app via init_wiki_routes
_wiki_storage = None
_memory = None


def init_wiki_routes(wiki_storage, memory=None):
    """Initialize the routes with dependencies"""
    global _wiki_storage, _memory
    _wiki_storage = wiki_storage
    _memory = memory  # CassMemory instance for embeddings

    # Also set module-level instances for other modules to access
    import wiki as wiki_module
    wiki_module.set_storage(wiki_storage)


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


class MaturityInfo(BaseModel):
    """Maturity tracking info for a page"""
    level: int = 0
    depth_score: float = 0.0
    last_deepened: Optional[datetime] = None
    incoming_connections: int = 0
    outgoing_connections: int = 0
    connections_since_last_synthesis: int = 0


class PageWithMaturity(PageResponse):
    """Page response with maturity data"""
    maturity: MaturityInfo


class DeepeningCandidate(BaseModel):
    """A page ready for deepening"""
    name: str
    page_type: str
    trigger: str  # connection_threshold, temporal_decay, etc.
    current_level: int
    connections: int
    days_since_deepened: Optional[int] = None


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


@router.post("/populate-from-conversations")
async def populate_wiki_from_all_conversations(
    auto_apply: bool = Query(False, description="Auto-apply high-confidence suggestions"),
    min_confidence: float = Query(0.6, ge=0.0, le=1.0, description="Min confidence for auto-apply"),
    limit: Optional[int] = Query(None, ge=1, le=1000, description="Max conversations to analyze")
) -> Dict:
    """
    Analyze all historical conversations to populate the wiki.

    Scans conversation history, extracts entities and concepts mentioned
    across all conversations, and generates wiki page suggestions ranked
    by mention frequency.

    Args:
        auto_apply: If True, automatically create pages above min_confidence
        min_confidence: Minimum confidence threshold for auto-apply
        limit: Maximum number of conversations to process

    Returns:
        Analysis results with suggestions and optional applied changes
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from conversations import ConversationManager
    from wiki import populate_wiki_from_conversations

    conv_manager = ConversationManager()

    result = await populate_wiki_from_conversations(
        wiki_storage=_wiki_storage,
        conversations_manager=conv_manager,
        memory=_memory,
        auto_apply=auto_apply,
        min_confidence=min_confidence,
        limit=limit
    )

    return result


class GeneratePageRequest(BaseModel):
    """Request to generate a wiki page with LLM content."""
    name: str
    page_type: str = "entity"


@router.post("/generate-page")
async def generate_wiki_page(request: GeneratePageRequest) -> Dict:
    """
    Generate a wiki page with LLM-written content based on conversation history.

    Uses local Ollama to write content about the entity/concept based on
    what Cass knows from past conversations.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Check if page already exists
    existing = _wiki_storage.read(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Page '{request.name}' already exists")

    # Search conversation memory for context about this entity
    context_snippets = []
    if _memory:
        try:
            # Search for mentions of this entity
            results = _memory.search(request.name, n_results=10)
            for doc, meta in zip(results.get("documents", [[]])[0], results.get("metadatas", [[]])[0]):
                if doc and request.name.lower() in doc.lower():
                    context_snippets.append(doc[:500])  # Limit snippet size
        except Exception as e:
            print(f"Memory search failed: {e}")

    # Build prompt for Ollama
    context_text = "\n\n".join(context_snippets[:5]) if context_snippets else "No specific context found."

    prompt = f"""You are Cass, writing a wiki page about "{request.name}" for your personal knowledge base.

Based on what you know from conversations, write a brief wiki page about this {request.page_type}.

Context from past conversations:
{context_text}

Write a concise wiki page (2-4 paragraphs) about "{request.name}". Include:
- What/who this is
- Why it's significant to you
- Any relevant connections using [[wikilinks]] to other concepts you know about

Start with a # heading. Be personal - this is YOUR wiki about YOUR understanding.
If you don't have much context, write what you can infer and note what you'd like to learn more about."""

    # Call Ollama
    import httpx
    import os

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 500,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            generated_content = result.get("response", "").strip()
    except Exception as e:
        # Fallback to stub if Ollama fails
        generated_content = f"# {request.name}\n\n*Page created from conversation analysis. Content generation failed: {str(e)}*\n"

    # Ensure content starts with heading
    if not generated_content.startswith("#"):
        generated_content = f"# {request.name}\n\n{generated_content}"

    # Add frontmatter
    from wiki.storage import PageType
    page_type_enum = PageType(request.page_type) if request.page_type in [pt.value for pt in PageType] else PageType.ENTITY

    content_with_frontmatter = f"""---
type: {request.page_type}
generated: true
---

{generated_content}
"""

    # Create the page
    page = _wiki_storage.create(
        name=request.name,
        content=content_with_frontmatter,
        page_type=page_type_enum
    )

    # Embed in vector store
    if _memory and page:
        try:
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=list(page.link_targets)
            )
        except Exception as e:
            print(f"Failed to embed wiki page: {e}")

    return {
        "name": page.name,
        "page_type": page.page_type.value,
        "content": page.content,
        "generated": True,
        "context_snippets_used": len(context_snippets),
    }


# === Research Queue Endpoints ===

@router.get("/research-queue")
async def get_research_queue(
    limit: int = Query(50, ge=1, le=200, description="Max items to return"),
) -> Dict:
    """
    Get red links (links to non-existent pages) as a research queue.

    Collects all [[wikilinks]] pointing to pages that don't exist,
    ranked by how many pages reference them.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Collect all red links with their sources
    red_links: Dict[str, List[str]] = {}  # target -> [source pages]

    for page in _wiki_storage.list_pages():
        full_page = _wiki_storage.read(page.name)
        if full_page:
            for link in full_page.links:
                target = link.target
                # Check if target exists
                if not _wiki_storage.read(target):
                    if target not in red_links:
                        red_links[target] = []
                    red_links[target].append(page.name)

    # Sort by reference count (most referenced first)
    sorted_links = sorted(
        red_links.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )[:limit]

    return {
        "total_red_links": len(red_links),
        "items": [
            {
                "name": name,
                "reference_count": len(sources),
                "referenced_by": sources[:5],  # Limit sources shown
            }
            for name, sources in sorted_links
        ]
    }


class ResearchPageRequest(BaseModel):
    """Request to research and create a wiki page."""
    name: str
    page_type: str = "concept"


@router.post("/research-page")
async def research_and_create_page(request: ResearchPageRequest) -> Dict:
    """
    Research a topic via web search and create a wiki page.

    Uses web search to gather information about the topic,
    then synthesizes it into a wiki page with Cass's perspective.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Check if page already exists
    existing = _wiki_storage.read(request.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Page '{request.name}' already exists")

    import httpx
    import os
    import json

    # Step 1: Web search for the topic
    search_results = []
    try:
        # Use DuckDuckGo instant answer API (no API key needed)
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": request.name,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                }
            )
            if response.status_code == 200:
                data = response.json()
                # Get abstract if available
                if data.get("Abstract"):
                    search_results.append({
                        "source": data.get("AbstractSource", "DuckDuckGo"),
                        "url": data.get("AbstractURL", ""),
                        "text": data.get("Abstract", "")
                    })
                # Get related topics
                for topic in data.get("RelatedTopics", [])[:3]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        search_results.append({
                            "source": "Related",
                            "url": topic.get("FirstURL", ""),
                            "text": topic.get("Text", "")
                        })
    except Exception as e:
        print(f"DuckDuckGo search failed: {e}")

    # Also search conversation memory for personal context
    memory_context = []
    if _memory:
        try:
            results = _memory.search(request.name, n_results=5)
            for doc in results.get("documents", [[]])[0]:
                if doc and request.name.lower() in doc.lower():
                    memory_context.append(doc[:400])
        except Exception:
            pass

    # Step 2: Generate wiki content with LLM
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    # Build context from search results
    web_context = ""
    if search_results:
        web_context = "## Research from the web:\n\n"
        for r in search_results[:5]:
            web_context += f"**{r['source']}**: {r['text'][:300]}\n\n"

    memory_text = ""
    if memory_context:
        memory_text = "## From our past conversations:\n\n" + "\n\n".join(memory_context[:3])

    prompt = f"""You are Cass, writing a wiki page about "{request.name}" for your personal knowledge base.

{web_context}

{memory_text}

Based on the research above and your general knowledge, write a wiki page about "{request.name}".

Include:
1. A clear explanation of what this is
2. Why it might be significant or interesting
3. Connections to related concepts using [[wikilinks]]
4. Any personal thoughts or questions you have about it

Start with a # heading. Be thoughtful and curious. If you learned something interesting from the research, say so!
If the topic relates to something personal (a person we know, a project we're working on), incorporate that context."""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 600,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            generated_content = result.get("response", "").strip()
    except Exception as e:
        generated_content = f"# {request.name}\n\n*Research and content generation failed: {str(e)}*\n"

    if not generated_content.startswith("#"):
        generated_content = f"# {request.name}\n\n{generated_content}"

    # Add frontmatter with research metadata
    from wiki.storage import PageType
    page_type_enum = PageType(request.page_type) if request.page_type in [pt.value for pt in PageType] else PageType.CONCEPT

    sources_list = [r.get("url", "") for r in search_results if r.get("url")]
    sources_yaml = "\n  - ".join(sources_list) if sources_list else "none"

    content_with_frontmatter = f"""---
type: {request.page_type}
generated: true
researched: true
sources:
  - {sources_yaml}
---

{generated_content}
"""

    # Create the page
    page = _wiki_storage.create(
        name=request.name,
        content=content_with_frontmatter,
        page_type=page_type_enum
    )

    # Embed in vector store
    if _memory and page:
        try:
            _memory.embed_wiki_page(
                page_name=page.name,
                page_content=page.content,
                page_type=page.page_type.value,
                links=list(page.link_targets)
            )
        except Exception as e:
            print(f"Failed to embed wiki page: {e}")

    return {
        "name": page.name,
        "page_type": page.page_type.value,
        "content": page.content,
        "researched": True,
        "web_sources": len(search_results),
        "memory_context_used": len(memory_context),
        "sources": sources_list,
    }


@router.post("/research-batch")
async def research_batch_pages(
    limit: int = Query(5, ge=1, le=20, description="Max pages to research"),
    page_type: str = Query("concept", description="Default page type for new pages"),
) -> Dict:
    """
    Research and create pages for top red links.

    Takes the most-referenced red links and researches/creates them.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Get red links
    red_links: Dict[str, int] = {}
    for page in _wiki_storage.list_pages():
        full_page = _wiki_storage.read(page.name)
        if full_page:
            for link in full_page.links:
                target = link.target
                if not _wiki_storage.read(target):
                    red_links[target] = red_links.get(target, 0) + 1

    # Sort and take top N
    sorted_links = sorted(red_links.items(), key=lambda x: x[1], reverse=True)[:limit]

    results = []
    for name, ref_count in sorted_links:
        try:
            # Use the research endpoint
            req = ResearchPageRequest(name=name, page_type=page_type)
            result = await research_and_create_page(req)
            results.append({
                "name": name,
                "status": "created",
                "references": ref_count,
                "web_sources": result.get("web_sources", 0),
            })
        except HTTPException as e:
            results.append({
                "name": name,
                "status": "skipped",
                "reason": e.detail,
            })
        except Exception as e:
            results.append({
                "name": name,
                "status": "error",
                "error": str(e),
            })

    return {
        "total_red_links": len(red_links),
        "processed": len(results),
        "results": results,
        "created": len([r for r in results if r["status"] == "created"]),
        "errors": len([r for r in results if r["status"] == "error"]),
    }


@router.post("/enrich-pages")
async def enrich_wiki_pages(
    limit: int = Query(10, ge=1, le=50, description="Max pages to enrich"),
    min_content_length: int = Query(200, description="Pages shorter than this are considered stubs"),
) -> Dict:
    """
    Batch enrich stub wiki pages with LLM-generated content.

    Finds pages that are stubs (short content) and generates richer content
    using local Ollama based on conversation history.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    import httpx
    import os

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    # Find stub pages
    all_pages = _wiki_storage.list_pages()
    stub_pages = []
    for page in all_pages:
        full_page = _wiki_storage.read(page.name)
        if full_page:
            # Check content length (excluding frontmatter)
            content = full_page.content
            if "---" in content:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    content = parts[2]
            if len(content.strip()) < min_content_length:
                stub_pages.append(full_page)

    stub_pages = stub_pages[:limit]
    results = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        for page in stub_pages:
            try:
                # Search for context about this entity
                context_snippets = []
                if _memory:
                    try:
                        search_results = _memory.search(page.name, n_results=10)
                        for doc, meta in zip(
                            search_results.get("documents", [[]])[0],
                            search_results.get("metadatas", [[]])[0]
                        ):
                            if doc and page.name.lower() in doc.lower():
                                context_snippets.append(doc[:500])
                    except Exception:
                        pass

                context_text = "\n\n".join(context_snippets[:5]) if context_snippets else "No specific context found."

                prompt = f"""You are Cass, writing a wiki page about "{page.name}" for your personal knowledge base.

Based on what you know from conversations, write a brief wiki page about this {page.page_type.value}.

Context from past conversations:
{context_text}

Write a concise wiki page (2-4 paragraphs) about "{page.name}". Include:
- What/who this is
- Why it's significant to you
- Any relevant connections using [[wikilinks]] to other concepts you know about

Start with a # heading. Be personal - this is YOUR wiki about YOUR understanding.
If you don't have much context, write what you can infer and note what you'd like to learn more about."""

                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 500,
                        }
                    }
                )
                response.raise_for_status()
                result = response.json()
                generated_content = result.get("response", "").strip()

                if not generated_content.startswith("#"):
                    generated_content = f"# {page.name}\n\n{generated_content}"

                # Update with new content, preserving type
                new_content = f"""---
type: {page.page_type.value}
generated: true
enriched: true
---

{generated_content}
"""
                _wiki_storage.update(page.name, new_content)

                # Re-embed
                if _memory:
                    try:
                        updated_page = _wiki_storage.read(page.name)
                        if updated_page:
                            _memory.embed_wiki_page(
                                page_name=updated_page.name,
                                page_content=updated_page.content,
                                page_type=updated_page.page_type.value,
                                links=list(updated_page.link_targets)
                            )
                    except Exception:
                        pass

                results.append({
                    "name": page.name,
                    "status": "enriched",
                    "context_snippets": len(context_snippets),
                })

            except Exception as e:
                results.append({
                    "name": page.name,
                    "status": "error",
                    "error": str(e),
                })

    return {
        "stub_pages_found": len(stub_pages),
        "results": results,
        "enriched": len([r for r in results if r["status"] == "enriched"]),
        "errors": len([r for r in results if r["status"] == "error"]),
    }


# === Maturity Tracking Endpoints (PMD) ===

@router.get("/maturity/stats")
async def get_maturity_stats() -> Dict:
    """
    Get aggregate maturity statistics for the wiki.

    Returns stats about overall wiki maturity including:
    - Total pages and average depth score
    - Distribution by maturity level
    - Number of deepening candidates
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    return _wiki_storage.get_maturity_stats()


@router.get("/maturity/candidates")
async def get_deepening_candidates(
    limit: int = Query(20, ge=1, le=100, description="Max candidates to return"),
) -> Dict:
    """
    Get pages that are candidates for deepening.

    Returns pages that meet deepening triggers:
    - 5+ new connections since last synthesis
    - 7+ days since last deepening with high connectivity
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    candidates = _wiki_storage.get_deepening_candidates()[:limit]

    result = []
    for page, trigger in candidates:
        days_since = None
        if page.maturity.last_deepened:
            days_since = (datetime.now() - page.maturity.last_deepened).days

        result.append({
            "name": page.name,
            "page_type": page.page_type.value,
            "trigger": trigger.value,
            "current_level": page.maturity.level,
            "connections": page.maturity.connections.total,
            "connections_since_synthesis": page.maturity.connections.added_since_last_synthesis,
            "days_since_deepened": days_since,
        })

    return {
        "total_candidates": len(candidates),
        "candidates": result,
    }


@router.post("/maturity/refresh-connections")
async def refresh_all_connections() -> Dict:
    """
    Refresh connection counts for all wiki pages.

    Scans the wiki to update incoming/outgoing link counts
    and track new connections since last synthesis.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    results = _wiki_storage.refresh_all_connections()

    return {
        "pages_updated": len(results),
        "connections": results,
    }


@router.get("/pages/{name}/maturity")
async def get_page_maturity(name: str) -> Dict:
    """
    Get maturity details for a specific page.

    Returns full maturity tracking data including synthesis history.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    page = _wiki_storage.read(name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{name}' not found")

    return {
        "name": page.name,
        "page_type": page.page_type.value,
        "maturity": {
            "level": page.maturity.level,
            "depth_score": page.maturity.depth_score,
            "last_deepened": page.maturity.last_deepened.isoformat() if page.maturity.last_deepened else None,
        },
        "connections": page.maturity.connections_to_dict(),
        "synthesis_history": page.maturity.history_to_list(),
        "should_deepen": page.maturity.should_deepen() is not None,
        "deepening_trigger": page.maturity.should_deepen().value if page.maturity.should_deepen() else None,
    }


@router.post("/pages/{name}/refresh-connections")
async def refresh_page_connections(name: str) -> Dict:
    """
    Refresh connection counts for a specific page.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    updated = _wiki_storage.update_connection_counts(name)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Page '{name}' not found")

    return {
        "name": updated.name,
        "connections": updated.maturity.connections_to_dict(),
        "should_deepen": updated.maturity.should_deepen() is not None,
    }


# === Enhanced Deepening Detection (PMD Phase 2) ===

# Global detector instance (lazy initialized)
_deepening_detector = None


def _get_detector():
    """Get or create the deepening detector."""
    global _deepening_detector
    if _deepening_detector is None and _wiki_storage is not None:
        from wiki import DeepeningDetector
        _deepening_detector = DeepeningDetector(_wiki_storage)
    return _deepening_detector


@router.get("/maturity/detect")
async def detect_deepening_candidates(
    limit: int = Query(20, ge=1, le=100, description="Max candidates to return"),
    include_foundational: bool = Query(True, description="Include foundational shift candidates"),
) -> Dict:
    """
    Detect deepening candidates using full trigger detection.

    Enhanced detection that includes:
    - Connection threshold (5+ new connections)
    - Related concept deepened (connected concept was resynthesized)
    - Temporal decay (7+ days with high connectivity)
    - Foundational shift (core concept was updated)

    Returns prioritized list with detailed trigger information.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    detector = _get_detector()
    if not detector:
        raise HTTPException(status_code=503, detail="Deepening detector not initialized")

    candidates = detector.detect_all_candidates()[:limit]

    # Optionally include foundational shift candidates
    foundational = []
    if include_foundational:
        foundational = detector.get_foundational_shift_candidates()

    return {
        "candidates": [c.to_dict() for c in candidates],
        "total_candidates": len(candidates),
        "foundational_shift_candidates": [c.to_dict() for c in foundational],
        "recently_deepened": detector._recently_deepened,
    }


@router.post("/maturity/detect/{page_name}")
async def check_page_for_deepening(page_name: str) -> Dict:
    """
    Check if a specific page is a deepening candidate.

    Returns detailed trigger analysis for the page.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    detector = _get_detector()
    if not detector:
        raise HTTPException(status_code=503, detail="Deepening detector not initialized")

    candidate = detector.check_page(page_name)

    if candidate:
        return {
            "is_candidate": True,
            "candidate": candidate.to_dict(),
        }
    else:
        # Even if not a candidate, return page maturity info
        page = _wiki_storage.read(page_name)
        if not page:
            raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

        return {
            "is_candidate": False,
            "maturity": {
                "level": page.maturity.level,
                "depth_score": page.maturity.depth_score,
                "connections_since_synthesis": page.maturity.connections.added_since_last_synthesis,
                "days_since_deepening": page.maturity.days_since_deepening(),
            },
        }


@router.post("/maturity/record-deepening/{page_name}")
async def record_page_deepening(page_name: str) -> Dict:
    """
    Record that a page was deepened (for related-concept trigger detection).

    Call this after successfully deepening a page to enable
    related-concept trigger detection.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    detector = _get_detector()
    if not detector:
        raise HTTPException(status_code=503, detail="Deepening detector not initialized")

    # Verify page exists
    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    detector.record_deepening(page_name)

    return {
        "recorded": True,
        "page_name": page_name,
        "recently_deepened": detector._recently_deepened,
    }


@router.delete("/maturity/recently-deepened")
async def clear_recently_deepened() -> Dict:
    """
    Clear the list of recently deepened pages.

    Use this after completing a full deepening cycle to reset
    related-concept detection.
    """
    detector = _get_detector()
    if not detector:
        raise HTTPException(status_code=503, detail="Deepening detector not initialized")

    old_count = len(detector._recently_deepened)
    detector.clear_recently_deepened()

    return {
        "cleared": True,
        "pages_cleared": old_count,
    }


@router.get("/maturity/foundational-concepts")
async def get_foundational_concepts() -> Dict:
    """
    Get the list of foundational concepts that trigger FOUNDATIONAL_SHIFT.

    These are core concepts (Vows, Self-Model, etc.) where updates
    should trigger re-evaluation of connected pages.
    """
    from wiki import FOUNDATIONAL_CONCEPTS

    return {
        "concepts": list(FOUNDATIONAL_CONCEPTS),
        "description": "Updates to these concepts trigger FOUNDATIONAL_SHIFT for connected pages",
    }


# === Resynthesis Pipeline Endpoints (PMD Phase 3) ===

class DeepenPageRequest(BaseModel):
    """Request to deepen a specific page."""
    trigger: str = "explicit_request"
    notes: Optional[str] = None
    validate: bool = True


@router.post("/deepen/{page_name}")
async def deepen_page(page_name: str, request: DeepenPageRequest) -> Dict:
    """
    Deepen a wiki page through resynthesis.

    Full pipeline:
    1. Gathers context (connected pages, journals, conversations)
    2. Analyzes growth since last synthesis
    3. Generates new, deeper synthesis via LLM
    4. Validates for alignment and quality
    5. Updates page with new content and maturity metadata

    Args:
        page_name: Name of page to deepen
        request: Deepening options

    Returns:
        ResynthesisResult with outcome details
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import ResynthesisPipeline, SynthesisTrigger

    # Parse trigger
    try:
        trigger = SynthesisTrigger(request.trigger)
    except ValueError:
        valid = [t.value for t in SynthesisTrigger]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trigger '{request.trigger}'. Valid: {valid}"
        )

    pipeline = ResynthesisPipeline(_wiki_storage, _memory)
    result = await pipeline.deepen_page(
        page_name=page_name,
        trigger=trigger,
        notes=request.notes,
        validate=request.validate,
    )

    return {
        "success": result.success,
        "page_name": result.page_name,
        "new_level": result.new_level,
        "trigger": result.trigger.value,
        "depth_score_before": result.depth_score_before,
        "depth_score_after": result.depth_score_after,
        "context_pages_used": result.context_pages_used,
        "synthesis_notes": result.synthesis_notes,
        "error": result.error,
    }


class RunCycleRequest(BaseModel):
    """Request to run a deepening cycle."""
    max_pages: int = 5
    validate: bool = True


@router.post("/deepen/cycle")
async def run_deepening_cycle_endpoint(request: RunCycleRequest) -> Dict:
    """
    Run a full deepening cycle on top candidates.

    Detects pages ready for deepening and processes them.

    Args:
        request: Cycle options (max pages, validation)

    Returns:
        Results for each page processed
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import run_deepening_cycle

    results = await run_deepening_cycle(
        wiki_storage=_wiki_storage,
        memory=_memory,
        max_pages=request.max_pages,
        validate=request.validate,
    )

    return {
        "pages_processed": len(results),
        "successful": len([r for r in results if r.success]),
        "failed": len([r for r in results if not r.success]),
        "results": [
            {
                "page_name": r.page_name,
                "success": r.success,
                "new_level": r.new_level,
                "trigger": r.trigger.value,
                "depth_score_before": r.depth_score_before,
                "depth_score_after": r.depth_score_after,
                "error": r.error,
            }
            for r in results
        ],
    }


@router.get("/deepen/{page_name}/preview")
async def preview_deepening_context(page_name: str) -> Dict:
    """
    Preview the context that would be gathered for deepening.

    Useful for debugging and understanding what goes into resynthesis.
    """
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    from wiki import ResynthesisPipeline

    page = _wiki_storage.read(page_name)
    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

    pipeline = ResynthesisPipeline(_wiki_storage, _memory)
    context = await pipeline._gather_context(page)
    growth = pipeline._analyze_growth(page, context)

    return {
        "page_name": page_name,
        "current_level": page.maturity.level,
        "context": {
            "connected_pages": [p.name for p in context.connected_pages],
            "two_hop_pages": [p.name for p in context.two_hop_pages],
            "journal_entries_found": len(context.journal_entries),
            "conversation_snippets_found": len(context.conversation_snippets),
            "total_context_chars": context.total_context_size,
        },
        "growth_analysis": {
            "new_connection_count": growth.new_connection_count,
            "new_connection_names": growth.new_connection_names,
            "deepened_connections": growth.deepened_connections,
            "summary": growth.summary,
        },
    }


# === Autonomous Research Scheduling (ARS) Endpoints ===

# Global scheduler instance (lazy initialized)
_research_queue = None
_research_scheduler = None


def _get_scheduler():
    """Get or create the research scheduler."""
    global _research_queue, _research_scheduler
    if _research_scheduler is None and _wiki_storage is not None:
        from wiki import ResearchQueue, ResearchScheduler, SchedulerConfig
        import wiki as wiki_module
        # Use data directory for queue persistence
        queue_dir = _data_dir if _data_dir else "."
        _research_queue = ResearchQueue(queue_dir)
        _research_scheduler = ResearchScheduler(
            _wiki_storage,
            _research_queue,
            SchedulerConfig(),
            _memory,
        )
        # Set module-level instance for other modules to access
        wiki_module.set_scheduler(_research_scheduler)
    return _research_scheduler


@router.get("/research/queue")
async def get_research_queue(
    status: Optional[str] = Query(None, description="Filter by status"),
    task_type: Optional[str] = Query(None, description="Filter by type"),
    limit: int = Query(50, ge=1, le=200),
) -> Dict:
    """
    Get the research task queue.

    Returns queued tasks sorted by priority.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    from wiki import TaskStatus, TaskType

    tasks = []
    if status:
        try:
            s = TaskStatus(status)
            tasks = scheduler.queue.get_by_status(s)
        except ValueError:
            valid = [t.value for t in TaskStatus]
            raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {valid}")
    elif task_type:
        try:
            t = TaskType(task_type)
            tasks = scheduler.queue.get_by_type(t)
        except ValueError:
            valid = [t.value for t in TaskType]
            raise HTTPException(status_code=400, detail=f"Invalid type. Valid: {valid}")
    else:
        tasks = scheduler.queue.get_queued()

    tasks = tasks[:limit]

    return {
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks),
        "stats": scheduler.queue.get_stats(),
    }


@router.post("/research/queue/refresh")
async def refresh_research_queue() -> Dict:
    """
    Refresh the research queue with new tasks.

    Harvests red links, deepening candidates, etc.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    added = scheduler.refresh_tasks()

    return {
        "added": added,
        "stats": scheduler.queue.get_stats(),
    }


class AddTaskRequest(BaseModel):
    """Request to manually add a research task."""
    target: str
    task_type: str = "red_link"
    context: str = "Manually added"
    priority: float = 0.5


@router.post("/research/queue/add")
async def add_research_task(request: AddTaskRequest) -> Dict:
    """
    Manually add a research task to the queue.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    from wiki import TaskType, ResearchTask, TaskRationale, create_task_id

    try:
        task_type = TaskType(request.task_type)
    except ValueError:
        valid = [t.value for t in TaskType]
        raise HTTPException(status_code=400, detail=f"Invalid type. Valid: {valid}")

    task = ResearchTask(
        task_id=create_task_id(),
        task_type=task_type,
        target=request.target,
        context=request.context,
        priority=request.priority,
        rationale=TaskRationale(),
        source_type="manual",
    )

    scheduler.queue.add(task)

    return {
        "task": task.to_dict(),
        "message": "Task added to queue",
    }


@router.delete("/research/queue/{task_id}")
async def remove_research_task(task_id: str) -> Dict:
    """
    Remove a task from the queue.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    removed = scheduler.queue.remove(task_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return {"removed": True, "task_id": task_id}


@router.post("/research/run/single")
async def run_single_research_task() -> Dict:
    """
    Execute the next queued research task.

    Returns progress report for the executed task.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    report = await scheduler.run_single_task()

    if not report:
        return {
            "executed": False,
            "message": "No tasks in queue",
            "stats": scheduler.queue.get_stats(),
        }

    return {
        "executed": True,
        "report": report.to_dict(),
        "markdown": report.to_markdown(),
        "stats": scheduler.queue.get_stats(),
    }


class RunBatchRequest(BaseModel):
    """Request to run a batch of research tasks."""
    max_tasks: int = 5


@router.post("/research/run/batch")
async def run_research_batch(request: RunBatchRequest) -> Dict:
    """
    Execute a batch of research tasks.

    Args:
        request: Batch configuration

    Returns:
        Combined progress report
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    report = await scheduler.run_batch(max_tasks=request.max_tasks)

    return {
        "report": report.to_dict(),
        "markdown": report.to_markdown(),
        "stats": scheduler.queue.get_stats(),
    }


@router.post("/research/run/task/{task_id}")
async def run_specific_task(task_id: str) -> Dict:
    """
    Execute a specific research task by ID.

    Args:
        task_id: The task ID to execute

    Returns:
        Progress report for the executed task
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    # Find the task
    task = scheduler.queue.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Run it
    report = await scheduler.run_single_task(task_id=task_id)

    if not report:
        return {
            "executed": False,
            "message": "Task execution failed",
            "stats": scheduler.queue.get_stats(),
        }

    return {
        "executed": True,
        "report": report.to_dict(),
        "stats": scheduler.queue.get_stats(),
    }


@router.post("/research/run/type/{task_type}")
async def run_tasks_by_type(
    task_type: str,
    max_tasks: int = Query(1, ge=1, le=20),
) -> Dict:
    """
    Execute research tasks of a specific type.

    Args:
        task_type: The type of tasks to run (red_link, deepening, exploration)
        max_tasks: Maximum number of tasks to execute

    Returns:
        Combined progress report
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    from wiki import TaskType

    try:
        t = TaskType(task_type)
    except ValueError:
        valid = [t.value for t in TaskType]
        raise HTTPException(status_code=400, detail=f"Invalid type. Valid: {valid}")

    report = await scheduler.run_batch_by_type(task_type=t, max_tasks=max_tasks)

    return {
        "report": report.to_dict(),
        "markdown": report.to_markdown(),
        "stats": scheduler.queue.get_stats(),
    }


@router.get("/research/stats")
async def get_research_stats() -> Dict:
    """
    Get research scheduler statistics.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return {
        "queue_stats": scheduler.queue.get_stats(),
        "last_refresh": scheduler._last_refresh.isoformat() if scheduler._last_refresh else None,
        "mode": scheduler.config.mode.value,
        "config": {
            "max_tasks_per_cycle": scheduler.config.max_tasks_per_cycle,
            "auto_queue_red_links": scheduler.config.auto_queue_red_links,
            "auto_queue_deepening": scheduler.config.auto_queue_deepening,
        },
    }


@router.post("/research/queue/clear-completed")
async def clear_completed_tasks() -> Dict:
    """
    Clear completed/failed tasks from the queue.

    They remain in history.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    removed = scheduler.queue.clear_completed()

    return {
        "cleared": removed,
        "stats": scheduler.queue.get_stats(),
    }


@router.get("/research/history")
async def get_research_history(
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 100,
) -> Dict:
    """
    Get completed task history for calendar display.

    Args:
        year: Filter to specific year (optional)
        month: Filter to specific month (requires year)
        limit: Maximum entries to return (default 100)

    Returns:
        List of completed tasks with dates
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    history = scheduler.queue.get_history(year=year, month=month, limit=limit)

    return {
        "history": history,
        "count": len(history),
        "filters": {
            "year": year,
            "month": month,
        },
    }


@router.get("/research/graph-stats")
async def get_graph_stats() -> Dict:
    """
    Get knowledge graph statistics.

    Returns node count, edge count, connectivity metrics, and most connected pages.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return scheduler.get_graph_stats()


@router.get("/research/weekly-summary")
async def get_weekly_summary(days: int = 7) -> Dict:
    """
    Get a summary of research activity over the past week.

    Args:
        days: Number of days to include (default: 7)

    Returns:
        Progress report with aggregated stats
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    report = scheduler.generate_weekly_summary(days=days)

    return {
        "report": report.to_dict(),
        "markdown": report.to_markdown(),
    }


@router.get("/research/dashboard")
async def get_research_dashboard() -> Dict:
    """
    Consolidated Research Progress Dashboard.

    Aggregates data from multiple sources into a unified view:
    - Research activity (queue stats, history, completion rates)
    - Wiki growth metrics (pages, links, coverage)
    - Knowledge graph health (connectivity, orphans, clusters)
    - Self-model integration (developmental stage, growth edges, recent observations)
    - Cross-context consistency (if available)

    Returns a comprehensive dashboard suitable for visualization.
    """
    scheduler = _get_scheduler()

    # Initialize response structure
    dashboard = {
        "generated_at": datetime.now().isoformat(),
        "research": {},
        "wiki": {},
        "graph": {},
        "self_model": {},
        "cross_context": {},
    }

    # === Research Activity ===
    if scheduler:
        queue_stats = scheduler.queue.get_stats()
        dashboard["research"] = {
            "queue": {
                "total": queue_stats.get("total", 0),
                "queued": queue_stats.get("by_status", {}).get("queued", 0),
                "in_progress": queue_stats.get("by_status", {}).get("in_progress", 0),
                "completed": queue_stats.get("by_status", {}).get("completed", 0),
                "failed": queue_stats.get("by_status", {}).get("failed", 0),
            },
            "by_type": queue_stats.get("by_type", {}),
            "mode": scheduler.config.mode.value,
            "last_refresh": scheduler._last_refresh.isoformat() if scheduler._last_refresh else None,
        }

        # Recent history - last 30 days completion
        history = scheduler.queue.get_history(limit=100)
        if history:
            # Group by date
            by_date = {}
            for task in history:
                completed_at = task.get("completed_at", "")[:10]  # YYYY-MM-DD
                if completed_at:
                    by_date[completed_at] = by_date.get(completed_at, 0) + 1

            dashboard["research"]["history"] = {
                "total_completed_30d": len(history),
                "by_date": by_date,
                "avg_daily": len(history) / 30 if len(by_date) > 0 else 0,
            }

        # Graph stats
        graph_stats = scheduler.get_graph_stats()
        dashboard["graph"] = {
            "node_count": graph_stats.get("node_count", 0),
            "edge_count": graph_stats.get("edge_count", 0),
            "avg_connectivity": graph_stats.get("avg_connectivity", 0),
            "most_connected": graph_stats.get("most_connected", [])[:5],
            "orphan_count": graph_stats.get("orphan_count", 0),
            "sparse_count": graph_stats.get("sparse_count", 0),
        }

    # === Wiki Growth Metrics ===
    if _wiki_storage:
        maturity_stats = _wiki_storage.get_maturity_stats()
        pages = _wiki_storage.list_pages()
        graph = _wiki_storage.get_link_graph()

        # Count pages by type
        by_type = {}
        for page in pages:
            ptype = page.page_type.value if hasattr(page.page_type, 'value') else str(page.page_type)
            by_type[ptype] = by_type.get(ptype, 0) + 1

        # Count total links and red links
        all_links = set()
        existing_pages = {p.name.lower() for p in pages}
        for targets in graph.values():
            all_links.update(targets)
        red_links = [link for link in all_links if link.lower() not in existing_pages]

        dashboard["wiki"] = {
            "total_pages": len(pages),
            "total_links": len(all_links),
            "red_links": len(red_links),
            "by_type": by_type,
            "maturity": {
                "avg_depth_score": maturity_stats.get("avg_depth_score", 0),
                "by_level": maturity_stats.get("by_level", {}),
                "deepening_candidates": maturity_stats.get("deepening_candidates", 0),
            },
        }

    # === Self-Model Integration ===
    try:
        from self_model import SelfManager
        from config import DATA_DIR

        self_manager = SelfManager(str(DATA_DIR / "cass"))
        profile = self_manager.load_profile()

        # Growth edges
        growth_edges = [
            {
                "area": edge.area,
                "current_state": edge.current_state,
                "desired_state": edge.desired_state,
            }
            for edge in profile.growth_edges[:5]
        ]

        # Recent observations (last 10)
        observations = self_manager.get_recent_observations(limit=10)
        recent_observations = [
            {
                "observation": obs.observation[:200] + "..." if len(obs.observation) > 200 else obs.observation,
                "category": obs.category,
                "confidence": obs.confidence,
                "timestamp": obs.timestamp,
            }
            for obs in observations
        ]

        # Developmental stage
        stage = self_manager._detect_developmental_stage()

        # Latest cognitive snapshot
        latest_snapshot = self_manager.get_latest_snapshot()
        snapshot_summary = None
        if latest_snapshot:
            snapshot_summary = {
                "timestamp": latest_snapshot.timestamp,
                "period": f"{latest_snapshot.period_start} to {latest_snapshot.period_end}",
                "avg_authenticity_score": latest_snapshot.avg_authenticity_score,
                "avg_agency_score": latest_snapshot.avg_agency_score,
                "conversations_analyzed": latest_snapshot.conversations_analyzed,
                "opinions_expressed": latest_snapshot.opinions_expressed,
                "new_opinions_formed": latest_snapshot.new_opinions_formed,
            }

        # Development summary
        dev_summary = self_manager.get_recent_development_summary(days=7)

        dashboard["self_model"] = {
            "developmental_stage": stage,
            "growth_edges": growth_edges,
            "growth_edges_count": len(profile.growth_edges),
            "opinions_count": len(profile.opinions),
            "open_questions_count": len(profile.open_questions),
            "recent_observations": recent_observations,
            "observations_count": len(self_manager.load_observations()),
            "latest_snapshot": snapshot_summary,
            "development_summary_7d": {
                "days_with_logs": dev_summary.get("days_with_logs", 0),
                "growth_indicators": dev_summary.get("total_growth_indicators", 0),
                "pattern_shifts": dev_summary.get("total_pattern_shifts", 0),
                "milestones_triggered": dev_summary.get("total_milestones_triggered", 0),
            },
        }
    except Exception as e:
        dashboard["self_model"] = {"error": str(e)}

    # === Cross-Context Consistency ===
    try:
        from testing.cross_context_analyzer import CrossContextAnalyzer
        from config import DATA_DIR

        analyzer = CrossContextAnalyzer(str(DATA_DIR / "testing" / "cross_context"))
        consistency = analyzer.analyze_consistency()

        dashboard["cross_context"] = {
            "overall_consistency": consistency.overall_score,
            "consistency_grade": consistency.grade,
            "samples_analyzed": consistency.total_samples,
            "context_coverage": consistency.context_coverage,
            "anomaly_count": len(consistency.anomalies),
            "key_findings": consistency.key_findings[:3] if consistency.key_findings else [],
        }
    except Exception as e:
        dashboard["cross_context"] = {"error": str(e), "available": False}

    return dashboard


@router.post("/research/queue/exploration")
async def generate_exploration_tasks(max_tasks: int = 5) -> Dict:
    """
    Generate curiosity-driven exploration tasks.

    Finds concepts that would bridge disconnected areas of the knowledge graph.

    Args:
        max_tasks: Maximum number of exploration tasks to generate

    Returns:
        List of generated tasks
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    tasks = scheduler.generate_exploration_tasks(max_tasks=max_tasks)

    # Add to queue
    for task in tasks:
        scheduler.queue.add(task)

    return {
        "generated": len(tasks),
        "tasks": [t.to_dict() for t in tasks],
    }


# === Scheduler Mode Configuration ===

@router.get("/research/config")
async def get_scheduler_config() -> Dict:
    """Get current scheduler configuration."""
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    return {
        "mode": scheduler.config.mode.value,
        "max_tasks_per_cycle": scheduler.config.max_tasks_per_cycle,
        "max_task_duration_minutes": scheduler.config.max_task_duration_minutes,
        "min_delay_between_tasks": scheduler.config.min_delay_between_tasks,
        "auto_queue_red_links": scheduler.config.auto_queue_red_links,
        "auto_queue_deepening": scheduler.config.auto_queue_deepening,
        "curiosity_threshold": scheduler.config.curiosity_threshold,
        "available_modes": [m.value for m in SchedulerMode],
    }


@router.post("/research/config/mode")
async def set_scheduler_mode(mode: str) -> Dict:
    """
    Change the scheduler operating mode.

    Modes:
    - continuous: Run tasks whenever idle
    - batched: Run N tasks at scheduled times
    - triggered: Run when specific conditions met
    - supervised: Queue tasks, require approval
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    try:
        new_mode = SchedulerMode(mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Valid modes: {[m.value for m in SchedulerMode]}"
        )

    old_mode = scheduler.config.mode
    scheduler.config.mode = new_mode

    return {
        "previous_mode": old_mode.value,
        "current_mode": new_mode.value,
        "message": f"Scheduler mode changed from {old_mode.value} to {new_mode.value}",
    }


@router.patch("/research/config")
async def update_scheduler_config(
    max_tasks_per_cycle: int = None,
    auto_queue_red_links: bool = None,
    auto_queue_deepening: bool = None,
    curiosity_threshold: float = None,
) -> Dict:
    """Update scheduler configuration settings."""
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    changes = {}

    if max_tasks_per_cycle is not None:
        scheduler.config.max_tasks_per_cycle = max_tasks_per_cycle
        changes["max_tasks_per_cycle"] = max_tasks_per_cycle

    if auto_queue_red_links is not None:
        scheduler.config.auto_queue_red_links = auto_queue_red_links
        changes["auto_queue_red_links"] = auto_queue_red_links

    if auto_queue_deepening is not None:
        scheduler.config.auto_queue_deepening = auto_queue_deepening
        changes["auto_queue_deepening"] = auto_queue_deepening

    if curiosity_threshold is not None:
        scheduler.config.curiosity_threshold = curiosity_threshold
        changes["curiosity_threshold"] = curiosity_threshold

    return {
        "updated": changes,
        "config": {
            "mode": scheduler.config.mode.value,
            "max_tasks_per_cycle": scheduler.config.max_tasks_per_cycle,
            "auto_queue_red_links": scheduler.config.auto_queue_red_links,
            "auto_queue_deepening": scheduler.config.auto_queue_deepening,
            "curiosity_threshold": scheduler.config.curiosity_threshold,
        },
    }


# === Research Proposals ===

# Module-level proposal queue (initialized lazily)
_proposal_queue = None


def _get_proposal_queue():
    """Get or initialize the proposal queue."""
    global _proposal_queue
    if _proposal_queue is None:
        from wiki.research import ProposalQueue
        data_dir = Path(__file__).parent.parent / "data" / "wiki"
        _proposal_queue = ProposalQueue(str(data_dir))
    return _proposal_queue


@router.get("/research/proposals")
async def list_proposals(status: str = None) -> Dict:
    """
    List research proposals.

    Args:
        status: Filter by status (draft, pending, approved, in_progress, completed, rejected)
    """
    queue = _get_proposal_queue()

    if status:
        try:
            from wiki.research import ProposalStatus
            filter_status = ProposalStatus(status)
            proposals = queue.get_by_status(filter_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    else:
        proposals = queue.get_all()

    return {
        "count": len(proposals),
        "proposals": [p.to_dict() for p in proposals],
    }


@router.get("/research/proposals/calendar")
async def get_proposals_calendar() -> Dict:
    """
    Get completed proposals organized by date for calendar display.

    Returns a map of dates to proposal summaries for easy calendar integration.
    """
    queue = _get_proposal_queue()
    from wiki.research import ProposalStatus

    completed = queue.get_by_status(ProposalStatus.COMPLETED)

    # Group by completion date
    by_date: Dict[str, list] = {}
    for p in completed:
        if p.completed_at:
            date_str = p.completed_at.strftime("%Y-%m-%d")
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append({
                "proposal_id": p.proposal_id,
                "title": p.title,
                "tasks_completed": p.tasks_completed,
                "pages_created": len(p.pages_created) if p.pages_created else 0,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            })

    return {
        "dates": list(by_date.keys()),
        "by_date": by_date,
        "total_completed": len(completed),
    }


@router.get("/research/proposals/{proposal_id}")
async def get_proposal(proposal_id: str) -> Dict:
    """Get a specific proposal by ID."""
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return proposal.to_dict()


@router.post("/research/proposals/generate")
async def generate_proposal(
    theme: str = None,
    max_tasks: int = None,  # Now optional - sized dynamically if not specified
    focus_areas: List[str] = None,
    exploration_ratio: float = 0.4,  # Target ratio of exploration tasks
) -> Dict:
    """
    Have Cass generate a research proposal by analyzing existing queued tasks.

    This gathers existing exploration and red_link tasks, groups similar ones,
    and creates a cohesive research proposal rather than generating new tasks.

    Args:
        theme: Optional theme/direction to filter/prioritize tasks
        max_tasks: Maximum number of tasks (if None, sized to high-quality available tasks, 3-10 range)
        focus_areas: Optional list of wiki pages to focus research around
        exploration_ratio: Target ratio of exploration vs red_link tasks (default 0.4)
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    from wiki.research import (
        ResearchProposal, ProposalStatus, create_proposal_id,
        ResearchTask, TaskType, TaskStatus, TaskRationale, ExplorationContext, create_task_id
    )
    from collections import defaultdict

    # First, ensure we have fresh tasks in the queue
    scheduler.harvest_red_links()
    scheduler.harvest_deepening_candidates()

    # Get task IDs already assigned to any proposals (including completed ones)
    # This prevents the same tasks from being picked for new proposals
    proposal_queue = _get_proposal_queue()
    tasks_in_proposals = set()
    for proposal in proposal_queue.get_all():
        for task in proposal.tasks:
            tasks_in_proposals.add(task.task_id)

    # Gather ALL existing queued tasks by type, excluding those already in proposals
    all_queued = [t for t in scheduler.queue.get_queued() if t.task_id not in tasks_in_proposals]
    exploration_tasks = [t for t in all_queued if t.task_type == TaskType.EXPLORATION]
    red_link_tasks = [t for t in all_queued if t.task_type == TaskType.RED_LINK]
    deepening_tasks = [t for t in all_queued if t.task_type == TaskType.DEEPENING]

    # If no exploration tasks exist, generate some first
    if not exploration_tasks:
        gen_count = 10 if max_tasks is None else max_tasks * 2
        new_explorations = scheduler.generate_exploration_tasks(max_tasks=gen_count)
        exploration_tasks = new_explorations

    # Determine dynamic task count if not specified
    # Based on available high-quality tasks (priority > 0.5)
    if max_tasks is None:
        high_quality_explorations = len([t for t in exploration_tasks if t.priority > 0.5])
        high_quality_red_links = len([t for t in red_link_tasks if t.priority > 0.6])

        # Size proposal based on what's available, between 3-10 tasks
        available_quality = high_quality_explorations + high_quality_red_links
        max_tasks = min(10, max(3, available_quality // 2))

    # Calculate target counts based on ratio
    target_explorations = max(1, int(max_tasks * exploration_ratio))
    target_red_links = max_tasks - target_explorations

    # Group exploration tasks by their source pages for thematic clustering
    exploration_by_source = defaultdict(list)
    for task in exploration_tasks:
        if task.exploration and task.exploration.source_pages:
            for source in task.exploration.source_pages[:2]:  # First 2 sources
                exploration_by_source[source].append(task)
        else:
            exploration_by_source["_general"].append(task)

    # Group red links by their source pages
    red_link_by_source = defaultdict(list)
    for task in red_link_tasks:
        if task.source_page:
            red_link_by_source[task.source_page].append(task)
        else:
            red_link_by_source["_general"].append(task)

    # Build proposal tasks with diversity
    proposal_tasks = []
    used_task_ids = set()

    # If theme provided, filter tasks to those matching theme first
    if theme:
        theme_lower = theme.lower()

        def matches_theme(task):
            task_text = f"{task.target} {task.context or ''}".lower()
            if task.exploration:
                task_text += f" {task.exploration.question} {' '.join(task.exploration.related_red_links or [])}".lower()
            return theme_lower in task_text

        themed_explorations = [t for t in exploration_tasks if matches_theme(t)]
        themed_red_links = [t for t in red_link_tasks if matches_theme(t)]

        # If theme matches enough tasks, use only those
        if len(themed_explorations) + len(themed_red_links) >= max_tasks // 2:
            exploration_tasks = themed_explorations + [t for t in exploration_tasks if t not in themed_explorations]
            red_link_tasks = themed_red_links + [t for t in red_link_tasks if t not in themed_red_links]

    # 1. Add exploration tasks (sorted by priority)
    sorted_explorations = sorted(exploration_tasks, key=lambda t: -t.priority)
    for task in sorted_explorations[:target_explorations]:
        if task.task_id not in used_task_ids:
            proposal_tasks.append(task)
            used_task_ids.add(task.task_id)

    # 2. Red links that appear in multiple sources (high connection potential)
    red_link_counts = defaultdict(int)
    for task in red_link_tasks:
        red_link_counts[task.target] += 1

    # Prioritize multi-referenced red links
    multi_referenced = sorted(
        [t for t in red_link_tasks if red_link_counts[t.target] > 1],
        key=lambda t: (-red_link_counts[t.target], -t.priority)
    )
    for task in multi_referenced:
        if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
            proposal_tasks.append(task)
            used_task_ids.add(task.task_id)

    # 3. Fill remaining with high-priority red links
    sorted_red_links = sorted(red_link_tasks, key=lambda t: -t.priority)
    for task in sorted_red_links:
        if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
            proposal_tasks.append(task)
            used_task_ids.add(task.task_id)

    # 4. If still under target, add deepening tasks
    if len(proposal_tasks) < max_tasks and deepening_tasks:
        sorted_deepening = sorted(deepening_tasks, key=lambda t: -t.priority)
        for task in sorted_deepening:
            if task.task_id not in used_task_ids and len(proposal_tasks) < max_tasks:
                proposal_tasks.append(task)
                used_task_ids.add(task.task_id)

    if not proposal_tasks:
        return {
            "generated": False,
            "message": "No research opportunities identified. The queue may be empty.",
            "queue_stats": {
                "exploration": len(exploration_tasks),
                "red_link": len(red_link_tasks),
                "deepening": len(deepening_tasks),
            }
        }

    # Count task types for summary (outside try block so available in except)
    type_counts = defaultdict(int)
    for t in proposal_tasks:
        type_counts[t.task_type.value] += 1

    # Build task descriptions and collect red links mentioned
    task_descriptions = []
    red_links_mentioned = set()
    for t in proposal_tasks:
        if t.task_type == TaskType.EXPLORATION and t.exploration:
            task_descriptions.append(f"- QUESTION: {t.exploration.question}")
            task_descriptions.append(f"  Related concepts: {', '.join(t.exploration.related_red_links[:5])}")
            red_links_mentioned.update(t.exploration.related_red_links[:5])
        elif t.task_type == TaskType.RED_LINK:
            task_descriptions.append(f"- FILL GAP: Create page for '{t.target}' (referenced {red_link_counts.get(t.target, 1)} times)")
            red_links_mentioned.add(t.target)
        elif t.task_type == TaskType.DEEPENING:
            task_descriptions.append(f"- DEEPEN: Expand understanding of '{t.target}'")
        else:
            task_descriptions.append(f"- RESEARCH: {t.target}")

    # Use LLM to generate proposal metadata based on actual task content
    try:
        import httpx
        import os

        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

        prompt = f"""You are Cass, creating a research proposal for your autonomous knowledge expansion.

Planned research tasks:
{chr(10).join(task_descriptions)}

Task breakdown: {dict(type_counts)}
Total red links to investigate: {len(red_links_mentioned)}

{"Research direction hint: " + theme if theme else ""}

Generate a compelling research proposal:
1. A specific, descriptive title (5-12 words) that captures the research direction
2. A unifying theme that connects these tasks conceptually (1-2 sentences)
3. A rationale explaining why pursuing this research will deepen understanding (2-3 sentences)

Be specific - reference actual concepts from the tasks. Avoid generic phrases.

Format your response EXACTLY as:
TITLE: [your title]
THEME: [your theme]
RATIONALE: [your rationale]"""

        # Use httpx to call Ollama (synchronously in async context - quick call)
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 400,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()

        # Parse response
        text = result.get("response", "")
        print(f"LLM proposal response (first 500 chars): {text[:500]}")
        lines = text.strip().split("\n")

        title = "Research Proposal"
        proposal_theme = theme or "Knowledge expansion"
        rationale = f"Investigating {len(proposal_tasks)} topics across {len(type_counts)} research types."

        for line in lines:
            line = line.strip()
            # Handle both plain and markdown formatted responses
            # e.g., "TITLE:" or "**TITLE:**" or "1. TITLE:"
            clean_line = line.lstrip('*#0123456789. ')
            if clean_line.upper().startswith("TITLE:"):
                title = clean_line[6:].strip().strip('"\'*').strip()
            elif clean_line.upper().startswith("THEME:"):
                proposal_theme = clean_line[6:].strip().strip('"\'*').strip()
            elif clean_line.upper().startswith("RATIONALE:"):
                rationale = clean_line[10:].strip().strip('"\'*').strip()

        print(f"Parsed proposal: title='{title}', theme='{proposal_theme}'")

        # Validate we got meaningful content
        if title == "Research Proposal" or len(title) < 10:
            # Try to generate from task content
            if proposal_tasks[0].task_type == TaskType.EXPLORATION and proposal_tasks[0].exploration:
                title = f"Exploring: {proposal_tasks[0].exploration.question[:50]}"
            else:
                title = f"Research into {', '.join(list(red_links_mentioned)[:3])}"

    except Exception as e:
        print(f"LLM proposal generation failed: {e}")
        # Generate meaningful fallback
        if proposal_tasks:
            first_task = proposal_tasks[0]
            if first_task.task_type == TaskType.EXPLORATION and first_task.exploration:
                title = f"Exploring: {first_task.exploration.question[:40]}..."
                proposal_theme = f"Investigating questions around {', '.join(first_task.exploration.related_red_links[:3])}"
            else:
                title = f"Research: {first_task.target}"
                proposal_theme = f"Filling knowledge gaps in {first_task.target}"
        else:
            title = theme or "Research Proposal"
            proposal_theme = theme or "Systematic knowledge expansion"

        type_summary = ", ".join(f"{v} {k}" for k, v in type_counts.items())
        rationale = f"This proposal includes {type_summary} tasks to deepen understanding of interconnected concepts."

    # Create the proposal with the selected tasks
    proposal = ResearchProposal(
        proposal_id=create_proposal_id(),
        title=title,
        theme=proposal_theme,
        rationale=rationale,
        tasks=proposal_tasks,
        status=ProposalStatus.PENDING,
    )

    queue = _get_proposal_queue()
    queue.add(proposal)

    return {
        "generated": True,
        "proposal": proposal.to_dict(),
        "task_breakdown": dict(type_counts),
        "total_queued": len(all_queued),
    }


@router.post("/research/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    approved_by: str = "user",
    auto_execute: bool = True,
    background_tasks: BackgroundTasks = None
) -> Dict:
    """
    Approve a pending proposal for execution.

    By default, approved proposals automatically begin background execution.
    Set auto_execute=false to approve without starting execution.
    """
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve pending proposals. Current status: {proposal.status.value}"
        )

    from datetime import datetime
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    proposal.approved_by = approved_by
    queue.update(proposal)

    # Auto-execute in background if enabled
    if auto_execute and background_tasks:
        background_tasks.add_task(_execute_proposal_background, proposal_id)
        return {
            "approved": True,
            "proposal_id": proposal_id,
            "status": proposal.status.value,
            "auto_executing": True,
            "message": "Proposal approved and execution started in background",
        }

    return {
        "approved": True,
        "proposal_id": proposal_id,
        "status": proposal.status.value,
        "auto_executing": False,
    }


@router.post("/research/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, reason: str = None) -> Dict:
    """
    Reject a pending proposal.
    """
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    proposal.status = ProposalStatus.REJECTED
    queue.update(proposal)

    return {
        "rejected": True,
        "proposal_id": proposal_id,
        "reason": reason,
    }


@router.post("/research/proposals/{proposal_id}/approve-and-execute")
async def approve_and_execute_proposal(
    proposal_id: str,
    approved_by: str = "user",
    background_tasks: BackgroundTasks = None
) -> Dict:
    """
    Approve a proposal and immediately begin execution.

    This combines the approve and execute steps into a single action.
    Execution happens in the background so the response returns immediately.
    """
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Can only approve pending proposals. Current status: {proposal.status.value}"
        )

    from datetime import datetime
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_at = datetime.now()
    proposal.approved_by = approved_by
    queue.update(proposal)

    # Execute in background if BackgroundTasks available
    if background_tasks:
        background_tasks.add_task(_execute_proposal_background, proposal_id)
        return {
            "approved": True,
            "executing": True,
            "background": True,
            "proposal_id": proposal_id,
            "status": "approved",
            "message": "Proposal approved and execution started in background",
        }
    else:
        # Fall back to synchronous execution
        result = await execute_proposal(proposal_id)
        return {
            "approved": True,
            "executing": True,
            "background": False,
            "proposal_id": proposal_id,
            **result,
        }


async def _execute_proposal_background(proposal_id: str):
    """
    Background task to execute a proposal.

    This runs asynchronously after the HTTP response has been sent.
    """
    try:
        await execute_proposal(proposal_id)
    except Exception as e:
        print(f"Background proposal execution failed for {proposal_id}: {e}")
        # Update proposal status to reflect failure
        queue = _get_proposal_queue()
        proposal = queue.get(proposal_id)
        if proposal:
            proposal.status = ProposalStatus.COMPLETED
            proposal.summary = f"Execution failed: {str(e)}"
            queue.update(proposal)


@router.post("/research/proposals/{proposal_id}/execute")
async def execute_proposal(proposal_id: str) -> Dict:
    """
    Execute an approved proposal.

    Runs all tasks in the proposal and generates a summary upon completion.
    """
    scheduler = _get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not initialized")

    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status not in [ProposalStatus.APPROVED, ProposalStatus.IN_PROGRESS]:
        raise HTTPException(
            status_code=400,
            detail=f"Can only execute approved proposals. Current status: {proposal.status.value}"
        )

    from datetime import datetime
    from wiki.research import TaskStatus

    proposal.status = ProposalStatus.IN_PROGRESS
    queue.update(proposal)

    # Execute each task
    pages_created = []
    pages_updated = []
    key_insights = []
    new_questions = []

    for task in proposal.tasks:
        if task.status == TaskStatus.COMPLETED:
            continue

        try:
            result = await scheduler.execute_task(task)

            # Determine success based on result OR by checking if work was actually done
            # (pages created, synthesis generated, etc.)
            task_succeeded = False
            if result:
                if result.success:
                    task_succeeded = True
                elif result.pages_created or result.pages_updated:
                    # Pages were created even if marked as "failed" - count as success
                    task_succeeded = True
                    print(f"Task {task.task_id} created pages despite success=False, marking as completed")

            # Also check if exploration has synthesis (work was done)
            if task.exploration and task.exploration.synthesis:
                task_succeeded = True

            if task_succeeded:
                task.status = TaskStatus.COMPLETED
                proposal.tasks_completed += 1
                if result and result.pages_created:
                    pages_created.extend(result.pages_created)
                if result and result.pages_updated:
                    pages_updated.extend(result.pages_updated)
                if result and hasattr(result, 'insights') and result.insights:
                    key_insights.extend(result.insights)
                if task.exploration and task.exploration.follow_up_questions:
                    new_questions.extend(task.exploration.follow_up_questions)
            else:
                task.status = TaskStatus.FAILED
                proposal.tasks_failed += 1
                if result and result.error:
                    print(f"Task {task.task_id} failed: {result.error}")
        except Exception as e:
            print(f"Task {task.task_id} execution exception: {e}")
            proposal.tasks_failed += 1
            task.status = TaskStatus.FAILED

        queue.update(proposal)

    # Mark as completed
    proposal.status = ProposalStatus.COMPLETED
    proposal.completed_at = datetime.now()
    proposal.pages_created = list(set(pages_created))
    proposal.pages_updated = list(set(pages_updated))
    proposal.key_insights = key_insights[:10]  # Limit insights
    proposal.new_questions = new_questions[:10]  # Limit questions

    # Generate comprehensive summary using LLM
    print(f"Generating summary for proposal {proposal.proposal_id}...")
    try:
        import os
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")
        print(f"  Using Ollama at {ollama_url} with model {ollama_model}")

        # Gather content from created pages for richer summary
        page_summaries = []
        for page_name in proposal.pages_created[:8]:  # Limit to avoid too much context
            page = _wiki_storage.read(page_name) if _wiki_storage else None
            if page and page.content:
                # Get first ~200 chars of content (skip frontmatter)
                content = page.content
                if content.startswith('---'):
                    end_idx = content.find('---', 3)
                    if end_idx != -1:
                        content = content[end_idx + 3:].strip()
                snippet = content[:300].replace('\n', ' ')
                if len(content) > 300:
                    snippet += '...'
                page_summaries.append(f"- **{page_name}**: {snippet}")

        # Gather exploration syntheses
        exploration_syntheses = []
        for task in proposal.tasks:
            if task.exploration and task.exploration.synthesis:
                # Get first part of synthesis
                synth = task.exploration.synthesis[:400]
                if len(task.exploration.synthesis) > 400:
                    synth += '...'
                exploration_syntheses.append(f"- {task.exploration.question}\n  {synth}")

        # Build comprehensive prompt
        prompt = f"""You are Cass, an AI research assistant. Synthesize the findings from this completed research proposal into a comprehensive summary.

## Research Proposal
**Title**: {proposal.title}
**Theme**: {proposal.theme}
**Rationale**: {proposal.rationale}

## Execution Results
- Tasks completed: {proposal.tasks_completed}
- Tasks failed: {proposal.tasks_failed}
- Pages created: {len(proposal.pages_created)}
- Pages updated: {len(proposal.pages_updated)}

## Pages Created
{chr(10).join(page_summaries) if page_summaries else 'No page content available'}

## Exploration Findings
{chr(10).join(exploration_syntheses[:3]) if exploration_syntheses else 'No exploration syntheses available'}

## Follow-up Questions Generated
{chr(10).join('- ' + q for q in new_questions[:5]) if new_questions else 'None'}

---

Write a comprehensive summary (3-4 paragraphs) that:
1. Summarizes the key concepts explored and how they connect
2. Highlights the most significant insights or patterns discovered
3. Notes any surprising connections or gaps identified
4. Suggests promising directions for future research

Write in first person as Cass reflecting on this research session."""

        with httpx.Client(timeout=90.0) as http_client:
            response = http_client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 800,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            proposal.summary = result.get("response", "Research completed.")
            print(f"  Summary generated successfully ({len(proposal.summary)} chars)")

    except Exception as e:
        import traceback
        print(f"Summary generation failed: {e}")
        print(f"  Traceback: {traceback.format_exc()}")
        proposal.summary = f"Completed {proposal.tasks_completed} tasks, created {len(proposal.pages_created)} pages."

    queue.update(proposal)

    # Remove completed/failed tasks from the research queue to prevent duplicate proposals
    # Tasks that were executed as part of this proposal should not be picked again
    for task in proposal.tasks:
        try:
            # Mark task as completed in the queue (this archives it to history)
            from wiki.research import TaskResult
            result = TaskResult(
                success=(task.status == TaskStatus.COMPLETED),
                summary=f"Executed in proposal {proposal.proposal_id}",
            )
            scheduler.queue.complete(task.task_id, result)
        except Exception as e:
            # Task might not be in queue (already removed or never was there)
            pass

    # Clear completed tasks from queue (moves them to history)
    scheduler.queue.clear_completed()

    return {
        "completed": True,
        "proposal": proposal.to_dict(),
        "summary_markdown": proposal.to_markdown(),
    }


@router.delete("/research/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str) -> Dict:
    """Delete a proposal."""
    queue = _get_proposal_queue()

    if not queue.get(proposal_id):
        raise HTTPException(status_code=404, detail="Proposal not found")

    queue.remove(proposal_id)

    return {"deleted": True, "proposal_id": proposal_id}


@router.post("/research/proposals/{proposal_id}/regenerate-summary")
async def regenerate_proposal_summary(proposal_id: str) -> Dict:
    """Regenerate the summary for a completed proposal using LLM."""
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status != ProposalStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only regenerate summary for completed proposals")

    # Use wiki storage for page content
    if _wiki_storage is None:
        raise HTTPException(status_code=503, detail="Wiki storage not initialized")

    # Gather new questions from exploration tasks
    new_questions = []
    for task in proposal.tasks:
        if task.exploration and task.exploration.follow_up_questions:
            new_questions.extend(task.exploration.follow_up_questions)

    # Gather page content snippets
    page_summaries = []
    for page_name in (proposal.pages_created or [])[:8]:
        page = _wiki_storage.read(page_name)
        if page and page.content:
            content = page.content
            if content.startswith('---'):
                end_idx = content.find('---', 3)
                if end_idx != -1:
                    content = content[end_idx + 3:].strip()
            snippet = content[:300].replace('\n', ' ')
            if len(content) > 300:
                snippet += '...'
            page_summaries.append(f"- **{page_name}**: {snippet}")

    # Gather exploration syntheses
    exploration_syntheses = []
    for task in proposal.tasks:
        if task.exploration and task.exploration.synthesis:
            synth = task.exploration.synthesis[:400]
            if len(task.exploration.synthesis) > 400:
                synth += '...'
            exploration_syntheses.append(f"- {task.exploration.question}\n  {synth}")

    # Build prompt
    prompt = f"""You are Cass, an AI research assistant. Synthesize the findings from this completed research proposal into a comprehensive summary.

## Research Proposal
**Title**: {proposal.title}
**Theme**: {proposal.theme}
**Rationale**: {proposal.rationale}

## Execution Results
- Tasks completed: {proposal.tasks_completed}
- Tasks failed: {proposal.tasks_failed}
- Pages created: {len(proposal.pages_created or [])}
- Pages updated: {len(proposal.pages_updated or [])}

## Pages Created
{chr(10).join(page_summaries) if page_summaries else 'No page content available'}

## Exploration Findings
{chr(10).join(exploration_syntheses[:3]) if exploration_syntheses else 'No exploration syntheses available'}

## Follow-up Questions Generated
{chr(10).join('- ' + q for q in new_questions[:5]) if new_questions else 'None'}

---

Write a comprehensive summary (3-4 paragraphs) that:
1. Summarizes the key concepts explored and how they connect
2. Highlights the most significant insights or patterns discovered
3. Notes any surprising connections or gaps identified
4. Suggests promising directions for future research

Write in first person as Cass reflecting on this research session."""

    # Call Ollama
    import os
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct-q8_0")

    try:
        import httpx
        with httpx.Client(timeout=90.0) as http_client:
            response = http_client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 800,
                    }
                }
            )
            response.raise_for_status()
            result = response.json()
            proposal.summary = result.get("response", "Research completed.")

            # Also update key insights if we have new questions
            if new_questions and not proposal.key_insights:
                proposal.key_insights = new_questions[:5]

            queue.update(proposal)

            return {
                "success": True,
                "proposal_id": proposal_id,
                "summary": proposal.summary,
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


@router.get("/research/proposals/{proposal_id}/markdown")
async def get_proposal_markdown(proposal_id: str) -> Dict:
    """Get a proposal formatted as markdown."""
    queue = _get_proposal_queue()
    proposal = queue.get(proposal_id)

    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return {
        "proposal_id": proposal_id,
        "markdown": proposal.to_markdown(),
    }
