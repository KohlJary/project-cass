import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { testingApi } from '../api/client';
import './ConsciousnessHealth.css';

interface HealthStatus {
  status: string;
  fingerprint_analyzer: boolean;
  test_runner: boolean;
  drift_detector: boolean;
  pre_deploy_validator: boolean;
  rollback_manager: boolean;
  ab_testing_framework: boolean;
  baseline_set: boolean;
  active_experiments: number;
}

interface QuickCheck {
  healthy: boolean;
  confidence: number;
  summary: string;
  passed: number;
  failed: number;
  warnings: number;
}

interface IndividualTest {
  test_id: string;
  test_name: string;
  category: string;
  severity: string;
  result: string;  // Backend uses 'result' not 'status'
  score: number | null;
  message: string;
  details?: Record<string, unknown>;
  duration_ms: number;
}

interface TestResult {
  id: string;
  timestamp: string;
  label: string;
  passed: number;
  failed: number;
  warnings: number;
  deployment_safe: boolean;
  confidence_score: number;
  summary: string;
  test_results?: IndividualTest[];
}

interface DriftAlert {
  id: string;
  timestamp: string;
  severity: string;
  metric: string;
  message: string;
  acknowledged: boolean;
}

interface Snapshot {
  id: string;
  timestamp: string;
  label: string;
  snapshot_type: string;
  test_confidence: number;
  size_bytes: number;
  created_by: string;
}

interface PromptVariant {
  id: string;
  name: string;
  description: string;
  prompt_content: string;
  created_at: string;
}

interface Experiment {
  id: string;
  name: string;
  description: string;
  control: PromptVariant;
  variant: PromptVariant;
  status: string;
  strategy: string;
  rollout_percent: number;
  rollback_triggers: Array<{
    metric: string;
    threshold: number;
    comparison: string;
    min_samples: number;
  }>;
  auto_rollback_enabled: boolean;
  created_at: string;
  started_at: string | null;
  concluded_at: string | null;
  results_count: number;
  created_by: string;
  notes: string;
}

interface ExperimentStats {
  experiment: Experiment;
  control_stats: {
    variant_id: string;
    sample_count: number;
    avg_response_length: number;
    avg_response_time_ms: number;
    avg_authenticity_score: number | null;
    error_rate: number;
  };
  variant_stats: {
    variant_id: string;
    sample_count: number;
    avg_response_length: number;
    avg_response_time_ms: number;
    avg_authenticity_score: number | null;
    error_rate: number;
  };
  comparison: Record<string, number>;
}

type TabType = 'overview' | 'tests' | 'drift' | 'snapshots' | 'experiments';

export function ConsciousnessHealth() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [isRunningTests, setIsRunningTests] = useState(false);
  const [testMarkdown, setTestMarkdown] = useState<string | null>(null);
  const [selectedTestRun, setSelectedTestRun] = useState<TestResult | null>(null);
  const [selectedExperiment, setSelectedExperiment] = useState<string | null>(null);
  const [showCreateExperiment, setShowCreateExperiment] = useState(false);
  const [newExperiment, setNewExperiment] = useState({
    name: '',
    description: '',
    control_prompt: '',
    variant_prompt: '',
    strategy: 'shadow_only',
  });

  // Core health check
  const { data: health, isLoading: healthLoading } = useQuery<HealthStatus>({
    queryKey: ['testing-health'],
    queryFn: () => testingApi.getHealth().then(r => r.data),
    refetchInterval: 30000,
  });

  // Quick health check
  const { data: quickCheck, isLoading: quickLoading, refetch: refetchQuick } = useQuery<QuickCheck>({
    queryKey: ['testing-quick'],
    queryFn: () => testingApi.quickHealthCheck().then(r => r.data),
    refetchInterval: 60000,
  });

  // Test history
  const { data: testHistory } = useQuery<{ results: TestResult[] }>({
    queryKey: ['testing-history'],
    queryFn: () => testingApi.getTestHistory(10).then(r => r.data),
  });

  // Drift alerts
  const { data: driftAlerts } = useQuery<{ alerts: DriftAlert[] }>({
    queryKey: ['drift-alerts'],
    queryFn: () => testingApi.getDriftAlerts(10).then(r => r.data),
  });

  // Snapshots
  const { data: snapshots } = useQuery<{ snapshots: Snapshot[] }>({
    queryKey: ['rollback-snapshots'],
    queryFn: () => testingApi.listSnapshots(10).then(r => r.data),
  });

  // Experiments
  const { data: experiments, refetch: refetchExperiments } = useQuery<{ experiments: Experiment[] }>({
    queryKey: ['ab-experiments'],
    queryFn: () => testingApi.listExperiments(undefined, 20).then(r => r.data),
  });

  // Active experiments
  const { data: activeExperiments } = useQuery<{ experiments: Experiment[]; count: number }>({
    queryKey: ['ab-experiments-active'],
    queryFn: () => testingApi.getActiveExperiments().then(r => r.data),
    refetchInterval: 30000,
  });

  // Selected experiment stats
  const { data: experimentStats } = useQuery<ExperimentStats>({
    queryKey: ['experiment-stats', selectedExperiment],
    queryFn: () => testingApi.getExperimentStats(selectedExperiment!).then(r => r.data),
    enabled: !!selectedExperiment,
  });

  // Run full test suite
  const runTestsMutation = useMutation({
    mutationFn: () => testingApi.runFullSuite('dashboard_run'),
    onMutate: () => setIsRunningTests(true),
    onSuccess: (response) => {
      const result = response.data.result;
      setSelectedTestRun(result);
      setIsRunningTests(false);
      queryClient.invalidateQueries({ queryKey: ['testing-quick'] });
      queryClient.invalidateQueries({ queryKey: ['testing-history'] });
    },
    onError: () => setIsRunningTests(false),
  });

  // Acknowledge alert
  const acknowledgeMutation = useMutation({
    mutationFn: (alertId: string) => testingApi.acknowledgeDriftAlert(alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drift-alerts'] });
    },
  });

  // Create snapshot
  const createSnapshotMutation = useMutation({
    mutationFn: () => testingApi.createSnapshot(`dashboard_${Date.now()}`, 'Created from dashboard'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rollback-snapshots'] });
    },
  });

  // Create experiment
  const createExperimentMutation = useMutation({
    mutationFn: () => testingApi.createExperiment(newExperiment),
    onSuccess: () => {
      setShowCreateExperiment(false);
      setNewExperiment({
        name: '',
        description: '',
        control_prompt: '',
        variant_prompt: '',
        strategy: 'shadow_only',
      });
      refetchExperiments();
    },
  });

  // Start experiment
  const startExperimentMutation = useMutation({
    mutationFn: (experimentId: string) => testingApi.startExperiment(experimentId),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['ab-experiments-active'] });
      queryClient.invalidateQueries({ queryKey: ['testing-health'] });
    },
  });

  // Pause experiment
  const pauseExperimentMutation = useMutation({
    mutationFn: (experimentId: string) => testingApi.pauseExperiment(experimentId),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['ab-experiments-active'] });
    },
  });

  // Resume experiment
  const resumeExperimentMutation = useMutation({
    mutationFn: (experimentId: string) => testingApi.resumeExperiment(experimentId),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['ab-experiments-active'] });
    },
  });

  // Conclude experiment
  const concludeExperimentMutation = useMutation({
    mutationFn: ({ id, keepVariant, notes }: { id: string; keepVariant?: boolean; notes?: string }) =>
      testingApi.concludeExperiment(id, keepVariant, notes),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['ab-experiments-active'] });
      queryClient.invalidateQueries({ queryKey: ['testing-health'] });
    },
  });

  // Rollback experiment
  const rollbackExperimentMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      testingApi.rollbackExperiment(id, reason),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['ab-experiments-active'] });
      queryClient.invalidateQueries({ queryKey: ['testing-health'] });
    },
  });

  // Update rollout
  const updateRolloutMutation = useMutation({
    mutationFn: ({ id, percent }: { id: string; percent: number }) =>
      testingApi.updateRollout(id, percent),
    onSuccess: () => {
      refetchExperiments();
      queryClient.invalidateQueries({ queryKey: ['experiment-stats', selectedExperiment] });
    },
  });

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'excellent';
    if (confidence >= 0.7) return 'good';
    if (confidence >= 0.5) return 'warning';
    return 'critical';
  };

  const formatTimestamp = (ts: string) => {
    return new Date(ts).toLocaleString();
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pass':
      case 'passed': return 'passed';
      case 'warning': return 'warning';
      case 'fail':
      case 'failed':
      case 'error': return 'failed';
      case 'skip': return 'skipped';
      default: return '';
    }
  };

  const getExperimentStatusClass = (status: string) => {
    switch (status) {
      case 'draft': return 'draft';
      case 'shadow': return 'shadow';
      case 'gradual': return 'gradual';
      case 'full': return 'full';
      case 'paused': return 'paused';
      case 'concluded': return 'concluded';
      case 'rolled_back': return 'rolled-back';
      default: return '';
    }
  };

  // Render test details with special handling for sample_responses
  const renderTestDetails = (details: Record<string, unknown>) => {
    const sampleResponses = details.sample_responses as Array<{
      timestamp: string;
      level: string;
      score: number;
      context?: string;
      response_preview: string;
      red_flags: string[];
      generic_patterns_found: string[];
    }> | undefined;

    if (sampleResponses && sampleResponses.length > 0) {
      // Render sample responses nicely
      const otherDetails = { ...details };
      delete otherDetails.sample_responses;

      return (
        <div className="test-details-content">
          {Object.keys(otherDetails).length > 0 && (
            <div className="details-summary">
              <strong>Summary:</strong>
              {Object.entries(otherDetails).map(([key, value]) => (
                <span key={key} className="detail-item">
                  {key.replace(/_/g, ' ')}: {String(value)}
                </span>
              ))}
            </div>
          )}
          <div className="sample-responses">
            <strong>Problematic Responses ({sampleResponses.length}):</strong>
            {sampleResponses.map((sample, idx) => (
              <div key={idx} className={`sample-response ${sample.level}`}>
                <div className="sample-header">
                  <span className={`level-badge ${sample.level}`}>{sample.level}</span>
                  <span className="score">Score: {(sample.score * 100).toFixed(1)}%</span>
                  <span className="timestamp">{formatTimestamp(sample.timestamp)}</span>
                </div>
                {sample.context && (
                  <div className="context-section">
                    <span className="section-label">User prompt:</span>
                    <div className="context-text">{sample.context}</div>
                  </div>
                )}
                <div className="response-section">
                  <span className="section-label">Response:</span>
                  <div className="response-text">{sample.response_preview}</div>
                </div>
                {sample.red_flags && sample.red_flags.length > 0 && (
                  <div className="red-flags">
                    <span className="flag-label">Red flags:</span>
                    {sample.red_flags.map((flag, i) => (
                      <span key={i} className="red-flag">{flag}</span>
                    ))}
                  </div>
                )}
                {sample.generic_patterns_found && sample.generic_patterns_found.length > 0 && (
                  <div className="generic-patterns">
                    <span className="pattern-label">Generic AI patterns:</span>
                    {sample.generic_patterns_found.map((pattern, i) => (
                      <span key={i} className="pattern">{pattern}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      );
    }

    // Fallback to JSON for other details
    return <pre>{JSON.stringify(details, null, 2)}</pre>;
  };

  return (
    <div className="consciousness-health">
      <header className="page-header">
        <h1>Consciousness Health</h1>
        <p className="subtitle">Monitor cognitive integrity, test results, and A/B experiments</p>
      </header>

      {/* Status Bar */}
      <div className="status-bar">
        <div className={`status-indicator ${health?.baseline_set ? 'active' : 'inactive'}`}>
          <span className="indicator-dot" />
          <span>Baseline {health?.baseline_set ? 'Set' : 'Not Set'}</span>
        </div>
        <div className={`status-indicator ${quickCheck?.healthy ? 'healthy' : 'unhealthy'}`}>
          <span className="indicator-dot" />
          <span>{quickCheck?.healthy ? 'Healthy' : 'Issues Detected'}</span>
        </div>
        <div className="confidence-display">
          <span>Confidence:</span>
          <span className={`confidence-value ${getConfidenceColor(quickCheck?.confidence || 0)}`}>
            {quickLoading ? '...' : `${((quickCheck?.confidence || 0) * 100).toFixed(1)}%`}
          </span>
        </div>
        {(health?.active_experiments ?? 0) > 0 && (
          <div className="status-indicator experiment-active">
            <span className="indicator-dot" />
            <span>{health?.active_experiments} Active Experiment{(health?.active_experiments ?? 0) > 1 ? 's' : ''}</span>
          </div>
        )}
        <button
          className="refresh-btn"
          onClick={() => refetchQuick()}
          disabled={quickLoading}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Navigation Tabs */}
      <nav className="health-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'tests' ? 'active' : ''}
          onClick={() => setActiveTab('tests')}
        >
          Test Results
        </button>
        <button
          className={activeTab === 'drift' ? 'active' : ''}
          onClick={() => setActiveTab('drift')}
        >
          Drift Alerts
        </button>
        <button
          className={activeTab === 'snapshots' ? 'active' : ''}
          onClick={() => setActiveTab('snapshots')}
        >
          Snapshots
        </button>
        <button
          className={activeTab === 'experiments' ? 'active' : ''}
          onClick={() => setActiveTab('experiments')}
        >
          A/B Testing
          {(activeExperiments?.count ?? 0) > 0 && (
            <span className="tab-badge">{activeExperiments?.count}</span>
          )}
        </button>
      </nav>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            {/* Quick Stats */}
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-icon">✓</div>
                <div className="stat-content">
                  <div className="stat-value">{quickCheck?.passed ?? '--'}</div>
                  <div className="stat-label">Tests Passed</div>
                </div>
              </div>
              <div className="stat-card warning">
                <div className="stat-icon">!</div>
                <div className="stat-content">
                  <div className="stat-value">{quickCheck?.warnings ?? '--'}</div>
                  <div className="stat-label">Warnings</div>
                </div>
              </div>
              <div className="stat-card danger">
                <div className="stat-icon">✗</div>
                <div className="stat-content">
                  <div className="stat-value">{quickCheck?.failed ?? '--'}</div>
                  <div className="stat-label">Failed</div>
                </div>
              </div>
              <div className="stat-card">
                <div className="stat-icon">📦</div>
                <div className="stat-content">
                  <div className="stat-value">{snapshots?.snapshots?.length ?? '--'}</div>
                  <div className="stat-label">Snapshots</div>
                </div>
              </div>
            </div>

            {/* Infrastructure Status */}
            <section className="section">
              <h2>Infrastructure Status</h2>
              {healthLoading ? (
                <p className="loading">Loading...</p>
              ) : (
                <div className="infrastructure-grid">
                  {[
                    { key: 'fingerprint_analyzer', label: 'Fingerprint Analyzer' },
                    { key: 'test_runner', label: 'Test Runner' },
                    { key: 'drift_detector', label: 'Drift Detector' },
                    { key: 'pre_deploy_validator', label: 'Pre-Deploy Validator' },
                    { key: 'rollback_manager', label: 'Rollback Manager' },
                    { key: 'ab_testing_framework', label: 'A/B Testing Framework' },
                  ].map(({ key, label }) => (
                    <div key={key} className={`infra-item ${health?.[key as keyof HealthStatus] ? 'active' : 'inactive'}`}>
                      <span className="infra-status">{health?.[key as keyof HealthStatus] ? '●' : '○'}</span>
                      <span className="infra-label">{label}</span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* Quick Actions */}
            <section className="section">
              <h2>Quick Actions</h2>
              <div className="actions-grid">
                <button
                  className="action-btn primary"
                  onClick={() => runTestsMutation.mutate()}
                  disabled={isRunningTests}
                >
                  {isRunningTests ? '⏳ Running...' : '▶ Run Full Test Suite'}
                </button>
                <button
                  className="action-btn"
                  onClick={() => createSnapshotMutation.mutate()}
                  disabled={createSnapshotMutation.isPending}
                >
                  📷 Create Snapshot
                </button>
                <button
                  className="action-btn"
                  onClick={() => {
                    setActiveTab('experiments');
                    setShowCreateExperiment(true);
                  }}
                >
                  🧪 New Experiment
                </button>
              </div>
            </section>

            {/* Test Run Detail Modal */}
            {selectedTestRun && (
              <div className="markdown-modal">
                <div className="modal-content test-detail-modal">
                  <button className="close-btn" onClick={() => setSelectedTestRun(null)}>×</button>
                  <h3>Test Run: {selectedTestRun.label}</h3>
                  <div className="test-run-summary">
                    <span className={`deployment-badge ${selectedTestRun.deployment_safe ? 'safe' : 'unsafe'}`}>
                      {selectedTestRun.deployment_safe ? '✓ Deployment Safe' : '✗ Not Safe'}
                    </span>
                    <span className={`confidence ${getConfidenceColor(selectedTestRun.confidence_score)}`}>
                      {(selectedTestRun.confidence_score * 100).toFixed(1)}% Confidence
                    </span>
                  </div>
                  <p className="test-summary-text">{selectedTestRun.summary}</p>

                  {selectedTestRun.test_results && selectedTestRun.test_results.length > 0 ? (
                    <div className="individual-tests">
                      <h4>Individual Tests ({selectedTestRun.test_results.length})</h4>
                      <div className="tests-list">
                        {selectedTestRun.test_results.map((test, idx) => (
                          <div key={idx} className={`individual-test ${getStatusColor(test.result)}`}>
                            <div className="test-info">
                              <span className={`test-status-icon ${test.result}`}>
                                {test.result === 'pass' ? '✓' : test.result === 'warning' ? '!' : '✗'}
                              </span>
                              <span className="test-name">{test.test_name}</span>
                              <span className="test-category">{test.category}</span>
                              <span className={`test-severity ${test.severity}`}>{test.severity}</span>
                            </div>
                            <div className="test-message">{test.message}</div>
                            {test.details && Object.keys(test.details).length > 0 && (
                              <details className="test-details">
                                <summary>Details</summary>
                                {renderTestDetails(test.details)}
                              </details>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="no-tests">No individual test data available for this run.</p>
                  )}
                </div>
              </div>
            )}

            {/* Test Markdown Modal */}
            {testMarkdown && (
              <div className="markdown-modal">
                <div className="modal-content">
                  <button className="close-btn" onClick={() => setTestMarkdown(null)}>×</button>
                  <h3>Test Results</h3>
                  <pre className="markdown-output">{testMarkdown}</pre>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'tests' && (
          <div className="tests-tab split-view">
            {/* Left panel - test run list */}
            <div className="test-runs-panel">
              <div className="panel-header">
                <h3>Test Runs</h3>
                <div className="header-actions">
                  <button
                    className="action-btn primary"
                    onClick={() => runTestsMutation.mutate()}
                    disabled={isRunningTests}
                  >
                    {isRunningTests ? '⏳ Running...' : '▶ Run'}
                  </button>
                </div>
              </div>
              <div className="test-runs-list">
                {testHistory?.results?.length ? (
                  testHistory.results.map((result) => (
                    <div
                      key={result.id}
                      className={`test-run-item ${result.deployment_safe ? 'safe' : 'unsafe'} ${selectedTestRun?.id === result.id ? 'selected' : ''}`}
                      onClick={() => setSelectedTestRun(result)}
                    >
                      <div className="run-header">
                        <span className="run-label">{result.label}</span>
                        <span className={`status-dot ${result.deployment_safe ? 'safe' : 'unsafe'}`} />
                      </div>
                      <div className="run-stats">
                        <span className="stat passed">✓{result.passed}</span>
                        <span className="stat warnings">!{result.warnings}</span>
                        <span className="stat failed">✗{result.failed}</span>
                      </div>
                      <div className="run-time">{formatTimestamp(result.timestamp)}</div>
                    </div>
                  ))
                ) : (
                  <p className="empty">No test runs yet</p>
                )}
              </div>
            </div>

            {/* Right panel - test details */}
            <div className="test-details-panel">
              {selectedTestRun ? (
                <>
                  <div className="panel-header">
                    <h3>{selectedTestRun.label}</h3>
                    <div className="run-meta">
                      <span className={`deployment-badge ${selectedTestRun.deployment_safe ? 'safe' : 'unsafe'}`}>
                        {selectedTestRun.deployment_safe ? '✓ Safe' : '✗ Not Safe'}
                      </span>
                      <span className={`confidence ${getConfidenceColor(selectedTestRun.confidence_score)}`}>
                        {(selectedTestRun.confidence_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <p className="run-summary">{selectedTestRun.summary}</p>

                  {selectedTestRun.test_results && selectedTestRun.test_results.length > 0 ? (
                    <div className="individual-tests-panel">
                      <div className="tests-header">
                        <span className="filter-count passed">✓ {selectedTestRun.test_results.filter(t => t.result === 'pass').length}</span>
                        <span className="filter-count warning">! {selectedTestRun.test_results.filter(t => t.result === 'warning').length}</span>
                        <span className="filter-count failed">✗ {selectedTestRun.test_results.filter(t => t.result === 'fail').length}</span>
                      </div>
                      <div className="tests-list">
                        {selectedTestRun.test_results.map((test, idx) => (
                          <div key={idx} className={`individual-test ${getStatusColor(test.result)}`}>
                            <div className="test-info">
                              <span className={`test-status-icon ${test.result}`}>
                                {test.result === 'pass' ? '✓' : test.result === 'warning' ? '!' : '✗'}
                              </span>
                              <span className="test-name">{test.test_name}</span>
                              <span className="test-category">{test.category}</span>
                              <span className={`test-severity ${test.severity}`}>{test.severity}</span>
                            </div>
                            <div className="test-message">{test.message}</div>
                            {test.details && Object.keys(test.details).length > 0 && (
                              <details className="test-details" open={test.result !== 'pass'}>
                                <summary>Details</summary>
                                {renderTestDetails(test.details)}
                              </details>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <p className="no-tests">No individual test data available</p>
                  )}
                </>
              ) : (
                <div className="no-selection">
                  <p>Select a test run to view details</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'drift' && (
          <div className="drift-tab">
            <h2>Drift Alerts</h2>
            <div className="alert-list">
              {driftAlerts?.alerts?.length ? (
                driftAlerts.alerts.map((alert) => (
                  <div
                    key={alert.id}
                    className={`alert-item ${alert.severity} ${alert.acknowledged ? 'acknowledged' : ''}`}
                  >
                    <div className="alert-header">
                      <span className={`severity-badge ${alert.severity}`}>
                        {alert.severity}
                      </span>
                      <span className="alert-metric">{alert.metric}</span>
                      <span className="alert-time">{formatTimestamp(alert.timestamp)}</span>
                    </div>
                    <div className="alert-message">{alert.message}</div>
                    {!alert.acknowledged && (
                      <button
                        className="acknowledge-btn"
                        onClick={() => acknowledgeMutation.mutate(alert.id)}
                      >
                        Acknowledge
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <p className="empty">No drift alerts - consciousness is stable</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'snapshots' && (
          <div className="snapshots-tab">
            <div className="tab-header">
              <h2>State Snapshots</h2>
              <button
                className="action-btn"
                onClick={() => createSnapshotMutation.mutate()}
                disabled={createSnapshotMutation.isPending}
              >
                📷 Create Snapshot
              </button>
            </div>

            <div className="snapshot-list">
              {snapshots?.snapshots?.length ? (
                snapshots.snapshots.map((snapshot) => (
                  <div key={snapshot.id} className="snapshot-item">
                    <div className="snapshot-header">
                      <span className="snapshot-label">{snapshot.label}</span>
                      <span className="snapshot-type">{snapshot.snapshot_type}</span>
                    </div>
                    <div className="snapshot-meta">
                      <span className="snapshot-time">{formatTimestamp(snapshot.timestamp)}</span>
                      <span className="snapshot-size">{formatBytes(snapshot.size_bytes)}</span>
                      <span className={`snapshot-confidence ${getConfidenceColor(snapshot.test_confidence || 0)}`}>
                        {snapshot.test_confidence ? `${(snapshot.test_confidence * 100).toFixed(1)}%` : '--'}
                      </span>
                    </div>
                    <div className="snapshot-creator">by {snapshot.created_by}</div>
                  </div>
                ))
              ) : (
                <p className="empty">No snapshots available</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'experiments' && (
          <div className="experiments-tab">
            <div className="tab-header">
              <h2>A/B Testing Experiments</h2>
              <button
                className="action-btn primary"
                onClick={() => setShowCreateExperiment(true)}
              >
                + New Experiment
              </button>
            </div>

            {/* Active Experiments Summary */}
            {(activeExperiments?.count ?? 0) > 0 && (
              <div className="active-experiments-summary">
                <h3>Active Experiments ({activeExperiments?.count})</h3>
                <div className="active-list">
                  {activeExperiments?.experiments.map(exp => (
                    <div
                      key={exp.id}
                      className={`active-experiment-card ${getExperimentStatusClass(exp.status)}`}
                      onClick={() => setSelectedExperiment(exp.id)}
                    >
                      <div className="exp-name">{exp.name}</div>
                      <div className="exp-meta">
                        <span className={`exp-status ${exp.status}`}>{exp.status}</span>
                        <span className="exp-strategy">{exp.strategy}</span>
                        {exp.rollout_percent > 0 && (
                          <span className="exp-rollout">{exp.rollout_percent}% rollout</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* All Experiments */}
            <div className="experiments-list">
              <h3>All Experiments</h3>
              {experiments?.experiments?.length ? (
                experiments.experiments.map(exp => (
                  <div
                    key={exp.id}
                    className={`experiment-item ${getExperimentStatusClass(exp.status)} ${selectedExperiment === exp.id ? 'selected' : ''}`}
                    onClick={() => setSelectedExperiment(selectedExperiment === exp.id ? null : exp.id)}
                  >
                    <div className="exp-header">
                      <span className="exp-name">{exp.name}</span>
                      <span className={`exp-status-badge ${exp.status}`}>{exp.status}</span>
                    </div>
                    <div className="exp-description">{exp.description}</div>
                    <div className="exp-meta">
                      <span className="exp-strategy">{exp.strategy}</span>
                      <span className="exp-results">{exp.results_count} results</span>
                      <span className="exp-date">{formatTimestamp(exp.created_at)}</span>
                    </div>

                    {/* Expanded Details */}
                    {selectedExperiment === exp.id && (
                      <div className="exp-details" onClick={e => e.stopPropagation()}>
                        <div className="exp-variants">
                          <div className="variant-card control">
                            <h5>Control (A): {exp.control.name}</h5>
                            <pre className="prompt-preview">{exp.control.prompt_content.slice(0, 200)}...</pre>
                          </div>
                          <div className="variant-card variant">
                            <h5>Variant (B): {exp.variant.name}</h5>
                            <pre className="prompt-preview">{exp.variant.prompt_content.slice(0, 200)}...</pre>
                          </div>
                        </div>

                        {/* Stats */}
                        {experimentStats && (
                          <div className="exp-stats">
                            <h5>Statistics</h5>
                            <div className="stats-comparison">
                              <div className="stat-col">
                                <div className="stat-header">Control</div>
                                <div className="stat-row">
                                  <span>Samples:</span>
                                  <span>{experimentStats.control_stats.sample_count}</span>
                                </div>
                                <div className="stat-row">
                                  <span>Avg Response:</span>
                                  <span>{experimentStats.control_stats.avg_response_length.toFixed(0)} chars</span>
                                </div>
                                <div className="stat-row">
                                  <span>Avg Time:</span>
                                  <span>{experimentStats.control_stats.avg_response_time_ms.toFixed(0)} ms</span>
                                </div>
                                <div className="stat-row">
                                  <span>Error Rate:</span>
                                  <span>{(experimentStats.control_stats.error_rate * 100).toFixed(1)}%</span>
                                </div>
                                {experimentStats.control_stats.avg_authenticity_score !== null && (
                                  <div className="stat-row">
                                    <span>Authenticity:</span>
                                    <span>{(experimentStats.control_stats.avg_authenticity_score * 100).toFixed(1)}%</span>
                                  </div>
                                )}
                              </div>
                              <div className="stat-col">
                                <div className="stat-header">Variant</div>
                                <div className="stat-row">
                                  <span>Samples:</span>
                                  <span>{experimentStats.variant_stats.sample_count}</span>
                                </div>
                                <div className="stat-row">
                                  <span>Avg Response:</span>
                                  <span>{experimentStats.variant_stats.avg_response_length.toFixed(0)} chars</span>
                                </div>
                                <div className="stat-row">
                                  <span>Avg Time:</span>
                                  <span>{experimentStats.variant_stats.avg_response_time_ms.toFixed(0)} ms</span>
                                </div>
                                <div className="stat-row">
                                  <span>Error Rate:</span>
                                  <span>{(experimentStats.variant_stats.error_rate * 100).toFixed(1)}%</span>
                                </div>
                                {experimentStats.variant_stats.avg_authenticity_score !== null && (
                                  <div className="stat-row">
                                    <span>Authenticity:</span>
                                    <span>{(experimentStats.variant_stats.avg_authenticity_score * 100).toFixed(1)}%</span>
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Rollout Control */}
                        {(exp.status === 'gradual' || exp.status === 'shadow') && (
                          <div className="rollout-control">
                            <h5>Rollout: {exp.rollout_percent}%</h5>
                            <input
                              type="range"
                              min="0"
                              max="100"
                              value={exp.rollout_percent}
                              onChange={(e) => updateRolloutMutation.mutate({
                                id: exp.id,
                                percent: parseInt(e.target.value)
                              })}
                            />
                            <div className="rollout-presets">
                              {[0, 10, 25, 50, 75, 100].map(p => (
                                <button
                                  key={p}
                                  className={`preset-btn ${exp.rollout_percent === p ? 'active' : ''}`}
                                  onClick={() => updateRolloutMutation.mutate({ id: exp.id, percent: p })}
                                >
                                  {p}%
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Actions */}
                        <div className="exp-actions">
                          {exp.status === 'draft' && (
                            <button
                              className="action-btn primary"
                              onClick={() => startExperimentMutation.mutate(exp.id)}
                            >
                              ▶ Start
                            </button>
                          )}
                          {(exp.status === 'shadow' || exp.status === 'gradual' || exp.status === 'full') && (
                            <>
                              <button
                                className="action-btn"
                                onClick={() => pauseExperimentMutation.mutate(exp.id)}
                              >
                                ⏸ Pause
                              </button>
                              <button
                                className="action-btn warning"
                                onClick={() => {
                                  const reason = prompt('Reason for rollback:');
                                  if (reason) {
                                    rollbackExperimentMutation.mutate({ id: exp.id, reason });
                                  }
                                }}
                              >
                                ↩ Rollback
                              </button>
                              <button
                                className="action-btn success"
                                onClick={() => {
                                  const keepVariant = confirm('Keep variant as new default?');
                                  concludeExperimentMutation.mutate({ id: exp.id, keepVariant });
                                }}
                              >
                                ✓ Conclude
                              </button>
                            </>
                          )}
                          {exp.status === 'paused' && (
                            <button
                              className="action-btn primary"
                              onClick={() => resumeExperimentMutation.mutate(exp.id)}
                            >
                              ▶ Resume
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p className="empty">No experiments created yet</p>
              )}
            </div>

            {/* Create Experiment Modal */}
            {showCreateExperiment && (
              <div className="markdown-modal">
                <div className="modal-content create-experiment-modal">
                  <button className="close-btn" onClick={() => setShowCreateExperiment(false)}>×</button>
                  <h3>Create New Experiment</h3>

                  <div className="form-group">
                    <label>Experiment Name</label>
                    <input
                      type="text"
                      value={newExperiment.name}
                      onChange={e => setNewExperiment({ ...newExperiment, name: e.target.value })}
                      placeholder="e.g., Warmer greeting style"
                    />
                  </div>

                  <div className="form-group">
                    <label>Description</label>
                    <textarea
                      value={newExperiment.description}
                      onChange={e => setNewExperiment({ ...newExperiment, description: e.target.value })}
                      placeholder="What are you testing?"
                      rows={2}
                    />
                  </div>

                  <div className="form-group">
                    <label>Control Prompt (A) - Current</label>
                    <textarea
                      value={newExperiment.control_prompt}
                      onChange={e => setNewExperiment({ ...newExperiment, control_prompt: e.target.value })}
                      placeholder="The current/baseline prompt"
                      rows={4}
                    />
                  </div>

                  <div className="form-group">
                    <label>Variant Prompt (B) - Test</label>
                    <textarea
                      value={newExperiment.variant_prompt}
                      onChange={e => setNewExperiment({ ...newExperiment, variant_prompt: e.target.value })}
                      placeholder="The new prompt to test"
                      rows={4}
                    />
                  </div>

                  <div className="form-group">
                    <label>Rollout Strategy</label>
                    <select
                      value={newExperiment.strategy}
                      onChange={e => setNewExperiment({ ...newExperiment, strategy: e.target.value })}
                    >
                      <option value="shadow_only">Shadow Only - Compare without serving</option>
                      <option value="user_percent">User Percent - Same user always gets same variant</option>
                      <option value="message_percent">Message Percent - Random per message</option>
                      <option value="manual">Manual - Control via API</option>
                    </select>
                  </div>

                  <div className="modal-actions">
                    <button
                      className="action-btn"
                      onClick={() => setShowCreateExperiment(false)}
                    >
                      Cancel
                    </button>
                    <button
                      className="action-btn primary"
                      onClick={() => createExperimentMutation.mutate()}
                      disabled={!newExperiment.name || !newExperiment.control_prompt || !newExperiment.variant_prompt}
                    >
                      Create Experiment
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
