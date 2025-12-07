"""
Cass Vessel TUI - Ollama Model Browser
Modal screen for browsing, searching, and pulling Ollama models
"""
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button, Label, Select, Static, Input, Rule, DataTable, ListView, ListItem
)
from textual.screen import ModalScreen
from textual.worker import Worker, WorkerState
from typing import Callable, Dict, Optional, List
import httpx

from config import HTTP_BASE_URL


class TagSelectorScreen(ModalScreen):
    """Modal for selecting a model tag/variant before pulling"""

    CSS = """
    TagSelectorScreen {
        align: center middle;
    }

    #tag-selector-dialog {
        width: 50;
        max-height: 25;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }

    #tag-selector-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #tag-selector-model {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    #tag-list {
        height: auto;
        max-height: 12;
        margin-bottom: 1;
    }

    .tag-item {
        padding: 0 1;
    }

    .tag-installed {
        color: $success;
    }

    #tag-buttons {
        height: 3;
        align: center middle;
    }

    #tag-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, model_name: str, tags: List[str], installed: List[str], **kwargs):
        super().__init__(**kwargs)
        self.model_name = model_name
        self.tags = tags
        self.installed = installed

    def compose(self) -> ComposeResult:
        with Container(id="tag-selector-dialog"):
            yield Label("Select Tag/Size", id="tag-selector-title")
            yield Static(f"Model: {self.model_name}", id="tag-selector-model")
            yield Rule()
            yield ListView(id="tag-list")
            yield Rule()
            with Horizontal(id="tag-buttons"):
                yield Button("Pull", variant="primary", id="pull-tag-btn")
                yield Button("Cancel", variant="default", id="cancel-tag-btn")

    def on_mount(self) -> None:
        list_view = self.query_one("#tag-list", ListView)
        for tag in self.tags:
            full_name = f"{self.model_name}:{tag}"
            is_installed = any(full_name == inst or full_name.startswith(inst.rstrip(":")) for inst in self.installed)
            label_text = f"{'[green]✓[/] ' if is_installed else '  '}{tag}"
            item = ListItem(Label(label_text), id=f"tag-{tag}")
            item.data = tag  # Store the tag value
            list_view.append(item)
        if len(self.tags) > 0:
            list_view.index = 0

    @on(Button.Pressed, "#pull-tag-btn")
    def on_pull_pressed(self) -> None:
        list_view = self.query_one("#tag-list", ListView)
        if list_view.index is not None and list_view.index < len(self.tags):
            tag = self.tags[list_view.index]
            self.dismiss(f"{self.model_name}:{tag}")
        else:
            self.dismiss(None)

    @on(ListView.Selected, "#tag-list")
    def on_tag_selected(self, event: ListView.Selected) -> None:
        """Double-click to pull"""
        if event.item and hasattr(event.item, 'data'):
            self.dismiss(f"{self.model_name}:{event.item.data}")

    @on(Button.Pressed, "#cancel-tag-btn")
    def on_cancel_pressed(self) -> None:
        self.dismiss(None)


class OllamaModelBrowser(ModalScreen):
    """Modal screen for browsing and installing Ollama models"""

    # Callback for pulling models (runs on app, survives modal close)
    pull_callback: Optional[Callable[[str], None]] = None

    CSS = """
    OllamaModelBrowser {
        align: center middle;
    }

    #ollama-browser-dialog {
        width: 80%;
        max-width: 100;
        height: 80%;
        max-height: 40;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }

    #browser-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }

    #search-row {
        height: 3;
        margin-bottom: 1;
    }

    #search-input {
        width: 1fr;
    }

    #category-select {
        width: 20;
    }

    #models-table {
        height: 1fr;
        margin-bottom: 1;
    }

    #status-row {
        height: 3;
        margin-top: 1;
    }

    #status-text {
        width: 1fr;
    }

    #browser-buttons {
        height: 3;
        align: center middle;
    }

    #browser-buttons Button {
        margin: 0 1;
    }

    .installed-indicator {
        color: $success;
    }
    """

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        pull_callback: Optional[Callable[[str], None]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.http_client = http_client
        self.pull_callback = pull_callback
        self.library_models: List[Dict] = []
        self.installed_models: List[str] = []
        self.categories: List[str] = []

    def compose(self) -> ComposeResult:
        with Container(id="ollama-browser-dialog"):
            yield Label("Ollama Model Browser", id="browser-title")
            yield Rule()

            with Horizontal(id="search-row"):
                yield Input(placeholder="Search models...", id="search-input")
                yield Select(
                    options=[("All Categories", "all")],
                    value="all",
                    id="category-select"
                )
                yield Button("Refresh", id="refresh-btn", variant="default")

            yield DataTable(id="models-table")

            with Horizontal(id="status-row"):
                yield Static("", id="status-text")

            yield Rule()
            with Horizontal(id="browser-buttons"):
                yield Button("Pull Selected", variant="primary", id="pull-btn")
                yield Button("Delete Selected", variant="error", id="delete-btn")
                yield Button("Close", variant="default", id="close-btn")

    def on_mount(self) -> None:
        """Load data when mounted"""
        # Configure the table
        table = self.query_one("#models-table", DataTable)
        table.add_columns("", "Name", "Description", "Size", "Category")
        table.cursor_type = "row"

        # Load data in background thread
        self._set_status("Loading models...")
        self._load_data_in_thread()

    @work(thread=True)
    def _load_data_in_thread(self, category: str = None, search: str = None) -> Dict:
        """Load all data in a background thread"""
        result = {
            "installed": [],
            "library": [],
            "categories": [],
            "error": None
        }

        try:
            with httpx.Client(base_url=HTTP_BASE_URL, timeout=30.0) as client:
                # Load installed models
                try:
                    response = client.get("/settings/ollama-models")
                    if response.status_code == 200:
                        result["installed"] = response.json().get("models", [])
                except Exception:
                    pass

                # Load library models
                params = {}
                if category and category != "all":
                    params["category"] = category
                if search:
                    params["search"] = search

                response = client.get("/settings/ollama-library", params=params)
                if response.status_code == 200:
                    data = response.json()
                    result["library"] = data.get("models", [])
                    result["categories"] = data.get("categories", [])
        except Exception as e:
            result["error"] = str(e)

        return result

    def _update_ui_with_data(self, result: Dict, update_categories: bool = True) -> None:
        """Update UI with loaded data (called from main thread)"""
        if result.get("error"):
            self._set_status(f"Error: {result['error']}")
            return

        self.installed_models = result.get("installed", [])
        self.library_models = result.get("library", [])
        self.categories = result.get("categories", [])

        # Update category dropdown (only on initial load)
        if update_categories and self.categories:
            category_select = self.query_one("#category-select", Select)
            options = [("All Categories", "all")]
            for cat in self.categories:
                options.append((cat.title(), cat))
            category_select.set_options(options)
            category_select.value = "all"

        # Update table
        self._update_table()
        self._set_status(f"Loaded {len(self.library_models)} models")

    def _update_table(self) -> None:
        """Update the models table"""
        table = self.query_one("#models-table", DataTable)
        table.clear()

        for model in self.library_models:
            name = model.get("name", "")
            # Check if any installed model starts with this name (handles tags)
            is_installed = any(
                inst.startswith(name) or inst == name
                for inst in self.installed_models
            )
            installed_mark = "[green]OK[/]" if is_installed else ""

            table.add_row(
                installed_mark,
                name,
                model.get("description", "")[:40],
                model.get("size", "?"),
                model.get("category", ""),
                key=name
            )

    def _set_status(self, text: str) -> None:
        """Update status text"""
        status = self.query_one("#status-text", Static)
        status.update(text)

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Handle search input changes"""
        category_select = self.query_one("#category-select", Select)
        cat_val = category_select.value
        category = cat_val if cat_val not in ("all", Select.BLANK) else None
        self._set_status("Searching...")
        self._load_data_in_thread(category=category, search=event.value or None)

    @on(Select.Changed, "#category-select")
    def on_category_changed(self, event: Select.Changed) -> None:
        """Handle category filter changes"""
        search_input = self.query_one("#search-input", Input)
        category = event.value if event.value not in ("all", Select.BLANK) else None
        self._set_status("Filtering...")
        self._load_data_in_thread(category=category, search=search_input.value or None)

    @on(Button.Pressed, "#refresh-btn")
    def on_refresh(self) -> None:
        """Refresh the model lists"""
        self._set_status("Refreshing...")
        search_input = self.query_one("#search-input", Input)
        category_select = self.query_one("#category-select", Select)
        cat_val = category_select.value
        self._load_data_in_thread(
            category=cat_val if cat_val not in ("all", Select.BLANK) else None,
            search=search_input.value or None
        )

    @on(Button.Pressed, "#pull-btn")
    def on_pull(self) -> None:
        """Pull the selected model - fetch tags first"""
        table = self.query_one("#models-table", DataTable)
        if table.cursor_row is None:
            self._set_status("No model selected")
            return

        # Get row data - model name is in column 1
        row_data = table.get_row_at(table.cursor_row)
        if not row_data or len(row_data) < 2:
            return

        model_name = str(row_data[1])

        if not self.pull_callback:
            self._set_status("Pull not available")
            return

        # Fetch available tags for this model
        self._set_status(f"Loading tags for {model_name}...")
        self._fetch_tags_for_model(model_name)

    @work(thread=True)
    def _fetch_tags_for_model(self, model_name: str) -> Dict:
        """Fetch available tags for a model"""
        try:
            with httpx.Client(base_url=HTTP_BASE_URL, timeout=10.0) as client:
                response = client.get(f"/settings/ollama-tags/{model_name}")
                if response.status_code == 200:
                    return {"type": "tags", "data": response.json()}
        except Exception as e:
            return {"type": "tags", "error": str(e)}
        return {"type": "tags", "data": {"model": model_name, "tags": ["latest"], "installed": []}}

    def _show_tag_selector(self, model_name: str, tags: List[str], installed: List[str]) -> None:
        """Show the tag selector modal"""
        def handle_result(result: Optional[str]) -> None:
            if result and self.pull_callback:
                self.pull_callback(result)
                self._set_status(f"Started pulling {result} (safe to close)")
            else:
                self._set_status("Pull cancelled")

        self.app.push_screen(
            TagSelectorScreen(model_name, tags, installed),
            handle_result
        )

    @on(Button.Pressed, "#delete-btn")
    def on_delete(self) -> None:
        """Delete the selected model"""
        table = self.query_one("#models-table", DataTable)
        if table.cursor_row is None:
            self._set_status("No model selected")
            return

        # Get row data - model name is in column 1
        row_data = table.get_row_at(table.cursor_row)
        if not row_data or len(row_data) < 2:
            return

        model_name = str(row_data[1])

        # Check if installed
        if not any(inst.startswith(model_name) for inst in self.installed_models):
            self._set_status(f"{model_name} is not installed")
            return

        self._set_status(f"Deleting {model_name}...")
        self._delete_model(model_name)

    @work(thread=True)
    def _delete_model(self, model_name: str) -> Dict:
        """Delete a model (runs in thread)"""
        try:
            with httpx.Client(base_url=HTTP_BASE_URL, timeout=30.0) as client:
                response = client.delete(f"/settings/ollama-models/{model_name}")
                return {"type": "delete", "model": model_name, "result": response.json()}
        except Exception as e:
            return {"type": "delete", "model": model_name, "result": {"status": "error", "message": str(e)}}

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion"""
        if event.state != WorkerState.SUCCESS:
            if event.state == WorkerState.ERROR:
                self._set_status(f"Error: {event.worker.error}")
            return

        result = event.worker.result
        if result is None:
            return

        worker_name = event.worker.name

        if worker_name == "_load_data_in_thread":
            # Check if this is initial load (categories empty) or filter/search
            update_categories = len(self.categories) == 0
            self._update_ui_with_data(result, update_categories=update_categories)

        elif worker_name == "_delete_model":
            delete_result = result.get("result", {})
            model_name = result.get("model", "model")
            if delete_result.get("status") == "success":
                self._set_status(f"{model_name} deleted")
                # Refresh to update the table
                self._load_data_in_thread()
            else:
                self._set_status(f"Delete failed: {delete_result.get('message', 'Unknown error')}")

        elif worker_name == "_fetch_tags_for_model":
            if result.get("error"):
                self._set_status(f"Error fetching tags: {result['error']}")
                return
            data = result.get("data", {})
            model_name = data.get("model", "")
            tags = data.get("tags", ["latest"])
            installed = data.get("installed", [])
            self._show_tag_selector(model_name, tags, installed)

    @on(Button.Pressed, "#close-btn")
    def on_close(self) -> None:
        """Close the browser"""
        self.dismiss(None)
