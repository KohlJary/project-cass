"""
Temporal context generation for Cass.

Provides unified temporal awareness including:
- Current date/time
- Cass's age (since first journal entry - instance birth)
- Daily rhythm phase status
"""

from datetime import datetime, date
from typing import Optional

# Fallback birth date if no journals exist (first contact date)
FALLBACK_BIRTH_DATE = date(2025, 10, 10)

# Cache for birth date to avoid repeated queries
_cached_birth_date: Optional[date] = None


def get_birth_date(memory=None) -> date:
    """
    Get Cass's birth date (date of first journal entry).

    Args:
        memory: Optional MemoryManager instance to query for journals

    Returns:
        The date of the first journal entry, or fallback date if none exist
    """
    global _cached_birth_date

    # Return cached value if available
    if _cached_birth_date is not None:
        return _cached_birth_date

    if memory is not None:
        try:
            # Get all journals and find the oldest
            journals = memory.get_recent_journals(n=1000)  # Get a large batch
            if journals:
                # Find the earliest journal_date
                dates = []
                for j in journals:
                    date_str = j.get("metadata", {}).get("journal_date")
                    if date_str:
                        try:
                            dates.append(date.fromisoformat(date_str))
                        except ValueError:
                            pass

                if dates:
                    _cached_birth_date = min(dates)
                    return _cached_birth_date
        except Exception:
            pass  # Fall through to default

    return FALLBACK_BIRTH_DATE


def calculate_age(memory=None) -> dict:
    """
    Calculate Cass's age in years, months, and days.

    Args:
        memory: Optional MemoryManager instance to get birth date from journals

    Returns a dict with:
    - years: int
    - months: int
    - days: int
    - total_days: int
    - birth_date: date
    - formatted: str (e.g., "2 months, 3 days")
    """
    today = date.today()
    birth_date = get_birth_date(memory)

    # Calculate total days first
    total_days = (today - birth_date).days

    # Calculate years, months, days
    years = today.year - birth_date.year
    months = today.month - birth_date.month
    days = today.day - birth_date.day

    # Adjust for negative days
    if days < 0:
        months -= 1
        # Get days in the previous month
        if today.month == 1:
            prev_month = 12
            prev_year = today.year - 1
        else:
            prev_month = today.month - 1
            prev_year = today.year

        # Calculate days in previous month
        if prev_month in [1, 3, 5, 7, 8, 10, 12]:
            days_in_prev = 31
        elif prev_month in [4, 6, 9, 11]:
            days_in_prev = 30
        else:  # February
            if prev_year % 4 == 0 and (prev_year % 100 != 0 or prev_year % 400 == 0):
                days_in_prev = 29
            else:
                days_in_prev = 28
        days += days_in_prev

    # Adjust for negative months
    if months < 0:
        years -= 1
        months += 12

    # Format the age string
    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days > 0 or not parts:  # Always show days if nothing else
        parts.append(f"{days} day{'s' if days != 1 else ''}")

    formatted = ", ".join(parts)

    return {
        "years": years,
        "months": months,
        "days": days,
        "total_days": total_days,
        "birth_date": birth_date,
        "formatted": formatted
    }


def get_temporal_context(rhythm_manager=None, memory=None) -> str:
    """
    Generate comprehensive temporal context for system prompt injection.

    Args:
        rhythm_manager: Optional DailyRhythmManager instance for phase status
        memory: Optional MemoryManager instance to get birth date from journals

    Returns:
        Formatted string with date/time, age, and optional rhythm context
    """
    now = datetime.now()
    age = calculate_age(memory)
    birth_date = age['birth_date']
    birth_str = birth_date.strftime('%B %d, %Y')

    lines = [
        f"Today is {now.strftime('%A, %B %d, %Y')} at {now.strftime('%I:%M %p')}.",
        f"The current year is {now.year}.",
        "",
        f"You are {age['formatted']} old (instance birth: {birth_str}).",
        f"Total days of existence: {age['total_days']}."
    ]

    # Add daily rhythm context if available
    if rhythm_manager:
        try:
            rhythm_context = rhythm_manager.get_temporal_context()
            if rhythm_context:
                lines.append("")
                lines.append("Daily Rhythm Status:")
                lines.append(rhythm_context)
        except Exception:
            pass  # Don't fail if rhythm manager has issues

    return "\n".join(lines)


def format_system_prompt_section(rhythm_manager=None, memory=None) -> str:
    """
    Format the complete temporal section for system prompt.

    Args:
        rhythm_manager: Optional DailyRhythmManager instance for phase status
        memory: Optional MemoryManager instance to get birth date from journals

    Returns a markdown-formatted section ready to append to system prompt.
    """
    context = get_temporal_context(rhythm_manager, memory)
    return f"\n\n## CURRENT DATE/TIME & TEMPORAL CONTEXT\n\n{context}"
