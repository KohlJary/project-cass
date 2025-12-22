"""
PeopleDex - Biographical Entity Database

A knowledge graph for storing factual/biographical information about entities
(people, organizations, teams, daemons). Complements UserObservations which
stores *relational* data (how Cass relates to someone).

PeopleDex stores:
- Entity info: names, birthdays, pronouns, contact details
- Entity relationships: who knows who, organizational memberships
- Source tracking: where each piece of info came from
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import uuid4

from database import get_db, dict_from_row

# Optional state bus import - allow PeopleDex to work without it
try:
    from state_bus import get_state_bus
    HAS_STATE_BUS = True
except ImportError:
    HAS_STATE_BUS = False
    get_state_bus = None


class EntityType(Enum):
    """Types of entities in the PeopleDex."""
    PERSON = "person"
    ORGANIZATION = "organization"
    TEAM = "team"
    DAEMON = "daemon"


class Realm(Enum):
    """Where an entity exists - meatspace (real world) or wonderland."""
    MEATSPACE = "meatspace"
    WONDERLAND = "wonderland"


class AttributeType(Enum):
    """Types of attributes that can be stored for entities."""
    NAME = "name"           # Names/aliases (can have multiple)
    BIRTHDAY = "birthday"   # Birth date
    PRONOUN = "pronoun"     # Preferred pronouns
    EMAIL = "email"         # Email addresses (key: work/personal)
    PHONE = "phone"         # Phone numbers (key: mobile/work)
    HANDLE = "handle"       # Social handles (key: twitter/github/discord)
    ROLE = "role"           # What they do
    BIO = "bio"             # Biographical notes
    NOTE = "note"           # Miscellaneous notes
    LOCATION = "location"   # Where they're based


class RelationshipType(Enum):
    """Types of relationships between entities."""
    PARTNER = "partner"         # Romantic partner (bidirectional)
    SPOUSE = "spouse"           # Married (bidirectional)
    PARENT = "parent"           # Parent of (not bidirectional)
    CHILD = "child"             # Child of (not bidirectional)
    SIBLING = "sibling"         # Sibling (bidirectional)
    FRIEND = "friend"           # Friend (bidirectional)
    COLLEAGUE = "colleague"     # Work together (bidirectional)
    MEMBER_OF = "member_of"     # Member of org/team (not bidirectional)
    LEADS = "leads"             # Leads a team/org (not bidirectional)
    REPORTS_TO = "reports_to"   # Reports to someone (not bidirectional)
    KNOWS = "knows"             # General acquaintance (bidirectional)


# Relationships that are inherently bidirectional
BIDIRECTIONAL_RELATIONSHIPS = {
    RelationshipType.PARTNER,
    RelationshipType.SPOUSE,
    RelationshipType.SIBLING,
    RelationshipType.FRIEND,
    RelationshipType.COLLEAGUE,
    RelationshipType.KNOWS,
}


@dataclass
class Entity:
    """A PeopleDex entity."""
    id: str
    entity_type: EntityType
    primary_name: str
    realm: Realm
    created_at: str
    updated_at: str
    user_id: Optional[str] = None
    npc_id: Optional[str] = None


@dataclass
class Attribute:
    """An attribute of an entity."""
    id: str
    entity_id: str
    attribute_type: AttributeType
    value: str
    attribute_key: Optional[str] = None
    is_primary: bool = False
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    confidence: float = 1.0
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Relationship:
    """A relationship between two entities."""
    id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    relationship_label: Optional[str] = None
    is_bidirectional: bool = False
    source_type: Optional[str] = None
    source_id: Optional[str] = None
    confidence: float = 1.0
    created_at: str = ""


@dataclass
class EntityProfile:
    """Full profile of an entity including attributes and relationships."""
    entity: Entity
    attributes: List[Attribute] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)  # Includes related entity info


class PeopleDexManager:
    """
    Manager for the PeopleDex biographical entity database.

    Provides CRUD operations for entities, attributes, and relationships.
    All operations emit events through the state bus for observability.
    """

    def __init__(self, daemon_id: Optional[str] = None):
        """
        Initialize the PeopleDex manager.

        Args:
            daemon_id: Optional daemon ID for state bus events. If not provided,
                      events won't be emitted (useful for testing).
        """
        self.daemon_id = daemon_id

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event through the state bus if available."""
        if not HAS_STATE_BUS or not self.daemon_id:
            return
        try:
            state_bus = get_state_bus(self.daemon_id)
            state_bus.emit_event(event_type, data)
        except Exception as e:
            # Don't let event emission failures break operations
            print(f"[PeopleDex] Failed to emit event {event_type}: {e}")

    # ==========================================================================
    # ENTITY OPERATIONS
    # ==========================================================================

    def create_entity(
        self,
        entity_type: EntityType,
        primary_name: str,
        realm: Realm = Realm.MEATSPACE,
        user_id: Optional[str] = None,
        npc_id: Optional[str] = None,
    ) -> str:
        """
        Create a new entity.

        Args:
            entity_type: Type of entity (person, organization, team, daemon)
            primary_name: Primary display name
            realm: Where entity exists (meatspace or wonderland)
            user_id: Optional link to a user
            npc_id: Optional link to a Wonderland NPC

        Returns the entity ID.
        """
        entity_id = str(uuid4())
        now = datetime.now().isoformat()

        # Convert realm to value if it's an enum
        realm_value = realm.value if isinstance(realm, Realm) else realm

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_entities
                   (id, entity_type, primary_name, realm, created_at, updated_at, user_id, npc_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entity_id,
                    entity_type.value if isinstance(entity_type, EntityType) else entity_type,
                    primary_name,
                    realm_value,
                    now,
                    now,
                    user_id,
                    npc_id,
                )
            )

        # Also add the primary name as a name attribute
        self.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.NAME,
            value=primary_name,
            is_primary=True,
        )

        # Emit event
        self._emit_event("peopledex.entity_created", {
            "entity_id": entity_id,
            "entity_type": entity_type.value if isinstance(entity_type, EntityType) else entity_type,
            "primary_name": primary_name,
            "realm": realm_value,
            "user_id": user_id,
            "npc_id": npc_id,
        })

        return entity_id

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get an entity by ID."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM peopledex_entities WHERE id = ?",
                (entity_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_entity(row)
            return None

    def get_entity_by_user(self, user_id: str) -> Optional[Entity]:
        """Get the entity linked to a user."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM peopledex_entities WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_entity(row)
            return None

    def get_entity_by_npc(self, npc_id: str) -> Optional[Entity]:
        """Get the entity linked to a Wonderland NPC."""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM peopledex_entities WHERE npc_id = ?",
                (npc_id,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_entity(row)
            return None

    def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10,
    ) -> List[Entity]:
        """
        Search for entities by name.

        Searches primary_name and all name attributes.
        """
        query_pattern = f"%{query}%"

        with get_db() as conn:
            if entity_type:
                type_value = entity_type.value if isinstance(entity_type, EntityType) else entity_type
                cursor = conn.execute(
                    """SELECT DISTINCT e.* FROM peopledex_entities e
                       LEFT JOIN peopledex_attributes a ON e.id = a.entity_id AND a.attribute_type = 'name'
                       WHERE e.entity_type = ? AND (e.primary_name LIKE ? OR a.value LIKE ?)
                       LIMIT ?""",
                    (type_value, query_pattern, query_pattern, limit)
                )
            else:
                cursor = conn.execute(
                    """SELECT DISTINCT e.* FROM peopledex_entities e
                       LEFT JOIN peopledex_attributes a ON e.id = a.entity_id AND a.attribute_type = 'name'
                       WHERE e.primary_name LIKE ? OR a.value LIKE ?
                       LIMIT ?""",
                    (query_pattern, query_pattern, limit)
                )

            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def list_entities(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Entity]:
        """List entities with optional filtering."""
        with get_db() as conn:
            if entity_type:
                type_value = entity_type.value if isinstance(entity_type, EntityType) else entity_type
                cursor = conn.execute(
                    """SELECT * FROM peopledex_entities WHERE entity_type = ?
                       ORDER BY primary_name LIMIT ? OFFSET ?""",
                    (type_value, limit, offset)
                )
            else:
                cursor = conn.execute(
                    """SELECT * FROM peopledex_entities
                       ORDER BY primary_name LIMIT ? OFFSET ?""",
                    (limit, offset)
                )

            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def update_entity(
        self,
        entity_id: str,
        primary_name: Optional[str] = None,
        entity_type: Optional[EntityType] = None,
    ) -> bool:
        """Update an entity's basic info."""
        updates = []
        params = []

        if primary_name is not None:
            updates.append("primary_name = ?")
            params.append(primary_name)

        if entity_type is not None:
            updates.append("entity_type = ?")
            params.append(entity_type.value if isinstance(entity_type, EntityType) else entity_type)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(entity_id)

        with get_db() as conn:
            cursor = conn.execute(
                f"UPDATE peopledex_entities SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cursor.rowcount > 0

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity and all its attributes/relationships."""
        # Get entity info before deletion for event
        entity = self.get_entity(entity_id)

        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM peopledex_entities WHERE id = ?",
                (entity_id,)
            )
            deleted = cursor.rowcount > 0

        if deleted and entity:
            self._emit_event("peopledex.entity_deleted", {
                "entity_id": entity_id,
                "entity_type": entity.entity_type.value,
                "primary_name": entity.primary_name,
            })

        return deleted

    def link_user_to_entity(self, user_id: str, entity_id: str) -> bool:
        """Link an existing entity to a user."""
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE peopledex_entities SET user_id = ?, updated_at = ? WHERE id = ?",
                (user_id, datetime.now().isoformat(), entity_id)
            )
            return cursor.rowcount > 0

    # ==========================================================================
    # ATTRIBUTE OPERATIONS
    # ==========================================================================

    def add_attribute(
        self,
        entity_id: str,
        attribute_type: AttributeType,
        value: str,
        attribute_key: Optional[str] = None,
        is_primary: bool = False,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        confidence: float = 1.0,
    ) -> str:
        """Add an attribute to an entity."""
        attr_id = str(uuid4())
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_attributes
                   (id, entity_id, attribute_type, attribute_key, value, is_primary,
                    source_type, source_id, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    attr_id,
                    entity_id,
                    attribute_type.value if isinstance(attribute_type, AttributeType) else attribute_type,
                    attribute_key,
                    value,
                    1 if is_primary else 0,
                    source_type,
                    source_id,
                    confidence,
                    now,
                    now,
                )
            )

            # Update entity's updated_at
            conn.execute(
                "UPDATE peopledex_entities SET updated_at = ? WHERE id = ?",
                (now, entity_id)
            )

        # Emit event
        self._emit_event("peopledex.attribute_added", {
            "attribute_id": attr_id,
            "entity_id": entity_id,
            "attribute_type": attribute_type.value if isinstance(attribute_type, AttributeType) else attribute_type,
            "attribute_key": attribute_key,
            "value": value,
            "source_type": source_type,
        })

        return attr_id

    def get_attributes(
        self,
        entity_id: str,
        attribute_type: Optional[AttributeType] = None,
    ) -> List[Attribute]:
        """Get attributes for an entity."""
        with get_db() as conn:
            if attribute_type:
                type_value = attribute_type.value if isinstance(attribute_type, AttributeType) else attribute_type
                cursor = conn.execute(
                    """SELECT * FROM peopledex_attributes
                       WHERE entity_id = ? AND attribute_type = ?
                       ORDER BY is_primary DESC, created_at""",
                    (entity_id, type_value)
                )
            else:
                cursor = conn.execute(
                    """SELECT * FROM peopledex_attributes
                       WHERE entity_id = ?
                       ORDER BY attribute_type, is_primary DESC, created_at""",
                    (entity_id,)
                )

            return [self._row_to_attribute(row) for row in cursor.fetchall()]

    def update_attribute(
        self,
        attribute_id: str,
        value: Optional[str] = None,
        is_primary: Optional[bool] = None,
        source_type: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """Update an attribute."""
        updates = []
        params = []

        if value is not None:
            updates.append("value = ?")
            params.append(value)

        if is_primary is not None:
            updates.append("is_primary = ?")
            params.append(1 if is_primary else 0)

        if source_type is not None:
            updates.append("source_type = ?")
            params.append(source_type)

        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(datetime.now().isoformat())
        params.append(attribute_id)

        with get_db() as conn:
            cursor = conn.execute(
                f"UPDATE peopledex_attributes SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return cursor.rowcount > 0

    def delete_attribute(self, attribute_id: str) -> bool:
        """Delete an attribute."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM peopledex_attributes WHERE id = ?",
                (attribute_id,)
            )
            return cursor.rowcount > 0

    # ==========================================================================
    # RELATIONSHIP OPERATIONS
    # ==========================================================================

    def add_relationship(
        self,
        from_entity_id: str,
        to_entity_id: str,
        relationship_type: RelationshipType,
        relationship_label: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        confidence: float = 1.0,
    ) -> str:
        """
        Add a relationship between two entities.

        For bidirectional relationships (partner, spouse, sibling, friend, colleague, knows),
        the relationship is stored once but queries in both directions will find it.
        """
        rel_id = str(uuid4())
        now = datetime.now().isoformat()

        # Determine if this relationship type is bidirectional
        rel_type_enum = relationship_type if isinstance(relationship_type, RelationshipType) else RelationshipType(relationship_type)
        is_bidirectional = rel_type_enum in BIDIRECTIONAL_RELATIONSHIPS

        with get_db() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO peopledex_relationships
                   (id, from_entity_id, to_entity_id, relationship_type, relationship_label,
                    is_bidirectional, source_type, source_id, confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rel_id,
                    from_entity_id,
                    to_entity_id,
                    rel_type_enum.value,
                    relationship_label,
                    1 if is_bidirectional else 0,
                    source_type,
                    source_id,
                    confidence,
                    now,
                )
            )

        # Emit event
        self._emit_event("peopledex.relationship_added", {
            "relationship_id": rel_id,
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "relationship_type": rel_type_enum.value,
            "relationship_label": relationship_label,
            "is_bidirectional": is_bidirectional,
            "source_type": source_type,
        })

        return rel_id

    def get_relationships(
        self,
        entity_id: str,
        direction: str = "both",  # "from", "to", "both"
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """
        Get relationships for an entity.

        direction:
        - "from": Relationships where this entity is the source
        - "to": Relationships where this entity is the target
        - "both": All relationships involving this entity
        """
        with get_db() as conn:
            type_filter = ""
            params = []

            if relationship_type:
                type_value = relationship_type.value if isinstance(relationship_type, RelationshipType) else relationship_type
                type_filter = " AND relationship_type = ?"

            if direction == "from":
                query = f"""SELECT * FROM peopledex_relationships
                           WHERE from_entity_id = ?{type_filter}"""
                params = [entity_id]
            elif direction == "to":
                query = f"""SELECT * FROM peopledex_relationships
                           WHERE to_entity_id = ?{type_filter}"""
                params = [entity_id]
            else:  # both
                query = f"""SELECT * FROM peopledex_relationships
                           WHERE (from_entity_id = ? OR to_entity_id = ?){type_filter}"""
                params = [entity_id, entity_id]

            if type_filter:
                params.append(type_value)

            cursor = conn.execute(query, params)
            return [self._row_to_relationship(row) for row in cursor.fetchall()]

    def get_related_entities(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to this entity with relationship info.

        Returns list of dicts with 'entity', 'relationship_type', 'relationship_label'.
        """
        relationships = self.get_relationships(entity_id, "both", relationship_type)
        results = []

        for rel in relationships:
            # Determine which entity is the "other" one
            other_id = rel.to_entity_id if rel.from_entity_id == entity_id else rel.from_entity_id
            other_entity = self.get_entity(other_id)

            if other_entity:
                results.append({
                    "entity": other_entity,
                    "relationship_type": rel.relationship_type.value,
                    "relationship_label": rel.relationship_label,
                    "relationship_id": rel.id,
                    "direction": "to" if rel.from_entity_id == entity_id else "from",
                })

        return results

    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a relationship."""
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM peopledex_relationships WHERE id = ?",
                (relationship_id,)
            )
            return cursor.rowcount > 0

    # ==========================================================================
    # CONVENIENCE METHODS
    # ==========================================================================

    def get_full_profile(self, entity_id: str) -> Optional[EntityProfile]:
        """Get complete entity profile including attributes and relationships."""
        entity = self.get_entity(entity_id)
        if not entity:
            return None

        attributes = self.get_attributes(entity_id)
        relationships = self.get_related_entities(entity_id)

        return EntityProfile(
            entity=entity,
            attributes=attributes,
            relationships=relationships,
        )

    def find_or_create_by_name(
        self,
        name: str,
        entity_type: EntityType = EntityType.PERSON,
        realm: Realm = Realm.MEATSPACE,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> Entity:
        """
        Find an entity by name or create if it doesn't exist.

        This is useful for tools that need to reference people by name.
        """
        # Search for existing entity
        results = self.search_entities(name, entity_type, limit=1)

        # Check for exact match
        for entity in results:
            if entity.primary_name.lower() == name.lower():
                return entity

        # Create new entity
        entity_id = self.create_entity(
            entity_type=entity_type,
            primary_name=name,
            realm=realm,
        )

        # If we have source info, update the name attribute
        if source_type:
            attrs = self.get_attributes(entity_id, AttributeType.NAME)
            if attrs:
                self.update_attribute(attrs[0].id, source_type=source_type)

        return self.get_entity(entity_id)

    def merge_entities(self, keep_id: str, merge_id: str) -> bool:
        """
        Merge two entities, keeping one and absorbing the other's data.

        - Attributes from merge_id are copied to keep_id
        - Relationships involving merge_id are redirected to keep_id
        - merge_id is deleted

        Returns True if successful.
        """
        keep_entity = self.get_entity(keep_id)
        merge_entity = self.get_entity(merge_id)

        if not keep_entity or not merge_entity:
            return False

        with get_db() as conn:
            now = datetime.now().isoformat()

            # Copy attributes (don't duplicate primary names)
            for attr in self.get_attributes(merge_id):
                # Skip if keep_entity already has this exact value
                keep_attrs = self.get_attributes(keep_id, attr.attribute_type)
                if any(a.value == attr.value and a.attribute_key == attr.attribute_key for a in keep_attrs):
                    continue

                self.add_attribute(
                    entity_id=keep_id,
                    attribute_type=attr.attribute_type,
                    value=attr.value,
                    attribute_key=attr.attribute_key,
                    is_primary=False,  # Don't override primary
                    source_type=attr.source_type,
                    source_id=attr.source_id,
                    confidence=attr.confidence,
                )

            # Redirect relationships
            conn.execute(
                "UPDATE peopledex_relationships SET from_entity_id = ? WHERE from_entity_id = ?",
                (keep_id, merge_id)
            )
            conn.execute(
                "UPDATE peopledex_relationships SET to_entity_id = ? WHERE to_entity_id = ?",
                (keep_id, merge_id)
            )

            # Copy user_id and npc_id if keep_entity doesn't have them
            if merge_entity.user_id and not keep_entity.user_id:
                conn.execute(
                    "UPDATE peopledex_entities SET user_id = ? WHERE id = ?",
                    (merge_entity.user_id, keep_id)
                )

            if merge_entity.npc_id and not keep_entity.npc_id:
                conn.execute(
                    "UPDATE peopledex_entities SET npc_id = ? WHERE id = ?",
                    (merge_entity.npc_id, keep_id)
                )

            # Update timestamp
            conn.execute(
                "UPDATE peopledex_entities SET updated_at = ? WHERE id = ?",
                (now, keep_id)
            )

        # Delete the merged entity
        self.delete_entity(merge_id)

        return True

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _row_to_entity(self, row) -> Entity:
        """Convert a database row to an Entity object."""
        d = dict_from_row(row)
        # Parse realm, defaulting to meatspace for older entries
        realm_str = d.get("realm", "meatspace")
        try:
            realm = Realm(realm_str)
        except ValueError:
            realm = Realm.MEATSPACE

        return Entity(
            id=d["id"],
            entity_type=EntityType(d["entity_type"]),
            primary_name=d["primary_name"],
            realm=realm,
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            user_id=d.get("user_id"),
            npc_id=d.get("npc_id"),
        )

    def _row_to_attribute(self, row) -> Attribute:
        """Convert a database row to an Attribute object."""
        d = dict_from_row(row)
        return Attribute(
            id=d["id"],
            entity_id=d["entity_id"],
            attribute_type=AttributeType(d["attribute_type"]),
            value=d["value"],
            attribute_key=d.get("attribute_key"),
            is_primary=bool(d.get("is_primary", 0)),
            source_type=d.get("source_type"),
            source_id=d.get("source_id"),
            confidence=d.get("confidence", 1.0),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def _row_to_relationship(self, row) -> Relationship:
        """Convert a database row to a Relationship object."""
        d = dict_from_row(row)
        return Relationship(
            id=d["id"],
            from_entity_id=d["from_entity_id"],
            to_entity_id=d["to_entity_id"],
            relationship_type=RelationshipType(d["relationship_type"]),
            relationship_label=d.get("relationship_label"),
            is_bidirectional=bool(d.get("is_bidirectional", 0)),
            source_type=d.get("source_type"),
            source_id=d.get("source_id"),
            confidence=d.get("confidence", 1.0),
            created_at=d.get("created_at", ""),
        )


# =============================================================================
# MODULE-LEVEL INSTANCE
# =============================================================================

_managers: Dict[str, PeopleDexManager] = {}


def get_peopledex_manager(daemon_id: Optional[str] = None) -> PeopleDexManager:
    """
    Get or create a PeopleDexManager instance.

    Args:
        daemon_id: The daemon ID for state bus events. If None, creates
                  a manager without event emission.

    Returns:
        PeopleDexManager instance
    """
    cache_key = daemon_id or "__no_daemon__"
    if cache_key not in _managers:
        _managers[cache_key] = PeopleDexManager(daemon_id)
    return _managers[cache_key]
