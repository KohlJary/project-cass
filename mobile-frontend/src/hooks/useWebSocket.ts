/**
 * WebSocket hook with reconnection logic and JWT authentication
 */

import { useEffect, useRef, useCallback } from 'react';
import { Platform } from 'react-native';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';
import { WebSocketMessage, WebSocketResponse } from '../api/types';

// Backend WebSocket URL
// Options:
// - Local IP for same network: ws://192.168.0.17:8000/ws
// - Tunnel for remote access: wss://fair-chefs-show.loca.lt/ws
// - Emulator: ws://10.0.2.2:8000/ws (Android) or ws://localhost:8000/ws (iOS)
const WS_BASE_URL = 'wss://serial-around-described-cut.trycloudflare.com/ws';

const RECONNECT_DELAYS = [1000, 2000, 5000, 10000, 30000];
const PING_INTERVAL = 30000;

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const reconnectAttempt = useRef(0);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);
  const pingInterval = useRef<NodeJS.Timeout | null>(null);

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
    if (pingInterval.current) {
      clearInterval(pingInterval.current);
      pingInterval.current = null;
    }
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
      reconnectTimeout.current = null;
    }
    if (ws.current) {
      ws.current.onclose = null; // Prevent auto-reconnect
      ws.current.close();
      ws.current = null;
    }
    setConnected(false);
  }, [setConnected]);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    // Get auth token for WebSocket connection
    const { accessToken } = useAuthStore.getState();
    if (!accessToken) {
      console.log('No auth token available, skipping WebSocket connection');
      return;
    }

    // Build WebSocket URL with token as query parameter
    const wsUrl = `${WS_BASE_URL}?token=${encodeURIComponent(accessToken)}`;

    setConnecting(true);
    console.log('Connecting to WebSocket with auth...');

    try {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setConnected(true);
        reconnectAttempt.current = 0;

        // Start ping interval
        pingInterval.current = setInterval(() => {
          if (ws.current?.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: 'ping' }));
          }
        }, PING_INTERVAL);
      };

      ws.current.onmessage = (event) => {
        try {
          const data: WebSocketResponse = JSON.parse(event.data);
          handleMessage(data);
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.current.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        setConnected(false);

        // Clear ping interval
        if (pingInterval.current) {
          clearInterval(pingInterval.current);
          pingInterval.current = null;
        }

        scheduleReconnect();
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnected(false);
      };
    } catch (error) {
      console.error('WebSocket connection failed:', error);
      setConnecting(false);
      scheduleReconnect();
    }
  }, [handleMessage, setConnected, setConnecting]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimeout.current) {
      clearTimeout(reconnectTimeout.current);
    }

    const delay =
      RECONNECT_DELAYS[Math.min(reconnectAttempt.current, RECONNECT_DELAYS.length - 1)];

    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempt.current + 1})`);

    reconnectTimeout.current = setTimeout(() => {
      reconnectAttempt.current++;
      connect();
    }, delay);
  }, [connect]);

  const sendMessage = useCallback(
    (text: string, conversationId?: string | null): boolean => {
      if (ws.current?.readyState !== WebSocket.OPEN) {
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

      ws.current.send(JSON.stringify(message));
      return true;
    },
    []
  );

  const sendOnboardingIntro = useCallback(
    (conversationId: string): boolean => {
      if (ws.current?.readyState !== WebSocket.OPEN) {
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
      ws.current.send(JSON.stringify(message));
      return true;
    },
    []
  );

  const reconnect = useCallback(() => {
    console.log('Forcing WebSocket reconnection...');
    disconnect();
    // Small delay to ensure clean disconnect
    setTimeout(() => {
      connect();
    }, 100);
  }, [disconnect, connect]);

  useEffect(() => {
    connect();

    return () => {
      // Cleanup on unmount
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (pingInterval.current) {
        clearInterval(pingInterval.current);
      }
      ws.current?.close();
    };
  }, [connect]);

  return { sendMessage, sendOnboardingIntro, reconnect, isConnected };
}
