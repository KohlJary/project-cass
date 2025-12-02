#!/bin/bash
# Launch script for Cass Vessel TUI

# Change to script directory
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Check for --dev flag for hot reloading
if [[ "$1" == "--dev" ]]; then
    echo "Starting in dev mode with hot-reloading..."
    echo "Run 'textual console' in another terminal to see debug output."
    textual run --dev tui.py
else
    python tui.py
fi
