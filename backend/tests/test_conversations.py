"""
Tests for the ConversationManager module.
"""
import pytest
from datetime import datetime


class TestMessage:
    """Tests for the Message dataclass."""

    def test_message_creation_minimal(self):
        """Message can be created with required fields only."""
        from conversations import Message

        msg = Message(
            role="user",
            content="Hello",
            timestamp="2025-01-01T00:00:00"
        )

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.excluded is False
        assert msg.input_tokens is None

    def test_message_creation_full(self):
        """Message can be created with all fields."""
        from conversations import Message

        msg = Message(
            role="assistant",
            content="Hello! I'm Cass.",
            timestamp="2025-01-01T00:00:00",
            input_tokens=100,
            output_tokens=50,
            provider="anthropic",
            model="claude-sonnet-4",
            excluded=False
        )

        assert msg.provider == "anthropic"
        assert msg.model == "claude-sonnet-4"
        assert msg.input_tokens == 100


class TestConversation:
    """Tests for the Conversation dataclass."""

    def test_conversation_to_dict(self):
        """Conversation serializes to dict correctly."""
        from conversations import Conversation, Message

        conv = Conversation(
            id="test-id",
            title="Test",
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
            messages=[
                Message(role="user", content="Hi", timestamp="2025-01-01T00:00:00")
            ]
        )

        data = conv.to_dict()

        assert data["id"] == "test-id"
        assert data["title"] == "Test"
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Hi"

    def test_conversation_from_dict(self):
        """Conversation deserializes from dict correctly."""
        from conversations import Conversation

        data = {
            "id": "test-id",
            "title": "Test",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
            "messages": [
                {"role": "user", "content": "Hi", "timestamp": "2025-01-01T00:00:00"}
            ],
            "working_summary": "A test conversation"
        }

        conv = Conversation.from_dict(data)

        assert conv.id == "test-id"
        assert conv.working_summary == "A test conversation"
        assert len(conv.messages) == 1


class TestConversationManager:
    """Tests for ConversationManager."""

    @pytest.mark.unit
    def test_create_conversation(self, conversation_manager):
        """Creating a conversation returns valid Conversation object."""
        conv = conversation_manager.create_conversation(title="Test Conv")

        assert conv.title == "Test Conv"
        assert conv.id is not None
        assert len(conv.messages) == 0

    @pytest.mark.unit
    def test_create_conversation_default_title(self, conversation_manager):
        """Conversation gets default title if none provided."""
        conv = conversation_manager.create_conversation()

        assert conv.title == "New Conversation"

    @pytest.mark.unit
    def test_load_conversation(self, conversation_manager):
        """Created conversation can be loaded back."""
        conv = conversation_manager.create_conversation(title="Load Test")

        loaded = conversation_manager.load_conversation(conv.id)

        assert loaded is not None
        assert loaded.id == conv.id
        assert loaded.title == "Load Test"

    @pytest.mark.unit
    def test_load_nonexistent_conversation(self, conversation_manager):
        """Loading nonexistent conversation returns None."""
        result = conversation_manager.load_conversation("nonexistent-id")

        assert result is None

    @pytest.mark.unit
    def test_add_message(self, conversation_manager, sample_conversation):
        """Adding message updates conversation."""
        conversation_manager.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Test message"
        )

        loaded = conversation_manager.load_conversation(sample_conversation.id)

        assert len(loaded.messages) == 1
        assert loaded.messages[0].content == "Test message"
        assert loaded.messages[0].role == "user"

    @pytest.mark.unit
    def test_add_message_with_metadata(self, conversation_manager, sample_conversation):
        """Adding message with token metadata preserves it."""
        conversation_manager.add_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="Hello!",
            input_tokens=100,
            output_tokens=50,
            provider="anthropic",
            model="claude-sonnet-4"
        )

        loaded = conversation_manager.load_conversation(sample_conversation.id)
        msg = loaded.messages[0]

        assert msg.input_tokens == 100
        assert msg.output_tokens == 50
        assert msg.provider == "anthropic"

    @pytest.mark.unit
    def test_list_conversations(self, conversation_manager, sample_user_id):
        """Listing conversations returns all for user."""
        conversation_manager.create_conversation(title="Conv 1", user_id=sample_user_id)
        conversation_manager.create_conversation(title="Conv 2", user_id=sample_user_id)
        conversation_manager.create_conversation(title="Other", user_id="other-user")

        convs = conversation_manager.list_conversations(user_id=sample_user_id)

        assert len(convs) == 2
        titles = [c["title"] for c in convs]
        assert "Conv 1" in titles
        assert "Conv 2" in titles

    @pytest.mark.unit
    def test_delete_conversation(self, conversation_manager, sample_conversation):
        """Deleting conversation removes it from storage."""
        conv_id = sample_conversation.id

        result = conversation_manager.delete_conversation(conv_id)

        assert result is True
        assert conversation_manager.load_conversation(conv_id) is None

    @pytest.mark.unit
    def test_update_title(self, conversation_manager, sample_conversation):
        """Updating title changes conversation title."""
        conversation_manager.update_title(
            sample_conversation.id,
            "New Title"
        )

        loaded = conversation_manager.load_conversation(sample_conversation.id)

        assert loaded.title == "New Title"

    @pytest.mark.unit
    def test_update_working_summary(self, conversation_manager, sample_conversation):
        """Working summary can be updated."""
        conversation_manager.update_working_summary(
            sample_conversation.id,
            "This is a summary of the conversation."
        )

        loaded = conversation_manager.load_conversation(sample_conversation.id)

        assert loaded.working_summary == "This is a summary of the conversation."
