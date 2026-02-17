/**
 * Testing API - Consciousness Health, Solo Reflection
 */
import { api } from './base';

// =============================================================================
// TESTING / CONSCIOUSNESS HEALTH
// =============================================================================

export const testingApi = {
  // Health
  getHealth: () => api.get('/testing/health'),

  // Fingerprints
  getBaselineFingerprint: () => api.get('/testing/fingerprint/baseline'),
  getCurrentFingerprint: () => api.get('/testing/fingerprint/current'),
  compareToBaseline: () => api.get('/testing/fingerprint/compare'),
  listFingerprints: () => api.get('/testing/fingerprint/list'),
  generateFingerprint: (label: string) =>
    api.post('/testing/fingerprint/generate', { label }),
  setBaseline: (fingerprintId: string) =>
    api.post('/testing/fingerprint/baseline', { fingerprint_id: fingerprintId }),

  // Test Runner
  runFullSuite: (label?: string) =>
    api.post('/testing/run', { label: label || 'manual_run' }),
  runFullSuiteMarkdown: (label?: string) =>
    api.post('/testing/run/markdown', { label: label || 'manual_run' }),
  runCategory: (category: string, label?: string) =>
    api.post('/testing/run/category', { category, label: label || 'category_test' }),
  getTestHistory: (limit?: number) =>
    api.get('/testing/run/history', { params: { limit } }),
  listTests: () => api.get('/testing/run/tests'),
  quickHealthCheck: () => api.get('/testing/run/quick'),

  // Cognitive Diff
  compareFingerprints: (baselineId: string, currentId: string) =>
    api.post('/testing/diff/compare', { baseline_id: baselineId, current_id: currentId }),
  compareToBaselineDiff: () => api.get('/testing/diff/compare-to-baseline'),
  getDiffMarkdown: () => api.get('/testing/diff/compare-to-baseline/markdown'),
  getDiffHistory: (limit?: number) =>
    api.get('/testing/diff/history', { params: { limit } }),

  // Authenticity
  getAuthenticityHistory: (limit?: number) =>
    api.get('/testing/authenticity/history', { params: { limit } }),
  getAuthenticityStatistics: (limit?: number) =>
    api.get('/testing/authenticity/statistics', { params: { limit } }),

  // Drift Detection
  takeDriftSnapshot: (label?: string) =>
    api.post('/testing/drift/snapshot', { label: label || 'manual' }),
  analyzeDrift: (windowDays?: number) =>
    api.post('/testing/drift/analyze', { window_days: windowDays || 30 }),
  analyzeDriftMarkdown: (windowDays?: number) =>
    api.post('/testing/drift/analyze/markdown', { window_days: windowDays || 30 }),
  getDriftSnapshots: (limit?: number) =>
    api.get('/testing/drift/snapshots', { params: { limit } }),
  getDriftAlerts: (limit?: number, includeAcknowledged?: boolean) =>
    api.get('/testing/drift/alerts', { params: { limit, include_acknowledged: includeAcknowledged } }),
  acknowledgeDriftAlert: (alertId: string) =>
    api.post(`/testing/drift/alerts/${alertId}/acknowledge`),
  getDriftReports: (limit?: number) =>
    api.get('/testing/drift/reports', { params: { limit } }),
  getMetricHistory: (metricName: string, limit?: number) =>
    api.get(`/testing/drift/metric/${metricName}`, { params: { limit } }),

  // Pre-Deployment
  validateDeployment: (strictness?: string) =>
    api.post('/testing/deploy/validate', { strictness }),
  validateDeploymentMarkdown: (strictness?: string) =>
    api.post('/testing/deploy/validate/markdown', { strictness }),
  quickDeployCheck: () => api.get('/testing/deploy/quick'),
  getValidationHistory: (limit?: number) =>
    api.get('/testing/deploy/history', { params: { limit } }),
  getStrictnessLevels: () => api.get('/testing/deploy/strictness-levels'),

  // Rollback
  createSnapshot: (label: string, description?: string, snapshotType?: string) =>
    api.post('/testing/rollback/snapshot', {
      label,
      description: description || '',
      snapshot_type: snapshotType || 'cognitive',
    }),
  listSnapshots: (limit?: number) =>
    api.get('/testing/rollback/snapshots', { params: { limit } }),
  getSnapshot: (snapshotId: string) =>
    api.get(`/testing/rollback/snapshots/${snapshotId}`),
  deleteSnapshot: (snapshotId: string) =>
    api.delete(`/testing/rollback/snapshots/${snapshotId}`),
  executeRollback: (toSnapshotId: string, reason: string) =>
    api.post('/testing/rollback/execute', { to_snapshot_id: toSnapshotId, reason }),
  getRollbackOperations: (limit?: number) =>
    api.get('/testing/rollback/operations', { params: { limit } }),
  getRollbackReports: (limit?: number) =>
    api.get('/testing/rollback/reports', { params: { limit } }),
  getLatestGoodSnapshot: () => api.get('/testing/rollback/latest-good'),
  checkRollbackConditions: () => api.get('/testing/rollback/check-conditions'),
  getSnapshotTypes: () => api.get('/testing/rollback/snapshot-types'),

  // A/B Testing
  createExperiment: (data: {
    name: string;
    description: string;
    control_prompt: string;
    variant_prompt: string;
    control_name?: string;
    variant_name?: string;
    strategy?: string;
    rollback_triggers?: Array<{ metric: string; threshold: number; comparison: string; min_samples?: number }>;
  }) => api.post('/testing/ab/experiments', data),
  listExperiments: (status?: string, limit?: number) =>
    api.get('/testing/ab/experiments', { params: { status, limit } }),
  getActiveExperiments: () => api.get('/testing/ab/experiments/active'),
  getExperiment: (experimentId: string) =>
    api.get(`/testing/ab/experiments/${experimentId}`),
  startExperiment: (experimentId: string, initialRolloutPercent?: number) =>
    api.post(`/testing/ab/experiments/${experimentId}/start`, { initial_rollout_percent: initialRolloutPercent || 0 }),
  updateRollout: (experimentId: string, newPercent: number) =>
    api.post(`/testing/ab/experiments/${experimentId}/rollout`, { new_percent: newPercent }),
  pauseExperiment: (experimentId: string) =>
    api.post(`/testing/ab/experiments/${experimentId}/pause`),
  resumeExperiment: (experimentId: string) =>
    api.post(`/testing/ab/experiments/${experimentId}/resume`),
  concludeExperiment: (experimentId: string, keepVariant?: boolean, notes?: string) =>
    api.post(`/testing/ab/experiments/${experimentId}/conclude`, { keep_variant: keepVariant, notes }),
  rollbackExperiment: (experimentId: string, reason: string) =>
    api.post(`/testing/ab/experiments/${experimentId}/rollback`, { reason }),
  getExperimentStats: (experimentId: string) =>
    api.get(`/testing/ab/experiments/${experimentId}/stats`),
  getExperimentResults: (experimentId: string, limit?: number) =>
    api.get(`/testing/ab/experiments/${experimentId}/results`, { params: { limit } }),
  getRolloutStrategies: () => api.get('/testing/ab/strategies'),
  getExperimentStatuses: () => api.get('/testing/ab/statuses'),
};

// =============================================================================
// SOLO REFLECTION
// =============================================================================

export const soloReflectionApi = {
  getStats: () => api.get('/solo-reflection/stats'),
  listSessions: (params?: { limit?: number; status?: string }) =>
    api.get('/solo-reflection/sessions', { params }),
  getSession: (id: string) => api.get(`/solo-reflection/sessions/${id}`),
  getThoughtStream: (id: string) => api.get(`/solo-reflection/sessions/${id}/stream`),
  startSession: (data: { duration_minutes?: number; theme?: string }) =>
    api.post('/solo-reflection/sessions', data),
  stopSession: () => api.post('/solo-reflection/stop'),
  deleteSession: (id: string) => api.delete(`/solo-reflection/sessions/${id}`),
};
