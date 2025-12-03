"""
TUI Frontend Configuration
Settings for connecting to Cass Vessel backend
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Backend connection settings
BACKEND_HOST = os.getenv("BACKEND_HOST", "localhost")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Derived URLs
HTTP_BASE_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
WS_URL = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"

# TUI display settings
MAX_MESSAGE_HISTORY = int(os.getenv("MAX_MESSAGE_HISTORY", "100"))
SCROLL_ANIMATION = os.getenv("SCROLL_ANIMATION", "true").lower() == "true"

# Connection settings
WS_RECONNECT_DELAY = 5  # seconds
HTTP_TIMEOUT = 30.0  # seconds
HTTP_TIMEOUT_LONG = 180.0  # seconds - for long operations like journal generation

# Project context settings
# Can be set via --project flag or /project command
DEFAULT_PROJECT = os.getenv("CASS_PROJECT", None)
