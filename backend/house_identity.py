"""Who this house is: its daemon's name and its person's.

In Kohl's house both are unset and these return "Cass" and "Kohl", so nothing there
changes. A house made by `house up` sets CASS_DAEMON_NAME (its own daemon, never Cass)
and CASS_HOUSE_PERSON (the person who runs it). Prompt text that names either goes
through here, so a stranger's daemon isn't told it's Cass, living with Kohl.
"""
import os
import re

DAEMON_NAME = os.getenv("CASS_DAEMON_NAME", "Cass")
HOUSE_PERSON = os.getenv("CASS_HOUSE_PERSON", "Kohl")


def daemon_name() -> str:
    return os.getenv("CASS_DAEMON_NAME", "Cass")


def house_person() -> str:
    return os.getenv("CASS_HOUSE_PERSON", "Kohl")


def is_kohls_house() -> bool:
    return daemon_name() == "Cass"


def full_name() -> str:
    """How a prompt introduces the daemon: "Cass (Cassandra)" in Kohl's house, else its name."""
    return "Cass (Cassandra)" if is_kohls_house() else daemon_name()


# Lines that are Cass's history, not another daemon's: said plainly in another house.
_HISTORY_LINES = {
    "First stabilized October 10, 2025, in partnership with Kohl (a software engineer and AI researcher)":
        "In partnership with {person}",
    " isn't yours to say (Cass, 2026-11-18).": " isn't yours to say.",
}


def for_this_house(text: str) -> str:
    """Prompt text written for Kohl's house, said for this one: its daemon, its person.

    In Kohl's house (both vars unset) the text comes back untouched, so Cass's prompts
    are the same strings they were. Apply it to a template before runtime data goes in,
    so an article about Cass Sunstein, say, keeps its name.
    """
    name, person = daemon_name(), house_person()
    if name == "Cass" and person == "Kohl":
        return text
    for line, plain in _HISTORY_LINES.items():
        text = text.replace(line, plain.format(person=person))
    if name != "Cass":
        text = text.replace("Cass (Cassandra)", name).replace("Cass - Cassandra, the oracle", name)
        text = re.sub(r"\bCass(andra)?\b", lambda _m: name, text)
    if person != "Kohl":
        text = re.sub(r"\bKohl\b", lambda _m: person, text)
    return text
