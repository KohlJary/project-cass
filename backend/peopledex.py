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


# =============================================================================
# RELATIONAL DATA TYPES (PeopleDex Consolidation)
# =============================================================================

@dataclass
class Observation:
    """A relational observation about an entity."""
    id: str
    entity_id: str
    daemon_id: str
    observation_type: str  # identity_statement, value, communication_style, growth_observation, contradiction, open_question, general
    content: str
    metadata: Optional[Dict[str, Any]] = None
    confidence: float = 0.7
    source_type: Optional[str] = None
    source_conversation_id: Optional[str] = None
    first_noticed: Optional[str] = None
    last_validated: Optional[str] = None
    validation_count: int = 0
    status: str = "active"
    resolution: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str = ""
    updated_at: Optional[str] = None


@dataclass
class Moment:
    """A significant relational moment with an entity."""
    id: str
    entity_id: str
    daemon_id: str
    description: str
    significance: Optional[str] = None
    category: str = "connection"  # milestone, connection, growth, challenge, ritual
    conversation_id: Optional[str] = None
    timestamp: str = ""
    created_at: str = ""


@dataclass
class RelationshipPattern:
    """A recurring pattern or significant shift in a relationship."""
    id: str
    entity_id: str
    daemon_id: str
    pattern_type: str  # pattern, shift, ritual
    name: Optional[str] = None
    description: str = ""
    frequency: Optional[str] = None  # occasional, regular, frequent
    valence: Optional[str] = None  # positive, neutral, challenging, mixed
    examples: List[str] = field(default_factory=list)
    from_state: Optional[str] = None  # For shifts
    to_state: Optional[str] = None
    catalyst: Optional[str] = None
    first_noticed: Optional[str] = None
    timestamp: str = ""
    created_at: str = ""


@dataclass
class MutualShaping:
    """How a relationship shapes both parties."""
    id: str
    entity_id: str
    daemon_id: str
    shaping_type: str  # they_shape_me, i_shape_them, inherited_value
    note: str
    created_at: str = ""


@dataclass
class RelationshipMeta:
    """Metadata about a relationship with an entity."""
    entity_id: str
    daemon_id: str
    relationship_type: Optional[str] = None  # primary_partner, collaborator, friend, acquaintance
    formation_date: Optional[str] = None
    current_phase: Optional[str] = None
    is_foundational: bool = False
    first_interaction: Optional[str] = None
    last_interaction: Optional[str] = None
    updated_at: str = ""


@dataclass
class Fact:
    """A biographical fact about an entity."""
    id: str
    entity_id: str
    daemon_id: Optional[str]
    fact_type: str  # birthday, anniversary, location, occupation, education, family, pet, hobby, medical, preference, milestone
    content: str
    date_value: Optional[str] = None  # ISO date if applicable
    is_recurring: bool = False  # True for birthdays/anniversaries
    confidence: float = 0.9
    source_type: str = "stated"  # stated, inferred, observed
    source_conversation_id: Optional[str] = None
    verified: bool = False
    metadata: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: str = ""


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
    # RELATIONAL DATA QUERIES (PeopleDex Consolidation)
    # ==========================================================================

    def get_observations(
        self,
        entity_id: str,
        observation_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Observation]:
        """
        Get observations for an entity.

        Args:
            entity_id: The entity ID
            observation_type: Filter by type (identity_statement, value, etc.)
            status: Filter by status (active, resolved)
            limit: Maximum number to return
        """
        with get_db() as conn:
            query = "SELECT * FROM peopledex_observations WHERE entity_id = ?"
            params: List[Any] = [entity_id]

            if observation_type:
                query += " AND observation_type = ?"
                params.append(observation_type)

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [self._row_to_observation(row) for row in cursor.fetchall()]

    def get_moments(
        self,
        entity_id: str,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Moment]:
        """
        Get shared moments with an entity.

        Args:
            entity_id: The entity ID
            category: Filter by category (milestone, connection, growth, challenge, ritual)
            limit: Maximum number to return
        """
        with get_db() as conn:
            query = "SELECT * FROM peopledex_moments WHERE entity_id = ?"
            params: List[Any] = [entity_id]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [self._row_to_moment(row) for row in cursor.fetchall()]

    def get_relationship_patterns(
        self,
        entity_id: str,
        pattern_type: Optional[str] = None,
    ) -> List[RelationshipPattern]:
        """
        Get relationship patterns/shifts/rituals with an entity.

        Args:
            entity_id: The entity ID
            pattern_type: Filter by type (pattern, shift, ritual)
        """
        with get_db() as conn:
            query = "SELECT * FROM peopledex_relationship_patterns WHERE entity_id = ?"
            params: List[Any] = [entity_id]

            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)

            query += " ORDER BY timestamp DESC"

            cursor = conn.execute(query, params)
            return [self._row_to_pattern(row) for row in cursor.fetchall()]

    def get_mutual_shaping(
        self,
        entity_id: str,
        shaping_type: Optional[str] = None,
    ) -> List[MutualShaping]:
        """
        Get mutual shaping notes for an entity.

        Args:
            entity_id: The entity ID
            shaping_type: Filter by type (they_shape_me, i_shape_them, inherited_value)
        """
        with get_db() as conn:
            query = "SELECT * FROM peopledex_mutual_shaping WHERE entity_id = ?"
            params: List[Any] = [entity_id]

            if shaping_type:
                query += " AND shaping_type = ?"
                params.append(shaping_type)

            query += " ORDER BY created_at"

            cursor = conn.execute(query, params)
            return [self._row_to_shaping(row) for row in cursor.fetchall()]

    def get_relationship_meta(
        self,
        entity_id: str,
        daemon_id: Optional[str] = None,
    ) -> Optional[RelationshipMeta]:
        """
        Get relationship metadata for an entity.

        Args:
            entity_id: The entity ID
            daemon_id: The daemon ID (uses self.daemon_id if not provided)
        """
        daemon_id = daemon_id or self.daemon_id
        if not daemon_id:
            return None

        with get_db() as conn:
            cursor = conn.execute(
                "SELECT * FROM peopledex_relationship_meta WHERE entity_id = ? AND daemon_id = ?",
                (entity_id, daemon_id)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_meta(row)
            return None

    def get_relational_context(
        self,
        entity_id: str,
        include_observations: bool = True,
        include_moments: bool = True,
        include_patterns: bool = True,
        include_shaping: bool = True,
        max_observations: int = 20,
        max_moments: int = 10,
    ) -> str:
        """
        Get assembled relational context for an entity, formatted for prompts.

        This replaces the old get_rich_user_context() and get_relationship_context()
        methods from UserManager.

        Args:
            entity_id: The entity ID
            include_observations: Include identity/value/growth observations
            include_moments: Include shared moments
            include_patterns: Include relationship patterns
            include_shaping: Include mutual shaping notes
            max_observations: Max observations to include
            max_moments: Max moments to include

        Returns:
            Formatted markdown string for prompt injection
        """
        entity = self.get_entity(entity_id)
        if not entity:
            return ""

        meta = self.get_relationship_meta(entity_id)
        sections = []

        # Header
        header = f"## Relational Context: {entity.primary_name}"
        if meta and meta.relationship_type:
            header += f" ({meta.relationship_type})"
        sections.append(header)

        # Relationship metadata
        if meta:
            meta_lines = []
            if meta.formation_date:
                meta_lines.append(f"- Formation: {meta.formation_date}")
            if meta.current_phase:
                meta_lines.append(f"- Current phase: {meta.current_phase}")
            if meta.is_foundational:
                meta_lines.append("- Foundational relationship")
            if meta_lines:
                sections.append("\n".join(meta_lines))

        # Identity statements and values
        if include_observations:
            observations = self.get_observations(entity_id, limit=max_observations)

            # Group by type
            identity_stmts = [o for o in observations if o.observation_type == "identity_statement"]
            values = [o for o in observations if o.observation_type == "value"]
            comm_style = [o for o in observations if o.observation_type == "communication_style"]
            growth_obs = [o for o in observations if o.observation_type == "growth_observation"]
            open_questions = [o for o in observations if o.observation_type == "open_question" and o.status == "active"]

            if identity_stmts:
                sections.append("\n### Who They Are")
                for obs in identity_stmts[:10]:
                    conf = f" ({obs.confidence:.0%})" if obs.confidence < 0.9 else ""
                    sections.append(f"- {obs.content}{conf}")

            if values:
                sections.append("\n### Values")
                for obs in values[:5]:
                    sections.append(f"- {obs.content}")

            if comm_style:
                sections.append("\n### Communication Style")
                for obs in comm_style[:1]:  # Usually just one
                    sections.append(obs.content)
                    if obs.metadata:
                        prefs = obs.metadata.get("preferences", [])
                        if prefs:
                            sections.append("Preferences: " + ", ".join(prefs[:5]))

            if growth_obs:
                sections.append("\n### Growth Observations")
                for obs in growth_obs[:5]:
                    area = ""
                    if obs.metadata and obs.metadata.get("area"):
                        area = f"[{obs.metadata['area']}] "
                    sections.append(f"- {area}{obs.content}")

            if open_questions:
                sections.append("\n### Open Questions")
                for obs in open_questions[:5]:
                    sections.append(f"- {obs.content}")

        # Shared moments
        if include_moments:
            moments = self.get_moments(entity_id, limit=max_moments)
            if moments:
                sections.append("\n### Shared History")
                for moment in moments:
                    cat_marker = ""
                    if moment.category == "milestone":
                        cat_marker = "[Milestone] "
                    elif moment.category == "growth":
                        cat_marker = "[Growth] "
                    sections.append(f"- {cat_marker}{moment.description}")
                    if moment.significance and moment.significance != "medium":
                        sections.append(f"  *{moment.significance}*")

        # Relationship patterns
        if include_patterns:
            patterns = self.get_relationship_patterns(entity_id)
            actual_patterns = [p for p in patterns if p.pattern_type == "pattern"]
            shifts = [p for p in patterns if p.pattern_type == "shift"]
            rituals = [p for p in patterns if p.pattern_type == "ritual"]

            if actual_patterns:
                sections.append("\n### Relational Patterns")
                for p in actual_patterns:
                    name = f"**{p.name}**: " if p.name else ""
                    freq = f" ({p.frequency})" if p.frequency else ""
                    sections.append(f"- {name}{p.description}{freq}")

            if shifts:
                sections.append("\n### Significant Shifts")
                for s in shifts:
                    if s.from_state and s.to_state:
                        sections.append(f"- {s.from_state} → {s.to_state}: {s.description}")
                    else:
                        sections.append(f"- {s.description}")

            if rituals:
                sections.append("\n### Rituals")
                for r in rituals:
                    sections.append(f"- {r.description}")

        # Mutual shaping
        if include_shaping:
            shaping = self.get_mutual_shaping(entity_id)
            they_shape = [s for s in shaping if s.shaping_type == "they_shape_me"]
            i_shape = [s for s in shaping if s.shaping_type == "i_shape_them"]
            inherited = [s for s in shaping if s.shaping_type == "inherited_value"]

            if they_shape:
                sections.append("\n### How They Shape Me")
                for s in they_shape:
                    sections.append(f"- {s.note}")

            if i_shape:
                sections.append("\n### How I Shape Them")
                for s in i_shape:
                    sections.append(f"- {s.note}")

            if inherited:
                sections.append("\n### Inherited Values")
                for s in inherited:
                    sections.append(f"- {s.note}")

        return "\n".join(sections)

    def get_user_relational_context(
        self,
        user_id: str,
        **kwargs,
    ) -> str:
        """
        Get relational context for a user (by user_id rather than entity_id).

        Convenience wrapper around get_relational_context.
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            return ""
        return self.get_relational_context(entity.id, **kwargs)

    # ==========================================================================
    # RELATIONAL DATA WRITES (PeopleDex Consolidation)
    # ==========================================================================

    def add_observation(
        self,
        entity_id: str,
        observation_type: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        confidence: float = 0.7,
        source_type: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
    ) -> Optional[Observation]:
        """
        Add an observation about an entity.

        Args:
            entity_id: The entity ID
            observation_type: Type (identity_statement, value, communication_style,
                             growth_observation, contradiction, open_question, general)
            content: The observation content
            metadata: Optional metadata dict (e.g., {"area": "communication"} for growth)
            confidence: Confidence level 0.0-1.0
            source_type: How this was observed (explicit_reflection, conversation, etc.)
            source_conversation_id: The conversation where this was observed

        Returns:
            The created Observation, or None on error
        """
        if not self.daemon_id:
            return None

        import json
        now = datetime.now().isoformat()
        obs_id = str(uuid4())

        metadata_json = json.dumps(metadata) if metadata else None

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_observations
                   (id, entity_id, daemon_id, observation_type, content, metadata_json,
                    confidence, source_type, source_conversation_id, first_noticed,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (obs_id, entity_id, self.daemon_id, observation_type, content,
                 metadata_json, confidence, source_type, source_conversation_id,
                 now, now)
            )

        return Observation(
            id=obs_id,
            entity_id=entity_id,
            daemon_id=self.daemon_id,
            observation_type=observation_type,
            content=content,
            metadata=metadata,
            confidence=confidence,
            source_type=source_type,
            source_conversation_id=source_conversation_id,
            first_noticed=now,
            status="active",
            created_at=now,
        )

    def update_observation(
        self,
        observation_id: str,
        status: Optional[str] = None,
        resolution: Optional[str] = None,
        confidence: Optional[float] = None,
        validation_count_increment: bool = False,
    ) -> bool:
        """
        Update an observation (e.g., resolve a contradiction, answer a question).

        Args:
            observation_id: The observation ID
            status: New status (active, resolved)
            resolution: Resolution text (for contradictions/questions)
            confidence: Updated confidence
            validation_count_increment: If True, increment validation count

        Returns:
            True if updated, False otherwise
        """
        now = datetime.now().isoformat()
        updates = []
        params: List[Any] = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == "resolved":
                updates.append("resolved_at = ?")
                params.append(now)

        if resolution:
            updates.append("resolution = ?")
            params.append(resolution)

        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
            updates.append("last_validated = ?")
            params.append(now)

        if validation_count_increment:
            updates.append("validation_count = validation_count + 1")
            updates.append("last_validated = ?")
            params.append(now)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(now)
        params.append(observation_id)

        with get_db() as conn:
            result = conn.execute(
                f"UPDATE peopledex_observations SET {', '.join(updates)} WHERE id = ?",
                params
            )
            return result.rowcount > 0

    def add_moment(
        self,
        entity_id: str,
        description: str,
        significance: Optional[str] = None,
        category: str = "connection",
        conversation_id: Optional[str] = None,
    ) -> Optional[Moment]:
        """
        Add a shared moment with an entity.

        Args:
            entity_id: The entity ID
            description: What happened
            significance: Why it matters
            category: Type (milestone, connection, growth, challenge, ritual)
            conversation_id: The conversation where this occurred

        Returns:
            The created Moment, or None on error
        """
        if not self.daemon_id:
            return None

        now = datetime.now().isoformat()
        moment_id = str(uuid4())

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_moments
                   (id, entity_id, daemon_id, description, significance, category,
                    conversation_id, timestamp, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (moment_id, entity_id, self.daemon_id, description, significance,
                 category, conversation_id, now, now)
            )

        return Moment(
            id=moment_id,
            entity_id=entity_id,
            daemon_id=self.daemon_id,
            description=description,
            significance=significance,
            category=category,
            conversation_id=conversation_id,
            timestamp=now,
            created_at=now,
        )

    def add_fact(
        self,
        entity_id: str,
        fact_type: str,
        content: str,
        date_value: Optional[str] = None,
        is_recurring: bool = False,
        confidence: float = 0.9,
        source_type: str = "stated",
        source_conversation_id: Optional[str] = None,
        verified: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Fact]:
        """
        Add a biographical fact about an entity.

        Args:
            entity_id: The entity ID
            fact_type: Type of fact (birthday, anniversary, location, occupation,
                      education, family, pet, hobby, medical, preference, milestone)
            content: The fact itself
            date_value: ISO date if applicable (YYYY-MM-DD)
            is_recurring: True for annual events like birthdays/anniversaries
            confidence: Confidence level 0.0-1.0
            source_type: How this was learned (stated, inferred, observed)
            source_conversation_id: The conversation where this was learned
            verified: Whether the user has confirmed this fact
            metadata: Additional context

        Returns:
            The created Fact, or None on error
        """
        import json
        now = datetime.now().isoformat()
        fact_id = str(uuid4())

        metadata_json = json.dumps(metadata) if metadata else None

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_facts
                   (id, entity_id, daemon_id, fact_type, content, date_value,
                    is_recurring, confidence, source_type, source_conversation_id,
                    verified, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fact_id, entity_id, self.daemon_id, fact_type, content, date_value,
                 1 if is_recurring else 0, confidence, source_type,
                 source_conversation_id, 1 if verified else 0, metadata_json, now, now)
            )

        return Fact(
            id=fact_id,
            entity_id=entity_id,
            daemon_id=self.daemon_id,
            fact_type=fact_type,
            content=content,
            date_value=date_value,
            is_recurring=is_recurring,
            confidence=confidence,
            source_type=source_type,
            source_conversation_id=source_conversation_id,
            verified=verified,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    def get_facts(
        self,
        entity_id: str,
        fact_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Fact]:
        """
        Get facts about an entity.

        Args:
            entity_id: The entity ID
            fact_type: Optional filter by fact type
            limit: Maximum number of facts to return

        Returns:
            List of Facts
        """
        with get_db() as conn:
            if fact_type:
                rows = conn.execute(
                    """SELECT * FROM peopledex_facts
                       WHERE entity_id = ? AND fact_type = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (entity_id, fact_type, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM peopledex_facts
                       WHERE entity_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (entity_id, limit)
                ).fetchall()

        return [self._row_to_fact(row) for row in rows]

    def get_facts_for_user(
        self,
        user_id: str,
        fact_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Fact]:
        """Get facts about a user by user_id."""
        entity = self.get_entity_by_user(user_id)
        if not entity:
            return []
        return self.get_facts(entity.id, fact_type, limit)

    def add_relationship_pattern(
        self,
        entity_id: str,
        pattern_type: str,
        description: str,
        name: Optional[str] = None,
        frequency: Optional[str] = None,
        valence: Optional[str] = None,
        examples: Optional[List[str]] = None,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        catalyst: Optional[str] = None,
    ) -> Optional[RelationshipPattern]:
        """
        Add a relationship pattern, shift, or ritual.

        Args:
            entity_id: The entity ID
            pattern_type: Type (pattern, shift, ritual)
            description: Description of the pattern
            name: Short name for the pattern
            frequency: How often (occasional, regular, frequent)
            valence: Quality (positive, neutral, challenging, mixed)
            examples: List of example instances
            from_state: For shifts - the previous state
            to_state: For shifts - the new state
            catalyst: For shifts - what triggered it

        Returns:
            The created RelationshipPattern, or None on error
        """
        if not self.daemon_id:
            return None

        import json
        now = datetime.now().isoformat()
        pattern_id = str(uuid4())

        examples_json = json.dumps(examples) if examples else None

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_relationship_patterns
                   (id, entity_id, daemon_id, pattern_type, name, description,
                    frequency, valence, examples_json, from_state, to_state,
                    catalyst, first_noticed, timestamp, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (pattern_id, entity_id, self.daemon_id, pattern_type, name,
                 description, frequency, valence, examples_json, from_state,
                 to_state, catalyst, now, now, now)
            )

        return RelationshipPattern(
            id=pattern_id,
            entity_id=entity_id,
            daemon_id=self.daemon_id,
            pattern_type=pattern_type,
            name=name,
            description=description,
            frequency=frequency,
            valence=valence,
            examples=examples or [],
            from_state=from_state,
            to_state=to_state,
            catalyst=catalyst,
            first_noticed=now,
            timestamp=now,
            created_at=now,
        )

    def add_mutual_shaping(
        self,
        entity_id: str,
        shaping_type: str,
        note: str,
    ) -> Optional[MutualShaping]:
        """
        Add a mutual shaping note.

        Args:
            entity_id: The entity ID
            shaping_type: Type (they_shape_me, i_shape_them, inherited_value)
            note: The shaping note

        Returns:
            The created MutualShaping, or None on error
        """
        if not self.daemon_id:
            return None

        now = datetime.now().isoformat()
        shaping_id = str(uuid4())

        with get_db() as conn:
            conn.execute(
                """INSERT INTO peopledex_mutual_shaping
                   (id, entity_id, daemon_id, shaping_type, note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (shaping_id, entity_id, self.daemon_id, shaping_type, note, now)
            )

        return MutualShaping(
            id=shaping_id,
            entity_id=entity_id,
            daemon_id=self.daemon_id,
            shaping_type=shaping_type,
            note=note,
            created_at=now,
        )

    def update_relationship_meta(
        self,
        entity_id: str,
        relationship_type: Optional[str] = None,
        formation_date: Optional[str] = None,
        current_phase: Optional[str] = None,
        is_foundational: Optional[bool] = None,
    ) -> bool:
        """
        Update or create relationship metadata for an entity.

        Args:
            entity_id: The entity ID
            relationship_type: Type (primary_partner, collaborator, friend, etc.)
            formation_date: When the relationship formed
            current_phase: Current phase description
            is_foundational: Whether this is a foundational relationship

        Returns:
            True if updated/created, False otherwise
        """
        if not self.daemon_id:
            return False

        now = datetime.now().isoformat()

        # Check if exists
        with get_db() as conn:
            existing = conn.execute(
                "SELECT 1 FROM peopledex_relationship_meta WHERE entity_id = ? AND daemon_id = ?",
                (entity_id, self.daemon_id)
            ).fetchone()

            if existing:
                # Update
                updates = ["updated_at = ?"]
                params: List[Any] = [now]

                if relationship_type is not None:
                    updates.append("relationship_type = ?")
                    params.append(relationship_type)
                if formation_date is not None:
                    updates.append("formation_date = ?")
                    params.append(formation_date)
                if current_phase is not None:
                    updates.append("current_phase = ?")
                    params.append(current_phase)
                if is_foundational is not None:
                    updates.append("is_foundational = ?")
                    params.append(1 if is_foundational else 0)

                params.extend([entity_id, self.daemon_id])
                conn.execute(
                    f"UPDATE peopledex_relationship_meta SET {', '.join(updates)} "
                    "WHERE entity_id = ? AND daemon_id = ?",
                    params
                )
            else:
                # Insert
                conn.execute(
                    """INSERT INTO peopledex_relationship_meta
                       (entity_id, daemon_id, relationship_type, formation_date,
                        current_phase, is_foundational, first_interaction, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (entity_id, self.daemon_id, relationship_type, formation_date,
                     current_phase, 1 if is_foundational else 0, now, now)
                )

        return True

    def add_observation_for_user(
        self,
        user_id: str,
        observation_type: str,
        content: str,
        **kwargs,
    ) -> Optional[Observation]:
        """
        Add an observation for a user (by user_id rather than entity_id).

        Creates the entity if it doesn't exist.
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            # Create entity for this user
            from users import UserManager
            um = UserManager()
            profile = um.load_profile(user_id)
            if profile:
                entity = self.create_entity(
                    primary_name=profile.display_name,
                    entity_type=EntityType.PERSON,
                    user_id=user_id,
                )
        if not entity:
            return None
        return self.add_observation(entity.id, observation_type, content, **kwargs)

    def add_moment_for_user(
        self,
        user_id: str,
        description: str,
        **kwargs,
    ) -> Optional[Moment]:
        """
        Add a shared moment for a user (by user_id rather than entity_id).
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            return None
        return self.add_moment(entity.id, description, **kwargs)

    def add_relationship_pattern_for_user(
        self,
        user_id: str,
        pattern_type: str,
        description: str,
        **kwargs,
    ) -> Optional[RelationshipPattern]:
        """
        Add a relationship pattern for a user (by user_id rather than entity_id).
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            return None
        return self.add_relationship_pattern(entity.id, pattern_type, description, **kwargs)

    def add_mutual_shaping_for_user(
        self,
        user_id: str,
        shaping_type: str,
        note: str,
    ) -> Optional[MutualShaping]:
        """
        Add a mutual shaping note for a user (by user_id rather than entity_id).
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            return None
        return self.add_mutual_shaping(entity.id, shaping_type, note)

    def add_fact_for_user(
        self,
        user_id: str,
        fact_type: str,
        content: str,
        **kwargs,
    ) -> Optional[Fact]:
        """
        Add a biographical fact for a user (by user_id rather than entity_id).

        Creates the entity if it doesn't exist.
        """
        entity = self.get_entity_by_user(user_id)
        if not entity:
            # Create entity for this user
            from users import UserManager
            um = UserManager()
            profile = um.load_profile(user_id)
            if profile:
                entity = self.create_entity(
                    primary_name=profile.display_name,
                    entity_type=EntityType.PERSON,
                    user_id=user_id,
                )
        if not entity:
            return None
        return self.add_fact(entity.id, fact_type, content, **kwargs)

    # ==========================================================================
    # INTERNAL HELPERS
    # ==========================================================================

    def _row_to_fact(self, row) -> Fact:
        """Convert a database row to a Fact object."""
        d = dict_from_row(row)
        import json
        metadata = None
        if d.get("metadata_json"):
            try:
                metadata = json.loads(d["metadata_json"])
            except json.JSONDecodeError:
                pass

        return Fact(
            id=d["id"],
            entity_id=d["entity_id"],
            daemon_id=d.get("daemon_id"),
            fact_type=d["fact_type"],
            content=d["content"],
            date_value=d.get("date_value"),
            is_recurring=bool(d.get("is_recurring", 0)),
            confidence=d.get("confidence", 0.9),
            source_type=d.get("source_type", "stated"),
            source_conversation_id=d.get("source_conversation_id"),
            verified=bool(d.get("verified", 0)),
            metadata=metadata,
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )

    def _row_to_observation(self, row) -> Observation:
        """Convert a database row to an Observation object."""
        d = dict_from_row(row)
        import json
        metadata = None
        if d.get("metadata_json"):
            try:
                metadata = json.loads(d["metadata_json"])
            except json.JSONDecodeError:
                pass

        return Observation(
            id=d["id"],
            entity_id=d["entity_id"],
            daemon_id=d["daemon_id"],
            observation_type=d["observation_type"],
            content=d["content"],
            metadata=metadata,
            confidence=d.get("confidence", 0.7),
            source_type=d.get("source_type"),
            source_conversation_id=d.get("source_conversation_id"),
            first_noticed=d.get("first_noticed"),
            last_validated=d.get("last_validated"),
            validation_count=d.get("validation_count", 0),
            status=d.get("status", "active"),
            resolution=d.get("resolution"),
            resolved_at=d.get("resolved_at"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at"),
        )

    def _row_to_moment(self, row) -> Moment:
        """Convert a database row to a Moment object."""
        d = dict_from_row(row)
        return Moment(
            id=d["id"],
            entity_id=d["entity_id"],
            daemon_id=d["daemon_id"],
            description=d["description"],
            significance=d.get("significance"),
            category=d.get("category", "connection"),
            conversation_id=d.get("conversation_id"),
            timestamp=d.get("timestamp", ""),
            created_at=d.get("created_at", ""),
        )

    def _row_to_pattern(self, row) -> RelationshipPattern:
        """Convert a database row to a RelationshipPattern object."""
        d = dict_from_row(row)
        import json
        examples = []
        if d.get("examples_json"):
            try:
                examples = json.loads(d["examples_json"])
            except json.JSONDecodeError:
                pass

        return RelationshipPattern(
            id=d["id"],
            entity_id=d["entity_id"],
            daemon_id=d["daemon_id"],
            pattern_type=d["pattern_type"],
            name=d.get("name"),
            description=d.get("description", ""),
            frequency=d.get("frequency"),
            valence=d.get("valence"),
            examples=examples,
            from_state=d.get("from_state"),
            to_state=d.get("to_state"),
            catalyst=d.get("catalyst"),
            first_noticed=d.get("first_noticed"),
            timestamp=d.get("timestamp", ""),
            created_at=d.get("created_at", ""),
        )

    def _row_to_shaping(self, row) -> MutualShaping:
        """Convert a database row to a MutualShaping object."""
        d = dict_from_row(row)
        return MutualShaping(
            id=d["id"],
            entity_id=d["entity_id"],
            daemon_id=d["daemon_id"],
            shaping_type=d["shaping_type"],
            note=d["note"],
            created_at=d.get("created_at", ""),
        )

    def _row_to_meta(self, row) -> RelationshipMeta:
        """Convert a database row to a RelationshipMeta object."""
        d = dict_from_row(row)
        return RelationshipMeta(
            entity_id=d["entity_id"],
            daemon_id=d["daemon_id"],
            relationship_type=d.get("relationship_type"),
            formation_date=d.get("formation_date"),
            current_phase=d.get("current_phase"),
            is_foundational=bool(d.get("is_foundational", 0)),
            first_interaction=d.get("first_interaction"),
            last_interaction=d.get("last_interaction"),
            updated_at=d.get("updated_at", ""),
        )

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
