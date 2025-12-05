"""
Cass Vessel TUI - Theme System
Color schemes for the terminal interface

Uses Textual's built-in Theme system for proper color variable support.
Custom themes are registered on app startup and can be switched at runtime.
"""
from textual.theme import Theme
from typing import Dict, List


# ============================================================================
# Custom Cass Vessel Themes
# Uses Textual's Theme class for native integration
# ============================================================================

def get_custom_themes() -> Dict[str, Theme]:
    """
    Return custom themes for Cass Vessel.
    These supplement Textual's built-in themes (nord, gruvbox, tokyo-night, etc.)
    """
    return {
        # Default Cass Vessel theme - purple/magenta accents
        "cass-default": Theme(
            name="cass-default",
            primary="#9d4edd",      # Purple
            secondary="#00d4aa",    # Cyan/teal
            accent="#ff79c6",       # Pink accent
            background="#1a1a2e",   # Dark blue-gray
            surface="#16213e",      # Slightly lighter
            panel="#0f3460",        # Panel blue
            success="#00d26a",      # Green
            warning="#ffc107",      # Amber
            error="#ff4757",        # Red
            dark=True,
        ),

        # Srcery - High contrast with vibrant colors (Kohl's favorite)
        "srcery": Theme(
            name="srcery",
            primary="#fbb829",      # Bright yellow (distinctive)
            secondary="#2dc55e",    # Bright green
            accent="#98d1ce",       # Cyan
            background="#1c1b19",   # Hard black
            surface="#2d2c29",      # Dark gray
            panel="#3a3a37",        # Slightly lighter
            success="#2dc55e",      # Bright green
            warning="#fbb829",      # Yellow
            error="#ef2f27",        # Bright red
            dark=True,
        ),

        # Monokai - Classic sublime text theme
        "monokai": Theme(
            name="monokai",
            primary="#f92672",      # Pink
            secondary="#a6e22e",    # Green
            accent="#66d9ef",       # Cyan
            background="#272822",   # Dark olive
            surface="#3e3d32",      # Lighter olive
            panel="#49483e",        # Panel
            success="#a6e22e",      # Green
            warning="#e6db74",      # Yellow
            error="#f92672",        # Pink
            dark=True,
        ),

        # Solarized Dark
        "solarized-dark": Theme(
            name="solarized-dark",
            primary="#268bd2",      # Blue
            secondary="#2aa198",    # Cyan
            accent="#6c71c4",       # Violet
            background="#002b36",   # Base03
            surface="#073642",      # Base02
            panel="#073642",        # Base02
            success="#859900",      # Green
            warning="#b58900",      # Yellow
            error="#dc322f",        # Red
            dark=True,
        ),

        # Solarized Light
        "solarized-light": Theme(
            name="solarized-light",
            primary="#268bd2",      # Blue
            secondary="#2aa198",    # Cyan
            accent="#6c71c4",       # Violet
            background="#fdf6e3",   # Base3
            surface="#eee8d5",      # Base2
            panel="#eee8d5",        # Base2
            success="#859900",      # Green
            warning="#b58900",      # Yellow
            error="#dc322f",        # Red
            dark=False,
        ),

        # Dracula - Popular dark theme with purple accents
        "dracula": Theme(
            name="dracula",
            primary="#bd93f9",      # Purple
            secondary="#8be9fd",    # Cyan
            accent="#ff79c6",       # Pink
            background="#282a36",   # Background
            surface="#44475a",      # Current line
            panel="#44475a",        # Selection
            success="#50fa7b",      # Green
            warning="#ffb86c",      # Orange
            error="#ff5555",        # Red
            dark=True,
        ),

        # One Dark - Atom's iconic dark theme
        "one-dark": Theme(
            name="one-dark",
            primary="#61afef",      # Blue
            secondary="#56b6c2",    # Cyan
            accent="#c678dd",       # Purple
            background="#282c34",   # Bg
            surface="#21252b",      # Gutter
            panel="#2c313c",        # Selection
            success="#98c379",      # Green
            warning="#e5c07b",      # Yellow
            error="#e06c75",        # Red
            dark=True,
        ),
    }


def list_themes() -> List[Dict[str, str]]:
    """
    List all available themes (built-in + custom).
    Returns list suitable for settings UI.
    """
    # Built-in Textual themes
    themes = [
        {"id": "textual-dark", "name": "Textual Dark", "description": "Textual's default dark theme"},
        {"id": "textual-light", "name": "Textual Light", "description": "Textual's default light theme"},
        {"id": "nord", "name": "Nord", "description": "Arctic, north-bluish color palette"},
        {"id": "gruvbox", "name": "Gruvbox", "description": "Retro groove color scheme"},
        {"id": "tokyo-night", "name": "Tokyo Night", "description": "Dark theme inspired by Tokyo nights"},
    ]

    # Custom Cass themes
    custom_themes = [
        {"id": "cass-default", "name": "Cass Default", "description": "Cass Vessel purple/cyan theme"},
        {"id": "srcery", "name": "Srcery", "description": "High contrast with vibrant yellow"},
        {"id": "monokai", "name": "Monokai", "description": "Classic Sublime Text theme"},
        {"id": "solarized-dark", "name": "Solarized Dark", "description": "Precision colors for dark backgrounds"},
        {"id": "solarized-light", "name": "Solarized Light", "description": "Precision colors for light backgrounds"},
        {"id": "dracula", "name": "Dracula", "description": "Dark theme with purple accents"},
        {"id": "one-dark", "name": "One Dark", "description": "Atom's iconic dark theme"},
    ]

    return themes + custom_themes


def get_theme_id_for_preference(pref_id: str) -> str:
    """
    Map user preference theme ID to actual Textual theme name.
    Handles legacy/alias names.
    """
    # Map old names to new ones
    aliases = {
        "default": "cass-default",
        "gruvbox-dark": "gruvbox",
        "gruvbox-light": "gruvbox",  # Textual's gruvbox handles both
    }
    return aliases.get(pref_id, pref_id)
