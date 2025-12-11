import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { conversationsApi } from '../../api/client';

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

interface Observation {
  id: string;
  observation: string;
  category?: string;
  confidence?: number;
  timestamp: string;
  source_type?: string;
}

interface ObservationsData {
  user_observations: Observation[];
  self_observations: Observation[];
}

// Generate markdown export for a conversation
async function generateMarkdownExport(
  conversation: {
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
    messages: Message[];
    summary?: string;
  },
  observations?: ObservationsData
): Promise<string> {
  const lines: string[] = [];

  lines.push(`# ${conversation.title || 'Untitled Conversation'}`);
  lines.push('');
  lines.push(`**ID:** \`${conversation.id}\``);
  lines.push(`**Created:** ${new Date(conversation.created_at).toLocaleString()}`);
  lines.push(`**Updated:** ${new Date(conversation.updated_at).toLocaleString()}`);
  lines.push(`**Messages:** ${conversation.messages?.length || 0}`);
  lines.push('');

  let totalInput = 0;
  let totalOutput = 0;
  const modelUsage: Record<string, number> = {};

  for (const msg of conversation.messages || []) {
    if (msg.token_usage) {
      totalInput += msg.token_usage.input_tokens || 0;
      totalOutput += msg.token_usage.output_tokens || 0;
    }
    if (msg.model && msg.role === 'assistant') {
      const key = msg.provider ? `${msg.provider}/${msg.model}` : msg.model;
      modelUsage[key] = (modelUsage[key] || 0) + 1;
    }
  }

  if (totalInput > 0 || totalOutput > 0) {
    lines.push('## Token Usage');
    lines.push('');
    lines.push(`- **Input tokens:** ${totalInput.toLocaleString()}`);
    lines.push(`- **Output tokens:** ${totalOutput.toLocaleString()}`);
    lines.push(`- **Total tokens:** ${(totalInput + totalOutput).toLocaleString()}`);
    lines.push('');
  }

  if (Object.keys(modelUsage).length > 0) {
    lines.push('## Models Used');
    lines.push('');
    for (const [model, count] of Object.entries(modelUsage)) {
      lines.push(`- **${model}:** ${count} responses`);
    }
    lines.push('');
  }

  if (conversation.summary) {
    lines.push('## Summary');
    lines.push('');
    lines.push(conversation.summary);
    lines.push('');
  }

  if (observations) {
    const hasUserObs = observations.user_observations?.length > 0;
    const hasSelfObs = observations.self_observations?.length > 0;

    if (hasUserObs || hasSelfObs) {
      lines.push('## Observations Generated');
      lines.push('');

      if (hasSelfObs) {
        lines.push('### Self-Observations');
        lines.push('');
        for (const obs of observations.self_observations) {
          lines.push(`- ${obs.observation}`);
          if (obs.category) lines.push(`  - *Category: ${obs.category}*`);
          if (obs.confidence) lines.push(`  - *Confidence: ${(obs.confidence * 100).toFixed(0)}%*`);
        }
        lines.push('');
      }

      if (hasUserObs) {
        lines.push('### User Observations');
        lines.push('');
        for (const obs of observations.user_observations) {
          lines.push(`- ${obs.observation}`);
          if (obs.confidence) lines.push(`  - *Confidence: ${(obs.confidence * 100).toFixed(0)}%*`);
        }
        lines.push('');
      }
    }
  }

  lines.push('---');
  lines.push('');
  lines.push('## Conversation');
  lines.push('');

  for (const msg of conversation.messages || []) {
    const timestamp = new Date(msg.timestamp).toLocaleString();
    const role = msg.role === 'assistant' ? 'Cass' : msg.role === 'user' ? 'User' : 'System';

    lines.push(`### ${role}`);
    lines.push(`*${timestamp}*`);

    if (msg.role === 'assistant') {
      const metaParts: string[] = [];
      if (msg.model) metaParts.push(msg.provider ? `${msg.provider}/${msg.model}` : msg.model);
      if (msg.token_usage) {
        if (msg.token_usage.input_tokens) metaParts.push(`${msg.token_usage.input_tokens} in`);
        if (msg.token_usage.output_tokens) metaParts.push(`${msg.token_usage.output_tokens} out`);
      }
      if (metaParts.length > 0) lines.push(`*[${metaParts.join(' | ')}]*`);
    }

    lines.push('');
    lines.push(msg.content);
    lines.push('');
  }

  lines.push('---');
  lines.push(`*Exported from Cass Vessel on ${new Date().toLocaleString()}*`);

  return lines.join('\n');
}

function downloadMarkdown(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function ConversationsTab() {
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [exporting, setExporting] = useState(false);

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

  const totalTokens = convDetail?.messages?.reduce(
    (acc: { input: number; output: number }, msg: Message) => ({
      input: acc.input + (msg.token_usage?.input_tokens || 0),
      output: acc.output + (msg.token_usage?.output_tokens || 0),
    }),
    { input: 0, output: 0 }
  );

  const handleExport = async () => {
    if (!convDetail || !selectedConvId) return;

    setExporting(true);
    try {
      let observations: ObservationsData | undefined;
      try {
        const obsResponse = await conversationsApi.getObservations(selectedConvId);
        observations = obsResponse.data;
      } catch {
        console.log('Observations not available for this conversation');
      }

      const markdown = await generateMarkdownExport(convDetail, observations);

      const safeTitle = (convDetail.title || 'conversation')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 50);
      const date = new Date(convDetail.created_at).toISOString().split('T')[0];
      const filename = `${date}-${safeTitle}.md`;

      downloadMarkdown(markdown, filename);
    } catch (error) {
      console.error('Export failed:', error);
      alert('Failed to export conversation');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="conversations-tab">
      <div className="conversations-layout">
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
                  <div className="detail-actions">
                    <button
                      className="export-btn"
                      onClick={handleExport}
                      disabled={exporting}
                      title="Export to Markdown"
                    >
                      {exporting ? 'Exporting...' : 'Export'}
                    </button>
                    <code className="detail-id">{convDetail.id}</code>
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
            {showMeta ? '-' : '+'}
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
