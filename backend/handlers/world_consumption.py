"""
World consumption tool handler - manages article recall and search
"""
from typing import Dict, Any

from world.memory_integration import (
    search_consumed_articles,
    get_article_details,
    list_article_sources,
    get_article_stats,
    get_articles_by_author,
)


async def execute_world_consumption_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    daemon_id: str,
) -> Dict[str, Any]:
    """
    Execute a world consumption tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: Daemon ID

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "search_articles":
            query = tool_input.get("query")
            category = tool_input.get("category")
            source = tool_input.get("source")
            author = tool_input.get("author")
            days_back = tool_input.get("days_back", 30)
            limit = tool_input.get("limit", 10)

            articles = search_consumed_articles(
                daemon_id=daemon_id,
                query=query,
                category=category,
                source=source,
                author=author,
                days_back=days_back,
                limit=limit,
            )

            if not articles:
                filters = []
                if query:
                    filters.append(f"query='{query}'")
                if category:
                    filters.append(f"category='{category}'")
                if source:
                    filters.append(f"source='{source}'")
                if author:
                    filters.append(f"author='{author}'")
                filter_desc = f" matching {', '.join(filters)}" if filters else ""
                return {
                    "success": True,
                    "result": f"No articles found{filter_desc} in the last {days_back} days."
                }

            # Format results
            result_lines = [f"Found {len(articles)} article(s):\n"]
            for article in articles:
                date = article["consumed_at"][:10] if article.get("consumed_at") else "unknown"
                author_str = ""
                if article.get("author_name"):
                    author_str = f"By: {article['author_name']}"
                    if article.get("author_handle"):
                        author_str += f" ({article['author_handle']})"
                    author_str += " | "
                result_lines.append(
                    f"**{article['headline']}**\n"
                    f"  {author_str}Source: {article.get('source', 'Unknown')} | "
                    f"Category: {article.get('category', 'general')} | "
                    f"Read: {date}\n"
                    f"  ID: `{article['id']}`\n"
                    f"  Summary: {(article.get('summary') or 'No summary')[:200]}...\n"
                )

            result_lines.append("\n*Use get_article with an ID for full details including extractions.*")

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "get_articles_by_author":
            author_name = tool_input.get("author_name")
            author_entity_id = tool_input.get("author_entity_id")
            limit = tool_input.get("limit", 20)

            if not author_name and not author_entity_id:
                return {
                    "success": False,
                    "error": "Either author_name or author_entity_id is required"
                }

            articles = get_articles_by_author(
                daemon_id=daemon_id,
                author_entity_id=author_entity_id,
                author_name=author_name,
                limit=limit,
            )

            if not articles:
                author_desc = author_name or author_entity_id
                return {
                    "success": True,
                    "result": f"No articles found by author '{author_desc}'."
                }

            # Get author info from first article
            first = articles[0]
            author_info = first.get("author_name", "Unknown")
            if first.get("author_handle"):
                author_info += f" ({first['author_handle']})"

            result_lines = [f"Found {len(articles)} article(s) by {author_info}:\n"]
            for article in articles:
                date = article["consumed_at"][:10] if article.get("consumed_at") else "unknown"
                result_lines.append(
                    f"**{article['headline']}**\n"
                    f"  Source: {article.get('source', 'Unknown')} | "
                    f"Read: {date}\n"
                    f"  ID: `{article['id']}`\n"
                    f"  Summary: {(article.get('summary') or 'No summary')[:200]}...\n"
                )

            return {
                "success": True,
                "result": "\n".join(result_lines)
            }

        elif tool_name == "get_article":
            article_id = tool_input.get("article_id")
            if not article_id:
                return {
                    "success": False,
                    "error": "article_id is required"
                }

            article = get_article_details(daemon_id, article_id)

            if not article:
                return {
                    "success": True,
                    "result": f"No article found with ID '{article_id}'."
                }

            # Format full article details
            lines = [
                f"# {article['headline']}\n",
            ]

            # Add author info if available
            if article.get('author_name'):
                author_line = f"**Author:** {article['author_name']}"
                if article.get('author_handle'):
                    author_line += f" ({article['author_handle']})"
                lines.append(author_line)

            lines.extend([
                f"**Source:** {article.get('source', 'Unknown')}",
                f"**Category:** {article.get('category', 'general')}",
                f"**Read:** {article.get('consumed_at', 'unknown')[:10]}",
                f"**URL:** {article['url']}\n",
                f"## Summary\n{article.get('summary', 'No summary available.')}\n",
            ])

            if article.get("observations"):
                lines.append("## Observations")
                for obs in article["observations"]:
                    text = obs.get("text", obs) if isinstance(obs, dict) else obs
                    lines.append(f"- {text}")
                lines.append("")

            if article.get("questions"):
                lines.append("## Questions Raised")
                for q in article["questions"]:
                    text = q.get("question", q) if isinstance(q, dict) else q
                    lines.append(f"- {text}")
                lines.append("")

            if article.get("opinions"):
                lines.append("## Opinions Formed")
                for op in article["opinions"]:
                    if isinstance(op, dict):
                        lines.append(f"- **{op.get('topic', 'Unknown')}:** {op.get('position', 'N/A')}")
                    else:
                        lines.append(f"- {op}")
                lines.append("")

            if article.get("growth_edges"):
                lines.append("## Growth Edges Identified")
                for ge in article["growth_edges"]:
                    if isinstance(ge, dict):
                        lines.append(f"- **{ge.get('area', 'Unknown')}:** {ge.get('current_state', 'N/A')} → {ge.get('desired_state', 'N/A')}")
                    else:
                        lines.append(f"- {ge}")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        elif tool_name == "list_article_sources":
            days_back = tool_input.get("days_back", 30)
            sources = list_article_sources(daemon_id, days_back)

            if not sources:
                return {
                    "success": True,
                    "result": f"No articles consumed in the last {days_back} days."
                }

            lines = [f"Article sources (last {days_back} days):\n"]
            for src in sources:
                lines.append(f"- **{src['source']}**: {src['count']} article(s)")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        elif tool_name == "get_reading_stats":
            stats = get_article_stats(daemon_id)

            if not stats:
                return {
                    "success": True,
                    "result": "No article consumption data available."
                }

            lines = [
                "# Reading Statistics\n",
                f"**Total articles read:** {stats.get('total_articles', 0)}",
                f"**Articles in last 7 days:** {stats.get('articles_last_7_days', 0)}",
                f"**Total tokens used:** {stats.get('total_tokens_used', 0):,}\n",
            ]

            if stats.get("by_category"):
                lines.append("**By category:**")
                for cat, count in stats["by_category"].items():
                    lines.append(f"  - {cat}: {count}")

            return {
                "success": True,
                "result": "\n".join(lines)
            }

        else:
            return {
                "success": False,
                "error": f"Unknown world consumption tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        }
