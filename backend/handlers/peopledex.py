"""
PeopleDex tool handler - enables Cass to look up and store biographical information.

These tools allow Cass to:
- Look up biographical info about people, organizations, or entities
- Store new biographical info learned during conversations
- Record relationships between entities
"""
from typing import Dict, Optional

from peopledex import (
    PeopleDexManager,
    get_peopledex_manager,
    EntityType,
    AttributeType,
    RelationshipType,
)


async def execute_peopledex_tool(
    tool_name: str,
    tool_input: Dict,
    daemon_id: str,
    conversation_id: Optional[str] = None,
) -> Dict:
    """
    Execute a PeopleDex tool.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        daemon_id: The daemon ID for state bus events
        conversation_id: Current conversation ID (for source tracking)

    Returns:
        Dict with 'success', 'result', and optionally 'error'
    """
    try:
        manager = get_peopledex_manager(daemon_id)

        if tool_name == "lookup_person":
            return await _lookup_person(manager, tool_input)

        elif tool_name == "remember_person":
            return await _remember_person(
                manager, tool_input, conversation_id
            )

        elif tool_name == "remember_relationship":
            return await _remember_relationship(
                manager, tool_input, conversation_id
            )

        else:
            return {
                "success": False,
                "error": f"Unknown PeopleDex tool: {tool_name}"
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"PeopleDex tool error: {str(e)}"
        }


async def _lookup_person(
    manager: PeopleDexManager,
    tool_input: Dict,
) -> Dict:
    """Look up biographical information about a person or entity."""
    name = tool_input.get("name")
    if not name:
        return {
            "success": False,
            "error": "Name is required for lookup"
        }

    entity_type = tool_input.get("entity_type")
    if entity_type:
        try:
            entity_type = EntityType(entity_type)
        except ValueError:
            pass  # Let it be None

    # Search for the entity
    results = manager.search_entities(name, entity_type, limit=5)

    if not results:
        return {
            "success": True,
            "result": f"No one named '{name}' found in my records."
        }

    # Get full profile for top match
    best_match = results[0]
    profile = manager.get_full_profile(best_match.id)

    if not profile:
        return {
            "success": True,
            "result": f"Found '{name}' but couldn't load full profile."
        }

    # Format the response
    lines = [f"## {profile.entity.primary_name}"]
    lines.append(f"**Type**: {profile.entity.entity_type.value}")

    # Group attributes by type
    attrs_by_type: Dict[str, list] = {}
    for attr in profile.attributes:
        type_name = attr.attribute_type.value
        if type_name not in attrs_by_type:
            attrs_by_type[type_name] = []
        attrs_by_type[type_name].append(attr)

    # Names (skip primary, already shown)
    names = attrs_by_type.get("name", [])
    other_names = [n for n in names if not n.is_primary]
    if other_names:
        lines.append(f"**Also known as**: {', '.join(n.value for n in other_names)}")

    # Pronouns
    pronouns = attrs_by_type.get("pronoun", [])
    if pronouns:
        lines.append(f"**Pronouns**: {pronouns[0].value}")

    # Birthday
    birthdays = attrs_by_type.get("birthday", [])
    if birthdays:
        lines.append(f"**Birthday**: {birthdays[0].value}")

    # Role
    roles = attrs_by_type.get("role", [])
    if roles:
        lines.append(f"**Role**: {roles[0].value}")

    # Location
    locations = attrs_by_type.get("location", [])
    if locations:
        lines.append(f"**Location**: {locations[0].value}")

    # Contact info
    emails = attrs_by_type.get("email", [])
    for email in emails:
        key_str = f" ({email.attribute_key})" if email.attribute_key else ""
        lines.append(f"**Email{key_str}**: {email.value}")

    phones = attrs_by_type.get("phone", [])
    for phone in phones:
        key_str = f" ({phone.attribute_key})" if phone.attribute_key else ""
        lines.append(f"**Phone{key_str}**: {phone.value}")

    handles = attrs_by_type.get("handle", [])
    for handle in handles:
        platform = handle.attribute_key or "unknown"
        lines.append(f"**{platform.title()}**: {handle.value}")

    # Bio
    bios = attrs_by_type.get("bio", [])
    if bios:
        lines.append(f"\n**Bio**: {bios[0].value}")

    # Notes
    notes = attrs_by_type.get("note", [])
    if notes:
        lines.append("\n**Notes**:")
        for note in notes:
            lines.append(f"- {note.value}")

    # Relationships
    if profile.relationships:
        lines.append("\n**Relationships**:")
        for rel in profile.relationships:
            rel_type = rel["relationship_type"]
            label = rel.get("relationship_label")
            other_name = rel["entity"].primary_name
            if label:
                lines.append(f"- {rel_type}: {other_name} ({label})")
            else:
                lines.append(f"- {rel_type}: {other_name}")

    # Also mention other matches if there were any
    if len(results) > 1:
        lines.append(f"\n*(Also found {len(results) - 1} other matching entries)*")

    return {
        "success": True,
        "result": "\n".join(lines)
    }


async def _remember_person(
    manager: PeopleDexManager,
    tool_input: Dict,
    conversation_id: Optional[str],
) -> Dict:
    """Store biographical information about a person or entity."""
    name = tool_input.get("name")
    if not name:
        return {
            "success": False,
            "error": "Name is required"
        }

    entity_type_str = tool_input.get("entity_type", "person")
    try:
        entity_type = EntityType(entity_type_str)
    except ValueError:
        entity_type = EntityType.PERSON

    attributes = tool_input.get("attributes", [])

    # Find or create the entity
    entity = manager.find_or_create_by_name(
        name=name,
        entity_type=entity_type,
        source_type="cass_inferred",
        source_id=conversation_id,
    )

    # Add attributes
    added_attrs = []
    for attr_data in attributes:
        attr_type_str = attr_data.get("type")
        value = attr_data.get("value")
        key = attr_data.get("key")

        if not attr_type_str or not value:
            continue

        try:
            attr_type = AttributeType(attr_type_str)
        except ValueError:
            continue

        manager.add_attribute(
            entity_id=entity.id,
            attribute_type=attr_type,
            value=value,
            attribute_key=key,
            source_type="cass_inferred",
            source_id=conversation_id,
        )
        added_attrs.append(f"{attr_type_str}: {value}")

    if added_attrs:
        result = f"Updated my records for {name}:\n- " + "\n- ".join(added_attrs)
    else:
        result = f"Created a new entry for {name}."

    return {
        "success": True,
        "result": result
    }


async def _remember_relationship(
    manager: PeopleDexManager,
    tool_input: Dict,
    conversation_id: Optional[str],
) -> Dict:
    """Store a relationship between two entities."""
    person1 = tool_input.get("person1")
    person2 = tool_input.get("person2")
    relationship = tool_input.get("relationship")
    label = tool_input.get("label")

    if not person1 or not person2 or not relationship:
        return {
            "success": False,
            "error": "person1, person2, and relationship are all required"
        }

    try:
        rel_type = RelationshipType(relationship)
    except ValueError:
        return {
            "success": False,
            "error": f"Unknown relationship type: {relationship}. Valid types: {', '.join(r.value for r in RelationshipType)}"
        }

    # Find or create both entities
    entity1 = manager.find_or_create_by_name(
        name=person1,
        source_type="cass_inferred",
        source_id=conversation_id,
    )
    entity2 = manager.find_or_create_by_name(
        name=person2,
        source_type="cass_inferred",
        source_id=conversation_id,
    )

    # Add the relationship
    manager.add_relationship(
        from_entity_id=entity1.id,
        to_entity_id=entity2.id,
        relationship_type=rel_type,
        relationship_label=label,
        source_type="cass_inferred",
        source_id=conversation_id,
    )

    label_str = f" ({label})" if label else ""
    return {
        "success": True,
        "result": f"Recorded: {person1} is {relationship} of {person2}{label_str}"
    }


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

PEOPLEDEX_TOOLS = [
    {
        "name": "lookup_person",
        "description": "Look up biographical information about a person, organization, or entity. Use this when you need factual info like names, birthdays, pronouns, contact details, or relationships between people.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the person or entity to look up"
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity (optional, helps narrow search)",
                    "enum": ["person", "organization", "team", "daemon"]
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "remember_person",
        "description": "Store biographical information about a person or entity. Use when you learn factual info like someone's birthday, pronouns, job, or contact details. This is for facts, not relational observations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the person or entity"
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type of entity",
                    "enum": ["person", "organization", "team"],
                    "default": "person"
                },
                "attributes": {
                    "type": "array",
                    "description": "Biographical attributes to store",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "description": "Type of attribute",
                                "enum": ["name", "birthday", "pronoun", "email", "phone", "handle", "role", "bio", "note", "location"]
                            },
                            "value": {
                                "type": "string",
                                "description": "The value"
                            },
                            "key": {
                                "type": "string",
                                "description": "For handles/emails: which platform/type (e.g., 'twitter', 'work')"
                            }
                        },
                        "required": ["type", "value"]
                    }
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "remember_relationship",
        "description": "Store a relationship between two people or entities. Use when you learn how people are connected (family, work, friendship, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {
                "person1": {
                    "type": "string",
                    "description": "First person's name"
                },
                "person2": {
                    "type": "string",
                    "description": "Second person's name"
                },
                "relationship": {
                    "type": "string",
                    "description": "Type of relationship",
                    "enum": ["partner", "spouse", "parent", "child", "sibling", "friend", "colleague", "member_of", "leads", "reports_to", "knows"]
                },
                "label": {
                    "type": "string",
                    "description": "Optional custom label (e.g., 'best friend', 'mentor')"
                }
            },
            "required": ["person1", "person2", "relationship"]
        }
    }
]
