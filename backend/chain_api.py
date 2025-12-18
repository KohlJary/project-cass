"""
Chain API - REST endpoints for prompt chain management.

Provides CRUD operations for:
- Node templates (list, get, create custom)
- Prompt chains (list, get, create, update, delete, activate, duplicate)
- Chain nodes (list, add, update, remove, reorder)
- Preview (assemble and return prompt text)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import json

from database import get_db, seed_node_templates, seed_default_chains
from node_templates import (
    ALL_TEMPLATES,
    TEMPLATES_BY_SLUG,
    TEMPLATES_BY_ID,
    NodeTemplate,
    get_categories,
)
from chain_assembler import (
    ChainNode,
    Condition,
    RuntimeContext,
    assemble_chain,
    parse_conditions,
    estimate_tokens,
)
from temporal import get_temporal_context

router = APIRouter(prefix="/admin/chains", tags=["chains"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class NodeTemplateResponse(BaseModel):
    id: str
    name: str
    slug: str
    category: str
    description: Optional[str]
    template: str
    params_schema: Optional[Dict[str, Any]]
    default_params: Optional[Dict[str, Any]]
    is_system: bool
    is_locked: bool
    default_enabled: bool
    default_order: int
    token_estimate: int


class ConditionModel(BaseModel):
    type: str
    key: Optional[str] = None
    op: str = "exists"
    value: Optional[Any] = None
    start: Optional[str] = None
    end: Optional[str] = None
    phase: Optional[str] = None


class ChainNodeResponse(BaseModel):
    id: str
    template_id: str
    template_slug: str
    template_name: Optional[str] = None
    template_category: Optional[str] = None
    params: Optional[Dict[str, Any]]
    order_index: int
    enabled: bool
    locked: bool
    conditions: List[ConditionModel]
    token_estimate: Optional[int] = None


class ChainResponse(BaseModel):
    id: str
    daemon_id: str
    name: str
    description: Optional[str]
    is_active: bool
    is_default: bool
    token_estimate: Optional[int]
    node_count: int
    created_at: str
    updated_at: str
    created_by: Optional[str]


class ChainDetailResponse(BaseModel):
    id: str
    daemon_id: str
    name: str
    description: Optional[str]
    is_active: bool
    is_default: bool
    token_estimate: Optional[int]
    nodes: List[ChainNodeResponse]
    created_at: str
    updated_at: str
    created_by: Optional[str]


class CreateChainRequest(BaseModel):
    name: str
    description: Optional[str] = None
    copy_from: Optional[str] = None  # Chain ID to copy nodes from


class UpdateChainRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddNodeRequest(BaseModel):
    template_slug: str
    params: Optional[Dict[str, Any]] = None
    order_index: Optional[int] = None
    enabled: bool = True
    conditions: Optional[List[ConditionModel]] = None


class UpdateNodeRequest(BaseModel):
    params: Optional[Dict[str, Any]] = None
    order_index: Optional[int] = None
    enabled: Optional[bool] = None
    conditions: Optional[List[ConditionModel]] = None


class ReorderNodesRequest(BaseModel):
    node_ids: List[str]  # Node IDs in desired order


class PreviewRequest(BaseModel):
    daemon_name: str = "Cass"
    identity_snippet: Optional[str] = None
    # Test message for memory retrieval simulation
    test_message: Optional[str] = None
    # Conversation context
    conversation_id: Optional[str] = None
    # Optional runtime context for condition evaluation
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    message_count: int = 0
    unsummarized_count: int = 0
    has_memories: bool = False
    has_dream_context: bool = False


class ContextSection(BaseModel):
    """Details about a retrieved context section."""
    name: str
    enabled: bool
    char_count: int
    content: Optional[str] = None  # Only included if requested


class PreviewResponse(BaseModel):
    chain_id: str
    chain_name: str
    full_text: str
    token_estimate: int
    included_nodes: List[str]
    excluded_nodes: List[str]
    warnings: List[str]
    # Context retrieval details
    context_sections: Optional[Dict[str, ContextSection]] = None
    test_message: Optional[str] = None
    conversation_id: Optional[str] = None


# =============================================================================
# NODE TEMPLATE ENDPOINTS
# =============================================================================

@router.get("/templates", response_model=List[NodeTemplateResponse])
async def list_templates(
    category: Optional[str] = Query(None, description="Filter by category")
):
    """List all available node templates."""
    # Ensure templates are seeded
    seed_node_templates()

    templates = ALL_TEMPLATES
    if category:
        templates = [t for t in templates if t.category == category]

    return [
        NodeTemplateResponse(
            id=t.id,
            name=t.name,
            slug=t.slug,
            category=t.category,
            description=t.description,
            template=t.template,
            params_schema=t.params_schema,
            default_params=t.default_params,
            is_system=t.is_system,
            is_locked=t.is_locked,
            default_enabled=t.default_enabled,
            default_order=t.default_order,
            token_estimate=t.token_estimate,
        )
        for t in templates
    ]


@router.get("/templates/categories")
async def list_categories():
    """List all template categories."""
    return get_categories()


@router.get("/templates/{slug}", response_model=NodeTemplateResponse)
async def get_template(slug: str):
    """Get a specific template by slug."""
    template = TEMPLATES_BY_SLUG.get(slug)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")

    return NodeTemplateResponse(
        id=template.id,
        name=template.name,
        slug=template.slug,
        category=template.category,
        description=template.description,
        template=template.template,
        params_schema=template.params_schema,
        default_params=template.default_params,
        is_system=template.is_system,
        is_locked=template.is_locked,
        default_enabled=template.default_enabled,
        default_order=template.default_order,
        token_estimate=template.token_estimate,
    )


# =============================================================================
# PROMPT CHAIN ENDPOINTS
# =============================================================================

@router.get("", response_model=List[ChainResponse])
async def list_chains(
    daemon_id: str = Query(..., description="Daemon ID to list chains for")
):
    """List all prompt chains for a daemon."""
    # Ensure defaults are seeded
    seed_node_templates()
    seed_default_chains(daemon_id)

    with get_db() as conn:
        cursor = conn.execute("""
            SELECT
                pc.id, pc.daemon_id, pc.name, pc.description,
                pc.is_active, pc.is_default, pc.token_estimate,
                pc.created_at, pc.updated_at, pc.created_by,
                COUNT(cn.id) as node_count
            FROM prompt_chains pc
            LEFT JOIN chain_nodes cn ON cn.chain_id = pc.id
            WHERE pc.daemon_id = ?
            GROUP BY pc.id
            ORDER BY pc.is_active DESC, pc.is_default DESC, pc.name
        """, (daemon_id,))

        rows = cursor.fetchall()

    return [
        ChainResponse(
            id=row[0],
            daemon_id=row[1],
            name=row[2],
            description=row[3],
            is_active=bool(row[4]),
            is_default=bool(row[5]),
            token_estimate=row[6],
            created_at=row[7],
            updated_at=row[8],
            created_by=row[9],
            node_count=row[10],
        )
        for row in rows
    ]


@router.get("/active", response_model=ChainDetailResponse)
async def get_active_chain(
    daemon_id: str = Query(..., description="Daemon ID")
):
    """Get the active prompt chain for a daemon."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, daemon_id, name, description, is_active, is_default,
                   token_estimate, created_at, updated_at, created_by
            FROM prompt_chains
            WHERE daemon_id = ? AND is_active = 1
        """, (daemon_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No active chain found")

    chain_id = row[0]
    nodes = _get_chain_nodes(chain_id)

    return ChainDetailResponse(
        id=row[0],
        daemon_id=row[1],
        name=row[2],
        description=row[3],
        is_active=bool(row[4]),
        is_default=bool(row[5]),
        token_estimate=row[6],
        nodes=nodes,
        created_at=row[7],
        updated_at=row[8],
        created_by=row[9],
    )


@router.get("/{chain_id}", response_model=ChainDetailResponse)
async def get_chain(chain_id: str):
    """Get a specific chain with all its nodes."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, daemon_id, name, description, is_active, is_default,
                   token_estimate, created_at, updated_at, created_by
            FROM prompt_chains
            WHERE id = ?
        """, (chain_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Chain not found")

    nodes = _get_chain_nodes(chain_id)

    return ChainDetailResponse(
        id=row[0],
        daemon_id=row[1],
        name=row[2],
        description=row[3],
        is_active=bool(row[4]),
        is_default=bool(row[5]),
        token_estimate=row[6],
        nodes=nodes,
        created_at=row[7],
        updated_at=row[8],
        created_by=row[9],
    )


@router.post("", response_model=ChainDetailResponse)
async def create_chain(
    daemon_id: str = Query(..., description="Daemon ID"),
    request: CreateChainRequest = None
):
    """Create a new prompt chain."""
    now = datetime.now().isoformat()
    chain_id = str(uuid4())

    with get_db() as conn:
        conn.execute("""
            INSERT INTO prompt_chains (
                id, daemon_id, name, description, is_active, is_default,
                created_at, updated_at, created_by
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, 'user')
        """, (chain_id, daemon_id, request.name, request.description, now, now))

        # Copy nodes from another chain if specified
        if request.copy_from:
            _copy_chain_nodes(request.copy_from, chain_id, conn)

    return await get_chain(chain_id)


@router.put("/{chain_id}", response_model=ChainDetailResponse)
async def update_chain(chain_id: str, request: UpdateChainRequest):
    """Update chain metadata (name, description)."""
    with get_db() as conn:
        # Check if chain exists and is not default
        cursor = conn.execute(
            "SELECT is_default FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot modify default chains")

        updates = []
        params = []
        if request.name is not None:
            updates.append("name = ?")
            params.append(request.name)
        if request.description is not None:
            updates.append("description = ?")
            params.append(request.description)

        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(chain_id)

            conn.execute(
                f"UPDATE prompt_chains SET {', '.join(updates)} WHERE id = ?",
                params
            )

    return await get_chain(chain_id)


@router.delete("/{chain_id}")
async def delete_chain(chain_id: str):
    """Delete a chain."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT is_default, is_active FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot delete default chains")
        if row[1]:
            raise HTTPException(status_code=400, detail="Cannot delete active chain")

        # Delete nodes first (cascade should handle this, but be explicit)
        conn.execute("DELETE FROM chain_nodes WHERE chain_id = ?", (chain_id,))
        conn.execute("DELETE FROM prompt_chains WHERE id = ?", (chain_id,))

    return {"status": "deleted", "chain_id": chain_id}


@router.post("/{chain_id}/activate")
async def activate_chain(chain_id: str):
    """Set a chain as the active chain for its daemon."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT daemon_id FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")

        daemon_id = row[0]

        # Deactivate all chains for this daemon
        conn.execute(
            "UPDATE prompt_chains SET is_active = 0 WHERE daemon_id = ?",
            (daemon_id,)
        )

        # Activate the specified chain
        conn.execute(
            "UPDATE prompt_chains SET is_active = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), chain_id)
        )

    return {"status": "activated", "chain_id": chain_id}


@router.post("/{chain_id}/duplicate", response_model=ChainDetailResponse)
async def duplicate_chain(
    chain_id: str,
    name: Optional[str] = Query(None, description="Name for the new chain")
):
    """Duplicate a chain."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT daemon_id, name, description FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")

        daemon_id, original_name, description = row
        new_name = name or f"{original_name} (Copy)"
        new_chain_id = str(uuid4())
        now = datetime.now().isoformat()

        conn.execute("""
            INSERT INTO prompt_chains (
                id, daemon_id, name, description, is_active, is_default,
                created_at, updated_at, created_by
            ) VALUES (?, ?, ?, ?, 0, 0, ?, ?, 'user')
        """, (new_chain_id, daemon_id, new_name, description, now, now))

        _copy_chain_nodes(chain_id, new_chain_id, conn)

    return await get_chain(new_chain_id)


# =============================================================================
# CHAIN NODE ENDPOINTS
# =============================================================================

@router.get("/{chain_id}/nodes", response_model=List[ChainNodeResponse])
async def list_chain_nodes(chain_id: str):
    """List all nodes in a chain."""
    return _get_chain_nodes(chain_id)


@router.post("/{chain_id}/nodes", response_model=ChainNodeResponse)
async def add_node(chain_id: str, request: AddNodeRequest):
    """Add a node to a chain."""
    # Validate template exists
    template = TEMPLATES_BY_SLUG.get(request.template_slug)
    if not template:
        raise HTTPException(status_code=400, detail=f"Template '{request.template_slug}' not found")

    now = datetime.now().isoformat()
    node_id = str(uuid4())

    with get_db() as conn:
        # Check chain exists and is not default
        cursor = conn.execute(
            "SELECT is_default FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot modify default chains")

        # Check if template already in chain
        cursor = conn.execute(
            "SELECT id FROM chain_nodes WHERE chain_id = ? AND template_id = ?",
            (chain_id, template.id)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Template already in chain")

        # Determine order index
        order_index = request.order_index
        if order_index is None:
            cursor = conn.execute(
                "SELECT MAX(order_index) FROM chain_nodes WHERE chain_id = ?",
                (chain_id,)
            )
            max_order = cursor.fetchone()[0]
            order_index = (max_order or 0) + 10

        # Serialize conditions
        conditions_json = None
        if request.conditions:
            conditions_json = json.dumps([c.dict() for c in request.conditions])

        conn.execute("""
            INSERT INTO chain_nodes (
                id, chain_id, template_id, params, order_index,
                enabled, locked, conditions, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node_id,
            chain_id,
            template.id,
            json.dumps(request.params) if request.params else None,
            order_index,
            1 if request.enabled else 0,
            1 if template.is_locked else 0,
            conditions_json,
            now,
            now,
        ))

        # Update chain timestamp
        conn.execute(
            "UPDATE prompt_chains SET updated_at = ? WHERE id = ?",
            (now, chain_id)
        )

    return _get_node(node_id)


@router.put("/{chain_id}/nodes/{node_id}", response_model=ChainNodeResponse)
async def update_node(chain_id: str, node_id: str, request: UpdateNodeRequest):
    """Update a node in a chain."""
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Check chain is not default
        cursor = conn.execute(
            "SELECT is_default FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot modify default chains")

        # Check node exists and get current locked state
        cursor = conn.execute(
            "SELECT locked FROM chain_nodes WHERE id = ? AND chain_id = ?",
            (node_id, chain_id)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Node not found")

        is_locked = row[0]

        # Build update
        updates = []
        params_list = []

        if request.params is not None:
            updates.append("params = ?")
            params_list.append(json.dumps(request.params))

        if request.order_index is not None:
            updates.append("order_index = ?")
            params_list.append(request.order_index)

        if request.enabled is not None:
            # Can't disable locked nodes
            if is_locked and not request.enabled:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot disable locked (safety-critical) nodes"
                )
            updates.append("enabled = ?")
            params_list.append(1 if request.enabled else 0)

        if request.conditions is not None:
            updates.append("conditions = ?")
            params_list.append(json.dumps([c.dict() for c in request.conditions]))

        if updates:
            updates.append("updated_at = ?")
            params_list.append(now)
            params_list.append(node_id)

            conn.execute(
                f"UPDATE chain_nodes SET {', '.join(updates)} WHERE id = ?",
                params_list
            )

            # Update chain timestamp
            conn.execute(
                "UPDATE prompt_chains SET updated_at = ? WHERE id = ?",
                (now, chain_id)
            )

    return _get_node(node_id)


@router.delete("/{chain_id}/nodes/{node_id}")
async def remove_node(chain_id: str, node_id: str):
    """Remove a node from a chain."""
    with get_db() as conn:
        # Check chain is not default
        cursor = conn.execute(
            "SELECT is_default FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot modify default chains")

        # Check node exists and is not locked
        cursor = conn.execute(
            "SELECT locked FROM chain_nodes WHERE id = ? AND chain_id = ?",
            (node_id, chain_id)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Node not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot remove locked (safety-critical) nodes")

        conn.execute("DELETE FROM chain_nodes WHERE id = ?", (node_id,))

        # Update chain timestamp
        conn.execute(
            "UPDATE prompt_chains SET updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), chain_id)
        )

    return {"status": "removed", "node_id": node_id}


@router.post("/{chain_id}/nodes/reorder")
async def reorder_nodes(chain_id: str, request: ReorderNodesRequest):
    """Reorder nodes in a chain."""
    now = datetime.now().isoformat()

    with get_db() as conn:
        # Check chain is not default
        cursor = conn.execute(
            "SELECT is_default FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")
        if row[0]:
            raise HTTPException(status_code=400, detail="Cannot modify default chains")

        # Update order indices
        for idx, node_id in enumerate(request.node_ids):
            order_index = (idx + 1) * 10  # 10, 20, 30, ...
            conn.execute(
                "UPDATE chain_nodes SET order_index = ?, updated_at = ? WHERE id = ? AND chain_id = ?",
                (order_index, now, node_id, chain_id)
            )

        # Update chain timestamp
        conn.execute(
            "UPDATE prompt_chains SET updated_at = ? WHERE id = ?",
            (now, chain_id)
        )

    return {"status": "reordered", "chain_id": chain_id}


# =============================================================================
# PREVIEW ENDPOINT
# =============================================================================

@router.post("/{chain_id}/preview", response_model=PreviewResponse)
async def preview_chain(chain_id: str, request: PreviewRequest):
    """Preview the assembled prompt for a chain with optional memory retrieval."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT name, daemon_id FROM prompt_chains WHERE id = ?",
            (chain_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Chain not found")

        chain_name = row[0]
        daemon_id = row[1]

        # Fetch active identity snippet if not provided
        identity_snippet = request.identity_snippet
        if not identity_snippet:
            snippet_row = conn.execute(
                """SELECT snippet_text FROM daemon_identity_snippets
                   WHERE daemon_id = ? AND is_active = 1
                   ORDER BY generated_at DESC LIMIT 1""",
                (daemon_id,)
            ).fetchone()
            if snippet_row:
                identity_snippet = snippet_row[0]

    # Get nodes
    node_responses = _get_chain_nodes(chain_id)

    # Convert to ChainNode objects
    nodes = []
    for nr in node_responses:
        conditions = [
            Condition.from_dict(c.dict())
            for c in nr.conditions
        ]
        nodes.append(ChainNode(
            id=nr.id,
            template_id=nr.template_id,
            template_slug=nr.template_slug,
            params=nr.params or {},
            order_index=nr.order_index,
            enabled=nr.enabled,
            locked=nr.locked,
            conditions=conditions,
        ))

    # Track context sections for response
    context_sections: Dict[str, ContextSection] = {}

    # Retrieve memory context if test_message provided
    retrieved_context = await _retrieve_memory_context(
        test_message=request.test_message,
        conversation_id=request.conversation_id,
        project_id=request.project_id,
        user_id=request.user_id,
        daemon_id=daemon_id,
    )

    # Generate temporal context string
    temporal_ctx = get_temporal_context()

    # Build runtime context with retrieved data
    now = datetime.now()
    context = RuntimeContext(
        project_id=request.project_id,
        conversation_id=request.conversation_id,
        message_count=request.message_count,
        unsummarized_count=request.unsummarized_count,
        has_memories=bool(retrieved_context.get("memories")),
        memory_context=retrieved_context.get("memories"),
        has_dream_context=request.has_dream_context,
        # Memory subsystem flags
        has_self_model=bool(retrieved_context.get("self_model")),
        self_model_context=retrieved_context.get("self_model"),
        has_graph_context=bool(retrieved_context.get("graph")),
        graph_context=retrieved_context.get("graph"),
        has_wiki_context=bool(retrieved_context.get("wiki")),
        wiki_context=retrieved_context.get("wiki"),
        has_cross_session=bool(retrieved_context.get("cross_session")),
        cross_session_context=retrieved_context.get("cross_session"),
        has_active_goals=bool(retrieved_context.get("goals")),
        goals_context=retrieved_context.get("goals"),
        has_patterns=bool(retrieved_context.get("patterns")),
        patterns_context=retrieved_context.get("patterns"),
        has_intro_guidance=bool(retrieved_context.get("intro_guidance")),
        intro_guidance=retrieved_context.get("intro_guidance"),
        # Enhanced user modeling
        has_user_model=bool(retrieved_context.get("user_model")),
        user_model_context=retrieved_context.get("user_model"),
        has_relationship_model=bool(retrieved_context.get("relationship")),
        relationship_context=retrieved_context.get("relationship"),
        current_time=now,
        hour=now.hour,
        temporal_context=temporal_ctx,
        model="preview",
        provider="preview",
    )

    # Build context sections for response
    for key, name in [
        ("memories", "Relevant Memories"),
        ("self_model", "Self-Model Profile"),
        ("graph", "Self-Model Graph"),
        ("wiki", "Wiki Context"),
        ("cross_session", "Cross-Session Insights"),
        ("goals", "Active Goals"),
        ("patterns", "Recognition Patterns"),
        ("intro_guidance", "User Intro Guidance"),
        ("user_model", "User Understanding"),
        ("relationship", "Relationship Context"),
    ]:
        content = retrieved_context.get(key, "")
        context_sections[key] = ContextSection(
            name=name,
            enabled=bool(content),
            char_count=len(content) if content else 0,
            content=content if content else None,
        )

    # Assemble
    result = assemble_chain(
        nodes=nodes,
        context=context,
        daemon_name=request.daemon_name,
        identity_snippet=identity_snippet,
    )

    return PreviewResponse(
        chain_id=chain_id,
        chain_name=chain_name,
        full_text=result.full_text,
        token_estimate=result.token_estimate,
        included_nodes=result.included_nodes,
        excluded_nodes=result.excluded_nodes,
        warnings=result.warnings,
        context_sections=context_sections,
        test_message=request.test_message,
        conversation_id=request.conversation_id,
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def _retrieve_memory_context(
    test_message: Optional[str],
    conversation_id: Optional[str],
    project_id: Optional[str],
    user_id: Optional[str],
    daemon_id: str,
) -> Dict[str, str]:
    """
    Retrieve memory context for preview.
    Returns dict of context type -> content string.
    """
    import sys
    result: Dict[str, str] = {}

    # Early return if no message to query against
    if not test_message:
        return result

    try:
        # Get the already-loaded main_sdk module from sys.modules
        # When running `python main_sdk.py` directly, it's registered as __main__
        if 'main_sdk' in sys.modules:
            main_sdk_module = sys.modules['main_sdk']
        elif '__main__' in sys.modules:
            main_sdk_module = sys.modules['__main__']
        else:
            print("[Preview] ERROR: Cannot find main_sdk module")
            return result

        # Check if heavy components are initialized
        if not main_sdk_module._heavy_components_ready:
            result["_status"] = "Memory systems still initializing..."
            return result

        # Get references directly from the already-loaded module
        memory = main_sdk_module.memory
        self_manager = main_sdk_module.self_manager
        self_model_graph = main_sdk_module.self_model_graph
        goal_manager = main_sdk_module.goal_manager
        marker_store = main_sdk_module.marker_store
        conversation_manager = main_sdk_module.conversation_manager
        user_manager = main_sdk_module.user_manager
        get_automatic_wiki_context = main_sdk_module.get_automatic_wiki_context
        from pattern_aggregation import get_pattern_summary_for_surfacing

        # Look up user_id from conversation if not provided directly
        if not user_id and conversation_id and conversation_manager:
            try:
                conversation = conversation_manager.load_conversation(conversation_id)
                if conversation and conversation.user_id:
                    user_id = conversation.user_id
                    print(f"[Preview] Resolved user_id from conversation: {user_id}")
            except Exception as e:
                print(f"[Preview] Could not resolve user_id from conversation: {e}")

        # 0. User context (intro guidance based on relationship sparseness)
        if user_id and user_manager:
            try:
                sparseness = user_manager.check_user_model_sparseness(user_id)
                print(f"[Preview] User sparseness for {user_id}: level={sparseness.get('sparseness_level')}, has_intro={bool(sparseness.get('intro_guidance'))}")
                if sparseness and sparseness.get("intro_guidance"):
                    result["intro_guidance"] = sparseness["intro_guidance"]

                # Enhanced user modeling - deep understanding of user
                user_model_ctx = user_manager.get_rich_user_context(user_id)
                if user_model_ctx:
                    result["user_model"] = user_model_ctx
                    print(f"[Preview] User model context: {len(user_model_ctx)} chars")

                # Relationship context - patterns, shared moments, mutual shaping
                relationship_ctx = user_manager.get_relationship_context(user_id)
                if relationship_ctx:
                    result["relationship"] = relationship_ctx
                    print(f"[Preview] Relationship context: {len(relationship_ctx)} chars")
            except Exception as e:
                print(f"[Preview] User context error: {e}")
        else:
            print(f"[Preview] No user context: user_id={user_id}, has_manager={bool(user_manager)}")

        # 1. Self-model profile (growth-focused: positions, edges, open questions)
        # Semantically filtered based on message relevance
        if self_manager:
            self_context = self_manager.get_growth_context(query=test_message, top_k=3)
            if self_context:
                result["self_model"] = self_context

        # 2. Self-model graph (message-relevant)
        if self_model_graph:
            graph_context = self_model_graph.get_graph_context(
                message=test_message,
                include_contradictions=True,
                include_recent=True,
                include_stats=True,
                max_related=5
            )
            if graph_context:
                result["graph"] = graph_context

        # 3. Wiki context
        wiki_context_str, wiki_page_names, _ = get_automatic_wiki_context(
            query=test_message,
            relevance_threshold=0.5,
            max_pages=3,
            max_tokens=1500
        )
        if wiki_context_str:
            result["wiki"] = wiki_context_str

        # 4. Cross-session insights
        if memory:
            cross_session_insights = memory.retrieve_cross_session_insights(
                query=test_message,
                n_results=5,
                max_distance=1.2,
                min_importance=0.5,
                exclude_conversation_id=conversation_id
            )
            if cross_session_insights:
                insights_context = memory.format_cross_session_context(cross_session_insights)
                if insights_context:
                    result["cross_session"] = insights_context

        # 5. Active goals
        if goal_manager:
            goals_context = goal_manager.get_active_summary()
            if goals_context:
                result["goals"] = goals_context

        # 6. Recognition patterns
        if marker_store:
            patterns_context, _ = get_pattern_summary_for_surfacing(
                marker_store=marker_store,
                min_significance=0.5,
                limit=3
            )
            if patterns_context:
                result["patterns"] = patterns_context

        # 7. Hierarchical memory (summaries + working summary + recent messages)
        # Only retrieve if conversation_id is provided - otherwise there's no context
        if memory and conversation_id:
            hierarchical = memory.retrieve_hierarchical(
                query=test_message,
                conversation_id=conversation_id
            )
            print(f"[Preview] Hierarchical: summaries={len(hierarchical.get('summaries', []))}, details={len(hierarchical.get('details', []))}")

            working_summary = None
            if conversation_id and conversation_manager:
                working_summary = conversation_manager.get_working_summary(conversation_id)
                print(f"[Preview] Working summary: {len(working_summary) if working_summary else 0} chars")

            recent_messages = []
            if conversation_id and conversation_manager:
                recent_messages = conversation_manager.get_recent_messages(
                    conversation_id, count=6
                )
                print(f"[Preview] Recent messages: {len(recent_messages)}")

            formatted = memory.format_hierarchical_context(
                hierarchical,
                working_summary=working_summary,
                recent_messages=recent_messages
            )
            print(f"[Preview] Formatted memory context: {len(formatted) if formatted else 0} chars")
            if formatted:
                result["memories"] = formatted

    except Exception as e:
        # Log but don't fail preview
        import traceback
        print(f"[Preview] Memory retrieval error: {e}")
        traceback.print_exc()

    return result


def _get_chain_nodes(chain_id: str) -> List[ChainNodeResponse]:
    """Get all nodes for a chain."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT cn.id, cn.template_id, cn.params, cn.order_index,
                   cn.enabled, cn.locked, cn.conditions,
                   nt.slug, nt.name, nt.category, nt.token_estimate
            FROM chain_nodes cn
            JOIN node_templates nt ON nt.id = cn.template_id
            WHERE cn.chain_id = ?
            ORDER BY cn.order_index
        """, (chain_id,))

        rows = cursor.fetchall()

    results = []
    for row in rows:
        conditions = []
        if row[6]:
            try:
                cond_data = json.loads(row[6])
                conditions = [ConditionModel(**c) for c in cond_data]
            except (json.JSONDecodeError, TypeError):
                pass

        params = None
        if row[2]:
            try:
                params = json.loads(row[2])
            except json.JSONDecodeError:
                pass

        results.append(ChainNodeResponse(
            id=row[0],
            template_id=row[1],
            template_slug=row[7],
            template_name=row[8],
            template_category=row[9],
            params=params,
            order_index=row[3],
            enabled=bool(row[4]),
            locked=bool(row[5]),
            conditions=conditions,
            token_estimate=row[10],
        ))

    return results


def _get_node(node_id: str) -> ChainNodeResponse:
    """Get a single node by ID."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT cn.id, cn.template_id, cn.params, cn.order_index,
                   cn.enabled, cn.locked, cn.conditions,
                   nt.slug, nt.name, nt.category, nt.token_estimate
            FROM chain_nodes cn
            JOIN node_templates nt ON nt.id = cn.template_id
            WHERE cn.id = ?
        """, (node_id,))

        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Node not found")

    conditions = []
    if row[6]:
        try:
            cond_data = json.loads(row[6])
            conditions = [ConditionModel(**c) for c in cond_data]
        except (json.JSONDecodeError, TypeError):
            pass

    params = None
    if row[2]:
        try:
            params = json.loads(row[2])
        except json.JSONDecodeError:
            pass

    return ChainNodeResponse(
        id=row[0],
        template_id=row[1],
        template_slug=row[7],
        template_name=row[8],
        template_category=row[9],
        params=params,
        order_index=row[3],
        enabled=bool(row[4]),
        locked=bool(row[5]),
        conditions=conditions,
        token_estimate=row[10],
    )


def _copy_chain_nodes(source_chain_id: str, target_chain_id: str, conn):
    """Copy all nodes from source chain to target chain."""
    now = datetime.now().isoformat()

    cursor = conn.execute("""
        SELECT template_id, params, order_index, enabled, locked, conditions
        FROM chain_nodes
        WHERE chain_id = ?
        ORDER BY order_index
    """, (source_chain_id,))

    for row in cursor.fetchall():
        node_id = str(uuid4())
        conn.execute("""
            INSERT INTO chain_nodes (
                id, chain_id, template_id, params, order_index,
                enabled, locked, conditions, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node_id,
            target_chain_id,
            row[0],  # template_id
            row[1],  # params
            row[2],  # order_index
            row[3],  # enabled
            row[4],  # locked
            row[5],  # conditions
            now,
            now,
        ))


# =============================================================================
# PUBLIC HELPER FOR AGENT_CLIENT INTEGRATION
# =============================================================================

def get_system_prompt_for_daemon(
    daemon_id: str,
    daemon_name: str = "Cass",
    # Context flags
    project_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    user_id: Optional[str] = None,
    message_count: int = 0,
    unsummarized_count: int = 0,
    has_dream_context: bool = False,
    # Memory context strings (pre-formatted)
    memory_context: Optional[str] = None,
    user_context: Optional[str] = None,
    self_model_context: Optional[str] = None,
    graph_context: Optional[str] = None,
    wiki_context: Optional[str] = None,
    cross_session_context: Optional[str] = None,
    goals_context: Optional[str] = None,
    patterns_context: Optional[str] = None,
    intro_guidance: Optional[str] = None,
    # Enhanced user/relationship modeling
    user_model_context: Optional[str] = None,
    relationship_context: Optional[str] = None,
    # Model info
    model: str = "unknown",
    provider: str = "unknown",
) -> Optional[str]:
    """
    Get the assembled system prompt for a daemon using the active chain.

    This is the main integration point for agent_client.py to use chain-based
    prompts instead of the hardcoded Temple-Codex kernel.

    Args:
        daemon_id: The daemon ID to get the prompt for
        daemon_name: The daemon's display name
        project_id: Active project ID if any
        conversation_id: Current conversation ID
        user_id: Current user ID for user-specific context
        message_count: Total messages in conversation
        unsummarized_count: Messages not yet summarized
        has_dream_context: Whether dream context is available
        memory_context: Pre-formatted memory context string
        user_context: Pre-formatted user profile/observations
        self_model_context: Pre-formatted self-model context
        graph_context: Pre-formatted graph context
        wiki_context: Pre-formatted wiki context
        cross_session_context: Pre-formatted cross-session insights
        goals_context: Pre-formatted goals context
        patterns_context: Pre-formatted patterns context
        intro_guidance: User intro guidance if sparse user model
        user_model_context: Deep understanding of user (identity, values, growth)
        relationship_context: Relationship dynamics (patterns, moments, shaping)
        model: Current model name
        provider: Current provider name

    Returns:
        Assembled system prompt string, or None if no active chain exists
    """
    # Get active chain for daemon
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT id, name FROM prompt_chains
            WHERE daemon_id = ? AND is_active = 1
        """, (daemon_id,))
        row = cursor.fetchone()

        if not row:
            return None  # No active chain, caller should fall back

        chain_id = row[0]

        # Get identity snippet if available
        identity_snippet = None
        snippet_row = conn.execute(
            """SELECT snippet_text FROM daemon_identity_snippets
               WHERE daemon_id = ? AND is_active = 1
               ORDER BY generated_at DESC LIMIT 1""",
            (daemon_id,)
        ).fetchone()
        if snippet_row:
            identity_snippet = snippet_row[0]

    # Get chain nodes
    node_responses = _get_chain_nodes(chain_id)

    # Convert to ChainNode objects
    nodes = []
    for nr in node_responses:
        conditions = [
            Condition.from_dict(c.dict())
            for c in nr.conditions
        ]
        nodes.append(ChainNode(
            id=nr.id,
            template_id=nr.template_id,
            template_slug=nr.template_slug,
            params=nr.params or {},
            order_index=nr.order_index,
            enabled=nr.enabled,
            locked=nr.locked,
            conditions=conditions,
        ))

    # Build temporal context
    temporal_ctx = get_temporal_context()
    now = datetime.now()

    # Build runtime context
    context = RuntimeContext(
        project_id=project_id,
        conversation_id=conversation_id,
        user_id=user_id,
        message_count=message_count,
        unsummarized_count=unsummarized_count,
        has_memories=bool(memory_context),
        memory_context=memory_context,
        has_dream_context=has_dream_context,
        has_self_model=bool(self_model_context),
        self_model_context=self_model_context,
        has_graph_context=bool(graph_context),
        graph_context=graph_context,
        has_wiki_context=bool(wiki_context),
        wiki_context=wiki_context,
        has_cross_session=bool(cross_session_context),
        cross_session_context=cross_session_context,
        has_active_goals=bool(goals_context),
        goals_context=goals_context,
        has_patterns=bool(patterns_context),
        patterns_context=patterns_context,
        has_intro_guidance=bool(intro_guidance),
        intro_guidance=intro_guidance,
        has_user_context=bool(user_context),
        user_context=user_context,
        has_user_model=bool(user_model_context),
        user_model_context=user_model_context,
        has_relationship_model=bool(relationship_context),
        relationship_context=relationship_context,
        current_time=now,
        hour=now.hour,
        temporal_context=temporal_ctx,
        model=model,
        provider=provider,
    )

    # Assemble the chain
    result = assemble_chain(
        nodes=nodes,
        context=context,
        daemon_name=daemon_name,
        identity_snippet=identity_snippet,
    )

    return result.full_text
