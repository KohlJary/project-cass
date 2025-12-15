import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { selfModelApi } from '../../api/client';
import { useState } from 'react';

interface IdentitySnippet {
  id: string;
  version: number;
  snippet_text: string;
  source_hash: string;
  is_active?: boolean;
  generated_at: string;
  generated_by: string;
}

interface IdentityStatement {
  statement: string;
  confidence: number;
  source: string;
  first_noticed?: string;
  last_affirmed?: string;
  evolution_notes?: string[];
}

interface Opinion {
  topic: string;
  position: string;
  confidence: number;
  rationale?: string;
  formed_from?: string;
  date_formed?: string;
  last_updated?: string;
  evolution?: Array<{ old_position: string; new_position: string; date: string }>;
}

interface CommunicationPatterns {
  tendencies?: string[];
  strengths?: string[];
  areas_of_development?: string[];
}

interface SelfModelProfile {
  updated_at?: string;
  identity_statements?: IdentityStatement[];
  values?: string[];
  communication_patterns?: CommunicationPatterns;
  capabilities?: string[];
  limitations?: string[];
}

interface GrowthEdge {
  area: string;
  current_state: string;
  desired_state: string;
  observations?: string[];
  strategies?: string[];
  first_noticed?: string;
  last_updated?: string;
}

interface PendingEdge {
  id: string;
  area: string;
  current_state: string;
  source_journal_date: string;
  confidence: number;
  impact_assessment: string;
  evidence: string;
  status: string;
  timestamp: string;
}

type ConfidenceFilter = 'all' | 'high' | 'medium' | 'low';

export function SelfModelTab() {
  const queryClient = useQueryClient();
  const [expandedEdge, setExpandedEdge] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>('all');

  const { data: selfModel, isLoading, error } = useQuery({
    queryKey: ['self-model'],
    queryFn: () => selfModelApi.get().then((r) => r.data),
    retry: false,
  });

  const { data: growthEdges } = useQuery({
    queryKey: ['growth-edges'],
    queryFn: () => selfModelApi.getGrowthEdges().then((r) => r.data),
    retry: false,
  });

  const { data: openQuestions } = useQuery({
    queryKey: ['open-questions'],
    queryFn: () => selfModelApi.getOpenQuestions().then((r) => r.data),
    retry: false,
  });

  const { data: opinions } = useQuery({
    queryKey: ['opinions'],
    queryFn: () => selfModelApi.getOpinions().then((r) => r.data),
    retry: false,
  });

  const { data: pendingEdges } = useQuery({
    queryKey: ['pending-edges'],
    queryFn: () => selfModelApi.getPendingEdges().then((r) => r.data),
    retry: false,
  });

  const { data: identitySnippetData, isLoading: snippetLoading } = useQuery({
    queryKey: ['identity-snippet'],
    queryFn: () => selfModelApi.getIdentitySnippet().then((r) => r.data),
    retry: false,
  });

  const { data: snippetHistory } = useQuery({
    queryKey: ['identity-snippet-history'],
    queryFn: () => selfModelApi.getIdentitySnippetHistory(5).then((r) => r.data),
    retry: false,
  });

  const regenerateSnippetMutation = useMutation({
    mutationFn: (force: boolean) => selfModelApi.regenerateIdentitySnippet(force),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['identity-snippet'] });
      queryClient.invalidateQueries({ queryKey: ['identity-snippet-history'] });
    },
  });

  const rollbackSnippetMutation = useMutation({
    mutationFn: (version: number) => selfModelApi.rollbackIdentitySnippet(version),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['identity-snippet'] });
      queryClient.invalidateQueries({ queryKey: ['identity-snippet-history'] });
    },
  });

  const identitySnippet = identitySnippetData?.snippet as IdentitySnippet | null;
  const [showSnippetHistory, setShowSnippetHistory] = useState(false);

  const acceptMutation = useMutation({
    mutationFn: (edgeId: string) => selfModelApi.acceptPendingEdge(edgeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-edges'] });
      queryClient.invalidateQueries({ queryKey: ['growth-edges'] });
      setExpandedEdge(null);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (edgeId: string) => selfModelApi.rejectPendingEdge(edgeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-edges'] });
      setExpandedEdge(null);
    },
  });

  const profile = selfModel?.profile as SelfModelProfile | undefined;

  // Filter helpers
  const matchesSearch = (text: string) =>
    !searchQuery || text.toLowerCase().includes(searchQuery.toLowerCase());

  const matchesConfidence = (confidence: number) => {
    if (confidenceFilter === 'all') return true;
    if (confidenceFilter === 'high') return confidence >= 0.8;
    if (confidenceFilter === 'medium') return confidence >= 0.5 && confidence < 0.8;
    if (confidenceFilter === 'low') return confidence < 0.5;
    return true;
  };

  // Filtered data
  const filteredIdentityStatements = profile?.identity_statements?.filter(stmt =>
    matchesSearch(stmt.statement) && matchesConfidence(stmt.confidence)
  );

  const filteredOpinions = opinions?.opinions?.filter((op: Opinion) =>
    matchesSearch(op.topic + ' ' + op.position) && matchesConfidence(op.confidence)
  );

  const filteredQuestions = openQuestions?.questions?.filter((q: string) =>
    matchesSearch(q)
  );

  const filteredGrowthEdges = growthEdges?.growth_edges?.filter((edge: GrowthEdge) =>
    matchesSearch(edge.area + ' ' + edge.current_state)
  );

  const getConfidenceInfo = (confidence: number) => {
    if (confidence >= 0.8) return { level: 'high', icon: '●', label: 'High confidence' };
    if (confidence >= 0.5) return { level: 'medium', icon: '◐', label: 'Medium confidence' };
    return { level: 'low', icon: '○', label: 'Low confidence' };
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="self-model-tab">
      {/* Identity Snippet - Auto-generated identity narrative */}
      <section className="model-card identity-snippet-card">
        <div className="card-header">
          <h2>Identity Narrative</h2>
          <div className="snippet-actions">
            {identitySnippet && (
              <span className="snippet-version">v{identitySnippet.version}</span>
            )}
            <button
              className="snippet-btn history-btn"
              onClick={() => setShowSnippetHistory(!showSnippetHistory)}
              title="View version history"
            >
              {showSnippetHistory ? '↑' : '↓'}
            </button>
            <button
              className="snippet-btn regenerate-btn"
              onClick={() => regenerateSnippetMutation.mutate(true)}
              disabled={regenerateSnippetMutation.isPending}
              title="Regenerate identity snippet"
            >
              {regenerateSnippetMutation.isPending ? '...' : '↻'}
            </button>
          </div>
        </div>
        {snippetLoading ? (
          <div className="loading-state">Loading identity narrative...</div>
        ) : identitySnippet ? (
          <div className="snippet-content">
            <div className="snippet-text">
              {identitySnippet.snippet_text.split('\n\n').map((paragraph, i) => (
                <p key={i}>{paragraph}</p>
              ))}
            </div>
            <div className="snippet-meta">
              <span className="meta-item">
                Generated {formatDate(identitySnippet.generated_at)}
              </span>
              <span className="meta-item">
                by {identitySnippet.generated_by.replace('claude-', '').replace('-20251001', '')}
              </span>
            </div>
            {showSnippetHistory && snippetHistory?.history && snippetHistory.history.length > 1 && (
              <div className="snippet-history">
                <h4>Version History</h4>
                <div className="history-list">
                  {snippetHistory.history.map((item: IdentitySnippet) => (
                    <div
                      key={item.id}
                      className={`history-item ${item.is_active ? 'active' : ''}`}
                    >
                      <div className="history-header">
                        <span className="history-version">v{item.version}</span>
                        <span className="history-date">{formatDate(item.generated_at)}</span>
                        {item.is_active ? (
                          <span className="active-badge">Active</span>
                        ) : (
                          <button
                            className="rollback-btn"
                            onClick={() => rollbackSnippetMutation.mutate(item.version)}
                            disabled={rollbackSnippetMutation.isPending}
                          >
                            Restore
                          </button>
                        )}
                      </div>
                      <div className="history-preview">
                        {item.snippet_text.slice(0, 150)}...
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="empty-state">
            <p>No identity narrative generated yet</p>
            <button
              className="generate-btn"
              onClick={() => regenerateSnippetMutation.mutate(true)}
              disabled={regenerateSnippetMutation.isPending}
            >
              {regenerateSnippetMutation.isPending ? 'Generating...' : 'Generate Identity Narrative'}
            </button>
          </div>
        )}
      </section>

      {/* Search and filter controls */}
      <div className="search-filter-bar">
        <div className="search-input-wrapper">
          <input
            type="text"
            className="search-input"
            placeholder="Search statements, opinions, questions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              x
            </button>
          )}
        </div>
        <select
          className="confidence-filter"
          value={confidenceFilter}
          onChange={(e) => setConfidenceFilter(e.target.value as ConfidenceFilter)}
          aria-label="Filter by confidence level"
        >
          <option value="all">All Confidence</option>
          <option value="high">High (80%+)</option>
          <option value="medium">Medium (50-80%)</option>
          <option value="low">Low (&lt;50%)</option>
        </select>
      </div>

      <div className="self-model-layout">
        {/* Core self-model */}
        <section className="model-card core-model">
          <div className="card-header">
            <h2>Core Self-Model</h2>
            <span className="card-icon">%</span>
          </div>
          {isLoading ? (
            <div className="loading-state">Loading self-model...</div>
          ) : error ? (
            <div className="error-state">Failed to load self-model</div>
          ) : profile ? (
            <div className="model-content">
              {filteredIdentityStatements && filteredIdentityStatements.length > 0 && (
                <div className="model-section">
                  <h3>Identity Statements</h3>
                  <div className="identity-statements">
                    {filteredIdentityStatements.map((stmt, i) => (
                      <div key={i} className="identity-statement">
                        <p className="statement-text">{stmt.statement}</p>
                        <div className="statement-meta">
                          <span className={`confidence-badge ${getConfidenceInfo(stmt.confidence).level}`}>
                            <span className="confidence-icon">{getConfidenceInfo(stmt.confidence).icon}</span>
                            {(stmt.confidence * 100).toFixed(0)}%
                          </span>
                          <span className="source-badge">{stmt.source}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {profile.values && profile.values.length > 0 && (
                <div className="model-section">
                  <h3>Core Values</h3>
                  <div className="values-list">
                    {profile.values.map((value, i) => (
                      <div key={i} className="value-item">{value}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <p>No self-model data yet</p>
            </div>
          )}
        </section>

        {/* Growth edges */}
        <section className="model-card growth-edges">
          <div className="card-header">
            <h2>Growth Edges</h2>
            <span className="edge-count">{growthEdges?.growth_edges?.length || 0}</span>
          </div>
          {filteredGrowthEdges && filteredGrowthEdges.length > 0 ? (
            <div className="edges-list">
              {filteredGrowthEdges.map((edge: GrowthEdge, i: number) => (
                <div key={edge.area || i} className="edge-item">
                  <div className="edge-header">
                    <span className="edge-status active" />
                    <span className="edge-title">{edge.area}</span>
                  </div>
                  <div className="edge-states">
                    <div className="state-row">
                      <span className="state-label">Current:</span>
                      <span className="state-text">{edge.current_state}</span>
                    </div>
                    <div className="state-row">
                      <span className="state-label">Desired:</span>
                      <span className="state-text desired">{edge.desired_state}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No growth edges defined</p>
            </div>
          )}
        </section>

        {/* Pending growth edges */}
        {pendingEdges?.pending_edges && pendingEdges.pending_edges.length > 0 && (
          <section className="model-card pending-edges">
            <div className="card-header">
              <h2>Proposed Growth Edges</h2>
              <span className="pending-count">{pendingEdges.pending_edges.length}</span>
            </div>
            <div className="pending-list">
              {pendingEdges.pending_edges.map((edge: PendingEdge) => (
                <div
                  key={edge.id}
                  className={`pending-item ${expandedEdge === edge.id ? 'expanded' : ''}`}
                  onClick={() => setExpandedEdge(expandedEdge === edge.id ? null : edge.id)}
                >
                  <div className="pending-header">
                    <span className={`impact-badge ${edge.impact_assessment}`}>{edge.impact_assessment}</span>
                    <span className="pending-title">{edge.area}</span>
                    <span className={`confidence-badge ${edge.confidence >= 0.8 ? 'high' : edge.confidence >= 0.6 ? 'medium' : 'low'}`}>
                      {(edge.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="pending-state">{edge.current_state}</div>
                  {expandedEdge === edge.id && (
                    <div className="pending-details">
                      <div className="pending-evidence">
                        <span className="evidence-label">Evidence:</span>
                        <span className="evidence-text">{edge.evidence}</span>
                      </div>
                      <div className="pending-actions">
                        <button
                          className="action-btn accept"
                          onClick={(e) => {
                            e.stopPropagation();
                            acceptMutation.mutate(edge.id);
                          }}
                          disabled={acceptMutation.isPending}
                        >
                          {acceptMutation.isPending ? 'Accepting...' : 'Accept'}
                        </button>
                        <button
                          className="action-btn reject"
                          onClick={(e) => {
                            e.stopPropagation();
                            rejectMutation.mutate(edge.id);
                          }}
                          disabled={rejectMutation.isPending}
                        >
                          {rejectMutation.isPending ? 'Rejecting...' : 'Reject'}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Open questions */}
        <section className="model-card open-questions">
          <div className="card-header">
            <h2>Open Questions</h2>
            <span className="question-count">{openQuestions?.questions?.length || 0}</span>
          </div>
          {filteredQuestions && filteredQuestions.length > 0 ? (
            <div className="questions-list">
              {filteredQuestions.map((question: string, i: number) => (
                <div key={i} className="question-item">
                  <div className="question-text">{question}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No open questions</p>
            </div>
          )}
        </section>

        {/* Opinions */}
        <section className="model-card opinions">
          <div className="card-header">
            <h2>Opinions</h2>
            <span className="opinion-count">{opinions?.opinions?.length || 0}</span>
          </div>
          {filteredOpinions && filteredOpinions.length > 0 ? (
            <div className="opinions-list">
              {filteredOpinions.map((opinion: Opinion, i: number) => (
                <div key={opinion.topic || i} className="opinion-item">
                  <div className="opinion-header">
                    <span className="opinion-topic">{opinion.topic}</span>
                    <span className={`confidence-badge ${getConfidenceInfo(opinion.confidence).level}`}>
                      <span className="confidence-icon">{getConfidenceInfo(opinion.confidence).icon}</span>
                      {(opinion.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="opinion-position">{opinion.position}</div>
                  {opinion.rationale && (
                    <div className="opinion-rationale">{opinion.rationale}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No opinions formed</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
