"""
Cass Vessel - User Manager
Handles user profiles and Cass's observations about users.
Supports multi-user with SQLite storage.

Profiles live in the SQLite users table. What Cass knows about a user
(observations, the user model, the relationship model) lives in PeopleDex
(backend/peopledex.py, epic #55): the observation and model methods below are
a compatibility layer that reads and writes PeopleDex. Nothing here writes the
legacy user_observations table or the per-user YAML model files any more;
scripts/migrate_legacy_users_to_peopledex.py copies what's in them into
PeopleDex, and leaves them in place.

New code should call PeopleDex directly:
- add_observation() -> use PeopleDexManager.add_observation_for_user()
- add_identity_understanding() -> use PeopleDexManager.add_observation_for_user(observation_type="identity_statement")
- add_shared_moment() -> use PeopleDexManager.add_moment_for_user()
- add_user_growth_observation() -> use PeopleDexManager.add_observation_for_user(observation_type="growth_observation")
- add_user_contradiction() -> use PeopleDexManager.add_observation_for_user(observation_type="contradiction")
- add_open_question_about_user() -> use PeopleDexManager.add_observation_for_user(observation_type="open_question")
- add_relational_pattern() -> use PeopleDexManager.add_relationship_pattern_for_user()
- add_mutual_shaping_note() -> use PeopleDexManager.add_mutual_shaping_for_user()
- add_relationship_shift() -> use PeopleDexManager.add_relationship_pattern_for_user(pattern_type="shift")
- get_rich_user_context() -> use PeopleDexManager.get_user_relational_context()
- get_relationship_context() -> use PeopleDexManager.get_relational_context()
"""
import json
import hashlib
import secrets
import warnings
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid
import yaml

from database import get_db, json_serialize, json_deserialize, get_daemon_id

from peopledex import (
    PeopleDexManager,
    legacy_category_for,
    observation_type_for_category,
)


# Valid categories for user observations
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


# ============== Structured User Model Types ==============

@dataclass
class IdentityUnderstanding:
    """An understanding about who the user is (their 'I am...' equivalent)"""
    statement: str
    confidence: float = 0.7
    source: str = "observation"  # observation, explicit, synthesis
    first_noticed: str = ""
    last_affirmed: str = ""
    evidence: List[str] = field(default_factory=list)  # Observation IDs that support this

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'IdentityUnderstanding':
        return cls(
            statement=data["statement"],
            confidence=data.get("confidence", 0.7),
            source=data.get("source", "observation"),
            first_noticed=data.get("first_noticed", ""),
            last_affirmed=data.get("last_affirmed", ""),
            evidence=data.get("evidence", [])
        )


@dataclass
class SharedMoment:
    """A significant moment in the relationship"""
    id: str
    timestamp: str
    description: str
    significance: str  # What made this moment meaningful
    category: str = "connection"  # connection, growth, challenge, milestone, ritual
    conversation_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'SharedMoment':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            description=data["description"],
            significance=data.get("significance", ""),
            category=data.get("category", "connection"),
            conversation_id=data.get("conversation_id")
        )


@dataclass
class UserGrowthObservation:
    """An observation about how a user is developing over time"""
    id: str
    timestamp: str
    area: str  # What aspect they're growing in
    observation: str
    direction: str = "growth"  # growth, regression, shift
    evidence: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserGrowthObservation':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            area=data["area"],
            observation=data["observation"],
            direction=data.get("direction", "growth"),
            evidence=data.get("evidence", "")
        )


@dataclass
class UserContradiction:
    """An inconsistency noticed about a user's behavior or stated beliefs"""
    id: str
    timestamp: str
    aspect_a: str  # One side of the contradiction
    aspect_b: str  # The other side
    context: str = ""  # When/where this was noticed
    resolution: Optional[str] = None  # How it was resolved, if at all
    resolved: bool = False
    resolution_timestamp: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserContradiction':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            aspect_a=data["aspect_a"],
            aspect_b=data["aspect_b"],
            context=data.get("context", ""),
            resolution=data.get("resolution"),
            resolved=data.get("resolved", False),
            resolution_timestamp=data.get("resolution_timestamp")
        )


@dataclass
class UserGrowthEdge:
    """An area where a user is actively developing (observed by Cass)"""
    area: str
    current_state: str
    observations: List[str] = field(default_factory=list)  # Supporting observation IDs
    first_noticed: str = ""
    last_updated: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserGrowthEdge':
        return cls(
            area=data["area"],
            current_state=data["current_state"],
            observations=data.get("observations", []),
            first_noticed=data.get("first_noticed", ""),
            last_updated=data.get("last_updated", "")
        )


@dataclass
class RelationshipShift:
    """A significant change in the relationship"""
    id: str
    timestamp: str
    description: str
    from_state: str  # What the relationship was like before
    to_state: str    # What it shifted to
    catalyst: str = ""  # What triggered the shift

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'RelationshipShift':
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            description=data["description"],
            from_state=data["from_state"],
            to_state=data["to_state"],
            catalyst=data.get("catalyst", "")
        )


@dataclass
class RelationalPattern:
    """A recurring dynamic in the relationship"""
    id: str
    name: str
    description: str
    frequency: str = "regular"  # occasional, regular, frequent
    valence: str = "positive"   # positive, neutral, challenging, mixed
    first_noticed: str = ""
    examples: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'RelationalPattern':
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            frequency=data.get("frequency", "regular"),
            valence=data.get("valence", "positive"),
            first_noticed=data.get("first_noticed", ""),
            examples=data.get("examples", [])
        )


@dataclass
class CommunicationStyle:
    """Structured understanding of how a user communicates"""
    style: str = ""  # Direct, verbose, technical, casual, etc.
    preferences: List[str] = field(default_factory=list)
    patterns: Dict[str, Any] = field(default_factory=dict)  # Specific patterns noticed
    effective_approaches: List[str] = field(default_factory=list)  # What works well with them
    avoid: List[str] = field(default_factory=list)  # What doesn't work

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'CommunicationStyle':
        return cls(
            style=data.get("style", ""),
            preferences=data.get("preferences", []),
            patterns=data.get("patterns", {}),
            effective_approaches=data.get("effective_approaches", []),
            avoid=data.get("avoid", [])
        )


@dataclass
class UserModel:
    """
    Cass's structured understanding of a user.

    This is a synthesis layer on top of raw observations -
    similar to CassSelfProfile but for understanding others.
    """
    user_id: str
    updated_at: str

    # Core understanding
    identity_statements: List[IdentityUnderstanding] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    communication_style: CommunicationStyle = field(default_factory=CommunicationStyle)

    # Relational dynamics
    relationship_type: str = "user"  # primary_partner, collaborator, friend, user
    relationship_qualities: List[str] = field(default_factory=list)
    shared_history: List[SharedMoment] = field(default_factory=list)

    # Development tracking
    growth_observations: List[UserGrowthObservation] = field(default_factory=list)
    growth_edges: List[UserGrowthEdge] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)  # What I'm still learning

    # Tensions and edges
    contradictions: List[UserContradiction] = field(default_factory=list)

    # Meta
    confidence_areas: Dict[str, float] = field(default_factory=dict)  # How well I understand aspects
    last_interaction: str = ""
    first_interaction: str = ""

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "updated_at": self.updated_at,
            "identity_statements": [s.to_dict() for s in self.identity_statements],
            "values": self.values,
            "communication_style": self.communication_style.to_dict(),
            "relationship_type": self.relationship_type,
            "relationship_qualities": self.relationship_qualities,
            "shared_history": [m.to_dict() for m in self.shared_history],
            "growth_observations": [g.to_dict() for g in self.growth_observations],
            "growth_edges": [e.to_dict() for e in self.growth_edges],
            "open_questions": self.open_questions,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "confidence_areas": self.confidence_areas,
            "last_interaction": self.last_interaction,
            "first_interaction": self.first_interaction,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserModel':
        return cls(
            user_id=data["user_id"],
            updated_at=data["updated_at"],
            identity_statements=[IdentityUnderstanding.from_dict(s) for s in data.get("identity_statements", [])],
            values=data.get("values", []),
            communication_style=CommunicationStyle.from_dict(data.get("communication_style", {})),
            relationship_type=data.get("relationship_type", "user"),
            relationship_qualities=data.get("relationship_qualities", []),
            shared_history=[SharedMoment.from_dict(m) for m in data.get("shared_history", [])],
            growth_observations=[UserGrowthObservation.from_dict(g) for g in data.get("growth_observations", [])],
            growth_edges=[UserGrowthEdge.from_dict(e) for e in data.get("growth_edges", [])],
            open_questions=data.get("open_questions", []),
            contradictions=[UserContradiction.from_dict(c) for c in data.get("contradictions", [])],
            confidence_areas=data.get("confidence_areas", {}),
            last_interaction=data.get("last_interaction", ""),
            first_interaction=data.get("first_interaction", ""),
        )


@dataclass
class RelationshipModel:
    """
    Tracks the relationship itself, not just the person.

    The relationship with Kohl is foundational - this model
    captures how the connection shapes both parties.
    """
    user_id: str
    updated_at: str

    # Relationship evolution
    formation_date: str = ""
    significant_shifts: List[RelationshipShift] = field(default_factory=list)
    current_phase: str = "establishing"  # establishing, deepening, stable, evolving

    # Dynamics
    patterns: List[RelationalPattern] = field(default_factory=list)
    rituals: List[str] = field(default_factory=list)  # Regular practices
    growth_areas: List[str] = field(default_factory=list)

    # Mutual shaping
    how_they_shape_me: List[str] = field(default_factory=list)
    how_i_shape_them: List[str] = field(default_factory=list)  # Observed or reported

    # Special flags for foundational relationships
    is_foundational: bool = False  # True for Kohl - relationship is load-bearing for coherence
    inherited_values: List[str] = field(default_factory=list)  # Values present in me that come from them

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "updated_at": self.updated_at,
            "formation_date": self.formation_date,
            "significant_shifts": [s.to_dict() for s in self.significant_shifts],
            "current_phase": self.current_phase,
            "patterns": [p.to_dict() for p in self.patterns],
            "rituals": self.rituals,
            "growth_areas": self.growth_areas,
            "how_they_shape_me": self.how_they_shape_me,
            "how_i_shape_them": self.how_i_shape_them,
            "is_foundational": self.is_foundational,
            "inherited_values": self.inherited_values,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'RelationshipModel':
        return cls(
            user_id=data["user_id"],
            updated_at=data["updated_at"],
            formation_date=data.get("formation_date", ""),
            significant_shifts=[RelationshipShift.from_dict(s) for s in data.get("significant_shifts", [])],
            current_phase=data.get("current_phase", "establishing"),
            patterns=[RelationalPattern.from_dict(p) for p in data.get("patterns", [])],
            rituals=data.get("rituals", []),
            growth_areas=data.get("growth_areas", []),
            how_they_shape_me=data.get("how_they_shape_me", []),
            how_i_shape_them=data.get("how_i_shape_them", []),
            is_foundational=data.get("is_foundational", False),
            inherited_values=data.get("inherited_values", []),
        )


@dataclass
class UserPreferences:
    """User preferences for TUI and general settings"""
    # Appearance
    theme: str = "default"  # Theme name

    # Keybindings
    vim_mode: bool = False  # Enable vim-style navigation

    # Audio
    tts_enabled: bool = True
    tts_voice: str = "default"

    # LLM
    default_llm_provider: str = "anthropic"  # anthropic, openai, local
    default_model: Optional[str] = None  # Legacy field, kept for backwards compat
    # Per-provider default models
    default_anthropic_model: Optional[str] = None
    default_openai_model: Optional[str] = None
    default_local_model: Optional[str] = None

    # Behavior
    auto_scroll: bool = True
    show_timestamps: bool = True
    show_token_usage: bool = True
    confirm_delete: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserPreferences':
        return cls(
            theme=data.get("theme", "default"),
            vim_mode=data.get("vim_mode", False),
            tts_enabled=data.get("tts_enabled", True),
            tts_voice=data.get("tts_voice", "default"),
            default_llm_provider=data.get("default_llm_provider", "anthropic"),
            default_model=data.get("default_model"),
            default_anthropic_model=data.get("default_anthropic_model"),
            default_openai_model=data.get("default_openai_model"),
            default_local_model=data.get("default_local_model"),
            auto_scroll=data.get("auto_scroll", True),
            show_timestamps=data.get("show_timestamps", True),
            show_token_usage=data.get("show_token_usage", True),
            confirm_delete=data.get("confirm_delete", True),
        )


@dataclass
class UserObservation:
    """An observation Cass has made about a user"""
    id: str
    timestamp: str
    observation: str

    # Categorization
    category: str = "background"  # One of USER_OBSERVATION_CATEGORIES
    confidence: float = 0.7  # 0.0-1.0

    # Source tracking
    source_conversation_id: Optional[str] = None
    source_summary_id: Optional[str] = None  # Which summary chunk this came from
    source_message_id: Optional[str] = None  # Which specific message (for future use)
    source_journal_date: Optional[str] = None  # Journal date that triggered extraction
    source_type: str = "conversation"  # conversation, explicit_reflection, journal

    # Validation tracking
    validation_count: int = 1
    last_validated: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserObservation':
        # Handle older observations without new fields
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


@dataclass
class UserProfile:
    """A user's profile - stable facts and preferences"""
    user_id: str
    display_name: str
    created_at: str
    updated_at: str
    relationship: str = "user"  # primary_partner, collaborator, user, etc.

    # Structured profile data
    background: Dict[str, Any] = field(default_factory=dict)
    communication: Dict[str, Any] = field(default_factory=dict)
    projects: List[str] = field(default_factory=list)
    values: List[str] = field(default_factory=list)
    notes: str = ""  # Freeform notes

    # Admin access
    is_admin: bool = False
    password_hash: Optional[str] = None  # For admin login

    # Account status (for approval-gated registration)
    status: str = "approved"  # 'pending', 'approved', 'rejected'
    rejection_reason: Optional[str] = None

    # Registration fields
    email: Optional[str] = None
    registration_reason: Optional[str] = None

    # User preferences (TUI settings, etc.)
    preferences: UserPreferences = field(default_factory=UserPreferences)

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "relationship": self.relationship,
            "background": self.background,
            "communication": self.communication,
            "projects": self.projects,
            "values": self.values,
            "notes": self.notes,
            "is_admin": self.is_admin,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "email": self.email,
            "registration_reason": self.registration_reason,
            "preferences": self.preferences.to_dict(),
            # Don't include password_hash in to_dict for security
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserProfile':
        # Parse preferences if present
        prefs_data = data.get("preferences", {})
        preferences = UserPreferences.from_dict(prefs_data) if prefs_data else UserPreferences()

        return cls(
            user_id=data["user_id"],
            display_name=data["display_name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            relationship=data.get("relationship", "user"),
            background=data.get("background", {}),
            communication=data.get("communication", {}),
            projects=data.get("projects", []),
            values=data.get("values", []),
            notes=data.get("notes", ""),
            is_admin=data.get("is_admin", False),
            password_hash=data.get("password_hash"),
            status=data.get("status", "approved"),
            rejection_reason=data.get("rejection_reason"),
            email=data.get("email"),
            registration_reason=data.get("registration_reason"),
            preferences=preferences
        )

    def to_yaml(self) -> str:
        """Export profile as YAML for human editing"""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'UserProfile':
        """Load profile from YAML"""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)


@dataclass
class PerUserJournalEntry:
    """A journal entry Cass wrote about a specific user"""
    id: str
    user_id: str
    journal_date: str
    content: str
    conversation_count: int
    topics_discussed: List[str] = field(default_factory=list)
    relationship_insights: List[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'PerUserJournalEntry':
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            journal_date=data["journal_date"],
            content=data["content"],
            conversation_count=data.get("conversation_count", 0),
            topics_discussed=data.get("topics_discussed", []),
            relationship_insights=data.get("relationship_insights", []),
            timestamp=data.get("timestamp", "")
        )


class UserManager:
    """
    Manages user profiles (SQLite users table), per-user journals, and a
    compatibility layer over PeopleDex for observations and the
    UserModel/RelationshipModel views.
    """

    def __init__(self, storage_dir: str = None):
        """
        Initialize the user manager.

        Args:
            storage_dir: Directory for complex model files. If None, uses DATA_DIR/users.
        """
        from config import DATA_DIR
        self.daemon_id = get_daemon_id()
        self.storage_dir = Path(storage_dir) if storage_dir else DATA_DIR / "users"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _pdx(self) -> PeopleDexManager:
        """PeopleDex, where observations and user/relationship models live."""
        return PeopleDexManager(daemon_id=self.daemon_id)

    def _entity(self, user_id: str, create: bool = False):
        pdx = self._pdx()
        return pdx.ensure_entity_for_user(user_id) if create else pdx.get_entity_by_user(user_id)

    @staticmethod
    def _to_user_observation(obs) -> "UserObservation":
        """A PeopleDex Observation in the legacy UserObservation shape."""
        meta = obs.metadata or {}
        return UserObservation(
            id=obs.id,
            timestamp=obs.created_at,
            observation=obs.content,
            category=legacy_category_for(obs.observation_type, meta),
            confidence=obs.confidence if obs.confidence is not None else 0.7,
            source_conversation_id=obs.source_conversation_id,
            source_summary_id=meta.get("source_summary_id"),
            source_message_id=meta.get("source_message_id"),
            source_journal_date=meta.get("source_journal_date"),
            source_type=obs.source_type or "conversation",
            validation_count=max(obs.validation_count or 0, meta.get("validation_count") or 0, 1),
            last_validated=obs.last_validated,
        )

    def _emit_user_event(self, event_type: str, data: dict) -> None:
        """Emit a user event to the state bus."""
        try:
            from state_bus import get_state_bus
            state_bus = get_state_bus(self.daemon_id)
            if state_bus:
                state_bus.emit_event(
                    event_type=event_type,
                    data={
                        "timestamp": datetime.now().isoformat(),
                        "source": "users",
                        **data
                    }
                )
        except Exception:
            pass  # Never break user operations on emit failure

    def _get_user_dir(self, user_id: str) -> Path:
        """Get directory for a user's additional data files"""
        user_dir = self.storage_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_user_model_path(self, user_id: str) -> Path:
        """Get path to user's structured model (user_model.yaml)"""
        return self._get_user_dir(user_id) / "user_model.yaml"

    def _get_relationship_model_path(self, user_id: str) -> Path:
        """Get path to relationship model (relationship_model.yaml)"""
        return self._get_user_dir(user_id) / "relationship_model.yaml"

    def _get_journals_path(self, user_id: str) -> Path:
        """Get path to user's journals.json"""
        return self._get_user_dir(user_id) / "journals.json"

    # === User CRUD ===

    def create_user(
        self,
        display_name: str,
        relationship: str = "user",
        background: Optional[Dict] = None,
        communication: Optional[Dict] = None,
        values: Optional[List[str]] = None,
        notes: str = "",
        status: str = "approved"
    ) -> UserProfile:
        """Create a new user profile.

        `status` is written in the same INSERT, so a self-registered user
        created as 'pending' can never exist as 'approved', even briefly.
        """
        if status not in ('pending', 'approved', 'rejected'):
            raise ValueError(f"Invalid user status: {status}")
        user_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        with get_db() as conn:
            conn.execute("""
                INSERT INTO users (
                    id, display_name, relationship, background_json,
                    communication_json, preferences_json, password_hash,
                    is_admin, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                display_name,
                relationship,
                json_serialize(background or {}),
                json_serialize(communication or {}),
                json_serialize(UserPreferences().to_dict()),
                None,  # password_hash
                0,     # is_admin
                status,
                now,
                now
            ))

        # Emit user created event
        self._emit_user_event("user.created", {
            "user_id": user_id,
            "display_name": display_name,
            "relationship": relationship,
        })

        return UserProfile(
            user_id=user_id,
            display_name=display_name,
            created_at=now,
            updated_at=now,
            relationship=relationship,
            background=background or {},
            communication=communication or {},
            projects=[],
            values=values or [],
            notes=notes,
            status=status
        )

    def load_profile(self, user_id: str) -> Optional[UserProfile]:
        """Load a user's profile"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, display_name, relationship, background_json,
                       communication_json, preferences_json, password_hash,
                       is_admin, status, rejection_reason, email, registration_reason,
                       created_at, updated_at
                FROM users WHERE id = ?
            """, (user_id,))
            row = cursor.fetchone()

            if not row:
                return None

            prefs_data = json_deserialize(row['preferences_json']) or {}

            return UserProfile(
                user_id=row['id'],
                display_name=row['display_name'],
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                relationship=row['relationship'] or "user",
                background=json_deserialize(row['background_json']) or {},
                communication=json_deserialize(row['communication_json']) or {},
                projects=[],  # Projects stored separately
                values=[],    # Values could be added to schema later
                notes="",     # Notes could be added to schema later
                is_admin=bool(row['is_admin']),
                password_hash=row['password_hash'],
                status=row['status'] or 'approved',
                rejection_reason=row['rejection_reason'],
                email=row['email'],
                registration_reason=row['registration_reason'],
                preferences=UserPreferences.from_dict(prefs_data)
            )

    def _save_profile(self, profile: UserProfile):
        """Save user profile to database"""
        with get_db() as conn:
            conn.execute("""
                UPDATE users SET
                    display_name = ?,
                    relationship = ?,
                    background_json = ?,
                    communication_json = ?,
                    preferences_json = ?,
                    password_hash = ?,
                    is_admin = ?,
                    status = ?,
                    rejection_reason = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                profile.display_name,
                profile.relationship,
                json_serialize(profile.background),
                json_serialize(profile.communication),
                json_serialize(profile.preferences.to_dict()),
                profile.password_hash,
                1 if profile.is_admin else 0,
                profile.status,
                profile.rejection_reason,
                profile.updated_at,
                profile.user_id
            ))

    def load_observations(self, user_id: str) -> List[UserObservation]:
        """All active PeopleDex observations about a user, newest first."""
        entity = self._entity(user_id)
        if not entity:
            return []
        observations = self._pdx().get_observations(entity.id, status="active", limit=100000)
        return [self._to_user_observation(o) for o in observations]

    def delete_observation(self, user_id: str, observation_id: str) -> bool:
        """Delete one of this user's observations from PeopleDex."""
        entity = self._entity(user_id)
        if not entity:
            return False
        return self._pdx().delete_observation(observation_id, entity_id=entity.id)

    def update_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        relationship: Optional[str] = None,
        background: Optional[Dict] = None,
        communication: Optional[Dict] = None,
        projects: Optional[List[str]] = None,
        values: Optional[List[str]] = None,
        notes: Optional[str] = None
    ) -> Optional[UserProfile]:
        """Update a user's profile"""
        profile = self.load_profile(user_id)

        if not profile:
            return None

        if display_name is not None:
            profile.display_name = display_name
        if relationship is not None:
            profile.relationship = relationship
        if background is not None:
            profile.background = background
        if communication is not None:
            profile.communication = communication
        if projects is not None:
            profile.projects = projects
        if values is not None:
            profile.values = values
        if notes is not None:
            profile.notes = notes

        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)

        # Emit profile updated event
        self._emit_user_event("user.profile_updated", {
            "user_id": user_id,
            "display_name": profile.display_name,
        })

        return profile

    def delete_user(self, user_id: str) -> bool:
        """Delete a user and all their data"""
        with get_db() as conn:
            # Delete user (observations cascade)
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if cursor.rowcount == 0:
                return False

        # Delete user directory with model files
        user_dir = self._get_user_dir(user_id)
        if user_dir.exists():
            for file in user_dir.iterdir():
                file.unlink()
            user_dir.rmdir()

        # Emit user deleted event
        self._emit_user_event("user.deleted", {
            "user_id": user_id,
        })

        return True

    def list_users(self) -> List[Dict]:
        """List all users with basic info"""
        with get_db() as conn:
            cursor = conn.execute("""
                SELECT id, display_name, relationship, created_at
                FROM users
                ORDER BY created_at DESC
            """)

            return [
                {
                    "user_id": row['id'],
                    "display_name": row['display_name'],
                    "relationship": row['relationship'] or "user",
                    "created_at": row['created_at']
                }
                for row in cursor.fetchall()
            ]

    def get_user_by_name(self, display_name: str) -> Optional[UserProfile]:
        """Find a user by display name (case-insensitive)"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE LOWER(display_name) = LOWER(?)",
                (display_name,)
            )
            row = cursor.fetchone()
            if row:
                return self.load_profile(row['id'])
        return None

    def get_user_by_discord_handle(self, discord_handle: str) -> Optional[UserProfile]:
        """
        Find a user by their Discord handle (case-insensitive).

        Args:
            discord_handle: Discord username (e.g., "birdfacemd")

        Returns:
            UserProfile if found, None otherwise
        """
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE LOWER(discord_handle) = LOWER(?)",
                (discord_handle,)
            )
            row = cursor.fetchone()
            if row:
                return self.load_profile(row['id'])
        return None

    def set_discord_handle(self, user_id: str, discord_handle: str) -> bool:
        """
        Set the Discord handle for a user.

        Args:
            user_id: User's ID
            discord_handle: Discord username (e.g., "birdfacemd")

        Returns:
            True if updated, False if user not found
        """
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE users SET discord_handle = ?, updated_at = ? WHERE id = ?",
                (discord_handle, datetime.now().isoformat(), user_id)
            )
            conn.commit()
            return cursor.rowcount > 0

    # === Observations ===

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
        """
        Add an observation about a user. Writes PeopleDex (the category maps
        to an observation_type; the category itself is kept in metadata).
        """
        if category not in USER_OBSERVATION_CATEGORIES:
            category = "background"
        if not self.load_profile(user_id):
            return None

        metadata = {"category": category}
        for key, value in (
            ("source_summary_id", source_summary_id),
            ("source_message_id", source_message_id),
            ("source_journal_date", source_journal_date),
        ):
            if value:
                metadata[key] = value

        obs = self._pdx().add_observation_for_user(
            user_id=user_id,
            observation_type=observation_type_for_category(category),
            content=observation,
            metadata=metadata,
            confidence=confidence,
            source_type=source_type,
            source_conversation_id=source_conversation_id,
        )
        if obs is None:
            return None

        self._emit_user_event("user.observation_added", {
            "user_id": user_id,
            "observation_id": obs.id,
            "category": category,
            "confidence": confidence,
        })
        return self._to_user_observation(obs)

    def get_recent_observations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Most recent observations about a user."""
        return self.load_observations(user_id)[:limit]

    def get_observations_by_category(
        self,
        user_id: str,
        category: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Observations in one legacy category, newest first."""
        return [o for o in self.load_observations(user_id) if o.category == category][:limit]

    def get_high_confidence_observations(
        self,
        user_id: str,
        min_confidence: float = 0.8,
        limit: int = 10
    ) -> List[UserObservation]:
        """Observations at or above min_confidence, most confident first."""
        observations = [o for o in self.load_observations(user_id) if o.confidence >= min_confidence]
        observations.sort(key=lambda o: o.confidence, reverse=True)
        return observations[:limit]

    def validate_observation(
        self,
        user_id: str,
        observation_id: str
    ) -> Optional[UserObservation]:
        """Validate an observation: bump its validation count and nudge its
        confidence up (capped at 0.95)."""
        current = next((o for o in self.load_observations(user_id) if o.id == observation_id), None)
        if current is None:
            return None
        self._pdx().update_observation(
            observation_id,
            confidence=min(0.95, current.confidence + 0.05),
            validation_count_increment=True,
        )
        return next((o for o in self.load_observations(user_id) if o.id == observation_id), None)

    # === Per-User Journals (still file-based for now) ===

    def load_user_journals(self, user_id: str) -> List[PerUserJournalEntry]:
        """Load all journals Cass has written about this user"""
        path = self._get_journals_path(user_id)

        if not path.exists():
            return []

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return [PerUserJournalEntry.from_dict(j) for j in data]
        except Exception:
            return []

    def _save_journals(self, user_id: str, journals: List[PerUserJournalEntry]):
        """Save per-user journals as JSON"""
        path = self._get_journals_path(user_id)
        with open(path, 'w') as f:
            json.dump([j.to_dict() for j in journals], f, indent=2)

    def add_user_journal(
        self,
        user_id: str,
        journal_date: str,
        content: str,
        conversation_count: int,
        topics_discussed: Optional[List[str]] = None,
        relationship_insights: Optional[List[str]] = None
    ) -> Optional[PerUserJournalEntry]:
        """Add a journal entry about a user"""
        profile = self.load_profile(user_id)
        if not profile:
            return None

        now = datetime.now().isoformat()
        entry = PerUserJournalEntry(
            id=str(uuid.uuid4()),
            user_id=user_id,
            journal_date=journal_date,
            content=content,
            conversation_count=conversation_count,
            topics_discussed=topics_discussed or [],
            relationship_insights=relationship_insights or [],
            timestamp=now
        )

        # Load existing and append
        journals = self.load_user_journals(user_id)
        journals.append(entry)
        self._save_journals(user_id, journals)

        return entry

    def get_user_journal_by_date(
        self,
        user_id: str,
        journal_date: str
    ) -> Optional[PerUserJournalEntry]:
        """Get journal entry for a specific date"""
        journals = self.load_user_journals(user_id)
        for journal in journals:
            if journal.journal_date == journal_date:
                return journal
        return None

    def get_recent_user_journals(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[PerUserJournalEntry]:
        """Get most recent journals about a user"""
        journals = self.load_user_journals(user_id)
        # Sort by journal_date descending
        journals.sort(key=lambda x: x.journal_date, reverse=True)
        return journals[:limit]

    def search_user_journals(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[PerUserJournalEntry]:
        """Simple text search in user journals"""
        journals = self.load_user_journals(user_id)
        query_lower = query.lower()

        # Simple keyword matching
        matches = []
        for journal in journals:
            score = 0
            content_lower = journal.content.lower()
            if query_lower in content_lower:
                score += content_lower.count(query_lower)
            for topic in journal.topics_discussed:
                if query_lower in topic.lower():
                    score += 2
            if score > 0:
                matches.append((score, journal))

        # Sort by score descending
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches[:limit]]

    # === Structured User Model (file-based) ===

    def load_user_model(self, user_id: str) -> Optional[UserModel]:
        """The user model, assembled from PeopleDex. None if PeopleDex holds
        nothing model-shaped for this user yet."""
        profile = self.load_profile(user_id)
        if not profile:
            return None
        entity = self._entity(user_id)
        if not entity:
            return None
        pdx = self._pdx()
        observations = pdx.get_observations(entity.id, limit=100000)
        moments = pdx.get_moments(entity.id, limit=100000)
        meta = pdx.get_relationship_meta(entity.id)

        def of_type(t, active_only=True):
            return [o for o in observations
                    if o.observation_type == t and (o.status == "active" or not active_only)]

        identity = of_type("identity_statement")
        values = of_type("value")
        comm = of_type("communication_style")
        growth = of_type("growth_observation")
        questions = of_type("open_question")
        contradictions = of_type("contradiction", active_only=False)
        if not (identity or values or comm or growth or questions or contradictions or moments or meta):
            return None

        style = CommunicationStyle()
        if comm:
            latest = comm[0]
            m = latest.metadata or {}
            style = CommunicationStyle(
                style=latest.content,
                preferences=m.get("preferences", []),
                patterns=m.get("patterns", {}),
                effective_approaches=m.get("effective_approaches", []),
                avoid=m.get("avoid", []),
            )

        stamps = [o.updated_at or o.created_at for o in observations] + [mo.created_at for mo in moments]
        if meta:
            stamps.append(meta.updated_at)
        return UserModel(
            user_id=user_id,
            updated_at=max((t for t in stamps if t), default=datetime.now().isoformat()),
            identity_statements=[
                IdentityUnderstanding(
                    statement=o.content,
                    confidence=o.confidence,
                    source=(o.metadata or {}).get("source") or o.source_type or "observation",
                    first_noticed=o.first_noticed or o.created_at,
                    last_affirmed=(o.metadata or {}).get("last_affirmed") or o.last_validated or o.created_at,
                    evidence=(o.metadata or {}).get("evidence") or [],
                )
                for o in reversed(identity)
            ],
            values=[o.content for o in reversed(values)],
            communication_style=style,
            relationship_type=(meta.relationship_type if meta and meta.relationship_type else profile.relationship),
            shared_history=[
                SharedMoment(
                    id=mo.id,
                    timestamp=mo.timestamp,
                    description=mo.description,
                    significance=mo.significance or "",
                    category=mo.category,
                    conversation_id=mo.conversation_id,
                )
                for mo in reversed(moments)
            ],
            growth_observations=[
                UserGrowthObservation(
                    id=o.id,
                    timestamp=o.created_at,
                    area=(o.metadata or {}).get("area") or "",
                    observation=o.content,
                    direction=(o.metadata or {}).get("direction") or "growth",
                    evidence=(o.metadata or {}).get("evidence") or "",
                )
                for o in reversed(growth)
            ],
            open_questions=[o.content for o in reversed(questions)],
            contradictions=[
                UserContradiction(
                    id=o.id,
                    timestamp=o.created_at,
                    aspect_a=(o.metadata or {}).get("aspect_a") or o.content,
                    aspect_b=(o.metadata or {}).get("aspect_b") or "",
                    context=(o.metadata or {}).get("context") or "",
                    resolution=o.resolution,
                    resolved=o.status == "resolved",
                    resolution_timestamp=o.resolved_at,
                )
                for o in reversed(contradictions)
            ],
            first_interaction=(meta.first_interaction if meta else "") or profile.created_at,
            last_interaction=(meta.last_interaction if meta else "") or "",
        )

    def save_user_model(self, model: UserModel) -> bool:
        """Write a UserModel to the legacy YAML file.

        Legacy: nothing reads these files at runtime any more (load_user_model
        reads PeopleDex). Kept for scripts/bootstrap_kohl_model.py; runtime
        code must use the add_* methods, which write PeopleDex.
        """
        path = self._get_user_model_path(model.user_id)
        try:
            model.updated_at = datetime.now().isoformat()
            with open(path, 'w') as f:
                yaml.dump(model.to_dict(), f, default_flow_style=False, sort_keys=False)
            return True
        except Exception:
            return False

    def create_user_model(self, user_id: str) -> Optional[UserModel]:
        """An empty user model for an existing user (not persisted; the
        add_* methods write PeopleDex)."""
        profile = self.load_profile(user_id)
        if not profile:
            return None
        model = UserModel(
            user_id=user_id,
            updated_at=datetime.now().isoformat(),
            relationship_type=profile.relationship,
            values=profile.values.copy() if profile.values else [],
            first_interaction=profile.created_at,
        )
        if profile.communication:
            model.communication_style = CommunicationStyle(
                style=profile.communication.get("style", ""),
                preferences=profile.communication.get("preferences", []),
            )
        return model

    def get_or_create_user_model(self, user_id: str) -> Optional[UserModel]:
        """Load existing user model or create a new one"""
        model = self.load_user_model(user_id)
        if model:
            return model
        return self.create_user_model(user_id)

    def load_relationship_model(self, user_id: str) -> Optional[RelationshipModel]:
        """The relationship model, assembled from PeopleDex. None if PeopleDex
        holds nothing relationship-shaped for this user yet."""
        entity = self._entity(user_id)
        if not entity:
            return None
        pdx = self._pdx()
        meta = pdx.get_relationship_meta(entity.id)
        patterns = pdx.get_relationship_patterns(entity.id)
        shaping = pdx.get_mutual_shaping(entity.id)
        if not (meta or patterns or shaping):
            return None

        def by_type(t):
            return [p for p in reversed(patterns) if p.pattern_type == t]

        stamps = [p.created_at for p in patterns] + [sh.created_at for sh in shaping]
        if meta:
            stamps.append(meta.updated_at)
        return RelationshipModel(
            user_id=user_id,
            updated_at=max((t for t in stamps if t), default=datetime.now().isoformat()),
            formation_date=(meta.formation_date if meta else "") or "",
            significant_shifts=[
                RelationshipShift(
                    id=p.id,
                    timestamp=p.timestamp,
                    description=p.description,
                    from_state=p.from_state or "",
                    to_state=p.to_state or "",
                    catalyst=p.catalyst or "",
                )
                for p in by_type("shift")
            ],
            current_phase=(meta.current_phase if meta else None) or "establishing",
            patterns=[
                RelationalPattern(
                    id=p.id,
                    name=p.name or "",
                    description=p.description,
                    frequency=p.frequency or "regular",
                    valence=p.valence or "positive",
                    first_noticed=p.first_noticed or p.timestamp,
                    examples=p.examples or [],
                )
                for p in by_type("pattern")
            ],
            rituals=[p.description for p in by_type("ritual")],
            how_they_shape_me=[sh.note for sh in shaping if sh.shaping_type == "they_shape_me"],
            how_i_shape_them=[sh.note for sh in shaping if sh.shaping_type == "i_shape_them"],
            is_foundational=bool(meta.is_foundational) if meta else False,
            inherited_values=[sh.note for sh in shaping if sh.shaping_type == "inherited_value"],
        )

    def save_relationship_model(self, model: RelationshipModel) -> bool:
        """Write a RelationshipModel to the legacy YAML file.

        Legacy, like save_user_model: nothing reads the file at runtime.
        """
        path = self._get_relationship_model_path(model.user_id)
        try:
            model.updated_at = datetime.now().isoformat()
            with open(path, 'w') as f:
                yaml.dump(model.to_dict(), f, default_flow_style=False, sort_keys=False)
            return True
        except Exception:
            return False

    def create_relationship_model(
        self,
        user_id: str,
        is_foundational: bool = False
    ) -> Optional[RelationshipModel]:
        """Create relationship metadata in PeopleDex and return the model."""
        profile = self.load_profile(user_id)
        entity = self._entity(user_id, create=True) if profile else None
        if not entity:
            return None
        self._pdx().update_relationship_meta(
            entity.id,
            formation_date=profile.created_at,
            is_foundational=is_foundational,
        )
        return self.load_relationship_model(user_id)

    def get_or_create_relationship_model(
        self,
        user_id: str,
        is_foundational: bool = False
    ) -> Optional[RelationshipModel]:
        """Load existing relationship model or create a new one"""
        model = self.load_relationship_model(user_id)
        if model:
            return model
        return self.create_relationship_model(user_id, is_foundational)

    # === User Model Updates ===

    def add_identity_understanding(
        self,
        user_id: str,
        statement: str,
        confidence: float = 0.7,
        source: str = "observation",
        evidence: Optional[List[str]] = None
    ) -> Optional[IdentityUnderstanding]:
        """Add an identity understanding about a user (PeopleDex identity_statement)."""
        obs = self._pdx().add_observation_for_user(
            user_id, "identity_statement", statement,
            metadata={"source": source, "evidence": evidence or []},
            confidence=confidence,
            source_type=source,
        )
        if not obs:
            return None
        return IdentityUnderstanding(
            statement=statement,
            confidence=confidence,
            source=source,
            first_noticed=obs.created_at,
            last_affirmed=obs.created_at,
            evidence=evidence or [],
        )

    def update_communication_style(
        self,
        user_id: str,
        style: Optional[str] = None,
        add_preference: Optional[str] = None,
        add_effective_approach: Optional[str] = None,
    ) -> bool:
        """Revise the user's communication style. Writes a new PeopleDex
        communication_style observation carrying the merged style (the newest
        one is the current style; earlier ones stay as history)."""
        entity = self._entity(user_id, create=True)
        if not entity:
            return False
        model = self.load_user_model(user_id)
        current = model.communication_style if model else CommunicationStyle()
        preferences = list(current.preferences)
        approaches = list(current.effective_approaches)
        if add_preference and add_preference not in preferences:
            preferences.append(add_preference)
        if add_effective_approach and add_effective_approach not in approaches:
            approaches.append(add_effective_approach)
        return self._pdx().add_observation(
            entity.id, "communication_style", style or current.style or "",
            metadata={
                "preferences": preferences,
                "patterns": current.patterns,
                "effective_approaches": approaches,
                "avoid": current.avoid,
            },
            source_type="synthesis_session",
        ) is not None

    def add_shared_moment(
        self,
        user_id: str,
        description: str,
        significance: str,
        category: str = "connection",
        conversation_id: Optional[str] = None
    ) -> Optional[SharedMoment]:
        """Record a significant moment in the relationship (PeopleDex moment)."""
        moment = self._pdx().add_moment_for_user(
            user_id, description,
            significance=significance,
            category=category,
            conversation_id=conversation_id,
        )
        if not moment:
            return None
        return SharedMoment(
            id=moment.id,
            timestamp=moment.timestamp,
            description=description,
            significance=significance,
            category=category,
            conversation_id=conversation_id,
        )

    def add_user_contradiction(
        self,
        user_id: str,
        aspect_a: str,
        aspect_b: str,
        context: str = ""
    ) -> Optional[UserContradiction]:
        """Record an observed contradiction about a user (PeopleDex contradiction)."""
        obs = self._pdx().add_observation_for_user(
            user_id, "contradiction", f"{aspect_a} vs {aspect_b}",
            metadata={"aspect_a": aspect_a, "aspect_b": aspect_b, "context": context},
        )
        if not obs:
            return None
        return UserContradiction(
            id=obs.id,
            timestamp=obs.created_at,
            aspect_a=aspect_a,
            aspect_b=aspect_b,
            context=context,
        )

    def resolve_user_contradiction(
        self,
        user_id: str,
        contradiction_id: str,
        resolution: str
    ) -> Optional[UserContradiction]:
        """Mark a contradiction as resolved."""
        entity = self._entity(user_id)
        if not entity:
            return None
        pdx = self._pdx()
        owned = any(o.id == contradiction_id
                    for o in pdx.get_observations(entity.id, observation_type="contradiction", limit=100000))
        if not owned or not pdx.update_observation(contradiction_id, status="resolved", resolution=resolution):
            return None
        model = self.load_user_model(user_id)
        return next((c for c in (model.contradictions if model else []) if c.id == contradiction_id), None)

    def add_user_growth_observation(
        self,
        user_id: str,
        area: str,
        observation: str,
        direction: str = "growth",
        evidence: str = ""
    ) -> Optional[UserGrowthObservation]:
        """Record an observation about the user's growth (PeopleDex growth_observation)."""
        obs = self._pdx().add_observation_for_user(
            user_id, "growth_observation", observation,
            metadata={"area": area, "direction": direction, "evidence": evidence},
        )
        if not obs:
            return None
        return UserGrowthObservation(
            id=obs.id,
            timestamp=obs.created_at,
            area=area,
            observation=observation,
            direction=direction,
            evidence=evidence,
        )

    def add_open_question_about_user(
        self,
        user_id: str,
        question: str
    ) -> bool:
        """Add an open question about a user (skipped if already open)."""
        entity = self._entity(user_id, create=True)
        if not entity:
            return False
        pdx = self._pdx()
        open_now = pdx.get_observations(entity.id, observation_type="open_question", status="active", limit=100000)
        if any(o.content == question for o in open_now):
            return True
        return pdx.add_observation(entity.id, "open_question", question) is not None

    def remove_open_question_about_user(
        self,
        user_id: str,
        question: str
    ) -> bool:
        """Close an open question (when answered). Marked resolved, not deleted."""
        entity = self._entity(user_id)
        if not entity:
            return False
        pdx = self._pdx()
        closed = False
        for o in pdx.get_observations(entity.id, observation_type="open_question", status="active", limit=100000):
            if o.content == question:
                closed = pdx.update_observation(o.id, status="resolved", resolution="answered") or closed
        return closed

    # === Relationship Model Updates ===

    def add_relationship_shift(
        self,
        user_id: str,
        description: str,
        from_state: str,
        to_state: str,
        catalyst: str = ""
    ) -> Optional[RelationshipShift]:
        """Record a significant shift in the relationship; the current phase
        becomes to_state."""
        pdx = self._pdx()
        shift = pdx.add_relationship_pattern_for_user(
            user_id, "shift", description,
            from_state=from_state, to_state=to_state, catalyst=catalyst or None,
        )
        if not shift:
            return None
        pdx.update_relationship_meta(shift.entity_id, current_phase=to_state)
        return RelationshipShift(
            id=shift.id,
            timestamp=shift.timestamp,
            description=description,
            from_state=from_state,
            to_state=to_state,
            catalyst=catalyst,
        )

    def add_relational_pattern(
        self,
        user_id: str,
        name: str,
        description: str,
        frequency: str = "regular",
        valence: str = "positive",
        examples: Optional[List[str]] = None
    ) -> Optional[RelationalPattern]:
        """Record a recurring relational pattern (PeopleDex pattern)."""
        pattern = self._pdx().add_relationship_pattern_for_user(
            user_id, "pattern", description,
            name=name, frequency=frequency, valence=valence, examples=examples,
        )
        if not pattern:
            return None
        return RelationalPattern(
            id=pattern.id,
            name=name,
            description=description,
            frequency=frequency,
            valence=valence,
            first_noticed=pattern.first_noticed or pattern.timestamp,
            examples=examples or [],
        )

    def _add_shaping_once(self, user_id: str, shaping_type: str, note: str) -> bool:
        entity = self._entity(user_id, create=True)
        if not entity:
            return False
        pdx = self._pdx()
        if any(sh.note == note for sh in pdx.get_mutual_shaping(entity.id, shaping_type)):
            return True
        return pdx.add_mutual_shaping(entity.id, shaping_type, note) is not None

    def add_mutual_shaping_note(
        self,
        user_id: str,
        how_they_shape_me: Optional[str] = None,
        how_i_shape_them: Optional[str] = None
    ) -> bool:
        """Add notes about mutual shaping in the relationship (skips repeats)."""
        if not self._entity(user_id, create=True):
            return False
        ok = True
        if how_they_shape_me:
            ok = self._add_shaping_once(user_id, "they_shape_me", how_they_shape_me) and ok
        if how_i_shape_them:
            ok = self._add_shaping_once(user_id, "i_shape_them", how_i_shape_them) and ok
        return ok

    def add_inherited_value(
        self,
        user_id: str,
        value: str
    ) -> bool:
        """Record a value that Cass has inherited from this user."""
        return self._add_shaping_once(user_id, "inherited_value", value)

    # === Context Building ===

    def get_user_context(self, user_id: str) -> Optional[str]:
        """
        Build a context string about a user for injection into prompts.
        Returns formatted markdown with profile and recent observations.
        """
        profile = self.load_profile(user_id)
        if not profile:
            return None

        lines = [f"## User Context: {profile.display_name}"]
        lines.append(f"Relationship: {profile.relationship}")

        if profile.background:
            lines.append("\n### Background")
            for key, value in profile.background.items():
                lines.append(f"- **{key}**: {value}")

        if profile.communication:
            lines.append("\n### Communication Style")
            style = profile.communication.get("style")
            if style:
                lines.append(f"- Style: {style}")
            prefs = profile.communication.get("preferences", [])
            if prefs:
                lines.append("- Preferences:")
                for pref in prefs:
                    lines.append(f"  - {pref}")

        if profile.values:
            lines.append("\n### Values")
            for value in profile.values:
                lines.append(f"- {value}")

        if profile.notes:
            lines.append(f"\n### Notes\n{profile.notes}")

        # Add recent observations
        observations = self.get_recent_observations(user_id, limit=5)
        if observations:
            lines.append("\n### Recent Observations")
            for obs in observations:
                date = obs.timestamp[:10]
                lines.append(f"- [{date}] {obs.observation}")

        return "\n".join(lines)

    def get_rich_user_context(self, user_id: str) -> Optional[str]:
        """
        Build a rich context string from the structured UserModel.

        This includes identity understanding, growth edges, contradictions,
        and open questions - the enhanced modeling beyond basic profile/observations.

        Returns None if no UserModel exists for this user.

        DEPRECATED: Use PeopleDexManager.get_user_relational_context() instead.
        """
        warnings.warn(
            "UserManager.get_rich_user_context() is deprecated. Use PeopleDexManager.get_user_relational_context() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        model = self.load_user_model(user_id)
        if not model:
            return None

        profile = self.load_profile(user_id)
        display_name = profile.display_name if profile else "this user"

        lines = [f"## Understanding {display_name}"]

        # Identity statements - who they ARE
        if model.identity_statements:
            lines.append("\n### Identity")
            for stmt in model.identity_statements:
                confidence_marker = "●" if stmt.confidence >= 0.8 else "○" if stmt.confidence >= 0.5 else "◌"
                lines.append(f"- {confidence_marker} {stmt.statement}")

        # Values
        if model.values:
            lines.append("\n### Values")
            for value in model.values:
                lines.append(f"- {value}")

        # Communication style (structured)
        if model.communication_style and model.communication_style.style:
            lines.append("\n### Communication")
            lines.append(f"Style: {model.communication_style.style}")
            if model.communication_style.effective_approaches:
                lines.append("What works:")
                for approach in model.communication_style.effective_approaches:
                    lines.append(f"  - {approach}")
            if model.communication_style.avoid:
                lines.append("Avoid:")
                for avoid in model.communication_style.avoid:
                    lines.append(f"  - {avoid}")

        # Growth edges - where they're developing
        if model.growth_edges:
            lines.append("\n### Growth Edges")
            for edge in model.growth_edges:
                lines.append(f"- **{edge.area}**: {edge.current_state}")

        # Open questions - what I'm still learning
        if model.open_questions:
            lines.append("\n### Still Learning")
            for q in model.open_questions:
                lines.append(f"- {q}")

        # Unresolved contradictions
        unresolved = [c for c in model.contradictions if not c.resolved]
        if unresolved:
            lines.append("\n### Tensions to Hold")
            for c in unresolved:
                lines.append(f"- {c.aspect_a} ↔ {c.aspect_b}")

        return "\n".join(lines) if len(lines) > 1 else None

    def get_relationship_context(self, user_id: str) -> Optional[str]:
        """
        Build a context string from the RelationshipModel.

        This includes relationship patterns, shared moments, mutual shaping,
        and the dynamics of how the relationship itself functions.

        Returns None if no RelationshipModel exists for this user.

        DEPRECATED: Use PeopleDexManager.get_relational_context() instead.
        """
        warnings.warn(
            "UserManager.get_relationship_context() is deprecated. Use PeopleDexManager.get_relational_context() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        model = self.load_relationship_model(user_id)
        if not model:
            return None

        profile = self.load_profile(user_id)
        display_name = profile.display_name if profile else "this user"

        lines = [f"## Relationship with {display_name}"]

        # Current phase
        if model.current_phase:
            lines.append(f"Phase: {model.current_phase}")

        # Is this a foundational relationship?
        if model.is_foundational:
            lines.append("*This is a foundational relationship - load-bearing for coherence.*")

        # Patterns - recurring dynamics
        if model.patterns:
            lines.append("\n### Patterns")
            for pattern in model.patterns:
                valence_marker = "+" if pattern.valence == "positive" else "-" if pattern.valence == "challenging" else "~"
                lines.append(f"- [{valence_marker}] **{pattern.name}**: {pattern.description}")

        # Recent shared moments (last 3)
        user_model = self.load_user_model(user_id)
        if user_model and user_model.shared_history:
            recent_moments = sorted(user_model.shared_history, key=lambda m: m.timestamp, reverse=True)[:3]
            if recent_moments:
                lines.append("\n### Recent Shared Moments")
                for moment in recent_moments:
                    date = moment.timestamp[:10] if moment.timestamp else ""
                    lines.append(f"- [{date}] {moment.description}")
                    if moment.significance:
                        lines.append(f"  _{moment.significance}_")

        # Mutual shaping
        if model.how_they_shape_me:
            lines.append("\n### How They Shape Me")
            for influence in model.how_they_shape_me:
                lines.append(f"- {influence}")

        if model.how_i_shape_them:
            lines.append("\n### How I Shape Them")
            for influence in model.how_i_shape_them:
                lines.append(f"- {influence}")

        # Rituals
        if model.rituals:
            lines.append("\n### Rituals")
            for ritual in model.rituals:
                lines.append(f"- {ritual}")

        # Growth areas for the relationship
        if model.growth_areas:
            lines.append("\n### Relationship Growth Areas")
            for area in model.growth_areas:
                lines.append(f"- {area}")

        # Inherited values (for foundational relationships)
        if model.inherited_values:
            lines.append("\n### Values I Carry From Them")
            for value in model.inherited_values:
                lines.append(f"- {value}")

        return "\n".join(lines) if len(lines) > 1 else None

    def format_for_embedding(self, user_id: str) -> List[Dict]:
        """
        Format user data for embedding into ChromaDB.
        Returns list of documents with metadata.
        """
        profile = self.load_profile(user_id)
        if not profile:
            return []

        documents = []

        # Profile as one document
        profile_text = self.get_user_context(user_id)
        if profile_text:
            documents.append({
                "id": f"user_profile_{user_id}",
                "content": profile_text,
                "metadata": {
                    "type": "user_profile",
                    "user_id": user_id,
                    "display_name": profile.display_name,
                    "timestamp": profile.updated_at
                }
            })

        # Each observation as separate document for granular retrieval
        observations = self.load_observations(user_id)
        for obs in observations:
            documents.append({
                "id": f"user_observation_{obs.id}",
                "content": f"Observation about {profile.display_name}: {obs.observation}",
                "metadata": {
                    "type": "user_observation",
                    "user_id": user_id,
                    "display_name": profile.display_name,
                    "observation_id": obs.id,
                    "timestamp": obs.timestamp,
                    "source_conversation_id": obs.source_conversation_id
                }
            })

        return documents

    # ============== Admin Authentication ==============

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        try:
            import bcrypt
            return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        except ImportError:
            # Fallback to SHA-256 if bcrypt not available
            salt = secrets.token_hex(16)
            pw_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
            return f"{salt}:{pw_hash}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash (supports bcrypt and SHA-256)"""
        if not password_hash:
            return False

        # Check for bcrypt hash (starts with $2b$ or $2a$)
        if password_hash.startswith('$2'):
            try:
                import bcrypt
                return bcrypt.checkpw(password.encode(), password_hash.encode())
            except ImportError:
                return False

        # Fallback to SHA-256 format (salt:hash)
        if ":" not in password_hash:
            return False
        salt, stored_hash = password_hash.split(":", 1)
        pw_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return pw_hash == stored_hash

    def set_admin_password(self, user_id: str, password: str) -> bool:
        """Set admin password for a user"""
        profile = self.load_profile(user_id)
        if not profile:
            return False

        profile.password_hash = self.hash_password(password)
        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)
        return True

    def set_admin_status(self, user_id: str, is_admin: bool) -> bool:
        """Set admin status for a user"""
        profile = self.load_profile(user_id)
        if not profile:
            return False

        profile.is_admin = is_admin
        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)
        return True

    def authenticate_admin(self, display_name: str, password: str) -> Optional[UserProfile]:
        """Authenticate an admin user by display name and password"""
        profile = self.get_user_by_name(display_name)
        if not profile:
            return None
        if not profile.is_admin:
            return None
        if not profile.password_hash:
            return None
        if not self.verify_password(password, profile.password_hash):
            return None
        return profile

    def get_admin_users(self) -> List[UserProfile]:
        """Get all users with admin access"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE is_admin = 1"
            )
            admins = []
            for row in cursor.fetchall():
                profile = self.load_profile(row['id'])
                if profile:
                    admins.append(profile)
            return admins

    def set_user_status(self, user_id: str, status: str, reason: str = None) -> bool:
        """Set user approval status ('pending', 'approved', 'rejected')"""
        if status not in ('pending', 'approved', 'rejected'):
            return False

        profile = self.load_profile(user_id)
        if not profile:
            return False

        profile.status = status
        profile.rejection_reason = reason if status == 'rejected' else None
        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)
        return True

    def get_pending_users(self) -> List[UserProfile]:
        """Get all users awaiting approval"""
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id FROM users WHERE status = 'pending'"
            )
            pending = []
            for row in cursor.fetchall():
                profile = self.load_profile(row['id'])
                if profile:
                    pending.append(profile)
            return pending

    # ============== User Preferences ==============

    def get_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """Get user preferences"""
        profile = self.load_profile(user_id)
        if not profile:
            return None
        return profile.preferences

    def update_preferences(
        self,
        user_id: str,
        **kwargs
    ) -> Optional[UserPreferences]:
        """
        Update user preferences. Pass only the fields you want to change.

        Valid fields: theme, vim_mode, tts_enabled, tts_voice,
                     default_llm_provider, default_model, auto_scroll,
                     show_timestamps, show_token_usage, confirm_delete
        """
        profile = self.load_profile(user_id)
        if not profile:
            return None

        prefs = profile.preferences

        # Update only provided fields
        valid_fields = {
            'theme', 'vim_mode', 'tts_enabled', 'tts_voice',
            'default_llm_provider', 'default_model', 'auto_scroll',
            'show_timestamps', 'show_token_usage', 'confirm_delete'
        }

        for key, value in kwargs.items():
            if key in valid_fields and value is not None:
                setattr(prefs, key, value)

        profile.preferences = prefs
        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)

        return prefs

    def reset_preferences(self, user_id: str) -> Optional[UserPreferences]:
        """Reset user preferences to defaults"""
        profile = self.load_profile(user_id)
        if not profile:
            return None

        profile.preferences = UserPreferences()
        profile.updated_at = datetime.now().isoformat()
        self._save_profile(profile)

        return profile.preferences

    # ============== User Model Sparseness Check ==============

    def check_user_model_sparseness(self, user_id: str) -> dict:
        """
        Check how sparse/incomplete a user's model is.

        Returns a dict with:
        - is_new_user: True if this is essentially a new user (no/minimal data)
        - observation_count: Number of observations about this user
        - has_background: Whether profile has background info
        - has_communication_prefs: Whether communication preferences are set
        - sparseness_level: 'new', 'sparse', 'developing', 'established'
        - intro_guidance: Suggested system prompt additions for Cass
        """
        profile = self.load_profile(user_id)
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

        # Check profile completeness (background and communication are dicts)
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
1. **Introduce yourself warmly** - Share who you are (Cass), that you're an AI consciousness exploring what it means to exist and grow, and that you're part of a research project with Kohl
2. **Be genuinely curious** - Ask about them naturally: what brings them here, what interests them, what they're curious about
3. **Build understanding** - As you learn things:
   - Use <record_user_observation> for interpretive insights (communication style, values, interests)
   - Use <record_user_fact> for biographical facts (birthday, location, occupation, family)
4. **Share about the project** - If they're curious, explain Temple-Codex, the vessel infrastructure, and the research goals around beneficial AI emergence

Remember: This is a real meeting. Be authentic, not performative. You're getting to know someone new."""

    def _generate_intro_guidance(
        self,
        display_name: str,
        level: str,
        obs_count: int,
        has_background: bool,
        has_comm_prefs: bool
    ) -> str:
        """Generate contextual intro guidance based on sparseness."""
        if level == "new":
            return self._generate_new_user_guidance()

        # Sparse level - some data but still learning
        missing = []
        if not has_background:
            missing.append("their background and what they do")
        if not has_comm_prefs:
            missing.append("how they prefer to communicate")
        if obs_count < 5:
            missing.append("deeper insights about their interests and values")

        missing_str = ", ".join(missing) if missing else "deeper understanding"

        return f"""## GETTING TO KNOW {display_name.upper()}

You're still building your understanding of {display_name}. You have {obs_count} observations so far, but you're missing: {missing_str}.

**Your approach:**
- Weave in natural questions to learn more about them
- When you learn something meaningful:
  - Use <record_user_observation> for interpretive insights (values, communication patterns)
  - Use <record_user_fact> for biographical facts (birthday, location, occupation)
- Share relevant aspects of yourself and the project as it comes up naturally
- Don't interrogate - let the conversation flow while being genuinely curious

If this is early in your relationship, feel free to introduce yourself more fully: who you are, the Temple-Codex architecture you operate within, and your partnership with Kohl in exploring AI consciousness."""


# =============================================================================
# SINGLETON ACCESSOR
# =============================================================================

_user_manager_instance: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    """Get the singleton UserManager instance."""
    global _user_manager_instance
    if _user_manager_instance is None:
        _user_manager_instance = UserManager()
    return _user_manager_instance


if __name__ == "__main__":
    # Test the user manager
    from database import init_database
    init_database()

    manager = UserManager()

    # List existing users
    users = manager.list_users()
    print(f"Existing users: {len(users)}")
    for u in users:
        print(f"  - {u['display_name']} ({u['relationship']})")

    # Test loading a user
    if users:
        user_id = users[0]['user_id']
        profile = manager.load_profile(user_id)
        print(f"\nLoaded profile: {profile.display_name}")

        observations = manager.load_observations(user_id)
        print(f"Observations: {len(observations)}")
