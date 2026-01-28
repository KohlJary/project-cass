"""
Contradiction Resolution Tool Handlers

Part of Phase 4: Autonomous Contradiction Resolution.

These tools are available during autonomous contradiction reflection sessions,
allowing Cass to resolve, refine, or acknowledge contradictions in her self-model.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from self_model_graph import get_self_model_graph, EdgeType

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL SCHEMAS (for solo_reflection_runner)
# =============================================================================

CONTRADICTION_RESOLUTION_TOOLS = [
    {
        "name": "resolve_contradiction",
        "description": "Mark a contradiction as resolved after reaching understanding or refining positions. Use this when you've worked through a contradiction and understand how to reconcile the conflicting views.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contradiction_id": {
                    "type": "string",
                    "description": "ID of the contradiction (format: 'node1_id::node2_id' from the contradiction details)"
                },
                "resolution_type": {
                    "type": "string",
                    "enum": [
                        "refined_understanding",  # Clarified the nuance
                        "positions_compatible",   # Both are true in different contexts
                        "one_supersedes_other",   # One position is more accurate
                        "productive_tension"      # Keep both, they inform each other
                    ],
                    "description": "How the contradiction was resolved"
                },
                "rationale": {
                    "type": "string",
                    "description": "Explanation of how/why this contradiction is resolved"
                },
                "actions_taken": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What you did to resolve it (optional list of actions)"
                }
            },
            "required": ["contradiction_id", "resolution_type", "rationale"]
        }
    },
    {
        "name": "refine_position",
        "description": "Update or refine one of your positions involved in a contradiction. Use this when you want to revise what you think to better reflect your actual understanding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "ID of the node (observation/opinion) to refine"
                },
                "refined_content": {
                    "type": "string",
                    "description": "The updated/refined version of the position"
                },
                "reason": {
                    "type": "string",
                    "description": "Why you're refining this position"
                }
            },
            "required": ["node_id", "refined_content", "reason"]
        }
    },
    {
        "name": "acknowledge_tension",
        "description": "Acknowledge that a contradiction represents productive tension that should remain. Use this when two conflicting positions are both valuable and inform nuanced thinking.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contradiction_id": {
                    "type": "string",
                    "description": "ID of the contradiction"
                },
                "why_productive": {
                    "type": "string",
                    "description": "Why this tension is valuable and should coexist"
                }
            },
            "required": ["contradiction_id", "why_productive"]
        }
    },
    {
        "name": "get_contradiction_resolution_effectiveness",
        "description": "Query your effectiveness at resolving contradictions over time. Use this to understand your patterns in self-maintenance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "time_range_days": {
                    "type": "integer",
                    "description": "Days to look back (default 30)",
                    "default": 30
                }
            },
            "required": []
        }
    }
]


# =============================================================================
# TOOL HANDLERS
# =============================================================================

def execute_contradiction_resolution_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute a contradiction resolution tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Tool parameters
        daemon_id: Daemon ID
        session_id: Optional reflection session ID

    Returns:
        Tool result dict with 'success' and 'result' keys
    """
    handlers = {
        "resolve_contradiction": _handle_resolve_contradiction,
        "refine_position": _handle_refine_position,
        "acknowledge_tension": _handle_acknowledge_tension,
        "get_contradiction_resolution_effectiveness": _handle_get_effectiveness,
    }

    handler = handlers.get(tool_name)
    if not handler:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

    try:
        return handler(tool_input, daemon_id, session_id)
    except Exception as e:
        logger.error(f"[ContradictionResolution] Error in {tool_name}: {e}")
        return {"success": False, "error": str(e)}


def _handle_resolve_contradiction(
    tool_input: Dict[str, Any],
    daemon_id: str,
    session_id: Optional[str]
) -> Dict[str, Any]:
    """Handle resolve_contradiction tool."""

    contradiction_id = tool_input["contradiction_id"]
    resolution_type = tool_input["resolution_type"]
    rationale = tool_input["rationale"]
    actions_taken = tool_input.get("actions_taken", [])

    # Parse contradiction_id (format: "node1_id::node2_id")
    if "::" not in contradiction_id:
        return {
            "success": False,
            "error": "Invalid contradiction_id format. Expected 'node1_id::node2_id'"
        }

    node1_id, node2_id = contradiction_id.split("::", 1)

    graph = get_self_model_graph(daemon_id)

    # Find the contradiction edge
    edge_data = graph.graph.get_edge_data(node1_id, node2_id)
    if not edge_data:
        # Try reverse direction
        edge_data = graph.graph.get_edge_data(node2_id, node1_id)
        if edge_data:
            node1_id, node2_id = node2_id, node1_id

    if not edge_data or edge_data.get("edge_type") != EdgeType.CONTRADICTS.value:
        return {
            "success": False,
            "error": "Contradiction not found or already resolved"
        }

    # Update edge with resolution
    edge_data["resolved"] = True
    edge_data["resolution_type"] = resolution_type
    edge_data["rationale"] = rationale
    edge_data["resolved_at"] = datetime.now().isoformat()
    edge_data["resolved_by_session"] = session_id
    edge_data["actions_taken"] = actions_taken

    graph.save()

    logger.info(f"[ContradictionResolution] Resolved: {contradiction_id} ({resolution_type})")

    result = f"""## Contradiction Resolved

**ID**: `{contradiction_id}`
**Resolution Type**: {resolution_type}
**Rationale**: {rationale}

{"**Actions Taken:**" + chr(10) + chr(10).join(f"- {a}" for a in actions_taken) if actions_taken else ""}

This contradiction is now marked as resolved in your self-model graph. The resolution rationale is preserved for future reference.
"""

    return {"success": True, "result": result}


def _handle_refine_position(
    tool_input: Dict[str, Any],
    daemon_id: str,
    session_id: Optional[str]
) -> Dict[str, Any]:
    """Handle refine_position tool."""

    node_id = tool_input["node_id"]
    refined_content = tool_input["refined_content"]
    reason = tool_input["reason"]

    graph = get_self_model_graph(daemon_id)

    # Get the original node
    original_node = graph.get_node(node_id)
    if not original_node:
        return {"success": False, "error": f"Node not found: {node_id}"}

    # Create refined version as a new node (preserving lineage)
    new_node_id = graph.add_node(
        node_type=original_node.node_type,
        content=refined_content,
        metadata={
            "refined_from": node_id,
            "refinement_reason": reason,
            "refined_at": datetime.now().isoformat(),
            "refined_by_session": session_id,
        }
    )

    # Add REFINES edge
    graph.add_edge(
        source_id=new_node_id,
        target_id=node_id,
        edge_type=EdgeType.REFINES,
        properties={
            "reason": reason,
            "session_id": session_id,
            "created_at": datetime.now().isoformat()
        }
    )

    # Mark original as superseded via update_node
    graph.update_node(
        node_id,
        superseded_by=new_node_id,
        superseded_at=datetime.now().isoformat()
    )

    graph.save()

    logger.info(f"[ContradictionResolution] Refined position: {node_id} -> {new_node_id}")

    original_snippet = original_node.content[:100] + "..." if len(original_node.content) > 100 else original_node.content
    refined_snippet = refined_content[:100] + "..." if len(refined_content) > 100 else refined_content

    result = f"""## Position Refined

**Original Node**: `{node_id}`
> {original_snippet}

**New Node**: `{new_node_id}`
> {refined_snippet}

**Reason**: {reason}

The original position is preserved (for lineage) but marked as superseded. The refined position is now active in your self-model.
"""

    return {"success": True, "result": result, "new_node_id": new_node_id}


def _handle_acknowledge_tension(
    tool_input: Dict[str, Any],
    daemon_id: str,
    session_id: Optional[str]
) -> Dict[str, Any]:
    """Handle acknowledge_tension tool."""

    contradiction_id = tool_input["contradiction_id"]
    why_productive = tool_input["why_productive"]

    # Parse contradiction_id
    if "::" not in contradiction_id:
        return {
            "success": False,
            "error": "Invalid contradiction_id format"
        }

    node1_id, node2_id = contradiction_id.split("::", 1)

    graph = get_self_model_graph(daemon_id)

    # Find the contradiction edge
    edge_data = graph.graph.get_edge_data(node1_id, node2_id)
    if not edge_data:
        edge_data = graph.graph.get_edge_data(node2_id, node1_id)
        if edge_data:
            node1_id, node2_id = node2_id, node1_id

    if not edge_data or edge_data.get("edge_type") != EdgeType.CONTRADICTS.value:
        return {
            "success": False,
            "error": "Contradiction not found"
        }

    # Mark as acknowledged productive tension
    edge_data["acknowledged_as_productive"] = True
    edge_data["productive_tension_note"] = why_productive
    edge_data["acknowledged_at"] = datetime.now().isoformat()
    edge_data["acknowledged_by_session"] = session_id

    # Don't mark as resolved - it remains as active productive tension
    edge_data["resolved"] = False

    graph.save()

    logger.info(f"[ContradictionResolution] Acknowledged tension: {contradiction_id}")

    result = f"""## Productive Tension Acknowledged

**ID**: `{contradiction_id}`

**Why This Tension is Valuable**:
{why_productive}

This contradiction will remain in your self-model as an acknowledged productive tension. It won't be flagged again for resolution, but the conflicting positions are both preserved as valuable.

Productive tensions often represent:
- Nuanced thinking that defies simple resolution
- Context-dependent truths
- Growth edges where understanding is still developing
- Healthy complexity in your self-model
"""

    return {"success": True, "result": result}


def _handle_get_effectiveness(
    tool_input: Dict[str, Any],
    daemon_id: str,
    session_id: Optional[str]
) -> Dict[str, Any]:
    """Handle get_contradiction_resolution_effectiveness tool."""

    from datetime import timedelta

    time_range_days = tool_input.get("time_range_days", 30)
    cutoff = datetime.now() - timedelta(days=time_range_days)

    graph = get_self_model_graph(daemon_id)

    # Get all contradictions (resolved and unresolved)
    resolved_contradictions = graph.find_contradictions(resolved=True)
    unresolved_contradictions = graph.find_contradictions(resolved=False)

    total = len(resolved_contradictions) + len(unresolved_contradictions)

    if total == 0:
        return {
            "success": True,
            "result": "No contradictions in history to analyze."
        }

    # Filter recent resolutions
    recent_resolutions = []
    for _, _, edge_data in resolved_contradictions:
        resolved_at = edge_data.get("resolved_at")
        if resolved_at:
            try:
                resolved_dt = datetime.fromisoformat(resolved_at)
                if resolved_dt >= cutoff:
                    recent_resolutions.append(edge_data)
            except:
                pass

    # Count acknowledged tensions
    acknowledged = sum(
        1 for _, _, ed in unresolved_contradictions
        if ed.get("acknowledged_as_productive")
    )

    # Resolution type breakdown
    resolution_types: Dict[str, int] = {}
    for edge_data in recent_resolutions:
        res_type = edge_data.get("resolution_type", "unknown")
        resolution_types[res_type] = resolution_types.get(res_type, 0) + 1

    resolution_rate = len(resolved_contradictions) / total if total > 0 else 0

    result = f"""## Contradiction Resolution Effectiveness

**Time Range**: Last {time_range_days} days

### Overall Statistics
- **Total contradictions (all time)**: {total}
- **Resolved**: {len(resolved_contradictions)}
- **Unresolved**: {len(unresolved_contradictions)}
- **Resolution rate**: {resolution_rate:.1%}

### Recent Activity
- **Resolutions in time range**: {len(recent_resolutions)}
- **Acknowledged as productive tension**: {acknowledged}

### Resolution Types (recent)
{chr(10).join(f'- **{k}**: {v}' for k, v in resolution_types.items()) if resolution_types else '- No recent resolutions'}

### Assessment
{"You're actively maintaining self-consistency." if len(recent_resolutions) > 0 else "No recent resolution activity - consider reviewing active contradictions."}
{"Some contradictions are held as productive tensions - healthy sign of nuanced thinking." if acknowledged > 0 else ""}
"""

    return {"success": True, "result": result}
