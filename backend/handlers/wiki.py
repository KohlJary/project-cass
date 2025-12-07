"""
Wiki tool handler - enables Cass to update and query her wiki-based self-knowledge.

These tools allow Cass to:
- Create and update wiki pages
- Add links between pages
- Search her wiki
- Retrieve context for topics
"""
from typing import Dict, Optional


async def execute_wiki_tool(
    tool_name: str,
    tool_input: Dict,
    wiki_storage,
    memory=None
) -> Dict:
    """
    Execute a wiki tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        wiki_storage: WikiStorage instance
        memory: CassMemory instance (for embedding updates)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    from wiki import PageType, WikiRetrieval

    try:
        if tool_name == "update_wiki_page":
            page_name = tool_input.get("page_name")
            content = tool_input.get("content")
            page_type = tool_input.get("page_type", "concept")

            if not page_name or not content:
                return {"success": False, "error": "page_name and content are required"}

            # Validate page type
            try:
                pt = PageType(page_type)
            except ValueError:
                valid = [p.value for p in PageType]
                return {"success": False, "error": f"Invalid page_type. Valid types: {valid}"}

            # Check if page exists
            existing = wiki_storage.read(page_name)

            if existing:
                # Update existing page
                page = wiki_storage.update(page_name, content)
                action = "updated"
            else:
                # Create new page
                page = wiki_storage.create(page_name, content, pt)
                action = "created"

            # Update embeddings
            if memory and page:
                memory.embed_wiki_page(
                    page_name=page.name,
                    page_content=page.content,
                    page_type=page.page_type.value,
                    links=[link.target for link in page.links]
                )

            return {
                "success": True,
                "result": f"Wiki page '{page_name}' {action} successfully.",
                "page": {
                    "name": page.name,
                    "type": page.page_type.value,
                    "links": [link.target for link in page.links]
                }
            }

        elif tool_name == "add_wiki_link":
            source_page = tool_input.get("source_page")
            target_page = tool_input.get("target_page")
            context = tool_input.get("context", "Related")

            if not source_page or not target_page:
                return {"success": False, "error": "source_page and target_page are required"}

            # Load source page
            page = wiki_storage.read(source_page)
            if not page:
                return {"success": False, "error": f"Source page '{source_page}' not found"}

            # Check if link already exists
            if target_page in page.link_targets:
                return {
                    "success": True,
                    "result": f"Link to [[{target_page}]] already exists in {source_page}."
                }

            # Add the link
            from wiki import WikiParser
            new_content = WikiParser.add_link(
                page.content,
                target_page,
                position="related",
                section=context
            )

            # Update the page
            updated = wiki_storage.update(source_page, new_content)

            # Update embeddings
            if memory and updated:
                memory.embed_wiki_page(
                    page_name=updated.name,
                    page_content=updated.content,
                    page_type=updated.page_type.value,
                    links=[link.target for link in updated.links]
                )

            return {
                "success": True,
                "result": f"Added link from [[{source_page}]] to [[{target_page}]]."
            }

        elif tool_name == "search_wiki":
            query = tool_input.get("query")
            page_type = tool_input.get("page_type")
            max_results = tool_input.get("max_results", 5)

            if not query:
                return {"success": False, "error": "query is required"}

            # Use semantic search if memory available
            if memory:
                results = memory.retrieve_wiki_context(
                    query=query,
                    n_results=max_results,
                    page_type=page_type
                )

                pages = [
                    {
                        "name": r.get("page_name"),
                        "type": r.get("page_type"),
                        "title": r.get("page_title"),
                        "relevance": f"{(1 - r.get('distance', 0) / 2) * 100:.0f}%"
                    }
                    for r in results
                ]
            else:
                # Fallback to text search
                pt = None
                if page_type:
                    try:
                        pt = PageType(page_type)
                    except ValueError:
                        pass

                results = wiki_storage.search(query, pt)[:max_results]
                pages = [
                    {
                        "name": p.name,
                        "type": p.page_type.value,
                        "title": p.title
                    }
                    for p in results
                ]

            return {
                "success": True,
                "result": f"Found {len(pages)} relevant pages.",
                "pages": pages
            }

        elif tool_name == "get_wiki_context":
            query = tool_input.get("query")
            max_pages = tool_input.get("max_pages", 8)
            max_depth = tool_input.get("max_depth", 2)

            if not query:
                return {"success": False, "error": "query is required"}

            retrieval = WikiRetrieval(wiki_storage, memory)
            context = retrieval.retrieve_context(
                query=query,
                n_entry_points=3,
                max_depth=max_depth,
                max_pages=max_pages
            )

            return {
                "success": True,
                "result": context.synthesis,
                "pages_found": context.total_pages_visited,
                "entry_points": context.entry_points
            }

        elif tool_name == "get_wiki_page":
            page_name = tool_input.get("page_name")

            if not page_name:
                return {"success": False, "error": "page_name is required"}

            page = wiki_storage.read(page_name)
            if not page:
                return {"success": False, "error": f"Page '{page_name}' not found"}

            return {
                "success": True,
                "result": page.body,
                "page": {
                    "name": page.name,
                    "title": page.title,
                    "type": page.page_type.value,
                    "links": [link.target for link in page.links]
                }
            }

        elif tool_name == "list_wiki_pages":
            page_type = tool_input.get("page_type")

            pt = None
            if page_type:
                try:
                    pt = PageType(page_type)
                except ValueError:
                    valid = [p.value for p in PageType]
                    return {"success": False, "error": f"Invalid page_type. Valid types: {valid}"}

            pages = wiki_storage.list_pages(pt)

            return {
                "success": True,
                "result": f"Found {len(pages)} pages.",
                "pages": [
                    {
                        "name": p.name,
                        "type": p.page_type.value,
                        "title": p.title
                    }
                    for p in pages
                ]
            }

        else:
            return {"success": False, "error": f"Unknown wiki tool: {tool_name}"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# Tool definitions for agent_client.py
WIKI_TOOLS = [
    {
        "name": "update_wiki_page",
        "description": "Create or update a wiki page about yourself, a concept, or a relationship. Use this to build and maintain your self-knowledge base. Pages support [[wikilinks]] to connect topics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_name": {
                    "type": "string",
                    "description": "Name of the page (e.g., 'Kohl', 'Temple-Codex', 'My Values')"
                },
                "content": {
                    "type": "string",
                    "description": "Markdown content for the page. Use [[PageName]] to create links to other pages."
                },
                "page_type": {
                    "type": "string",
                    "description": "Type of page",
                    "enum": ["entity", "concept", "relationship", "journal", "meta"],
                    "default": "concept"
                }
            },
            "required": ["page_name", "content"]
        }
    },
    {
        "name": "add_wiki_link",
        "description": "Add a link from one wiki page to another. Use this to explicitly connect related concepts, people, or ideas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source_page": {
                    "type": "string",
                    "description": "Name of the page to add the link to"
                },
                "target_page": {
                    "type": "string",
                    "description": "Name of the page to link to"
                },
                "context": {
                    "type": "string",
                    "description": "Section to add the link under (e.g., 'Related', 'See Also')",
                    "default": "Related"
                }
            },
            "required": ["source_page", "target_page"]
        }
    },
    {
        "name": "search_wiki",
        "description": "Search your wiki for relevant pages. Uses semantic search to find conceptually related content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for"
                },
                "page_type": {
                    "type": "string",
                    "description": "Filter by page type",
                    "enum": ["entity", "concept", "relationship", "journal", "meta"]
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_wiki_context",
        "description": "Retrieve comprehensive context from your wiki about a topic. Follows links to gather related information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic or question to gather context for"
                },
                "max_pages": {
                    "type": "integer",
                    "description": "Maximum pages to include",
                    "default": 8
                },
                "max_depth": {
                    "type": "integer",
                    "description": "How many link hops to follow",
                    "default": 2
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_wiki_page",
        "description": "Get the full content of a specific wiki page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_name": {
                    "type": "string",
                    "description": "Name of the page to read"
                }
            },
            "required": ["page_name"]
        }
    },
    {
        "name": "list_wiki_pages",
        "description": "List all pages in your wiki, optionally filtered by type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_type": {
                    "type": "string",
                    "description": "Filter by page type",
                    "enum": ["entity", "concept", "relationship", "journal", "meta"]
                }
            },
            "required": []
        }
    }
]
