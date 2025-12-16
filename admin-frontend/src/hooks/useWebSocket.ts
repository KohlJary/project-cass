import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (window.location.hostname === 'localhost') return 'http://localhost:8000';
  return window.location.origin;
};
const API_BASE = getApiBase();
const WS_BASE = API_BASE.replace(/^http/, 'ws');

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  isThinking?: boolean;
  inputTokens?: number;
  outputTokens?: number;
  provider?: string;
  model?: string;
  audio?: string;  // base64 encoded audio
  audioFormat?: string;  // e.g., 'mp3'
}

interface MemoryContext {
  summaries_count: number;
  details_count: number;
  has_context: boolean;
}

export interface RecognitionMark {
  category: string;
  description: string;
}

export interface SelfObservation {
  observation: string;
  category: string;
  confidence: number;
}

export interface UserObservation {
  observation: string;
  category: string;
  confidence: number;
}

interface WebSocketMessage {
  type: string;
  message?: string;
  text?: string;
  status?: string;
  memories?: MemoryContext;
  conversation_id?: string;
  timestamp?: string;
  title?: string;
  input_tokens?: number;
  output_tokens?: number;
  provider?: string;
  model?: string;
  audio?: string;
  audio_format?: string;
  // Recognition-in-flow markers
  marks?: RecognitionMark[];
  self_observations?: SelfObservation[];
  user_observations?: UserObservation[];
}

export interface RecognitionData {
  marks: RecognitionMark[];
  selfObservations: SelfObservation[];
  userObservations: UserObservation[];
}

interface UseWebSocketReturn {
  isConnected: boolean;
  isThinking: boolean;
  thinkingStatus: string | null;
  memoryContext: MemoryContext | null;
  messages: ChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  sendMessage: (message: string, conversationId?: string, image?: { data: string; mediaType: string }) => void;
  error: string | null;
  currentConversationId: string | null;
  conversationTitle: string | null;
  recognition: RecognitionData;
  setRecognition: React.Dispatch<React.SetStateAction<RecognitionData>>;
  clearRecognition: () => void;
}

export function useWebSocket(): UseWebSocketReturn {
  const { token } = useAuth();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const isConnectingRef = useRef(false);
  const mountedRef = useRef(true);

  const [isConnected, setIsConnected] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [thinkingStatus, setThinkingStatus] = useState<string | null>(null);
  const [memoryContext, setMemoryContext] = useState<MemoryContext | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [recognition, setRecognition] = useState<RecognitionData>({
    marks: [],
    selfObservations: [],
    userObservations: [],
  });

  const clearRecognition = useCallback(() => {
    setRecognition({ marks: [], selfObservations: [], userObservations: [] });
  }, []);

  // Use ref for message handler to avoid stale closures
  const handleMessageRef = useRef<(msg: WebSocketMessage) => void>(() => {});

  handleMessageRef.current = (msg: WebSocketMessage) => {
    switch (msg.type) {
      case 'connected':
        console.log('[WebSocket] Server confirmed connection');
        break;

      case 'thinking':
        setIsThinking(true);
        setThinkingStatus(msg.status || 'Thinking...');
        if (msg.memories) {
          setMemoryContext(msg.memories);
        }
        break;

      case 'response':
        setIsThinking(false);
        setThinkingStatus(null);
        // Always remove thinking placeholder
        if (msg.text) {
          const newMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: msg.text,
            timestamp: msg.timestamp || new Date().toISOString(),
            inputTokens: msg.input_tokens,
            outputTokens: msg.output_tokens,
            provider: msg.provider,
            model: msg.model,
            audio: msg.audio,
            audioFormat: msg.audio_format,
          };
          setMessages(prev => prev.filter(m => !m.isThinking).concat(newMessage));
        } else {
          // No text but still clear thinking message
          setMessages(prev => prev.filter(m => !m.isThinking));
        }
        if (msg.conversation_id) {
          setCurrentConversationId(msg.conversation_id);
        }
        // Capture recognition-in-flow markers
        if (msg.marks || msg.self_observations || msg.user_observations) {
          setRecognition(prev => ({
            marks: msg.marks ? [...prev.marks, ...msg.marks] : prev.marks,
            selfObservations: msg.self_observations ? [...prev.selfObservations, ...msg.self_observations] : prev.selfObservations,
            userObservations: msg.user_observations ? [...prev.userObservations, ...msg.user_observations] : prev.userObservations,
          }));
        }
        break;

      case 'error':
        setIsThinking(false);
        setThinkingStatus(null);
        setError(msg.message || 'Unknown error');
        // Remove thinking message on error
        setMessages(prev => prev.filter(m => !m.isThinking));
        break;

      case 'title_updated':
        if (msg.title) {
          setConversationTitle(msg.title);
        }
        break;

      case 'system':
        if (msg.message) {
          const sysMessage: ChatMessage = {
            id: crypto.randomUUID(),
            role: 'system',
            content: msg.message,
            timestamp: msg.timestamp || new Date().toISOString(),
          };
          setMessages(prev => [...prev, sysMessage]);
        }
        break;

      case 'pong':
        // Keepalive response, ignore
        break;

      case 'debug':
        // Debug messages from backend, just log
        console.log('[WebSocket] Debug:', msg.message);
        break;

      case 'calendar_updated':
      case 'tasks_updated':
        // Tool notification messages, ignore in chat
        break;

      default:
        console.log('[WebSocket] Unhandled message type:', msg.type, msg);
    }
  };

  const connect = useCallback(() => {
    if (!token) return;

    // Prevent concurrent connection attempts
    if (isConnectingRef.current) {
      console.log('[WebSocket] Already connecting, skipping');
      return;
    }

    // Don't reconnect if already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('[WebSocket] Already connected, skipping');
      return;
    }

    // Clean up existing connection if in a bad state
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    isConnectingRef.current = true;
    const wsUrl = `${WS_BASE}/ws?token=${token}`;
    console.log('[WebSocket] Initiating connection...');
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WebSocket] Connected');
      isConnectingRef.current = false;
      if (mountedRef.current) {
        setIsConnected(true);
        setError(null);
      }
      reconnectAttempts.current = 0;
    };

    ws.onclose = (event) => {
      console.log('[WebSocket] Disconnected', event.code, event.reason);
      isConnectingRef.current = false;
      if (mountedRef.current) {
        setIsConnected(false);
        setIsThinking(false);
      }

      // Only reconnect if still mounted and not intentionally closed
      if (mountedRef.current && token && reconnectAttempts.current < 5) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
        reconnectAttempts.current++;
        console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`);
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = (event) => {
      console.error('[WebSocket] Error', event);
      isConnectingRef.current = false;
      if (mountedRef.current) {
        setError('WebSocket connection error');
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        handleMessageRef.current?.(msg);
      } catch (e) {
        console.error('[WebSocket] Failed to parse message', e);
      }
    };
  }, [token]);

  const sendMessage = useCallback((
    message: string,
    conversationId?: string,
    image?: { data: string; mediaType: string }
  ) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('Not connected');
      return;
    }

    // Add user message to display
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    };

    // Add thinking placeholder
    const thinkingMessage: ChatMessage = {
      id: 'thinking',
      role: 'assistant',
      content: '',
      timestamp: new Date().toISOString(),
      isThinking: true,
    };

    setMessages(prev => [...prev, userMessage, thinkingMessage]);
    setError(null);

    const payload: Record<string, unknown> = {
      type: 'chat',
      message,
      conversation_id: conversationId || currentConversationId,
    };

    if (image) {
      payload.image = image.data;
      payload.image_media_type = image.mediaType;
    }

    wsRef.current.send(JSON.stringify(payload));
  }, [currentConversationId]);

  // Connect on mount and when token changes
  useEffect(() => {
    mountedRef.current = true;

    if (token) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      isConnectingRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]); // connect depends on token, so we only need token here

  // Keepalive ping
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [isConnected]);

  return {
    isConnected,
    isThinking,
    thinkingStatus,
    memoryContext,
    messages,
    setMessages,
    sendMessage,
    error,
    currentConversationId,
    conversationTitle,
    recognition,
    setRecognition,
    clearRecognition,
  };
}
