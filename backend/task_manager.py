"""
Cass Vessel - Task Manager
Taskwarrior-inspired task management with tags and priorities
"""
import json
from datetime import datetime
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, asdict, field
from pathlib import Path
import uuid
from enum import Enum


class Priority(str, Enum):
    """Task priority levels (Taskwarrior style)"""
    HIGH = "H"
    MEDIUM = "M"
    LOW = "L"
    NONE = ""


class TaskStatus(str, Enum):
    """Task status"""
    PENDING = "pending"
    COMPLETED = "completed"
    DELETED = "deleted"


@dataclass
class Task:
    """A task with Taskwarrior-like properties"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.NONE
    tags: List[str] = field(default_factory=list)
    project: Optional[str] = None

    # Timestamps
    created_at: str = ""
    modified_at: str = ""
    completed_at: Optional[str] = None

    # Optional fields
    due: Optional[str] = None  # Due date (ISO format)
    notes: Optional[str] = None
    user_id: Optional[str] = None

    # Urgency score (calculated)
    urgency: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """Create from dictionary"""
        # Handle enums
        if isinstance(data.get("status"), str):
            data["status"] = TaskStatus(data["status"])
        if isinstance(data.get("priority"), str):
            # Handle empty string for NONE priority
            data["priority"] = Priority(data["priority"]) if data["priority"] else Priority.NONE
        # Handle tags default
        if "tags" not in data:
            data["tags"] = []
        return cls(**data)

    def calculate_urgency(self) -> float:
        """
        Calculate urgency score (Taskwarrior-inspired).
        Higher = more urgent.
        """
        score = 0.0

        # Priority contributes significantly
        if self.priority == Priority.HIGH:
            score += 6.0
        elif self.priority == Priority.MEDIUM:
            score += 3.9
        elif self.priority == Priority.LOW:
            score += 1.8

        # Age contributes (older = more urgent, up to a point)
        if self.created_at:
            try:
                created = datetime.fromisoformat(self.created_at)
                age_days = (datetime.now() - created).days
                score += min(age_days * 0.1, 2.0)  # Cap at 2.0
            except Exception:
                pass

        # Due date contributes heavily
        if self.due:
            try:
                due_date = datetime.fromisoformat(self.due)
                days_until = (due_date - datetime.now()).days
                if days_until < 0:
                    score += 10.0  # Overdue!
                elif days_until == 0:
                    score += 8.0   # Due today
                elif days_until <= 3:
                    score += 5.0   # Due soon
                elif days_until <= 7:
                    score += 2.0   # Due this week
            except Exception:
                pass

        # Tags can add urgency
        if "urgent" in self.tags:
            score += 4.0
        if "next" in self.tags:
            score += 2.0

        self.urgency = round(score, 2)
        return self.urgency

    def matches_filter(self, filter_str: str) -> bool:
        """
        Check if task matches a Taskwarrior-style filter.
        Examples: +work, -home, project:cass, priority:H
        """
        parts = filter_str.split()
        for part in parts:
            # Tag inclusion: +tag
            if part.startswith("+"):
                tag = part[1:]
                if tag not in self.tags:
                    return False
            # Tag exclusion: -tag
            elif part.startswith("-"):
                tag = part[1:]
                if tag in self.tags:
                    return False
            # Project filter: project:name
            elif part.startswith("project:"):
                proj = part[8:]
                if self.project != proj:
                    return False
            # Priority filter: priority:H
            elif part.startswith("priority:"):
                pri = part[9:].upper()
                if self.priority.value != pri:
                    return False
            # Status filter: status:pending
            elif part.startswith("status:"):
                status = part[7:]
                if self.status.value != status:
                    return False
            # Description search (default)
            else:
                if part.lower() not in self.description.lower():
                    return False
        return True


class TaskManager:
    """
    Manages tasks with Taskwarrior-like functionality.
    Stores tasks in a JSON file per user.
    """

    def __init__(self, storage_dir: str = "./data/tasks"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_file(self, user_id: str) -> Path:
        """Get the task file for a user"""
        return self.storage_dir / f"{user_id}.json"

    def _load_tasks(self, user_id: str) -> List[Task]:
        """Load all tasks for a user"""
        filepath = self._get_user_file(user_id)
        if not filepath.exists():
            return []

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return [Task.from_dict(t) for t in data.get("tasks", [])]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save_tasks(self, user_id: str, tasks: List[Task]):
        """Save all tasks for a user"""
        filepath = self._get_user_file(user_id)
        with open(filepath, 'w') as f:
            json.dump({
                "tasks": [t.to_dict() for t in tasks],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2)

    def add(
        self,
        user_id: str,
        description: str,
        priority: Priority = Priority.NONE,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        due: Optional[datetime] = None,
        notes: Optional[str] = None
    ) -> Task:
        """Add a new task"""
        now = datetime.now().isoformat()

        task = Task(
            id=str(uuid.uuid4()),
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
            tags=tags or [],
            project=project,
            due=due.isoformat() if due else None,
            notes=notes,
            created_at=now,
            modified_at=now,
            user_id=user_id
        )
        task.calculate_urgency()

        tasks = self._load_tasks(user_id)
        tasks.append(task)
        self._save_tasks(user_id, tasks)

        return task

    def get(self, user_id: str, task_id: str) -> Optional[Task]:
        """Get a specific task by ID"""
        tasks = self._load_tasks(user_id)
        for task in tasks:
            if task.id == task_id:
                return task
        return None

    def complete(self, user_id: str, task_id: str) -> Optional[Task]:
        """Mark a task as completed"""
        tasks = self._load_tasks(user_id)

        for i, task in enumerate(tasks):
            if task.id == task_id:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                task.modified_at = datetime.now().isoformat()
                tasks[i] = task
                self._save_tasks(user_id, tasks)
                return task

        return None

    def delete(self, user_id: str, task_id: str) -> bool:
        """Delete a task (mark as deleted)"""
        tasks = self._load_tasks(user_id)

        for i, task in enumerate(tasks):
            if task.id == task_id:
                task.status = TaskStatus.DELETED
                task.modified_at = datetime.now().isoformat()
                tasks[i] = task
                self._save_tasks(user_id, tasks)
                return True

        return False

    def modify(
        self,
        user_id: str,
        task_id: str,
        description: Optional[str] = None,
        priority: Optional[Priority] = None,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        due: Optional[datetime] = None,
        notes: Optional[str] = None,
        add_tags: Optional[List[str]] = None,
        remove_tags: Optional[List[str]] = None
    ) -> Optional[Task]:
        """Modify an existing task"""
        tasks = self._load_tasks(user_id)

        for i, task in enumerate(tasks):
            if task.id == task_id:
                if description is not None:
                    task.description = description
                if priority is not None:
                    task.priority = priority
                if tags is not None:
                    task.tags = tags
                if project is not None:
                    task.project = project
                if due is not None:
                    task.due = due.isoformat()
                if notes is not None:
                    task.notes = notes

                # Add/remove tags
                if add_tags:
                    for tag in add_tags:
                        if tag not in task.tags:
                            task.tags.append(tag)
                if remove_tags:
                    task.tags = [t for t in task.tags if t not in remove_tags]

                task.modified_at = datetime.now().isoformat()
                task.calculate_urgency()
                tasks[i] = task
                self._save_tasks(user_id, tasks)
                return task

        return None

    def list_tasks(
        self,
        user_id: str,
        filter_str: Optional[str] = None,
        include_completed: bool = False,
        sort_by_urgency: bool = True
    ) -> List[Task]:
        """
        List tasks with optional filtering.

        Filter syntax (Taskwarrior-style):
        - +tag: include tasks with tag
        - -tag: exclude tasks with tag
        - project:name: filter by project
        - priority:H/M/L: filter by priority
        - Any other word: search in description
        """
        tasks = self._load_tasks(user_id)

        # Filter out deleted tasks
        tasks = [t for t in tasks if t.status != TaskStatus.DELETED]

        # Filter out completed unless requested
        if not include_completed:
            tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        # Apply filter string
        if filter_str:
            tasks = [t for t in tasks if t.matches_filter(filter_str)]

        # Calculate urgency and sort
        for task in tasks:
            task.calculate_urgency()

        if sort_by_urgency:
            tasks.sort(key=lambda t: t.urgency, reverse=True)

        return tasks

    def get_by_description(
        self,
        user_id: str,
        search: str,
        include_completed: bool = False
    ) -> List[Task]:
        """Find tasks by description (for natural language matching)"""
        tasks = self._load_tasks(user_id)
        search_lower = search.lower()

        results = []
        for task in tasks:
            if task.status == TaskStatus.DELETED:
                continue
            if not include_completed and task.status == TaskStatus.COMPLETED:
                continue
            if search_lower in task.description.lower():
                results.append(task)

        return results

    def get_projects(self, user_id: str) -> List[str]:
        """Get all unique project names"""
        tasks = self._load_tasks(user_id)
        projects = set()
        for task in tasks:
            if task.project and task.status != TaskStatus.DELETED:
                projects.add(task.project)
        return sorted(projects)

    def get_tags(self, user_id: str) -> List[str]:
        """Get all unique tags"""
        tasks = self._load_tasks(user_id)
        tags = set()
        for task in tasks:
            if task.status != TaskStatus.DELETED:
                tags.update(task.tags)
        return sorted(tags)

    def count_pending(self, user_id: str) -> int:
        """Count pending tasks"""
        tasks = self._load_tasks(user_id)
        return sum(1 for t in tasks if t.status == TaskStatus.PENDING)


if __name__ == "__main__":
    # Test the task manager
    manager = TaskManager("./data/tasks_test")
    test_user = "test-user-123"

    # Add some tasks
    task1 = manager.add(
        user_id=test_user,
        description="Review pull request",
        priority=Priority.HIGH,
        tags=["work", "code"],
        project="cass-vessel"
    )
    print(f"Created: {task1.description} (urgency: {task1.urgency})")

    task2 = manager.add(
        user_id=test_user,
        description="Buy groceries",
        priority=Priority.LOW,
        tags=["personal", "errands"]
    )
    print(f"Created: {task2.description} (urgency: {task2.urgency})")

    task3 = manager.add(
        user_id=test_user,
        description="Fix calendar bug",
        priority=Priority.MEDIUM,
        tags=["work", "code", "urgent"],
        project="cass-vessel"
    )
    print(f"Created: {task3.description} (urgency: {task3.urgency})")

    # List all tasks
    print("\nAll pending tasks (sorted by urgency):")
    for task in manager.list_tasks(test_user):
        tags_str = " ".join(f"+{t}" for t in task.tags)
        pri_str = f"[{task.priority.value}]" if task.priority != Priority.NONE else ""
        print(f"  {task.urgency:.1f} {pri_str} {task.description} {tags_str}")

    # Filter by tag
    print("\nTasks with +work tag:")
    for task in manager.list_tasks(test_user, "+work"):
        print(f"  {task.description}")

    # Filter by project
    print("\nTasks in project:cass-vessel:")
    for task in manager.list_tasks(test_user, "project:cass-vessel"):
        print(f"  {task.description}")

    # Complete a task
    manager.complete(test_user, task2.id)
    print(f"\nCompleted: {task2.description}")

    # Count pending
    print(f"\nPending tasks: {manager.count_pending(test_user)}")
