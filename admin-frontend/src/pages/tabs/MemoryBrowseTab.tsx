import { useState, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { memoryApi } from '../../api/client';

type MemoryType = 'all' | 'summary' | 'journal' | 'user_observation' | 'cass_self_observation' | 'per_user_journal';

interface Memory {
  id: string;
  content: string;
  type: string;
  timestamp: string;
  metadata: Record<string, any>;
}

interface GroupedMemories {
  [date: string]: Memory[];
}

export function MemoryBrowseTab() {
  const [filter, setFilter] = useState<MemoryType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchMode, setIsSearchMode] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['memories', filter],
    queryFn: () =>
      memoryApi
        .getAll({ type: filter === 'all' ? undefined : filter, limit: 200 })
        .then((r) => r.data),
    retry: false,
    enabled: !isSearchMode,
  });

  const searchMutation = useMutation({
    mutationFn: (query: string) => memoryApi.search(query, 50).then((r) => r.data),
    onSuccess: () => setIsSearchMode(true),
  });

  const handleSearch = () => {
    if (searchQuery.trim()) {
      searchMutation.mutate(searchQuery);
    }
  };

  const handleClearSearch = () => {
    setIsSearchMode(false);
    setSearchQuery('');
    searchMutation.reset();
  };

  // Group memories by date for timeline view
  const groupedMemories = useMemo(() => {
    const memories = isSearchMode
      ? searchMutation.data?.results
      : data?.memories;

    if (!memories) return {};

    const grouped: GroupedMemories = {};

    for (const memory of memories) {
      const timestamp = memory.timestamp || memory.metadata?.timestamp;
      const date = timestamp
        ? new Date(timestamp).toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })
        : 'Unknown Date';

      if (!grouped[date]) {
        grouped[date] = [];
      }
      grouped[date].push(memory);
    }

    return grouped;
  }, [data, searchMutation.data, isSearchMode]);

  const filters: { value: MemoryType; label: string; count?: number }[] = [
    { value: 'all', label: 'All' },
    { value: 'summary', label: 'Summaries' },
    { value: 'journal', label: 'Journals' },
    { value: 'user_observation', label: 'User Obs' },
    { value: 'cass_self_observation', label: 'Self Obs' },
    { value: 'per_user_journal', label: 'User Journals' },
  ];

  const totalCount = isSearchMode
    ? searchMutation.data?.results?.length || 0
    : data?.memories?.length || 0;

  return (
    <div className="memory-browse-tab">
      <div className="tab-description">
        {isSearchMode
          ? `Search results for "${searchQuery}" (${totalCount} found)`
          : `Browse memories by type (${totalCount} loaded)`
        }
      </div>

      <div className="memory-controls">
        <div className="filter-tabs">
          {filters.map((f) => (
            <button
              key={f.value}
              className={`filter-tab ${filter === f.value && !isSearchMode ? 'active' : ''}`}
              onClick={() => {
                setFilter(f.value);
                handleClearSearch();
              }}
              disabled={isSearchMode}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="search-box">
          <input
            type="text"
            placeholder="Semantic search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          />
          {isSearchMode ? (
            <button className="search-btn clear" onClick={handleClearSearch}>
              Clear
            </button>
          ) : (
            <button
              className="search-btn"
              onClick={handleSearch}
              disabled={!searchQuery.trim() || searchMutation.isPending}
            >
              {searchMutation.isPending ? '...' : 'Search'}
            </button>
          )}
        </div>
      </div>

      <div className="memory-timeline">
        {isLoading || searchMutation.isPending ? (
          <div className="loading-state">Loading memories...</div>
        ) : error || searchMutation.isError ? (
          <div className="error-state">
            Failed to load memories. Is the admin API running?
          </div>
        ) : Object.keys(groupedMemories).length > 0 ? (
          Object.entries(groupedMemories).map(([date, memories]) => (
            <div key={date} className="timeline-group">
              <div className="timeline-date">
                <div className="date-marker" />
                <span>{date}</span>
                <span className="date-count">{memories.length}</span>
              </div>
              <div className="timeline-items">
                {memories.map((memory: Memory) => (
                  <MemoryCard
                    key={memory.id}
                    memory={memory}
                    showSimilarity={isSearchMode}
                  />
                ))}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">No memories found</div>
        )}
      </div>
    </div>
  );
}

function MemoryCard({ memory, showSimilarity }: { memory: any; showSimilarity?: boolean }) {
  const [expanded, setExpanded] = useState(false);

  const typeConfig: Record<string, { color: string; icon: string }> = {
    summary: { color: '#89ddff', icon: 'S' },
    journal: { color: '#c792ea', icon: 'J' },
    user_observation: { color: '#ffcb6b', icon: 'U' },
    cass_self_observation: { color: '#c3e88d', icon: 'C' },
    per_user_journal: { color: '#f78c6c', icon: 'P' },
    conversation: { color: '#82aaff', icon: '>' },
    attractor_marker: { color: '#ff9cac', icon: 'A' },
    project_document: { color: '#ffd580', icon: 'D' },
  };

  const config = typeConfig[memory.type] || { color: '#888', icon: '?' };

  // Extract useful metadata for display
  const conversationId = memory.metadata?.conversation_id;
  const userId = memory.metadata?.user_id;
  const displayName = memory.metadata?.display_name;
  const journalDate = memory.metadata?.journal_date;

  // Get a preview of the content
  const preview = memory.content?.slice(0, 150) + (memory.content?.length > 150 ? '...' : '');

  return (
    <div className={`memory-card ${expanded ? 'expanded' : ''}`}>
      <div
        className="memory-header"
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setExpanded(!expanded)}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
      >
        <div className="memory-type-badge" style={{ backgroundColor: config.color + '20', color: config.color }}>
          <span className="type-icon">{config.icon}</span>
          <span className="type-label">{memory.type?.replace(/_/g, ' ')}</span>
        </div>

        <div className="memory-meta">
          {showSimilarity && memory.similarity && (
            <span className="similarity-badge">
              {(memory.similarity * 100).toFixed(0)}%
            </span>
          )}
          {displayName && (
            <span className="user-badge">@{displayName}</span>
          )}
          {journalDate && (
            <span className="journal-date">{journalDate}</span>
          )}
        </div>

        <span className="memory-time">
          {memory.timestamp
            ? new Date(memory.timestamp).toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
              })
            : ''}
        </span>
        <span className="expand-icon">{expanded ? '−' : '+'}</span>
      </div>

      {!expanded && (
        <div className="memory-preview">
          {preview}
        </div>
      )}

      {expanded && (
        <div className="memory-content">
          <div className="content-text">{memory.content}</div>

          <div className="memory-details">
            {conversationId && (
              <div className="detail-item">
                <span className="detail-label">Conversation:</span>
                <span className="detail-value">{conversationId.slice(0, 8)}...</span>
              </div>
            )}
            {userId && (
              <div className="detail-item">
                <span className="detail-label">User:</span>
                <span className="detail-value">{displayName || userId.slice(0, 8)}</span>
              </div>
            )}
            <div className="detail-item">
              <span className="detail-label">ID:</span>
              <span className="detail-value">{memory.id.slice(0, 16)}...</span>
            </div>
          </div>

          {memory.metadata && Object.keys(memory.metadata).length > 0 && (
            <details className="metadata-section">
              <summary>Raw Metadata</summary>
              <pre>{JSON.stringify(memory.metadata, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
