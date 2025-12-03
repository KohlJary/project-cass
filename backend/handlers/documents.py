"""
Document tool handler - manages project documents
"""
from typing import Dict


async def execute_document_tool(
    tool_name: str,
    tool_input: Dict,
    project_id: str,
    project_manager,
    memory
) -> Dict:
    """
    Execute a project document tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        project_id: Project ID context
        project_manager: ProjectManager instance
        memory: CassMemory instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "create_project_document":
            document = project_manager.add_document(
                project_id=project_id,
                title=tool_input["title"],
                content=tool_input["content"],
                created_by="cass"
            )
            if not document:
                return {"success": False, "error": "Project not found"}

            # Embed the document
            chunks = memory.embed_project_document(
                project_id=project_id,
                document_id=document.id,
                title=document.title,
                content=document.content
            )
            project_manager.mark_document_embedded(project_id, document.id)

            return {
                "success": True,
                "result": f"Created document '{document.title}' (ID: {document.id}) with {chunks} chunks embedded."
            }

        elif tool_name == "list_project_documents":
            documents = project_manager.list_documents(project_id)
            if not documents:
                return {
                    "success": True,
                    "result": "No documents found in this project."
                }

            doc_list = []
            for d in documents:
                preview = d.content[:150] + "..." if len(d.content) > 150 else d.content
                doc_list.append(f"- **{d.title}** (ID: {d.id})\n  Created: {d.created_at[:10]}\n  Preview: {preview}")

            return {
                "success": True,
                "result": f"Found {len(documents)} document(s):\n\n" + "\n\n".join(doc_list)
            }

        elif tool_name == "get_project_document":
            document = None
            if tool_input.get("document_id"):
                document = project_manager.get_document(project_id, tool_input["document_id"])
            elif tool_input.get("title"):
                document = project_manager.get_document_by_title(project_id, tool_input["title"])

            if not document:
                return {"success": False, "error": "Document not found"}

            return {
                "success": True,
                "result": f"# {document.title}\n\n**ID:** {document.id}\n**Created:** {document.created_at}\n**Updated:** {document.updated_at}\n\n---\n\n{document.content}"
            }

        elif tool_name == "update_project_document":
            document = project_manager.update_document(
                project_id=project_id,
                document_id=tool_input["document_id"],
                title=tool_input.get("title"),
                content=tool_input.get("content")
            )

            if not document:
                return {"success": False, "error": "Document not found"}

            # Re-embed if content changed
            if tool_input.get("content"):
                memory.remove_project_document_embeddings(project_id, document.id)
                chunks = memory.embed_project_document(
                    project_id=project_id,
                    document_id=document.id,
                    title=document.title,
                    content=document.content
                )
                project_manager.mark_document_embedded(project_id, document.id)
                return {
                    "success": True,
                    "result": f"Updated document '{document.title}' and re-embedded ({chunks} chunks)."
                }

            return {
                "success": True,
                "result": f"Updated document '{document.title}'."
            }

        elif tool_name == "search_project_documents":
            query = tool_input["query"]
            limit = tool_input.get("limit", 5)

            results = memory.search_project_documents(
                query=query,
                project_id=project_id,
                n_results=limit
            )

            if not results:
                return {
                    "success": True,
                    "result": f"No documents found matching '{query}'."
                }

            result_lines = [f"Found {len(results)} document(s) matching '{query}':\n"]
            for r in results:
                relevance_pct = int(r["relevance"] * 100)
                result_lines.append(
                    f"- **{r['title']}** (ID: {r['document_id']}, {relevance_pct}% relevant)\n"
                    f"  Best matching section:\n  > {r['best_chunk'][:200]}..."
                )

            return {
                "success": True,
                "result": "\n\n".join(result_lines)
            }

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
