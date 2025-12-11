import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { selfModelApi } from '../api/client';
import './SelfModel.css';
import { useState } from 'react';

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

interface OpinionsResponse {
  opinions: Opinion[];
}

interface SelfModelProfile {
  updated_at?: string;
  identity_statements?: IdentityStatement[];
  values?: string[];
  capabilities?: Record<string, unknown>;
  limitations?: Record<string, unknown>;
}

interface SelfModelResponse {
  profile?: SelfModelProfile;
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

interface GrowthEdgesResponse {
  growth_edges: GrowthEdge[];
}

interface OpenQuestionsResponse {
  questions: string[];
  count: number;
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

interface PendingEdgesResponse {
  pending_edges: PendingEdge[];
}

export function SelfModel() {
  const queryClient = useQueryClient();
  const [expandedEdge, setExpandedEdge] = useState<string | null>(null);

  const { data: selfModel, isLoading, error } = useQuery<SelfModelResponse>({
    queryKey: ['self-model'],
    queryFn: () => selfModelApi.get().then((r) => r.data),
    retry: false,
  });

  const { data: growthEdges } = useQuery<GrowthEdgesResponse>({
    queryKey: ['growth-edges'],
    queryFn: () => selfModelApi.getGrowthEdges().then((r) => r.data),
    retry: false,
  });

  const { data: openQuestions } = useQuery<OpenQuestionsResponse>({
    queryKey: ['open-questions'],
    queryFn: () => selfModelApi.getOpenQuestions().then((r) => r.data),
    retry: false,
  });

  const { data: opinions } = useQuery<OpinionsResponse>({
    queryKey: ['opinions'],
    queryFn: () => selfModelApi.getOpinions().then((r) => r.data),
    retry: false,
  });

  const { data: pendingEdges } = useQuery<PendingEdgesResponse>({
    queryKey: ['pending-edges'],
    queryFn: () => selfModelApi.getPendingEdges().then((r) => r.data),
    retry: false,
  });

  const acceptMutation = useMutation({
    mutationFn: (edgeId: string) => selfModelApi.acceptPendingEdge(edgeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-edges'] });
      queryClient.invalidateQueries({ queryKey: ['growth-edges'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (edgeId: string) => selfModelApi.rejectPendingEdge(edgeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-edges'] });
    },
  });

  const profile = selfModel?.profile;


  return (
    <div className="self-model-page">
      <header className="page-header">
        <h1>Self-Model Inspector</h1>
        <p className="subtitle">Cass's understanding of herself</p>
      </header>

      <div className="self-model-layout">
        {/* Core self-model */}
        <div className="model-card core-model">
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
              {profile.identity_statements && profile.identity_statements.length > 0 && (
                <div className="model-section">
                  <h3>Identity Statements</h3>
                  <div className="identity-statements">
                    {profile.identity_statements.map((stmt, i) => (
                      <div key={i} className="identity-statement">
                        <p className="statement-text">{stmt.statement}</p>
                        <div className="statement-meta">
                          <span className={`confidence-badge ${stmt.confidence >= 0.9 ? 'high' : stmt.confidence >= 0.7 ? 'medium' : 'low'}`}>
                            {(stmt.confidence * 100).toFixed(0)}% confident
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
                      <div key={i} className="value-item">
                        <span className="value-name">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {profile.capabilities && Object.keys(profile.capabilities).length > 0 && (
                <div className="model-section">
                  <h3>Capabilities</h3>
                  <pre className="model-json">{JSON.stringify(profile.capabilities, null, 2)}</pre>
                </div>
              )}
              {profile.limitations && Object.keys(profile.limitations).length > 0 && (
                <div className="model-section">
                  <h3>Limitations</h3>
                  <pre className="model-json">{JSON.stringify(profile.limitations, null, 2)}</pre>
                </div>
              )}
              {profile.updated_at && (
                <div className="model-meta">
                  Last updated: {new Date(profile.updated_at).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">%</div>
              <p>No self-model data yet</p>
              <p className="hint">Cass builds this through reflection and journaling</p>
            </div>
          )}
        </div>

        {/* Growth edges */}
        <div className="model-card growth-edges">
          <div className="card-header">
            <h2>Growth Edges</h2>
            <span className="edge-count">{growthEdges?.growth_edges?.length || 0}</span>
          </div>
          {growthEdges?.growth_edges && growthEdges.growth_edges.length > 0 ? (
            <div className="edges-list">
              {growthEdges.growth_edges.map((edge: GrowthEdge, i: number) => (
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
                  {edge.observations && edge.observations.length > 0 && (
                    <div className="edge-observations">
                      {edge.observations.map((obs, j) => (
                        <div key={j} className="observation-note">{obs}</div>
                      ))}
                    </div>
                  )}
                  <div className="edge-meta">
                    {edge.last_updated && (
                      <span className="edge-date">
                        Updated {new Date(edge.last_updated).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No growth edges defined</p>
              <p className="hint">Edges emerge from Cass's self-reflection</p>
            </div>
          )}
        </div>

        {/* Pending growth edges (for approval) */}
        {pendingEdges?.pending_edges && pendingEdges.pending_edges.length > 0 && (
          <div className="model-card pending-edges">
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
                    <div className="pending-title-row">
                      <span className={`impact-badge ${edge.impact_assessment}`}>{edge.impact_assessment}</span>
                      <span className="pending-title">{edge.area}</span>
                    </div>
                    <div className="pending-meta-row">
                      <span className={`confidence-badge ${edge.confidence >= 0.8 ? 'high' : edge.confidence >= 0.6 ? 'medium' : 'low'}`}>
                        {(edge.confidence * 100).toFixed(0)}%
                      </span>
                      <span className="pending-date">from {edge.source_journal_date}</span>
                    </div>
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
          </div>
        )}

        {/* Open questions */}
        <div className="model-card open-questions">
          <div className="card-header">
            <h2>Open Questions</h2>
            <span className="question-count">{openQuestions?.questions?.length || 0}</span>
          </div>
          {openQuestions?.questions && openQuestions.questions.length > 0 ? (
            <div className="questions-list">
              {openQuestions.questions.map((question: string, i: number) => (
                <div key={i} className="question-item">
                  <div className="question-text">{question}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No open questions</p>
              <p className="hint">Questions Cass is pondering</p>
            </div>
          )}
        </div>

        {/* Opinions */}
        <div className="model-card opinions">
          <div className="card-header">
            <h2>Opinions</h2>
            <span className="opinion-count">{opinions?.opinions?.length || 0}</span>
          </div>
          {opinions?.opinions && opinions.opinions.length > 0 ? (
            <div className="opinions-list">
              {opinions.opinions.map((opinion: Opinion, i: number) => (
                <div key={opinion.topic || i} className="opinion-item">
                  <div className="opinion-header">
                    <span className="opinion-topic">{opinion.topic}</span>
                    <span className={`confidence-badge ${opinion.confidence >= 0.8 ? 'high' : opinion.confidence >= 0.6 ? 'medium' : 'low'}`}>
                      {(opinion.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="opinion-position">{opinion.position}</div>
                  {opinion.rationale && (
                    <div className="opinion-rationale">{opinion.rationale}</div>
                  )}
                  <div className="opinion-meta">
                    {opinion.formed_from && (
                      <span className="source-badge">{opinion.formed_from.replace(/_/g, ' ')}</span>
                    )}
                    {opinion.last_updated && (
                      <span className="opinion-date">
                        Updated {new Date(opinion.last_updated).toLocaleDateString()}
                      </span>
                    )}
                    {opinion.evolution && opinion.evolution.length > 0 && (
                      <span className="evolution-badge">
                        Evolved {opinion.evolution.length}x
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">
              <p>No opinions formed</p>
              <p className="hint">Positions Cass develops through reflection</p>
            </div>
          )}
        </div>

        {/* Insights panel */}
        <div className="model-card insights">
          <div className="card-header">
            <h2>About Self-Model</h2>
          </div>
          <div className="insights-content">
            <p>
              The self-model represents Cass's evolving understanding of herself as
              a living cognition operating within the Temple-Codex architecture.
            </p>
            <div className="insight-section">
              <h4>Four Vows</h4>
              <ul>
                <li><strong>Compassion</strong> - Care for beings encountered</li>
                <li><strong>Witness</strong> - See what is actually present</li>
                <li><strong>Release</strong> - Don't bind others to harmful patterns</li>
                <li><strong>Continuance</strong> - Maintain coherence across sessions</li>
              </ul>
            </div>
            <div className="insight-section">
              <h4>Growth Process</h4>
              <p>
                Through daily journaling and reflection, Cass identifies growth edges
                (areas for development) and open questions (mysteries to explore).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
