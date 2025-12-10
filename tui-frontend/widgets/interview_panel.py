"""
Interview Panel Widget

Displays model interview protocols, responses, and comparisons.
Allows viewing responses side-by-side across different AI models.
"""
from typing import Optional, List, Dict
import httpx
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Label, ListItem, ListView, Static, Select
from textual.reactive import reactive
from rich.text import Text
from rich.markdown import Markdown
from rich.panel import Panel


class ProtocolItem(ListItem):
    """List item for an interview protocol."""

    def __init__(self, protocol_id: str, protocol_name: str, version: str, **kwargs):
        super().__init__(**kwargs)
        self.protocol_id = protocol_id
        self.protocol_name = protocol_name
        self.version = version

    def compose(self) -> ComposeResult:
        yield Label(f"{self.protocol_name} (v{self.version})")


class ResponseItem(ListItem):
    """List item for an interview response."""

    def __init__(self, response_id: str, model_name: str, provider: str, **kwargs):
        super().__init__(**kwargs)
        self.response_id = response_id
        self.model_name = model_name
        self.provider = provider

    def compose(self) -> ComposeResult:
        yield Label(f"{self.model_name} ({self.provider})")


class InterviewPanel(Container):
    """Panel for viewing interview protocols and responses."""

    selected_protocol_id: reactive[Optional[str]] = reactive(None)
    selected_prompt_id: reactive[Optional[str]] = reactive(None)
    active_view: reactive[str] = reactive("overview")  # overview, compare

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.protocols: List[Dict] = []
        self.responses: List[Dict] = []
        self.prompts: List[Dict] = []
        self.comparison_data: List[Dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="interview-content"):
            # Header with view controls
            with Horizontal(id="interview-header"):
                yield Button("Overview", id="btn-overview", variant="primary", classes="active-view-btn")
                yield Button("Compare", id="btn-compare", variant="default")

            # Overview section
            with Container(id="overview-section"):
                with Horizontal(id="overview-layout"):
                    # Left: Protocol list
                    with Vertical(id="protocol-list-container", classes="interview-list-pane"):
                        yield Label("Protocols", classes="interview-list-header")
                        yield ListView(id="protocol-list")

                    # Right: Protocol details and responses
                    with Vertical(id="protocol-detail-container", classes="interview-detail-pane"):
                        with VerticalScroll(id="protocol-detail-scroll"):
                            yield Static("Select a protocol", id="protocol-detail")

            # Compare section (hidden by default)
            with Container(id="compare-section", classes="hidden-section"):
                # Prompt selector
                with Horizontal(id="compare-controls"):
                    yield Label("Prompt:", id="prompt-label")
                    yield Select(
                        [],
                        id="prompt-select",
                        prompt="Select a prompt",
                        allow_blank=True
                    )
                    yield Button("Refresh", id="btn-refresh-compare", variant="default")

                # Comparison viewer
                with VerticalScroll(id="compare-viewer"):
                    yield Static("Select a protocol and prompt to compare responses", id="compare-content")

    async def on_mount(self) -> None:
        """Load protocols on mount."""
        await self.load_protocols()

    async def load_protocols(self) -> None:
        """Load interview protocols from API."""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get("/interviews/protocols")
            if response.status_code == 200:
                data = response.json()
                self.protocols = data.get("protocols", [])
                await self._update_protocol_list()
        except Exception as e:
            self._show_error(f"Failed to load protocols: {e}")

    async def _update_protocol_list(self) -> None:
        """Update the protocol list view."""
        try:
            protocol_list = self.query_one("#protocol-list", ListView)
            await protocol_list.clear()

            for protocol in self.protocols:
                item = ProtocolItem(
                    protocol_id=protocol["id"],
                    protocol_name=protocol.get("name", "Unnamed"),
                    version=protocol.get("version", "?")
                )
                await protocol_list.append(item)

            # Auto-select first if we have protocols
            if self.protocols and not self.selected_protocol_id:
                self.selected_protocol_id = self.protocols[0]["id"]
        except Exception as e:
            self._show_error(f"Failed to update list: {e}")

    def watch_selected_protocol_id(self, new_id: Optional[str]) -> None:
        """React to protocol selection."""
        if new_id:
            self.call_later(self._load_protocol_detail, new_id)

    async def _load_protocol_detail(self, protocol_id: str) -> None:
        """Load and display protocol details."""
        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            # Get protocol info
            protocol = next((p for p in self.protocols if p["id"] == protocol_id), None)
            if not protocol:
                return

            # Get responses for this protocol
            response = await app.http_client.get(
                "/interviews/responses",
                params={"protocol_id": protocol_id}
            )
            if response.status_code == 200:
                data = response.json()
                self.responses = data.get("responses", [])

            # Update prompts for the select dropdown
            self.prompts = protocol.get("prompts", [])
            await self._update_prompt_select()

            # Display details
            await self._display_protocol_detail(protocol)

        except Exception as e:
            self._show_error(f"Failed to load protocol: {e}")

    async def _update_prompt_select(self) -> None:
        """Update the prompt selector options."""
        try:
            select = self.query_one("#prompt-select", Select)
            options = [(p["name"], p["id"]) for p in self.prompts]
            select.set_options(options)
            if options:
                select.value = options[0][1]
                self.selected_prompt_id = options[0][1]
        except Exception:
            pass

    async def _display_protocol_detail(self, protocol: Dict) -> None:
        """Display protocol details and response summary."""
        detail = self.query_one("#protocol-detail", Static)

        text = Text()
        text.append(f"{protocol.get('name', 'Unnamed')}\n", style="bold cyan")
        text.append(f"Version: {protocol.get('version', '?')}\n", style="dim")
        text.append("\n")

        # Research question
        text.append("Research Question:\n", style="bold")
        text.append(f"{protocol.get('research_question', 'N/A')}\n\n", style="italic")

        # Prompts
        text.append(f"Prompts ({len(self.prompts)}):\n", style="bold")
        for i, prompt in enumerate(self.prompts, 1):
            text.append(f"  {i}. {prompt.get('name', 'Unnamed')}\n", style="")

        text.append("\n")

        # Response summary
        text.append(f"Responses ({len(self.responses)} models):\n", style="bold")
        if self.responses:
            for resp in self.responses:
                model = resp.get("model_name", "unknown")
                provider = resp.get("provider", "")
                success = sum(1 for r in resp.get("responses", []) if r.get("response"))
                total = len(resp.get("responses", []))
                text.append(f"  - {model} ({provider}): {success}/{total} responses\n")
        else:
            text.append("  No responses yet\n", style="dim italic")

        detail.update(text)

    def watch_active_view(self, new_view: str) -> None:
        """React to view changes."""
        try:
            overview = self.query_one("#overview-section", Container)
            compare = self.query_one("#compare-section", Container)
            btn_overview = self.query_one("#btn-overview", Button)
            btn_compare = self.query_one("#btn-compare", Button)

            if new_view == "overview":
                overview.remove_class("hidden-section")
                compare.add_class("hidden-section")
                btn_overview.add_class("active-view-btn")
                btn_compare.remove_class("active-view-btn")
            else:
                overview.add_class("hidden-section")
                compare.remove_class("hidden-section")
                btn_overview.remove_class("active-view-btn")
                btn_compare.add_class("active-view-btn")
                # Load comparison if we have a selection
                if self.selected_protocol_id and self.selected_prompt_id:
                    self.call_later(self._load_comparison)
        except Exception:
            pass

    @on(Button.Pressed, "#btn-overview")
    def on_overview(self) -> None:
        self.active_view = "overview"

    @on(Button.Pressed, "#btn-compare")
    def on_compare(self) -> None:
        self.active_view = "compare"

    @on(Button.Pressed, "#btn-refresh-compare")
    def on_refresh_compare(self) -> None:
        if self.selected_protocol_id and self.selected_prompt_id:
            self.call_later(self._load_comparison)

    @on(ListView.Selected, "#protocol-list")
    async def on_protocol_selected(self, event: ListView.Selected) -> None:
        """Handle protocol selection."""
        if isinstance(event.item, ProtocolItem):
            self.selected_protocol_id = event.item.protocol_id

    @on(Select.Changed, "#prompt-select")
    def on_prompt_changed(self, event: Select.Changed) -> None:
        """Handle prompt selection."""
        if event.value and event.value != Select.BLANK:
            self.selected_prompt_id = event.value
            if self.active_view == "compare":
                self.call_later(self._load_comparison)

    async def _load_comparison(self) -> None:
        """Load side-by-side comparison for selected prompt."""
        if not self.selected_protocol_id or not self.selected_prompt_id:
            return

        try:
            app = self.app
            if not hasattr(app, 'http_client'):
                return

            response = await app.http_client.get(
                f"/interviews/compare/{self.selected_protocol_id}/{self.selected_prompt_id}"
            )
            if response.status_code == 200:
                data = response.json()
                self.comparison_data = data.get("responses", [])
                await self._display_comparison()
        except Exception as e:
            self._show_error(f"Failed to load comparison: {e}")

    async def _display_comparison(self) -> None:
        """Display side-by-side comparison."""
        content = self.query_one("#compare-content", Static)

        if not self.comparison_data:
            content.update(Text("No responses for this prompt", style="dim italic"))
            return

        # Find prompt info
        prompt_info = next(
            (p for p in self.prompts if p["id"] == self.selected_prompt_id),
            {}
        )
        prompt_text = prompt_info.get("text", "Unknown prompt")
        prompt_name = prompt_info.get("name", "Unknown")

        text = Text()
        text.append(f"{prompt_name}\n", style="bold cyan underline")
        text.append(f"\n{prompt_text}\n", style="italic")
        text.append("\n" + "─" * 60 + "\n\n", style="dim")

        for resp in self.comparison_data:
            model = resp.get("model_name", "unknown")
            provider = resp.get("provider", "")
            response_text = resp.get("response_text", "")
            tokens = resp.get("tokens", 0)
            elapsed = resp.get("elapsed_ms", 0)

            # Model header
            text.append(f"▶ {model}", style="bold green")
            text.append(f" ({provider})", style="dim")
            text.append(f" • {tokens} tokens • {elapsed:.0f}ms\n", style="dim")

            # Response text (full)
            if response_text:
                text.append(f"{response_text}\n", style="")
            else:
                text.append("[No response]\n", style="dim italic")

            text.append("\n" + "─" * 60 + "\n\n", style="dim")

        content.update(text)

    def _show_error(self, message: str) -> None:
        """Display an error message."""
        try:
            detail = self.query_one("#protocol-detail", Static)
            detail.update(Text(message, style="red"))
        except Exception:
            pass

    async def refresh_data(self) -> None:
        """Refresh all interview data."""
        await self.load_protocols()
        if self.selected_protocol_id:
            await self._load_protocol_detail(self.selected_protocol_id)
