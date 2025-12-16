# Deployment Guide

## Railway Deployment

### Quick Start

1. Connect your GitHub repo to Railway
2. Set environment variables (see below)
3. Deploy

### Required Environment Variables

Set these in Railway dashboard under Variables:

```
# LLM API Keys (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...      # Optional
OPENAI_ENABLED=true              # Set to true if using OpenAI

# Security
JWT_SECRET_KEY=your-secret-key-min-32-chars
DEMO_MODE=false                  # Set true for public demo (no auth required)

# Server Config
HOST=0.0.0.0
PORT=8000

# Optional
DEBUG=false
ALLOWED_ORIGINS=https://your-domain.railway.app
```

### Environment Variable Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | Claude API key |
| `OPENAI_API_KEY` | No | OpenAI API key (if OPENAI_ENABLED=true) |
| `OPENAI_ENABLED` | No | Enable OpenAI provider (default: false) |
| `JWT_SECRET_KEY` | Yes | Secret for JWT tokens (min 32 chars) |
| `DEMO_MODE` | No | Skip auth for demo (default: false) |
| `HOST` | No | Server host (default: 127.0.0.1) |
| `PORT` | No | Server port (default: 8000) |
| `DEBUG` | No | Enable debug logging (default: false) |
| `ALLOWED_ORIGINS` | No | CORS origins (comma-separated) |
| `BOOTSTRAP_FROM_SEED` | No | Path to .anima seed file to import on first boot |

*At least one LLM API key required

### Bootstrap from Seed

To initialize a fresh deployment with existing data, set `BOOTSTRAP_FROM_SEED` to the path of an `.anima` export file. On startup, if the database is empty, the seed data will be imported automatically.

```bash
# Example: bootstrap from seed in the repository
BOOTSTRAP_FROM_SEED=seed/cass_export_20251215.anima
```

This is useful for:
- Friends & family demos with pre-existing Cass data
- Restoring from backup after data loss
- Setting up test environments with known state

The import runs with `skip_embeddings=True` for faster startup - ChromaDB embeddings will be regenerated as needed.

### Data Persistence

Railway provides ephemeral storage by default. For persistent data:

1. Create a Railway Volume
2. Mount it at `/app/data`
3. The app stores:
   - SQLite database: `data/cass.db`
   - Vector store: `data/chroma/`
   - Conversations, journals, etc.

### Build Process

Railway will automatically:
1. Detect Python + Node.js
2. Install backend dependencies (`pip install -r requirements.txt`)
3. Build frontend (`npm install && npm run build`)
4. Start server (`python main_sdk.py`)

### Health Check

The app exposes `/health` endpoint for Railway health checks.

### TTS Note

Piper TTS requires ONNX runtime. If TTS fails on Railway:
- TTS is optional - chat will work without it
- Audio playback buttons will be disabled

## Manual Deployment

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main_sdk.py

# Frontend (in another terminal, for development)
cd admin-frontend
npm install
npm run dev
```

## Docker (Alternative)

```dockerfile
# Dockerfile example - create if needed
FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY admin-frontend/dist/ ./admin-frontend/dist/

WORKDIR /app/backend
CMD ["python", "main_sdk.py"]
```
