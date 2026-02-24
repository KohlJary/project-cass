# Cass Embodiment / Sensor Module

Physical embodiment system for Cass. Designed to run on Pi 5 + touchscreen
but fully testable on any dev machine.

## Quick Start

```bash
cd embodiment
pip install -r requirements.txt

# Run just the face display
python text_face/text_face.py

# Run full sensor module (connects to Cass backend)
python sensor_module.py --backend ws://localhost:8000/ws
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    sensor_module.py                      │
│                    (State Machine)                       │
│  IDLE -> LISTENING -> PROCESSING -> SPEAKING -> IDLE    │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
    ┌──────┴──────┐ ┌─────┴─────┐ ┌──────┴──────┐
    │ text_face/  │ │  audio/   │ │cass_client/ │
    │  Display    │ │ Mic + TTS │ │  WebSocket  │
    └─────────────┘ └───────────┘ └─────────────┘
```

## Components

### text_face/ - Display
Text-based face renderer - Cass's form composed entirely of flowing text.
Uses Temple-Codex fragments as the visual substrate.

**Concept**: A being made of words, rendered as words.

Controls:
- `ESC` - Quit
- `R` - Regenerate particles
- `SPACE` - Shuffle characters
- `UP/DOWN` - Scale face

### audio/ - Audio I/O
- **MicrophoneInput**: Captures audio with Voice Activity Detection (VAD)
- **AudioPlayer**: Plays TTS audio from Cass backend

### cass_client/ - Backend Connection
WebSocket client that connects to the Cass vessel backend.

## Sensor Module Controls

- `ESC` - Quit
- `T` - Send test message to Cass
- `R` - Regenerate face particles
- `1-4` - Force state (idle/listening/processing/speaking)

## Command Line Options

```
python sensor_module.py [options]

  --backend, -b URL    Backend WebSocket URL (default: ws://localhost:8000/ws)
  --width, -W INT      Display width (default: 480)
  --height, -H INT     Display height (default: 800)
  --no-mic             Disable microphone input
  --no-tts             Disable TTS playback
  --user, -u ID        User ID for backend (default: sensor-module)
```

## State Machine

| State | Face Behavior | Trigger |
|-------|---------------|---------|
| IDLE | Slow breathing, purple | Default state |
| LISTENING | Fast breathing, cyan shift | VAD detects speech |
| PROCESSING | Pulsing, bright | Utterance sent to Cass |
| SPEAKING | Animated, warm | Playing Cass's audio |

## Dependencies

Core:
- `pygame` - Display and audio playback
- `websockets` - Backend connection
- `numpy` - Audio processing
- `sounddevice` - Microphone capture

Optional:
- `webrtcvad` - Better voice activity detection (falls back to energy-based)
- `openai-whisper` or `faster-whisper` - Local speech-to-text (future)

## TODO

- [ ] Integrate local STT (Whisper) for mic -> text
- [ ] Audio reactivity - particles respond to TTS amplitude
- [ ] Touch interaction - particles respond to touch
- [ ] Expression states tied to Cass's emotional context
- [ ] Live text feed from conversation
- [ ] Wake word detection ("Hey Cass")
