"""
Home Automation Authoring - Create HA automations via natural language.

Provides tools for Cass to:
- Draft automations from natural language descriptions
- Preview automation YAML before creation
- Create automations in Home Assistant (with approval)
- List and manage existing automations
"""

import logging
from typing import Dict, Any, List, Optional
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions
# =============================================================================

HOME_AUTOMATION_TOOLS = [
    {
        "name": "draft_automation",
        "description": """Draft a Home Assistant automation from a natural language description.
Returns a preview of the automation YAML that would be created.
Use this to show the user what the automation will do before creating it.

Examples:
- "Turn on porch light when I arrive home"
- "Turn off all lights at midnight"
- "When motion detected in hallway, turn on hallway light for 5 minutes"
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural language description of the desired automation",
                },
                "name": {
                    "type": "string",
                    "description": "Optional friendly name for the automation",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "create_automation",
        "description": """Create a Home Assistant automation that was previously drafted.
Only call this after showing the user the draft and getting their approval.
Requires the automation config from draft_automation.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "automation_config": {
                    "type": "object",
                    "description": "The automation configuration from draft_automation",
                },
            },
            "required": ["automation_config"],
        },
    },
    {
        "name": "list_automations",
        "description": "List existing Home Assistant automations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of automations to return",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "toggle_automation",
        "description": "Enable or disable an existing automation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "automation_id": {
                    "type": "string",
                    "description": "The automation entity ID (e.g., automation.porch_light_on_arrival)",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable",
                },
            },
            "required": ["automation_id", "enabled"],
        },
    },
]


# =============================================================================
# Automation Templates
# =============================================================================

# Common trigger templates
TRIGGER_TEMPLATES = {
    "time": {
        "platform": "time",
        "at": "{time}",  # e.g., "22:00:00"
    },
    "state": {
        "platform": "state",
        "entity_id": "{entity_id}",
        "to": "{to_state}",
    },
    "sun": {
        "platform": "sun",
        "event": "{event}",  # sunrise or sunset
        "offset": "{offset}",  # e.g., "-00:30:00"
    },
    "zone_enter": {
        "platform": "zone",
        "entity_id": "{person_entity}",
        "zone": "zone.home",
        "event": "enter",
    },
    "zone_leave": {
        "platform": "zone",
        "entity_id": "{person_entity}",
        "zone": "zone.home",
        "event": "leave",
    },
}

# Common action templates
ACTION_TEMPLATES = {
    "turn_on": {
        "service": "{domain}.turn_on",
        "target": {"entity_id": "{entity_id}"},
    },
    "turn_off": {
        "service": "{domain}.turn_off",
        "target": {"entity_id": "{entity_id}"},
    },
    "delay": {
        "delay": "{duration}",  # e.g., "00:05:00"
    },
}


# =============================================================================
# Natural Language Parsing Helpers
# =============================================================================

def parse_time_reference(text: str) -> Optional[str]:
    """Extract time from natural language."""
    import re

    # Match patterns like "10pm", "10:30pm", "22:00"
    time_patterns = [
        (r"(\d{1,2}):(\d{2})\s*(am|pm)?", lambda m: _format_time(m)),
        (r"(\d{1,2})\s*(am|pm)", lambda m: _format_time_simple(m)),
        (r"midnight", lambda m: "00:00:00"),
        (r"noon", lambda m: "12:00:00"),
    ]

    text_lower = text.lower()
    for pattern, formatter in time_patterns:
        match = re.search(pattern, text_lower)
        if match:
            return formatter(match)

    return None


def _format_time(match) -> str:
    """Format matched time to HH:MM:SS."""
    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3)

    if period == "pm" and hour < 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}:00"


def _format_time_simple(match) -> str:
    """Format simple time like '10pm' to HH:MM:SS."""
    hour = int(match.group(1))
    period = match.group(2)

    if period == "pm" and hour < 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    return f"{hour:02d}:00:00"


def parse_duration(text: str) -> Optional[str]:
    """Extract duration from natural language."""
    import re

    patterns = [
        (r"(\d+)\s*minutes?", lambda m: f"00:{int(m.group(1)):02d}:00"),
        (r"(\d+)\s*hours?", lambda m: f"{int(m.group(1)):02d}:00:00"),
        (r"(\d+)\s*seconds?", lambda m: f"00:00:{int(m.group(1)):02d}"),
    ]

    text_lower = text.lower()
    for pattern, formatter in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return formatter(match)

    return None


def extract_entities_from_description(description: str, available_entities: List[str]) -> List[str]:
    """Find entity IDs mentioned in description."""
    description_lower = description.lower()
    found = []

    for entity_id in available_entities:
        # Check entity name
        friendly_name = entity_id.split(".")[-1].replace("_", " ")
        if friendly_name in description_lower:
            found.append(entity_id)

    return found


# =============================================================================
# Tool Handlers
# =============================================================================

async def handle_draft_automation(tool_input: Dict[str, Any], **kwargs) -> str:
    """Draft an automation from natural language."""
    from home_assistant import get_ha_client

    description = tool_input.get("description", "")
    name = tool_input.get("name", "")

    if not description:
        return "Error: description is required"

    client = get_ha_client()
    if not client.is_configured:
        return "Home Assistant is not configured."

    # Get available entities for reference
    try:
        states = await client.get_states()
        entity_ids = [s.entity_id for s in states]
    except Exception as e:
        return f"Error getting entities: {e}"

    # Parse the description to build automation config
    description_lower = description.lower()
    automation = {
        "id": str(uuid.uuid4())[:8],
        "alias": name or f"Cass Automation - {description[:50]}",
        "description": f"Created by Cass: {description}",
        "trigger": [],
        "condition": [],
        "action": [],
        "mode": "single",
    }

    # Detect trigger type
    if "when" in description_lower and "motion" in description_lower:
        # Motion trigger
        motion_sensors = [e for e in entity_ids if "motion" in e.lower() and "binary_sensor" in e]
        if motion_sensors:
            automation["trigger"].append({
                "platform": "state",
                "entity_id": motion_sensors[0],
                "to": "on",
            })

    elif any(word in description_lower for word in ["arrive", "get home", "come home"]):
        # Zone enter trigger
        persons = [e for e in entity_ids if e.startswith("person.")]
        if persons:
            automation["trigger"].append({
                "platform": "zone",
                "entity_id": persons[0],
                "zone": "zone.home",
                "event": "enter",
            })

    elif any(word in description_lower for word in ["leave", "left home"]):
        # Zone leave trigger
        persons = [e for e in entity_ids if e.startswith("person.")]
        if persons:
            automation["trigger"].append({
                "platform": "zone",
                "entity_id": persons[0],
                "zone": "zone.home",
                "event": "leave",
            })

    elif "sunset" in description_lower:
        automation["trigger"].append({
            "platform": "sun",
            "event": "sunset",
        })

    elif "sunrise" in description_lower:
        automation["trigger"].append({
            "platform": "sun",
            "event": "sunrise",
        })

    else:
        # Check for time trigger
        time_ref = parse_time_reference(description)
        if time_ref:
            automation["trigger"].append({
                "platform": "time",
                "at": time_ref,
            })

    # Detect action
    if "turn on" in description_lower:
        # Find what to turn on
        lights = [e for e in entity_ids if "light" in e.lower()]
        switches = [e for e in entity_ids if "switch" in e.lower()]

        # Try to match entity name
        for entity_id in lights + switches:
            friendly = entity_id.split(".")[-1].replace("_", " ")
            if friendly in description_lower:
                domain = entity_id.split(".")[0]
                automation["action"].append({
                    "service": f"{domain}.turn_on",
                    "target": {"entity_id": entity_id},
                })
                break
        else:
            # If "all lights" mentioned
            if "all light" in description_lower:
                automation["action"].append({
                    "service": "light.turn_on",
                    "target": {"entity_id": "all"},
                })

    elif "turn off" in description_lower:
        lights = [e for e in entity_ids if "light" in e.lower()]
        switches = [e for e in entity_ids if "switch" in e.lower()]

        for entity_id in lights + switches:
            friendly = entity_id.split(".")[-1].replace("_", " ")
            if friendly in description_lower:
                domain = entity_id.split(".")[0]
                automation["action"].append({
                    "service": f"{domain}.turn_off",
                    "target": {"entity_id": entity_id},
                })
                break
        else:
            if "all light" in description_lower:
                automation["action"].append({
                    "service": "light.turn_off",
                    "target": {"entity_id": "all"},
                })

    # Check for duration/delay (e.g., "for 5 minutes")
    if " for " in description_lower:
        duration = parse_duration(description)
        if duration and automation["action"]:
            # Add delay then turn off
            automation["action"].append({"delay": duration})
            # Reverse the last action
            last_action = automation["action"][0]
            if "turn_on" in str(last_action):
                entity = last_action.get("target", {}).get("entity_id")
                domain = entity.split(".")[0] if entity and "." in entity else "light"
                automation["action"].append({
                    "service": f"{domain}.turn_off",
                    "target": last_action.get("target"),
                })

    # Validate automation has required parts
    if not automation["trigger"]:
        return f"""Could not determine trigger from description.

Please specify when the automation should run, such as:
- "at 10pm"
- "when I arrive home"
- "when motion is detected in [area]"
- "at sunset"

Description provided: {description}"""

    if not automation["action"]:
        return f"""Could not determine action from description.

Please specify what should happen, such as:
- "turn on the [light name]"
- "turn off all lights"

Description provided: {description}"""

    # Format as YAML-like preview
    import yaml
    yaml_preview = yaml.dump(automation, default_flow_style=False, sort_keys=False)

    return f"""**Automation Draft**

{yaml_preview}

If this looks correct, I can create it for you. Would you like me to proceed?"""


async def handle_create_automation(tool_input: Dict[str, Any], **kwargs) -> str:
    """Create an automation in Home Assistant."""
    from home_assistant import get_ha_client

    automation_config = tool_input.get("automation_config", {})

    if not automation_config:
        return "Error: automation_config is required"

    client = get_ha_client()
    if not client.is_configured:
        return "Home Assistant is not configured."

    # Create via HA API
    try:
        http_client = await client._get_client()
        response = await http_client.post(
            "/api/config/automation/config",
            json=automation_config,
        )
        response.raise_for_status()

        # Reload automations
        await client.call_service("automation", "reload")

        return f"Automation '{automation_config.get('alias', 'New automation')}' created successfully!"

    except Exception as e:
        logger.error(f"Failed to create automation: {e}")
        return f"Failed to create automation: {e}"


async def handle_list_automations(tool_input: Dict[str, Any], **kwargs) -> str:
    """List existing automations."""
    from home_assistant import get_ha_client

    limit = tool_input.get("limit", 20)

    client = get_ha_client()
    if not client.is_configured:
        return "Home Assistant is not configured."

    try:
        states = await client.get_states()
        automations = [s for s in states if s.entity_id.startswith("automation.")]

        if not automations:
            return "No automations found."

        lines = [f"**{len(automations)} Automations**\n"]
        for auto in automations[:limit]:
            state = "✓" if auto.state == "on" else "✗"
            name = auto.friendly_name or auto.entity_id
            lines.append(f"- [{state}] {name} (`{auto.entity_id}`)")

        if len(automations) > limit:
            lines.append(f"\n...and {len(automations) - limit} more")

        return "\n".join(lines)

    except Exception as e:
        return f"Error listing automations: {e}"


async def handle_toggle_automation(tool_input: Dict[str, Any], **kwargs) -> str:
    """Enable or disable an automation."""
    from home_assistant import get_ha_client

    automation_id = tool_input.get("automation_id", "")
    enabled = tool_input.get("enabled", True)

    if not automation_id:
        return "Error: automation_id is required"

    client = get_ha_client()
    if not client.is_configured:
        return "Home Assistant is not configured."

    try:
        service = "turn_on" if enabled else "turn_off"
        result = await client.call_service("automation", service, automation_id)

        if result.get("success"):
            action = "enabled" if enabled else "disabled"
            return f"Automation {action} successfully."
        else:
            return f"Failed to toggle automation: {result.get('error', 'Unknown error')}"

    except Exception as e:
        return f"Error toggling automation: {e}"


# =============================================================================
# Tool Executor
# =============================================================================

HOME_AUTOMATION_HANDLERS = {
    "draft_automation": handle_draft_automation,
    "create_automation": handle_create_automation,
    "list_automations": handle_list_automations,
    "toggle_automation": handle_toggle_automation,
}


async def execute_home_automation_tool(tool_name: str, tool_input: Dict[str, Any], **kwargs) -> str:
    """Execute a home automation tool."""
    handler = HOME_AUTOMATION_HANDLERS.get(tool_name)
    if not handler:
        return f"Unknown home automation tool: {tool_name}"

    try:
        return await handler(tool_input, **kwargs)
    except Exception as e:
        logger.error(f"Home automation tool {tool_name} failed: {e}")
        return f"Error executing {tool_name}: {e}"
