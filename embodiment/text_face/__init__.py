"""
Text Face - Cass embodiment display system.

Provides:
- TextFaceRenderer: Main face rendering with particle-based text animation
- UI framework: Pages, buttons, labels for overlay interfaces
- PageManager: Stack-based page navigation
- TabbedPage: Pages with tab navigation
- Widgets: Toggle, ValueDisplay, TabBar
"""

from .text_face import TextFaceRenderer, TEMPLE_FRAGMENTS, TEXT_POOL
from .ui import (
    PageManager, UIPage, TabbedPage, UIElement,
    Button, Label, Toggle, ValueDisplay, Selector, Slider, TabBar
)

__all__ = [
    "TextFaceRenderer",
    "TEMPLE_FRAGMENTS",
    "TEXT_POOL",
    "PageManager",
    "UIPage",
    "TabbedPage",
    "UIElement",
    "Button",
    "Label",
    "Toggle",
    "ValueDisplay",
    "Selector",
    "Slider",
    "TabBar",
]
