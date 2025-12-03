"""
Journal tool handler - manages journal entries
"""
from typing import Dict


async def execute_journal_tool(
    tool_name: str,
    tool_input: Dict,
    memory
) -> Dict:
    """
    Execute a journal tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        memory: CassMemory instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "recall_journal":
            date = tool_input.get("date")

            if date:
                # Get specific journal entry
                journal = memory.get_journal_entry(date)
                if not journal:
                    return {
                        "success": True,
                        "result": f"No journal entry found for {date}. You may not have journaled that day, or the journal hasn't been generated yet."
                    }

                return {
                    "success": True,
                    "result": f"# Journal Entry - {date}\n\n{journal['content']}\n\n---\n*Written: {journal['metadata'].get('timestamp', 'unknown')}*"
                }
            else:
                # Get most recent journal
                journals = memory.get_recent_journals(n=1)
                if not journals:
                    return {
                        "success": True,
                        "result": "No journal entries found yet. You haven't written any journals."
                    }

                journal = journals[0]
                date = journal["metadata"].get("journal_date", "unknown")
                return {
                    "success": True,
                    "result": f"# Most Recent Journal - {date}\n\n{journal['content']}\n\n---\n*Written: {journal['metadata'].get('timestamp', 'unknown')}*"
                }

        elif tool_name == "list_journals":
            limit = tool_input.get("limit", 10)
            journals = memory.get_recent_journals(n=limit)

            if not journals:
                return {
                    "success": True,
                    "result": "No journal entries found yet."
                }

            journal_list = []
            for j in journals:
                date = j["metadata"].get("journal_date", "unknown")
                preview = j["content"][:150] + "..." if len(j["content"]) > 150 else j["content"]
                summaries = j["metadata"].get("summary_count", 0)
                journal_list.append(f"**{date}** ({summaries} summaries used)\n> {preview}")

            return {
                "success": True,
                "result": f"Found {len(journals)} journal(s):\n\n" + "\n\n".join(journal_list)
            }

        elif tool_name == "search_journals":
            query = tool_input["query"]
            limit = tool_input.get("limit", 5)

            # Use semantic search on journal type
            results = memory.collection.query(
                query_texts=[query],
                n_results=limit,
                where={"type": "journal"}
            )

            if not results["documents"] or not results["documents"][0]:
                return {
                    "success": True,
                    "result": f"No journal entries found matching '{query}'."
                }

            result_lines = [f"Found {len(results['documents'][0])} journal(s) matching '{query}':\n"]
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                date = metadata.get("journal_date", "unknown")
                distance = results["distances"][0][i] if results["distances"] else 1.0
                relevance_pct = int(max(0, 1 - distance) * 100)
                preview = doc[:200] + "..." if len(doc) > 200 else doc
                result_lines.append(f"**{date}** ({relevance_pct}% relevant)\n> {preview}")

            return {
                "success": True,
                "result": "\n\n".join(result_lines)
            }

        else:
            return {"success": False, "error": f"Unknown journal tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
