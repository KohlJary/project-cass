"""
Cass Vessel TUI - Sidebar Widgets
Sidebar components for navigation
"""
from typing import Optional, List, Dict

import httpx
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Label, ListView, ListItem, Rule, Static, Collapsible, RadioButton, RadioSet
from textual.reactive import reactive
from rich.text import Text

from .items import ProjectItem, ConversationItem, UserItem


# Forward declaration for debug_log - will be set by main module
def debug_log(message: str, level: str = "info"):
    """Log to debug panel if available, else print"""
    print(f"[{level.upper()}] {message}")


def set_debug_log(func):
    """Set the debug_log function from main module"""
    global debug_log
    debug_log = func


class UserSelector(Vertical):
    """User selector component for the sidebar"""

    current_user_id: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.users = []

    def compose(self) -> ComposeResult:
        yield Label("👤 User", id="user-header")
        yield Static("No user selected", id="current-user-display")
        yield Button("Switch User", id="switch-user-btn", variant="default")

    async def load_users(self, http_client: httpx.AsyncClient):
        """Load users and current user from backend"""
        try:
            # Get current user
            response = await http_client.get("/users/current")
            if response.status_code == 200:
                data = response.json()
                user = data.get("user")
                if user:
                    self.current_user_id = user.get("user_id")
                    display_name = user.get("display_name")
                    display = self.query_one("#current-user-display", Static)
                    display.update(Text(f"● {display_name}", style="bold green"))
                    # Update app's current user display name
                    app = self.app
                    if hasattr(app, 'current_user_display_name'):
                        app.current_user_display_name = display_name

            # Get all users
            response = await http_client.get("/users")
            if response.status_code == 200:
                data = response.json()
                self.users = data.get("users", [])

        except Exception as e:
            debug_log(f"Error loading users: {e}", "error")

    async def show_user_selector(self):
        """Show user selection modal"""
        app = self.app
        if hasattr(app, 'show_user_select_modal'):
            await app.show_user_select_modal(self.users, self.current_user_id)


# Static model lists for cloud providers
ANTHROPIC_MODELS = [
    ("claude-sonnet-4-20250514", "Claude Sonnet 4"),
    ("claude-opus-4-20250514", "Claude Opus 4"),
    ("claude-haiku-3-5-20241022", "Claude Haiku 3.5"),
]

OPENAI_MODELS = [
    ("gpt-4o", "GPT-4o"),
    ("gpt-4o-mini", "GPT-4o Mini"),
    ("gpt-4.1", "GPT-4.1"),
    ("gpt-5", "GPT-5"),
    ("gpt-5-mini", "GPT-5 Mini"),
    ("o4-mini", "o4-mini (reasoning)"),
    ("o3", "o3 (reasoning)"),
]


class LLMSelector(Vertical):
    """LLM provider and model selector"""

    current_provider: reactive[str] = reactive("anthropic")
    current_model: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ollama_models: List[tuple] = []  # List of (model_id, display_name)
        self.provider_available = {
            "anthropic": True,
            "openai": False,
            "local": False,
        }

    def compose(self) -> ComposeResult:
        with Collapsible(title="🤖 LLM Provider", collapsed=True, id="llm-collapsible"):
            # Provider selection
            yield Label("Provider", classes="llm-section-header")
            with RadioSet(id="provider-radio"):
                yield RadioButton("☁️ Anthropic", id="provider-anthropic", value=True)
                yield RadioButton("🌐 OpenAI", id="provider-openai")
                yield RadioButton("🖥️ Local", id="provider-local")

            yield Rule()

            # Model selection (changes based on provider)
            yield Label("Model", classes="llm-section-header")
            with RadioSet(id="model-radio"):
                # Default to Anthropic models
                for model_id, display_name in ANTHROPIC_MODELS:
                    yield RadioButton(display_name, id=f"model-{model_id}")

    async def load_provider_status(self, http_client: httpx.AsyncClient):
        """Load available providers and current selection from backend"""
        try:
            response = await http_client.get("/settings/llm-provider")
            if response.status_code == 200:
                data = response.json()
                self.current_provider = data.get("current", "anthropic")
                self.provider_available["openai"] = data.get("openai_enabled", False)
                self.provider_available["local"] = "local" in data.get("available", [])

                # Update provider radio buttons
                await self._update_provider_selection()

                # Get current model info
                if self.current_provider == "anthropic":
                    self.current_model = data.get("anthropic_model")
                elif self.current_provider == "openai":
                    self.current_model = data.get("openai_model")
                elif self.current_provider == "local":
                    self.current_model = data.get("local_model")

                await self._update_model_list()

        except Exception as e:
            debug_log(f"Error loading LLM provider status: {e}", "error")

    async def load_ollama_models(self, http_client: httpx.AsyncClient):
        """Fetch available Ollama models from backend"""
        try:
            response = await http_client.get("/settings/ollama-models")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                self.ollama_models = [(m, m) for m in models]  # model_id same as display
                debug_log(f"Loaded {len(self.ollama_models)} Ollama models")
        except Exception as e:
            debug_log(f"Error loading Ollama models: {e}", "error")

    async def _update_provider_selection(self):
        """Update the provider radio buttons to match current state"""
        try:
            radio_set = self.query_one("#provider-radio", RadioSet)

            # Enable/disable based on availability
            openai_btn = self.query_one("#provider-openai", RadioButton)
            local_btn = self.query_one("#provider-local", RadioButton)

            openai_btn.disabled = not self.provider_available["openai"]
            local_btn.disabled = not self.provider_available["local"]

            # Select current provider
            if self.current_provider == "anthropic":
                self.query_one("#provider-anthropic", RadioButton).value = True
            elif self.current_provider == "openai":
                self.query_one("#provider-openai", RadioButton).value = True
            elif self.current_provider == "local":
                self.query_one("#provider-local", RadioButton).value = True

        except Exception as e:
            debug_log(f"Error updating provider selection: {e}", "error")

    async def _update_model_list(self):
        """Update the model list based on current provider"""
        try:
            model_radio = self.query_one("#model-radio", RadioSet)

            # Clear existing models
            for child in list(model_radio.children):
                child.remove()

            # Add models for current provider
            if self.current_provider == "anthropic":
                models = ANTHROPIC_MODELS
            elif self.current_provider == "openai":
                models = OPENAI_MODELS
            elif self.current_provider == "local":
                models = self.ollama_models if self.ollama_models else [("llama3.1:8b-instruct-q8_0", "llama3.1:8b")]

            for model_id, display_name in models:
                btn = RadioButton(display_name, id=f"model-{model_id}")
                await model_radio.mount(btn)

                # Select current model if it matches
                if self.current_model and model_id == self.current_model:
                    btn.value = True

            # If no model selected, select first one
            if not self.current_model and models:
                first_btn = model_radio.query_one(f"#model-{models[0][0]}", RadioButton)
                first_btn.value = True

        except Exception as e:
            debug_log(f"Error updating model list: {e}", "error")

    async def on_radio_set_changed(self, event: RadioSet.Changed):
        """Handle provider or model selection changes"""
        radio_set = event.radio_set

        if radio_set.id == "provider-radio":
            # Provider changed
            pressed = event.pressed
            if pressed:
                new_provider = pressed.id.replace("provider-", "")
                if new_provider != self.current_provider:
                    await self._switch_provider(new_provider)

        elif radio_set.id == "model-radio":
            # Model changed
            pressed = event.pressed
            if pressed:
                new_model = pressed.id.replace("model-", "")
                if new_model != self.current_model:
                    await self._switch_model(new_model)

    async def _switch_provider(self, new_provider: str):
        """Switch to a new LLM provider"""
        app = self.app
        if not hasattr(app, 'http_client'):
            return

        try:
            response = await app.http_client.post(
                "/settings/llm-provider",
                json={"provider": new_provider}
            )
            if response.status_code == 200:
                self.current_provider = new_provider
                data = response.json()
                self.current_model = data.get("model")

                # Update model list for new provider
                if new_provider == "local" and not self.ollama_models:
                    await self.load_ollama_models(app.http_client)
                await self._update_model_list()

                # Update status bar
                if hasattr(app, 'update_llm_status'):
                    await app.update_llm_status()

                debug_log(f"Switched to {new_provider} provider", "success")

        except Exception as e:
            debug_log(f"Error switching provider: {e}", "error")

    async def _switch_model(self, new_model: str):
        """Switch to a new model within the current provider"""
        app = self.app
        if not hasattr(app, 'http_client'):
            return

        try:
            response = await app.http_client.post(
                "/settings/llm-model",
                json={"model": new_model}
            )
            if response.status_code == 200:
                self.current_model = new_model

                # Update status bar
                if hasattr(app, 'update_llm_status'):
                    await app.update_llm_status()

                debug_log(f"Switched to model: {new_model}", "success")

        except Exception as e:
            debug_log(f"Error switching model: {e}", "error")


class Sidebar(Vertical):
    """Sidebar showing projects and conversations"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.projects = []
        self.conversations = []
        self.selected_project_id: Optional[str] = None  # None = show all/unassigned

    def compose(self) -> ComposeResult:
        # User section
        yield UserSelector(id="user-selector")

        yield Rule()

        # Projects section
        yield Label("Projects", id="projects-header")
        yield Button("+ New Project", id="new-project-btn", variant="primary")
        yield ListView(id="project-list")

        # Conversations section
        yield Label("Conversations", id="conversations-header")
        yield Button("+ New Chat", id="new-conversation-btn", variant="success")
        yield ListView(id="conversation-list")

        yield Rule()

        # LLM Provider selector at bottom
        yield LLMSelector(id="llm-selector")

    async def load_projects(self, http_client: httpx.AsyncClient):
        """Load projects from backend"""
        try:
            debug_log("Fetching projects from backend...")
            response = await http_client.get("/projects")
            debug_log(f"Projects response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                self.projects = data.get("projects", [])
                debug_log(f"Loaded {len(self.projects)} projects", "success")
                await self.update_project_list()
            else:
                debug_log(f"Projects request failed: {response.text}", "error")
        except Exception as e:
            debug_log(f"Error loading projects: {e}", "error")

    async def update_project_list(self):
        """Update the project list display"""
        list_view = self.query_one("#project-list", ListView)
        await list_view.clear()

        # Add "All Conversations" option
        all_item = ListItem(Static(Text("📋 All Conversations", style="italic")))
        all_item.project_id = None
        await list_view.append(all_item)

        debug_log(f"Adding {len(self.projects)} projects to list")

        for proj in self.projects:
            debug_log(f"  → {proj['name']}", "debug")
            item = ProjectItem(
                proj["id"],
                proj["name"],
                proj.get("file_count", 0)
            )
            await list_view.append(item)

        debug_log(f"Project list updated with {len(self.projects) + 1} items", "success")

    async def load_conversations(self, http_client: httpx.AsyncClient):
        """Load conversations from backend"""
        try:
            if self.selected_project_id:
                # Load project-specific conversations
                response = await http_client.get(f"/projects/{self.selected_project_id}/conversations")
            else:
                # Load all conversations
                response = await http_client.get("/conversations")

            if response.status_code == 200:
                data = response.json()
                self.conversations = data.get("conversations", [])
                await self.update_conversation_list()
        except Exception:
            pass

    async def update_conversation_list(self):
        """Update the conversation list display"""
        list_view = self.query_one("#conversation-list", ListView)
        await list_view.clear()

        for conv in self.conversations:
            item = ConversationItem(
                conv["id"],
                conv["title"],
                conv.get("message_count", 0),
                conv.get("project_id")
            )
            await list_view.append(item)

    async def select_project(self, project_id: Optional[str], http_client: httpx.AsyncClient):
        """Select a project and reload conversations"""
        self.selected_project_id = project_id
        await self.load_conversations(http_client)
