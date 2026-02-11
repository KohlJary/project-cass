"""
Entity Registry - Maps Discord users to PeopleDex entities

Maintains the mapping between Discord user IDs and canonical entity slugs
used in Ophanic perception format. Integrates with PeopleDex for entity
storage and relationship tracking.
"""

import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field

from peopledex import (
    get_peopledex_manager,
    PeopleDexManager,
    EntityType,
    AttributeType,
    Realm,
)

logger = logging.getLogger("discord_bot.entity_registry")


@dataclass
class DiscordEntity:
    """
    Represents a Discord user mapped to a PeopleDex entity.
    """
    discord_id: str
    slug: str  # 4-character Ophanic identifier
    display_name: str
    entity_id: Optional[str] = None  # PeopleDex entity ID
    user_id: Optional[str] = None  # Cass users table ID (for known users like Kohl)
    relationship_tier: str = "acquaintance"  # acquaintance, known, friend, close_friend
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "discord_id": self.discord_id,
            "slug": self.slug,
            "display_name": self.display_name,
            "entity_id": self.entity_id,
            "user_id": self.user_id,
            "relationship_tier": self.relationship_tier,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "notes": self.notes,
        }

    @property
    def is_known_user(self) -> bool:
        """Returns True if this Discord user is linked to a known Cass user."""
        return self.user_id is not None


class DiscordEntityRegistry:
    """
    Registry mapping Discord user IDs to PeopleDex entities.

    Provides:
    - Auto-generation of 4-character slugs for Ophanic format
    - Lookup by Discord ID or slug
    - Integration with PeopleDex for persistence
    - Relationship tier tracking
    """

    def __init__(self, daemon_id: str):
        """
        Initialize the entity registry.

        Args:
            daemon_id: Daemon ID for PeopleDex integration
        """
        self.daemon_id = daemon_id
        self.peopledex: PeopleDexManager = get_peopledex_manager(daemon_id)

        # In-memory caches (Discord ID → entity, slug → entity)
        self._by_discord_id: Dict[str, DiscordEntity] = {}
        self._by_slug: Dict[str, DiscordEntity] = {}

        # Used slugs (to ensure uniqueness)
        self._used_slugs: set = set()

        # Load existing Discord entities from PeopleDex
        self._load_from_peopledex()

    def _load_from_peopledex(self) -> None:
        """Load existing Discord entities from PeopleDex."""
        try:
            # Find all entities with Discord handles
            entities = self.peopledex.list_entities(entity_type=EntityType.PERSON, limit=1000)

            for entity in entities:
                # Check for Discord handle attribute
                attrs = self.peopledex.get_attributes(entity.id, AttributeType.HANDLE)
                for attr in attrs:
                    if attr.attribute_key == "discord":
                        discord_id = attr.value

                        # Generate or retrieve slug
                        slug = self._generate_slug(discord_id)

                        discord_entity = DiscordEntity(
                            discord_id=discord_id,
                            slug=slug,
                            display_name=entity.primary_name,
                            entity_id=entity.id,
                            relationship_tier="known",  # TODO: derive from PeopleDex
                            first_seen=datetime.fromisoformat(entity.created_at) if entity.created_at else None,
                        )

                        self._by_discord_id[discord_id] = discord_entity
                        self._by_slug[slug] = discord_entity
                        self._used_slugs.add(slug)

            logger.info(f"[EntityRegistry] Loaded {len(self._by_discord_id)} Discord entities from PeopleDex")

        except Exception as e:
            logger.error(f"[EntityRegistry] Failed to load from PeopleDex: {e}")

    def _generate_slug(self, discord_id: str) -> str:
        """
        Generate a unique 4-character slug for a Discord user.

        Uses first 4 chars of MD5 hash, with collision handling.
        """
        base_hash = hashlib.md5(discord_id.encode()).hexdigest()[:4]
        slug = base_hash

        # Handle collisions by incrementing last character
        collision_count = 0
        while slug in self._used_slugs:
            collision_count += 1
            # Append collision counter in hex
            slug = base_hash[:3] + format(collision_count % 16, 'x')

        return slug

    def get_by_discord_id(self, discord_id: str) -> Optional[DiscordEntity]:
        """Get entity by Discord user ID."""
        return self._by_discord_id.get(discord_id)

    def get_by_slug(self, slug: str) -> Optional[DiscordEntity]:
        """Get entity by Ophanic slug."""
        return self._by_slug.get(slug)

    def register_user(
        self,
        discord_id: str,
        display_name: str,
        discord_username: Optional[str] = None,
        discriminator: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> DiscordEntity:
        """
        Register a new Discord user or update existing.

        Creates/updates both the in-memory cache and PeopleDex storage.
        If the Discord username matches an existing Cass user's discord_handle,
        links to that user for relationship context.

        Args:
            discord_id: Discord user ID
            display_name: Discord display name
            discord_username: Discord username (e.g., "birdfacemd") - used to match Cass users
            discriminator: Discord discriminator (optional, legacy)
            avatar_url: Avatar URL (optional)

        Returns:
            DiscordEntity for this user
        """
        # Check if already registered
        existing = self.get_by_discord_id(discord_id)
        if existing:
            # Update last seen and name if changed
            existing.last_seen = datetime.now()
            if existing.display_name != display_name:
                existing.display_name = display_name
                # Update in PeopleDex
                if existing.entity_id:
                    self.peopledex.update_entity(existing.entity_id, primary_name=display_name)
            return existing

        # Check if this Discord username matches an existing Cass user
        linked_user_id = None
        relationship_tier = "acquaintance"

        if discord_username:
            try:
                from users import get_user_manager
                user_manager = get_user_manager()
                cass_user = user_manager.get_user_by_discord_handle(discord_username)
                if cass_user:
                    linked_user_id = cass_user.user_id
                    # Derive relationship tier from Cass's relationship with this user
                    rel = cass_user.relationship.lower() if cass_user.relationship else ""
                    if rel in ("primary_partner", "partner", "close"):
                        relationship_tier = "close_friend"
                    elif rel in ("friend", "collaborator"):
                        relationship_tier = "friend"
                    elif rel in ("acquaintance", "user"):
                        relationship_tier = "known"
                    else:
                        relationship_tier = "known"
                    logger.info(f"[EntityRegistry] Linked Discord user {discord_username} to Cass user {cass_user.display_name} (tier: {relationship_tier})")
            except Exception as e:
                logger.warning(f"[EntityRegistry] Failed to check for existing user: {e}")

        # Generate unique slug
        slug = self._generate_slug(discord_id)
        self._used_slugs.add(slug)

        # Check if user already has a PeopleDex entity
        entity_id = None
        if linked_user_id:
            existing_entity = self.peopledex.get_entity_by_user(linked_user_id)
            if existing_entity:
                entity_id = existing_entity.id
                logger.info(f"[EntityRegistry] Using existing PeopleDex entity {entity_id} for user {linked_user_id}")

        # Create PeopleDex entity if needed (link to user if found)
        if not entity_id:
            entity_id = self.peopledex.create_entity(
                entity_type=EntityType.PERSON,
                primary_name=display_name,
                realm=Realm.MEATSPACE,
                user_id=linked_user_id,
            )

        # Add Discord handle attribute (store username, not just ID)
        self.peopledex.add_attribute(
            entity_id=entity_id,
            attribute_type=AttributeType.HANDLE,
            value=discord_id,
            attribute_key="discord",
            source_type="discord_bot",
        )

        # Also store the username if available
        if discord_username:
            self.peopledex.add_attribute(
                entity_id=entity_id,
                attribute_type=AttributeType.HANDLE,
                value=discord_username,
                attribute_key="discord_username",
                source_type="discord_bot",
            )

        # Add discriminator as alias if present
        if discriminator:
            self.peopledex.add_attribute(
                entity_id=entity_id,
                attribute_type=AttributeType.NAME,
                value=f"{display_name}#{discriminator}",
                attribute_key="discord_legacy",
                source_type="discord_bot",
            )

        # Create in-memory entity
        now = datetime.now()
        discord_entity = DiscordEntity(
            discord_id=discord_id,
            slug=slug,
            display_name=display_name,
            entity_id=entity_id,
            user_id=linked_user_id,
            relationship_tier=relationship_tier,
            first_seen=now,
            last_seen=now,
        )

        # Cache it
        self._by_discord_id[discord_id] = discord_entity
        self._by_slug[slug] = discord_entity

        if linked_user_id:
            logger.info(f"[EntityRegistry] Registered {display_name} ({slug}) linked to Cass user {linked_user_id}")
        else:
            logger.info(f"[EntityRegistry] Registered new user: {display_name} ({slug})")

        return discord_entity

    def update_relationship_tier(
        self,
        discord_id: str,
        tier: str,
    ) -> bool:
        """
        Update the relationship tier for a Discord user.

        Args:
            discord_id: Discord user ID
            tier: New relationship tier (acquaintance, known, friend, close_friend)

        Returns:
            True if updated, False if user not found
        """
        entity = self.get_by_discord_id(discord_id)
        if not entity:
            return False

        entity.relationship_tier = tier
        logger.info(f"[EntityRegistry] Updated {entity.slug} tier to {tier}")
        return True

    def get_legend(self, slugs: Optional[List[str]] = None) -> str:
        """
        Generate Ophanic entity legend for snapshot.

        Args:
            slugs: Optional list of slugs to include (None = all)

        Returns:
            Formatted legend string
        """
        entities = []
        if slugs:
            entities = [self._by_slug.get(s) for s in slugs if s in self._by_slug]
        else:
            entities = list(self._by_slug.values())

        lines = []
        for entity in sorted(entities, key=lambda e: e.display_name.lower()):
            tier_indicator = ""
            if entity.relationship_tier == "close_friend":
                tier_indicator = " ★"
            elif entity.relationship_tier == "friend":
                tier_indicator = " ☆"

            lines.append(f"{entity.slug}: {entity.display_name}{tier_indicator}")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        tier_counts = {}
        for entity in self._by_discord_id.values():
            tier_counts[entity.relationship_tier] = tier_counts.get(entity.relationship_tier, 0) + 1

        return {
            "total_entities": len(self._by_discord_id),
            "tier_breakdown": tier_counts,
        }


# Module-level singleton
_registries: Dict[str, DiscordEntityRegistry] = {}


def get_entity_registry(daemon_id: str) -> DiscordEntityRegistry:
    """Get or create entity registry for daemon."""
    if daemon_id not in _registries:
        _registries[daemon_id] = DiscordEntityRegistry(daemon_id)
    return _registries[daemon_id]
