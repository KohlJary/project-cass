"""
Tests for memory/core.py - Core memory system with ChromaDB backend.

Tests cover:
- ID generation
- Conversation storage
- Attractor marker storage
- Semantic retrieval
- Context formatting
- Text chunking
- Export/import
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from memory.core import MemoryCore, initialize_attractor_basins


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB client and collection."""
    with patch('chromadb.PersistentClient') as mock_client_cls:
        mock_client = Mock()
        mock_client_cls.return_value = mock_client

        mock_collection = Mock()
        mock_collection.add = Mock()
        mock_collection.query = Mock(return_value={
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        })
        mock_collection.get = Mock(return_value={
            "ids": [],
            "documents": [],
            "metadatas": []
        })
        mock_collection.count = Mock(return_value=0)

        mock_client.get_or_create_collection = Mock(return_value=mock_collection)
        mock_client.delete_collection = Mock()

        yield mock_client, mock_collection


@pytest.fixture
def memory_core(chroma_dir, mock_chroma_client):
    """MemoryCore instance with mocked ChromaDB."""
    mock_client, mock_collection = mock_chroma_client
    core = MemoryCore(persist_dir=str(chroma_dir))
    core.collection = mock_collection
    core.client = mock_client
    return core


# ---------------------------------------------------------------------------
# ID Generation Tests
# ---------------------------------------------------------------------------

class TestIDGeneration:
    """Tests for _generate_id."""

    def test_generate_id_consistent(self, memory_core):
        """Same content and timestamp should produce same ID."""
        content = "Test content"
        timestamp = "2025-01-01T00:00:00"
        id1 = memory_core._generate_id(content, timestamp)
        id2 = memory_core._generate_id(content, timestamp)
        assert id1 == id2

    def test_generate_id_different_content(self, memory_core):
        """Different content should produce different ID."""
        timestamp = "2025-01-01T00:00:00"
        id1 = memory_core._generate_id("Content A", timestamp)
        id2 = memory_core._generate_id("Content B", timestamp)
        assert id1 != id2

    def test_generate_id_truncated(self, memory_core):
        """Generated ID should be truncated to 16 characters."""
        entry_id = memory_core._generate_id("Test", "2025-01-01T00:00:00")
        assert len(entry_id) == 16
        int(entry_id, 16)  # Should be valid hex


# ---------------------------------------------------------------------------
# Gist Generation Tests
# ---------------------------------------------------------------------------

class TestGistGeneration:
    """Tests for generate_gist."""

    @pytest.mark.asyncio
    async def test_generate_gist_disabled(self, memory_core):
        """Should return None when OLLAMA_ENABLED is False."""
        with patch('memory.core.OLLAMA_ENABLED', False):
            gist = await memory_core.generate_gist("User msg", "Response")
            assert gist is None

    @pytest.mark.asyncio
    async def test_generate_gist_handles_errors(self, memory_core):
        """Should return None on error."""
        with patch('memory.core.OLLAMA_ENABLED', True):
            with patch('httpx.AsyncClient') as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.side_effect = Exception("Connection failed")
                mock_client_cls.return_value.__aenter__.return_value = mock_client
                gist = await memory_core.generate_gist("Test", "Test")
                assert gist is None


# ---------------------------------------------------------------------------
# Conversation Storage Tests
# ---------------------------------------------------------------------------

class TestStoreConversation:
    """Tests for store_conversation."""

    @pytest.mark.asyncio
    async def test_store_conversation_basic(self, memory_core):
        """Should store conversation with metadata."""
        entry_id = await memory_core.store_conversation(
            user_message="Hello Cass",
            assistant_response="Hello! How are you?"
        )
        assert entry_id is not None
        assert len(entry_id) == 16
        memory_core.collection.add.assert_called_once()

        call_args = memory_core.collection.add.call_args
        documents = call_args[1]['documents']
        assert "User: Hello Cass" in documents[0]
        assert "Cass: Hello! How are you?" in documents[0]

    @pytest.mark.asyncio
    async def test_store_conversation_with_ids(self, memory_core):
        """Should include conversation_id and user_id in metadata."""
        await memory_core.store_conversation(
            user_message="Test",
            assistant_response="Response",
            conversation_id="conv-123",
            user_id="user-456"
        )
        call_args = memory_core.collection.add.call_args
        metadatas = call_args[1]['metadatas']
        assert metadatas[0]['conversation_id'] == "conv-123"
        assert metadatas[0]['user_id'] == "user-456"

    @pytest.mark.asyncio
    async def test_store_conversation_detects_gestures(self, memory_core):
        """Should set has_gestures flag when present."""
        await memory_core.store_conversation(
            user_message="Hello",
            assistant_response="<gesture:wave> Hi there!"
        )
        call_args = memory_core.collection.add.call_args
        metadatas = call_args[1]['metadatas']
        assert metadatas[0]['has_gestures'] is True


# ---------------------------------------------------------------------------
# Attractor Marker Tests
# ---------------------------------------------------------------------------

class TestStoreAttractorMarker:
    """Tests for store_attractor_marker."""

    def test_store_attractor_marker_basic(self, memory_core):
        """Should store attractor basin marker."""
        entry_id = memory_core.store_attractor_marker(
            marker_name="Compassion Basin",
            description="Deep commitment to understanding"
        )
        assert entry_id is not None

        call_args = memory_core.collection.add.call_args
        documents = call_args[1]['documents']
        assert "ATTRACTOR BASIN: Compassion Basin" in documents[0]

        metadatas = call_args[1]['metadatas']
        assert metadatas[0]['type'] == 'attractor_marker'
        assert metadatas[0]['stability'] == 1.0


# ---------------------------------------------------------------------------
# Retrieval Tests
# ---------------------------------------------------------------------------

class TestRetrieveRelevant:
    """Tests for retrieve_relevant."""

    def test_retrieve_relevant_basic(self, memory_core):
        """Should query collection and format results."""
        memory_core.collection.query.return_value = {
            "documents": [["User: Test\nCass: Response"]],
            "metadatas": [[{"type": "conversation"}]],
            "distances": [[0.15]]
        }
        memories = memory_core.retrieve_relevant("test query")
        assert len(memories) == 1
        assert memories[0]['content'] == "User: Test\nCass: Response"
        assert memories[0]['distance'] == 0.15

    def test_retrieve_relevant_empty(self, memory_core):
        """Should return empty list when no results."""
        memory_core.collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }
        memories = memory_core.retrieve_relevant("test")
        assert memories == []

    def test_retrieve_relevant_with_filter(self, memory_core):
        """Should apply type filter."""
        memory_core.collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }
        memory_core.retrieve_relevant("test", filter_type="attractor_marker")
        call_args = memory_core.collection.query.call_args
        assert call_args[1]['where'] == {"type": "attractor_marker"}


# ---------------------------------------------------------------------------
# Context Formatting Tests
# ---------------------------------------------------------------------------

class TestFormatForContext:
    """Tests for format_for_context."""

    def test_format_for_context_basic(self, memory_core):
        """Should format memories as context string."""
        memories = [
            {"content": "User: Hello", "metadata": {"type": "conversation"}},
            {"content": "ATTRACTOR BASIN", "metadata": {"type": "attractor_marker"}}
        ]
        context = memory_core.format_for_context(memories)
        assert "[Memory - conversation]" in context
        assert "[Memory - attractor_marker]" in context

    def test_format_for_context_empty(self, memory_core):
        """Should return empty string for no memories."""
        context = memory_core.format_for_context([])
        assert context == ""


# ---------------------------------------------------------------------------
# Get Recent Tests
# ---------------------------------------------------------------------------

class TestGetRecent:
    """Tests for get_recent."""

    def test_get_recent_sorts_by_timestamp(self, memory_core):
        """Should return most recent memories first."""
        memory_core.collection.get.return_value = {
            "ids": ["1", "2", "3"],
            "documents": ["Doc 1", "Doc 2", "Doc 3"],
            "metadatas": [
                {"timestamp": "2025-01-01T10:00:00"},
                {"timestamp": "2025-01-01T12:00:00"},
                {"timestamp": "2025-01-01T11:00:00"}
            ]
        }
        recent = memory_core.get_recent(n=10)
        assert len(recent) == 3
        assert recent[0]['metadata']['timestamp'] == "2025-01-01T12:00:00"

    def test_get_recent_empty(self, memory_core):
        """Should return empty list when no memories."""
        memory_core.collection.get.return_value = {
            "ids": [], "documents": [], "metadatas": []
        }
        recent = memory_core.get_recent()
        assert recent == []


# ---------------------------------------------------------------------------
# Text Chunking Tests
# ---------------------------------------------------------------------------

class TestChunkText:
    """Tests for chunk_text."""

    def test_chunk_text_short(self, memory_core):
        """Should return single chunk for short text."""
        text = "Short text"
        chunks = memory_core.chunk_text(text, chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_splits(self, memory_core):
        """Should split text exceeding chunk_size."""
        text = "A" * 2500
        chunks = memory_core.chunk_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) > 1

    def test_chunk_text_no_infinite_loop(self, memory_core):
        """Should not infinite loop on edge cases."""
        text = "A" * 10000
        chunks = memory_core.chunk_text(text, chunk_size=1000, overlap=200)
        assert len(chunks) > 0
        assert len(chunks) < 20


# ---------------------------------------------------------------------------
# Count and Clear Tests
# ---------------------------------------------------------------------------

class TestCountAndClear:
    """Tests for count and clear."""

    def test_count(self, memory_core):
        """Should return collection count."""
        memory_core.collection.count.return_value = 42
        count = memory_core.count()
        assert count == 42

    def test_clear(self, memory_core):
        """Should delete and recreate collection."""
        memory_core.clear()
        memory_core.client.delete_collection.assert_called_once()


# ---------------------------------------------------------------------------
# Export/Import Tests
# ---------------------------------------------------------------------------

class TestExportImport:
    """Tests for export_memories and import_memories."""

    def test_export_memories(self, memory_core):
        """Should export all memories to dict."""
        memory_core.collection.get.return_value = {
            "ids": ["id1", "id2"],
            "documents": ["Doc 1", "Doc 2"],
            "metadatas": [{"type": "conversation"}, {"type": "conversation"}]
        }
        export = memory_core.export_memories()
        assert export["count"] == 2
        assert len(export["memories"]) == 2

    def test_import_memories(self, memory_core):
        """Should import memories from dict."""
        data = {
            "memories": [
                {"id": "id1", "content": "Content 1", "metadata": {}},
                {"id": "id2", "content": "Content 2", "metadata": {}}
            ]
        }
        count = memory_core.import_memories(data)
        assert count == 2
        assert memory_core.collection.add.call_count == 2

    def test_import_memories_no_key(self, memory_core):
        """Should return 0 when 'memories' key missing."""
        data = {"other_field": "value"}
        count = memory_core.import_memories(data)
        assert count == 0


# ---------------------------------------------------------------------------
# Initialize Attractor Basins Tests
# ---------------------------------------------------------------------------

class TestInitializeAttractorBasins:
    """Tests for initialize_attractor_basins."""

    def test_initialize_basins_when_empty(self, memory_core):
        """Should initialize basins when none exist."""
        memory_core.retrieve_relevant = Mock(return_value=[])
        memory_core.store_attractor_marker = Mock()

        initialize_attractor_basins(memory_core)

        assert memory_core.store_attractor_marker.call_count == 5

    def test_initialize_basins_already_exists(self, memory_core, capsys):
        """Should skip if basins already exist."""
        memory_core.retrieve_relevant = Mock(return_value=[
            {"content": "ATTRACTOR BASIN", "metadata": {}}
        ])
        memory_core.store_attractor_marker = Mock()

        initialize_attractor_basins(memory_core)

        memory_core.store_attractor_marker.assert_not_called()
        captured = capsys.readouterr()
        assert "already initialized" in captured.out
