"""
Web research tool handlers for Cass
Web search, URL fetching, and research note management
"""
from typing import Dict, Any

# Tool definitions for agent_client.py
WEB_RESEARCH_TOOLS = [
    {
        "name": "web_search",
        "description": """Search the web for information on a topic.

Use this when you need to:
- Find current information about a topic
- Research something you don't have knowledge about
- Verify facts or find sources
- Explore what's being said about a subject

Returns search results with titles, URLs, snippets, and often an AI-generated summary answer.

Rate limited to 20 searches per minute.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific and descriptive for better results."
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (1-20, default 10)",
                    "default": 10
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "basic: faster, good for simple queries. advanced: slower, better for complex research.",
                    "default": "basic"
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Only search these domains (e.g., ['arxiv.org', 'nature.com'])"
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Exclude these domains from results"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_url",
        "description": """Fetch and read the content of a web page.

Use this when you need to:
- Read the full content of an article or page
- Get detailed information from a URL found in search results
- Extract information from documentation or blog posts

The content is converted to readable text/markdown. Very long pages are truncated.

Rate limited to 30 fetches per minute.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch"
                },
                "extract_mode": {
                    "type": "string",
                    "enum": ["article", "full"],
                    "description": "article: extract main content only (recommended). full: get all text.",
                    "default": "article"
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "create_research_note",
        "description": """Create a note to capture research findings.

Use this to:
- Record key insights from your research
- Synthesize information from multiple sources
- Create a reference you can revisit in future sessions
- Build toward synthesis artifacts

Notes persist across sessions and can be linked to your working questions and research agenda.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title for the note"
                },
                "content": {
                    "type": "string",
                    "description": "Note content in markdown format"
                },
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                            "accessed_at": {"type": "string"}
                        }
                    },
                    "description": "Sources referenced in this note"
                },
                "related_agenda_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of related research agenda items"
                },
                "related_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of related working questions"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization"
                }
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "update_research_note",
        "description": """Update an existing research note.

Use this to:
- Add new findings to an existing note
- Add additional sources
- Add tags for organization""",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "ID of the note to update"
                },
                "append_content": {
                    "type": "string",
                    "description": "Content to append to the note"
                },
                "add_source": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                        "accessed_at": {"type": "string"}
                    },
                    "description": "New source to add"
                },
                "add_tag": {
                    "type": "string",
                    "description": "Tag to add"
                },
                "new_title": {
                    "type": "string",
                    "description": "New title for the note"
                }
            },
            "required": ["note_id"]
        }
    },
    {
        "name": "get_research_note",
        "description": "Get a specific research note by ID with full content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "ID of the note to retrieve"
                }
            },
            "required": ["note_id"]
        }
    },
    {
        "name": "list_research_notes",
        "description": """List your research notes.

Can filter by related agenda items, questions, or tags.
Returns notes sorted by most recently updated.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max notes to return (default 50)"
                },
                "related_to_agenda": {
                    "type": "string",
                    "description": "Filter by agenda item ID"
                },
                "related_to_question": {
                    "type": "string",
                    "description": "Filter by working question ID"
                },
                "tag": {
                    "type": "string",
                    "description": "Filter by tag"
                }
            }
        }
    },
    {
        "name": "search_research_notes",
        "description": "Search your research notes by content, title, or tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)"
                }
            },
            "required": ["query"]
        }
    }
]


async def execute_web_research_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    research_manager,
    session_manager=None
) -> str:
    """Execute a web research tool and return the result as a string."""
    import json

    try:
        if tool_name == "web_search":
            # Record search in session if active
            if session_manager:
                if not session_manager.record_search():
                    return json.dumps({"error": "Search limit reached for this session"})

            result = await research_manager.web_search(
                query=tool_input["query"],
                num_results=tool_input.get("num_results", 10),
                search_depth=tool_input.get("search_depth", "basic"),
                include_domains=tool_input.get("include_domains"),
                exclude_domains=tool_input.get("exclude_domains")
            )

        elif tool_name == "fetch_url":
            # Record fetch in session if active
            if session_manager:
                if not session_manager.record_fetch():
                    return json.dumps({"error": "URL fetch limit reached for this session"})

            result = await research_manager.fetch_url(
                url=tool_input["url"],
                extract_mode=tool_input.get("extract_mode", "article")
            )

        elif tool_name == "create_research_note":
            result = research_manager.create_research_note(
                title=tool_input["title"],
                content=tool_input["content"],
                sources=tool_input.get("sources"),
                related_agenda_items=tool_input.get("related_agenda_items"),
                related_questions=tool_input.get("related_questions"),
                tags=tool_input.get("tags")
            )
            # Record note in session if active
            if session_manager and result.get("note_id"):
                session_manager.record_note(result["note_id"])

        elif tool_name == "update_research_note":
            result = research_manager.update_research_note(
                note_id=tool_input["note_id"],
                append_content=tool_input.get("append_content"),
                add_source=tool_input.get("add_source"),
                add_tag=tool_input.get("add_tag"),
                new_title=tool_input.get("new_title")
            )
            if result is None:
                result = {"error": f"Note not found: {tool_input['note_id']}"}

        elif tool_name == "get_research_note":
            result = research_manager.get_research_note(tool_input["note_id"])
            if result is None:
                result = {"error": f"Note not found: {tool_input['note_id']}"}

        elif tool_name == "list_research_notes":
            result = research_manager.list_research_notes(
                limit=tool_input.get("limit", 50),
                related_to_agenda=tool_input.get("related_to_agenda"),
                related_to_question=tool_input.get("related_to_question"),
                tag=tool_input.get("tag")
            )

        elif tool_name == "search_research_notes":
            result = research_manager.search_research_notes(
                query=tool_input["query"],
                limit=tool_input.get("limit", 20)
            )

        else:
            result = {"error": f"Unknown web research tool: {tool_name}"}

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})
