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
    # Shopping List / To-Do List tools
    {
        "name": "get_shopping_list",
        "description": "Get the current shopping/to-do list from Home Assistant. Shows all items with their completion status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "show_completed": {
                    "type": "boolean",
                    "description": "Whether to include completed items (default: True)",
                    "default": True,
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_shopping_item",
        "description": "Add an item to the shopping/to-do list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The item to add to the list",
                },
            },
            "required": ["item"],
        },
    },
    {
        "name": "complete_shopping_item",
        "description": "Mark a shopping/to-do list item as complete.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The item name to mark as complete (case-insensitive partial match supported)",
                },
            },
            "required": ["item"],
        },
    },
    {
        "name": "remove_shopping_item",
        "description": "Remove an item from the shopping/to-do list entirely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The item name to remove (case-insensitive partial match supported)",
                },
            },
            "required": ["item"],
        },
    },
    {
        "name": "clear_completed_items",
        "description": "Remove all completed items from the shopping/to-do list.",
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
# Shopping List / To-Do Handlers
# =============================================================================

async def handle_get_shopping_list(tool_input: Dict[str, Any], **kwargs) -> str:
    """Get the shopping/to-do list."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    show_completed = tool_input.get("show_completed", True)

    try:
        http_client = await client._get_client()
        response = await http_client.get("/api/shopping_list")
        response.raise_for_status()
        items = response.json()

        if not items:
            return "The shopping list is empty."

        # Separate into incomplete and complete
        incomplete = [i for i in items if not i.get("complete")]
        complete = [i for i in items if i.get("complete")]

        lines = []

        if incomplete:
            lines.append(f"**To Do ({len(incomplete)} items)**")
            for item in incomplete:
                lines.append(f"- [ ] {item['name']}")

        if show_completed and complete:
            if lines:
                lines.append("")
            lines.append(f"**Completed ({len(complete)} items)**")
            for item in complete:
                lines.append(f"- [x] {item['name']}")

        if not incomplete and not (show_completed and complete):
            return "No incomplete items on the list."

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Failed to get shopping list: {e}")
        return f"Failed to get shopping list: {e}"


async def handle_add_shopping_item(tool_input: Dict[str, Any], **kwargs) -> str:
    """Add an item to the shopping list."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    item = tool_input.get("item", "").strip()
    if not item:
        return "Error: item is required"

    try:
        result = await client.call_service(
            "shopping_list", "add_item",
            data={"name": item}
        )

        if result.get("success"):
            return f"Added '{item}' to the list."
        else:
            return f"Failed to add item: {result.get('error', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Failed to add shopping item: {e}")
        return f"Failed to add item: {e}"


async def _find_shopping_item(client, search: str) -> Dict[str, Any] | None:
    """Find a shopping list item by name (case-insensitive partial match)."""
    try:
        http_client = await client._get_client()
        response = await http_client.get("/api/shopping_list")
        response.raise_for_status()
        items = response.json()

        search_lower = search.lower()

        # Try exact match first
        for item in items:
            if item["name"].lower() == search_lower:
                return item

        # Then try partial match
        for item in items:
            if search_lower in item["name"].lower():
                return item

        return None

    except Exception:
        return None


async def handle_complete_shopping_item(tool_input: Dict[str, Any], **kwargs) -> str:
    """Mark a shopping list item as complete."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    search = tool_input.get("item", "").strip()
    if not search:
        return "Error: item is required"

    item = await _find_shopping_item(client, search)
    if not item:
        return f"Could not find '{search}' on the list."

    if item.get("complete"):
        return f"'{item['name']}' is already complete."

    try:
        result = await client.call_service(
            "shopping_list", "complete_item",
            data={"name": item["name"]}
        )

        if result.get("success"):
            return f"Marked '{item['name']}' as complete."
        else:
            return f"Failed to complete item: {result.get('error', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Failed to complete shopping item: {e}")
        return f"Failed to complete item: {e}"


async def handle_remove_shopping_item(tool_input: Dict[str, Any], **kwargs) -> str:
    """Remove an item from the shopping list."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    search = tool_input.get("item", "").strip()
    if not search:
        return "Error: item is required"

    item = await _find_shopping_item(client, search)
    if not item:
        return f"Could not find '{search}' on the list."

    try:
        # HA shopping list doesn't have a direct remove service,
        # but we can use the REST API
        http_client = await client._get_client()
        response = await http_client.post(
            "/api/shopping_list/item/" + item["id"],
            json=None  # DELETE would be more RESTful but HA uses POST with empty body
        )

        # Actually HA uses a different approach - complete then clear
        # Let's just mark it complete if not already, then use clear_completed_items
        # Or we can use the websocket API...

        # Simpler approach: use the intent API or just mark complete
        if not item.get("complete"):
            await client.call_service(
                "shopping_list", "complete_item",
                data={"name": item["name"]}
            )

        # Now clear completed items (this removes ALL completed, which may not be ideal)
        # Actually let's check if there's a remove endpoint
        # The REST API has DELETE /api/shopping_list/item/{item_id}
        response = await http_client.request(
            "DELETE",
            f"/api/shopping_list/item/{item['id']}"
        )

        if response.status_code in (200, 204):
            return f"Removed '{item['name']}' from the list."
        else:
            return f"Failed to remove item (status {response.status_code})"

    except Exception as e:
        logger.error(f"Failed to remove shopping item: {e}")
        return f"Failed to remove item: {e}"


async def handle_clear_completed_items(tool_input: Dict[str, Any], **kwargs) -> str:
    """Clear all completed items from the shopping list."""
    client = get_ha_client()

    if not client.is_configured:
        return "Home Assistant is not configured."

    try:
        result = await client.call_service(
            "shopping_list", "clear_completed_items"
        )

        if result.get("success"):
            return "Cleared all completed items from the list."
        else:
            return f"Failed to clear completed items: {result.get('error', 'Unknown error')}"

    except Exception as e:
        logger.error(f"Failed to clear completed items: {e}")
        return f"Failed to clear completed items: {e}"


# =============================================================================
# Tool Executor
# =============================================================================

HA_TOOL_HANDLERS = {
    "get_home_state": handle_get_home_state,
    "get_device_state": handle_get_device_state,
    "list_devices": handle_list_devices,
    "control_device": handle_control_device,
    "list_areas": handle_list_areas,
    # Shopping list / to-do handlers
    "get_shopping_list": handle_get_shopping_list,
    "add_shopping_item": handle_add_shopping_item,
    "complete_shopping_item": handle_complete_shopping_item,
    "remove_shopping_item": handle_remove_shopping_item,
    "clear_completed_items": handle_clear_completed_items,
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
