/**
 * WebSocket hook with reconnection logic and JWT authentication
 */

import { useEffect, useCallback } from 'react';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { WebSocketMessage, WebSocketResponse } from '../api/types';
import { config } from '../config';

// Use configured WebSocket URL
const WS_BASE_URL = config.wsUrl;

const RECONNECT_DELAYS = config.reconnectDelays;
const PING_INTERVAL = config.pingInterval;

// Global WebSocket state - persists across component remounts
let globalWs: WebSocket | null = null;
let globalPingInterval: NodeJS.Timeout | null = null;
let globalReconnectTimeout: NodeJS.Timeout | null = null;
let globalReconnectAttempt = 0;

export function useWebSocket() {
  const {
    addMessage,
    setThinking,
    setThinkingStatus,
    setConnected,
    setConnecting,
    isConnected,
  } = useChatStore();

  const handleMessage = useCallback(
    (data: WebSocketResponse) => {
      switch (data.type) {
        case 'connected':
          console.log('Backend connected, SDK mode:', data.sdk_mode);
          break;

        case 'thinking':
          setThinking(true);
          if (data.status) {
            setThinkingStatus(data.status);
          } else if (data.memories) {
            const { summaries_count, details_count, project_docs_count } = data.memories;
            const parts = [];
            if (summaries_count > 0) parts.push(`${summaries_count} summaries`);
            if (details_count > 0) parts.push(`${details_count} memories`);
            if (project_docs_count > 0) parts.push(`${project_docs_count} docs`);
            setThinkingStatus(parts.length > 0 ? `Thinking (${parts.join(', ')})...` : 'Thinking...');
          }
          break;

        case 'response':
          setThinking(false);
          addMessage({
            role: 'assistant',
            content: data.text || '',
            timestamp: data.timestamp || new Date().toISOString(),
            animations: data.animations,
            inputTokens: data.input_tokens,
            outputTokens: data.output_tokens,
            provider: data.provider,
            model: data.model,
          });
          break;

        case 'system':
          addMessage({
            role: 'system',
            content: data.message || '',
            timestamp: data.timestamp || new Date().toISOString(),
          });
          break;

        case 'pong':
          // Heartbeat acknowledged
          break;
      }
    },
    [addMessage, setThinking, setThinkingStatus]
  );

  const disconnect = useCallback(() => {
    if (globalPingInterval) {
      clearInterval(globalPingInterval);
      globalPingInterval = null;
    }
    if (globalReconnectTimeout) {
      clearTimeout(globalReconnectTimeout);
      globalReconnectTimeout = null;
    }
    if (globalWs) {
      globalWs.onclose = null; // Prevent auto-reconnect
      globalWs.close();
      globalWs = null;
    }
    setConnected(false);
  }, [setConnected]);

  const scheduleReconnect = useCallback(() => {
    if (globalReconnectTimeout) {
      clearTimeout(globalReconnectTimeout);
    }

    const delay = RECONNECT_DELAYS[Math.min(globalReconnectAttempt, RECONNECT_DELAYS.length - 1)];
    console.log(`Reconnecting in ${delay}ms (attempt ${globalReconnectAttempt + 1})`);

    globalReconnectTimeout = setTimeout(() => {
      globalReconnectAttempt++;
      // We'll call connect through the effect
      const { accessToken } = useAuthStore.getState();
      if (accessToken && (!globalWs || globalWs.readyState !== WebSocket.OPEN)) {
        connectWebSocket(accessToken, handleMessage, setConnected, setConnecting, scheduleReconnect);
      }
    }, delay);
  }, [handleMessage, setConnected, setConnecting]);

  const connect = useCallback(() => {
    if (globalWs?.readyState === WebSocket.OPEN) {
      console.log('WebSocket already connected');
      return;
    }

    const { accessToken } = useAuthStore.getState();
    if (!accessToken) {
      console.log('No auth token available, skipping WebSocket connection');
      return;
    }

    connectWebSocket(accessToken, handleMessage, setConnected, setConnecting, scheduleReconnect);
  }, [handleMessage, setConnected, setConnecting, scheduleReconnect]);

  const sendMessage = useCallback(
    (text: string, conversationId?: string | null): boolean => {
      if (!globalWs || globalWs.readyState !== WebSocket.OPEN) {
        console.error('WebSocket not connected');
        return false;
      }

      const { user } = useAuthStore.getState();

      const message: WebSocketMessage = {
        type: 'chat',
        message: text,
        conversation_id: conversationId || undefined,
        user_id: user?.user_id || undefined,
      };

      globalWs.send(JSON.stringify(message));
      return true;
    },
    []
  );

  const sendOnboardingIntro = useCallback(
    (conversationId: string): boolean => {
      if (!globalWs || globalWs.readyState !== WebSocket.OPEN) {
        console.error('WebSocket not connected');
        return false;
      }

      const { user } = useAuthStore.getState();

      const message: WebSocketMessage = {
        type: 'onboarding_intro',
        conversation_id: conversationId,
        user_id: user?.user_id || undefined,
      };

      console.log('Sending onboarding_intro:', message);
      globalWs.send(JSON.stringify(message));
      return true;
    },
    []
  );

  const reconnect = useCallback(() => {
    console.log('Forcing WebSocket reconnection...');
    disconnect();
    setTimeout(() => {
      connect();
    }, 100);
  }, [disconnect, connect]);

  // Connect on mount if not already connected
  useEffect(() => {
    if (!globalWs || globalWs.readyState !== WebSocket.OPEN) {
      connect();
    }
    // No cleanup - WebSocket persists globally
  }, [connect]);

  return { sendMessage, sendOnboardingIntro, reconnect, isConnected };
}

// Helper function to create WebSocket connection
function connectWebSocket(
  accessToken: string,
  handleMessage: (data: WebSocketResponse) => void,
  setConnected: (connected: boolean) => void,
  setConnecting: (connecting: boolean) => void,
  scheduleReconnect: () => void
) {
  const wsUrl = `${WS_BASE_URL}?token=${encodeURIComponent(accessToken)}`;

  setConnecting(true);
  console.log('Connecting to WebSocket with auth...');

  try {
    globalWs = new WebSocket(wsUrl);

    globalWs.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
      globalReconnectAttempt = 0;

      // Start ping interval
      globalPingInterval = setInterval(() => {
        if (globalWs?.readyState === WebSocket.OPEN) {
          globalWs.send(JSON.stringify({ type: 'ping' }));
        }
      }, PING_INTERVAL);
    };

    globalWs.onmessage = (event) => {
      try {
        const data: WebSocketResponse = JSON.parse(event.data);
        handleMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    globalWs.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      setConnected(false);

      if (globalPingInterval) {
        clearInterval(globalPingInterval);
        globalPingInterval = null;
      }

      // Only reconnect if not a clean close
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    globalWs.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnected(false);
    };
  } catch (error) {
    console.error('WebSocket connection failed:', error);
    setConnecting(false);
    scheduleReconnect();
  }
}
