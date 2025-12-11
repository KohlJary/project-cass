"""
Tests for the UserManager module.
"""
import pytest
from datetime import datetime


class TestUserPreferences:
    """Tests for UserPreferences dataclass."""

    def test_default_preferences(self):
        """Default preferences have sensible values."""
        from users import UserPreferences

        prefs = UserPreferences()

        assert prefs.theme == "default"
        assert prefs.vim_mode is False
        assert prefs.tts_enabled is True
        assert prefs.default_llm_provider == "anthropic"

    def test_preferences_to_dict(self):
        """Preferences serialize to dict correctly."""
        from users import UserPreferences

        prefs = UserPreferences(vim_mode=True, theme="dark")
        data = prefs.to_dict()

        assert data["vim_mode"] is True
        assert data["theme"] == "dark"

    def test_preferences_from_dict(self):
        """Preferences deserialize from dict correctly."""
        from users import UserPreferences

        data = {
            "theme": "light",
            "tts_enabled": False,
            "default_llm_provider": "openai"
        }
        prefs = UserPreferences.from_dict(data)

        assert prefs.theme == "light"
        assert prefs.tts_enabled is False
        assert prefs.default_llm_provider == "openai"


class TestUserObservation:
    """Tests for UserObservation dataclass."""

    def test_observation_creation(self):
        """Observation can be created with required fields."""
        from users import UserObservation

        obs = UserObservation(
            id="obs-1",
            timestamp="2025-01-01T00:00:00",
            observation="User prefers concise responses"
        )

        assert obs.category == "background"  # default
        assert obs.confidence == 0.7  # default
        assert obs.source_type == "conversation"

    def test_observation_categories_valid(self):
        """Known categories are accepted."""
        from users import UserObservation, USER_OBSERVATION_CATEGORIES

        obs = UserObservation(
            id="obs-1",
            timestamp="2025-01-01T00:00:00",
            observation="Values direct communication",
            category="communication_style"
        )

        assert obs.category in USER_OBSERVATION_CATEGORIES


class TestUserManager:
    """Tests for UserManager."""

    @pytest.mark.unit
    def test_create_user(self, user_manager):
        """Creating a user returns valid UserProfile."""
        profile = user_manager.create_user(display_name="Test User")

        assert profile.display_name == "Test User"
        assert profile.user_id is not None
        assert profile.relationship == "user"

    @pytest.mark.unit
    def test_create_user_with_details(self, user_manager):
        """User can be created with full details."""
        profile = user_manager.create_user(
            display_name="Alice",
            relationship="friend",
            background={"profession": "engineer"},
            values=["honesty", "growth"]
        )

        assert profile.display_name == "Alice"
        assert profile.relationship == "friend"
        assert profile.background["profession"] == "engineer"
        assert "honesty" in profile.values

    @pytest.mark.unit
    def test_load_profile(self, user_manager):
        """Created user can be loaded by ID."""
        created = user_manager.create_user(display_name="Bob")

        loaded = user_manager.load_profile(created.user_id)

        assert loaded is not None
        assert loaded.user_id == created.user_id
        assert loaded.display_name == "Bob"

    @pytest.mark.unit
    def test_load_nonexistent_profile(self, user_manager):
        """Loading nonexistent user returns None."""
        result = user_manager.load_profile("nonexistent-id")

        assert result is None

    @pytest.mark.unit
    def test_list_users(self, user_manager):
        """Listing users returns all users."""
        user_manager.create_user(display_name="User1")
        user_manager.create_user(display_name="User2")

        users = user_manager.list_users()

        assert len(users) == 2
        names = [u["display_name"] for u in users]
        assert "User1" in names
        assert "User2" in names

    @pytest.mark.unit
    def test_update_profile(self, user_manager):
        """User profile can be updated."""
        profile = user_manager.create_user(display_name="Carol")

        user_manager.update_profile(
            profile.user_id,
            display_name="Carol Updated",
            relationship="collaborator"
        )

        updated = user_manager.load_profile(profile.user_id)

        assert updated.display_name == "Carol Updated"
        assert updated.relationship == "collaborator"

    @pytest.mark.unit
    def test_add_observation(self, user_manager):
        """Observations can be added to a user."""
        profile = user_manager.create_user(display_name="Dave")

        user_manager.add_observation(
            user_id=profile.user_id,
            observation="Prefers technical discussions",
            category="preference",
            confidence=0.8
        )

        observations = user_manager.load_observations(profile.user_id)

        assert len(observations) == 1
        assert observations[0].observation == "Prefers technical discussions"
        assert observations[0].category == "preference"
        assert observations[0].confidence == 0.8

    @pytest.mark.unit
    def test_add_multiple_observations(self, user_manager):
        """Multiple observations accumulate."""
        profile = user_manager.create_user(display_name="Eve")

        user_manager.add_observation(
            user_id=profile.user_id,
            observation="Works in data science",
            category="background"
        )
        user_manager.add_observation(
            user_id=profile.user_id,
            observation="Values documentation",
            category="value"
        )

        observations = user_manager.load_observations(profile.user_id)

        assert len(observations) == 2

    @pytest.mark.unit
    def test_delete_user(self, user_manager):
        """User can be deleted."""
        profile = user_manager.create_user(display_name="Grace")

        result = user_manager.delete_user(profile.user_id)

        assert result is True
        assert user_manager.load_profile(profile.user_id) is None

    @pytest.mark.unit
    def test_user_preferences(self, user_manager):
        """User preferences can be set and retrieved."""
        profile = user_manager.create_user(display_name="Henry")

        user_manager.update_preferences(
            profile.user_id,
            theme="dark",
            vim_mode=True
        )

        updated = user_manager.load_profile(profile.user_id)

        assert updated.preferences.theme == "dark"
        assert updated.preferences.vim_mode is True

    @pytest.mark.unit
    def test_get_user_by_name(self, user_manager):
        """User can be found by display name."""
        user_manager.create_user(display_name="UniqueNameForTest")

        found = user_manager.get_user_by_name("UniqueNameForTest")

        assert found is not None
        assert found.display_name == "UniqueNameForTest"

    @pytest.mark.unit
    def test_get_preferences(self, user_manager):
        """Preferences can be retrieved directly."""
        profile = user_manager.create_user(display_name="Ivan")

        prefs = user_manager.get_preferences(profile.user_id)

        assert prefs is not None
        assert prefs.theme == "default"  # default value
