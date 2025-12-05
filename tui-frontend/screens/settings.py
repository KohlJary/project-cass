"""
Cass Vessel TUI - Settings Screen
Modal screen for user preferences and settings
"""
from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button, Label, Select, Static, Switch, Rule,
    TabbedContent, TabPane
)
from textual.screen import ModalScreen
from typing import Dict, Optional, List, Any


class SettingsScreen(ModalScreen):
    """Modal screen for user settings and preferences"""

    def __init__(
        self,
        preferences: Dict[str, Any],
        themes: List[Dict[str, str]],
        available_models: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.preferences = preferences
        self.themes = themes
        self.available_models = available_models or {}
        self.pending_changes: Dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Label("Settings", id="settings-title")
            yield Rule()

            with TabbedContent(id="settings-tabs"):
                # Appearance Tab
                with TabPane("Appearance", id="appearance-tab"):
                    with VerticalScroll(id="appearance-scroll"):
                        yield Label("Theme", classes="setting-label")
                        theme_options = [(t["name"], t["id"]) for t in self.themes]
                        # Get current theme preference, defaulting to cass-default
                        current_theme = self.preferences.get("theme", "cass-default")
                        # Handle legacy "default" value
                        if current_theme == "default":
                            current_theme = "cass-default"
                        yield Select(
                            options=theme_options,
                            value=current_theme,
                            id="theme-select"
                        )
                        yield Static(
                            "Choose a color scheme for the interface",
                            classes="setting-hint"
                        )

                        yield Rule(classes="setting-divider")

                        yield Label("Display Options", classes="setting-label")

                        with Horizontal(classes="setting-row"):
                            yield Label("Show timestamps", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("show_timestamps", True),
                                id="show-timestamps-switch"
                            )

                        with Horizontal(classes="setting-row"):
                            yield Label("Show token usage", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("show_token_usage", True),
                                id="show-token-usage-switch"
                            )

                        with Horizontal(classes="setting-row"):
                            yield Label("Auto-scroll chat", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("auto_scroll", True),
                                id="auto-scroll-switch"
                            )

                # Keybindings Tab
                with TabPane("Keybindings", id="keybindings-tab"):
                    with VerticalScroll(id="keybindings-scroll"):
                        yield Label("Navigation Mode", classes="setting-label")

                        with Horizontal(classes="setting-row"):
                            yield Label("Enable vim mode", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("vim_mode", False),
                                id="vim-mode-switch"
                            )

                        yield Static(
                            "Vim mode enables hjkl navigation, "
                            "normal/insert modes, and : command prefix",
                            classes="setting-hint"
                        )

                        yield Rule(classes="setting-divider")

                        yield Label("Current Shortcuts", classes="setting-label")
                        yield Static(
                            "Ctrl+X  Quit application\n"
                            "Ctrl+1  Switch to Cass tab\n"
                            "Ctrl+2  Switch to Daedalus tab\n"
                            "Ctrl+G  Growth tab\n"
                            "Ctrl+N  New conversation\n"
                            "Ctrl+R  Rename conversation\n"
                            "Ctrl+O  Cycle LLM providers\n"
                            "Ctrl+M  Toggle TTS mute\n"
                            "Ctrl+L  Clear chat\n"
                            "Ctrl+\\  Open settings",
                            classes="shortcuts-list"
                        )

                # Audio Tab
                with TabPane("Audio", id="audio-tab"):
                    with VerticalScroll(id="audio-scroll"):
                        yield Label("Text-to-Speech", classes="setting-label")

                        with Horizontal(classes="setting-row"):
                            yield Label("Enable TTS", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("tts_enabled", True),
                                id="tts-enabled-switch"
                            )

                        yield Static(
                            "When enabled, Cass's responses will be spoken aloud",
                            classes="setting-hint"
                        )

                # LLM Tab
                with TabPane("LLM", id="llm-tab"):
                    with VerticalScroll(id="llm-scroll"):
                        yield Label("Default Provider", classes="setting-label")
                        yield Select(
                            options=[
                                ("Anthropic Claude", "anthropic"),
                                ("OpenAI", "openai"),
                                ("Local (Ollama)", "local"),
                            ],
                            value=self.preferences.get("default_llm_provider", "anthropic"),
                            id="llm-provider-select"
                        )
                        yield Static(
                            "Provider used when starting new conversations",
                            classes="setting-hint"
                        )

                        yield Rule(classes="setting-divider")

                        # Anthropic default model
                        yield Label("Default Anthropic Model", classes="setting-label")
                        anthropic_models = self.available_models.get("anthropic", {}).get("models", [])
                        anthropic_options = [(m.get("name", m["id"]), m["id"]) for m in anthropic_models]
                        if not anthropic_options:
                            anthropic_options = [
                                ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
                                ("Claude Opus 4", "claude-opus-4-20250514"),
                                ("Claude Haiku 3.5", "claude-haiku-3-5-20241022"),
                            ]
                        yield Select(
                            options=anthropic_options,
                            value=self.preferences.get("default_anthropic_model") or anthropic_options[0][1],
                            id="anthropic-model-select"
                        )

                        yield Rule(classes="setting-divider")

                        # OpenAI default model
                        yield Label("Default OpenAI Model", classes="setting-label")
                        openai_models = self.available_models.get("openai", {}).get("models", [])
                        openai_options = [(m.get("name", m["id"]), m["id"]) for m in openai_models]
                        if not openai_options:
                            openai_options = [
                                ("GPT-4o", "gpt-4o"),
                                ("GPT-4o Mini", "gpt-4o-mini"),
                            ]
                        openai_enabled = self.available_models.get("openai", {}).get("enabled", False)
                        yield Select(
                            options=openai_options,
                            value=self.preferences.get("default_openai_model") or openai_options[0][1],
                            id="openai-model-select",
                            disabled=not openai_enabled
                        )
                        if not openai_enabled:
                            yield Static("OpenAI not configured", classes="setting-hint warning")

                        yield Rule(classes="setting-divider")

                        # Local/Ollama default model
                        yield Label("Default Local Model", classes="setting-label")
                        local_models = self.available_models.get("local", {}).get("models", [])
                        local_options = [(m.get("name", m["id"]), m["id"]) for m in local_models]
                        if not local_options:
                            local_options = [("No models installed", "")]
                        local_enabled = self.available_models.get("local", {}).get("enabled", False)
                        yield Select(
                            options=local_options,
                            value=self.preferences.get("default_local_model") or (local_options[0][1] if local_options else ""),
                            id="local-model-select",
                            disabled=not local_enabled or not local_options[0][1]
                        )
                        if not local_enabled:
                            yield Static("Ollama not configured", classes="setting-hint warning")
                        elif not local_options[0][1]:
                            yield Static("No local models installed", classes="setting-hint warning")

                        yield Rule(classes="setting-divider")

                        # Ollama model browser button
                        if local_enabled:
                            yield Button(
                                "🦙 Browse & Install Models",
                                id="ollama-browser-btn",
                                variant="primary"
                            )
                            yield Static(
                                "Browse available Ollama models and pull new ones",
                                classes="setting-hint"
                            )

                # Behavior Tab
                with TabPane("Behavior", id="behavior-tab"):
                    with VerticalScroll(id="behavior-scroll"):
                        yield Label("Confirmations", classes="setting-label")

                        with Horizontal(classes="setting-row"):
                            yield Label("Confirm before delete", classes="setting-name")
                            yield Switch(
                                value=self.preferences.get("confirm_delete", True),
                                id="confirm-delete-switch"
                            )

                        yield Static(
                            "Show confirmation dialog before deleting "
                            "conversations or other items",
                            classes="setting-hint"
                        )

            yield Rule()
            with Horizontal(id="settings-buttons"):
                yield Button("Save", variant="primary", id="settings-save")
                yield Button("Reset Defaults", variant="warning", id="settings-reset")
                yield Button("Cancel", variant="default", id="settings-cancel")

    def on_mount(self) -> None:
        """Focus the first tab when mounted"""
        pass

    def _collect_changes(self) -> Dict[str, Any]:
        """Collect all changed settings"""
        changes = {}

        # Theme
        theme_select = self.query_one("#theme-select", Select)
        if theme_select.value != Select.BLANK:
            if theme_select.value != self.preferences.get("theme"):
                changes["theme"] = theme_select.value

        # Display options
        show_timestamps = self.query_one("#show-timestamps-switch", Switch).value
        if show_timestamps != self.preferences.get("show_timestamps", True):
            changes["show_timestamps"] = show_timestamps

        show_token_usage = self.query_one("#show-token-usage-switch", Switch).value
        if show_token_usage != self.preferences.get("show_token_usage", True):
            changes["show_token_usage"] = show_token_usage

        auto_scroll = self.query_one("#auto-scroll-switch", Switch).value
        if auto_scroll != self.preferences.get("auto_scroll", True):
            changes["auto_scroll"] = auto_scroll

        # Vim mode
        vim_mode = self.query_one("#vim-mode-switch", Switch).value
        if vim_mode != self.preferences.get("vim_mode", False):
            changes["vim_mode"] = vim_mode

        # TTS
        tts_enabled = self.query_one("#tts-enabled-switch", Switch).value
        if tts_enabled != self.preferences.get("tts_enabled", True):
            changes["tts_enabled"] = tts_enabled

        # LLM Provider
        llm_select = self.query_one("#llm-provider-select", Select)
        if llm_select.value != Select.BLANK:
            if llm_select.value != self.preferences.get("default_llm_provider"):
                changes["default_llm_provider"] = llm_select.value

        # Default models per provider
        anthropic_select = self.query_one("#anthropic-model-select", Select)
        if anthropic_select.value != Select.BLANK:
            if anthropic_select.value != self.preferences.get("default_anthropic_model"):
                changes["default_anthropic_model"] = anthropic_select.value

        openai_select = self.query_one("#openai-model-select", Select)
        if openai_select.value != Select.BLANK and not openai_select.disabled:
            if openai_select.value != self.preferences.get("default_openai_model"):
                changes["default_openai_model"] = openai_select.value

        local_select = self.query_one("#local-model-select", Select)
        if local_select.value != Select.BLANK and not local_select.disabled and local_select.value:
            if local_select.value != self.preferences.get("default_local_model"):
                changes["default_local_model"] = local_select.value

        # Confirm delete
        confirm_delete = self.query_one("#confirm-delete-switch", Switch).value
        if confirm_delete != self.preferences.get("confirm_delete", True):
            changes["confirm_delete"] = confirm_delete

        return changes

    @on(Button.Pressed, "#settings-save")
    async def on_save(self):
        """Save settings and close"""
        changes = self._collect_changes()
        self.dismiss({"action": "save", "changes": changes})

    @on(Button.Pressed, "#settings-reset")
    async def on_reset(self):
        """Reset to defaults"""
        self.dismiss({"action": "reset"})

    @on(Button.Pressed, "#settings-cancel")
    async def on_cancel(self):
        """Cancel without saving"""
        self.dismiss(None)

    @on(Button.Pressed, "#ollama-browser-btn")
    async def on_ollama_browser(self):
        """Open the Ollama model browser"""
        # Dismiss settings and signal to open Ollama browser
        self.dismiss({"action": "open_ollama_browser"})
