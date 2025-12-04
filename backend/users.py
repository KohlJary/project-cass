"""
Cass Vessel - User Manager
Handles user profiles and Cass's observations about users.
Supports multi-user with UUID-based storage.
"""
import json
import os
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
    "relationship_dynamic" # Patterns in how they relate to Cass
}


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
            "notes": self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'UserProfile':
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
            notes=data.get("notes", "")
        )

    def to_yaml(self) -> str:
        """Export profile as YAML for human editing"""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> 'UserProfile':
        """Load profile from YAML"""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)


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
        """Save user profile as YAML"""
        path = self._get_profile_path(profile.user_id)
        with open(path, 'w') as f:
            f.write(profile.to_yaml())

    def _save_observations(self, user_id: str, observations: List[UserObservation]):
        """Save observations as JSON"""
        path = self._get_observations_path(user_id)
        with open(path, 'w') as f:
            json.dump([o.to_dict() for o in observations], f, indent=2)

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
