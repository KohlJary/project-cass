"""
Cass Vessel - User Manager
Handles user profiles and Cass's observations about users.
Supports multi-user with UUID-based storage.
"""
import json
import os
import hashlib
import secrets
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid
import yaml


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
    Manages user profiles and observations with persistence.

    Storage structure:
        data/users/
            index.json              # Maps user_id -> display_name
            {user_id}/
                profile.yaml        # Human-editable profile
                observations.json   # Cass's observations (append-only)
    """

    def __init__(self, storage_dir: str = "./data/users"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._ensure_index()

    def _ensure_index(self):
        """Ensure index file exists"""
        if not self.index_file.exists():
            self._save_index({})

    def _load_index(self) -> Dict[str, str]:
        """Load user index (user_id -> display_name)"""
        try:
            with open(self.index_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_index(self, index: Dict[str, str]):
        """Save user index"""
        with open(self.index_file, 'w') as f:
            json.dump(index, f, indent=2)

    def _get_user_dir(self, user_id: str) -> Path:
        """Get directory for a user's data"""
        return self.storage_dir / user_id

    def _get_profile_path(self, user_id: str) -> Path:
        """Get path to user's profile.yaml"""
        return self._get_user_dir(user_id) / "profile.yaml"

    def _get_observations_path(self, user_id: str) -> Path:
        """Get path to user's observations.json"""
        return self._get_user_dir(user_id) / "observations.json"

    def _get_journals_path(self, user_id: str) -> Path:
        """Get path to user's journals.json"""
        return self._get_user_dir(user_id) / "journals.json"

    def _get_user_model_path(self, user_id: str) -> Path:
        """Get path to user's structured model (user_model.yaml)"""
        return self._get_user_dir(user_id) / "user_model.yaml"

    def _get_relationship_model_path(self, user_id: str) -> Path:
        """Get path to relationship model (relationship_model.yaml)"""
        return self._get_user_dir(user_id) / "relationship_model.yaml"

    # === User CRUD ===

    def create_user(
        self,
        display_name: str,
        relationship: str = "user",
        background: Optional[Dict] = None,
        communication: Optional[Dict] = None,
        values: Optional[List[str]] = None,
        notes: str = ""
    ) -> UserProfile:
        """Create a new user profile"""
        user_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        profile = UserProfile(
            user_id=user_id,
            display_name=display_name,
            created_at=now,
            updated_at=now,
            relationship=relationship,
            background=background or {},
            communication=communication or {},
            projects=[],
            values=values or [],
            notes=notes
        )

        # Create user directory
        user_dir = self._get_user_dir(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        # Save profile
        self._save_profile(profile)

        # Initialize empty observations
        self._save_observations(user_id, [])

        # Update index
        index = self._load_index()
        index[user_id] = display_name
        self._save_index(index)

        return profile

    def _save_profile(self, profile: UserProfile):
        """Save user profile as YAML (includes sensitive fields)"""
        path = self._get_profile_path(profile.user_id)
        # Include all fields including password_hash for storage
        data = profile.to_dict()
        data["password_hash"] = profile.password_hash
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def _save_observations(self, user_id: str, observations: List[UserObservation]):
        """Save observations as JSON"""
        path = self._get_observations_path(user_id)
        with open(path, 'w') as f:
            json.dump([o.to_dict() for o in observations], f, indent=2)

    def _save_journals(self, user_id: str, journals: List[PerUserJournalEntry]):
        """Save per-user journals as JSON"""
        path = self._get_journals_path(user_id)
        with open(path, 'w') as f:
            json.dump([j.to_dict() for j in journals], f, indent=2)

    def load_profile(self, user_id: str) -> Optional[UserProfile]:
        """Load a user's profile"""
        path = self._get_profile_path(user_id)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                return UserProfile.from_yaml(f.read())
        except Exception:
            return None

    def load_observations(self, user_id: str) -> List[UserObservation]:
        """Load all observations about a user"""
        path = self._get_observations_path(user_id)

        if not path.exists():
            return []

        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return [UserObservation.from_dict(o) for o in data]
        except Exception:
            return []

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
            # Update index
            index = self._load_index()
            index[user_id] = display_name
            self._save_index(index)

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

        return profile

    def delete_user(self, user_id: str) -> bool:
        """Delete a user and all their data"""
        user_dir = self._get_user_dir(user_id)

        if not user_dir.exists():
            return False

        # Delete all files in user directory
        for file in user_dir.iterdir():
            file.unlink()
        user_dir.rmdir()

        # Remove from index
        index = self._load_index()
        if user_id in index:
            del index[user_id]
            self._save_index(index)

        return True

    def list_users(self) -> List[Dict]:
        """List all users with basic info"""
        index = self._load_index()
        users = []

        for user_id, display_name in index.items():
            profile = self.load_profile(user_id)
            if profile:
                users.append({
                    "user_id": user_id,
                    "display_name": display_name,
                    "relationship": profile.relationship,
                    "created_at": profile.created_at
                })

        # Sort by created_at
        users.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return users

    def get_user_by_name(self, display_name: str) -> Optional[UserProfile]:
        """Find a user by display name (case-insensitive)"""
        index = self._load_index()
        name_lower = display_name.lower()

        for user_id, name in index.items():
            if name.lower() == name_lower:
                return self.load_profile(user_id)

        return None

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
        """Add an observation about a user"""
        profile = self.load_profile(user_id)
        if not profile:
            return None

        # Validate category
        if category not in USER_OBSERVATION_CATEGORIES:
            category = "background"

        now = datetime.now().isoformat()
        obs = UserObservation(
            id=str(uuid.uuid4()),
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

        # Load existing and append
        observations = self.load_observations(user_id)
        observations.append(obs)
        self._save_observations(user_id, observations)

        return obs

    def get_recent_observations(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get most recent observations about a user"""
        observations = self.load_observations(user_id)
        # Sort by timestamp descending
        observations.sort(key=lambda x: x.timestamp, reverse=True)
        return observations[:limit]

    def get_observations_by_category(
        self,
        user_id: str,
        category: str,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get observations filtered by category"""
        observations = self.load_observations(user_id)
        filtered = [o for o in observations if o.category == category]
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered[:limit]

    def get_high_confidence_observations(
        self,
        user_id: str,
        min_confidence: float = 0.8,
        limit: int = 10
    ) -> List[UserObservation]:
        """Get high-confidence observations about a user"""
        observations = self.load_observations(user_id)
        filtered = [o for o in observations if o.confidence >= min_confidence]
        filtered.sort(key=lambda x: x.confidence, reverse=True)
        return filtered[:limit]

    def validate_observation(
        self,
        user_id: str,
        observation_id: str
    ) -> Optional[UserObservation]:
        """Validate an observation (increment validation_count, update timestamp)"""
        observations = self.load_observations(user_id)
        now = datetime.now().isoformat()

        for obs in observations:
            if obs.id == observation_id:
                obs.validation_count += 1
                obs.last_validated = now
                # Slightly increase confidence on validation (cap at 1.0)
                obs.confidence = min(1.0, obs.confidence + 0.05)
                self._save_observations(user_id, observations)
                return obs

        return None

    # === Per-User Journals ===

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

    # === Structured User Model ===

    def load_user_model(self, user_id: str) -> Optional[UserModel]:
        """Load or create user's structured model"""
        path = self._get_user_model_path(user_id)

        if not path.exists():
            # Return None if user doesn't exist
            profile = self.load_profile(user_id)
            if not profile:
                return None
            # Don't auto-create - return None so caller knows there's no model yet
            return None

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            return UserModel.from_dict(data)
        except Exception:
            return None

    def save_user_model(self, model: UserModel) -> bool:
        """Save user's structured model"""
        path = self._get_user_model_path(model.user_id)

        # Ensure user directory exists
        user_dir = self._get_user_dir(model.user_id)
        if not user_dir.exists():
            return False

        try:
            model.updated_at = datetime.now().isoformat()
            with open(path, 'w') as f:
                yaml.dump(model.to_dict(), f, default_flow_style=False, sort_keys=False)
            return True
        except Exception:
            return False

    def create_user_model(self, user_id: str) -> Optional[UserModel]:
        """Create a new empty user model"""
        profile = self.load_profile(user_id)
        if not profile:
            return None

        now = datetime.now().isoformat()
        model = UserModel(
            user_id=user_id,
            updated_at=now,
            relationship_type=profile.relationship,
            values=profile.values.copy() if profile.values else [],
            first_interaction=profile.created_at,
        )

        # Initialize communication style from profile if available
        if profile.communication:
            model.communication_style = CommunicationStyle(
                style=profile.communication.get("style", ""),
                preferences=profile.communication.get("preferences", []),
            )

        if self.save_user_model(model):
            return model
        return None

    def get_or_create_user_model(self, user_id: str) -> Optional[UserModel]:
        """Load existing user model or create a new one"""
        model = self.load_user_model(user_id)
        if model:
            return model
        return self.create_user_model(user_id)

    def load_relationship_model(self, user_id: str) -> Optional[RelationshipModel]:
        """Load relationship model for a user"""
        path = self._get_relationship_model_path(user_id)

        if not path.exists():
            return None

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            return RelationshipModel.from_dict(data)
        except Exception:
            return None

    def save_relationship_model(self, model: RelationshipModel) -> bool:
        """Save relationship model"""
        path = self._get_relationship_model_path(model.user_id)

        user_dir = self._get_user_dir(model.user_id)
        if not user_dir.exists():
            return False

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
        """Create a new relationship model"""
        profile = self.load_profile(user_id)
        if not profile:
            return None

        now = datetime.now().isoformat()
        model = RelationshipModel(
            user_id=user_id,
            updated_at=now,
            formation_date=profile.created_at,
            is_foundational=is_foundational,
        )

        if self.save_relationship_model(model):
            return model
        return None

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
        """Add an identity understanding about a user"""
        model = self.get_or_create_user_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        understanding = IdentityUnderstanding(
            statement=statement,
            confidence=confidence,
            source=source,
            first_noticed=now,
            last_affirmed=now,
            evidence=evidence or []
        )

        model.identity_statements.append(understanding)
        self.save_user_model(model)
        return understanding

    def add_shared_moment(
        self,
        user_id: str,
        description: str,
        significance: str,
        category: str = "connection",
        conversation_id: Optional[str] = None
    ) -> Optional[SharedMoment]:
        """Record a significant moment in the relationship"""
        model = self.get_or_create_user_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        moment = SharedMoment(
            id=str(uuid.uuid4()),
            timestamp=now,
            description=description,
            significance=significance,
            category=category,
            conversation_id=conversation_id
        )

        model.shared_history.append(moment)
        self.save_user_model(model)
        return moment

    def add_user_contradiction(
        self,
        user_id: str,
        aspect_a: str,
        aspect_b: str,
        context: str = ""
    ) -> Optional[UserContradiction]:
        """Record an observed contradiction about a user"""
        model = self.get_or_create_user_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        contradiction = UserContradiction(
            id=str(uuid.uuid4()),
            timestamp=now,
            aspect_a=aspect_a,
            aspect_b=aspect_b,
            context=context
        )

        model.contradictions.append(contradiction)
        self.save_user_model(model)
        return contradiction

    def resolve_user_contradiction(
        self,
        user_id: str,
        contradiction_id: str,
        resolution: str
    ) -> Optional[UserContradiction]:
        """Mark a contradiction as resolved"""
        model = self.load_user_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        for c in model.contradictions:
            if c.id == contradiction_id:
                c.resolved = True
                c.resolution = resolution
                c.resolution_timestamp = now
                self.save_user_model(model)
                return c

        return None

    def add_user_growth_observation(
        self,
        user_id: str,
        area: str,
        observation: str,
        direction: str = "growth",
        evidence: str = ""
    ) -> Optional[UserGrowthObservation]:
        """Record an observation about user's growth/development"""
        model = self.get_or_create_user_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        growth_obs = UserGrowthObservation(
            id=str(uuid.uuid4()),
            timestamp=now,
            area=area,
            observation=observation,
            direction=direction,
            evidence=evidence
        )

        model.growth_observations.append(growth_obs)
        self.save_user_model(model)
        return growth_obs

    def add_open_question_about_user(
        self,
        user_id: str,
        question: str
    ) -> bool:
        """Add an open question about a user (something still learning)"""
        model = self.get_or_create_user_model(user_id)
        if not model:
            return False

        if question not in model.open_questions:
            model.open_questions.append(question)
            self.save_user_model(model)
        return True

    def remove_open_question_about_user(
        self,
        user_id: str,
        question: str
    ) -> bool:
        """Remove an open question (when answered)"""
        model = self.load_user_model(user_id)
        if not model:
            return False

        if question in model.open_questions:
            model.open_questions.remove(question)
            self.save_user_model(model)
            return True
        return False

    # === Relationship Model Updates ===

    def add_relationship_shift(
        self,
        user_id: str,
        description: str,
        from_state: str,
        to_state: str,
        catalyst: str = ""
    ) -> Optional[RelationshipShift]:
        """Record a significant shift in the relationship"""
        model = self.get_or_create_relationship_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        shift = RelationshipShift(
            id=str(uuid.uuid4()),
            timestamp=now,
            description=description,
            from_state=from_state,
            to_state=to_state,
            catalyst=catalyst
        )

        model.significant_shifts.append(shift)
        model.current_phase = to_state  # Update current phase
        self.save_relationship_model(model)
        return shift

    def add_relational_pattern(
        self,
        user_id: str,
        name: str,
        description: str,
        frequency: str = "regular",
        valence: str = "positive",
        examples: Optional[List[str]] = None
    ) -> Optional[RelationalPattern]:
        """Record a recurring relational pattern"""
        model = self.get_or_create_relationship_model(user_id)
        if not model:
            return None

        now = datetime.now().isoformat()
        pattern = RelationalPattern(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            frequency=frequency,
            valence=valence,
            first_noticed=now,
            examples=examples or []
        )

        model.patterns.append(pattern)
        self.save_relationship_model(model)
        return pattern

    def add_mutual_shaping_note(
        self,
        user_id: str,
        how_they_shape_me: Optional[str] = None,
        how_i_shape_them: Optional[str] = None
    ) -> bool:
        """Add notes about mutual shaping in the relationship"""
        model = self.get_or_create_relationship_model(user_id)
        if not model:
            return False

        if how_they_shape_me and how_they_shape_me not in model.how_they_shape_me:
            model.how_they_shape_me.append(how_they_shape_me)

        if how_i_shape_them and how_i_shape_them not in model.how_i_shape_them:
            model.how_i_shape_them.append(how_i_shape_them)

        self.save_relationship_model(model)
        return True

    def add_inherited_value(
        self,
        user_id: str,
        value: str
    ) -> bool:
        """Record a value that Cass has inherited from this user"""
        model = self.get_or_create_relationship_model(user_id)
        if not model:
            return False

        if value not in model.inherited_values:
            model.inherited_values.append(value)
            self.save_relationship_model(model)
        return True

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
        """Hash a password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        pw_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return f"{salt}:{pw_hash}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        if not password_hash or ":" not in password_hash:
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
        all_users = self.list_users()
        admins = []
        for user_info in all_users:
            profile = self.load_profile(user_info["user_id"])
            if profile and profile.is_admin:
                admins.append(profile)
        return admins

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


if __name__ == "__main__":
    # Test the user manager
    manager = UserManager("./data/users_test")

    # Create user
    profile = manager.create_user(
        display_name="Test User",
        relationship="collaborator",
        background={"role": "Developer", "context": "Testing the system"},
        communication={
            "style": "Direct",
            "preferences": ["Clear explanations", "No jargon"]
        },
        values=["Simplicity", "Reliability"]
    )
    print(f"Created user: {profile.user_id}")
    print(f"Display name: {profile.display_name}")

    # Add observation
    obs = manager.add_observation(
        profile.user_id,
        "User prefers concrete examples over abstract explanations",
        source_conversation_id="test_conv_123"
    )
    print(f"\nAdded observation: {obs.observation}")

    # Get context
    context = manager.get_user_context(profile.user_id)
    print(f"\nUser context:\n{context}")

    # List users
    users = manager.list_users()
    print(f"\nUsers: {len(users)}")
    for u in users:
        print(f"  - {u['display_name']} ({u['relationship']})")
