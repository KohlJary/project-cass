# Cass Smart Speaker

Voice interface for Cass using Raspberry Pi Zero 2 W + ReSpeaker HAT.

## Quick Start

1. **Get hardware** - See [BOM.md](BOM.md) for parts list (~$50-70)
2. **Flash SD card** - Raspberry Pi OS Lite (64-bit)
3. **Run setup** - `./setup_pi.sh`
4. **Configure** - Set backend URL in systemd service
5. **Test** - `python test_hardware.py`

## Files

| File | What it does |
|------|--------------|
| [BOM.md](BOM.md) | Bill of materials, wiring diagram |
| [setup_pi.sh](setup_pi.sh) | Automated Pi setup (run once) |
| [test_hardware.py](test_hardware.py) | Verify mic/speaker/LEDs work |
| [cass_speaker.py](cass_speaker.py) | Main client |
| [requirements.txt](requirements.txt) | Python dependencies |

## How It Works

```
"Hey Cass" → Wake word detected (local)
          → Record speech until silence
          → POST to backend /admin/stt/transcribe (Whisper)
          → Send text via WebSocket
          → Receive response + TTS audio
          → Play audio, update LEDs
```

The Pi handles wake word and audio I/O. The backend handles STT, LLM, and TTS.

## Configuration

Environment variables (set in systemd service or export):

```bash
CASS_BACKEND_URL=ws://192.168.1.X:8000/ws  # Your backend IP
CASS_AUTH_TOKEN=                            # Optional JWT token
CASS_WAKE_WORD=alexa                        # Wake word model
CASS_WAKE_THRESHOLD=0.5                     # Detection sensitivity
```

## Running

**As service (production):**
```bash
sudo systemctl enable cass-speaker
sudo systemctl start cass-speaker
journalctl -u cass-speaker -f  # View logs
```

**Manual (testing):**
```bash
source venv/bin/activate
CASS_BACKEND_URL=ws://YOUR_IP:8000/ws python cass_speaker.py
```

## Robot Embodiment

Same hardware mounts on a robot head:
- Add Pi Camera Module for vision
- Add servos via GPIO or PCA9685 board
- Upgrade to ReSpeaker 4-Mic for 360° audio
- LED ring doubles as expression indicator

The client code is designed to be extensible - add motor control on top.
