# Home Assistant Integration

This directory contains the Cass integration for Home Assistant, enabling Cass to function as a voice/home assistant.

## Components

```
home-assistant/
├── custom_components/cass/    # HA custom integration
│   ├── __init__.py            # Setup and config entry
│   ├── config_flow.py         # UI configuration
│   ├── const.py               # Constants
│   ├── conversation.py        # ConversationEntity (voice/text handling)
│   ├── manifest.json          # Integration metadata
│   └── strings.json           # UI translations
└── voice-pipeline/
    └── docker-compose.yml     # Wyoming voice services (Whisper, Piper, openWakeWord)
```

## Prerequisites

- Home Assistant running (Docker recommended)
- Cass backend running on port 8000
- Docker for voice pipeline services

## Setup Instructions

### 1. Install Custom Component

Copy the custom component to your HA config directory:

```bash
cp -r home-assistant/custom_components/cass /path/to/homeassistant/custom_components/
```

For the default setup:
```bash
cp -r home-assistant/custom_components/cass ~/homeassistant/custom_components/
```

Restart Home Assistant after copying.

### 2. Start Voice Pipeline

```bash
cd home-assistant/voice-pipeline
docker compose up -d
```

This starts:
- **Whisper** (STT) on port 10300
- **Piper** (TTS) on port 10200
- **openWakeWord** on port 10400

### 3. Configure Home Assistant

#### Add Wyoming Integrations

Go to **Settings > Devices & Services > Add Integration** and add:

1. **Wyoming Protocol** - Host: `localhost`, Port: `10300` (Whisper STT)
2. **Wyoming Protocol** - Host: `localhost`, Port: `10200` (Piper TTS)
3. **Wyoming Protocol** - Host: `localhost`, Port: `10400` (openWakeWord)

#### Add Cass Integration

1. **Settings > Devices & Services > Add Integration**
2. Search for "Cass"
3. Enter:
   - Host: `localhost` (or your Cass backend host)
   - Port: `8000`

#### Create Voice Assistant

1. **Settings > Voice Assistants**
2. Click **Add Assistant**
3. Configure:
   - Name: "Cass"
   - Conversation agent: **Cass**
   - Speech-to-text: **faster-whisper**
   - Text-to-speech: **piper**
   - Wake word: **ok nabu** (optional)

### 4. Test

Say "Ok Nabu" (if wake word enabled) or use the voice assistant button in HA to talk to Cass.

## Environment Variables

The Cass backend needs these in `.env`:

```bash
HOME_ASSISTANT_URL=http://localhost:8123
HOME_ASSISTANT_TOKEN=<your-long-lived-access-token>
```

To create a token:
1. HA Profile (bottom left) > Long-Lived Access Tokens
2. Create Token, name it "Cass"
3. Copy and add to `.env`

## GPU Acceleration

The default config uses CPU for Whisper. To enable GPU:

Edit `voice-pipeline/docker-compose.yml`:

```yaml
whisper:
  command: --model base.en --language en --device cuda
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

Note: Requires available VRAM (~2GB for base.en model).

## Troubleshooting

### Cass not appearing in integrations
- Ensure files are copied (not symlinked) to HA's custom_components
- Restart Home Assistant
- Check logs: `docker logs homeassistant 2>&1 | grep -i cass`

### Voice not working
- Verify Wyoming containers are running: `docker ps | grep wyoming`
- Check container logs: `docker logs wyoming-whisper`
- Ensure ports 10200, 10300, 10400 are not blocked

### Connection errors
- Verify Cass backend is running: `curl http://localhost:8000/health`
- Check backend has HA token configured
- Restart backend after adding HA config to `.env`
