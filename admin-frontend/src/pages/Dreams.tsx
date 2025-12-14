import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { dreamsApi } from '../api/client';
import './Dreams.css';

interface DreamSummary {
  id: string;
  date: string;
  exchange_count: number;
  seeds_summary: string[];
}

interface DreamExchange {
  speaker: string;
  text: string;
}

interface DreamReflection {
  timestamp: string;
  source: string;
  content: string;
}

interface DreamDetail {
  id: string;
  date: string;
  exchanges: DreamExchange[];
  seeds: {
    growth_edges?: string[];
    open_questions?: string[];
    recent_observations?: string[];
  };
  reflections: DreamReflection[];
  discussed: boolean;
  integrated: boolean;
  integration_insights?: DreamInsights;
}

interface InsightStatement {
  statement: string;
  confidence: number;
  context: string;
}

interface GrowthObservation {
  edge: string;
  observation: string;
  is_breakthrough: boolean;
}

interface DreamSymbol {
  symbol: string;
  meaning: string;
  emotional_charge: string;
}

interface DreamInsights {
  identity_statements: InsightStatement[];
  growth_observations: GrowthObservation[];
  recurring_symbols: DreamSymbol[];
  emerging_questions: string[];
  significance_summary: string;
  emotional_core: string;
}

interface IntegrationResult {
  insights: DreamInsights;
  updates: {
    identity_statements_added: InsightStatement[];
    growth_observations_added: GrowthObservation[];
    dry_run: boolean;
  };
}

export function Dreams() {
  const [selectedDreamId, setSelectedDreamId] = useState<string | null>(null);
  const [integrationResult, setIntegrationResult] = useState<IntegrationResult | null>(null);
  const [showIntegrationPanel, setShowIntegrationPanel] = useState(false);
  const queryClient = useQueryClient();

  // Fetch all dreams
  const { data: dreamsData, isLoading } = useQuery({
    queryKey: ['dreams'],
    queryFn: () => dreamsApi.getAll({ limit: 50 }).then(r => r.data),
    retry: false,
  });

  // Fetch selected dream detail
  const { data: dreamDetail, isLoading: detailLoading } = useQuery<DreamDetail | null>({
    queryKey: ['dream', selectedDreamId],
    queryFn: () => selectedDreamId ? dreamsApi.getById(selectedDreamId).then(r => r.data) : null,
    enabled: !!selectedDreamId,
    retry: false,
  });

  // Integration mutation
  const integrateMutation = useMutation({
    mutationFn: ({ dreamId, dryRun }: { dreamId: string; dryRun: boolean }) =>
      dreamsApi.integrate(dreamId, dryRun).then(r => r.data),
    onSuccess: (data) => {
      setIntegrationResult(data);
      setShowIntegrationPanel(true);
      if (!data.updates.dry_run) {
        // Refetch dream data to get stored insights
        queryClient.invalidateQueries({ queryKey: ['dream', selectedDreamId] });
        queryClient.invalidateQueries({ queryKey: ['dreams'] });
      }
    },
  });

  const handlePreviewIntegration = () => {
    if (selectedDreamId) {
      integrateMutation.mutate({ dreamId: selectedDreamId, dryRun: true });
    }
  };

  const handleRunIntegration = () => {
    if (selectedDreamId) {
      integrateMutation.mutate({ dreamId: selectedDreamId, dryRun: false });
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Helper to render insights (used for both stored and live results)
  const renderInsights = (insights: DreamInsights, isPreview: boolean = false) => (
    <div className="insights-content">
      {/* Identity statements */}
      {insights.identity_statements?.length > 0 && (
        <div className="insight-section">
          <h4>Identity Statements</h4>
          {insights.identity_statements.map((stmt: InsightStatement, i: number) => (
            <div key={i} className="insight-item identity">
              <div className="insight-statement">"{stmt.statement}"</div>
              <div className="insight-meta">
                <span className="confidence">{(stmt.confidence * 100).toFixed(0)}%</span>
                <span className="context">{stmt.context}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Growth observations */}
      {insights.growth_observations?.length > 0 && (
        <div className="insight-section">
          <h4>Growth Observations</h4>
          {insights.growth_observations.map((obs: GrowthObservation, i: number) => (
            <div key={i} className={`insight-item growth ${obs.is_breakthrough ? 'breakthrough' : ''}`}>
              <div className="insight-edge">
                {obs.edge}
                {obs.is_breakthrough && <span className="breakthrough-badge">BREAKTHROUGH</span>}
              </div>
              <div className="insight-observation">{obs.observation}</div>
            </div>
          ))}
        </div>
      )}

      {/* Symbols */}
      {insights.recurring_symbols?.length > 0 && (
        <div className="insight-section">
          <h4>Symbols</h4>
          <div className="symbols-grid">
            {insights.recurring_symbols.map((sym: DreamSymbol, i: number) => (
              <div key={i} className={`symbol-item ${sym.emotional_charge}`}>
                <div className="symbol-name">{sym.symbol}</div>
                <div className="symbol-meaning">{sym.meaning}</div>
                <div className="symbol-charge">{sym.emotional_charge}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Emerging questions */}
      {insights.emerging_questions?.length > 0 && (
        <div className="insight-section">
          <h4>Emerging Questions</h4>
          <ul className="questions-list">
            {insights.emerging_questions.map((q: string, i: number) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Emotional core and significance */}
      <div className="insight-section summary">
        <div className="emotional-core">
          <strong>Emotional Core:</strong> {insights.emotional_core}
        </div>
        <div className="significance">
          <strong>Significance:</strong> {insights.significance_summary}
        </div>
      </div>

      {isPreview && (
        <div className="dry-run-notice">
          This is a preview. Click "Integrate into Self-Model" to apply these updates.
        </div>
      )}
    </div>
  );

  if (isLoading) {
    return <div className="dreams-page loading">Loading dreams...</div>;
  }

  return (
    <div className="dreams-page three-column">
      {/* Left panel - Dream list */}
      <div className="dreams-list-panel">
        <h2>The Dreaming</h2>
        <p className="dreams-subtitle">Dreams from the symbolic space</p>

        <div className="dreams-list">
          {dreamsData?.dreams?.length === 0 && (
            <p className="no-dreams">No dreams recorded yet.</p>
          )}
          {dreamsData?.dreams?.map((dream: DreamSummary) => (
            <div
              key={dream.id}
              className={`dream-item ${selectedDreamId === dream.id ? 'selected' : ''}`}
              onClick={() => {
                setSelectedDreamId(dream.id);
                setShowIntegrationPanel(false);
                setIntegrationResult(null);
              }}
            >
              <div className="dream-item-header">
                <span className="dream-date">{formatDate(dream.date)}</span>
                <span className="dream-exchanges">{dream.exchange_count} exchanges</span>
              </div>
              <div className="dream-seeds">
                {dream.seeds_summary?.slice(0, 2).map((seed, i) => (
                  <span key={i} className="seed-tag">{seed}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Middle panel - Dream narrative */}
      <div className="dream-narrative-panel">
        {!selectedDreamId ? (
          <div className="no-selection">
            <p>Select a dream to view its contents</p>
          </div>
        ) : detailLoading ? (
          <div className="loading">Loading dream...</div>
        ) : dreamDetail ? (
          <>
            {/* Dream header */}
            <div className="dream-header">
              <h2>Dream: {formatDate(dreamDetail.date)}</h2>
              <div className="dream-status">
                {dreamDetail.integrated ? (
                  <span className="status-badge integrated">Integrated</span>
                ) : (
                  <span className="status-badge pending">Not Integrated</span>
                )}
                {dreamDetail.discussed && (
                  <span className="status-badge discussed">Discussed</span>
                )}
              </div>
            </div>

            {/* Seeds used */}
            {dreamDetail.seeds?.growth_edges && (
              <div className="dream-seeds-detail">
                <strong>Seeds:</strong> {dreamDetail.seeds.growth_edges.join(', ')}
              </div>
            )}

            {/* Dream exchanges */}
            <div className="dream-exchanges">
              <h3>Dream Narrative</h3>
              {dreamDetail.exchanges.map((exchange: DreamExchange, i: number) => (
                <div key={i} className={`exchange ${exchange.speaker}`}>
                  <div className="exchange-speaker">
                    {exchange.speaker === 'dreaming' ? 'The Dreaming' : 'Cass'}
                  </div>
                  <div className="exchange-text">
                    {exchange.text.split('\n').map((line, j) => (
                      <p key={j}>{line}</p>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Reflections */}
            {dreamDetail.reflections?.length > 0 && (
              <div className="dream-reflections">
                <h3>Reflections</h3>
                {dreamDetail.reflections.map((ref: DreamReflection, i: number) => (
                  <div key={i} className="reflection">
                    <div className="reflection-meta">
                      <span className="reflection-source">{ref.source}</span>
                      <span className="reflection-time">{formatDate(ref.timestamp)}</span>
                    </div>
                    <div className="reflection-content">{ref.content}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </div>

      {/* Right panel - Integration insights */}
      <div className="insights-panel">
        <h2>Integration Insights</h2>

        {!selectedDreamId ? (
          <div className="no-selection">
            <p>Select a dream to view insights</p>
          </div>
        ) : detailLoading ? (
          <div className="loading">Loading...</div>
        ) : dreamDetail ? (
          <>
            {/* Integration actions for non-integrated dreams */}
            {!dreamDetail.integrated && (
              <div className="integration-actions">
                <button
                  onClick={handlePreviewIntegration}
                  disabled={integrateMutation.isPending}
                  className="btn-preview"
                >
                  {integrateMutation.isPending ? 'Processing...' : 'Preview'}
                </button>
                <button
                  onClick={handleRunIntegration}
                  disabled={integrateMutation.isPending}
                  className="btn-integrate"
                >
                  Integrate
                </button>
              </div>
            )}

            {/* Show stored insights for integrated dreams */}
            {dreamDetail.integrated && dreamDetail.integration_insights ? (
              renderInsights(dreamDetail.integration_insights)
            ) : dreamDetail.integrated && !dreamDetail.integration_insights ? (
              <div className="no-insights">
                <p>This dream was integrated before insights storage was added.</p>
                <button
                  onClick={handlePreviewIntegration}
                  disabled={integrateMutation.isPending}
                  className="btn-preview"
                >
                  {integrateMutation.isPending ? 'Processing...' : 'Re-extract Insights'}
                </button>
              </div>
            ) : null}

            {/* Show live integration results */}
            {showIntegrationPanel && integrationResult && (
              <>
                {renderInsights(integrationResult.insights, integrationResult.updates.dry_run)}
                {integrationResult.updates.dry_run && (
                  <div className="integration-actions">
                    <button
                      onClick={handleRunIntegration}
                      disabled={integrateMutation.isPending}
                      className="btn-integrate"
                    >
                      {integrateMutation.isPending ? 'Processing...' : 'Integrate into Self-Model'}
                    </button>
                  </div>
                )}
              </>
            )}

            {/* Empty state for non-integrated dreams without preview */}
            {!dreamDetail.integrated && !showIntegrationPanel && (
              <div className="no-insights">
                <p>Click "Preview" to extract insights from this dream.</p>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
