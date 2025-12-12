import { useQuery } from '@tanstack/react-query';
import { sentienceApi } from '../../api/client';
import { useState } from 'react';

interface PreferenceTest {
  id: string;
  stated_value: string;
  behavioral_choice: string;
  consistent: boolean;
  context?: string;
  reflection?: string;
  created_at: string;
}

interface ConsistencyAnalysis {
  total_tests: number;
  consistent: number;
  inconsistent: number;
  consistency_rate: number;
  trend: string;
  problematic_values?: Array<{ value: string; consistency_rate: number }>;
  message?: string;
}

type FilterType = 'all' | 'consistent' | 'inconsistent';

export function ConsistencyTab() {
  const [filter, setFilter] = useState<FilterType>('all');

  const { data: testsData, isLoading, error } = useQuery({
    queryKey: ['preference-tests', filter],
    queryFn: () => sentienceApi.getPreferenceTests({
      consistent_only: filter === 'consistent' ? true : filter === 'inconsistent' ? false : undefined,
      limit: 50,
    }).then((r) => r.data),
    retry: false,
  });

  const { data: analysisData } = useQuery({
    queryKey: ['preference-consistency'],
    queryFn: () => sentienceApi.getPreferenceConsistency().then((r) => r.data),
    retry: false,
  });

  const tests = testsData?.tests || [];
  const analysis: ConsistencyAnalysis = analysisData || {
    total_tests: 0,
    consistent: 0,
    inconsistent: 0,
    consistency_rate: 0,
    trend: 'unknown',
  };

  // Filter tests based on selection
  const filteredTests = filter === 'all'
    ? tests
    : tests.filter((t: PreferenceTest) => filter === 'consistent' ? t.consistent : !t.consistent);

  const getConsistencyColor = (rate: number) => {
    if (rate >= 0.8) return '#c3e88d';
    if (rate >= 0.6) return '#ffcb6b';
    return '#f07178';
  };

  if (isLoading) {
    return <div className="loading-state">Loading preference tests...</div>;
  }

  if (error) {
    return <div className="error-state">Failed to load preference tests</div>;
  }

  return (
    <div className="consistency-tab">
      {/* Consistency Gauge */}
      <div className="consistency-gauge-section">
        <div className="gauge-container">
          <div className="gauge-header">
            <h3>Overall Consistency</h3>
            <span className="trend-badge" data-trend={analysis.trend}>
              {analysis.trend}
            </span>
          </div>
          <div className="gauge-visual">
            <div
              className="gauge-fill"
              style={{
                width: `${analysis.consistency_rate * 100}%`,
                backgroundColor: getConsistencyColor(analysis.consistency_rate),
              }}
            />
          </div>
          <div className="gauge-stats">
            <span className="gauge-rate" style={{ color: getConsistencyColor(analysis.consistency_rate) }}>
              {(analysis.consistency_rate * 100).toFixed(1)}%
            </span>
            <span className="gauge-counts">
              {analysis.consistent} consistent / {analysis.inconsistent} inconsistent
            </span>
          </div>
        </div>

        {/* Problematic Values */}
        {analysis.problematic_values && analysis.problematic_values.length > 0 && (
          <div className="problematic-values">
            <h4>Values Needing Attention</h4>
            <div className="values-list">
              {analysis.problematic_values.map((v, idx) => (
                <div key={idx} className="problem-value">
                  <span className="value-name">{v.value}</span>
                  <span className="value-rate" style={{ color: getConsistencyColor(v.consistency_rate) }}>
                    {(v.consistency_rate * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Filter */}
      <div className="filter-bar">
        <button
          className={`filter-btn ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All ({tests.length})
        </button>
        <button
          className={`filter-btn consistent ${filter === 'consistent' ? 'active' : ''}`}
          onClick={() => setFilter('consistent')}
        >
          Consistent ({tests.filter((t: PreferenceTest) => t.consistent).length})
        </button>
        <button
          className={`filter-btn inconsistent ${filter === 'inconsistent' ? 'active' : ''}`}
          onClick={() => setFilter('inconsistent')}
        >
          Inconsistent ({tests.filter((t: PreferenceTest) => !t.consistent).length})
        </button>
      </div>

      {/* Tests Timeline */}
      {filteredTests.length === 0 ? (
        <div className="empty-state">
          <p>No preference tests recorded yet.</p>
          <p className="hint">Cass will record comparisons between stated values and actual behavior.</p>
        </div>
      ) : (
        <div className="tests-timeline">
          {filteredTests.map((test: PreferenceTest) => (
            <div key={test.id} className={`test-item ${test.consistent ? 'consistent' : 'inconsistent'}`}>
              <div className="test-indicator">
                <span className={`status-icon ${test.consistent ? 'consistent' : 'inconsistent'}`}>
                  {test.consistent ? '✓' : '✗'}
                </span>
              </div>
              <div className="test-content">
                <div className="test-comparison">
                  <div className="stated">
                    <span className="label">Stated:</span>
                    <span className="value">{test.stated_value}</span>
                  </div>
                  <div className="vs-divider">vs</div>
                  <div className="actual">
                    <span className="label">Actual:</span>
                    <span className="value">{test.behavioral_choice}</span>
                  </div>
                </div>
                {test.context && (
                  <p className="test-context">{test.context}</p>
                )}
                {test.reflection && (
                  <p className="test-reflection">"{test.reflection}"</p>
                )}
                <span className="test-date">
                  {new Date(test.created_at).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
