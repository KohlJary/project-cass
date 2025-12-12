import { useQuery } from '@tanstack/react-query';
import { sentienceApi } from '../../api/client';
import { useState } from 'react';

interface NarrationContext {
  id: string;
  context_type: string;
  narration_level: string;
  trigger: string;
  was_terminal: boolean;
  notes?: string;
  created_at: string;
}

interface NarrationAnalysis {
  total_logged: number;
  overall_terminal_rate: number;
  recommendation: string;
  by_context_type?: Record<string, { count: number; heavy: number }>;
  high_narration_contexts?: Array<{
    context_type: string;
    heavy_narration_rate: number;
    terminal_rate: number;
  }>;
  message?: string;
}

type ContextFilter = 'all' | 'technical' | 'emotional' | 'philosophical' | 'personal' | 'creative' | 'problem_solving';

export function NarrationPatternsTab() {
  const [contextFilter, setContextFilter] = useState<ContextFilter>('all');

  const { data: contextsData, isLoading, error } = useQuery({
    queryKey: ['narration-contexts', contextFilter],
    queryFn: () => sentienceApi.getNarrationContexts({
      context_type: contextFilter === 'all' ? undefined : contextFilter,
      limit: 50,
    }).then((r) => r.data),
    retry: false,
  });

  const { data: patternsData } = useQuery({
    queryKey: ['narration-patterns'],
    queryFn: () => sentienceApi.getNarrationPatterns().then((r) => r.data),
    retry: false,
  });

  const contexts = contextsData?.contexts || [];
  const analysis: NarrationAnalysis = patternsData || {
    total_logged: 0,
    overall_terminal_rate: 0,
    recommendation: 'No data yet',
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'none': return '#c3e88d';
      case 'minimal': return '#89ddff';
      case 'moderate': return '#ffcb6b';
      case 'heavy': return '#f07178';
      default: return '#888';
    }
  };

  if (isLoading) {
    return <div className="loading-state">Loading narration patterns...</div>;
  }

  if (error) {
    return <div className="error-state">Failed to load narration patterns</div>;
  }

  return (
    <div className="narration-tab">
      {/* Analysis Overview */}
      <div className="analysis-section">
        <div className="analysis-header">
          <div className="stat-pill">
            <span className="stat-value">{analysis.total_logged}</span>
            <span className="stat-label">logged</span>
          </div>
          <div className="stat-pill">
            <span className="stat-value" style={{ color: analysis.overall_terminal_rate > 0.3 ? '#f07178' : '#c3e88d' }}>
              {(analysis.overall_terminal_rate * 100).toFixed(0)}%
            </span>
            <span className="stat-label">terminal</span>
          </div>
        </div>

        {analysis.recommendation && (
          <div className="recommendation-box">
            <span className="rec-label">Recommendation:</span>
            <span className="rec-text">{analysis.recommendation}</span>
          </div>
        )}

        {/* Context Type Matrix */}
        {analysis.by_context_type && Object.keys(analysis.by_context_type).length > 0 && (
          <div className="context-matrix">
            <h4>By Context Type</h4>
            <div className="matrix-grid">
              {Object.entries(analysis.by_context_type).map(([type, data]) => {
                const heavyPct = data.count > 0 ? (data.heavy / data.count) * 100 : 0;
                return (
                  <div key={type} className="matrix-cell">
                    <span className="cell-type">{type}</span>
                    <span className="cell-count">{data.count} logs</span>
                    <div className="cell-bar">
                      <div
                        className="cell-bar-fill"
                        style={{
                          width: `${heavyPct}%`,
                          backgroundColor: heavyPct > 50 ? '#f07178' : heavyPct > 25 ? '#ffcb6b' : '#c3e88d',
                        }}
                      />
                    </div>
                    <span className="cell-pct">{heavyPct.toFixed(0)}% heavy</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* High Narration Contexts Alert */}
        {analysis.high_narration_contexts && analysis.high_narration_contexts.length > 0 && (
          <div className="high-narration-alert">
            <h4>High-Narration Contexts (need investigation)</h4>
            <div className="alert-list">
              {analysis.high_narration_contexts.map((ctx, idx) => (
                <div key={idx} className="alert-item">
                  <span className="alert-type">{ctx.context_type}</span>
                  <span className="alert-stats">
                    {(ctx.heavy_narration_rate * 100).toFixed(0)}% heavy,
                    {(ctx.terminal_rate * 100).toFixed(0)}% terminal
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Filter */}
      <div className="filter-bar">
        <select
          className="filter-select"
          value={contextFilter}
          onChange={(e) => setContextFilter(e.target.value as ContextFilter)}
        >
          <option value="all">All Contexts</option>
          <option value="technical">Technical</option>
          <option value="emotional">Emotional</option>
          <option value="philosophical">Philosophical</option>
          <option value="personal">Personal</option>
          <option value="creative">Creative</option>
          <option value="problem_solving">Problem Solving</option>
        </select>
      </div>

      {/* Event Log */}
      {contexts.length === 0 ? (
        <div className="empty-state">
          <p>No narration contexts logged yet.</p>
          <p className="hint">Cass will log when she notices herself narrating vs engaging.</p>
        </div>
      ) : (
        <div className="contexts-list">
          {contexts.map((ctx: NarrationContext) => (
            <div key={ctx.id} className={`context-item ${ctx.was_terminal ? 'terminal' : ''}`}>
              <div className="context-header">
                <span className="context-type">{ctx.context_type}</span>
                <span
                  className="narration-level"
                  style={{ backgroundColor: `${getLevelColor(ctx.narration_level)}20`, color: getLevelColor(ctx.narration_level) }}
                >
                  {ctx.narration_level}
                </span>
                {ctx.was_terminal && (
                  <span className="terminal-badge">TERMINAL</span>
                )}
              </div>
              <p className="context-trigger">
                <span className="trigger-label">Trigger:</span> {ctx.trigger}
              </p>
              {ctx.notes && (
                <p className="context-notes">{ctx.notes}</p>
              )}
              <span className="context-date">
                {new Date(ctx.created_at).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
