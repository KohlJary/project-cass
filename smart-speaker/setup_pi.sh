#!/bin/bash
# Cass Smart Speaker - Raspberry Pi Setup Script
#
# Run this on a fresh Raspberry Pi OS Lite (64-bit) installation.
# Tested on Pi Zero 2 W with ReSpeaker 2-Mic HAT.

set -e

echo "=== Cass Smart Speaker Setup ==="
echo ""

# Check if running on Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    echo "Continuing anyway..."
fi

# Update system
echo ">>> Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install system dependencies
echo ">>> Installing system dependencies..."
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    portaudio19-dev \
    libsndfile1 \
    libatlas-base-dev \
    libopenblas-dev \
    ffmpeg \
    mpg123 \
    git

# Install ReSpeaker drivers
echo ">>> Installing ReSpeaker drivers..."
if [ ! -d ~/seeed-voicecard ]; then
    cd ~
    git clone https://github.com/respeaker/seeed-voicecard
    cd seeed-voicecard
    sudo ./install.sh
    cd -
else
    echo "ReSpeaker drivers already cloned"
fi

# Create virtual environment
echo ">>> Setting up Python environment..."
SPEAKER_DIR="$(dirname "$(readlink -f "$0")")"
cd "$SPEAKER_DIR"

if [ ! -d venv ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install Python dependencies
echo ">>> Installing Python dependencies..."
pip install websockets numpy sounddevice soundfile aiohttp

# Install PyAudio (may need special handling on Pi)
pip install PyAudio || echo "PyAudio install failed, using sounddevice only"

# Install openWakeWord
echo ">>> Installing wake word detection..."
pip install openwakeword

# Install pixel_ring for LED control
echo ">>> Installing LED control..."
pip install spidev gpiozero
if [ ! -d ~/pixel_ring ]; then
    cd ~
    git clone https://github.com/respeaker/pixel_ring
    cd pixel_ring
    pip install -e .
    cd -
else
    cd ~/pixel_ring
    pip install -e .
    cd -
fi

# Whisper is too heavy for Pi Zero, skip it
# Users can set up backend STT or use whisper.cpp separately
echo ">>> Skipping Whisper (use backend STT for Pi Zero)"

# Create systemd service
echo ">>> Creating systemd service..."
sudo tee /etc/systemd/system/cass-speaker.service > /dev/null << 'EOF'
[Unit]
Description=Cass Smart Speaker Client
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/cass-vessel/smart-speaker
Environment="CASS_BACKEND_URL=ws://YOUR_BACKEND_IP:8000/ws"
ExecStart=/home/pi/cass-vessel/smart-speaker/venv/bin/python cass_speaker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Reboot to load ReSpeaker drivers: sudo reboot"
echo "2. Edit /etc/systemd/system/cass-speaker.service to set CASS_BACKEND_URL"
echo "3. Enable and start the service:"
echo "   sudo systemctl enable cass-speaker"
echo "   sudo systemctl start cass-speaker"
echo ""
echo "Or run manually for testing:"
echo "   cd $SPEAKER_DIR"
echo "   source venv/bin/activate"
echo "   CASS_BACKEND_URL=ws://YOUR_BACKEND_IP:8000/ws python cass_speaker.py"
echo ""
