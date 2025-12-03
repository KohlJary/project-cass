"""
Task tool handler - Taskwarrior-style task management
"""
from datetime import datetime
from typing import Dict
from task_manager import TaskManager, Priority, TaskStatus


async def execute_task_tool(
    tool_name: str,
    tool_input: Dict,
    user_id: str,
    task_manager: TaskManager
) -> Dict:
    """
    Handle task-related tool calls (Taskwarrior-style).

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool
        user_id: Current user's ID
        task_manager: TaskManager instance

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        if tool_name == "add_task":
            description = tool_input["description"]
            priority_str = tool_input.get("priority", "")
            priority = Priority(priority_str) if priority_str else Priority.NONE
            tags = tool_input.get("tags", [])
            project = tool_input.get("project")
            due_str = tool_input.get("due")
            due = datetime.fromisoformat(due_str) if due_str else None

            task = task_manager.add(
                user_id=user_id,
                description=description,
                priority=priority,
                tags=tags,
                project=project,
                due=due
            )

            # Format response
            parts = [f"✓ Added task: **{task.description}**"]
            if priority != Priority.NONE:
                parts.append(f"priority:{priority.value}")
            if tags:
                parts.append(" ".join(f"+{t}" for t in tags))
            if project:
                parts.append(f"project:{project}")

            return {"success": True, "result": " ".join(parts), "task_id": task.id}

        elif tool_name == "list_tasks":
            filter_str = tool_input.get("filter", "")
            include_completed = tool_input.get("include_completed", False)

            tasks = task_manager.list_tasks(
                user_id=user_id,
                filter_str=filter_str if filter_str else None,
                include_completed=include_completed
            )

            if not tasks:
                return {
                    "success": True,
                    "result": "No tasks found." + (f" (filter: {filter_str})" if filter_str else "")
                }

            lines = [f"**Tasks ({len(tasks)}):**\n"]
            for task in tasks:
                # Format like taskwarrior
                pri = f"[{task.priority.value}]" if task.priority != Priority.NONE else "   "
                tags_str = " ".join(f"+{t}" for t in task.tags) if task.tags else ""
                proj_str = f"project:{task.project}" if task.project else ""
                status = "✓ " if task.status == TaskStatus.COMPLETED else ""

                line = f"{status}{pri} {task.description}"
                if tags_str or proj_str:
                    line += f"\n    {tags_str} {proj_str}".rstrip()
                line += f"\n    (urgency: {task.urgency}, id: {task.id[:8]})"
                lines.append(line)

            return {"success": True, "result": "\n".join(lines)}

        elif tool_name == "complete_task":
            task_id = tool_input.get("task_id")
            search = tool_input.get("search")

            if not task_id and not search:
                return {"success": False, "error": "Must provide either task_id or search term"}

            # Find by search if no ID
            if not task_id and search:
                matches = task_manager.get_by_description(user_id, search)
                if not matches:
                    return {"success": False, "error": f"No task found matching '{search}'"}
                task_id = matches[0].id

            task = task_manager.complete(user_id, task_id)
            if task:
                return {
                    "success": True,
                    "result": f"✓ Completed: **{task.description}**"
                }
            else:
                return {"success": False, "error": "Task not found"}

        elif tool_name == "modify_task":
            task_id = tool_input.get("task_id")
            search = tool_input.get("search")

            if not task_id and not search:
                return {"success": False, "error": "Must provide either task_id or search term"}

            # Find by search if no ID
            if not task_id and search:
                matches = task_manager.get_by_description(user_id, search)
                if not matches:
                    return {"success": False, "error": f"No task found matching '{search}'"}
                task_id = matches[0].id

            # Parse modifications
            priority_str = tool_input.get("priority")
            priority = Priority(priority_str) if priority_str else None
            add_tags = tool_input.get("add_tags", [])
            remove_tags = tool_input.get("remove_tags", [])
            project = tool_input.get("project")
            due_str = tool_input.get("due")
            due = datetime.fromisoformat(due_str) if due_str else None

            task = task_manager.modify(
                user_id=user_id,
                task_id=task_id,
                priority=priority,
                add_tags=add_tags if add_tags else None,
                remove_tags=remove_tags if remove_tags else None,
                project=project,
                due=due
            )

            if task:
                changes = []
                if priority_str:
                    changes.append(f"priority → {priority_str}")
                if add_tags:
                    changes.append(f"added {', '.join('+' + t for t in add_tags)}")
                if remove_tags:
                    changes.append(f"removed {', '.join('-' + t for t in remove_tags)}")
                if project:
                    changes.append(f"project → {project}")
                if due:
                    changes.append(f"due → {due.strftime('%Y-%m-%d')}")

                return {
                    "success": True,
                    "result": f"✓ Modified **{task.description}**: {', '.join(changes) if changes else 'updated'}"
                }
            else:
                return {"success": False, "error": "Task not found"}

        elif tool_name == "delete_task":
            task_id = tool_input.get("task_id")
            search = tool_input.get("search")

            if not task_id and not search:
                return {"success": False, "error": "Must provide either task_id or search term"}

            # Find by search if no ID
            if not task_id and search:
                matches = task_manager.get_by_description(user_id, search)
                if not matches:
                    return {"success": False, "error": f"No task found matching '{search}'"}
                task_id = matches[0].id
                description = matches[0].description
            else:
                task = task_manager.get(user_id, task_id)
                description = task.description if task else "Unknown"

            if task_manager.delete(user_id, task_id):
                return {
                    "success": True,
                    "result": f"✓ Deleted: **{description}**"
                }
            else:
                return {"success": False, "error": "Task not found"}

        else:
            return {"success": False, "error": f"Unknown task tool: {tool_name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
