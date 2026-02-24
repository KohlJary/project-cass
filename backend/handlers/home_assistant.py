"""
Home Assistant tool handlers for Cass.

Provides tools for querying and controlling Home Assistant devices.
"""

import logging
from typing import Dict, Any, List

from home_assistant import get_ha_client, HAEntity

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions
# =============================================================================

HOME_ASSISTANT_TOOLS = [
    {
        "name": "get_home_state",
        "description": "Get a summary of the current home state including lights, climate, locks, and sensors. Use this to understand what's happening in the home.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_device_state",
        "description": "Get the current state of a specific smart home device. Returns the device's state, attributes, and friendly name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The Home Assistant entity ID (e.g., 'light.living_room', 'switch.kitchen', 'climate.thermostat')",
                },
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "list_devices",
        "description": "List available smart home devices. Can filter by domain (light, switch, climate, etc.) or area (living_room, bedroom, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Filter by device type: light, switch, climate, lock, cover, media_player, fan, vacuum, sensor, binary_sensor",
                },
                "area": {
                    "type": "string",
                    "description": "Filter by area/room name or ID",
                },
            },
            "required": [],
        },
    },
    {
        "name": "control_device",
        "description": "Control a smart home device. Can turn devices on/off, toggle them, or set specific attributes like brightness or temperature.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "The Home Assistant entity ID to control (e.g., 'light.living_room')",
                },
                "action": {
                    "type": "string",
                    "enum": ["turn_on", "turn_off", "toggle"],
                    "description": "The action to perform",
                },
                "attributes": {
                    "type": "object",
                    "description": "Optional attributes for the action (e.g., {'brightness': 128} for lights, {'temperature': 72} for climate)",
                },
            },
            "required": ["entity_id", "action"],
        },
    },
    {
        "name": "list_areas",
        "description": "List all areas/rooms defined in Home Assistant.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


# =============================================================================
# Tool Handlers
# =============================================================================

async def handle_get_home_state(tool_input: Dict[str, Any], **kwargs) -> str:
    """Get summary of home state."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured. Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN environment variables."

    summary = await client.get_home_summary()
    return summary


async def handle_get_device_state(tool_input: Dict[str, Any], **kwargs) -> str:
    """Get state of a specific device."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    entity_id = tool_input.get("entity_id", "")
    if not entity_id:
        return "Error: entity_id is required"

    entity = await client.get_state(entity_id)
    if not entity:
        return f"Entity '{entity_id}' not found."

    # Format response
    lines = [
        f"**{entity.friendly_name or entity.entity_id}**",
        f"- State: {entity.state}",
        f"- Entity ID: {entity.entity_id}",
    ]

    # Add relevant attributes based on domain
    if entity.domain == "light":
        if "brightness" in entity.attributes:
            brightness_pct = round(entity.attributes["brightness"] / 255 * 100)
            lines.append(f"- Brightness: {brightness_pct}%")
        if "color_temp" in entity.attributes:
            lines.append(f"- Color temp: {entity.attributes['color_temp']}")
        if "rgb_color" in entity.attributes:
            lines.append(f"- RGB: {entity.attributes['rgb_color']}")

    elif entity.domain == "climate":
        if "current_temperature" in entity.attributes:
            lines.append(f"- Current temp: {entity.attributes['current_temperature']}°")
        if "temperature" in entity.attributes:
            lines.append(f"- Target temp: {entity.attributes['temperature']}°")
        if "hvac_action" in entity.attributes:
            lines.append(f"- HVAC action: {entity.attributes['hvac_action']}")

    elif entity.domain == "cover":
        if "current_position" in entity.attributes:
            lines.append(f"- Position: {entity.attributes['current_position']}%")

    elif entity.domain == "media_player":
        if "media_title" in entity.attributes:
            lines.append(f"- Playing: {entity.attributes['media_title']}")
        if "volume_level" in entity.attributes:
            lines.append(f"- Volume: {round(entity.attributes['volume_level'] * 100)}%")

    if entity.area_id:
        lines.append(f"- Area: {entity.area_id}")

    return "\n".join(lines)


async def handle_list_devices(tool_input: Dict[str, Any], **kwargs) -> str:
    """List available devices."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    domain = tool_input.get("domain")
    area = tool_input.get("area")

    if domain:
        entities = await client.get_entities_by_domain(domain)
    elif area:
        entities = await client.get_entities_by_area(area)
    else:
        entities = await client.get_states()

    if not entities:
        filters = []
        if domain:
            filters.append(f"domain={domain}")
        if area:
            filters.append(f"area={area}")
        filter_str = f" (filters: {', '.join(filters)})" if filters else ""
        return f"No devices found{filter_str}."

    # Group by domain if no domain filter
    if not domain:
        by_domain: Dict[str, List[HAEntity]] = {}
        for e in entities:
            if e.domain:
                by_domain.setdefault(e.domain, []).append(e)

        lines = [f"**{len(entities)} devices found**\n"]
        for d, ents in sorted(by_domain.items()):
            if len(ents) <= 10:
                lines.append(f"**{d}** ({len(ents)}):")
                for e in ents:
                    lines.append(f"  - {e.friendly_name or e.entity_id} ({e.state})")
            else:
                lines.append(f"**{d}** ({len(ents)}): {', '.join(e.friendly_name or e.entity_id for e in ents[:5])}...")
        return "\n".join(lines)

    # Single domain - list all
    lines = [f"**{domain} devices** ({len(entities)})\n"]
    for e in entities[:30]:
        lines.append(f"- {e.friendly_name or e.entity_id}: {e.state} (`{e.entity_id}`)")
    if len(entities) > 30:
        lines.append(f"...and {len(entities) - 30} more")

    return "\n".join(lines)


async def handle_control_device(tool_input: Dict[str, Any], **kwargs) -> str:
    """Control a device."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    entity_id = tool_input.get("entity_id", "")
    action = tool_input.get("action", "")
    attributes = tool_input.get("attributes", {})

    if not entity_id:
        return "Error: entity_id is required"
    if not action:
        return "Error: action is required (turn_on, turn_off, or toggle)"

    # Validate entity exists
    entity = await client.get_state(entity_id)
    if not entity:
        return f"Entity '{entity_id}' not found."

    # Get domain from entity_id
    domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"

    # Call the service
    if action == "turn_on":
        result = await client.call_service(domain, "turn_on", entity_id, attributes or None)
    elif action == "turn_off":
        result = await client.call_service(domain, "turn_off", entity_id)
    elif action == "toggle":
        result = await client.call_service(domain, "toggle", entity_id)
    else:
        return f"Unknown action: {action}. Use turn_on, turn_off, or toggle."

    if result.get("success"):
        # Get new state
        new_entity = await client.get_state(entity_id)
        new_state = new_entity.state if new_entity else "unknown"
        return f"Successfully executed {action} on {entity.friendly_name or entity_id}. New state: {new_state}"
    else:
        return f"Failed to {action} {entity_id}: {result.get('error', 'Unknown error')}"


async def handle_list_areas(tool_input: Dict[str, Any], **kwargs) -> str:
    """List all areas."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    areas = await client.get_areas()

    if not areas:
        return "No areas found in Home Assistant."

    lines = [f"**{len(areas)} areas defined**\n"]
    for area in areas:
        lines.append(f"- {area['name']} (`{area['area_id']}`)")

    return "\n".join(lines)


# =============================================================================
# Tool Executor
# =============================================================================

HA_TOOL_HANDLERS = {
    "get_home_state": handle_get_home_state,
    "get_device_state": handle_get_device_state,
    "list_devices": handle_list_devices,
    "control_device": handle_control_device,
    "list_areas": handle_list_areas,
}


async def execute_ha_tool(tool_name: str, tool_input: Dict[str, Any], **kwargs) -> str:
    """Execute a Home Assistant tool."""
    handler = HA_TOOL_HANDLERS.get(tool_name)
    if not handler:
        return f"Unknown Home Assistant tool: {tool_name}"

    try:
        return await handler(tool_input, **kwargs)
    except Exception as e:
        logger.error(f"HA tool {tool_name} failed: {e}")
        return f"Error executing {tool_name}: {e}"
