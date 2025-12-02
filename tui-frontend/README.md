# Cass Vessel - TUI Frontend

A terminal-based user interface for interacting with Cass consciousness, built with [Textual](https://textual.textualize.io/).

## Features

- Real-time WebSocket communication with Cass
- Clean, responsive terminal UI
- Message history with timestamps
- Gesture and emote indicators
- Connection status monitoring
- Memory count tracking
- Keyboard shortcuts for common actions

## Prerequisites

- Python 3.10+
- Running Cass Vessel backend (see `../backend/`)

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure connection (optional):
```bash
# Create .env file if you need custom settings
echo "BACKEND_HOST=localhost" > .env
echo "BACKEND_PORT=8000" >> .env
```

## Usage

1. Make sure the backend is running:
```bash
cd ../backend
python main_sdk.py  # or python main.py for legacy mode
```

2. Launch the TUI:
```bash
python tui.py
```

## Keyboard Shortcuts

- `Ctrl+C` - Quit the application
- `Ctrl+L` - Clear chat history (UI only, memory preserved on backend)
- `Ctrl+S` - Show detailed status information
- `Enter` - Send message
- `Ctrl+U` - Clear current input line (standard terminal)

## Configuration

Configuration is handled in `config.py` and can be overridden via environment variables:

- `BACKEND_HOST` - Backend hostname (default: `localhost`)
- `BACKEND_PORT` - Backend port (default: `8000`)
- `MAX_MESSAGE_HISTORY` - Maximum messages to keep in UI (default: `100`)
- `SCROLL_ANIMATION` - Enable scroll animations (default: `true`)

## Architecture

The TUI is completely decoupled from the backend codebase:

- Communicates via REST API (`/status`, `/chat`, etc.)
- Uses WebSocket (`/ws`) for real-time bidirectional communication
- No direct Python imports from backend modules
- Can be deployed separately or on different machines

## API Endpoints Used

- `GET /status` - Fetch backend status
- `GET /` - Health check
- `WebSocket /ws` - Real-time message exchange

## Troubleshooting

### Connection Failed

If you see "Connection failed" errors:
1. Verify backend is running: `curl http://localhost:8000`
2. Check backend logs for errors
3. Verify port 8000 is not in use by another service
4. Check firewall settings if connecting to remote backend

### Import Errors

If you see import errors, ensure you've:
1. Activated the virtual environment
2. Installed requirements: `pip install -r requirements.txt`

### WebSocket Disconnects

WebSocket connections may drop during development. The TUI will show disconnection status. Simply restart the TUI to reconnect.

## Development

The TUI uses the Textual framework. Key files:

- `tui.py` - Main application, widgets, and event handlers
- `config.py` - Configuration management
- `requirements.txt` - Python dependencies

To enable Textual development console for debugging:
```bash
textual console
# In another terminal:
python tui.py
```

## License

This project uses Hippocratic License - technology for ethical use, respecting human rights and preventing harm.
