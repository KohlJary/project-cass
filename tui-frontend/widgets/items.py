"""
Cass Vessel TUI - List Item Widgets
Simple list item widgets for various data types
"""
from datetime import datetime
from typing import Optional, Dict

from textual import on
from textual.app import ComposeResult
from textual.widgets import ListItem, Static, Button
from rich.text import Text


class ProjectItem(ListItem):
    """A project in the sidebar list"""

    def __init__(self, project_id: str, project_name: str, file_count: int, **kwargs):
        super().__init__(**kwargs)
        self.project_id = project_id
        self.project_name = project_name
        self.file_count = file_count

    def compose(self) -> ComposeResult:
        text = Text()
        text.append("📁 ", style="dim")
        text.append(self.project_name, style="bold")
        text.append(f" ({self.file_count} files)", style="dim")
        yield Static(text)


class ConversationItem(ListItem):
    """A conversation in the sidebar list"""

    def __init__(self, conv_id: str, title: str, message_count: int, project_id: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.conv_id = conv_id
        self.title = title
        self.message_count = message_count
        self.project_id = project_id

    def compose(self) -> ComposeResult:
        text = Text()
        text.append(self.title, style="bold")
        text.append(f"\n{self.message_count} messages", style="dim")
        yield Static(text)


class UserItem(ListItem):
    """A user in the user list"""

    def __init__(self, user_id: str, display_name: str, relationship: str, is_current: bool = False):
        self.user_id = user_id
        self.display_name = display_name
        self.relationship = relationship
        self.is_current = is_current

        # Format the display
        icon = "👤" if relationship == "primary_partner" else "🧑"
        indicator = " ●" if is_current else ""
        style = "bold green" if is_current else ""

        super().__init__(Static(Text(f"{icon} {display_name}{indicator}", style=style)))


class DocumentItem(ListItem):
    """List item for a project document"""

    def __init__(self, doc_id: str, title: str, preview: str, **kwargs):
        super().__init__(**kwargs)
        self.doc_id = doc_id
        self.doc_title = title
        self.preview = preview

    def compose(self) -> ComposeResult:
        text = Text()
        text.append(f"📄 {self.doc_title}\n", style="bold")
        text.append(self.preview[:60] + "..." if len(self.preview) > 60 else self.preview, style="dim")
        yield Static(text)


class ObservationItem(Static):
    """A single observation that can be deleted"""

    # Category display styling
    CATEGORY_STYLES = {
        "interest": ("💡", "cyan"),
        "preference": ("⚙", "yellow"),
        "communication_style": ("💬", "magenta"),
        "background": ("📋", "blue"),
        "value": ("💎", "green"),
        "relationship_dynamic": ("🤝", "bright_magenta"),
    }

    def __init__(
        self,
        obs_id: str,
        text: str,
        timestamp: str,
        category: str = "background",
        confidence: float = 0.7,
        **kwargs
    ):
        self.obs_id = obs_id
        self.obs_text = text
        self.timestamp = timestamp
        self.category = category
        self.confidence = confidence
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        date_str = self.timestamp[:10] if self.timestamp else "?"

        # Get category styling
        icon, color = self.CATEGORY_STYLES.get(self.category, ("•", "dim"))

        # Build the observation display
        parts = []

        # Date
        parts.append((f"[{date_str}] ", "dim"))

        # Category icon and label
        category_label = self.category.replace("_", " ").title()
        parts.append((f"{icon} ", color))
        parts.append((f"[{category_label}] ", f"bold {color}"))

        # Confidence (only show if < 90%)
        if self.confidence < 0.9:
            conf_pct = int(self.confidence * 100)
            parts.append((f"({conf_pct}%) ", "dim"))

        # Observation text
        parts.append((self.obs_text, ""))

        yield Static(Text.assemble(*parts), classes="obs-text")
        yield Button("×", variant="error", classes="obs-delete-btn")


class EventItem(Static):
    """A single calendar event or reminder"""

    def __init__(self, event_data: Dict, **kwargs):
        super().__init__(**kwargs)
        self.event_data = event_data

    def compose(self) -> ComposeResult:
        event = self.event_data
        is_reminder = event.get("is_reminder", False)

        # Parse time
        start_time = event.get("start_time", "")
        try:
            dt = datetime.fromisoformat(start_time)
            time_str = dt.strftime("%H:%M")
            date_str = dt.strftime("%a %b %d")
        except Exception:
            time_str = "?"
            date_str = ""

        # Build display
        icon = "🔔" if is_reminder else "📅"
        title = event.get("title", "Untitled")
        completed = event.get("completed", False)

        text = Text()
        text.append(f"{icon} ", style="dim" if completed else "")
        text.append(f"{time_str} ", style="bold cyan" if not completed else "dim")
        text.append(title, style="strike dim" if completed else "bold")

        if date_str:
            text.append(f"\n   {date_str}", style="dim")

        if event.get("location"):
            text.append(f" @ {event['location']}", style="dim italic")

        if event.get("description"):
            desc = event["description"][:50]
            if len(event["description"]) > 50:
                desc += "..."
            text.append(f"\n   {desc}", style="dim")

        yield Static(text, classes="event-content")


class TaskItem(Static):
    """A single task item (Taskwarrior-style)"""

    def __init__(self, task_data: Dict, **kwargs):
        super().__init__(**kwargs)
        self.task_data = task_data

    def compose(self) -> ComposeResult:
        task = self.task_data
        priority = task.get("priority", "")
        tags = task.get("tags", [])
        project = task.get("project")
        urgency = task.get("urgency", 0.0)
        description = task.get("description", "")
        status = task.get("status", "pending")
        completed = status == "completed"

        text = Text()

        # Priority indicator
        if priority == "H":
            text.append("[H] ", style="bold red")
        elif priority == "M":
            text.append("[M] ", style="bold yellow")
        elif priority == "L":
            text.append("[L] ", style="bold blue")

        # Urgency score
        text.append(f"{urgency:>4.1f} ", style="dim cyan")

        # Description
        text.append(description, style="strike dim" if completed else "bold")

        # Tags
        if tags:
            tags_str = " ".join(f"+{t}" for t in tags)
            text.append(f"\n      {tags_str}", style="dim magenta")

        # Project
        if project:
            text.append(f" project:{project}", style="dim green")

        # Due date if present
        due = task.get("due")
        if due:
            try:
                due_dt = datetime.fromisoformat(due)
                due_str = due_dt.strftime("%Y-%m-%d")
                days_until = (due_dt.date() - datetime.now().date()).days
                if days_until < 0:
                    text.append(f" (overdue: {due_str})", style="bold red")
                elif days_until == 0:
                    text.append(f" (due today)", style="bold yellow")
                elif days_until <= 3:
                    text.append(f" (due: {due_str})", style="yellow")
                else:
                    text.append(f" (due: {due_str})", style="dim")
            except Exception:
                pass

        yield Static(text, classes="task-content")
