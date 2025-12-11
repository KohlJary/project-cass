"""
Shared pytest fixtures for Cass Vessel backend tests.
"""
import pytest
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Directory Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_data_dir():
    """Create isolated temporary data directory, cleaned up after test."""
    path = Path(tempfile.mkdtemp(prefix="cass_test_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def conversations_dir(test_data_dir):
    """Create conversations subdirectory."""
    path = test_data_dir / "conversations"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def users_dir(test_data_dir):
    """Create users subdirectory."""
    path = test_data_dir / "users"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def summaries_dir(test_data_dir):
    """Create summaries subdirectory."""
    path = test_data_dir / "summaries"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Manager Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conversation_manager(conversations_dir):
    """ConversationManager with isolated storage."""
    from conversations import ConversationManager
    return ConversationManager(storage_dir=str(conversations_dir))


@pytest.fixture
def user_manager(users_dir):
    """UserManager with isolated storage."""
    from users import UserManager
    return UserManager(storage_dir=str(users_dir))


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_user_id():
    """Return a consistent test user ID."""
    return "test-user-00000000-0000-0000-0000-000000000001"


@pytest.fixture
def sample_conversation(conversation_manager, sample_user_id):
    """Create and return a sample conversation."""
    return conversation_manager.create_conversation(
        title="Test Conversation",
        user_id=sample_user_id
    )


@pytest.fixture
def sample_message_data():
    """Return sample message data dict."""
    return {
        "role": "user",
        "content": "Hello, Cass!",
        "timestamp": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_user_profile_data():
    """Return sample user profile data."""
    return {
        "display_name": "Test User",
        "email": "test@example.com",
        "bio": "A test user for unit tests",
        "preferences": {
            "theme": "dark",
            "tts_enabled": False
        }
    }


# ---------------------------------------------------------------------------
# Mock Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client."""
    with patch('anthropic.Anthropic') as mock:
        client = Mock()
        mock.return_value = client

        # Mock messages.create response
        response = Mock()
        response.content = [Mock(text="Hello! I'm Cass.")]
        response.usage = Mock(input_tokens=100, output_tokens=50)
        response.stop_reason = "end_turn"
        client.messages.create.return_value = response

        yield client


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI API client."""
    with patch('openai.OpenAI') as mock:
        client = Mock()
        mock.return_value = client

        # Mock chat.completions.create response
        response = Mock()
        response.choices = [Mock(message=Mock(content="Hello from OpenAI!"))]
        response.usage = Mock(prompt_tokens=100, completion_tokens=50)
        client.chat.completions.create.return_value = response

        yield client


@pytest.fixture
def mock_chromadb():
    """Mock ChromaDB client and collection."""
    with patch('chromadb.Client') as mock:
        client = Mock()
        mock.return_value = client

        collection = Mock()
        collection.add = Mock()
        collection.query = Mock(return_value={
            "documents": [["Sample document"]],
            "metadatas": [[{"source": "test"}]],
            "distances": [[0.1]]
        })
        collection.count = Mock(return_value=10)

        client.get_or_create_collection.return_value = collection

        yield client, collection


# ---------------------------------------------------------------------------
# Async Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection for testing handlers."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# FastAPI Test Client (for route tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app():
    """Create test FastAPI app instance."""
    # Import here to avoid circular imports
    from fastapi.testclient import TestClient
    from main_sdk import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Additional Directory Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def projects_dir(test_data_dir):
    """Create projects subdirectory."""
    path = test_data_dir / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def calendar_dir(test_data_dir):
    """Create calendar subdirectory."""
    path = test_data_dir / "calendar"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def tasks_dir(test_data_dir):
    """Create tasks subdirectory."""
    path = test_data_dir / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def chroma_dir(test_data_dir):
    """Create ChromaDB subdirectory."""
    path = test_data_dir / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Additional Manager Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project_manager(projects_dir):
    """ProjectManager with isolated storage."""
    from projects import ProjectManager
    return ProjectManager(storage_dir=str(projects_dir))


@pytest.fixture
def calendar_manager(calendar_dir):
    """CalendarManager with isolated storage."""
    from calendar_manager import CalendarManager
    return CalendarManager(storage_dir=str(calendar_dir))


@pytest.fixture
def task_manager(tasks_dir):
    """TaskManager with isolated storage."""
    from task_manager import TaskManager
    return TaskManager(storage_dir=str(tasks_dir))


@pytest.fixture
def roadmap_dir(test_data_dir):
    """Create roadmap subdirectory."""
    path = test_data_dir / "roadmap"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def roadmap_manager(roadmap_dir):
    """RoadmapManager with isolated storage."""
    from roadmap import RoadmapManager
    return RoadmapManager(storage_dir=str(roadmap_dir))


# ---------------------------------------------------------------------------
# Sample Data Fixtures - Calendar
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_event_data():
    """Return sample event data."""
    from datetime import timedelta
    return {
        "title": "Test Meeting",
        "start_time": datetime.now() + timedelta(days=1),
        "end_time": datetime.now() + timedelta(days=1, hours=1),
        "description": "A test meeting",
        "location": "Conference Room A",
    }


@pytest.fixture
def sample_reminder_data():
    """Return sample reminder data."""
    from datetime import timedelta
    return {
        "title": "Test Reminder",
        "remind_at": datetime.now() + timedelta(hours=2),
        "description": "Don't forget this",
    }


# ---------------------------------------------------------------------------
# Sample Data Fixtures - Tasks
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_task_data():
    """Return sample task data."""
    from task_manager import Priority
    return {
        "description": "Test task",
        "priority": Priority.MEDIUM,
        "tags": ["test", "sample"],
        "project": "test-project",
    }


# ---------------------------------------------------------------------------
# Sample Data Fixtures - Projects
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_project_data(test_data_dir):
    """Return sample project data with a real working directory."""
    work_dir = test_data_dir / "sample_project"
    work_dir.mkdir(parents=True, exist_ok=True)
    return {
        "name": "Test Project",
        "working_directory": str(work_dir),
        "description": "A test project",
    }


@pytest.fixture
def sample_project_with_file(project_manager, sample_project_data, test_data_dir):
    """Create a sample project with a test file."""
    # Create project
    project = project_manager.create_project(**sample_project_data)

    # Create a test file in the working directory
    test_file = Path(sample_project_data["working_directory"]) / "test_file.txt"
    test_file.write_text("Test content")

    return project, str(test_file)


# ---------------------------------------------------------------------------
# Mock Fixtures - Ollama/httpx
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_httpx_ollama():
    """Mock httpx for Ollama API calls."""
    with patch('httpx.AsyncClient') as mock:
        client = AsyncMock()
        mock.return_value.__aenter__.return_value = client

        # Mock successful response
        response = AsyncMock()
        response.status_code = 200
        response.json.return_value = {"response": "Test gist summary"}
        client.post.return_value = response

        yield client
