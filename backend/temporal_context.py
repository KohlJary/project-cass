"""
Temporal Context Module

Provides rich temporal awareness for Cass:
- Upcoming holidays (US-focused, expandable)
- Cultural context (seasonal events, notable dates)
- Time-aware greetings and suggestions

Part of Phase 3: Contextual World Integration
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import calendar


@dataclass
class TemporalContext:
    """Rich temporal context for world awareness."""

    # Basic temporal
    date: str
    season: str
    time_of_day: str  # morning, afternoon, evening, night
    day_of_week: str
    is_weekend: bool

    # Enhanced awareness
    upcoming_holidays: List[str] = field(default_factory=list)  # Within next 2 weeks
    cultural_context: Optional[str] = None  # "approaching winter solstice", etc.

    # Contextual suggestions
    seasonal_note: Optional[str] = None  # Weather-appropriate suggestions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "season": self.season,
            "time_of_day": self.time_of_day,
            "day_of_week": self.day_of_week,
            "is_weekend": self.is_weekend,
            "upcoming_holidays": self.upcoming_holidays,
            "cultural_context": self.cultural_context,
            "seasonal_note": self.seasonal_note,
        }


# US Federal Holidays (month, day, name, is_fixed)
# For floating holidays, we calculate them dynamically
US_HOLIDAYS = [
    # Fixed date holidays
    (1, 1, "New Year's Day", True),
    (7, 4, "Independence Day", True),
    (11, 11, "Veterans Day", True),
    (12, 25, "Christmas Day", True),
    (12, 31, "New Year's Eve", True),
    (2, 14, "Valentine's Day", True),
    (3, 17, "St. Patrick's Day", True),
    (10, 31, "Halloween", True),

    # Floating holidays handled separately
]

# Cultural/seasonal events
CULTURAL_EVENTS = {
    # Winter solstice (around Dec 21)
    "winter_solstice": {"month": 12, "day": 21, "context": "winter solstice - the longest night"},
    # Summer solstice (around June 21)
    "summer_solstice": {"month": 6, "day": 21, "context": "summer solstice - the longest day"},
    # Spring equinox (around March 20)
    "spring_equinox": {"month": 3, "day": 20, "context": "spring equinox - equal day and night"},
    # Fall equinox (around Sept 22)
    "fall_equinox": {"month": 9, "day": 22, "context": "fall equinox - equal day and night"},
}


def get_nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> datetime:
    """
    Get the nth occurrence of a weekday in a month.

    Args:
        year: Year
        month: Month (1-12)
        weekday: Day of week (0=Monday, 6=Sunday)
        n: Which occurrence (1=first, 2=second, etc.)

    Returns:
        datetime of the nth weekday
    """
    first_day = datetime(year, month, 1)
    # Find first occurrence of the weekday
    days_until = (weekday - first_day.weekday()) % 7
    first_occurrence = first_day + timedelta(days=days_until)
    # Add weeks for nth occurrence
    return first_occurrence + timedelta(weeks=n - 1)


def get_last_weekday_of_month(year: int, month: int, weekday: int) -> datetime:
    """Get the last occurrence of a weekday in a month."""
    # Start from last day of month and work backwards
    if month == 12:
        last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)

    days_back = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=days_back)


def get_floating_holidays(year: int) -> List[tuple]:
    """
    Calculate floating US holidays for a given year.

    Returns list of (month, day, name) tuples.
    """
    holidays = []

    # MLK Day - 3rd Monday of January
    mlk = get_nth_weekday_of_month(year, 1, 0, 3)
    holidays.append((1, mlk.day, "Martin Luther King Jr. Day"))

    # Presidents Day - 3rd Monday of February
    pres = get_nth_weekday_of_month(year, 2, 0, 3)
    holidays.append((2, pres.day, "Presidents' Day"))

    # Memorial Day - Last Monday of May
    memorial = get_last_weekday_of_month(year, 5, 0)
    holidays.append((5, memorial.day, "Memorial Day"))

    # Labor Day - 1st Monday of September
    labor = get_nth_weekday_of_month(year, 9, 0, 1)
    holidays.append((9, labor.day, "Labor Day"))

    # Columbus Day - 2nd Monday of October
    columbus = get_nth_weekday_of_month(year, 10, 0, 2)
    holidays.append((10, columbus.day, "Indigenous Peoples' Day"))

    # Thanksgiving - 4th Thursday of November
    thanksgiving = get_nth_weekday_of_month(year, 11, 3, 4)
    holidays.append((11, thanksgiving.day, "Thanksgiving"))

    # Mother's Day - 2nd Sunday of May
    mothers = get_nth_weekday_of_month(year, 5, 6, 2)
    holidays.append((5, mothers.day, "Mother's Day"))

    # Father's Day - 3rd Sunday of June
    fathers = get_nth_weekday_of_month(year, 6, 6, 3)
    holidays.append((6, fathers.day, "Father's Day"))

    return holidays


def get_upcoming_holidays(now: Optional[datetime] = None, days_ahead: int = 14) -> List[str]:
    """
    Get holidays coming up in the next N days.

    Args:
        now: Current datetime (defaults to now)
        days_ahead: How many days to look ahead

    Returns:
        List of holiday names with relative timing
    """
    if now is None:
        now = datetime.now()

    upcoming = []
    end_date = now + timedelta(days=days_ahead)

    # Collect all holidays for current and next year (in case we're near year end)
    all_holidays = []

    for year in [now.year, now.year + 1]:
        # Fixed holidays
        for month, day, name, is_fixed in US_HOLIDAYS:
            if is_fixed:
                try:
                    holiday_date = datetime(year, month, day)
                    all_holidays.append((holiday_date, name))
                except ValueError:
                    pass  # Invalid date

        # Floating holidays
        for month, day, name in get_floating_holidays(year):
            try:
                holiday_date = datetime(year, month, day)
                all_holidays.append((holiday_date, name))
            except ValueError:
                pass

    # Filter to upcoming
    for holiday_date, name in all_holidays:
        if now.date() <= holiday_date.date() <= end_date.date():
            days_until = (holiday_date.date() - now.date()).days
            if days_until == 0:
                upcoming.append(f"{name} (today)")
            elif days_until == 1:
                upcoming.append(f"{name} (tomorrow)")
            else:
                upcoming.append(f"{name} (in {days_until} days)")

    return upcoming


def get_cultural_context(now: Optional[datetime] = None) -> Optional[str]:
    """
    Get cultural/seasonal context for the current time.

    Args:
        now: Current datetime (defaults to now)

    Returns:
        Cultural context string or None
    """
    if now is None:
        now = datetime.now()

    contexts = []

    # Check proximity to solstices and equinoxes
    for event_name, event_info in CULTURAL_EVENTS.items():
        event_date = datetime(now.year, event_info["month"], event_info["day"])
        days_until = (event_date.date() - now.date()).days

        if -1 <= days_until <= 1:
            contexts.append(f"at the {event_info['context']}")
        elif 2 <= days_until <= 7:
            contexts.append(f"approaching the {event_info['context']}")

    # Season-specific context
    month = now.month
    if month == 12 and now.day >= 20:
        contexts.append("holiday season")
    elif month == 1 and now.day <= 7:
        contexts.append("start of a new year")
    elif month == 3 and 15 <= now.day <= 21:
        contexts.append("transition to spring")
    elif month == 6 and 15 <= now.day <= 21:
        contexts.append("transition to summer")
    elif month == 9 and 15 <= now.day <= 23:
        contexts.append("transition to fall")
    elif month == 12 and 15 <= now.day <= 21:
        contexts.append("transition to winter")

    if contexts:
        return ", ".join(contexts)
    return None


def get_seasonal_note(season: str, weather_description: Optional[str] = None) -> Optional[str]:
    """
    Get a seasonal note that might influence suggestions.

    Args:
        season: Current season (winter, spring, summer, fall)
        weather_description: Current weather description

    Returns:
        Contextual note about the season/weather
    """
    weather_lower = (weather_description or "").lower()

    if season == "winter":
        if "snow" in weather_lower:
            return "snowy conditions - good for indoor activities"
        elif "rain" in weather_lower or "cold" in weather_lower:
            return "cold weather - warm drinks and indoor pursuits"
        return "winter - shorter days, time for reflection"

    elif season == "spring":
        if "rain" in weather_lower:
            return "spring showers - nature awakening"
        return "spring - renewal and new beginnings"

    elif season == "summer":
        if "hot" in weather_lower or "sunny" in weather_lower:
            return "warm weather - great for outdoor activities"
        return "summer - long days and possibilities"

    elif season == "fall":
        if "cool" in weather_lower or "crisp" in weather_lower:
            return "crisp fall air - harvest and transition"
        return "fall - change and preparation"

    return None


def calculate_temporal_context(
    now: Optional[datetime] = None,
    weather_description: Optional[str] = None
) -> TemporalContext:
    """
    Calculate complete temporal context for the current moment.

    Args:
        now: Current datetime (defaults to now)
        weather_description: Current weather for seasonal note

    Returns:
        TemporalContext with all fields populated
    """
    if now is None:
        now = datetime.now()

    # Calculate season
    month = now.month
    if month in [12, 1, 2]:
        season = "winter"
    elif month in [3, 4, 5]:
        season = "spring"
    elif month in [6, 7, 8]:
        season = "summer"
    else:
        season = "fall"

    # Calculate time of day
    hour = now.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"

    return TemporalContext(
        date=now.strftime("%A, %B %d, %Y"),
        season=season,
        time_of_day=time_of_day,
        day_of_week=calendar.day_name[now.weekday()],
        is_weekend=now.weekday() >= 5,
        upcoming_holidays=get_upcoming_holidays(now),
        cultural_context=get_cultural_context(now),
        seasonal_note=get_seasonal_note(season, weather_description),
    )
