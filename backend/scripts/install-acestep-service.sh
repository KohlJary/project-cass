#!/bin/bash
# Install ACE-Step as a systemd service alongside cass-vessel
#
# This script:
# 1. Installs the acestep.service systemd unit
# 2. Optionally adds ACE-Step as a dependency of cass-vessel
# 3. Enables and starts the service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACESTEP_DIR="$SCRIPT_DIR/../music/ace-step"

# Check if ACE-Step is installed
if [ ! -d "$ACESTEP_DIR" ]; then
    echo "ACE-Step not found at $ACESTEP_DIR"
    echo ""
    echo "Install it first with:"
    echo "  cd $SCRIPT_DIR/../music"
    echo "  git clone https://github.com/ace-step/ACE-Step-1.5.git ace-step"
    echo "  cd ace-step"
    echo "  uv sync  # Install dependencies"
    exit 1
fi

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "uv not found. Please install uv first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "Installing ACE-Step systemd service..."

# Copy service file
sudo cp "$SCRIPT_DIR/acestep.service" /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable acestep.service

echo ""
echo "ACE-Step service installed!"
echo ""
echo "Commands:"
echo "  sudo systemctl start acestep     # Start ACE-Step"
echo "  sudo systemctl stop acestep      # Stop ACE-Step"
echo "  sudo systemctl status acestep    # Check status"
echo "  journalctl -u acestep -f         # View logs"
echo ""

# Ask about starting now
read -p "Start ACE-Step now? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Starting ACE-Step (first run may take a while to download models)..."
    sudo systemctl start acestep
    echo ""
    echo "Checking status..."
    sleep 2
    sudo systemctl status acestep --no-pager || true
fi

echo ""
read -p "Make cass-vessel depend on ACE-Step (recommended)? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "Installing drop-in configuration for cass-vessel..."
    sudo mkdir -p /etc/systemd/system/cass-vessel.service.d/
    sudo cp "$SCRIPT_DIR/cass-vessel-acestep.conf" /etc/systemd/system/cass-vessel.service.d/
    sudo systemctl daemon-reload
    echo "Done! cass-vessel will now wait for ACE-Step to start."
    echo ""
    read -p "Restart cass-vessel now to apply? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        sudo systemctl restart cass-vessel
        echo "cass-vessel restarted."
    fi
fi

echo ""
echo "Setup complete! Both services are now configured."
echo ""
echo "Service commands:"
echo "  systemctl status acestep cass-vessel  # Check both services"
echo "  journalctl -u acestep -f              # ACE-Step logs"
echo "  journalctl -u cass-vessel -f          # Cass logs"
