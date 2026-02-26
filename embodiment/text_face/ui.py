"""
UI Framework for Sensor Module Pages

Provides base classes for UI elements, pages, and page management.
Designed to work alongside the TextFaceRenderer, shrinking the face
to make room for page content when pages are active.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Callable
import pygame


# =============================================================================
# Base Elements
# =============================================================================

@dataclass
class UIElement:
    """Base UI element with position and size."""
    x: int
    y: int
    width: int
    height: int

    def contains(self, px: int, py: int) -> bool:
        """Check if point is within element bounds."""
        return (self.x <= px < self.x + self.width and
                self.y <= py < self.y + self.height)

    def render(self, screen: pygame.Surface):
        """Render the element. Override in subclasses."""
        pass

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle pygame event. Return True if consumed."""
        return False


# =============================================================================
# Widgets
# =============================================================================

@dataclass
class Button(UIElement):
    """Clickable button with label and callback."""
    label: str = ""
    callback: Callable[[], None] = field(default=lambda: None)
    bg_color: tuple = (60, 60, 80)
    hover_color: tuple = (80, 80, 100)
    text_color: tuple = (200, 200, 220)
    font_size: int = 24
    _hovered: bool = field(default=False, repr=False)
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)

    def render(self, screen: pygame.Surface):
        """Render button with hover effect."""
        color = self.hover_color if self._hovered else self.bg_color

        # Draw rounded rect background
        pygame.draw.rect(
            screen, color,
            (self.x, self.y, self.width, self.height),
            border_radius=8
        )

        # Draw border
        pygame.draw.rect(
            screen, (100, 100, 120),
            (self.x, self.y, self.width, self.height),
            2, border_radius=8
        )

        # Render centered label
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        text = self._font.render(self.label, True, self.text_color)
        rect = text.get_rect(center=(
            self.x + self.width // 2,
            self.y + self.height // 2
        ))
        screen.blit(text, rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle mouse events for hover and click."""
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.contains(*event.pos)
            return False  # Don't consume motion events

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(*event.pos):
                self.callback()
                return True

        return False


@dataclass
class Label(UIElement):
    """Static text label."""
    text: str = ""
    color: tuple = (180, 140, 200)
    font_size: int = 24
    centered: bool = True
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)

    def render(self, screen: pygame.Surface):
        """Render the label text."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        text_surface = self._font.render(self.text, True, self.color)

        if self.centered:
            rect = text_surface.get_rect(center=(
                self.x + self.width // 2,
                self.y + self.height // 2
            ))
        else:
            rect = text_surface.get_rect(topleft=(self.x, self.y))

        screen.blit(text_surface, rect)


@dataclass
class Toggle(UIElement):
    """Toggle switch with label and state."""
    label: str = ""
    value: bool = False
    on_change: Callable[[bool], None] = field(default=lambda _: None)
    label_color: tuple = (180, 180, 200)
    on_color: tuple = (80, 180, 120)  # Green when on
    off_color: tuple = (80, 80, 100)  # Gray when off
    font_size: int = 20
    _hovered: bool = field(default=False, repr=False)
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)

    def render(self, screen: pygame.Surface):
        """Render toggle with label on left, switch on right."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        # Draw label on left
        text = self._font.render(self.label, True, self.label_color)
        text_rect = text.get_rect(midleft=(self.x + 10, self.y + self.height // 2))
        screen.blit(text, text_rect)

        # Draw toggle switch on right
        switch_width = 50
        switch_height = 26
        switch_x = self.x + self.width - switch_width - 10
        switch_y = self.y + (self.height - switch_height) // 2

        # Track background
        track_color = self.on_color if self.value else self.off_color
        if self._hovered:
            # Brighten on hover
            track_color = tuple(min(255, c + 30) for c in track_color)

        pygame.draw.rect(
            screen, track_color,
            (switch_x, switch_y, switch_width, switch_height),
            border_radius=switch_height // 2
        )

        # Knob
        knob_radius = switch_height // 2 - 3
        knob_x = switch_x + switch_width - knob_radius - 5 if self.value else switch_x + knob_radius + 5
        knob_y = switch_y + switch_height // 2
        pygame.draw.circle(screen, (240, 240, 240), (knob_x, knob_y), knob_radius)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle click to toggle value."""
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.contains(*event.pos)
            return False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(*event.pos):
                self.value = not self.value
                self.on_change(self.value)
                return True

        return False


@dataclass
class ValueDisplay(UIElement):
    """Display a label with a value (read-only)."""
    label: str = ""
    value: str = ""
    label_color: tuple = (140, 140, 160)
    value_color: tuple = (180, 180, 200)
    font_size: int = 18
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)

    def render(self, screen: pygame.Surface):
        """Render label: value pair."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        # Label on left
        label_text = self._font.render(self.label, True, self.label_color)
        label_rect = label_text.get_rect(midleft=(self.x + 10, self.y + self.height // 2))
        screen.blit(label_text, label_rect)

        # Value on right (truncate if too long)
        max_value_width = self.width - label_rect.width - 30
        value_str = self.value
        value_text = self._font.render(value_str, True, self.value_color)

        # Truncate with ellipsis if needed
        while value_text.get_width() > max_value_width and len(value_str) > 3:
            value_str = value_str[:-4] + "..."
            value_text = self._font.render(value_str, True, self.value_color)

        value_rect = value_text.get_rect(midright=(self.x + self.width - 10, self.y + self.height // 2))
        screen.blit(value_text, value_rect)


@dataclass
class Slider(UIElement):
    """
    Horizontal slider for selecting a value in a range.
    """
    label: str = ""
    min_value: float = 0.0
    max_value: float = 1.0
    value: float = 0.5
    step: float = 0.1
    on_change: Callable[[float], None] = field(default=lambda _: None)
    label_color: tuple = (180, 180, 200)
    track_color: tuple = (60, 60, 80)
    fill_color: tuple = (80, 140, 180)
    knob_color: tuple = (200, 200, 220)
    value_format: str = "{:.0%}"  # Format for displaying value
    font_size: int = 18
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)
    _dragging: bool = field(default=False, repr=False)

    def _get_track_rect(self) -> pygame.Rect:
        """Get the slider track rectangle."""
        track_height = 8
        track_y = self.y + self.height - 20
        return pygame.Rect(self.x + 10, track_y, self.width - 20, track_height)

    def _value_to_x(self, value: float) -> int:
        """Convert value to x position."""
        track = self._get_track_rect()
        t = (value - self.min_value) / (self.max_value - self.min_value)
        return int(track.x + t * track.width)

    def _x_to_value(self, x: int) -> float:
        """Convert x position to value."""
        track = self._get_track_rect()
        t = (x - track.x) / track.width
        t = max(0, min(1, t))
        raw_value = self.min_value + t * (self.max_value - self.min_value)
        # Round to step
        if self.step > 0:
            raw_value = round(raw_value / self.step) * self.step
        return max(self.min_value, min(self.max_value, raw_value))

    def render(self, screen: pygame.Surface):
        """Render the slider."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        track = self._get_track_rect()

        # Draw label on left
        label_text = self._font.render(self.label, True, self.label_color)
        label_rect = label_text.get_rect(midleft=(self.x + 10, self.y + 15))
        screen.blit(label_text, label_rect)

        # Draw value on right
        value_str = self.value_format.format(self.value)
        value_text = self._font.render(value_str, True, self.label_color)
        value_rect = value_text.get_rect(midright=(self.x + self.width - 10, self.y + 15))
        screen.blit(value_text, value_rect)

        # Draw track background
        pygame.draw.rect(screen, self.track_color, track, border_radius=4)

        # Draw filled portion
        knob_x = self._value_to_x(self.value)
        fill_rect = pygame.Rect(track.x, track.y, knob_x - track.x, track.height)
        if fill_rect.width > 0:
            pygame.draw.rect(screen, self.fill_color, fill_rect, border_radius=4)

        # Draw knob
        knob_radius = 10
        pygame.draw.circle(screen, self.knob_color, (knob_x, track.centery), knob_radius)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle mouse events for dragging."""
        track = self._get_track_rect()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check if clicking on or near the track
            expanded = track.inflate(20, 30)  # Larger hit area
            if expanded.collidepoint(event.pos):
                self._dragging = True
                new_value = self._x_to_value(event.pos[0])
                if new_value != self.value:
                    self.value = new_value
                    self.on_change(self.value)
                return True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._dragging:
                self._dragging = False
                return True

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                new_value = self._x_to_value(event.pos[0])
                if new_value != self.value:
                    self.value = new_value
                    self.on_change(self.value)
                return True

        return False


@dataclass
class Selector(UIElement):
    """
    Horizontal selector for choosing from a list of options.
    Shows current value with prev/next buttons.
    """
    label: str = ""
    options: List[str] = field(default_factory=list)
    selected_index: int = 0
    on_change: Callable[[str, int], None] = field(default=lambda v, i: None)
    label_color: tuple = (180, 180, 200)
    value_color: tuple = (100, 180, 200)  # Cyan for selected value
    button_color: tuple = (80, 80, 100)
    button_hover_color: tuple = (100, 100, 120)
    font_size: int = 20
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)
    _left_hovered: bool = field(default=False, repr=False)
    _right_hovered: bool = field(default=False, repr=False)

    @property
    def value(self) -> str:
        """Get currently selected value."""
        if 0 <= self.selected_index < len(self.options):
            return self.options[self.selected_index]
        return ""

    def _get_button_rects(self) -> tuple:
        """Get the left and right button rectangles."""
        btn_size = 30
        btn_y = self.y + (self.height - btn_size) // 2

        # Position buttons on right side
        right_btn_x = self.x + self.width - btn_size - 10
        left_btn_x = right_btn_x - btn_size - 5

        left_rect = pygame.Rect(left_btn_x, btn_y, btn_size, btn_size)
        right_rect = pygame.Rect(right_btn_x, btn_y, btn_size, btn_size)

        return left_rect, right_rect

    def render(self, screen: pygame.Surface):
        """Render selector with label, value, and nav buttons."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        # Draw label on left
        label_text = self._font.render(self.label, True, self.label_color)
        label_rect = label_text.get_rect(midleft=(self.x + 10, self.y + self.height // 2))
        screen.blit(label_text, label_rect)

        # Get button positions
        left_rect, right_rect = self._get_button_rects()

        # Draw value between label and buttons
        value_x = left_rect.x - 10
        value_text = self._font.render(self.value, True, self.value_color)
        value_rect = value_text.get_rect(midright=(value_x, self.y + self.height // 2))
        screen.blit(value_text, value_rect)

        # Draw navigation buttons
        left_color = self.button_hover_color if self._left_hovered else self.button_color
        right_color = self.button_hover_color if self._right_hovered else self.button_color

        pygame.draw.rect(screen, left_color, left_rect, border_radius=4)
        pygame.draw.rect(screen, right_color, right_rect, border_radius=4)

        # Draw arrows
        arrow_font = pygame.font.Font(None, 24)
        left_arrow = arrow_font.render("<", True, (200, 200, 220))
        right_arrow = arrow_font.render(">", True, (200, 200, 220))

        screen.blit(left_arrow, left_arrow.get_rect(center=left_rect.center))
        screen.blit(right_arrow, right_arrow.get_rect(center=right_rect.center))

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle clicks on nav buttons."""
        left_rect, right_rect = self._get_button_rects()

        if event.type == pygame.MOUSEMOTION:
            self._left_hovered = left_rect.collidepoint(event.pos)
            self._right_hovered = right_rect.collidepoint(event.pos)
            return False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if left_rect.collidepoint(event.pos):
                # Previous
                if self.selected_index > 0:
                    self.selected_index -= 1
                    self.on_change(self.value, self.selected_index)
                return True

            elif right_rect.collidepoint(event.pos):
                # Next
                if self.selected_index < len(self.options) - 1:
                    self.selected_index += 1
                    self.on_change(self.value, self.selected_index)
                return True

        return False


@dataclass
class TabBar(UIElement):
    """Horizontal tab bar for switching between views."""
    tabs: List[str] = field(default_factory=list)
    active_tab: int = 0
    on_tab_change: Callable[[int], None] = field(default=lambda _: None)
    active_color: tuple = (100, 80, 140)
    inactive_color: tuple = (50, 50, 70)
    text_color: tuple = (200, 200, 220)
    font_size: int = 18
    _font: Optional[pygame.font.Font] = field(default=None, repr=False)
    _tab_rects: List[pygame.Rect] = field(default_factory=list, repr=False)

    def render(self, screen: pygame.Surface):
        """Render tab bar with clickable tabs."""
        if self._font is None:
            self._font = pygame.font.Font(None, self.font_size)

        if not self.tabs:
            return

        tab_width = self.width // len(self.tabs)
        self._tab_rects = []

        for i, tab_name in enumerate(self.tabs):
            tab_x = self.x + i * tab_width
            tab_rect = pygame.Rect(tab_x, self.y, tab_width, self.height)
            self._tab_rects.append(tab_rect)

            # Background
            color = self.active_color if i == self.active_tab else self.inactive_color
            pygame.draw.rect(screen, color, tab_rect)

            # Border between tabs
            if i > 0:
                pygame.draw.line(
                    screen, (80, 80, 100),
                    (tab_x, self.y + 4), (tab_x, self.y + self.height - 4)
                )

            # Active indicator line at bottom
            if i == self.active_tab:
                pygame.draw.line(
                    screen, (140, 100, 180),
                    (tab_x + 10, self.y + self.height - 2),
                    (tab_x + tab_width - 10, self.y + self.height - 2),
                    2
                )

            # Tab text
            text = self._font.render(tab_name, True, self.text_color)
            text_rect = text.get_rect(center=(tab_x + tab_width // 2, self.y + self.height // 2))
            screen.blit(text, text_rect)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle click to switch tabs."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, rect in enumerate(self._tab_rects):
                if rect.collidepoint(event.pos):
                    if i != self.active_tab:
                        self.active_tab = i
                        self.on_tab_change(i)
                    return True
        return False


# =============================================================================
# Pages
# =============================================================================

class UIPage:
    """
    Base class for pages with UI elements.

    Pages are rendered in the content area below the mini face
    when active. They handle their own events and rendering.
    """

    def __init__(self, title: str = ""):
        self.title = title
        self.elements: List[UIElement] = []
        self._title_font: Optional[pygame.font.Font] = None

    def add_element(self, element: UIElement):
        """Add a UI element to the page."""
        self.elements.append(element)

    def render(self, screen: pygame.Surface, content_rect: pygame.Rect):
        """
        Render page content within the given rect.

        Args:
            screen: Pygame surface to render to
            content_rect: Available area for page content
        """
        # Render title in upper right (next to mini face)
        if self.title:
            if self._title_font is None:
                self._title_font = pygame.font.Font(None, 32)

            text = self._title_font.render(self.title, True, (180, 140, 200))
            # Position title to the right of mini face area
            screen.blit(text, (content_rect.x + 140, 30))

        # Render all elements
        for elem in self.elements:
            elem.render(screen)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """
        Handle event, return True if consumed.

        Events are passed to all elements; first consumer wins.
        """
        for elem in self.elements:
            if elem.handle_event(event):
                return True
        return False

    def on_enter(self):
        """Called when page becomes active. Override for setup."""
        pass

    def on_exit(self):
        """Called when page is removed. Override for cleanup."""
        pass


class TabbedPage(UIPage):
    """
    Page with tabbed sections.

    Each tab has its own list of elements that are shown/hidden
    based on the active tab.
    """

    def __init__(self, title: str = "", tabs: Optional[List[str]] = None):
        super().__init__(title)
        self.tab_names = tabs or []
        self.tab_elements: List[List[UIElement]] = [[] for _ in self.tab_names]
        self.active_tab = 0
        self._tab_bar: Optional[TabBar] = None

    def setup_tab_bar(self, x: int, y: int, width: int, height: int = 36):
        """Create the tab bar widget."""
        self._tab_bar = TabBar(
            x=x, y=y, width=width, height=height,
            tabs=self.tab_names,
            active_tab=self.active_tab,
            on_tab_change=self._on_tab_change
        )

    def _on_tab_change(self, tab_index: int):
        """Handle tab switch."""
        self.active_tab = tab_index

    def add_to_tab(self, tab_index: int, element: UIElement):
        """Add element to a specific tab."""
        if 0 <= tab_index < len(self.tab_elements):
            self.tab_elements[tab_index].append(element)

    def render(self, screen: pygame.Surface, content_rect: pygame.Rect):
        """Render tab bar and active tab's elements."""
        # Render title
        if self.title:
            if self._title_font is None:
                self._title_font = pygame.font.Font(None, 32)
            text = self._title_font.render(self.title, True, (180, 140, 200))
            screen.blit(text, (content_rect.x + 140, 30))

        # Render tab bar
        if self._tab_bar:
            self._tab_bar.render(screen)

        # Render common elements
        for elem in self.elements:
            elem.render(screen)

        # Render active tab's elements
        if 0 <= self.active_tab < len(self.tab_elements):
            for elem in self.tab_elements[self.active_tab]:
                elem.render(screen)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events for tab bar and active tab's elements."""
        # Tab bar first
        if self._tab_bar and self._tab_bar.handle_event(event):
            return True

        # Common elements
        for elem in self.elements:
            if elem.handle_event(event):
                return True

        # Active tab's elements
        if 0 <= self.active_tab < len(self.tab_elements):
            for elem in self.tab_elements[self.active_tab]:
                if elem.handle_event(event):
                    return True

        return False


# =============================================================================
# Page Manager
# =============================================================================

class PageManager:
    """
    Manages a stack of pages with transitions.

    When pages are active, the face renderer should switch to
    mini face mode to make room for page content.
    """

    def __init__(self):
        self._pages: List[UIPage] = []

    @property
    def active_page(self) -> Optional[UIPage]:
        """Get the currently active (top) page."""
        return self._pages[-1] if self._pages else None

    @property
    def has_page(self) -> bool:
        """Check if any page is active."""
        return len(self._pages) > 0

    @property
    def depth(self) -> int:
        """Number of pages in the stack."""
        return len(self._pages)

    def push(self, page: UIPage):
        """Push a new page onto the stack."""
        self._pages.append(page)
        page.on_enter()

    def pop(self) -> Optional[UIPage]:
        """Pop the top page from the stack."""
        if self._pages:
            page = self._pages.pop()
            page.on_exit()
            return page
        return None

    def clear(self):
        """Clear all pages from the stack."""
        while self._pages:
            page = self._pages.pop()
            page.on_exit()

    def replace(self, page: UIPage):
        """Replace the current page with a new one."""
        if self._pages:
            old = self._pages.pop()
            old.on_exit()
        self._pages.append(page)
        page.on_enter()
