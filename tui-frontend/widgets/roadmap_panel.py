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
from textual.widgets import Button, Input, Label, ListView, Static, Select, Collapsible
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text


class MilestoneSection(Container):
    """A collapsible section for a milestone with its items"""

    def __init__(
        self,
        milestone_id: Optional[str],
        milestone_title: str,
        milestone_data: Optional[Dict],
        items: List[Dict],
        progress: Optional[Dict] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.milestone_id = milestone_id
        self.milestone_title = milestone_title
        self.milestone_data = milestone_data
        self.items = items
        self.progress = progress or {}
        self.collapsed = False

    def compose(self) -> ComposeResult:
        # Build parent/child hierarchy first to count visible items
        item_lookup = {item["id"]: item for item in self.items}
        child_ids = set()
        parent_children: Dict[str, List[Dict]] = {}

        for item in self.items:
            links = item.get("links", [])
            for link in links:
                if link.get("link_type") == "child":
                    # This item HAS a child; the target is the child
                    child_id = link.get("target_id")
                    if child_id:
                        child_ids.add(child_id)
                        if item["id"] not in parent_children:
                            parent_children[item["id"]] = []
                        if child_id in item_lookup:
                            if item_lookup[child_id] not in parent_children[item["id"]]:
                                parent_children[item["id"]].append(item_lookup[child_id])
                elif link.get("link_type") == "parent":
                    # This item HAS a parent; the target is the parent
                    parent_id = link.get("target_id")
                    if parent_id:
                        child_ids.add(item["id"])
                        if parent_id not in parent_children:
                            parent_children[parent_id] = []
                        if item not in parent_children[parent_id]:
                            parent_children[parent_id].append(item)

        # Count visible (top-level) items
        visible_count = sum(1 for item in self.items if item["id"] not in child_ids)

        # Build header text with progress
        header_text = Text()

        if self.milestone_id:
            # Regular milestone
            total = self.progress.get("total_items", len(self.items))
            done = self.progress.get("done_items", 0)
            pct = self.progress.get("progress_pct", 0)

            if pct >= 100:
                header_text.append("[OK] ", style="bold green")
            else:
                header_text.append("[>>] ", style="bold cyan")

            header_text.append(self.milestone_title, style="bold")

            # Show visible count, and total if different
            if visible_count < total:
                header_text.append(f"  ({visible_count} items, {done}/{total} tasks)", style="dim")
            else:
                header_text.append(f"  ({done}/{total})", style="dim")

            # Target date if set
            if self.milestone_data and self.milestone_data.get("target_date"):
                header_text.append(f"  Due: {self.milestone_data['target_date']}", style="dim yellow")
        else:
            # Unassigned section
            header_text.append("[..] ", style="dim")
            header_text.append(self.milestone_title, style="dim italic")
            if visible_count < len(self.items):
                header_text.append(f"  ({visible_count} items, {len(self.items)} tasks)", style="dim")
            else:
                header_text.append(f"  ({len(self.items)})", style="dim")

        with Collapsible(title=str(header_text), collapsed=self.collapsed):
            for item in self.items:
                item_id = item["id"]
                # Skip children (rendered under parent)
                if item_id in child_ids:
                    continue

                if item_id in parent_children and parent_children[item_id]:
                    yield ExpandableRoadmapItem(
                        item,
                        parent_children[item_id],
                        classes="roadmap-item expandable-item"
                    )
                else:
                    yield RoadmapItem(item, classes="roadmap-item")


class RoadmapItem(Static):
    """A single roadmap work item display"""

    def __init__(self, item: Dict, indent: int = 0, **kwargs):
        self.item_data = item
        self.item_id = item.get("id", "")
        self.indent = indent
        # Build the renderable text for this Static
        super().__init__(self._build_text(), **kwargs)

    def _build_text(self) -> Text:
        """Build the Rich Text for this item"""
        item = self.item_data

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

        # Build display text
        title = item.get("title", "Untitled")
        assigned = item.get("assigned_to", "")

        # Check for links/dependencies
        links = item.get("links", [])
        has_deps = any(l.get("link_type") == "depends_on" for l in links)
        has_links = len(links) > 0

        text = Text()

        # Add indentation for child items
        if self.indent > 0:
            text.append("  └─ ", style="dim")

        text.append(f"[{priority}] ", style=pri_style)

        # Show blocked indicator if has dependencies
        if has_deps:
            text.append("[!] ", style="bold red")
        elif has_links:
            text.append("[~] ", style="dim cyan")

        text.append(f"#{self.item_id[:8]} ", style="dim cyan")
        text.append(f"{title}", style="bold" if status == "in_progress" else "")
        if assigned:
            text.append(f" -> {assigned}", style="dim italic")
        text.append(f"\n      {status}", style="dim")

        return text

    def on_click(self, event) -> None:
        """Emit selection event when clicked"""
        event.stop()  # Prevent parent from also handling click
        self.post_message(RoadmapPanel.ItemSelected(self.item_id))


class ExpandableRoadmapItem(Container):
    """A roadmap item that can be expanded to show children using Collapsible"""

    def __init__(self, item: Dict, child_items: List[Dict], **kwargs):
        super().__init__(**kwargs)
        self.item_data = item
        self.item_id = item.get("id", "")
        self.child_items = child_items

    def compose(self) -> ComposeResult:
        item = self.item_data

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

        # Build title text
        title = item.get("title", "Untitled")
        assigned = item.get("assigned_to", "")

        # Check for links/dependencies
        links = item.get("links", [])
        has_deps = any(l.get("link_type") == "depends_on" for l in links)

        # Build the collapsible title
        title_parts = []
        title_parts.append(f"[{priority}]")
        if has_deps:
            title_parts.append("[!]")
        title_parts.append(f"#{self.item_id[:8]}")
        title_parts.append(title)
        title_parts.append(f"({len(self.child_items)})")
        if assigned:
            title_parts.append(f"-> {assigned}")

        collapsible_title = " ".join(title_parts)

        with Collapsible(title=collapsible_title, collapsed=True, classes="expandable-collapsible"):
            yield Static(f"        {status}", classes="parent-status")
            for child in self.child_items:
                yield RoadmapItem(child, indent=1, classes="roadmap-item child-item")

    def on_click(self, event) -> None:
        """Emit selection for the parent item"""
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
    project_id: reactive[Optional[str]] = reactive(None)
    show_all_projects: reactive[bool] = reactive(False)
    group_by_milestone: reactive[bool] = reactive(True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.all_items: List[Dict] = []
        self.milestones: List[Dict] = []
        self.milestone_progress: Dict[str, Dict] = {}
        self.selected_item_data: Optional[Dict] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="roadmap-content"):
            # Header
            with Horizontal(id="roadmap-header"):
                yield Label("Roadmap", id="roadmap-title")
                yield Label("", id="roadmap-scope-label", classes="scope-label")
                yield Button("Milestones", id="toggle-milestone-group-btn", variant="primary")
                yield Button("All Projects", id="toggle-all-projects-btn", variant="default")
                yield Button("Refresh", id="refresh-roadmap-btn", variant="default")

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
                    yield Button("Delete", id="delete-item-btn", variant="error")

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

            # Status filter
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

            # Project filter (unless showing all projects)
            if not self.show_all_projects and self.project_id:
                params.append(f"project_id={self.project_id}")

            if params:
                url += "?" + "&".join(params)

            response = await app.http_client.get(url)
            if response.status_code == 200:
                data = response.json()
                self.all_items = data.get("items", [])

            # Fetch milestones if grouping is enabled
            if self.group_by_milestone:
                await self._load_milestones()

            await self._render_items()

            # Update scope label
            await self._update_scope_label()

        except Exception as e:
            try:
                loading = self.query_one("#roadmap-loading", Static)
                loading.update(Text(f"Error loading items: {e}", style="red"))
            except Exception:
                pass

    async def _load_milestones(self) -> None:
        """Fetch milestones and their progress"""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Fetch milestones
            response = await app.http_client.get("/roadmap/milestones")
            if response.status_code == 200:
                data = response.json()
                self.milestones = data.get("milestones", [])

                # Fetch progress for each milestone
                self.milestone_progress = {}
                for milestone in self.milestones:
                    mid = milestone.get("id")
                    if mid:
                        prog_response = await app.http_client.get(f"/roadmap/milestones/{mid}/progress")
                        if prog_response.status_code == 200:
                            self.milestone_progress[mid] = prog_response.json()
        except Exception:
            pass

    async def _update_scope_label(self) -> None:
        """Update the scope label to show current filter scope"""
        try:
            label = self.query_one("#roadmap-scope-label", Label)
            toggle_btn = self.query_one("#toggle-all-projects-btn", Button)

            if self.show_all_projects:
                label.update("[dim](all projects)[/]")
                toggle_btn.label = "Current Project"
                toggle_btn.variant = "primary"
            elif self.project_id:
                # Try to get project name from app
                app = self.app
                project_name = None
                if hasattr(app, 'http_client'):
                    try:
                        response = await app.http_client.get(f"/projects/{self.project_id}")
                        if response.status_code == 200:
                            project_name = response.json().get("name", "")
                    except Exception:
                        pass
                if project_name:
                    label.update(f"[dim]({project_name})[/]")
                else:
                    label.update(f"[dim](project)[/]")
                toggle_btn.label = "All Projects"
                toggle_btn.variant = "default"
            else:
                label.update("[dim](no project)[/]")
                toggle_btn.label = "All Projects"
                toggle_btn.variant = "default"
        except Exception:
            pass

    async def _render_items(self) -> None:
        """Render the item list"""
        container = self.query_one("#roadmap-list", VerticalScroll)
        await container.remove_children()

        if not self.all_items:
            await container.mount(
                Static(Text("No items found", style="dim italic"), id="roadmap-loading")
            )
            return

        if self.group_by_milestone and self.milestones:
            # Group items by milestone
            await self._render_grouped_items(container)
        else:
            # Flat list with parent/child hierarchy
            await self._render_hierarchical_items(container, self.all_items)

    async def _render_hierarchical_items(self, container, items: List[Dict]) -> None:
        """Render items with parent/child hierarchy"""
        # Build lookup of item IDs to their data
        item_lookup = {item["id"]: item for item in items}

        # Find parent-child relationships
        # An item with "child" link to X means "I have X as a child"
        # An item with "parent" link to X means "X is my parent"
        child_ids = set()
        parent_children: Dict[str, List[Dict]] = {}

        for item in items:
            links = item.get("links", [])
            for link in links:
                if link.get("link_type") == "child":
                    # This item HAS a child; the target is the child
                    child_id = link.get("target_id")
                    if child_id:
                        child_ids.add(child_id)
                        if item["id"] not in parent_children:
                            parent_children[item["id"]] = []
                        if child_id in item_lookup:
                            # Avoid duplicates
                            if item_lookup[child_id] not in parent_children[item["id"]]:
                                parent_children[item["id"]].append(item_lookup[child_id])
                elif link.get("link_type") == "parent":
                    # This item HAS a parent; the target is the parent
                    parent_id = link.get("target_id")
                    if parent_id:
                        child_ids.add(item["id"])
                        if parent_id not in parent_children:
                            parent_children[parent_id] = []
                        if item not in parent_children[parent_id]:
                            parent_children[parent_id].append(item)

        # Render items: parents with children as expandable, others as regular
        for item in items:
            item_id = item["id"]

            # Skip items that are children (they'll be rendered under their parent)
            if item_id in child_ids:
                continue

            if item_id in parent_children and parent_children[item_id]:
                # This is a parent with children
                widget = ExpandableRoadmapItem(
                    item,
                    parent_children[item_id],
                    classes="roadmap-item expandable-item"
                )
            else:
                # Regular item (no children)
                widget = RoadmapItem(item, classes="roadmap-item")

            await container.mount(widget)

    async def _render_grouped_items(self, container: VerticalScroll) -> None:
        """Render items grouped by milestone"""
        # Build milestone lookup
        milestone_lookup = {m["id"]: m for m in self.milestones}

        # Group items by milestone_id
        grouped: Dict[Optional[str], List[Dict]] = {}
        for item in self.all_items:
            mid = item.get("milestone_id")
            if mid not in grouped:
                grouped[mid] = []
            grouped[mid].append(item)

        # Sort milestones: active first, then by target_date, then by title
        def milestone_sort_key(m: Dict) -> tuple:
            status_order = {"active": 0, "completed": 1, "archived": 2}
            status = m.get("status", "active")
            target_date = m.get("target_date") or "9999-99-99"
            return (status_order.get(status, 0), target_date, m.get("title", ""))

        sorted_milestones = sorted(self.milestones, key=milestone_sort_key)

        # Render milestone sections that have items in current filter
        for milestone in sorted_milestones:
            mid = milestone["id"]
            if mid in grouped and grouped[mid]:
                progress = self.milestone_progress.get(mid, {})
                is_completed = progress.get("progress_pct", 0) >= 100

                section = MilestoneSection(
                    milestone_id=mid,
                    milestone_title=milestone.get("title", "Untitled"),
                    milestone_data=milestone,
                    items=grouped[mid],
                    progress=progress,
                    classes="milestone-section" + (" completed" if is_completed else "")
                )
                await container.mount(section)

        # Render unassigned items at the end
        if None in grouped and grouped[None]:
            section = MilestoneSection(
                milestone_id=None,
                milestone_title="Unassigned",
                milestone_data=None,
                items=grouped[None],
                classes="milestone-section unassigned"
            )
            await container.mount(section)

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

        # Show links if any
        links = item.get("links", [])
        if links:
            text.append("Links:\n", style="bold")
            link_type_labels = {
                "depends_on": "Depends on",
                "blocks": "Blocks",
                "related": "Related to",
                "parent": "Parent of",
                "child": "Child of",
            }
            for link in links:
                ltype = link.get("link_type", "related")
                label = link_type_labels.get(ltype, ltype)
                target = link.get("target_id", "?")
                style = "bold red" if ltype == "depends_on" else "dim"
                text.append(f"  {label}: #{target}\n", style=style)
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

    def watch_project_id(self, new_project_id: Optional[str]) -> None:
        """Reload items when project changes"""
        self.call_later(self.load_items)

    def watch_show_all_projects(self, show_all: bool) -> None:
        """Reload items when scope changes"""
        self.call_later(self.load_items)

    def watch_group_by_milestone(self, group: bool) -> None:
        """Reload items when grouping mode changes"""
        self.call_later(self.load_items)

    def set_project(self, project_id: Optional[str]) -> None:
        """Set the active project (called by main app)"""
        self.project_id = project_id

    @on(ItemSelected)
    async def on_item_selected(self, event: ItemSelected) -> None:
        """Handle item selection"""
        self.selected_item_id = event.item_id
        await self._load_item_detail(event.item_id)

    @on(Button.Pressed, "#refresh-roadmap-btn")
    async def on_refresh(self) -> None:
        await self.load_items()

    @on(Button.Pressed, "#toggle-milestone-group-btn")
    async def on_toggle_milestone_group(self) -> None:
        """Toggle milestone grouping"""
        self.group_by_milestone = not self.group_by_milestone
        # Update button appearance
        try:
            btn = self.query_one("#toggle-milestone-group-btn", Button)
            if self.group_by_milestone:
                btn.variant = "primary"
                btn.label = "Milestones"
            else:
                btn.variant = "default"
                btn.label = "Flat List"
        except Exception:
            pass

    @on(Button.Pressed, "#toggle-all-projects-btn")
    async def on_toggle_all_projects(self) -> None:
        """Toggle between current project and all projects"""
        self.show_all_projects = not self.show_all_projects

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

    @on(Button.Pressed, "#delete-item-btn")
    async def on_delete_item(self) -> None:
        """Delete the selected item"""
        if not self.selected_item_id:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.delete(
                f"/roadmap/items/{self.selected_item_id}"
            )
            if response.status_code == 200:
                self.selected_item_id = None
                self.selected_item_data = None
                await self._render_detail()
                await self.load_items()

        except Exception as e:
            pass
