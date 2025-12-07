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
