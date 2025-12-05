#!/bin/bash
# Start cloudflared tunnel and Expo for mobile development
cd "$(dirname "$0")"

# Start cloudflared in background and capture URL
echo "Starting cloudflared tunnel..."
cloudflared tunnel --url http://localhost:8000 2>&1 &
TUNNEL_PID=$!

# Wait for tunnel URL to appear
sleep 5
TUNNEL_URL=$(cloudflared tunnel --url http://localhost:8000 2>&1 | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)

# If we didn't get it from a new process, try to get it from the metrics
if [ -z "$TUNNEL_URL" ]; then
  # Give it more time and check the running process output
  sleep 3
  TUNNEL_URL=$(curl -s http://127.0.0.1:20241/metrics 2>/dev/null | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' || echo "")
fi

# Kill the second cloudflared we started just to get the URL
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1

# Start it fresh and capture properly
TMPFILE=$(mktemp)
cloudflared tunnel --url http://localhost:8000 2>"$TMPFILE" &
TUNNEL_PID=$!

# Wait for URL
for i in {1..10}; do
  TUNNEL_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$TMPFILE" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  echo "Failed to get tunnel URL"
  cat "$TMPFILE"
  rm "$TMPFILE"
  exit 1
fi

rm "$TMPFILE"
echo "Tunnel URL: $TUNNEL_URL"

# Update the source files with new URL
sed -i "s|const API_BASE = '.*'|const API_BASE = '$TUNNEL_URL'|" src/api/client.ts
sed -i "s|const WS_BASE_URL = '.*'|const WS_BASE_URL = 'wss://${TUNNEL_URL#https://}/ws'|" src/hooks/useWebSocket.ts

echo "Updated source files with tunnel URL"
echo ""

# Cleanup on exit
cleanup() {
  echo "Stopping cloudflared..."
  kill $TUNNEL_PID 2>/dev/null
}
trap cleanup EXIT

# Start Expo
npx expo start --tunnel
