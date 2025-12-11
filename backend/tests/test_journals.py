"""
Tests for memory/journals.py - Journal generation and storage.

Tests cover:
- JournalManager initialization
- Journal entry storage and retrieval
- Journal locking/unlocking
- Recent journals listing
- Journal summary generation (mocked)
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from memory.journals import JournalManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_memory_core():
    """Mock MemoryCore with collection."""
    core = Mock()
    collection = Mock()

    # Default empty responses
    collection.add = Mock()
    collection.get = Mock(return_value={
        "ids": [],
        "documents": [],
        "metadatas": []
    })
    collection.update = Mock()

    core.collection = collection
    core._generate_id = Mock(return_value="journal-abc123")

    return core, collection


@pytest.fixture
def journal_manager(mock_memory_core):
    """JournalManager with mocked core."""
    core, collection = mock_memory_core
    manager = JournalManager(core=core)
    return manager


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------

class TestJournalManagerInit:
    """Tests for JournalManager initialization."""

    def test_init_with_core(self, mock_memory_core):
        """Should initialize with MemoryCore."""
        core, _ = mock_memory_core
        manager = JournalManager(core=core)
        assert manager._core == core
        assert manager._summaries is None

    def test_init_with_summary_manager(self, mock_memory_core):
        """Should accept optional summary manager."""
        core, _ = mock_memory_core
        summary_manager = Mock()
        manager = JournalManager(core=core, summary_manager=summary_manager)
        assert manager._summaries == summary_manager

    def test_set_summary_manager(self, journal_manager):
        """Should allow setting summary manager after init."""
        summary_manager = Mock()
        journal_manager.set_summary_manager(summary_manager)
        assert journal_manager._summaries == summary_manager

    def test_collection_property(self, journal_manager, mock_memory_core):
        """Should expose collection from core."""
        _, collection = mock_memory_core
        assert journal_manager.collection == collection


# ---------------------------------------------------------------------------
# Store Journal Entry Tests
# ---------------------------------------------------------------------------

class TestStoreJournalEntry:
    """Tests for store_journal_entry."""

    @pytest.mark.asyncio
    async def test_store_journal_basic(self, journal_manager, mock_memory_core):
        """Should store journal entry with metadata."""
        _, collection = mock_memory_core

        with patch('memory.journals.OLLAMA_ENABLED', False):
            entry_id = await journal_manager.store_journal_entry(
                date="2025-01-15",
                journal_text="Today was a meaningful day...",
                summary_count=3,
                conversation_count=2
            )

        assert entry_id == "journal-abc123"
        collection.add.assert_called_once()

        call_args = collection.add.call_args
        assert "Today was a meaningful day..." in call_args[1]['documents']

        metadata = call_args[1]['metadatas'][0]
        assert metadata['type'] == 'journal'
        assert metadata['journal_date'] == '2025-01-15'
        assert metadata['summary_count'] == 3
        assert metadata['conversation_count'] == 2
        assert metadata['is_journal'] is True

    @pytest.mark.asyncio
    async def test_store_journal_with_summary(self, journal_manager, mock_memory_core):
        """Should include generated summary in metadata."""
        _, collection = mock_memory_core

        with patch.object(journal_manager, 'generate_journal_summary',
                         new_callable=AsyncMock, return_value="A day of reflection"):
            entry_id = await journal_manager.store_journal_entry(
                date="2025-01-15",
                journal_text="Long journal content...",
                summary_count=5
            )

        call_args = collection.add.call_args
        metadata = call_args[1]['metadatas'][0]
        assert metadata.get('summary') == "A day of reflection"


# ---------------------------------------------------------------------------
# Get Journal Entry Tests
# ---------------------------------------------------------------------------

class TestGetJournalEntry:
    """Tests for get_journal_entry."""

    def test_get_journal_found(self, journal_manager, mock_memory_core):
        """Should return journal entry for date."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": ["journal-123"],
            "documents": ["Today I reflected on..."],
            "metadatas": [{
                "type": "journal",
                "journal_date": "2025-01-15",
                "timestamp": "2025-01-15T23:00:00"
            }]
        }

        result = journal_manager.get_journal_entry("2025-01-15")

        assert result is not None
        assert result['content'] == "Today I reflected on..."
        assert result['metadata']['journal_date'] == "2025-01-15"
        assert result['id'] == "journal-123"

    def test_get_journal_not_found(self, journal_manager, mock_memory_core):
        """Should return None when no journal exists."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": [],
            "documents": [],
            "metadatas": []
        }

        result = journal_manager.get_journal_entry("2025-01-15")
        assert result is None

    def test_get_journal_queries_correctly(self, journal_manager, mock_memory_core):
        """Should query with correct filters."""
        _, collection = mock_memory_core
        collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        journal_manager.get_journal_entry("2025-01-15")

        call_args = collection.get.call_args
        where_clause = call_args[1]['where']
        assert where_clause == {
            "$and": [
                {"type": "journal"},
                {"journal_date": "2025-01-15"}
            ]
        }


# ---------------------------------------------------------------------------
# Journal Locking Tests
# ---------------------------------------------------------------------------

class TestSetJournalLocked:
    """Tests for set_journal_locked."""

    def test_lock_journal_success(self, journal_manager, mock_memory_core):
        """Should lock an existing journal."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": ["journal-123"],
            "documents": ["Journal content"],
            "metadatas": [{"type": "journal", "journal_date": "2025-01-15"}]
        }

        result = journal_manager.set_journal_locked("2025-01-15", locked=True)

        assert result is True
        collection.update.assert_called_once()

        call_args = collection.update.call_args
        assert call_args[1]['ids'] == ["journal-123"]
        assert call_args[1]['metadatas'][0]['locked'] is True

    def test_unlock_journal(self, journal_manager, mock_memory_core):
        """Should unlock a locked journal."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": ["journal-123"],
            "documents": ["Journal content"],
            "metadatas": [{"type": "journal", "journal_date": "2025-01-15", "locked": True}]
        }

        result = journal_manager.set_journal_locked("2025-01-15", locked=False)

        assert result is True
        call_args = collection.update.call_args
        assert call_args[1]['metadatas'][0]['locked'] is False

    def test_lock_nonexistent_journal(self, journal_manager, mock_memory_core):
        """Should return False for nonexistent journal."""
        _, collection = mock_memory_core
        collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        result = journal_manager.set_journal_locked("2025-01-15", locked=True)

        assert result is False
        collection.update.assert_not_called()


# ---------------------------------------------------------------------------
# Recent Journals Tests
# ---------------------------------------------------------------------------

class TestGetRecentJournals:
    """Tests for get_recent_journals."""

    def test_get_recent_journals_sorted(self, journal_manager, mock_memory_core):
        """Should return journals sorted by date descending."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": ["j1", "j2", "j3"],
            "documents": ["Jan 10 entry", "Jan 15 entry", "Jan 12 entry"],
            "metadatas": [
                {"type": "journal", "journal_date": "2025-01-10"},
                {"type": "journal", "journal_date": "2025-01-15"},
                {"type": "journal", "journal_date": "2025-01-12"}
            ]
        }

        results = journal_manager.get_recent_journals(n=10)

        assert len(results) == 3
        # Should be sorted newest first
        assert results[0]['metadata']['journal_date'] == "2025-01-15"
        assert results[1]['metadata']['journal_date'] == "2025-01-12"
        assert results[2]['metadata']['journal_date'] == "2025-01-10"

    def test_get_recent_journals_limited(self, journal_manager, mock_memory_core):
        """Should limit results to n."""
        _, collection = mock_memory_core
        collection.get.return_value = {
            "ids": ["j1", "j2", "j3", "j4", "j5"],
            "documents": ["a", "b", "c", "d", "e"],
            "metadatas": [
                {"journal_date": "2025-01-01"},
                {"journal_date": "2025-01-02"},
                {"journal_date": "2025-01-03"},
                {"journal_date": "2025-01-04"},
                {"journal_date": "2025-01-05"}
            ]
        }

        results = journal_manager.get_recent_journals(n=3)

        assert len(results) == 3

    def test_get_recent_journals_empty(self, journal_manager, mock_memory_core):
        """Should return empty list when no journals."""
        _, collection = mock_memory_core
        collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

        results = journal_manager.get_recent_journals()

        assert results == []


# ---------------------------------------------------------------------------
# Journal Summary Generation Tests
# ---------------------------------------------------------------------------

class TestGenerateJournalSummary:
    """Tests for generate_journal_summary."""

    @pytest.mark.asyncio
    async def test_summary_disabled_when_ollama_off(self, journal_manager):
        """Should return None when OLLAMA_ENABLED is False."""
        with patch('memory.journals.OLLAMA_ENABLED', False):
            result = await journal_manager.generate_journal_summary("Long journal text...")

        assert result is None

    @pytest.mark.asyncio
    async def test_summary_truncates_long_result(self, journal_manager):
        """Should truncate summaries over 250 chars."""
        with patch('memory.journals.OLLAMA_ENABLED', True):
            with patch('httpx.AsyncClient') as mock_client_cls:
                mock_client = AsyncMock()
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "response": "A" * 300  # Too long
                }
                mock_client.post.return_value = mock_response
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                result = await journal_manager.generate_journal_summary("Journal text")

                assert result is not None
                assert len(result) == 250
                assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_summary_handles_error(self, journal_manager):
        """Should return None on error."""
        with patch('memory.journals.OLLAMA_ENABLED', True):
            with patch('httpx.AsyncClient') as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.post.side_effect = Exception("Connection failed")
                mock_client_cls.return_value.__aenter__.return_value = mock_client

                result = await journal_manager.generate_journal_summary("Journal text")

                assert result is None
