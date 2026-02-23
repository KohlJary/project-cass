"""
Stakeholder tool handler - enables linking PeopleDex entities to goals.

These tools allow Cass to:
- Link stakeholders to goals with roles and notes
- Query stakeholders associated with a goal
- Build context about key people for goal execution
"""
from typing import Dict, Optional

from unified_goals import UnifiedGoalManager, StakeholderRole
from peopledex import PeopleDexManager, get_peopledex_manager, EntityType


async def execute_stakeholder_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
    goal_manager: Optional[UnifiedGoalManager] = None,
    conversation_id: Optional[str] = None,
) -> Dict:
    """
    Execute a stakeholder tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID
        goal_manager: UnifiedGoalManager instance (created if not provided)
        conversation_id: Current conversation ID (for source tracking)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        # Initialize managers if not provided
        if goal_manager is None:
            goal_manager = UnifiedGoalManager(daemon_id)
        peopledex = get_peopledex_manager(daemon_id)

        if tool_name == "link_stakeholder":
            return await _link_stakeholder(
                goal_manager, peopledex, tool_input, conversation_id
            )

        elif tool_name == "get_goal_stakeholders":
            return await _get_goal_stakeholders(
                goal_manager, tool_input
            )

        else:
            return {
                "success": False,
                "error": f"Unknown stakeholder tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Stakeholder tool error: {str(e)}"
        }


async def _link_stakeholder(
    goal_manager: UnifiedGoalManager,
    peopledex: PeopleDexManager,
    tool_input: Dict,
    conversation_id: Optional[str] = None,
) -> Dict:
    """Link a person to a goal as a stakeholder."""
    goal_id = tool_input.get("goal_id")
    person_name = tool_input.get("person_name")
    role = tool_input.get("role", "contact")
    notes = tool_input.get("notes")

    if not goal_id:
        return {
            "success": False,
            "error": "goal_id is required"
        }

    if not person_name:
        return {
            "success": False,
            "error": "person_name is required"
        }

    # Verify the goal exists
    goal = goal_manager.get_goal(goal_id)
    if not goal:
        return {
            "success": False,
            "error": f"Goal not found: {goal_id}"
        }

    # Find or create the person in PeopleDex
    # Search for existing entity first
    results = peopledex.search_entities(person_name, EntityType.PERSON, limit=1)

    if results:
        entity = results[0]
        entity_id = entity.id
        entity_name = entity.primary_name
    else:
        # Create new entity
        entity_id = peopledex.create_entity(
            primary_name=person_name,
            entity_type=EntityType.PERSON,
            source_type="goal_research",
            source_id=goal_id,
            confidence=0.7,  # Lower confidence for auto-created
        )
        entity_name = person_name

    if not entity_id:
        return {
            "success": False,
            "error": f"Could not find or create person: {person_name}"
        }

    # Validate role
    valid_roles = [r.value for r in StakeholderRole]
    if role not in valid_roles:
        role = StakeholderRole.CONTACT.value

    # Link stakeholder to goal
    success = goal_manager.link_stakeholder(
        goal_id=goal_id,
        entity_id=entity_id,
        role=role,
        notes=notes,
        added_by="cass",
        confidence=0.8,
    )

    if success:
        return {
            "success": True,
            "result": f"Linked {entity_name} to goal as {role.replace('_', ' ')}"
        }
    else:
        return {
            "success": False,
            "error": "Failed to link stakeholder to goal"
        }


async def _get_goal_stakeholders(
    goal_manager: UnifiedGoalManager,
    tool_input: Dict,
) -> Dict:
    """Get all stakeholders linked to a goal."""
    goal_id = tool_input.get("goal_id")

    if not goal_id:
        return {
            "success": False,
            "error": "goal_id is required"
        }

    # Verify the goal exists
    goal = goal_manager.get_goal(goal_id)
    if not goal:
        return {
            "success": False,
            "error": f"Goal not found: {goal_id}"
        }

    # Get stakeholders (includes contact info from PeopleDex)
    stakeholders = goal_manager.get_stakeholders(goal_id)

    if not stakeholders:
        return {
            "success": True,
            "result": f"No stakeholders linked to goal: {goal.title}"
        }

    # Format output
    lines = [f"## Stakeholders for: {goal.title}\n"]

    for sh in stakeholders:
        role_label = sh["role"].replace("_", " ").title()
        lines.append(f"### {sh['name']} ({role_label})")

        if sh.get("title"):
            lines.append(f"- **Title:** {sh['title']}")
        if sh.get("email"):
            lines.append(f"- **Email:** {sh['email']}")
        if sh.get("phone"):
            lines.append(f"- **Phone:** {sh['phone']}")
        if sh.get("notes"):
            lines.append(f"- **Notes:** {sh['notes']}")

        confidence = sh.get("confidence", 0.8)
        if confidence < 0.7:
            lines.append(f"- _Confidence: {confidence:.0%} (needs verification)_")

        lines.append("")

    return {
        "success": True,
        "result": "\n".join(lines),
        "stakeholders": stakeholders,  # Structured data for programmatic use
    }


# Tool definitions for agent_client.py
STAKEHOLDER_TOOLS = [
    {
        "name": "link_stakeholder",
        "description": "Associate a person with a goal as a stakeholder. Use this when you identify someone relevant to a goal during research. The person will be added to PeopleDex if not already present.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {
                    "type": "string",
                    "description": "ID of the goal to link the stakeholder to"
                },
                "person_name": {
                    "type": "string",
                    "description": "Name of the person (will lookup/create in PeopleDex)"
                },
                "role": {
                    "type": "string",
                    "enum": ["decision_maker", "subject_expert", "gatekeeper", "contact", "influencer", "unknown"],
                    "description": "Their role relative to this goal. decision_maker=authority to approve/reject, subject_expert=domain expertise, gatekeeper=controls access, contact=general point of contact, influencer=can influence outcomes"
                },
                "notes": {
                    "type": "string",
                    "description": "Why this person is relevant to the goal"
                }
            },
            "required": ["goal_id", "person_name", "role"]
        }
    },
    {
        "name": "get_goal_stakeholders",
        "description": "Get all stakeholders linked to a goal, including their contact information from PeopleDex. Use this to understand who the key people are for a goal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {
                    "type": "string",
                    "description": "ID of the goal to get stakeholders for"
                }
            },
            "required": ["goal_id"]
        }
    }
]
