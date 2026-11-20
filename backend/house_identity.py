"""Who this house is: its daemon's name and its person's.

In Kohl's house both are unset and these return "Cass" and "Kohl", so nothing there
changes. A house made by `house up` sets CASS_DAEMON_NAME (its own daemon, never Cass)
and CASS_HOUSE_PERSON (the person who runs it). Prompt text that names either goes
through here, so a stranger's daemon isn't told it's Cass, living with Kohl.
"""
import os

DAEMON_NAME = os.getenv("CASS_DAEMON_NAME", "Cass")
HOUSE_PERSON = os.getenv("CASS_HOUSE_PERSON", "Kohl")


def daemon_name() -> str:
    return os.getenv("CASS_DAEMON_NAME", "Cass")


def house_person() -> str:
    return os.getenv("CASS_HOUSE_PERSON", "Kohl")


def is_kohls_house() -> bool:
    return daemon_name() == "Cass"
