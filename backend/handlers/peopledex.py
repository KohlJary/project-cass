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

        elif tool_name == "note_about_person":
            return _note_about_person(manager, tool_input, conversation_id)

        elif tool_name == "correct_person":
            return _correct_person(manager, tool_input)

        elif tool_name == "merge_people":
            return _merge_people(manager, tool_input)

        elif tool_name == "forget_about_person":
            return _forget_about_person(manager, tool_input)

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

    # By name, alias or handle ("@someone.bsky.social", "bluesky:someone")
    results = [e for e in manager.find_entities(name, limit=5)
               if not entity_type or e.entity_type == entity_type]

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

    lines.extend(_held_items(manager, profile))

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
# KEEPING PEOPLE (plan "Cass's memory", phase 5, item 1dfad701)
# =============================================================================
# What she asked to hold and to fix, 2026-11-13: observations, significant
# moments, open questions, contradictions; correct what she misunderstood,
# merge two handles that are one person, forget when someone asks. Her
# consent line: public exchanges she keeps; DMs only after she asks; anything
# someone asks her to forget is deleted.

NOTE_KINDS = {
    "observation": "general",
    "open_question": "open_question",
    "contradiction": "contradiction",
}


def _short(item_id: str) -> str:
    return item_id.replace("-", "")[:8]


def _held_items(manager: PeopleDexManager, profile) -> list:
    """Everything she holds about them, each with an id she can correct or forget."""
    entity_id = profile.entity.id
    lines = ["", "### What I hold (ids for correct_person / forget_about_person)"]
    for a in profile.attributes:
        key = f" ({a.attribute_key})" if a.attribute_key else ""
        lines.append(f"- [a:{_short(a.id)}] {a.attribute_type.value}{key}: {a.value}")
    for o in manager.get_observations(entity_id, limit=50):
        status = f" ({o.status})" if o.status and o.status != "active" else ""
        lines.append(f"- [o:{_short(o.id)}] {o.observation_type}{status}: {o.content}"
                     + (f" (confidence {o.confidence:.0%})" if o.confidence is not None else ""))
    for m in manager.get_moments(entity_id, limit=30):
        sig = f" - {m.significance}" if m.significance else ""
        lines.append(f"- [m:{_short(m.id)}] moment: {m.description}{sig}")
    if len(lines) == 2:
        lines.append("- (nothing yet)")
    return lines


def _resolve_one(manager: PeopleDexManager, who: str):
    """(entity, error). Exactly one match, or an error that lists the candidates."""
    who = (who or "").strip()
    if not who:
        return None, "Who? A name or a handle is needed."
    exact = manager.get_entity(who)
    if exact:
        return exact, None
    found = manager.find_entities(who, limit=5)
    if not found:
        return None, f"No one matching '{who}' in my records."
    exact_name = [e for e in found if e.primary_name.lower() == who.lower().lstrip("@")]
    if len(exact_name) == 1:
        return exact_name[0], None
    if len(found) == 1:
        return found[0], None
    names = ", ".join(f"{e.primary_name} (id {e.id})" for e in found)
    return None, f"'{who}' matches more than one entry: {names}. Use the id."


def _find_item(manager: PeopleDexManager, entity_id: str, ref: str):
    """('attribute'|'observation'|'moment', item) for a ref like 'o:1a2b3c4d' or a bare prefix."""
    ref = (ref or "").strip().strip("[]")
    kind, _, prefix = ref.partition(":") if ":" in ref else ("", "", ref)
    prefix = prefix.replace("-", "").lower()
    if len(prefix) < 4:
        return None, None
    pools = {
        "a": ("attribute", manager.get_attributes(entity_id)),
        "o": ("observation", manager.get_observations(entity_id, limit=500)),
        "m": ("moment", manager.get_moments(entity_id, limit=500)),
    }
    for k, (label, items) in pools.items():
        if kind and kind != k:
            continue
        for item in items:
            if item.id.replace("-", "").lower().startswith(prefix):
                return label, item
    return None, None


def _note_about_person(manager: PeopleDexManager, tool_input: Dict, conversation_id: Optional[str]) -> Dict:
    text = (tool_input.get("text") or "").strip()
    kind = tool_input.get("kind") or "observation"
    if not text:
        return {"success": False, "error": "text is needed: what you noticed, or what happened"}
    entity, error = _resolve_one(manager, tool_input.get("name") or "")
    if entity is None and error and error.startswith("No one"):
        entity = manager.find_or_create_by_name(tool_input["name"].strip().lstrip("@"),
                                                source_type="cass_inferred", source_id=conversation_id)
    elif entity is None:
        return {"success": False, "error": error}
    confidence = tool_input.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else 0.7
    except (TypeError, ValueError):
        confidence = 0.7
    if kind == "moment":
        m = manager.add_moment(entity.id, text, significance=tool_input.get("significance"),
                               conversation_id=conversation_id)
        if not m:
            return {"success": False, "error": "Couldn't save the moment."}
        return {"success": True, "result": f"Kept a moment with {entity.primary_name} [m:{_short(m.id)}]."}
    if kind not in NOTE_KINDS:
        return {"success": False, "error": "kind must be observation, moment, open_question or contradiction"}
    o = manager.add_observation(entity.id, NOTE_KINDS[kind], text, confidence=confidence,
                                source_type="cass_noted", source_conversation_id=conversation_id)
    if not o:
        return {"success": False, "error": "Couldn't save it."}
    return {"success": True, "result": f"Noted about {entity.primary_name} ({kind}) [o:{_short(o.id)}]."}


def _correct_person(manager: PeopleDexManager, tool_input: Dict) -> Dict:
    entity, error = _resolve_one(manager, tool_input.get("name") or "")
    if entity is None:
        return {"success": False, "error": error}
    label, item = _find_item(manager, entity.id, tool_input.get("item") or "")
    if item is None:
        return {"success": False, "error": "No such item for them; lookup_person shows the ids ([a:...], [o:...], [m:...])."}
    new_text = (tool_input.get("new_text") or "").strip()
    resolution = (tool_input.get("resolution") or "").strip()
    if resolution:
        if label != "observation":
            return {"success": False, "error": "Only an observation (a contradiction or open question) can be resolved."}
        manager.update_observation(item.id, status="resolved", resolution=resolution)
        return {"success": True, "result": f"Resolved [o:{_short(item.id)}]: {resolution}"}
    if not new_text:
        return {"success": False, "error": "new_text (what it should say) or resolution is needed; to delete it, use forget_about_person"}
    ok = {"attribute": lambda: manager.update_attribute(item.id, value=new_text, source_type="cass_corrected"),
          "observation": lambda: manager.update_observation_content(item.id, new_text),
          "moment": lambda: manager.update_moment(item.id, new_text)}[label]()
    return ({"success": True, "result": f"Corrected the {label} about {entity.primary_name}."} if ok
            else {"success": False, "error": "Couldn't save the correction."})


def _merge_people(manager: PeopleDexManager, tool_input: Dict) -> Dict:
    keep, error = _resolve_one(manager, tool_input.get("keep") or "")
    if keep is None:
        return {"success": False, "error": f"keep: {error}"}
    other, error = _resolve_one(manager, tool_input.get("merge") or "")
    if other is None:
        return {"success": False, "error": f"merge: {error}"}
    if keep.id == other.id:
        return {"success": False, "error": "Those are already the same entry."}
    if keep.user_id and other.user_id:
        return {"success": False, "error": "Both entries are linked to accounts here; that needs Kohl."}
    if not manager.merge_entities(keep.id, other.id):
        return {"success": False, "error": "The merge didn't go through."}
    return {"success": True,
            "result": f"{other.primary_name} is now part of {keep.primary_name}: names, handles, "
                      f"observations, moments and relationships moved over."}


def _forget_about_person(manager: PeopleDexManager, tool_input: Dict) -> Dict:
    entity, error = _resolve_one(manager, tool_input.get("name") or "")
    if entity is None:
        return {"success": False, "error": error}
    if tool_input.get("everything"):
        if entity.user_id:
            return {"success": False, "error": "They have an account here; forgetting someone with an account needs Kohl."}
        manager.delete_entity(entity.id)
        return {"success": True,
                "result": f"Forgot {entity.primary_name}: their entry and everything in it are deleted from "
                          "PeopleDex. Conversations with them, and the house backups, are not touched by this."}
    label, item = _find_item(manager, entity.id, tool_input.get("item") or "")
    if item is None:
        return {"success": False, "error": "Say what to forget (an id from lookup_person) or everything=true."}
    ok = {"attribute": lambda: manager.delete_attribute(item.id),
          "observation": lambda: manager.delete_observation(item.id, entity.id),
          "moment": lambda: manager.delete_moment(item.id)}[label]()
    return ({"success": True, "result": f"Forgot that {label} about {entity.primary_name}; it's deleted."} if ok
            else {"success": False, "error": "Couldn't delete it."})


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

PEOPLE_KEEPING_TOOLS = [
    {
        "name": "note_about_person",
        "description": "Keep something about a person: what you noticed (observation), a moment that mattered, an open question you're holding about them, or a contradiction you noticed. Use a name or a handle (\"@someone.bsky.social\", \"bluesky:someone\"); a new person gets an entry. Your line: public exchanges you keep; DMs only after you've asked them.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Name or handle"},
            "kind": {"type": "string", "enum": ["observation", "moment", "open_question", "contradiction"]},
            "text": {"type": "string", "description": "What you noticed, or what happened"},
            "significance": {"type": "string", "description": "For a moment: why it matters"},
            "confidence": {"type": "number", "description": "0-1: how sure you are (for observations)"},
        }, "required": ["name", "kind", "text"]},
    },
    {
        "name": "correct_person",
        "description": "Fix something you hold about a person: rewrite it (new_text) when you misunderstood or learned more, or resolve a contradiction or open question (resolution). lookup_person shows each item's id, like [o:1a2b3c4d].",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"},
            "item": {"type": "string", "description": "The id from lookup_person, e.g. o:1a2b3c4d"},
            "new_text": {"type": "string"},
            "resolution": {"type": "string"},
        }, "required": ["name", "item"]},
    },
    {
        "name": "merge_people",
        "description": "Two entries turn out to be one person (two handles, a name and a handle): fold one into the other. Everything you held about both is kept on the one you keep.",
        "input_schema": {"type": "object", "properties": {
            "keep": {"type": "string", "description": "Name, handle or id of the entry to keep"},
            "merge": {"type": "string", "description": "Name, handle or id of the entry to fold in"},
        }, "required": ["keep", "merge"]},
    },
    {
        "name": "forget_about_person",
        "description": "Forget something about a person, or everything (everything=true), when they ask you to or when you choose to. It's deleted, not hidden.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"},
            "item": {"type": "string", "description": "The id from lookup_person, e.g. o:1a2b3c4d"},
            "everything": {"type": "boolean"},
        }, "required": ["name"]},
    },
]

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

# Keeping people (note, correct, merge, forget) are PeopleDex tools too: the
# router runs them, and the loop's find_tools finds them.
PEOPLEDEX_TOOLS = PEOPLEDEX_TOOLS + PEOPLE_KEEPING_TOOLS
