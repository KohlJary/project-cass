"""
Cass Vessel TUI - Calendar Widgets
Calendar display components for date selection
"""
import calendar as cal_module
from datetime import datetime, date
from typing import Optional, List

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label
from textual.reactive import reactive


class CalendarDay(Button):
    """A single day button in the calendar"""

    def __init__(self, day: int, is_current_month: bool, has_journal: bool, is_today: bool, date_str: str, **kwargs):
        self.day = day
        self.is_current_month = is_current_month
        self.has_journal = has_journal
        self.is_today = is_today
        self.date_str = date_str  # YYYY-MM-DD format

        # Build label
        label = str(day) if day > 0 else ""
        super().__init__(label, **kwargs)

    def on_mount(self) -> None:
        # Apply styling classes
        if not self.is_current_month:
            self.add_class("other-month")
        if self.has_journal:
            self.add_class("has-journal")
        if self.is_today:
            self.add_class("is-today")
        if self.day <= 0:
            self.add_class("empty-day")


class CalendarWidget(Container):
    """A month calendar widget for selecting days"""

    selected_date: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.journal_dates: set = set()  # Dates that have journal entries

    def compose(self) -> ComposeResult:
        # Month navigation header
        with Horizontal(id="calendar-nav"):
            yield Button("◀", id="prev-month", classes="nav-btn")
            yield Label(self._get_month_label(), id="month-label")
            yield Button("▶", id="next-month", classes="nav-btn")

        # Weekday headers
        with Horizontal(id="weekday-headers"):
            for day in ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]:
                yield Label(day, classes="weekday-header")

        # Calendar grid
        yield Container(id="calendar-grid")

    def _get_month_label(self) -> str:
        """Get formatted month/year label"""
        return f"{cal_module.month_name[self.current_month]} {self.current_year}"

    async def on_mount(self) -> None:
        await self._render_calendar()

    async def _render_calendar(self) -> None:
        """Render the calendar grid for the current month"""
        grid = self.query_one("#calendar-grid", Container)
        await grid.remove_children()

        # Update month label
        label = self.query_one("#month-label", Label)
        label.update(self._get_month_label())

        # Get calendar data
        calendar = cal_module.Calendar(firstweekday=6)  # Start on Sunday
        today = date.today()

        # Build weeks
        for week in calendar.monthdatescalendar(self.current_year, self.current_month):
            week_container = Horizontal(classes="calendar-week")
            await grid.mount(week_container)

            for day_date in week:
                is_current_month = day_date.month == self.current_month
                date_str = day_date.strftime("%Y-%m-%d")
                has_journal = date_str in self.journal_dates
                is_today = day_date == today

                day_btn = CalendarDay(
                    day=day_date.day if is_current_month else 0,
                    is_current_month=is_current_month,
                    has_journal=has_journal,
                    is_today=is_today,
                    date_str=date_str,
                    classes="calendar-day"
                )
                await week_container.mount(day_btn)

    @on(Button.Pressed, "#prev-month")
    async def on_prev_month(self) -> None:
        """Go to previous month"""
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        await self._render_calendar()

    @on(Button.Pressed, "#next-month")
    async def on_next_month(self) -> None:
        """Go to next month"""
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        await self._render_calendar()

    @on(Button.Pressed, ".calendar-day")
    async def on_day_pressed(self, event: Button.Pressed) -> None:
        """Handle day selection"""
        if isinstance(event.button, CalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str

    async def set_journal_dates(self, dates: List[str]) -> None:
        """Update which dates have journal entries"""
        self.journal_dates = set(dates)
        await self._render_calendar()


class EventCalendarDay(Button):
    """A single day button in the events calendar"""

    def __init__(self, day: int, is_current_month: bool, has_events: bool, is_today: bool, date_str: str, **kwargs):
        self.day = day
        self.is_current_month = is_current_month
        self.has_events = has_events
        self.is_today = is_today
        self.date_str = date_str

        label = str(day) if day > 0 else ""
        super().__init__(label, **kwargs)

    def on_mount(self) -> None:
        if not self.is_current_month:
            self.add_class("other-month")
        if self.has_events:
            self.add_class("has-events")
        if self.is_today:
            self.add_class("is-today")
        if self.day <= 0:
            self.add_class("empty-day")


class EventCalendarWidget(Container):
    """A month calendar widget for selecting days to view events"""

    selected_date: reactive[Optional[str]] = reactive(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_year = datetime.now().year
        self.current_month = datetime.now().month
        self.event_dates: set = set()

    def compose(self) -> ComposeResult:
        with Horizontal(id="event-calendar-nav"):
            yield Button("◀", id="event-prev-month", classes="nav-btn")
            yield Label(self._get_month_label(), id="event-month-label")
            yield Button("▶", id="event-next-month", classes="nav-btn")

        with Horizontal(id="event-weekday-headers"):
            for day in ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]:
                yield Label(day, classes="weekday-header")

        yield Container(id="event-calendar-grid")

    def _get_month_label(self) -> str:
        return f"{cal_module.month_name[self.current_month]} {self.current_year}"

    async def on_mount(self) -> None:
        await self._render_calendar()

    async def _render_calendar(self) -> None:
        grid = self.query_one("#event-calendar-grid", Container)
        await grid.remove_children()

        label = self.query_one("#event-month-label", Label)
        label.update(self._get_month_label())

        calendar = cal_module.Calendar(firstweekday=6)
        today = date.today()

        for week in calendar.monthdatescalendar(self.current_year, self.current_month):
            week_container = Horizontal(classes="calendar-week")
            await grid.mount(week_container)

            for day_date in week:
                is_current_month = day_date.month == self.current_month
                date_str = day_date.strftime("%Y-%m-%d")
                has_events = date_str in self.event_dates
                is_today = day_date == today

                day_btn = EventCalendarDay(
                    day=day_date.day if is_current_month else 0,
                    is_current_month=is_current_month,
                    has_events=has_events,
                    is_today=is_today,
                    date_str=date_str,
                    classes="calendar-day event-calendar-day"
                )
                await week_container.mount(day_btn)

    @on(Button.Pressed, "#event-prev-month")
    async def on_prev_month(self) -> None:
        if self.current_month == 1:
            self.current_month = 12
            self.current_year -= 1
        else:
            self.current_month -= 1
        await self._render_calendar()

    @on(Button.Pressed, "#event-next-month")
    async def on_next_month(self) -> None:
        if self.current_month == 12:
            self.current_month = 1
            self.current_year += 1
        else:
            self.current_month += 1
        await self._render_calendar()

    @on(Button.Pressed, ".event-calendar-day")
    async def on_day_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, EventCalendarDay):
            if event.button.is_current_month and event.button.day > 0:
                self.selected_date = event.button.date_str

    async def set_event_dates(self, dates: List[str]) -> None:
        self.event_dates = set(dates)
        await self._render_calendar()
