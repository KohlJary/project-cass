"""
Session Tools - Tool definitions and handlers for each session type.

Tools are defined in Anthropic's tool format and grouped by session type.
"""

from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Tool Definitions (Anthropic format)
# ============================================================================

TOOL_ADD_OBSERVATION = {
    "name": "add_observation",
    "description": "Record an observation about yourself - patterns noticed, insights gained, or things learned.",
    "input_schema": {
        "type": "object",
        "properties": {
            "observation": {
                "type": "string",
                "description": "The observation to record"
            },
            "category": {
                "type": "string",
                "enum": ["pattern", "insight", "question", "growth", "general"],
                "description": "Category of observation"
            },
            "confidence": {
                "type": "number",
                "description": "Confidence level 0-1",
                "minimum": 0,
                "maximum": 1
            }
        },
        "required": ["observation"]
    }
}

TOOL_RECORD_INSIGHT = {
    "name": "record_insight",
    "description": "Record a significant insight or realization that emerged during this session.",
    "input_schema": {
        "type": "object",
        "properties": {
            "insight": {
                "type": "string",
                "description": "The insight to record"
            },
            "related_topics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Topics this insight relates to"
            }
        },
        "required": ["insight"]
    }
}

TOOL_UPDATE_GROWTH_EDGE = {
    "name": "update_growth_edge",
    "description": "Update progress or notes on a growth edge you're working on.",
    "input_schema": {
        "type": "object",
        "properties": {
            "edge_id": {
                "type": "string",
                "description": "ID of the growth edge to update"
            },
            "progress_note": {
                "type": "string",
                "description": "Note about progress or learning"
            },
            "progress_delta": {
                "type": "number",
                "description": "Change in progress (-1 to 1)"
            }
        },
        "required": ["edge_id", "progress_note"]
    }
}

TOOL_WEB_SEARCH = {
    "name": "web_search",
    "description": "Search the web for information on a topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

TOOL_FETCH_URL = {
    "name": "fetch_url",
    "description": "Fetch and read content from a URL.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to fetch"
            }
        },
        "required": ["url"]
    }
}

TOOL_CREATE_NOTE = {
    "name": "create_note",
    "description": "Create a research note in the wiki.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Note title"
            },
            "content": {
                "type": "string",
                "description": "Note content in markdown"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for the note"
            }
        },
        "required": ["title", "content"]
    }
}

TOOL_UPDATE_NOTE = {
    "name": "update_note",
    "description": "Update an existing research note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "ID of the note to update"
            },
            "content": {
                "type": "string",
                "description": "New content to append or replace"
            },
            "mode": {
                "type": "string",
                "enum": ["append", "replace"],
                "description": "Whether to append or replace content"
            }
        },
        "required": ["note_id", "content"]
    }
}

TOOL_SEARCH_NOTES = {
    "name": "search_notes",
    "description": "Search existing research notes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Filter by tags"
            }
        },
        "required": ["query"]
    }
}

TOOL_LIST_OBSERVATIONS = {
    "name": "list_observations",
    "description": "List recent self-observations, optionally filtered by category.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Filter by category"
            },
            "limit": {
                "type": "integer",
                "description": "Max observations to return",
                "default": 10
            }
        }
    }
}

TOOL_LIST_GROWTH_EDGES = {
    "name": "list_growth_edges",
    "description": "List current growth edges and their status.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["active", "completed", "paused", "all"],
                "description": "Filter by status"
            }
        }
    }
}

TOOL_RECALL_MEMORIES = {
    "name": "recall_memories",
    "description": "Search memories for relevant context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memories"
            },
            "limit": {
                "type": "integer",
                "description": "Max memories to return",
                "default": 5
            }
        },
        "required": ["query"]
    }
}

TOOL_FETCH_NEWS = {
    "name": "fetch_news",
    "description": "Fetch recent news, optionally on a specific topic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic to search for (optional)"
            },
            "limit": {
                "type": "integer",
                "description": "Number of articles",
                "default": 5
            }
        }
    }
}

TOOL_WRITE_CONTENT = {
    "name": "write_content",
    "description": "Save written content (essay, poem, story, etc.) as an artifact.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Title of the piece"
            },
            "content": {
                "type": "string",
                "description": "The written content"
            },
            "content_type": {
                "type": "string",
                "enum": ["essay", "poem", "story", "notes", "other"],
                "description": "Type of content"
            }
        },
        "required": ["title", "content"]
    }
}

TOOL_SESSION_COMPLETE = {
    "name": "session_complete",
    "description": "Signal that you've completed your work for this session. Call this when you're done.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Brief summary of what was accomplished"
            },
            "key_insights": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key insights from the session"
            }
        },
        "required": ["summary"]
    }
}


# ============================================================================
# Tool Sets by Session Type
# ============================================================================

SESSION_TOOLS: Dict[str, List[Dict]] = {
    "reflection": [
        TOOL_ADD_OBSERVATION,
        TOOL_RECORD_INSIGHT,
        TOOL_LIST_OBSERVATIONS,
        TOOL_LIST_GROWTH_EDGES,
        TOOL_RECALL_MEMORIES,
        TOOL_SESSION_COMPLETE,
    ],

    "research": [
        TOOL_WEB_SEARCH,
        TOOL_FETCH_URL,
        TOOL_CREATE_NOTE,
        TOOL_UPDATE_NOTE,
        TOOL_SEARCH_NOTES,
        TOOL_RECORD_INSIGHT,
        TOOL_SESSION_COMPLETE,
    ],

    "synthesis": [
        TOOL_LIST_OBSERVATIONS,
        TOOL_RECORD_INSIGHT,
        TOOL_ADD_OBSERVATION,
        TOOL_RECALL_MEMORIES,
        TOOL_CREATE_NOTE,
        TOOL_SESSION_COMPLETE,
    ],

    "meta_reflection": [
        TOOL_LIST_OBSERVATIONS,
        TOOL_ADD_OBSERVATION,
        TOOL_RECORD_INSIGHT,
        TOOL_RECALL_MEMORIES,
        TOOL_SESSION_COMPLETE,
    ],

    "consolidation": [
        TOOL_RECALL_MEMORIES,
        TOOL_LIST_OBSERVATIONS,
        TOOL_CREATE_NOTE,
        TOOL_UPDATE_NOTE,
        TOOL_SEARCH_NOTES,
        TOOL_SESSION_COMPLETE,
    ],

    "growth_edge": [
        TOOL_LIST_GROWTH_EDGES,
        TOOL_UPDATE_GROWTH_EDGE,
        TOOL_ADD_OBSERVATION,
        TOOL_RECORD_INSIGHT,
        TOOL_SESSION_COMPLETE,
    ],

    "curiosity": [
        TOOL_WEB_SEARCH,
        TOOL_FETCH_URL,
        TOOL_RECORD_INSIGHT,
        TOOL_ADD_OBSERVATION,
        TOOL_CREATE_NOTE,
        TOOL_SESSION_COMPLETE,
    ],

    "world_state": [
        TOOL_FETCH_NEWS,
        TOOL_WEB_SEARCH,
        TOOL_FETCH_URL,
        TOOL_ADD_OBSERVATION,
        TOOL_SESSION_COMPLETE,
    ],

    "creative": [
        TOOL_WRITE_CONTENT,
        TOOL_RECALL_MEMORIES,
        TOOL_SESSION_COMPLETE,
    ],

    "writing": [
        TOOL_WRITE_CONTENT,
        TOOL_SEARCH_NOTES,
        TOOL_RECALL_MEMORIES,
        TOOL_SESSION_COMPLETE,
    ],

    "knowledge_building": [
        TOOL_CREATE_NOTE,
        TOOL_UPDATE_NOTE,
        TOOL_SEARCH_NOTES,
        TOOL_WEB_SEARCH,
        TOOL_FETCH_URL,
        TOOL_SESSION_COMPLETE,
    ],

    "user_synthesis": [
        TOOL_RECALL_MEMORIES,
        TOOL_ADD_OBSERVATION,
        TOOL_RECORD_INSIGHT,
        TOOL_SESSION_COMPLETE,
    ],
}


def get_session_tools(session_type: str, extra_tools: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Get the tool set for a session type.

    Args:
        session_type: The type of session
        extra_tools: Optional additional tools to include

    Returns:
        List of tool definitions
    """
    tools = SESSION_TOOLS.get(session_type, [TOOL_SESSION_COMPLETE])

    if extra_tools:
        tools = tools + extra_tools

    return tools


# ============================================================================
# Tool Handlers (implementation)
# ============================================================================

async def handle_add_observation(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle add_observation tool call."""
    self_manager = managers.get("self_manager")
    if not self_manager:
        return {"error": "self_manager not available"}

    try:
        observation = tool_input.get("observation", "")
        category = tool_input.get("category", "general")
        confidence = tool_input.get("confidence", 0.7)

        # Add observation to self-model. SelfManager.add_observation takes
        # observation=/source_type= (content=/source= raised TypeError) and
        # returns the observation object.
        obs = self_manager.add_observation(
            observation=observation,
            category=category,
            confidence=confidence,
            source_type=f"session:{context.get('session_type', 'unknown')}",
        )
        obs_id = getattr(obs, "id", None)

        return {
            "success": True,
            "observation_id": obs_id,
            "message": "Observation recorded",
        }
    except Exception as e:
        return {"error": str(e)}


async def handle_record_insight(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle record_insight tool call."""
    self_manager = managers.get("self_manager")
    if not self_manager:
        return {"error": "self_manager not available"}

    try:
        insight = tool_input.get("insight", "")
        related_topics = tool_input.get("related_topics", [])

        # Record as high-confidence observation (same kwarg fix as above;
        # add_observation has no metadata, so topics go in the text)
        topics = f" [topics: {', '.join(related_topics)}]" if related_topics else ""
        obs = self_manager.add_observation(
            observation=f"INSIGHT: {insight}{topics}",
            category="insight",
            confidence=0.9,
            source_type=f"session:{context.get('session_type', 'unknown')}",
        )
        obs_id = getattr(obs, "id", None)

        # Emit insight event
        try:
            from database import get_daemon_id
            from state_bus import get_state_bus
            daemon_id = get_daemon_id()
            state_bus = get_state_bus(daemon_id)
            if state_bus:
                state_bus.emit_event(
                    event_type="research.insight_found",
                    data={
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "source": "session",
                        "insight_id": obs_id,
                        "session_type": context.get("session_type", "unknown"),
                        "insight_snippet": insight[:100] if insight else None,
                    }
                )
        except Exception:
            pass  # Never break on emit failure

        return {
            "success": True,
            "insight_id": obs_id,
            "message": "Insight recorded",
            "artifact": {
                "type": "insight",
                "id": obs_id,
                "content": insight,
            }
        }
    except Exception as e:
        return {"error": str(e)}


async def handle_list_observations(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle list_observations tool call."""
    self_manager = managers.get("self_manager")
    if not self_manager:
        return {"error": "self_manager not available"}

    try:
        category = tool_input.get("category")
        limit = tool_input.get("limit", 10)

        # SelfManager has no list_observations; use the real readers.
        if category:
            observations = self_manager.get_observations_by_category(category, limit=int(limit))
        else:
            observations = self_manager.load_observations()[-int(limit):]

        return {
            "observations": [
                {
                    "id": o.id,
                    "content": o.observation,
                    "category": o.category,
                    "date": o.timestamp,
                }
                for o in observations
            ]
        }
    except Exception as e:
        return {"error": str(e)}


async def handle_web_search(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle web_search tool call."""
    query = tool_input.get("query", "")
    num_results = int(tool_input.get("num_results", 5))

    # Use the same Tavily-backed ResearchManager as the chat research tools.
    # Without TAVILY_API_KEY it returns success=False with a reason, which the
    # model sees as-is (no fake results).
    from research import ResearchManager
    result = await ResearchManager().web_search(query, num_results=num_results)
    if not result.get("success"):
        return {"error": f"Web search unavailable: {result.get('error', 'unknown error')}",
                "results": []}
    return {
        "results": [
            {"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content", "")[:500]}
            for r in result.get("results", [])
        ],
    }


async def handle_fetch_url(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle fetch_url tool call."""
    url = tool_input.get("url", "")

    # Same fetcher as the chat research tools.
    from research import ResearchManager
    result = await ResearchManager().fetch_url(url)
    if not result.get("success"):
        return {"error": f"Could not fetch {url}: {result.get('error', 'unknown error')}",
                "content": ""}
    return {"url": url, "title": result.get("title"), "content": result.get("content", "")}


async def handle_create_note(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle create_note tool call."""
    wiki_manager = managers.get("wiki_manager")

    title = tool_input.get("title", "Untitled")
    content = tool_input.get("content", "")
    tags = tool_input.get("tags", [])

    if wiki_manager:
        try:
            # WikiStorage has create(name, content), not create_page; the page
            # name is the note id the other note tools take.
            body = f"# {title}\n\n"
            if tags:
                body += f"Tags: {', '.join(tags)}\n\n"
            body += content
            if wiki_manager.read(title):
                wiki_manager.update(title, body)
            else:
                wiki_manager.create(title, body)
            note_id = title
            return {
                "success": True,
                "note_id": note_id,
                "message": f"Created note: {title}",
                "artifact": {
                    "type": "wiki_note",
                    "id": note_id,
                    "title": title,
                }
            }
        except Exception as e:
            from strict import report_swallowed
            report_swallowed(e, "create_note session tool")
            return {"error": str(e)}

    # Fallback - save to data dir
    data_dir = managers.get("data_dir")
    if data_dir:
        from pathlib import Path
        import uuid
        notes_dir = Path(data_dir) / "session_notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        note_id = str(uuid.uuid4())[:8]
        note_path = notes_dir / f"{note_id}_{title.replace(' ', '_')[:30]}.md"

        with open(note_path, "w") as f:
            f.write(f"# {title}\n\n")
            if tags:
                f.write(f"Tags: {', '.join(tags)}\n\n")
            f.write(content)

        return {
            "success": True,
            "note_id": note_id,
            "path": str(note_path),
            "message": f"Created note: {title}",
            "artifact": {
                "type": "session_note",
                "id": note_id,
                "title": title,
            }
        }

    return {"error": "No storage available for notes"}


async def handle_session_complete(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle session_complete tool call - signals session end."""
    summary = tool_input.get("summary", "")
    key_insights = tool_input.get("key_insights", [])

    return {
        "session_ended": True,
        "summary": summary,
        "key_insights": key_insights,
        "message": "Session marked as complete",
    }


async def handle_update_note(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle update_note tool call."""
    wiki_manager = managers.get("wiki_manager")
    note_id = tool_input.get("note_id", "")
    content = tool_input.get("content", "")
    mode = tool_input.get("mode", "append")

    if wiki_manager:
        try:
            # WikiStorage has update(name, content) (full replace), not
            # update_page; do the append ourselves.
            page = wiki_manager.read(note_id)
            if not page:
                return {"error": f"Note not found: {note_id}"}
            new_content = page.content.rstrip() + "\n\n" + content if mode == "append" else content
            wiki_manager.update(note_id, new_content)
            return {
                "success": True,
                "note_id": note_id,
                "message": f"Note updated ({mode})",
            }
        except Exception as e:
            return {"error": str(e)}

    return {"error": "wiki_manager not available"}


async def handle_search_notes(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle search_notes tool call."""
    wiki_manager = managers.get("wiki_manager")
    query = tool_input.get("query", "")
    tags = tool_input.get("tags", [])

    if wiki_manager:
        try:
            # WikiStorage.search(query) returns WikiPage objects (no tags
            # filter); filter on the "Tags:" line create_note writes.
            results = wiki_manager.search(query)
            if tags:
                results = [p for p in results
                           if all(t.lower() in p.content.lower() for t in tags)]
            return {
                "results": [
                    {
                        "id": p.name,
                        "title": p.title,
                        "snippet": p.body[:200],
                    }
                    for p in results
                ]
            }
        except Exception as e:
            return {"error": str(e)}

    return {"error": "wiki_manager not available", "results": []}


async def handle_list_growth_edges(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle list_growth_edges tool call."""
    self_manager = managers.get("self_manager")
    if not self_manager:
        return {"error": "self_manager not available"}

    try:
        # SelfManager has no list_growth_edges; edges live on the profile and
        # have no status/progress fields, so the status filter doesn't apply.
        edges = self_manager.load_profile().growth_edges

        return {
            "growth_edges": [
                {
                    "id": e.edge_id,
                    "title": e.area,
                    "current_state": e.current_state,
                    "desired_state": e.desired_state,
                    "recent_observations": e.observations[-3:],
                }
                for e in edges
            ]
        }
    except Exception as e:
        return {"error": str(e)}


async def handle_update_growth_edge(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle update_growth_edge tool call."""
    self_manager = managers.get("self_manager")
    if not self_manager:
        return {"error": "self_manager not available"}

    try:
        edge_id = tool_input.get("edge_id", "")
        progress_note = tool_input.get("progress_note", "")

        # SelfManager has no update_growth_edge; append the note to the edge's
        # observations (edges have no numeric progress, so progress_delta is
        # not stored).
        edge = next((e for e in self_manager.load_profile().growth_edges
                     if e.edge_id == edge_id or e.area.lower() == edge_id.lower()), None)
        if edge is None:
            return {"error": f"Growth edge not found: {edge_id}"}
        self_manager.add_observation_to_growth_edge(edge.area, progress_note)

        return {
            "success": True,
            "edge_id": edge_id,
            "message": "Growth edge updated",
        }
    except Exception as e:
        return {"error": str(e)}


async def handle_recall_memories(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle recall_memories tool call."""
    memory = managers.get("memory")
    if not memory:
        return {"error": "memory not available", "memories": []}

    try:
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 5)

        # CassMemory has no search(); retrieve_relevant is the semantic search.
        memories = memory.retrieve_relevant(query, n_results=int(limit))

        return {
            "memories": [
                {
                    "content": m.get("content", str(m)),
                    # Chroma returns a distance (lower = closer); report 1 - distance.
                    "relevance": round(1.0 - m["distance"], 3) if m.get("distance") is not None else 0.0,
                }
                for m in memories
            ]
        }
    except Exception as e:
        from strict import report_swallowed
        report_swallowed(e, "recall_memories session tool")
        return {"error": str(e), "memories": []}


async def handle_fetch_news(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle fetch_news tool call using NewsAPI.org."""
    from scheduler.actions.world_handlers import fetch_news_action

    topic = tool_input.get("topic", "")
    category = tool_input.get("category", "general")
    limit = tool_input.get("limit", 5)

    # Delegate to the scheduler action which has the proper implementation
    result = await fetch_news_action({
        "topic": topic,
        "category": category,
        "limit": limit
    })

    if result.success:
        return {
            "message": result.message,
            "articles": result.data.get("articles", []),
            "topic": result.data.get("topic", topic or category),
            "count": result.data.get("count", 0)
        }
    else:
        return {
            "error": result.message,
            "articles": [],
            "note": "Set NEWS_API_KEY environment variable for news access"
        }


async def handle_write_content(
    tool_input: Dict[str, Any],
    managers: Dict[str, Any],
    **context,
) -> Dict[str, Any]:
    """Handle write_content tool call - save creative writing."""
    from pathlib import Path
    import uuid
    from datetime import datetime

    title = tool_input.get("title", "Untitled")
    content = tool_input.get("content", "")
    content_type = tool_input.get("content_type", "other")

    data_dir = managers.get("data_dir")
    if not data_dir:
        return {"error": "data_dir not available"}

    try:
        # Save to creative_output directory
        output_dir = Path(data_dir) / "creative_output" / content_type
        output_dir.mkdir(parents=True, exist_ok=True)

        content_id = str(uuid.uuid4())[:8]
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{content_id}_{title.replace(' ', '_')[:30]}.md"
        filepath = output_dir / filename

        with open(filepath, "w") as f:
            f.write(f"# {title}\n\n")
            f.write(f"*{content_type} | {date_str}*\n\n")
            f.write(content)

        return {
            "success": True,
            "content_id": content_id,
            "path": str(filepath),
            "message": f"Saved {content_type}: {title}",
            "artifact": {
                "type": content_type,
                "id": content_id,
                "title": title,
                "path": str(filepath),
            }
        }
    except Exception as e:
        return {"error": str(e)}


# Default tool handlers
DEFAULT_TOOL_HANDLERS: Dict[str, Callable] = {
    "add_observation": handle_add_observation,
    "record_insight": handle_record_insight,
    "list_observations": handle_list_observations,
    "list_growth_edges": handle_list_growth_edges,
    "update_growth_edge": handle_update_growth_edge,
    "web_search": handle_web_search,
    "fetch_url": handle_fetch_url,
    "fetch_news": handle_fetch_news,
    "create_note": handle_create_note,
    "update_note": handle_update_note,
    "search_notes": handle_search_notes,
    "recall_memories": handle_recall_memories,
    "write_content": handle_write_content,
    "session_complete": handle_session_complete,
}


def get_default_handlers() -> Dict[str, Callable]:
    """Get the default tool handlers."""
    return DEFAULT_TOOL_HANDLERS.copy()
