# Cass Smart Speaker - Bill of Materials

## Mid-Tier Build (~$50-70 per unit)

### Core Components

| Component | Model | Price | Link |
|-----------|-------|-------|------|
| SBC | Raspberry Pi Zero 2 W | ~$15 | [RPi Foundation](https://www.raspberrypi.com/products/raspberry-pi-zero-2-w/) |
| Microphone HAT | ReSpeaker 2-Mic Pi HAT | ~$12 | [Seeed Studio](https://www.seeedstudio.com/ReSpeaker-2-Mics-Pi-HAT.html) |
| Speaker | 3W 4Ohm 40mm | ~$3 | Generic |
| Amplifier | MAX98357A I2S | ~$4 | Adafruit/generic |
| microSD Card | 16GB+ Class 10 | ~$8 | Any brand |
| Power Supply | 5V 2.5A USB-C | ~$8 | Official RPi recommended |
| Enclosure | 3D printed / project box | ~$5-10 | Custom |
| Misc | Wires, standoffs, screws | ~$5 | - |

**Total: ~$60-65**

### Optional Upgrades

| Component | Purpose | Price |
|-----------|---------|-------|
| ReSpeaker 4-Mic Array | Better directionality, beamforming | ~$35 (replaces 2-mic) |
| Larger speaker (5W+) | Better audio quality | ~$8-15 |
| Custom PCB | Cleaner wiring | ~$5/board at scale |

---

## Budget Tier (~$25-35 per unit)

For maximum deployment density (many rooms):

| Component | Model | Price |
|-----------|-------|-------|
| MCU | ESP32-S3-DevKitC-1 | ~$10 |
| Microphone | INMP441 I2S MEMS | ~$3 |
| Amplifier | MAX98357A | ~$3 |
| Speaker | 3W 40mm | ~$3 |
| Power | 5V USB adapter | ~$5 |
| Enclosure | 3D printed | ~$3-5 |

**Total: ~$27-30**

Tradeoffs:
- No local Python (MicroPython or Arduino)
- Wake word must be tiny model or cloud
- Less processing power
- But: Much cheaper, lower power, instant boot

---

## Wiring Diagram (Pi Zero 2 W + ReSpeaker 2-Mic)

```
                    ReSpeaker 2-Mic HAT
                    ┌─────────────────────┐
                    │  [MIC1]     [MIC2]  │
                    │                     │
                    │   ○ ○ ○ (3 LEDs)    │
                    │                     │
                    │  [Button]           │
                    └─────────┬───────────┘
                              │ (40-pin GPIO)
                    ┌─────────┴───────────┐
                    │   Raspberry Pi      │
                    │   Zero 2 W          │
                    │                     │
                    │  [USB]  [HDMI]      │
                    └─────────────────────┘

Speaker Connection (separate amp):
  Pi GPIO 18 (PCM_CLK) ──► MAX98357A BCLK
  Pi GPIO 19 (PCM_FS)  ──► MAX98357A LRC
  Pi GPIO 21 (PCM_DOUT)──► MAX98357A DIN
  Pi 5V                ──► MAX98357A VIN
  Pi GND               ──► MAX98357A GND
  MAX98357A +/-        ──► Speaker

Note: ReSpeaker HAT has onboard speaker output jack,
but external amp gives better quality.
```

---

## Software Dependencies

```bash
# On Raspberry Pi OS Lite (64-bit recommended for Pi Zero 2 W)

# System packages
sudo apt update
sudo apt install -y python3-pip python3-venv \
    portaudio19-dev libsndfile1 \
    libatlas-base-dev  # For numpy

# Python packages (in venv)
pip install \
    websockets \
    pyaudio \
    numpy \
    openwakeword \  # Local wake word detection
    sounddevice \
    aiohttp

# ReSpeaker drivers
git clone https://github.com/respeaker/seeed-voicecard
cd seeed-voicecard
sudo ./install.sh
sudo reboot
```

---

## Robot Embodiment Notes

For mounting on a mobile robot:

1. **Same Pi Zero 2 W unit** serves as head/ears/mouth
2. Add **Pi Camera Module** for vision (via ribbon cable)
3. Servo control via:
   - PWM GPIO pins (2-3 servos)
   - Or separate servo controller board (PCA9685) for more
4. Consider **ReSpeaker 4-Mic** for 360° sound localization
5. LED ring doubles as "expression" indicator

The smart speaker client code is designed to be reusable - same WebSocket protocol, just add motor control layer on top.
