import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { conversationsApi } from '../api/client';
import './Conversations.css';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  token_usage?: {
    input_tokens?: number;
    output_tokens?: number;
  };
  model?: string;
  provider?: string;
}

interface Conversation {
  id: string;
  title: string;
  user_id?: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export function Conversations() {
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const { data, isLoading, error } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => conversationsApi.getAll({ limit: 100 }).then((r) => r.data),
    retry: false,
  });

  const { data: convDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['conversation', selectedConvId],
    queryFn: () =>
      selectedConvId ? conversationsApi.getById(selectedConvId).then((r) => r.data) : null,
    enabled: !!selectedConvId,
    retry: false,
  });

  const conversations = data?.conversations || [];
  const filteredConversations = searchQuery
    ? conversations.filter((c: Conversation) =>
        c.title?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : conversations;

  // Calculate total tokens for conversation
  const totalTokens = convDetail?.messages?.reduce(
    (acc: { input: number; output: number }, msg: Message) => {
      return {
        input: acc.input + (msg.token_usage?.input_tokens || 0),
        output: acc.output + (msg.token_usage?.output_tokens || 0),
      };
    },
    { input: 0, output: 0 }
  );

  return (
    <div className="conversations-page">
      <header className="page-header">
        <h1>Conversations</h1>
        <p className="subtitle">Browse conversation history and messages</p>
      </header>

      <div className="conversations-layout">
        {/* Conversation list panel */}
        <div className="conv-list-panel">
          <div className="panel-header">
            <h2>All Conversations</h2>
            <span className="count">{conversations.length}</span>
          </div>

          <div className="search-box">
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {isLoading ? (
            <div className="loading-state">Loading conversations...</div>
          ) : error ? (
            <div className="error-state">Failed to load conversations</div>
          ) : filteredConversations.length > 0 ? (
            <div className="conv-list">
              {filteredConversations.map((conv: Conversation) => (
                <div
                  key={conv.id}
                  className={`conv-item ${selectedConvId === conv.id ? 'selected' : ''}`}
                  onClick={() => setSelectedConvId(conv.id)}
                >
                  <div className="conv-title">{conv.title || 'Untitled'}</div>
                  <div className="conv-meta">
                    <span className="msg-count">{conv.message_count} messages</span>
                    <span className="conv-date">
                      {new Date(conv.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              {searchQuery ? 'No matching conversations' : 'No conversations yet'}
            </div>
          )}
        </div>

        {/* Conversation detail panel */}
        <div className="conv-detail-panel">
          {selectedConvId ? (
            detailLoading ? (
              <div className="loading-state">Loading conversation...</div>
            ) : convDetail ? (
              <div className="conv-detail">
                <div className="detail-header">
                  <div className="detail-info">
                    <h2>{convDetail.title || 'Untitled Conversation'}</h2>
                    <div className="detail-meta">
                      <span className="meta-item">
                        {convDetail.messages?.length || 0} messages
                      </span>
                      {totalTokens && (totalTokens.input > 0 || totalTokens.output > 0) && (
                        <span className="meta-item tokens">
                          {totalTokens.input.toLocaleString()} in / {totalTokens.output.toLocaleString()} out tokens
                        </span>
                      )}
                      <span className="meta-item">
                        {new Date(convDetail.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                  <div className="detail-id">
                    <code>{convDetail.id}</code>
                  </div>
                </div>

                <div className="messages-container">
                  {convDetail.messages?.map((msg: Message, i: number) => (
                    <MessageBubble key={msg.id || i} message={msg} />
                  ))}
                </div>
              </div>
            ) : (
              <div className="error-state">Failed to load conversation</div>
            )
          ) : (
            <div className="empty-state">
              <div className="empty-icon">#</div>
              <p>Select a conversation to view messages</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const [showMeta, setShowMeta] = useState(false);

  const roleColors: Record<string, string> = {
    user: '#89ddff',
    assistant: '#c792ea',
    system: '#666',
  };

  const roleLabels: Record<string, string> = {
    user: 'User',
    assistant: 'Cass',
    system: 'System',
  };

  return (
    <div className={`message-bubble ${message.role}`}>
      <div className="message-header">
        <span className="message-role" style={{ color: roleColors[message.role] }}>
          {roleLabels[message.role] || message.role}
        </span>
        <span className="message-time">
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
        {(message.token_usage || message.model) && (
          <button
            className={`meta-toggle ${showMeta ? 'active' : ''}`}
            onClick={() => setShowMeta(!showMeta)}
          >
            {showMeta ? '−' : '+'}
          </button>
        )}
      </div>

      <div className="message-content">{message.content}</div>

      {showMeta && (message.token_usage || message.model) && (
        <div className="message-meta">
          {message.model && (
            <span className="meta-tag model">
              {message.provider}/{message.model}
            </span>
          )}
          {message.token_usage && (
            <>
              {message.token_usage.input_tokens && (
                <span className="meta-tag tokens-in">
                  {message.token_usage.input_tokens} in
                </span>
              )}
              {message.token_usage.output_tokens && (
                <span className="meta-tag tokens-out">
                  {message.token_usage.output_tokens} out
                </span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
