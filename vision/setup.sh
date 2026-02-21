#!/bin/bash
# Cass Vision System - Setup Script

set -e

echo "=== Cass Vision Setup ==="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check for system dependencies
echo ">>> Checking system dependencies..."

if ! command -v cmake &> /dev/null; then
    echo "cmake not found. Installing..."
    sudo apt update
    sudo apt install -y cmake build-essential
else
    echo "cmake: OK"
fi

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo ">>> Creating virtual environment..."
    python3 -m venv venv
fi

echo ">>> Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip wheel setuptools

# Install core dependencies
echo ">>> Installing core dependencies..."
pip install opencv-python numpy mediapipe

# Install face recognition (optional but recommended)
echo ">>> Installing face recognition (this may take a while - compiling dlib)..."
pip install face-recognition || {
    echo ""
    echo "WARNING: face-recognition install failed."
    echo "This is often due to missing build tools."
    echo "Try: sudo apt install cmake build-essential"
    echo ""
    echo "Vision will work without it, but face identification won't be available."
}

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To use:"
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  python cass_vision.py      # Full system"
echo "  python attention_detector.py  # Just eye contact"
echo ""
