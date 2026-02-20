#!/usr/bin/env python3
"""
Hardware Test Script for Cass Smart Speaker

Tests each component individually:
1. Microphone recording
2. Speaker playback
3. LED ring (if ReSpeaker HAT present)

Run this after setup to verify hardware works before running the full client.
"""

import time
import wave
from io import BytesIO

print("=== Cass Smart Speaker Hardware Test ===\n")

# Test 1: Audio libraries
print("1. Testing audio libraries...")
try:
    import sounddevice as sd
    import numpy as np
    print(f"   sounddevice: OK (version {sd.__version__})")
    print(f"   Default input device: {sd.query_devices(kind='input')['name']}")
    print(f"   Default output device: {sd.query_devices(kind='output')['name']}")
except ImportError as e:
    print(f"   sounddevice: FAILED ({e})")
    sd = None

try:
    import pyaudio
    print(f"   pyaudio: OK")
except ImportError as e:
    print(f"   pyaudio: FAILED ({e})")
    pyaudio = None

if not sd and not pyaudio:
    print("\n   ERROR: No audio library available!")
    exit(1)

# Test 2: Microphone
print("\n2. Testing microphone (recording 3 seconds)...")
print("   Speak now!")

if sd:
    duration = 3  # seconds
    sample_rate = 16000
    recording = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype='int16'
    )
    sd.wait()

    # Check if we got audio
    rms = np.sqrt(np.mean(recording.astype(np.float32) ** 2))
    normalized_rms = rms / 32768.0

    if normalized_rms > 0.001:
        print(f"   Recording: OK (RMS level: {normalized_rms:.4f})")
    else:
        print(f"   Recording: WARNING - Very low audio level ({normalized_rms:.4f})")
        print("   Check microphone connection")
else:
    print("   Skipping (no sounddevice)")

# Test 3: Speaker
print("\n3. Testing speaker (playing test tone)...")
if sd:
    duration = 1  # seconds
    sample_rate = 44100
    frequency = 440  # A4 note

    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(2 * np.pi * frequency * t) * 0.3  # 30% volume

    print("   Playing 440Hz tone...")
    sd.play(tone, sample_rate)
    sd.wait()
    print("   Speaker: OK (did you hear the tone?)")
else:
    print("   Skipping (no sounddevice)")

# Test 4: LED ring
print("\n4. Testing LED ring...")
try:
    from pixel_ring import pixel_ring

    print("   LED library: OK")
    print("   Running LED test sequence...")

    pixel_ring.set_brightness(20)

    print("   - All white")
    pixel_ring.set_color(r=255, g=255, b=255)
    time.sleep(0.5)

    print("   - Red")
    pixel_ring.set_color(r=255, g=0, b=0)
    time.sleep(0.5)

    print("   - Green")
    pixel_ring.set_color(r=0, g=255, b=0)
    time.sleep(0.5)

    print("   - Blue")
    pixel_ring.set_color(r=0, g=0, b=255)
    time.sleep(0.5)

    print("   - Listen animation")
    pixel_ring.listen()
    time.sleep(1)

    print("   - Think animation")
    pixel_ring.think()
    time.sleep(1)

    print("   - Speak animation")
    pixel_ring.speak()
    time.sleep(1)

    pixel_ring.off()
    print("   LED ring: OK")

except ImportError:
    print("   LED library: NOT INSTALLED")
    print("   (This is OK if not using ReSpeaker HAT)")
except Exception as e:
    print(f"   LED ring: FAILED ({e})")

# Test 5: Wake word
print("\n5. Testing wake word detection...")
try:
    from openwakeword.model import Model

    model = Model(wakeword_models=["alexa"], inference_framework="onnx")
    print("   openWakeWord: OK")
    print(f"   Loaded model: alexa")

except ImportError:
    print("   openWakeWord: NOT INSTALLED")
except Exception as e:
    print(f"   openWakeWord: FAILED ({e})")

# Test 6: WebSocket connection
print("\n6. Testing WebSocket library...")
try:
    import websockets
    print(f"   websockets: OK (version {websockets.__version__})")
except ImportError as e:
    print(f"   websockets: FAILED ({e})")

print("\n=== Hardware Test Complete ===")
print("\nIf all tests passed, you're ready to run cass_speaker.py")
print("If LED or wake word tests failed, those features will be disabled")
