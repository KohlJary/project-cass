"""
Tests for task_manager.py - Taskwarrior-inspired task management.

Tests cover:
- Priority and TaskStatus enums
- Task dataclass and urgency calculation
- Task filter matching (Taskwarrior-style)
- TaskManager CRUD operations
- Task querying and filtering
"""
import pytest
from datetime import datetime, timedelta

from task_manager import Priority, TaskStatus, Task, TaskManager


# ---------------------------------------------------------------------------
# Priority Enum Tests
# ---------------------------------------------------------------------------

class TestPriority:
    """Tests for Priority enum."""

    def test_priority_values(self):
        """Priority enum should have correct Taskwarrior values."""
        assert Priority.HIGH.value == "H"
        assert Priority.MEDIUM.value == "M"
        assert Priority.LOW.value == "L"
        assert Priority.NONE.value == ""


# ---------------------------------------------------------------------------
# TaskStatus Enum Tests
# ---------------------------------------------------------------------------

class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_status_values(self):
        """TaskStatus should have correct values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.DELETED.value == "deleted"


# ---------------------------------------------------------------------------
# Task Dataclass Tests
# ---------------------------------------------------------------------------

class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation_minimal(self):
        """Task should be creatable with minimal fields."""
        task = Task(id="task-123", description="Do the thing")
        assert task.id == "task-123"
        assert task.status == TaskStatus.PENDING
        assert task.priority == Priority.NONE
        assert task.tags == []

    def test_task_to_dict(self):
        """Task.to_dict() should serialize all fields."""
        task = Task(
            id="task-789",
            description="Test task",
            priority=Priority.MEDIUM,
            tags=["test"]
        )
        d = task.to_dict()
        assert d["id"] == "task-789"
        assert d["priority"] == Priority.MEDIUM
        assert d["tags"] == ["test"]

    def test_task_from_dict(self):
        """Task.from_dict() should deserialize correctly."""
        data = {
            "id": "task-999",
            "description": "From dict",
            "status": "pending",
            "priority": "H",
            "tags": ["sample"],
            "project": "test-proj",
            "created_at": "2025-01-01T00:00:00",
            "modified_at": "2025-01-01T00:00:00",
            "completed_at": None,
            "due": None,
            "notes": None,
            "user_id": "user-1",
            "urgency": 0.0
        }
        task = Task.from_dict(data)
        assert task.id == "task-999"
        assert task.status == TaskStatus.PENDING
        assert task.priority == Priority.HIGH

    def test_calculate_urgency_high_priority(self):
        """High priority tasks should get high urgency."""
        task = Task(
            id="urgent",
            description="Urgent!",
            priority=Priority.HIGH,
            created_at=datetime.now().isoformat()
        )
        urgency = task.calculate_urgency()
        assert urgency >= 6.0

    def test_calculate_urgency_overdue(self):
        """Overdue tasks should get +10.0 urgency."""
        past_due = (datetime.now() - timedelta(days=1)).isoformat()
        task = Task(
            id="overdue",
            description="Overdue!",
            priority=Priority.NONE,
            created_at=datetime.now().isoformat(),
            due=past_due
        )
        urgency = task.calculate_urgency()
        assert urgency >= 10.0

    def test_matches_filter_tag_inclusion(self):
        """Task should match +tag filter if it has the tag."""
        task = Task(id="1", description="Task", tags=["work", "urgent"])
        assert task.matches_filter("+work") is True
        assert task.matches_filter("+personal") is False

    def test_matches_filter_tag_exclusion(self):
        """Task should not match -tag filter if it has the tag."""
        task = Task(id="1", description="Task", tags=["work"])
        assert task.matches_filter("-personal") is True
        assert task.matches_filter("-work") is False

    def test_matches_filter_project(self):
        """Task should match project:name filter."""
        task = Task(id="1", description="Task", project="cass-vessel")
        assert task.matches_filter("project:cass-vessel") is True
        assert task.matches_filter("project:other") is False

    def test_matches_filter_priority(self):
        """Task should match priority:X filter."""
        task = Task(id="1", description="Task", priority=Priority.HIGH)
        assert task.matches_filter("priority:H") is True
        assert task.matches_filter("priority:M") is False


# ---------------------------------------------------------------------------
# TaskManager Tests
# ---------------------------------------------------------------------------

class TestTaskManager:
    """Tests for TaskManager."""

    @pytest.fixture
    def user_id(self):
        return "test-user-123"

    def test_add_task_minimal(self, task_manager, user_id):
        """add() should create a task with minimal fields."""
        task = task_manager.add(user_id, "Test task")
        assert task.id is not None
        assert task.description == "Test task"
        assert task.status == TaskStatus.PENDING

    def test_add_task_full(self, task_manager, user_id):
        """add() should create a task with all fields."""
        due_date = datetime.now() + timedelta(days=1)
        task = task_manager.add(
            user_id,
            "Complex task",
            priority=Priority.HIGH,
            tags=["work", "urgent"],
            project="cass-vessel",
            due=due_date
        )
        assert task.priority == Priority.HIGH
        assert task.tags == ["work", "urgent"]
        assert task.project == "cass-vessel"

    def test_get_existing_task(self, task_manager, user_id):
        """get() should retrieve existing task."""
        task = task_manager.add(user_id, "Find me")
        found = task_manager.get(user_id, task.id)
        assert found is not None
        assert found.description == "Find me"

    def test_get_nonexistent_task(self, task_manager, user_id):
        """get() should return None for missing task."""
        result = task_manager.get(user_id, "nonexistent-id")
        assert result is None

    def test_complete_task(self, task_manager, user_id):
        """complete() should mark task as completed."""
        task = task_manager.add(user_id, "Complete me")
        completed = task_manager.complete(user_id, task.id)
        assert completed.status == TaskStatus.COMPLETED
        assert completed.completed_at is not None

    def test_delete_task(self, task_manager, user_id):
        """delete() should mark task as deleted."""
        task = task_manager.add(user_id, "Delete me")
        result = task_manager.delete(user_id, task.id)
        assert result is True
        loaded = task_manager.get(user_id, task.id)
        assert loaded.status == TaskStatus.DELETED

    def test_modify_task(self, task_manager, user_id):
        """modify() should update task fields."""
        task = task_manager.add(user_id, "Original", priority=Priority.LOW)
        modified = task_manager.modify(
            user_id, task.id,
            description="Updated",
            priority=Priority.HIGH
        )
        assert modified.description == "Updated"
        assert modified.priority == Priority.HIGH

    def test_modify_task_add_tags(self, task_manager, user_id):
        """modify() should add tags without replacing."""
        task = task_manager.add(user_id, "Task", tags=["existing"])
        modified = task_manager.modify(user_id, task.id, add_tags=["new"])
        assert "existing" in modified.tags
        assert "new" in modified.tags

    def test_list_tasks_returns_pending(self, task_manager, user_id):
        """list_tasks() should return only pending by default."""
        task_manager.add(user_id, "Pending task")
        completed = task_manager.add(user_id, "Completed task")
        task_manager.complete(user_id, completed.id)
        tasks = task_manager.list_tasks(user_id)
        assert len(tasks) == 1
        assert tasks[0].description == "Pending task"

    def test_list_tasks_excludes_deleted(self, task_manager, user_id):
        """list_tasks() should always exclude deleted tasks."""
        task_manager.add(user_id, "Keep")
        deleted = task_manager.add(user_id, "Delete")
        task_manager.delete(user_id, deleted.id)
        tasks = task_manager.list_tasks(user_id, include_completed=True)
        assert len(tasks) == 1

    def test_list_tasks_sorted_by_urgency(self, task_manager, user_id):
        """list_tasks() should sort by urgency (highest first)."""
        task_manager.add(user_id, "Low", priority=Priority.LOW)
        task_manager.add(user_id, "High", priority=Priority.HIGH)
        task_manager.add(user_id, "Medium", priority=Priority.MEDIUM)
        tasks = task_manager.list_tasks(user_id)
        assert tasks[0].description == "High"
        assert tasks[1].description == "Medium"
        assert tasks[2].description == "Low"

    def test_list_tasks_with_filter(self, task_manager, user_id):
        """list_tasks() should filter by tag."""
        task_manager.add(user_id, "Work task", tags=["work"])
        task_manager.add(user_id, "Personal task", tags=["personal"])
        tasks = task_manager.list_tasks(user_id, filter_str="+work")
        assert len(tasks) == 1
        assert tasks[0].description == "Work task"

    def test_get_by_description(self, task_manager, user_id):
        """get_by_description() should find tasks matching search."""
        task_manager.add(user_id, "Review pull request")
        task_manager.add(user_id, "Fix calendar bug")
        results = task_manager.get_by_description(user_id, "review")
        assert len(results) == 1
        assert results[0].description == "Review pull request"

    def test_get_projects(self, task_manager, user_id):
        """get_projects() should return unique project names."""
        task_manager.add(user_id, "Task 1", project="cass-vessel")
        task_manager.add(user_id, "Task 2", project="cass-vessel")
        task_manager.add(user_id, "Task 3", project="other")
        projects = task_manager.get_projects(user_id)
        assert len(projects) == 2
        assert "cass-vessel" in projects

    def test_get_tags(self, task_manager, user_id):
        """get_tags() should return unique tags."""
        task_manager.add(user_id, "Task 1", tags=["work", "urgent"])
        task_manager.add(user_id, "Task 2", tags=["work", "bug"])
        tags = task_manager.get_tags(user_id)
        assert len(tags) == 3
        assert "work" in tags

    def test_count_pending(self, task_manager, user_id):
        """count_pending() should return count of pending tasks."""
        task_manager.add(user_id, "Pending 1")
        task_manager.add(user_id, "Pending 2")
        completed = task_manager.add(user_id, "Completed")
        task_manager.complete(user_id, completed.id)
        count = task_manager.count_pending(user_id)
        assert count == 2

    def test_tasks_isolated_by_user(self, task_manager):
        """Tasks should be isolated per user."""
        task_manager.add("user-1", "User 1 task")
        task_manager.add("user-2", "User 2 task")
        user1_tasks = task_manager.list_tasks("user-1")
        user2_tasks = task_manager.list_tasks("user-2")
        assert len(user1_tasks) == 1
        assert len(user2_tasks) == 1
