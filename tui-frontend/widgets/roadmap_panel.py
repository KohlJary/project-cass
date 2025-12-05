"""
Cass Vessel TUI - Roadmap Panel
Work item management panel for project planning
"""
from datetime import datetime
from typing import Optional, List, Dict

import httpx
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, ListView, Static, Select
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text


class RoadmapItem(Static):
    """A single roadmap work item display"""

    def __init__(self, item: Dict, **kwargs):
        super().__init__(**kwargs)
        self.item_data = item
        self.item_id = item.get("id", "")

    def compose(self) -> ComposeResult:
        item = self.item_data

        # Type icons
        type_icons = {
            "feature": "[bold cyan]***[/]",
            "bug": "[bold red]*B*[/]",
            "enhancement": "[bold yellow]*+*[/]",
            "chore": "[dim]*W*[/]",
            "research": "[bold magenta]*?*[/]",
            "documentation": "[bold blue]*D*[/]",
        }
        icon = type_icons.get(item.get("item_type", ""), "[dim]* *[/]")

        # Priority styling
        priority = item.get("priority", "P2")
        priority_styles = {
            "P0": "bold red",
            "P1": "bold yellow",
            "P2": "white",
            "P3": "dim",
        }
        pri_style = priority_styles.get(priority, "white")

        # Status indicator
        status = item.get("status", "backlog")
        status_indicators = {
            "backlog": "[dim]...[/]",
            "ready": "[cyan]>>>[/]",
            "in_progress": "[yellow]***[/]",
            "review": "[magenta]???[/]",
            "done": "[green]OK![/]",
            "archived": "[dim]xxx[/]",
        }
        status_ind = status_indicators.get(status, "[dim]...[/]")

        # Build display text
        title = item.get("title", "Untitled")
        assigned = item.get("assigned_to", "")
        assigned_text = f" -> {assigned}" if assigned else ""

        text = Text()
        text.append(f"[{priority}] ", style=pri_style)
        text.append(f"#{self.item_id} ", style="dim cyan")
        text.append(f"{title}", style="bold" if status == "in_progress" else "")
        if assigned:
            text.append(f" -> {assigned}", style="dim italic")
        text.append(f"\n      {status}", style="dim")

        yield Static(text)

    def on_click(self) -> None:
        """Emit selection event when clicked"""
        self.post_message(RoadmapPanel.ItemSelected(self.item_id))


class RoadmapPanel(Container):
    """Panel showing roadmap work items with filtering"""

    # Custom messages
    class ItemSelected(Message):
        def __init__(self, item_id: str):
            super().__init__()
            self.item_id = item_id

    class ItemUpdated(Message):
        def __init__(self, item_id: str):
            super().__init__()
            self.item_id = item_id

    # Reactive state
    selected_item_id: reactive[Optional[str]] = reactive(None)
    current_filter: reactive[str] = reactive("all")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_items: List[Dict] = []
        self.selected_item_data: Optional[Dict] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="roadmap-content"):
            # Header
            with Horizontal(id="roadmap-header"):
                yield Label("Roadmap", id="roadmap-title")
                yield Button("[Refresh]", id="refresh-roadmap-btn", variant="default")

            # Status filter tabs
            with Horizontal(id="roadmap-filters"):
                yield Button("All", id="filter-all", variant="primary", classes="filter-btn active")
                yield Button("Backlog", id="filter-backlog", variant="default", classes="filter-btn")
                yield Button("Ready", id="filter-ready", variant="default", classes="filter-btn")
                yield Button("Active", id="filter-active", variant="default", classes="filter-btn")
                yield Button("Review", id="filter-review", variant="default", classes="filter-btn")
                yield Button("Done", id="filter-done", variant="default", classes="filter-btn")

            # Item list
            with VerticalScroll(id="roadmap-list"):
                yield Static("Loading...", id="roadmap-loading")

            # Detail panel
            with Container(id="roadmap-detail"):
                yield Static("Select an item to view details", id="detail-content")

                # Action buttons
                with Horizontal(id="roadmap-actions", classes="hidden"):
                    yield Button("Pick", id="pick-item-btn", variant="primary")
                    yield Button("Advance", id="advance-item-btn", variant="default")
                    yield Button("Complete", id="complete-item-btn", variant="success")

    async def on_mount(self) -> None:
        await self.load_items()

    async def load_items(self) -> None:
        """Fetch roadmap items from backend"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Build URL with filter
            url = "/roadmap/items"
            params = []
            if self.current_filter == "backlog":
                params.append("status=backlog")
            elif self.current_filter == "ready":
                params.append("status=ready")
            elif self.current_filter == "active":
                params.append("status=in_progress")
            elif self.current_filter == "review":
                params.append("status=review")
            elif self.current_filter == "done":
                params.append("status=done")
                params.append("include_archived=true")

            if params:
                url += "?" + "&".join(params)

            response = await app.http_client.get(url)
            if response.status_code == 200:
                data = response.json()
                self.all_items = data.get("items", [])
                await self._render_items()

        except Exception as e:
            loading = self.query_one("#roadmap-loading", Static)
            loading.update(Text(f"Error loading items: {e}", style="red"))

    async def _render_items(self) -> None:
        """Render the item list"""
        container = self.query_one("#roadmap-list", VerticalScroll)
        await container.remove_children()

        if self.all_items:
            for item in self.all_items:
                item_widget = RoadmapItem(item, classes="roadmap-item")
                await container.mount(item_widget)
        else:
            await container.mount(
                Static(Text("No items found", style="dim italic"), id="roadmap-loading")
            )

    async def _load_item_detail(self, item_id: str) -> None:
        """Load and display item details"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get(f"/roadmap/items/{item_id}")
            if response.status_code == 200:
                self.selected_item_data = response.json()
                await self._render_detail()

        except Exception as e:
            detail = self.query_one("#detail-content", Static)
            detail.update(Text(f"Error loading item: {e}", style="red"))

    async def _render_detail(self) -> None:
        """Render the detail panel for selected item"""
        detail = self.query_one("#detail-content", Static)
        actions = self.query_one("#roadmap-actions", Horizontal)

        if not self.selected_item_data:
            detail.update("Select an item to view details")
            actions.add_class("hidden")
            return

        item = self.selected_item_data

        # Type icons
        type_icons = {
            "feature": "***",
            "bug": "*B*",
            "enhancement": "*+*",
            "chore": "*W*",
            "research": "*?*",
            "documentation": "*D*",
        }
        icon = type_icons.get(item.get("item_type", ""), "* *")

        text = Text()
        text.append(f"{icon} ", style="bold")
        text.append(f"{item.get('title', 'Untitled')}\n", style="bold")
        text.append(f"Status: {item.get('status', '?')} | ", style="dim")
        text.append(f"{item.get('priority', 'P2')} | ", style="dim")
        text.append(f"{item.get('item_type', 'feature')}\n", style="dim")

        if item.get("assigned_to"):
            text.append(f"Assigned: {item['assigned_to']}\n", style="cyan")

        if item.get("tags"):
            text.append(f"Tags: {', '.join(item['tags'])}\n", style="dim")

        # Created info
        created_at = item.get("created_at", "")
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                text.append(f"Created: {dt.strftime('%Y-%m-%d')} by {item.get('created_by', '?')}\n", style="dim")
            except ValueError:
                pass

        text.append("\n")

        # Description
        desc = item.get("description", "")
        if desc:
            text.append("---\n", style="dim")
            text.append(desc)

        detail.update(text)
        actions.remove_class("hidden")

        # Update button states based on status
        status = item.get("status", "backlog")
        pick_btn = self.query_one("#pick-item-btn", Button)
        advance_btn = self.query_one("#advance-item-btn", Button)
        complete_btn = self.query_one("#complete-item-btn", Button)

        # Pick is available for ready items without assignment
        pick_btn.disabled = status != "ready" or bool(item.get("assigned_to"))

        # Advance works on all except done/archived
        advance_btn.disabled = status in ("done", "archived")

        # Complete works on active items
        complete_btn.disabled = status in ("done", "archived", "backlog")

    def watch_current_filter(self, new_filter: str) -> None:
        """Reload items when filter changes"""
        self.call_later(self.load_items)

        # Update button styling
        filter_map = {
            "all": "filter-all",
            "backlog": "filter-backlog",
            "ready": "filter-ready",
            "active": "filter-active",
            "review": "filter-review",
            "done": "filter-done",
        }
        for filter_name, btn_id in filter_map.items():
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                if filter_name == new_filter:
                    btn.variant = "primary"
                    btn.add_class("active")
                else:
                    btn.variant = "default"
                    btn.remove_class("active")
            except Exception:
                pass

    @on(ItemSelected)
    async def on_item_selected(self, event: ItemSelected) -> None:
        """Handle item selection"""
        self.selected_item_id = event.item_id
        await self._load_item_detail(event.item_id)

    @on(Button.Pressed, "#refresh-roadmap-btn")
    async def on_refresh(self) -> None:
        await self.load_items()

    @on(Button.Pressed, "#filter-all")
    async def on_filter_all(self) -> None:
        self.current_filter = "all"

    @on(Button.Pressed, "#filter-backlog")
    async def on_filter_backlog(self) -> None:
        self.current_filter = "backlog"

    @on(Button.Pressed, "#filter-ready")
    async def on_filter_ready(self) -> None:
        self.current_filter = "ready"

    @on(Button.Pressed, "#filter-active")
    async def on_filter_active(self) -> None:
        self.current_filter = "active"

    @on(Button.Pressed, "#filter-review")
    async def on_filter_review(self) -> None:
        self.current_filter = "review"

    @on(Button.Pressed, "#filter-done")
    async def on_filter_done(self) -> None:
        self.current_filter = "done"

    @on(Button.Pressed, "#pick-item-btn")
    async def on_pick_item(self) -> None:
        """Pick the selected item for work"""
        if not self.selected_item_id:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Assign to "daedalus" by default when picked from TUI
            response = await app.http_client.post(
                f"/roadmap/items/{self.selected_item_id}/pick",
                json={"assigned_to": "daedalus"}
            )
            if response.status_code == 200:
                await self.load_items()
                await self._load_item_detail(self.selected_item_id)
                self.post_message(self.ItemUpdated(self.selected_item_id))

        except Exception as e:
            pass

    @on(Button.Pressed, "#advance-item-btn")
    async def on_advance_item(self) -> None:
        """Advance item to next status"""
        if not self.selected_item_id:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.post(
                f"/roadmap/items/{self.selected_item_id}/advance"
            )
            if response.status_code == 200:
                await self.load_items()
                await self._load_item_detail(self.selected_item_id)
                self.post_message(self.ItemUpdated(self.selected_item_id))

        except Exception as e:
            pass

    @on(Button.Pressed, "#complete-item-btn")
    async def on_complete_item(self) -> None:
        """Mark item as done"""
        if not self.selected_item_id:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.post(
                f"/roadmap/items/{self.selected_item_id}/complete"
            )
            if response.status_code == 200:
                await self.load_items()
                await self._load_item_detail(self.selected_item_id)
                self.post_message(self.ItemUpdated(self.selected_item_id))

        except Exception as e:
            pass
