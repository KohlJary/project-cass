#!/bin/bash
# Install Wonderland as a systemd service
# Run with: sudo ./install-wonderland-service.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/wonderland.service"
USER="jaryk"

echo "Installing Wonderland service..."

# Copy service file
cp "$SERVICE_FILE" /etc/systemd/system/wonderland.service
echo "  ✓ Service file copied to /etc/systemd/system/"

# Reload systemd
systemctl daemon-reload
echo "  ✓ Systemd reloaded"

# Enable service
systemctl enable wonderland
echo "  ✓ Service enabled"

# Add sudoers rule for passwordless control
SUDOERS_FILE="/etc/sudoers.d/wonderland"
cat > "$SUDOERS_FILE" << EOF
# Allow $USER to manage wonderland service without password
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start wonderland
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop wonderland
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart wonderland
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status wonderland
$USER ALL=(ALL) NOPASSWD: /usr/bin/journalctl -u wonderland*
EOF
chmod 440 "$SUDOERS_FILE"
echo "  ✓ Sudoers configured for passwordless control"

# Stop any existing wonderland process on port 8100
if lsof -ti:8100 >/dev/null 2>&1; then
    echo "  Stopping existing process on port 8100..."
    kill $(lsof -ti:8100) 2>/dev/null || true
    sleep 2
fi

# Start service
systemctl start wonderland
echo "  ✓ Service started"

# Show status
echo ""
echo "Wonderland service installed successfully!"
echo ""
systemctl status wonderland --no-pager | head -15

echo ""
echo "You can now use these commands (no sudo needed):"
echo "  sudo systemctl start wonderland"
echo "  sudo systemctl stop wonderland"
echo "  sudo systemctl restart wonderland"
echo "  sudo systemctl status wonderland"
echo "  sudo journalctl -u wonderland -f"
