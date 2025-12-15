import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { conversationsApi } from '../api/client';
import { useWebSocket } from '../hooks/useWebSocket';
import type { ChatMessage } from '../hooks/useWebSocket';
import { parseGestureTags, formatTokens } from '../utils/gestures';
import { AudioPlayer } from '../components/AudioPlayer';
import './Chat.css';

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

interface ApiMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

interface PendingImage {
  data: string;  // base64
  mediaType: string;
  preview: string;  // data URL for preview
}

export function Chat() {
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [pendingImage, setPendingImage] = useState<PendingImage | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
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
  } = useWebSocket();

  // Fetch conversation list
  const { data: conversations, refetch: refetchConversations } = useQuery({
    queryKey: ['chat-conversations'],
    queryFn: () => conversationsApi.getAll({ limit: 50 }).then((r) => r.data.conversations),
    retry: false,
  });

  // Fetch messages when conversation is selected
  const { data: conversationMessages, isLoading: messagesLoading } = useQuery({
    queryKey: ['chat-messages', selectedConversationId],
    queryFn: () =>
      selectedConversationId
        ? conversationsApi.getMessages(selectedConversationId).then((r) => r.data.messages)
        : Promise.resolve([]),
    enabled: !!selectedConversationId,
    retry: false,
  });

  // Fetch summaries for current conversation
  const { data: summaryData } = useQuery({
    queryKey: ['chat-summaries', selectedConversationId],
    queryFn: () =>
      selectedConversationId
        ? conversationsApi.getSummaries(selectedConversationId).then((r) => r.data)
        : Promise.resolve(null),
    enabled: !!selectedConversationId,
    retry: false,
    refetchInterval: 30000, // Refresh every 30s
  });

  // Load history when conversation messages are fetched
  useEffect(() => {
    if (conversationMessages && conversationMessages.length > 0) {
      const historicalMessages: ChatMessage[] = conversationMessages.map((m: ApiMessage) => ({
        id: m.id || crypto.randomUUID(),
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
      }));
      setMessages(historicalMessages);
    }
  }, [conversationMessages, setMessages]);

  // Update conversation id when response comes with new one
  useEffect(() => {
    if (currentConversationId && currentConversationId !== selectedConversationId) {
      setSelectedConversationId(currentConversationId);
      refetchConversations().then(() => {
        // Restore focus after refetch
        inputRef.current?.focus();
      });
    }
  }, [currentConversationId, selectedConversationId, refetchConversations]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  // Focus input when connected
  useEffect(() => {
    if (isConnected) {
      inputRef.current?.focus();
    }
  }, [isConnected]);

  const handleSend = () => {
    const trimmed = inputValue.trim();
    if ((!trimmed && !pendingImage) || !isConnected) return;

    const imageData = pendingImage
      ? { data: pendingImage.data, mediaType: pendingImage.mediaType }
      : undefined;

    sendMessage(trimmed || '[Image]', selectedConversationId || undefined, imageData);
    setInputValue('');
    setPendingImage(null);
    // Keep focus on input after sending
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      alert('Please select an image file');
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      alert('Image must be less than 10MB');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      // Extract base64 data (remove data:image/xxx;base64, prefix)
      const base64Data = dataUrl.split(',')[1];
      setPendingImage({
        data: base64Data,
        mediaType: file.type,
        preview: dataUrl,
      });
    };
    reader.readAsDataURL(file);

    // Reset input so same file can be selected again
    e.target.value = '';
  };

  const handleRemoveImage = () => {
    setPendingImage(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewConversation = () => {
    setSelectedConversationId(null);
    setMessages([]);
  };

  const handleSelectConversation = (id: string) => {
    if (id !== selectedConversationId) {
      setSelectedConversationId(id);
      setMessages([]); // Clear messages, will be loaded by query
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return date.toLocaleDateString([], { weekday: 'short' });
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  return (
    <div className="chat-page">
      {/* Conversation List Sidebar */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <h2>Conversations</h2>
          <button className="new-chat-btn" onClick={handleNewConversation} title="New conversation">
            +
          </button>
        </div>
        <div className="conversation-list">
          {conversations?.map((conv: Conversation) => (
            <button
              key={conv.id}
              className={`conversation-item ${conv.id === selectedConversationId ? 'active' : ''}`}
              onClick={() => handleSelectConversation(conv.id)}
            >
              <div className="conversation-title">
                {conv.title || 'Untitled conversation'}
              </div>
              <div className="conversation-meta">
                <span>{formatDate(conv.updated_at)}</span>
                <span>{conv.message_count} msgs</span>
              </div>
            </button>
          ))}
          {(!conversations || conversations.length === 0) && (
            <div className="no-conversations">No conversations yet</div>
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-title">
            {selectedConversationId
              ? conversationTitle ||
                conversations?.find((c: Conversation) => c.id === selectedConversationId)?.title ||
                'Conversation'
              : 'New Conversation'}
          </div>
          <div className="header-right">
            <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </div>
          </div>
        </header>

        <div className="messages-container">
          {messagesLoading && (
            <div className="loading-messages">Loading messages...</div>
          )}

          {messages.map((msg) => {
            const parsed = msg.role === 'assistant' ? parseGestureTags(msg.content) : null;
            const displayContent = parsed ? parsed.text : msg.content;

            return (
              <div
                key={msg.id}
                className={`message ${msg.role} ${msg.isThinking ? 'thinking' : ''}`}
              >
                {msg.isThinking ? (
                  <div className="thinking-indicator">
                    <span className="thinking-dots">
                      <span>.</span><span>.</span><span>.</span>
                    </span>
                    <span className="thinking-text">{thinkingStatus || 'Thinking...'}</span>
                  </div>
                ) : (
                  <>
                    {parsed?.thinking && (
                      <details className="message-thinking">
                        <summary>Internal reasoning</summary>
                        <div className="thinking-content">{parsed.thinking}</div>
                      </details>
                    )}
                    <div className="message-content">{displayContent}</div>
                    <div className="message-meta">
                      <span className="message-time">{formatTime(msg.timestamp)}</span>
                      {msg.audio && (
                        <AudioPlayer audio={msg.audio} format={msg.audioFormat} />
                      )}
                      {msg.inputTokens !== undefined && msg.outputTokens !== undefined && (
                        <span className="message-tokens">
                          {formatTokens(msg.inputTokens, msg.outputTokens)}
                        </span>
                      )}
                      {msg.model && (
                        <span className="message-model">{msg.model}</span>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })}

          <div ref={messagesEndRef} />
        </div>

        {error && (
          <div className="chat-error">
            {error}
          </div>
        )}

        <div className="input-area">
          {pendingImage && (
            <div className="image-preview">
              <img src={pendingImage.preview} alt="Preview" />
              <button
                className="remove-image-btn"
                onClick={handleRemoveImage}
                title="Remove image"
              >
                x
              </button>
            </div>
          )}
          <div className="input-row">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelect}
              style={{ display: 'none' }}
            />
            <button
              className="image-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={!isConnected}
              title="Attach image"
            >
              +
            </button>
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isConnected ? 'Type a message...' : 'Connecting...'}
              disabled={!isConnected}
              rows={1}
              autoFocus
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!isConnected || (!inputValue.trim() && !pendingImage)}
            >
              Send
            </button>
          </div>
        </div>
      </main>

      {/* Memory Sidebar (Right) */}
      <aside className="memory-sidebar">
        <div className="memory-sidebar-header">
          <h3>Memory Context</h3>
        </div>
        <div className="memory-sidebar-content">
          {/* Live memory stats from WebSocket */}
          {memoryContext && (
            <div className="memory-stats">
              <div className="memory-stat-row">
                <span className="memory-stat-label">Summaries loaded</span>
                <span className="memory-stat-value">{memoryContext.summaries_count}</span>
              </div>
              <div className="memory-stat-row">
                <span className="memory-stat-label">Recent messages</span>
                <span className="memory-stat-value">{memoryContext.details_count}</span>
              </div>
              <div className="memory-stat-row">
                <span className="memory-stat-label">Context active</span>
                <span className={`memory-stat-value ${memoryContext.has_context ? 'active' : ''}`}>
                  {memoryContext.has_context ? 'Yes' : 'No'}
                </span>
              </div>
            </div>
          )}

          {/* Working Summary */}
          {summaryData?.working_summary && (
            <div className="memory-section">
              <div className="memory-section-header">
                <span className="memory-section-title">Working Summary</span>
              </div>
              <div className="memory-section-items">
                <div className="memory-item">
                  <div className="memory-item-content">{summaryData.working_summary}</div>
                </div>
              </div>
            </div>
          )}

          {/* Summary Chunks */}
          <div className="memory-section">
            <div className="memory-section-header">
              <span className="memory-section-title">Summaries</span>
              <span className="memory-section-count">{summaryData?.count || 0}</span>
            </div>
            <div className="memory-section-items">
              {summaryData?.summaries && summaryData.summaries.length > 0 ? (
                summaryData.summaries.slice(0, 10).map((summary: { id: string; content: string; metadata?: { timestamp?: string } }, idx: number) => (
                  <div key={summary.id || idx} className="memory-item">
                    {summary.metadata?.timestamp && (
                      <div className="memory-item-timestamp">
                        {new Date(summary.metadata.timestamp).toLocaleString()}
                      </div>
                    )}
                    <div className="memory-item-content">
                      {summary.content.length > 200
                        ? summary.content.substring(0, 200) + '...'
                        : summary.content}
                    </div>
                  </div>
                ))
              ) : (
                <div className="memory-empty">
                  {selectedConversationId
                    ? 'No summaries yet'
                    : 'Select a conversation'}
                </div>
              )}
            </div>
          </div>
        </div>
      </aside>
    </div>
  );
}
