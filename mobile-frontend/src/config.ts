/**
 * Mobile App Configuration
 *
 * Environment-based configuration for API and relay URLs.
 */

// Use Expo's environment variable support
// Set these in your .env or app.json extra config
const RELAY_URL = process.env.EXPO_PUBLIC_RELAY_URL || 'wss://your-relay.up.railway.app';

// API base URL (same host as WebSocket, just HTTP)
const API_BASE_URL = RELAY_URL.replace('wss://', 'https://').replace('ws://', 'http://').replace('/ws', '');

export const config = {
  // WebSocket endpoint for chat
  wsUrl: `${RELAY_URL}/ws`,

  // HTTP API base URL
  apiBaseUrl: API_BASE_URL,

  // Connection settings
  reconnectDelays: [1000, 2000, 5000, 10000, 30000],
  pingInterval: 30000,

  // Push notification settings
  pushEnabled: true,
};

// For development, you can override with local backend
// Set EXPO_PUBLIC_RELAY_URL=ws://localhost:8000 in .env
