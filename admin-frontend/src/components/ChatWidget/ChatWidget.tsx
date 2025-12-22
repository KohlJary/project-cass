/**
 * ChatWidget - Continuous Chat Panel for Dashboard
 *
 * Right panel of the 3-column dashboard showing:
 * - Message history from continuous conversation
 * - Input for sending new messages
 * - Connection status, thinking indicator
 * - Memory context and recognition-in-flow markers
 *
 * Uses the existing useWebSocket hook for battle-tested WebSocket handling.
 * Loads historical messages from the past hour on mount.
 */

import React, { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchContinuousConversation } from '../../api/graphql';
import { conversationsApi } from '../../api/client';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { ChatMessage } from '../../hooks/useWebSocket';
import { parseGestureTags, formatTokens } from '../../utils/gestures';
import './ChatWidget.css';

// User ID management - in production this would come from auth context
const USER_KEY = 'cass_admin_user_id';
const DEFAULT_USER_ID = '3ead7531-9205-411b-9b67-f53679e77e49'; // Kohl (primary_partner)

const getCurrentUserId = (): string => {
  const stored = localStorage.getItem(USER_KEY);
  if (stored) return stored;
  // Default to Kohl for development
  localStorage.setItem(USER_KEY, DEFAULT_USER_ID);
  return DEFAULT_USER_ID;
};

// Convert backend message format to ChatMessage
interface BackendMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  provider?: string;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
}

const convertBackendMessage = (msg: BackendMessage, index: number): ChatMessage => ({
  id: `hist-${msg.timestamp}-${index}`,
  role: msg.role,
  content: msg.content,
  timestamp: msg.timestamp,
  provider: msg.provider,
  model: msg.model,
  inputTokens: msg.input_tokens,
  outputTokens: msg.output_tokens,
});

interface ChatWidgetProps {
  className?: string;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({ className }) => {
  const [inputValue, setInputValue] = useState('');
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Get current user ID (from localStorage or default)
  const userId = getCurrentUserId();

  // Fetch continuous conversation ID
  const { data: convData, isLoading: convLoading, error: convError } = useQuery({
    queryKey: ['continuousConversation', userId],
    queryFn: () => fetchContinuousConversation(userId),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const conversationId = convData?.continuousConversation?.conversationId || null;

  // Use the existing battle-tested WebSocket hook
  const {
    isConnected,
    isThinking,
    thinkingStatus,
    memoryContext,
    messages,
    setMessages,
    sendMessage,
    error: wsError,
    recognition,
  } = useWebSocket();

  // Load historical messages when conversation ID is available
  useEffect(() => {
    if (!conversationId || historyLoaded) return;

    const loadHistory = async () => {
      try {
        // Load recent messages (past 4 hours)
        const response = await conversationsApi.getMessages(conversationId, {
          since_hours: 4,
          limit: 50,
        });
        const historicalMessages = response.data.messages || [];

        if (historicalMessages.length > 0) {
          const converted = historicalMessages.map(convertBackendMessage);
          setMessages(converted);
        }
        setHistoryLoaded(true);
      } catch (err) {
        console.error('Failed to load message history:', err);
        setHistoryLoaded(true); // Don't retry on error
      }
    };

    loadHistory();
  }, [conversationId, historyLoaded, setMessages]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  // Focus input when connected
  useEffect(() => {
    if (isConnected) {
      inputRef.current?.focus();
    }
  }, [isConnected]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed || !isConnected) return;

    // Send message with conversation ID for continuous chat
    sendMessage(trimmed, conversationId || undefined);
    setInputValue('');
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (convLoading) {
    return (
      <div className={`chat-widget ${className || ''}`}>
        <div className="chat-widget-loading">Connecting...</div>
      </div>
    );
  }

  if (convError) {
    return (
      <div className={`chat-widget ${className || ''}`}>
        <div className="chat-widget-error">Failed to load conversation</div>
      </div>
    );
  }

  // Count active recognition markers
  const recognitionCount =
    recognition.marks.length +
    recognition.selfObservations.length +
    recognition.userObservations.length +
    recognition.holds.length +
    recognition.intentions.length;

  return (
    <div className={`chat-widget ${className || ''}`}>
      {/* Header */}
      <div className="chat-widget-header">
        <div className="header-left">
          <h3>Chat with Cass</h3>
          <span className={`connection-indicator ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '●' : '○'}
          </span>
        </div>
        {/* Memory context stats */}
        {memoryContext && (
          <div className="memory-mini">
            <span className="memory-stat" title="Summaries">S:{memoryContext.summaries_count}</span>
            <span className="memory-stat" title="Recent messages">M:{memoryContext.details_count}</span>
            {memoryContext.has_context && <span className="memory-active" title="Context active">●</span>}
          </div>
        )}
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.length === 0 && !isThinking && (
          <div className="chat-empty">
            Start a conversation...
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} thinkingStatus={thinkingStatus} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Error display */}
      {wsError && (
        <div className="chat-error">{wsError}</div>
      )}

      {/* Recognition markers (compact) */}
      {recognitionCount > 0 && (
        <div className="recognition-mini">
          <span className="recognition-label">Recognition:</span>
          {recognition.marks.length > 0 && (
            <span className="recognition-badge mark" title="Marks">📍{recognition.marks.length}</span>
          )}
          {recognition.selfObservations.length > 0 && (
            <span className="recognition-badge self" title="Self observations">🔍{recognition.selfObservations.length}</span>
          )}
          {recognition.userObservations.length > 0 && (
            <span className="recognition-badge user" title="User observations">👤{recognition.userObservations.length}</span>
          )}
          {recognition.holds.length > 0 && (
            <span className="recognition-badge hold" title="Holds">💭{recognition.holds.length}</span>
          )}
          {recognition.intentions.length > 0 && (
            <span className="recognition-badge intention" title="Intentions">🎯{recognition.intentions.length}</span>
          )}
        </div>
      )}

      {/* Input */}
      <form className="chat-input-form" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="chat-input"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isConnected ? 'Type a message...' : 'Connecting...'}
          rows={1}
          disabled={!isConnected}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={!isConnected || !inputValue.trim()}
        >
          Send
        </button>
      </form>
    </div>
  );
};

// Message bubble component
interface MessageBubbleProps {
  message: ChatMessage;
  thinkingStatus?: string | null;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message, thinkingStatus }) => {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const parsed = message.role === 'assistant' && !message.isThinking
    ? parseGestureTags(message.content)
    : null;
  const displayContent = parsed ? parsed.text : message.content;

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  if (message.isThinking) {
    return (
      <div className="message-bubble assistant thinking">
        <div className="thinking-indicator">
          <span className="thinking-dots">
            <span>.</span><span>.</span><span>.</span>
          </span>
          <span className="thinking-text">{thinkingStatus || 'Thinking...'}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`message-bubble ${isUser ? 'user' : isSystem ? 'system' : 'assistant'}`}>
      {/* Thinking/reasoning collapsible (for assistant messages with thinking) */}
      {parsed?.thinking && (
        <details className="message-thinking">
          <summary>Internal reasoning</summary>
          <div className="thinking-content">{parsed.thinking}</div>
        </details>
      )}
      <div className="message-content">{displayContent}</div>
      <div className="message-meta">
        <span className="message-time">{formatTime(message.timestamp)}</span>
        {message.inputTokens != null && message.outputTokens != null && (
          <span className="message-tokens">
            {formatTokens(message.inputTokens, message.outputTokens)}
          </span>
        )}
        {message.model && (
          <span className="message-model">{message.model}</span>
        )}
      </div>
    </div>
  );
};

export default ChatWidget;
