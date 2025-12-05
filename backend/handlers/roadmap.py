"""
Roadmap tool handler - Work item management for Cass
Enables Cass to create, query, and update roadmap items
"""
from typing import Dict, Optional
from roadmap import RoadmapManager, ItemStatus, ItemPriority, ItemType


async def execute_roadmap_tool(
    tool_name: str,
    tool_input: Dict,
    roadmap_manager: RoadmapManager,
    conversation_id: Optional[str] = None
) -> Dict:
    """
    Handle roadmap-related tool calls.

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool
        roadmap_manager: RoadmapManager instance
        conversation_id: Current conversation ID (for linking items)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "create_roadmap_item":
            title = tool_input["title"]
            description = tool_input.get("description", "")
            priority = tool_input.get("priority", ItemPriority.P2.value)
            item_type = tool_input.get("item_type", ItemType.FEATURE.value)
            status = tool_input.get("status", ItemStatus.BACKLOG.value)
            tags = tool_input.get("tags", [])
            assigned_to = tool_input.get("assigned_to")
            project_id = tool_input.get("project_id")
            milestone_id = tool_input.get("milestone_id")

            item = roadmap_manager.create_item(
                title=title,
                description=description,
                status=status,
                priority=priority,
                item_type=item_type,
                tags=tags,
                assigned_to=assigned_to,
                project_id=project_id,
                milestone_id=milestone_id,
                source_conversation_id=conversation_id,
                created_by="cass",
            )

            # Format response
            type_icons = {
                "feature": "✨",
                "bug": "🐛",
                "enhancement": "⚡",
                "chore": "🔧",
                "research": "🔍",
                "documentation": "📚",
            }
            icon = type_icons.get(item_type, "📌")

            parts = [f"Created roadmap item **#{item.id}**: {icon} {title}"]
            parts.append(f"\n  [{priority}] {item_type} | {status}")
            if tags:
                parts.append(f"\n  Tags: {', '.join('+' + t for t in tags)}")
            if assigned_to:
                parts.append(f"\n  Assigned to: {assigned_to}")

            return {
                "success": True,
                "result": "".join(parts),
                "item_id": item.id
            }

        elif tool_name == "list_roadmap_items":
            status = tool_input.get("status")
            priority = tool_input.get("priority")
            item_type = tool_input.get("item_type")
            assigned_to = tool_input.get("assigned_to")
            project_id = tool_input.get("project_id")
            milestone_id = tool_input.get("milestone_id")
            include_done = tool_input.get("include_done", False)

            # Map include_done to the archived filter
            items = roadmap_manager.list_items(
                status=status,
                priority=priority,
                item_type=item_type,
                assigned_to=assigned_to,
                project_id=project_id,
                milestone_id=milestone_id,
                include_archived=include_done,
            )

            # Filter out done items if not requested
            if not include_done:
                items = [i for i in items if i.get("status") != ItemStatus.DONE.value]

            if not items:
                filter_desc = []
                if status:
                    filter_desc.append(f"status={status}")
                if priority:
                    filter_desc.append(f"priority={priority}")
                if assigned_to:
                    filter_desc.append(f"assigned to {assigned_to}")
                filter_str = f" ({', '.join(filter_desc)})" if filter_desc else ""
                return {
                    "success": True,
                    "result": f"No roadmap items found{filter_str}."
                }

            type_icons = {
                "feature": "✨",
                "bug": "🐛",
                "enhancement": "⚡",
                "chore": "🔧",
                "research": "🔍",
                "documentation": "📚",
            }

            lines = [f"**Roadmap Items ({len(items)}):**\n"]
            for item in items:
                icon = type_icons.get(item.get("item_type", ""), "📌")
                pri = f"[{item.get('priority', 'P2')}]"
                status_str = item.get("status", "backlog")
                assigned = f" → {item.get('assigned_to')}" if item.get("assigned_to") else ""

                line = f"  {icon} **#{item['id']}** {pri} {item['title']}"
                line += f"\n      {status_str}{assigned}"
                lines.append(line)

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "update_roadmap_item":
            item_id = tool_input["item_id"]

            # Gather update fields
            title = tool_input.get("title")
            description = tool_input.get("description")
            status = tool_input.get("status")
            priority = tool_input.get("priority")
            item_type = tool_input.get("item_type")
            tags = tool_input.get("tags")
            assigned_to = tool_input.get("assigned_to")
            project_id = tool_input.get("project_id")
            milestone_id = tool_input.get("milestone_id")

            item = roadmap_manager.update_item(
                item_id=item_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                item_type=item_type,
                tags=tags,
                assigned_to=assigned_to,
                project_id=project_id,
                milestone_id=milestone_id,
            )

            if not item:
                return {"success": False, "error": f"Item #{item_id} not found"}

            changes = []
            if title:
                changes.append(f"title → '{title}'")
            if status:
                changes.append(f"status → {status}")
            if priority:
                changes.append(f"priority → {priority}")
            if assigned_to:
                changes.append(f"assigned to {assigned_to}")
            if tags:
                changes.append(f"tags: {', '.join(tags)}")

            return {
                "success": True,
                "result": f"Updated **#{item_id}**: {', '.join(changes) if changes else 'updated'}"
            }

        elif tool_name == "get_roadmap_item":
            item_id = tool_input["item_id"]
            item = roadmap_manager.load_item(item_id)

            if not item:
                return {"success": False, "error": f"Item #{item_id} not found"}

            type_icons = {
                "feature": "✨",
                "bug": "🐛",
                "enhancement": "⚡",
                "chore": "🔧",
                "research": "🔍",
                "documentation": "📚",
            }
            icon = type_icons.get(item.item_type, "📌")

            lines = [
                f"**#{item.id}** {icon} {item.title}",
                f"",
                f"**Status:** {item.status} | **Priority:** {item.priority} | **Type:** {item.item_type}",
            ]

            if item.assigned_to:
                lines.append(f"**Assigned to:** {item.assigned_to}")
            if item.tags:
                lines.append(f"**Tags:** {', '.join(item.tags)}")
            if item.description:
                lines.append(f"\n---\n{item.description}")

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "complete_roadmap_item":
            item_id = tool_input["item_id"]
            item = roadmap_manager.complete_item(item_id)

            if not item:
                return {"success": False, "error": f"Item #{item_id} not found"}

            return {
                "success": True,
                "result": f"✓ Completed **#{item.id}**: {item.title}"
            }

        elif tool_name == "advance_roadmap_item":
            item_id = tool_input["item_id"]

            # Get current status for messaging
            before = roadmap_manager.load_item(item_id)
            if not before:
                return {"success": False, "error": f"Item #{item_id} not found"}

            old_status = before.status
            item = roadmap_manager.advance_status(item_id)

            if item.status == old_status:
                return {
                    "success": True,
                    "result": f"Item **#{item_id}** is already at final status: {item.status}"
                }

            return {
                "success": True,
                "result": f"Advanced **#{item.id}**: {old_status} → {item.status}"
            }

        else:
            return {"success": False, "error": f"Unknown roadmap tool: {tool_name}"}

    except KeyError as e:
        return {"success": False, "error": f"Missing required field: {e}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
