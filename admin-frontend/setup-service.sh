#!/bin/bash
# Setup admin-frontend as a user systemd service (no sudo required)

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="admin-frontend"

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/$SERVICE_NAME.service" << 'EOF'
[Unit]
Description=Cass Admin Frontend (Vite Dev Server)
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/jaryk/cass/cass-vessel/admin-frontend
ExecStart=/usr/bin/npm run dev -- --port 5173
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=development

[Install]
WantedBy=default.target
EOF

# Reload systemd user daemon
systemctl --user daemon-reload

# Enable and start the service
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo "Service installed and started!"
echo ""
echo "Useful commands:"
echo "  systemctl --user status admin-frontend   # Check status"
echo "  systemctl --user restart admin-frontend  # Restart after changes"
echo "  systemctl --user stop admin-frontend     # Stop the service"
echo "  systemctl --user start admin-frontend    # Start the service"
echo "  journalctl --user -u admin-frontend -f   # View logs"
