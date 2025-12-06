"""
Cass Vessel TUI - Widget Components
Reusable UI widgets for the TUI frontend
"""
from .items import (
    ProjectItem,
    ConversationItem,
    UserItem,
    DocumentItem,
    ObservationItem,
    EventItem,
    TaskItem,
)
from .sidebar import Sidebar, UserSelector, LLMSelector
from .chat import ChatMessage, ChatContainer, CodeBlockWidget
from .panels import (
    DebugPanel,
    StatusBar,
    SummaryPanel,
    ProjectPanel,
    UserPanel,
    GrowthPanel,
    CalendarEventsPanel,
    TasksPanel,
    SelfModelPanel,
)
from .roadmap_panel import RoadmapPanel
from .calendar import CalendarDay, CalendarWidget, EventCalendarDay, EventCalendarWidget
from .daedalus import DaedalusWidget, PTYManager
from .daedalus_panels import SessionsPanel, FilesPanel, GitPanel, BuildPanel

__all__ = [
    # Items
    "ProjectItem",
    "ConversationItem",
    "UserItem",
    "DocumentItem",
    "ObservationItem",
    "EventItem",
    "TaskItem",
    # Sidebar
    "Sidebar",
    "UserSelector",
    "LLMSelector",
    # Chat
    "ChatMessage",
    "ChatContainer",
    "CodeBlockWidget",
    # Panels
    "DebugPanel",
    "StatusBar",
    "SummaryPanel",
    "ProjectPanel",
    "UserPanel",
    "GrowthPanel",
    "CalendarEventsPanel",
    "TasksPanel",
    "SelfModelPanel",
    # Roadmap
    "RoadmapPanel",
    # Calendar
    "CalendarDay",
    "CalendarWidget",
    "EventCalendarDay",
    "EventCalendarWidget",
    # Daedalus (Claude Code integration)
    "DaedalusWidget",
    "PTYManager",
    # Daedalus panels
    "SessionsPanel",
    "FilesPanel",
    "GitPanel",
    "BuildPanel",
]
