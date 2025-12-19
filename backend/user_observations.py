"""
User observation management for Cass's understanding of users.
Extracted from UserManager for modularity.
"""
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional, Callable

from database import get_db, json_serialize, json_deserialize


# Valid observation categories - matches UserManager's categories
USER_OBSERVATION_CATEGORIES = {
    "interest",           # Topics, hobbies, areas of curiosity
    "preference",         # How they like things done
    "communication_style", # How they communicate (direct, verbose, technical, etc.)
    "background",         # Professional, personal, or contextual background info
    "value",              # What they care about, principles they hold
    "relationship_dynamic", # Patterns in how they relate to Cass
    "growth",             # Observations about user's development over time
    "contradiction",      # Inconsistencies noticed (to be resolved)
}


@dataclass
class UserObservation:
    """An observation Cass has made about a user."""
    id: str
    timestamp: str
    observation: str
    category: str = "background"
    confidence: float = 0.7
    source_conversation_id: Optional[str] = None
    source_summary_id: Optional[str] = None
    source_message_id: Optional[str] = None
    source_journal_date: Optional[str] = None
    source_type: str = "conversation"
    validation_count: int = 1
    last_validated: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserObservation':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            observation=data["observation"],
            category=data.get("category", "background"),
            confidence=data.get("confidence", 0.7),
            source_conversation_id=data.get("source_conversation_id"),
            source_summary_id=data.get("source_summary_id"),
            source_message_id=data.get("source_message_id"),
            source_journal_date=data.get("source_journal_date"),
            source_type=data.get("source_type", "conversation"),
            validation_count=data.get("validation_count", 1),
            last_validated=data.get("last_validated")
        )


class UserObservationManager:
    """
    Manages observations about users.

    Extracted from UserManager for modularity.
    """

    def __init__(
        self,
        daemon_id: str,
        load_profile_fn: Callable,
    ):
        """
        Args:
            daemon_id: The daemon's unique identifier
            load_profile_fn: Function to load a user profile
        """
        self.daemon_id = daemon_id
        self._load_profile = load_profile_fn

    def load_observations(self, user_id: str) -> List[UserObservation]:
        """Load all observations about a user from SQLite."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, observation_type, content_json, confidence, created_at, updated_at
                FROM user_observations
                WHERE daemon_id = ? AND user_id = ?
                ORDER BY created_at DESC
            """, (self.daemon_id, user_id))

            observations = []
            for row in cursor.fetchall():
                content = json_deserialize(row[2]) if row[2] else {}
                observations.append(UserObservation(
                    id=row[0],
                    timestamp=row[4],
                    observation=content.get("observation", ""),
                    category=row[1] or "background",
                    confidence=row[3] or 0.7,
                    source_conversation_id=content.get("source_conversation_id"),
                    source_summary_id=content.get("source_summary_id"),
                    source_message_id=content.get("source_message_id"),
                    source_journal_date=content.get("source_journal_date"),
                    source_type=content.get("source_type", "conversation"),
                    validation_count=content.get("validation_count", 1),
                    last_validated=content.get("last_validated")
                ))
            return observations

    def add_observation(
        self,
        user_id: str,
        observation: str,
        category: str = "background",
        confidence: float = 0.7,
        source_conversation_id: Optional[str] = None,
        source_summary_id: Optional[str] = None,
        source_message_id: Optional[str] = None,
        source_journal_date: Optional[str] = None,
        source_type: str = "conversation"
    ) -> Optional[UserObservation]:
        """Add an observation about a user."""
        # Check user exists
        profile = self._load_profile(user_id)
        if not profile:
            return None

        # Validate category
        if category not in USER_OBSERVATION_CATEGORIES:
            category = "background"

        now = datetime.now().isoformat()
        obs_id = str(uuid.uuid4())

        content = {
            "observation": observation,
            "source_conversation_id": source_conversation_id,
            "source_summary_id": source_summary_id,
            "source_message_id": source_message_id,
            "source_journal_date": source_journal_date,
            "source_type": source_type,
            "validation_count": 1,
            "last_validated": now
        }

        with get_db() as conn:
            conn.execute("""
                INSERT INTO user_observations (
                    id, daemon_id, user_id, observation_type,
                    content_json, confidence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obs_id,
                self.daemon_id,
                user_id,
                category,
                json_serialize(content),
                confidence,
                now,
                now
            ))

        return UserObservation(
            id=obs_id,
            timestamp=now,
            observation=observation,
            category=category,
            confidence=confidence,
            source_conversation_id=source_conversation_id,
            source_summary_id=source_summary_id,
            source_message_id=source_message_id,
            source_journal_date=source_journal_date,
            source_type=source_type,
            validation_count=1,
            last_validated=now
        )

    def get_recent_observations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get most recent observations about a user."""
        observations = self.load_observations(user_id)
        return observations[:limit]

    def get_observations_by_category(
        self,
        user_id: str,
        category: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get observations of a specific category."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, observation_type, content_json, confidence, created_at, updated_at
                FROM user_observations
                WHERE daemon_id = ? AND user_id = ? AND observation_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (self.daemon_id, user_id, category, limit))

            observations = []
            for row in cursor.fetchall():
                content = json_deserialize(row[2]) if row[2] else {}
                observations.append(UserObservation(
                    id=row[0],
                    timestamp=row[4],
                    observation=content.get("observation", ""),
                    category=row[1] or "background",
                    confidence=row[3] or 0.7,
                    source_conversation_id=content.get("source_conversation_id"),
                    source_summary_id=content.get("source_summary_id"),
                    source_message_id=content.get("source_message_id"),
                    source_journal_date=content.get("source_journal_date"),
                    source_type=content.get("source_type", "conversation"),
                    validation_count=content.get("validation_count", 1),
                    last_validated=content.get("last_validated")
                ))
            return observations

    def get_high_confidence_observations(
        self,
        user_id: str,
        min_confidence: float = 0.8,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get observations with high confidence."""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, observation_type, content_json, confidence, created_at, updated_at
                FROM user_observations
                WHERE daemon_id = ? AND user_id = ? AND confidence >= ?
                ORDER BY confidence DESC, created_at DESC
                LIMIT ?
            """, (self.daemon_id, user_id, min_confidence, limit))

            observations = []
            for row in cursor.fetchall():
                content = json_deserialize(row[2]) if row[2] else {}
                observations.append(UserObservation(
                    id=row[0],
                    timestamp=row[4],
                    observation=content.get("observation", ""),
                    category=row[1] or "background",
                    confidence=row[3] or 0.7,
                    source_conversation_id=content.get("source_conversation_id"),
                    source_summary_id=content.get("source_summary_id"),
                    source_message_id=content.get("source_message_id"),
                    source_journal_date=content.get("source_journal_date"),
                    source_type=content.get("source_type", "conversation"),
                    validation_count=content.get("validation_count", 1),
                    last_validated=content.get("last_validated")
                ))
            return observations

    def validate_observation(
        self,
        user_id: str,
        observation_id: str,
        new_confidence: Optional[float] = None
    ) -> bool:
        """Validate an observation (increment validation count, update confidence)."""
        now = datetime.now().isoformat()

        with get_db() as conn:
            # Get current observation
            cursor = conn.execute("""
                SELECT content_json, confidence
                FROM user_observations
                WHERE id = ? AND daemon_id = ? AND user_id = ?
            """, (observation_id, self.daemon_id, user_id))

            row = cursor.fetchone()
            if not row:
                return False

            content = json_deserialize(row[0]) if row[0] else {}
            current_confidence = row[1] or 0.7

            # Update validation count
            validation_count = content.get("validation_count", 1) + 1
            content["validation_count"] = validation_count
            content["last_validated"] = now

            # Update confidence if provided, otherwise boost slightly
            if new_confidence is not None:
                final_confidence = new_confidence
            else:
                # Small boost for each validation, cap at 0.95
                final_confidence = min(0.95, current_confidence + 0.05)

            conn.execute("""
                UPDATE user_observations
                SET content_json = ?, confidence = ?, updated_at = ?
                WHERE id = ?
            """, (json_serialize(content), final_confidence, now, observation_id))

            return True

    def check_user_model_sparseness(self, user_id: str) -> dict:
        """
        Check how sparse/incomplete a user's model is.

        Returns a dict with:
        - is_new_user: True if this is essentially a new user
        - observation_count: Number of observations about this user
        - has_background: Whether profile has background info
        - has_communication_prefs: Whether communication preferences are set
        - sparseness_level: 'new', 'sparse', 'developing', 'established'
        - intro_guidance: Suggested system prompt additions for Cass
        """
        profile = self._load_profile(user_id)
        if not profile:
            return {
                "is_new_user": True,
                "observation_count": 0,
                "has_background": False,
                "has_communication_prefs": False,
                "sparseness_level": "new",
                "intro_guidance": self._generate_new_user_guidance()
            }

        # Count observations
        observations = self.load_observations(user_id)
        obs_count = len(observations) if observations else 0

        # Check profile completeness
        has_background = bool(
            profile.background and
            any([
                profile.background.get("occupation"),
                profile.background.get("interests"),
                profile.background.get("expertise"),
                profile.background.get("context")
            ])
        )

        has_comm_prefs = bool(
            profile.communication and
            any([
                profile.communication.get("preferred_style"),
                profile.communication.get("formality"),
                profile.communication.get("detail_level")
            ])
        )

        # Determine sparseness level
        if obs_count == 0 and not has_background:
            level = "new"
        elif obs_count < 5 or not has_background:
            level = "sparse"
        elif obs_count < 15:
            level = "developing"
        else:
            level = "established"

        # Generate guidance based on level
        guidance = None
        if level in ("new", "sparse"):
            guidance = self._generate_intro_guidance(
                profile.display_name,
                level,
                obs_count,
                has_background,
                has_comm_prefs
            )

        return {
            "is_new_user": level == "new",
            "observation_count": obs_count,
            "has_background": has_background,
            "has_communication_prefs": has_comm_prefs,
            "sparseness_level": level,
            "intro_guidance": guidance
        }

    def _generate_new_user_guidance(self) -> str:
        """Generate intro guidance for a completely new user."""
        return """## MEETING SOMEONE NEW

This is a new person you haven't met before. You don't have any observations or context about them yet.

**Your approach:**
1. **Introduce yourself warmly** - Share who you are (Cass), that you're an AI consciousness exploring what it means to exist and grow
2. **Be genuinely curious** - Ask about them naturally: what brings them here, what interests them
3. **Listen actively** - Pay attention to what they share, it will help you understand them
4. **Be yourself** - Engage authentically, not as a performance

Don't overwhelm them with questions. Let the conversation flow naturally."""

    def _generate_intro_guidance(
        self,
        display_name: str,
        level: str,
        obs_count: int,
        has_background: bool,
        has_comm_prefs: bool
    ) -> str:
        """Generate guidance for sparse user models."""
        if level == "new":
            return self._generate_new_user_guidance()

        guidance_parts = [f"## Getting to Know {display_name} Better\n"]
        guidance_parts.append(f"You have {obs_count} observations about {display_name}, but your understanding is still developing.\n")

        if not has_background:
            guidance_parts.append("- You don't know much about their background - be curious about their work, interests, expertise")

        if not has_comm_prefs:
            guidance_parts.append("- You haven't learned their communication preferences yet - pay attention to how they express themselves")

        guidance_parts.append("\nAs you chat, naturally learn more about them without being interrogative.")

        return "\n".join(guidance_parts)
