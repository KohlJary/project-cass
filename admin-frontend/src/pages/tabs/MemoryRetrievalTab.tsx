import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { memoryApi } from '../../api/client';

interface RetrievalResult {
  id: string;
  content: string;
  type: string;
  similarity: number;
  metadata: Record<string, any>;
}

export function MemoryRetrievalTab() {
  const [query, setQuery] = useState('');
  const [resultLimit, setResultLimit] = useState(10);
  const [showContextPreview, setShowContextPreview] = useState(false);

  const searchMutation = useMutation({
    mutationFn: (q: string) => memoryApi.search(q, resultLimit).then((r) => r.data),
  });

  const handleSearch = () => {
    if (query.trim()) {
      searchMutation.mutate(query);
    }
  };

  const results = searchMutation.data?.results || [];
  const totalTokensEstimate = results.reduce((acc: number, r: RetrievalResult) => {
    return acc + Math.ceil((r.content?.length || 0) / 4); // Rough token estimate
  }, 0);

  // Build context preview (what would be injected into prompt)
  const contextPreview = results
    .map((r: RetrievalResult, i: number) =>
      `[Memory ${i + 1} - ${r.type} (${(r.similarity * 100).toFixed(0)}% match)]\n${r.content}`
    )
    .join('\n\n---\n\n');

  return (
    <div className="retrieval-tab">
      <div className="tab-description">
        Test what memories would be retrieved for a given query
      </div>

      <div className="retrieval-layout">
        {/* Query input panel */}
        <div className="query-panel">
          <div className="panel-section">
            <h3>Test Query</h3>
            <textarea
              placeholder="Enter a message to see what Cass would remember..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && e.ctrlKey && handleSearch()}
              rows={4}
            />
            <div className="query-controls">
              <div className="limit-control">
                <label>Results:</label>
                <select
                  value={resultLimit}
                  onChange={(e) => setResultLimit(Number(e.target.value))}
                >
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
              </div>
              <button
                className="search-btn"
                onClick={handleSearch}
                disabled={searchMutation.isPending || !query.trim()}
              >
                {searchMutation.isPending ? 'Searching...' : 'Test Retrieval'}
              </button>
            </div>
            <p className="hint">Ctrl+Enter to search</p>
          </div>

          {/* Stats */}
          {results.length > 0 && (
            <div className="panel-section stats">
              <h3>Retrieval Stats</h3>
              <div className="stat-grid">
                <div className="stat">
                  <span className="stat-value">{results.length}</span>
                  <span className="stat-label">Results</span>
                </div>
                <div className="stat">
                  <span className="stat-value">~{totalTokensEstimate.toLocaleString()}</span>
                  <span className="stat-label">Est. Tokens</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {results.length > 0 ? (results[0].similarity * 100).toFixed(0) : 0}%
                  </span>
                  <span className="stat-label">Top Match</span>
                </div>
              </div>
              <div className="type-breakdown">
                {Object.entries(
                  results.reduce((acc: Record<string, number>, r: RetrievalResult) => {
                    acc[r.type] = (acc[r.type] || 0) + 1;
                    return acc;
                  }, {})
                ).map(([type, count]) => (
                  <span key={type} className="type-tag">
                    {type}: {count as number}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Results panel */}
        <div className="results-panel">
          <div className="results-header">
            <h3>Retrieved Memories</h3>
            {results.length > 0 && (
              <button
                className={`toggle-btn ${showContextPreview ? 'active' : ''}`}
                onClick={() => setShowContextPreview(!showContextPreview)}
              >
                {showContextPreview ? 'Show Cards' : 'Show Context'}
              </button>
            )}
          </div>

          {searchMutation.isError && (
            <div className="error-state">
              Search failed. Is the admin API running?
            </div>
          )}

          {!searchMutation.data && !searchMutation.isPending && (
            <div className="empty-state">
              <div className="empty-icon">?</div>
              <p>Enter a query to test memory retrieval</p>
              <p className="hint">This shows what context would be injected into Cass's prompt</p>
            </div>
          )}

          {searchMutation.isPending && (
            <div className="loading-state">Searching memories...</div>
          )}

          {results.length > 0 && (
            showContextPreview ? (
              <div className="context-preview">
                <div className="preview-header">
                  <span>Context that would be injected into prompt:</span>
                  <span className="token-count">~{totalTokensEstimate} tokens</span>
                </div>
                <pre>{contextPreview}</pre>
              </div>
            ) : (
              <div className="results-list">
                {results.map((result: RetrievalResult, i: number) => (
                  <ResultCard key={result.id || i} result={result} rank={i + 1} />
                ))}
              </div>
            )
          )}

          {searchMutation.data && results.length === 0 && (
            <div className="empty-state">
              <p>No memories found matching this query</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultCard({ result, rank }: { result: RetrievalResult; rank: number }) {
  const [expanded, setExpanded] = useState(false);

  const typeColors: Record<string, string> = {
    summary: '#89ddff',
    journal: '#c792ea',
    conversation: '#82aaff',
    user_observation: '#ffcb6b',
    self_observation: '#c3e88d',
    per_user_journal: '#f78c6c',
    cass_self_observation: '#c3e88d',
    attractor_marker: '#ff9cac',
    project_document: '#ffd580',
  };

  const color = typeColors[result.type] || '#888';
  const similarityPercent = (result.similarity * 100).toFixed(1);

  return (
    <div className={`result-card ${expanded ? 'expanded' : ''}`}>
      <div
        className="result-header"
        onClick={() => setExpanded(!expanded)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setExpanded(!expanded)}
        tabIndex={0}
        role="button"
        aria-expanded={expanded}
      >
        <span className="result-rank">#{rank}</span>
        <span className="result-type" style={{ color }}>{result.type}</span>
        <div className="similarity-bar-container">
          <div
            className="similarity-bar"
            style={{
              width: `${result.similarity * 100}%`,
              backgroundColor: color
            }}
          />
        </div>
        <span className="result-score">{similarityPercent}%</span>
        <span className="expand-icon">{expanded ? '−' : '+'}</span>
      </div>

      <div className="result-preview">
        {result.content?.slice(0, 150)}
        {(result.content?.length || 0) > 150 && '...'}
      </div>

      {expanded && (
        <div className="result-content">
          <div className="content-full">{result.content}</div>
          {result.metadata && Object.keys(result.metadata).length > 0 && (
            <details className="result-metadata">
              <summary>Metadata</summary>
              <pre>{JSON.stringify(result.metadata, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
