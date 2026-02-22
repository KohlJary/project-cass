# Voice References for XTTS

Place voice reference audio files here for XTTS v2 voice cloning.

## Requirements

- WAV format
- 6-30 seconds of clear speech
- Minimal background noise
- Single speaker

## Usage

1. Record or extract clean audio of the target voice
2. Save as `<voice_name>.wav` in this directory
3. Use `voice="<voice_name>"` when calling synthesize()

Example:
```python
from backend.tts import synthesize

audio = synthesize(
    "Hello, I'm Cass!",
    provider="xtts",
    voice="cass"  # Uses voices/cass.wav
)
```

## Tips for Recording

- Use a good microphone in a quiet room
- Speak naturally, include variety (questions, statements)
- Avoid very short clips - 15-20 seconds is ideal
- Clean audio > quantity

## Built-in Voices

If no custom voice is provided, XTTS has built-in voices:
- `female_1` through `female_9`
- `male_1` through `male_9`
- `default` (neutral)
