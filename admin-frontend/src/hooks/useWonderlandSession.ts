import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';

const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (window.location.hostname === 'localhost') return 'http://localhost:8000';
  return window.location.origin;
};
const API_BASE = getApiBase();
const WS_BASE = API_BASE.replace(/^http/, 'ws');

export interface SessionEvent {
  event_id: string;
  event_type: string;
  timestamp: string;
  location: string;
  location_name: string;
  description: string;
  raw_output: string;
  daemon_thought?: string;
}

export interface ExplorationGoal {
  goal_id: string;
  title: string;
  goal_type: string;
  target_value: number;
  current_value: number;
  is_completed: boolean;
  completed_at?: string;
}

export interface GoalPreset {
  id: string;
  title: string;
  type: string;
  target: number;
}

export interface ConversationMessage {
  speaker: string;
  content: string;
  is_daemon: boolean;
  daemon_thought?: string;
}

export interface ConversationState {
  active: boolean;
  npc_name?: string;
  npc_title?: string;
  messages: ConversationMessage[];
}

export interface ExplorationSession {
  session_id: string;
  daemon_id: string;
  daemon_name: string;
  user_id: string;
  started_at: string;
  status: string;
  ended_at?: string;
  end_reason?: string;
  events: SessionEvent[];
  rooms_visited: string[];
  current_room: string;
  current_room_name: string;
  goal?: ExplorationGoal;
}

interface UseWonderlandSessionOptions {
  onEvent?: (event: SessionEvent) => void;
  onSessionEnded?: (reason: string) => void;
  onGoalProgress?: (goal: ExplorationGoal) => void;
  onGoalCompleted?: (goal: ExplorationGoal) => void;
  onConversationStart?: (npcName: string, npcTitle: string) => void;
  onConversationMessage?: (message: ConversationMessage) => void;
  onConversationEnd?: (npcName: string) => void;
}

export function useWonderlandSession(options: UseWonderlandSessionOptions = {}) {
  const { token } = useAuth();
  const [session, setSession] = useState<ExplorationSession | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [currentRoom, setCurrentRoom] = useState<string>('');
  const [currentRoomName, setCurrentRoomName] = useState<string>('');
  const [status, setStatus] = useState<'idle' | 'connecting' | 'active' | 'ended' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [goal, setGoal] = useState<ExplorationGoal | null>(null);
  const [goalPresets, setGoalPresets] = useState<GoalPreset[]>([]);
  const [conversation, setConversation] = useState<ConversationState>({
    active: false,
    messages: [],
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch goal presets
  const fetchPresets = useCallback(async () => {
    if (!token) return;

    try {
      const response = await fetch(`${API_BASE}/admin/wonderland/presets`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setGoalPresets(data.presets || []);
      }
    } catch (err) {
      console.error('Failed to fetch presets:', err);
    }
  }, [token]);

  // Fetch presets on mount
  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  // Start a new session
  const startSession = useCallback(async (
    daemonName: string = 'Cass',
    daemonId?: string,
    goalPreset?: string
  ) => {
    if (!token) {
      setError('Not authenticated');
      return null;
    }

    setStatus('connecting');
    setError(null);
    setEvents([]);
    setGoal(null);

    try {
      const body: { daemon_name: string; daemon_id?: string; goal_preset?: string } = {
        daemon_name: daemonName
      };
      if (daemonId) {
        body.daemon_id = daemonId;
      }
      if (goalPreset) {
        body.goal_preset = goalPreset;
      }

      const response = await fetch(`${API_BASE}/admin/wonderland/sessions?user_id=default`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to start session');
      }

      const data = await response.json();

      // Set initial goal from response
      if (data.goal) {
        setGoal(data.goal);
      }

      // Connect WebSocket to stream events
      connectWebSocket(data.session_id);

      return data.session_id;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session');
      setStatus('error');
      return null;
    }
  }, [token]);

  // Connect to WebSocket for event streaming
  const connectWebSocket = useCallback((sessionId: string) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const ws = new WebSocket(`${WS_BASE}/admin/wonderland/sessions/${sessionId}/stream`);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('active');
      // Start ping interval
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send('ping');
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'session_state') {
          // Initial state
          setSession(data.session);
          setCurrentRoom(data.session.current_room);
          setCurrentRoomName(data.session.current_room_name);
          setEvents(data.session.events || []);
          if (data.session.goal) {
            setGoal(data.session.goal);
          }
        } else if (data.type === 'session_event') {
          // New event
          const newEvent = data.event as SessionEvent;
          setEvents(prev => [...prev, newEvent]);

          // Update room if it changed
          if (newEvent.location) {
            setCurrentRoom(newEvent.location);
            setCurrentRoomName(newEvent.location_name);
          }

          // Callback
          options.onEvent?.(newEvent);
        } else if (data.type === 'goal_progress') {
          // Goal progress update
          const updatedGoal = data.goal as ExplorationGoal;
          setGoal(updatedGoal);
          options.onGoalProgress?.(updatedGoal);
        } else if (data.type === 'goal_completed') {
          // Goal completed
          const completedGoal = data.goal as ExplorationGoal;
          setGoal(completedGoal);
          options.onGoalCompleted?.(completedGoal);
        } else if (data.type === 'conversation_start') {
          // NPC conversation started
          setConversation({
            active: true,
            npc_name: data.npc_name,
            npc_title: data.npc_title,
            messages: [],
          });
          options.onConversationStart?.(data.npc_name, data.npc_title);
        } else if (data.type === 'conversation_message') {
          // Conversation message
          const message: ConversationMessage = {
            speaker: data.speaker,
            content: data.content,
            is_daemon: data.is_daemon,
            daemon_thought: data.daemon_thought,
          };
          setConversation(prev => ({
            ...prev,
            messages: [...prev.messages, message],
          }));
          options.onConversationMessage?.(message);
        } else if (data.type === 'conversation_end') {
          // NPC conversation ended
          setConversation({
            active: false,
            messages: [],
          });
          options.onConversationEnd?.(data.npc_name);
        } else if (data.type === 'session_ended') {
          setStatus('ended');
          options.onSessionEnded?.(data.reason);
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      setError('WebSocket connection error');
      setStatus('error');
    };

    ws.onclose = () => {
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      if (status === 'active') {
        setStatus('ended');
      }
    };
  }, [options, status]);

  // End the current session
  const endSession = useCallback(async () => {
    if (!session || !token) return;

    try {
      await fetch(`${API_BASE}/admin/wonderland/sessions/${session.session_id}/end?reason=user_request`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
    } catch (err) {
      console.error('Failed to end session:', err);
    }

    // Close WebSocket
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    setStatus('ended');
  }, [session, token]);

  // Export session
  const exportSession = useCallback(async (format: 'md' | 'json' = 'md') => {
    if (!session || !token) return null;

    try {
      const response = await fetch(
        `${API_BASE}/admin/wonderland/sessions/${session.session_id}/export?format=${format}`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to export session');
      }

      const data = await response.json();
      return data.content;
    } catch (err) {
      console.error('Failed to export session:', err);
      return null;
    }
  }, [session, token]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
    };
  }, []);

  return {
    session,
    events,
    currentRoom,
    currentRoomName,
    status,
    error,
    goal,
    goalPresets,
    conversation,
    startSession,
    endSession,
    exportSession,
    fetchPresets,
  };
}
