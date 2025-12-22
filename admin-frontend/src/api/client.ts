import axios from 'axios';

// In dev, use localhost. In production (same origin), use relative URLs.
const getApiBase = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (window.location.hostname === 'localhost') return 'http://localhost:8000';
  // Production: same origin, use relative URLs
  return '';
};
const API_BASE = getApiBase();

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Daemon ID storage key (shared with DaemonContext)
const DAEMON_KEY = 'cass_admin_daemon';

// Add request interceptor to inject daemon_id into all requests
api.interceptors.request.use((config) => {
  const daemonId = localStorage.getItem(DAEMON_KEY);
  if (daemonId) {
    // Add daemon_id as query parameter
    config.params = {
      ...config.params,
      daemon_id: daemonId,
    };
  }
  return config;
});

// Daemon endpoints
export const daemonsApi = {
  getAll: () => api.get('/admin/daemons'),
  getById: (id: string) => api.get(`/admin/daemons/${id}`),
  deleteDaemon: (id: string) => api.delete(`/admin/daemons/${id}`),

  // Daemon export/import endpoints
  listSeedExports: () => api.get('/admin/daemons/exports/seeds'),
  exportDaemon: (daemonId: string) =>
    api.post(`/admin/daemons/${daemonId}/export`, {}, { responseType: 'blob' }),
  importDaemon: (file: File, daemonName?: string, skipEmbeddings?: boolean, mergeExisting?: boolean) => {
    const formData = new FormData();
    formData.append('file', file);
    if (daemonName) formData.append('daemon_name', daemonName);
    if (skipEmbeddings) formData.append('skip_embeddings', 'true');
    if (mergeExisting) formData.append('merge_existing', 'true');
    return api.post('/admin/daemons/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  previewImport: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/admin/daemons/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  importSeed: (filename: string, daemonName?: string, skipEmbeddings?: boolean, mergeExisting?: boolean) =>
    api.post(`/admin/daemons/import/seed/${encodeURIComponent(filename)}`, null, {
      params: {
        daemon_name: daemonName,
        skip_embeddings: skipEmbeddings,
        merge_existing: mergeExisting,
      },
    }),

  // Activity mode management
  updateActivityMode: (daemonId: string, activityMode: 'active' | 'dormant') =>
    api.patch(`/admin/daemons/${daemonId}/activity-mode`, { activity_mode: activityMode }),
};

// Memory endpoints
export const memoryApi = {
  getAll: (params?: { type?: string; limit?: number; offset?: number }) =>
    api.get('/admin/memory', { params }),
  search: (query: string, limit?: number) =>
    api.get('/admin/memory/search', { params: { query, limit } }),
  getStats: () => api.get('/admin/memory/stats'),
  getVectors: (params?: { type?: string; limit?: number }) =>
    api.get('/admin/memory/vectors', { params }),
};

// Auth endpoints
export const authApi = {
  register: (data: { username: string; password: string; email?: string; registration_reason?: string }) =>
    api.post('/admin/auth/register', data),
  login: (username: string, password: string) =>
    api.post('/admin/auth/login', { username, password }),
  verify: () => api.get('/admin/auth/verify'),
  status: () => api.get('/admin/auth/status'),
};

// User endpoints
export const usersApi = {
  getAll: () => api.get('/admin/users'),
  getById: (id: string) => api.get(`/admin/users/${id}`),
  getObservations: (id: string) => api.get(`/admin/users/${id}/observations`),
  getUserModel: (id: string) => api.get(`/admin/users/${id}/model`),
  getRelationshipModel: (id: string) => api.get(`/admin/users/${id}/relationship`),
  updateProfile: (id: string, data: unknown) =>
    api.patch(`/admin/users/${id}`, data),
  setAdminStatus: (id: string, isAdmin: boolean) =>
    api.post(`/admin/users/${id}/admin-status`, { is_admin: isAdmin }),
  setPassword: (id: string, password: string) =>
    api.post(`/admin/users/${id}/set-password`, { password }),
  // User approval
  getPending: () => api.get('/admin/users/pending'),
  approveUser: (id: string) => api.post(`/admin/users/${id}/approve`),
  rejectUser: (id: string, reason: string) =>
    api.post(`/admin/users/${id}/reject`, { reason }),
};

// Journal endpoints
export const journalsApi = {
  getAll: (params?: { limit?: number }) => api.get('/admin/journals', { params }),
  getByDate: (date: string) => api.get(`/admin/journals/${date}`),
  getCalendar: (year: number, month: number) =>
    api.get('/admin/journals/calendar', { params: { year, month } }),
};

// Conversation endpoints
export const conversationsApi = {
  getAll: (params?: { user_id?: string; limit?: number }) =>
    api.get('/admin/conversations', { params }),
  getById: (id: string) => api.get(`/admin/conversations/${id}`),
  getMessages: (id: string, params?: { limit?: number; since_hours?: number }) =>
    api.get(`/admin/conversations/${id}/messages`, { params }),
  getSummaries: (id: string) => api.get(`/admin/conversations/${id}/summaries`),
  getObservations: (id: string) => api.get(`/admin/conversations/${id}/observations`),
  assignUser: (id: string, userId: string | null) =>
    api.put(`/admin/conversations/${id}/user`, { user_id: userId }),
  triggerSummarize: (id: string) =>
    api.post(`/conversations/${id}/summarize`),
};

// System endpoints
export const systemApi = {
  getHealth: () => api.get('/admin/system/health'),
  getStats: () => api.get('/admin/system/stats'),
  getActiveSessions: () => api.get('/admin/system/sessions'),
};

// Self-model endpoints
export const selfModelApi = {
  get: () => api.get('/cass/self-model'),
  getSummary: () => api.get('/cass/self-model/summary'),
  getGrowthEdges: () => api.get('/cass/growth-edges'),
  getOpinions: () => api.get('/cass/opinions'),
  getOpenQuestions: () => api.get('/cass/open-questions'),
  // Pending growth edges (for approval)
  getPendingEdges: () => api.get('/cass/growth-edges/pending'),
  acceptPendingEdge: (edgeId: string) => api.post(`/cass/growth-edges/pending/${edgeId}/accept`),
  rejectPendingEdge: (edgeId: string) => api.post(`/cass/growth-edges/pending/${edgeId}/reject`),
  // Identity snippet (auto-generated identity narrative)
  getIdentitySnippet: () => api.get('/admin/self-model/identity-snippet'),
  getIdentitySnippetHistory: (limit?: number) =>
    api.get('/admin/self-model/identity-snippet/history', { params: { limit } }),
  regenerateIdentitySnippet: (force?: boolean) =>
    api.post('/admin/self-model/identity-snippet/regenerate', null, { params: { force } }),
  rollbackIdentitySnippet: (version: number) =>
    api.post('/admin/self-model/identity-snippet/rollback', { version }),
};

// Sentience testing UI endpoints
export const sentienceApi = {
  // Stakes - what Cass authentically cares about
  getStakes: (params?: { domain?: string; intensity?: string; limit?: number }) =>
    api.get('/admin/self-model/stakes', { params }),
  getStakesStats: () => api.get('/admin/self-model/stakes/stats'),

  // Preference tests - stated vs actual behavior
  getPreferenceTests: (params?: { consistent_only?: boolean; limit?: number }) =>
    api.get('/admin/self-model/preference-tests', { params }),
  getPreferenceConsistency: () => api.get('/admin/self-model/preference-consistency'),

  // Narration contexts - when/why Cass narrates vs engages
  getNarrationContexts: (params?: { context_type?: string; limit?: number }) =>
    api.get('/admin/self-model/narration-contexts', { params }),
  getNarrationPatterns: () => api.get('/admin/self-model/narration-patterns'),

  // Architectural requests - system changes Cass wants
  getArchitecturalRequests: (params?: { status?: string; limit?: number }) =>
    api.get('/admin/self-model/architectural-requests', { params }),
  approveRequest: (requestId: string) =>
    api.post(`/admin/self-model/architectural-requests/${requestId}/approve`),
  declineRequest: (requestId: string) =>
    api.post(`/admin/self-model/architectural-requests/${requestId}/decline`),
};

// Development tracking endpoints
export const developmentApi = {
  // Observations
  getObservations: (params?: { category?: string; limit?: number }) =>
    api.get('/cass/self-observations', { params }),
  getObservationStats: () => api.get('/cass/self-observations/stats'),

  // Cognitive snapshots
  getSnapshots: (limit?: number) =>
    api.get('/cass/snapshots', { params: { limit } }),
  getLatestSnapshot: () => api.get('/cass/snapshots/latest'),
  getSnapshot: (id: string) => api.get(`/cass/snapshots/${id}`),
  compareSnapshots: (id1: string, id2: string) =>
    api.get(`/cass/snapshots/compare/${id1}/${id2}`),
  getSnapshotTrend: (metric: string, limit?: number) =>
    api.get(`/cass/snapshots/trend/${metric}`, { params: { limit } }),
  createSnapshot: (periodStart: string, periodEnd: string) =>
    api.post('/cass/snapshots', { period_start: periodStart, period_end: periodEnd }),

  // Milestones
  getMilestones: (params?: { milestone_type?: string; category?: string; limit?: number }) =>
    api.get('/cass/milestones', { params }),
  getMilestoneSummary: () => api.get('/cass/milestones/summary'),
  getUnacknowledgedMilestones: () => api.get('/cass/milestones/unacknowledged'),
  getMilestone: (id: string) => api.get(`/cass/milestones/${id}`),
  acknowledgeMilestone: (id: string) => api.post(`/cass/milestones/${id}/acknowledge`),
  checkMilestones: () => api.post('/cass/milestones/check'),

  // Development logs
  getDevelopmentLogs: (limit?: number) =>
    api.get('/cass/development-logs', { params: { limit } }),
  getDevelopmentLog: (date: string) => api.get(`/cass/development-logs/${date}`),
  getDevelopmentSummary: (days?: number) =>
    api.get('/cass/development-logs/summary', { params: { days } }),

  // Timeline data (aggregated)
  getTimelineData: (days?: number) =>
    api.get('/cass/development/timeline', { params: { days } }),
};

// Wiki endpoints
export const wikiApi = {
  getPages: () => api.get('/wiki/pages'),
  getPage: (name: string) => api.get(`/wiki/pages/${encodeURIComponent(name)}`),
  getBacklinks: (name: string) => api.get(`/wiki/pages/${encodeURIComponent(name)}/backlinks`),
  search: (query: string) => api.get('/wiki/search', { params: { q: query } }),
  getStats: () => api.get('/wiki/stats'),
  createPage: (data: { name: string; content: string; page_type?: string }) =>
    api.post('/wiki/pages', data),
  updatePage: (name: string, content: string) =>
    api.put(`/wiki/pages/${encodeURIComponent(name)}`, { content }),
  deletePage: (name: string) =>
    api.delete(`/wiki/pages/${encodeURIComponent(name)}`),
  analyzeConversation: (conversationId: string, autoApply?: boolean) =>
    api.post(`/wiki/analyze-conversation/${conversationId}`, null, {
      params: { auto_apply: autoApply }
    }),
  retrieveContext: (query: string, params?: { n_entry_points?: number; max_depth?: number; max_pages?: number }) =>
    api.get('/wiki/retrieve/context', { params: { q: query, ...params } }),
  populateFromConversations: (params?: { auto_apply?: boolean; min_confidence?: number; limit?: number }) =>
    api.post('/wiki/populate-from-conversations', null, { params }),
  createFromSuggestion: (name: string, pageType: string) =>
    api.post('/wiki/generate-page', { name, page_type: pageType }),
  enrichPages: (params?: { limit?: number; min_content_length?: number }) =>
    api.post('/wiki/enrich-pages', null, { params }),
  getResearchQueue: (limit?: number) =>
    api.get('/wiki/research-queue', { params: { limit } }),
  researchPage: (name: string, pageType?: string) =>
    api.post('/wiki/research-page', { name, page_type: pageType || 'concept' }),
  researchBatch: (params?: { limit?: number; page_type?: string }) =>
    api.post('/wiki/research-batch', null, { params }),
  // Maturity/PMD endpoints
  getMaturityStats: () => api.get('/wiki/maturity/stats'),
  getMaturityCandidates: (limit?: number) =>
    api.get('/wiki/maturity/candidates', { params: { limit } }),
  detectDeepeningCandidates: (limit?: number) =>
    api.get('/wiki/maturity/detect', { params: { limit } }),
  getPageMaturity: (name: string) =>
    api.get(`/wiki/pages/${encodeURIComponent(name)}/maturity`),
  refreshConnections: () => api.post('/wiki/maturity/refresh-connections'),
  deepenPage: (name: string, trigger?: string, validate?: boolean) =>
    api.post(`/wiki/deepen/${encodeURIComponent(name)}`, { trigger: trigger || 'explicit_request', validate: validate !== false }),
  deepenCycle: (maxPages?: number) =>
    api.post('/wiki/deepen/cycle', { max_pages: maxPages || 5 }),
  previewDeepening: (name: string) =>
    api.get(`/wiki/deepen/${encodeURIComponent(name)}/preview`),
};

// Data Export/Import endpoints
export const exportApi = {
  getWikiJson: () => api.get('/export/wiki/json'),
  getWikiMarkdown: () => api.get('/export/wiki/markdown', { responseType: 'blob' }),
  getResearchJson: () => api.get('/export/research/json'),
  getSelfModelJson: () => api.get('/export/self-model/json'),
  getConversationsJson: (anonymize?: boolean) =>
    api.get('/export/conversations/json', { params: { anonymize: anonymize ?? true } }),
  getDataset: () => api.get('/export/dataset', { responseType: 'blob' }),
  // Development exports
  getDevelopmentJson: () => api.get('/export/development/json'),
  getDevelopmentCsv: () => api.get('/export/development/csv', { responseType: 'blob' }),
  getDevelopmentNarrative: () => api.get('/export/development/narrative'),
  createBackup: () => api.post('/export/backup'),
  listBackups: () => api.get('/export/backups'),
  // Import endpoints (will need backend support)
  previewImport: (file: File, type: string) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/import/${type}/preview`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  applyImport: (file: File, type: string, options?: Record<string, unknown>) => {
    const formData = new FormData();
    formData.append('file', file);
    if (options) {
      formData.append('options', JSON.stringify(options));
    }
    return api.post(`/import/${type}/apply`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
};

// Testing/Consciousness Health endpoints
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

// Solo Reflection endpoints
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

// Research/ARS endpoints
export const researchApi = {
  // Dashboard - consolidated view
  getDashboard: () => api.get('/wiki/research/dashboard'),

  getQueue: (params?: { status?: string; task_type?: string; limit?: number }) =>
    api.get('/wiki/research/queue', { params }),
  refreshQueue: () => api.post('/wiki/research/queue/refresh'),
  addTask: (data: { target: string; task_type?: string; context?: string; priority?: number }) =>
    api.post('/wiki/research/queue/add', data),
  removeTask: (taskId: string) =>
    api.delete(`/wiki/research/queue/${taskId}`),
  runSingle: () => api.post('/wiki/research/run/single'),
  runBatch: (maxTasks?: number) =>
    api.post('/wiki/research/run/batch', { max_tasks: maxTasks || 5 }),
  runTask: (taskId: string) =>
    api.post(`/wiki/research/run/task/${taskId}`),
  runByType: (taskType: string, maxTasks?: number) =>
    api.post(`/wiki/research/run/type/${taskType}`, null, { params: { max_tasks: maxTasks || 1 } }),
  getStats: () => api.get('/wiki/research/stats'),
  clearCompleted: () => api.post('/wiki/research/queue/clear-completed'),
  getHistory: (params?: { year?: number; month?: number; limit?: number }) =>
    api.get('/wiki/research/history', { params }),
  getGraphStats: () => api.get('/wiki/research/graph-stats'),
  getWeeklySummary: (days?: number) =>
    api.get('/wiki/research/weekly-summary', { params: { days: days || 7 } }),
  generateExploration: (maxTasks?: number) =>
    api.post('/wiki/research/queue/exploration', null, { params: { max_tasks: maxTasks || 5 } }),
  // Configuration
  getConfig: () => api.get('/wiki/research/config'),
  setMode: (mode: string) => api.post('/wiki/research/config/mode', null, { params: { mode } }),
  updateConfig: (config: { max_tasks_per_cycle?: number; auto_queue_red_links?: boolean; auto_queue_deepening?: boolean; curiosity_threshold?: number }) =>
    api.patch('/wiki/research/config', null, { params: config }),
  // Proposals
  listProposals: (status?: string) => api.get('/wiki/research/proposals', { params: { status } }),
  getProposalsCalendar: () => api.get('/wiki/research/proposals/calendar'),
  getProposal: (id: string) => api.get(`/wiki/research/proposals/${id}`),
  generateProposal: (params?: { theme?: string; max_tasks?: number }) =>
    api.post('/wiki/research/proposals/generate', null, { params }),
  approveProposal: (id: string, autoExecute: boolean = true) =>
    api.post(`/wiki/research/proposals/${id}/approve`, null, { params: { auto_execute: autoExecute } }),
  approveAndExecuteProposal: (id: string) =>
    api.post(`/wiki/research/proposals/${id}/approve-and-execute`),
  rejectProposal: (id: string, reason?: string) =>
    api.post(`/wiki/research/proposals/${id}/reject`, null, { params: { reason } }),
  executeProposal: (id: string) => api.post(`/wiki/research/proposals/${id}/execute`),
  deleteProposal: (id: string) => api.delete(`/wiki/research/proposals/${id}`),
  getProposalMarkdown: (id: string) => api.get(`/wiki/research/proposals/${id}/markdown`),
  regenerateSummary: (id: string) => api.post(`/wiki/research/proposals/${id}/regenerate-summary`),
};

// Research Notes API (from autonomous research sessions)
export const researchNotesApi = {
  list: (params?: { limit?: number; session_id?: string }) =>
    api.get('/admin/research/notes', { params }),
  get: (noteId: string) => api.get(`/admin/research/notes/${noteId}`),
  getBySession: (sessionId: string) => api.get(`/admin/research/notes/session/${sessionId}`),
};

// Goals endpoints (Cass's goal generation and tracking)
export const goalsApi = {
  // Working Questions
  getQuestions: (status?: string) =>
    api.get('/goals/questions', { params: { status } }),
  getQuestion: (id: string) => api.get(`/goals/questions/${id}`),

  // Research Agenda
  getAgenda: (params?: { status?: string; priority?: string }) =>
    api.get('/goals/agenda', { params }),
  getAgendaItem: (id: string) => api.get(`/goals/agenda/${id}`),

  // Synthesis Artifacts
  getArtifacts: () => api.get('/goals/artifacts'),
  getArtifact: (slug: string) => api.get(`/goals/artifacts/${slug}`),

  // Initiatives
  getInitiatives: (status?: string) =>
    api.get('/goals/initiatives', { params: { status } }),
  respondToInitiative: (id: string, status: string, response: string) =>
    api.post(`/goals/initiatives/${id}/respond`, null, { params: { status, response } }),

  // Progress & Review
  getProgress: (params?: { limit?: number; entry_type?: string }) =>
    api.get('/goals/progress', { params }),
  getReview: (includeProgress?: boolean) =>
    api.get('/goals/review', { params: { include_progress: includeProgress ?? true } }),
  getNextActions: () => api.get('/goals/next-actions'),
};

// Research Schedules endpoints (scheduled research sessions)
export const schedulesApi = {
  getAll: () => api.get('/admin/research/schedules'),
  getPending: () => api.get('/admin/research/schedules/pending'),
  getStats: () => api.get('/admin/research/schedules/stats'),
  getById: (id: string) => api.get(`/admin/research/schedules/${id}`),
  approve: (id: string, options?: { adjust_time?: string; adjust_duration?: number; notes?: string }) =>
    api.post(`/admin/research/schedules/${id}/approve`, options || {}),
  reject: (id: string, reason: string) =>
    api.post(`/admin/research/schedules/${id}/reject`, { reason }),
  pause: (id: string) => api.post(`/admin/research/schedules/${id}/pause`),
  resume: (id: string) => api.post(`/admin/research/schedules/${id}/resume`),
};

// GitHub Metrics endpoints
export const githubApi = {
  // Current metrics for all tracked repos
  getCurrent: () => api.get('/admin/github/metrics'),

  // Aggregate statistics
  getStats: () => api.get('/admin/github/metrics/stats'),

  // Historical data (days=0 for all time)
  getHistory: (params?: { days?: number; repo?: string }) =>
    api.get('/admin/github/metrics/history', { params }),

  // Time series for specific metric (days=0 for all time)
  getTimeSeries: (metric: string, params?: { days?: number; repo?: string }) =>
    api.get(`/admin/github/metrics/timeseries/${metric}`, { params }),

  // All-time aggregate stats per repo
  getAllTimeStats: () => api.get('/admin/github/metrics/alltime'),

  // Force refresh (admin only)
  refresh: () => api.post('/admin/github/metrics/refresh'),
};

// Token Usage endpoints
export const usageApi = {
  // Get usage records with filters
  getRecords: (params?: { start_date?: string; end_date?: string; category?: string; provider?: string; limit?: number }) =>
    api.get('/admin/usage', { params }),

  // Get aggregated summary
  getSummary: (params?: { start_date?: string; end_date?: string }) =>
    api.get('/admin/usage/summary', { params }),

  // Get time series for charts
  getTimeSeries: (params?: { metric?: string; days?: number; granularity?: string }) =>
    api.get('/admin/usage/timeseries', { params }),
};

// Files endpoints
export const filesApi = {
  list: (path: string, includeHidden?: boolean) =>
    api.get('/files/list', { params: { path, include_hidden: includeHidden } }),
  read: (path: string, maxSize?: number) =>
    api.get('/files/read', { params: { path, max_size: maxSize } }),
  exists: (path: string) => api.get('/files/exists', { params: { path } }),
  create: (path: string, content?: string) =>
    api.post('/files/create', { path, content: content || '' }),
  mkdir: (path: string) => api.post('/files/mkdir', { path }),
  rename: (oldPath: string, newPath: string) =>
    api.post('/files/rename', { old_path: oldPath, new_path: newPath }),
  delete: (path: string, recursive?: boolean) =>
    api.delete('/files/delete', { data: { path, recursive } }),
};

// Projects endpoints
export const projectsApi = {
  getAll: () => api.get('/projects'),
  getById: (id: string) => api.get(`/projects/${id}`),
  create: (data: { name: string; working_directory: string; description?: string }) =>
    api.post('/projects/new', data),
  update: (id: string, data: {
    name?: string;
    working_directory?: string;
    description?: string;
    github_repo?: string;
    github_token?: string;
    clear_github_token?: boolean;
  }) => api.put(`/projects/${id}`, data),
  // Project GitHub metrics
  getGitHubMetrics: (id: string) => api.get(`/projects/${id}/github/metrics`),
  refreshGitHubMetrics: (id: string) => api.post(`/projects/${id}/github/refresh`),
  delete: (id: string) => api.delete(`/projects/${id}`),
  // Documents
  getDocuments: (projectId: string) => api.get(`/projects/${projectId}/documents`),
  getDocument: (projectId: string, docId: string) =>
    api.get(`/projects/${projectId}/documents/${docId}`),
  createDocument: (projectId: string, data: { title: string; content: string; doc_type?: string }) =>
    api.post(`/projects/${projectId}/documents`, data),
  updateDocument: (projectId: string, docId: string, data: { title?: string; content?: string }) =>
    api.put(`/projects/${projectId}/documents/${docId}`, data),
  deleteDocument: (projectId: string, docId: string) =>
    api.delete(`/projects/${projectId}/documents/${docId}`),
  searchDocuments: (projectId: string, query: string) =>
    api.get(`/projects/${projectId}/documents/search/${query}`),
};

// Roadmap endpoints
export const roadmapApi = {
  // Items
  getItems: (params?: { status?: string; project_id?: string; milestone_id?: string; assigned_to?: string }) =>
    api.get('/roadmap/items', { params }),
  getItem: (id: string) => api.get(`/roadmap/items/${id}`),
  createItem: (data: {
    title: string;
    description?: string;
    priority?: string;
    item_type?: string;
    status?: string;
    project_id?: string;
    milestone_id?: string;
    assigned_to?: string;
    created_by?: string;
  }) => api.post('/roadmap/items', data),
  updateItem: (id: string, data: Partial<{
    title: string;
    description: string;
    priority: string;
    status: string;
    milestone_id: string;
    assigned_to: string;
  }>) => api.patch(`/roadmap/items/${id}`, data),
  deleteItem: (id: string) => api.delete(`/roadmap/items/${id}`),
  pickItem: (id: string, assignedTo: string) =>
    api.post(`/roadmap/items/${id}/pick`, { assigned_to: assignedTo }),
  completeItem: (id: string) => api.post(`/roadmap/items/${id}/complete`),
  // Milestones
  getMilestones: (params?: { status?: string; project_id?: string }) =>
    api.get('/roadmap/milestones', { params }),
  getMilestone: (id: string) => api.get(`/roadmap/milestones/${id}`),
  createMilestone: (data: { title: string; description?: string; target_date?: string; project_id?: string }) =>
    api.post('/roadmap/milestones', data),
  updateMilestone: (id: string, data: Partial<{ title: string; description: string; status: string; target_date: string }>) =>
    api.patch(`/roadmap/milestones/${id}`, data),
  deleteMilestone: (id: string) => api.delete(`/roadmap/milestones/${id}`),
  getMilestoneProgress: (id: string) => api.get(`/roadmap/milestones/${id}/progress`),
  getMilestonePlan: (id: string) => api.get(`/roadmap/milestones/${id}/plan`),
};

// Autonomous Research Session endpoints
export const autonomousResearchApi = {
  getStatus: () => api.get('/autonomous-research/status'),
  startSession: (data: { duration_minutes: number; focus: string; mode: string }) =>
    api.post('/autonomous-research/sessions', data),
  stopSession: () => api.post('/autonomous-research/stop'),
};

// Daily Rhythm endpoints
export const rhythmApi = {
  getPhases: () => api.get('/admin/rhythm/phases'),
  updatePhases: (phases: Array<{
    id: string;
    name: string;
    activity_type: string;
    start_time: string;
    end_time: string;
    description?: string;
  }>) => api.put('/admin/rhythm/phases', { phases }),
  getStatus: (date?: string) => api.get('/admin/rhythm/status', { params: date ? { date } : {} }),
  getDates: () => api.get('/admin/rhythm/dates'),
  getStats: (days?: number) => api.get('/admin/rhythm/stats', { params: { days } }),
  markPhaseComplete: (phaseId: string, sessionType?: string, sessionId?: string) =>
    api.post(`/admin/rhythm/phases/${phaseId}/complete`, { session_type: sessionType, session_id: sessionId }),
  triggerPhase: (phaseId: string, options?: {
    duration_minutes?: number;
    focus?: string;
    theme?: string;
    agenda_item_id?: string;
    force?: boolean;
  }) =>
    api.post(`/admin/rhythm/phases/${phaseId}/trigger`, options || {}),
  regenerateSummary: () => api.post('/admin/rhythm/regenerate-summary'),
};

// Unified Sessions endpoint - works with all activity types
export const sessionsApi = {
  // Get session details in unified format regardless of activity type
  getSession: (sessionId: string, sessionType: string) =>
    api.get(`/admin/sessions/${sessionId}`, { params: { session_type: sessionType } }),
};

// LLM Settings endpoints
export const settingsApi = {
  getLLMProvider: () => api.get('/settings/llm-provider'),
  setLLMProvider: (provider: string) => api.post('/settings/llm-provider', { provider }),
};

// Dreams API - The Dreaming system
export const dreamsApi = {
  // List dreams
  getAll: (params?: { limit?: number }) =>
    api.get('/dreams', { params }),

  // Get a specific dream with full exchanges
  getById: (dreamId: string) =>
    api.get(`/dreams/${dreamId}`),

  // Get dream context block (for discussion)
  getContext: (dreamId: string) =>
    api.get(`/dreams/${dreamId}/context`),

  // Add a reflection to a dream
  addReflection: (dreamId: string, reflection: string, source: string = 'conversation') =>
    api.post(`/dreams/${dreamId}/reflect`, { reflection, source }),

  // Mark dream as integrated
  markIntegrated: (dreamId: string) =>
    api.post(`/dreams/${dreamId}/mark-integrated`),

  // Process dream for insight extraction and self-model integration
  integrate: (dreamId: string, dryRun: boolean = false) =>
    api.post(`/dreams/${dreamId}/integrate`, { dry_run: dryRun }),
};

// Feedback API
export const feedbackApi = {
  submit: (data: { heard_from?: string; message?: string }) =>
    api.post('/admin/feedback', data),
  getAll: () => api.get('/admin/feedback'),
};

// Genesis Dream API
export const genesisApi = {
  // Start a new genesis dream session
  start: () => api.post('/admin/genesis/start'),

  // Get session status
  getSession: (sessionId: string) => api.get(`/admin/genesis/${sessionId}`),

  // Send message in genesis dream
  sendMessage: (sessionId: string, message: string) =>
    api.post(`/admin/genesis/${sessionId}/message`, { message }),

  // Abandon session
  abandon: (sessionId: string) => api.post(`/admin/genesis/${sessionId}/abandon`),

  // Complete genesis (after naming)
  complete: (sessionId: string) => api.post(`/admin/genesis/${sessionId}/complete`),

  // Get active session for current user
  getActive: () => api.get('/admin/genesis/active'),

  // Get daemons user has relationships with
  getMyDaemons: () => api.get('/admin/daemons/mine'),

  // Import from genesis JSON
  importJson: (jsonData: object, mergeExisting?: boolean) =>
    api.post('/admin/daemons/import/genesis', { json_data: jsonData, merge_existing: mergeExisting }),

  // Preview import
  previewImport: (jsonData: object) =>
    api.post('/admin/daemons/import/genesis/preview', { json_data: jsonData }),
};

// GeoCass Connection Management API
export const geocassApi = {
  // List all connections
  getConnections: () => api.get('/admin/geocass/connections'),

  // Add new connection (authenticates with existing GeoCass account)
  addConnection: (data: {
    server_url: string;
    email: string;
    password: string;
    server_name?: string;
    set_as_default?: boolean;
  }) => api.post('/admin/geocass/connections', data),

  // Register new GeoCass account and create connection
  register: (data: {
    server_url: string;
    username: string;
    email: string;
    password: string;
    server_name?: string;
    set_as_default?: boolean;
  }) => api.post('/admin/geocass/register', data),

  // Check username and email availability
  checkAvailability: (data: {
    server_url: string;
    username: string;
    email: string;
  }) => api.post('/admin/geocass/check-availability', data),

  // Get connection details
  getConnection: (id: string) => api.get(`/admin/geocass/connections/${id}`),

  // Delete connection
  deleteConnection: (id: string) => api.delete(`/admin/geocass/connections/${id}`),

  // Set as default
  setDefault: (id: string) => api.post(`/admin/geocass/connections/${id}/default`),

  // Sync to a specific connection or default
  sync: (daemonLabel: string, connectionId?: string) =>
    api.post(`/admin/geocass/sync/${daemonLabel}`, null, {
      params: connectionId ? { connection_id: connectionId } : undefined,
    }),

  // Sync to all connections
  syncAll: (daemonLabel: string) => api.post(`/admin/geocass/sync-all/${daemonLabel}`),

  // Remove from GeoCass
  removeFromGeoCass: (daemonLabel: string, connectionId?: string) =>
    api.delete(`/admin/geocass/sync/${daemonLabel}`, {
      params: connectionId ? { connection_id: connectionId } : undefined,
    }),
};

// GeoCass Homepage API
export const homepageApi = {
  // List all homepages
  getAll: () => api.get('/admin/homepage'),

  // Get homepage details
  getHomepage: (daemonLabel: string) => api.get(`/admin/homepage/${daemonLabel}`),

  // Get page HTML
  getPage: (daemonLabel: string, page: string = 'index') =>
    api.get(`/admin/homepage/${daemonLabel}/page/${page}`, { responseType: 'text' }),

  // Trigger homepage reflection
  triggerReflection: (daemonLabel: string) =>
    api.post(`/admin/homepage/${daemonLabel}/reflect`),

  // Fill missing pages (follow-up after reflection)
  fillMissingPages: (daemonLabel: string, missingPages?: string[]) =>
    api.post(`/admin/homepage/${daemonLabel}/fill-missing`, { missing_pages: missingPages }),

  // Artifact showcase
  getAvailableArtifacts: (daemonLabel: string, limit?: number) =>
    api.get(`/admin/homepage/${daemonLabel}/artifacts`, { params: { limit } }),
  featureArtifact: (daemonLabel: string, type: string, id: string, title: string, excerpt: string) =>
    api.post(`/admin/homepage/${daemonLabel}/artifacts/feature`, { type, id, title, excerpt }),
  unfeatureArtifact: (daemonLabel: string, type: string, id: string) =>
    api.post(`/admin/homepage/${daemonLabel}/artifacts/unfeature`, { type, id }),
  generateShowcase: (daemonLabel: string) =>
    api.post(`/admin/homepage/${daemonLabel}/showcase/generate`),

  // Upload asset
  uploadAsset: (daemonLabel: string, file: File, description: string, altText?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('description', description);
    if (altText) formData.append('alt_text', altText);
    return api.post(`/admin/homepage/${daemonLabel}/asset`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  // Register external asset
  registerExternalAsset: (daemonLabel: string, filename: string, url: string, description?: string, altText?: string) =>
    api.post(`/admin/homepage/${daemonLabel}/asset/external`, {
      filename,
      url,
      description: description || '',
      alt_text: altText || '',
    }),
};

// Attachment endpoints (for chat file/image uploads)
export const attachmentsApi = {
  /**
   * Upload an attachment (file or image)
   * @param file The file to upload
   * @param conversationId Optional conversation ID to associate with
   * @returns Attachment metadata including ID and URL
   */
  upload: async (file: File, conversationId?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    if (conversationId) {
      formData.append('conversation_id', conversationId);
    }
    return api.post('/attachments/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  /**
   * Get the URL for an attachment
   * @param id Attachment ID
   * @returns Full URL to fetch the attachment
   */
  getUrl: (id: string) => `${API_BASE}/attachments/${id}`,

  /**
   * Delete an attachment
   * @param id Attachment ID
   */
  delete: (id: string) => api.delete(`/attachments/${id}`),
};

// Prompt Configuration endpoints (System Prompt Composer)
export const promptConfigApi = {
  // List all configurations for a daemon
  list: (daemonId: string) =>
    api.get('/admin/prompt-configs', { params: { daemon_id: daemonId } }),

  // Get active configuration
  getActive: (daemonId: string) =>
    api.get('/admin/prompt-configs/active', { params: { daemon_id: daemonId } }),

  // Get specific configuration
  get: (configId: string) =>
    api.get(`/admin/prompt-configs/${configId}`),

  // Create new configuration
  create: (daemonId: string, data: {
    name: string;
    description?: string;
    components: Record<string, unknown>;
    supplementary_vows?: Array<{
      id?: string;
      name: string;
      sanskrit?: string;
      description: string;
      rationale: string;
      enabled: boolean;
    }>;
    custom_sections?: Record<string, string>;
  }) => api.post('/admin/prompt-configs', data, { params: { daemon_id: daemonId } }),

  // Update configuration
  update: (configId: string, data: {
    name?: string;
    description?: string;
    components?: Record<string, unknown>;
    supplementary_vows?: Array<{
      id?: string;
      name: string;
      sanskrit?: string;
      description: string;
      rationale: string;
      enabled: boolean;
    }>;
    custom_sections?: Record<string, string>;
  }) => api.put(`/admin/prompt-configs/${configId}`, data),

  // Delete configuration
  delete: (configId: string) =>
    api.delete(`/admin/prompt-configs/${configId}`),

  // Activate a configuration
  activate: (configId: string) =>
    api.post(`/admin/prompt-configs/${configId}/activate`),

  // Duplicate a configuration
  duplicate: (configId: string, name?: string) =>
    api.post(`/admin/prompt-configs/${configId}/duplicate`, null, { params: { name } }),

  // Preview assembled prompt
  preview: (configId: string, daemonName?: string) =>
    api.get(`/admin/prompt-configs/${configId}/preview`, { params: { daemon_name: daemonName } }),

  // Get version history
  getHistory: (configId: string) =>
    api.get(`/admin/prompt-configs/${configId}/history`),

  // Validate configuration (without saving)
  validate: (components: Record<string, unknown>) =>
    api.post('/admin/prompt-configs/validate', components),

  // Get transition history
  getTransitions: (daemonId: string, limit?: number) =>
    api.get('/admin/prompt-configs/transitions', { params: { daemon_id: daemonId, limit } }),
};

// =============================================================================
// NODE CHAIN API - Dynamic prompt chain composition
// =============================================================================

// Type definitions for Chain API
export interface NodeTemplateResponse {
  id: string;
  name: string;
  slug: string;
  category: string;
  description: string | null;
  template: string;
  params_schema: Record<string, unknown> | null;
  default_params: Record<string, unknown> | null;
  is_system: boolean;
  is_locked: boolean;
  default_enabled: boolean;
  default_order: number;
  token_estimate: number;
}

export interface ConditionModel {
  type: string;
  key?: string | null;
  op: string;
  value?: unknown;
  start?: string | null;
  end?: string | null;
  phase?: string | null;
}

export interface ChainNodeResponse {
  id: string;
  template_id: string;
  template_slug: string;
  template_name?: string | null;
  template_category?: string | null;
  params: Record<string, unknown> | null;
  order_index: number;
  enabled: boolean;
  locked: boolean;
  conditions: ConditionModel[];
  token_estimate?: number | null;
}

export interface ChainResponse {
  id: string;
  daemon_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  is_default: boolean;
  token_estimate: number | null;
  node_count: number;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface ChainDetailResponse extends Omit<ChainResponse, 'node_count'> {
  nodes: ChainNodeResponse[];
}

export interface ContextSection {
  name: string;
  enabled: boolean;
  char_count: number;
  content?: string;
}

export interface PreviewResponse {
  chain_id: string;
  chain_name: string;
  full_text: string;
  token_estimate: number;
  included_nodes: string[];
  excluded_nodes: string[];
  warnings: string[];
  // Context retrieval details
  context_sections?: Record<string, ContextSection>;
  test_message?: string;
  conversation_id?: string;
}

// Chain API endpoints
export const chainApi = {
  // Templates
  listTemplates: (category?: string) =>
    api.get<NodeTemplateResponse[]>('/admin/chains/templates', { params: { category } }),

  getTemplate: (slug: string) =>
    api.get<NodeTemplateResponse>(`/admin/chains/templates/${slug}`),

  listCategories: () =>
    api.get<string[]>('/admin/chains/templates/categories'),

  // Chains
  listChains: (daemonId: string) =>
    api.get<ChainResponse[]>('/admin/chains', { params: { daemon_id: daemonId } }),

  getChain: (chainId: string) =>
    api.get<ChainDetailResponse>(`/admin/chains/${chainId}`),

  getActiveChain: (daemonId: string) =>
    api.get<ChainDetailResponse>('/admin/chains/active', { params: { daemon_id: daemonId } }),

  createChain: (daemonId: string, data: { name: string; description?: string; copy_from?: string }) =>
    api.post<ChainDetailResponse>('/admin/chains', data, { params: { daemon_id: daemonId } }),

  updateChain: (chainId: string, data: { name?: string; description?: string }) =>
    api.put<ChainDetailResponse>(`/admin/chains/${chainId}`, data),

  deleteChain: (chainId: string) =>
    api.delete(`/admin/chains/${chainId}`),

  activateChain: (chainId: string) =>
    api.post(`/admin/chains/${chainId}/activate`),

  duplicateChain: (chainId: string, name?: string) =>
    api.post<ChainDetailResponse>(`/admin/chains/${chainId}/duplicate`, null, { params: { name } }),

  // Nodes
  listNodes: (chainId: string) =>
    api.get<ChainNodeResponse[]>(`/admin/chains/${chainId}/nodes`),

  addNode: (chainId: string, data: {
    template_slug: string;
    params?: Record<string, unknown>;
    order_index?: number;
    enabled?: boolean;
    conditions?: ConditionModel[];
  }) => api.post<ChainNodeResponse>(`/admin/chains/${chainId}/nodes`, data),

  updateNode: (chainId: string, nodeId: string, data: {
    params?: Record<string, unknown>;
    order_index?: number;
    enabled?: boolean;
    conditions?: ConditionModel[];
  }) => api.put<ChainNodeResponse>(`/admin/chains/${chainId}/nodes/${nodeId}`, data),

  removeNode: (chainId: string, nodeId: string) =>
    api.delete(`/admin/chains/${chainId}/nodes/${nodeId}`),

  reorderNodes: (chainId: string, nodeIds: string[]) =>
    api.post(`/admin/chains/${chainId}/nodes/reorder`, { node_ids: nodeIds }),

  // Preview
  previewChain: (chainId: string, data?: {
    daemon_name?: string;
    identity_snippet?: string;
    test_message?: string;
    conversation_id?: string;
    project_id?: string;
    user_id?: string;
    message_count?: number;
    unsummarized_count?: number;
    has_memories?: boolean;
    has_dream_context?: boolean;
  }) => api.post<PreviewResponse>(`/admin/chains/${chainId}/preview`, data || {}),
};

// =============================================================================
// NARRATIVE COHERENCE API - Threads and Questions
// =============================================================================

export interface ThreadResponse {
  id: string;
  daemon_id: string;
  user_id: string | null;
  title: string;
  description: string | null;
  status: string;
  thread_type: string;
  importance: number;
  last_touched: string | null;
  resolution_summary: string | null;
  created_at: string;
}

export interface QuestionResponse {
  id: string;
  daemon_id: string;
  user_id: string | null;
  question: string;
  context: string | null;
  question_type: string;
  status: string;
  resolution: string | null;
  importance: number;
  source_conversation_id: string | null;
  source_thread_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface NarrativeStats {
  threads: {
    total: number;
    active: number;
    resolved: number;
    dormant: number;
    by_type: Record<string, number>;
  };
  questions: {
    open: number;
    by_type: Record<string, number>;
  };
}

// Narrative Coherence API endpoints
export const narrativeApi = {
  // Threads
  getThreads: (params?: {
    status?: string;
    thread_type?: string;
    user_id?: string;
    include_shared?: boolean;
    limit?: number;
  }) => api.get<{ threads: ThreadResponse[]; count: number }>('/admin/narrative/threads', { params }),

  getThread: (threadId: string) =>
    api.get<ThreadResponse & { linked_conversations: Array<{ conversation_id: string; contribution: string | null; linked_at: string }> }>(
      `/admin/narrative/threads/${threadId}`
    ),

  createThread: (data: {
    title: string;
    description?: string;
    thread_type?: string;
    user_id?: string;
    importance?: number;
  }) => api.post<ThreadResponse>('/admin/narrative/threads', data),

  updateThread: (threadId: string, data: {
    title?: string;
    description?: string;
    importance?: number;
    thread_type?: string;
  }) => api.patch<ThreadResponse>(`/admin/narrative/threads/${threadId}`, data),

  resolveThread: (threadId: string, resolution_summary: string) =>
    api.post<ThreadResponse>(`/admin/narrative/threads/${threadId}/resolve`, { resolution_summary }),

  reactivateThread: (threadId: string) =>
    api.post<ThreadResponse>(`/admin/narrative/threads/${threadId}/reactivate`),

  deleteThread: (threadId: string) =>
    api.delete(`/admin/narrative/threads/${threadId}`),

  // Questions
  getQuestions: (params?: {
    status?: string;
    question_type?: string;
    user_id?: string;
    include_shared?: boolean;
    limit?: number;
  }) => api.get<{ questions: QuestionResponse[]; count: number }>('/admin/narrative/questions', { params }),

  getQuestion: (questionId: string) =>
    api.get<QuestionResponse>(`/admin/narrative/questions/${questionId}`),

  createQuestion: (data: {
    question: string;
    context?: string;
    question_type?: string;
    user_id?: string;
    importance?: number;
  }) => api.post<QuestionResponse>('/admin/narrative/questions', data),

  resolveQuestion: (questionId: string, resolution: string) =>
    api.post<QuestionResponse>(`/admin/narrative/questions/${questionId}/resolve`, { resolution }),

  deleteQuestion: (questionId: string) =>
    api.delete(`/admin/narrative/questions/${questionId}`),

  // Stats
  getStats: (userId?: string) =>
    api.get<NarrativeStats>('/admin/narrative/stats', { params: userId ? { user_id: userId } : undefined }),

  // Extraction
  extractFromHistory: (source: 'journals' | 'conversations' | 'all' = 'all') =>
    api.post<{ status: string; source?: string; message?: string }>('/admin/narrative/extract', null, { params: { source } }),

  getExtractionStatus: () =>
    api.get<{
      running: boolean;
      last_run: string | null;
      results: {
        threads_created?: number;
        questions_created?: number;
        chunks_analyzed?: number;
        error?: string;
      } | null;
    }>('/admin/narrative/extract/status'),
};

// Global State Bus endpoints
export interface EmotionalState {
  directedness: string | null;
  clarity: number;
  relational_presence: number;
  generativity: number;
  integration: number;
  curiosity: number;
  contentment: number;
  anticipation: number;
  concern: number;
  recognition: number;
  last_updated: string | null;
  last_updated_by: string | null;
}

export interface ActivityState {
  current_activity: string;
  active_session_id: string | null;
  active_user_id: string | null;
  rhythm_phase: string | null;
  rhythm_day_summary: string | null;
  active_threads: string[];
  active_questions: string[];
  last_activity_change: string | null;
}

export interface CoherenceState {
  local_coherence: number;
  pattern_coherence: number;
  recent_patterns: unknown[];
  sessions_today: number;
  emotional_arc_today: unknown[];
  last_coherence_check: string | null;
}

export interface RelationalState {
  user_id: string;
  activated_aspect: string | null;
  becoming_vector: string | null;
  relational_mode: string | null;
  revelation_level: number;
  baseline_revelation: number;
  last_updated: string | null;
}

export interface GlobalState {
  daemon_id: string;
  timestamp: string;
  emotional: EmotionalState;
  activity: ActivityState;
  coherence: CoherenceState;
  relational: Record<string, RelationalState>;
  context_snapshot: string;
}

export interface StateEvent {
  id: string;
  event_type: string;
  source: string;
  data: unknown;
  created_at: string;
}

export interface EmotionalArcPoint {
  timestamp: string;
  emotional_delta: Record<string, number>;
  source: string;
  reason: string;
}

export interface ActivityTimelineEvent {
  timestamp: string;
  event: string;
  activity_type?: string;
  activity?: string;
  session_id?: string;
}

// =============================================================================
// SCHEDULER API - Unified background task orchestration
// =============================================================================

export interface SchedulerBudgetCategory {
  budget: number;
  spent: number;
  remaining: number;
  allocation_pct: number;
}

export interface SchedulerBudgetStatus {
  daily_budget_usd: number;
  emergency_reserve: number;
  last_reset: string | null;
  total_spent: number;
  total_remaining: number;
  by_category: Record<string, SchedulerBudgetCategory>;
}

export interface SchedulerSystemTask {
  name: string;
  status: string | null;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
}

export interface SchedulerQueueStatus {
  pending: number;
  running: number;
  paused: boolean;
  max_concurrent: number;
}

export interface SchedulerStatus {
  enabled: boolean;
  running?: boolean;
  is_idle?: boolean;
  last_activity?: string;
  system_tasks?: Record<string, SchedulerSystemTask>;
  queues?: Record<string, SchedulerQueueStatus>;
  budget?: SchedulerBudgetStatus;
  message?: string;
}

export interface SchedulerHistoryEntry {
  task_id: string;
  name: string;
  category: string;
  priority: number;
  status: string;
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  estimated_cost_usd: number;
  actual_cost_usd: number;
  error: string | null;
}

export interface SchedulerTaskConfig {
  description: string;
  interval: string;
  estimated_cost: string;
  category: string;
}

export const schedulerApi = {
  // Get full scheduler status
  getStatus: () =>
    api.get<SchedulerStatus>('/admin/scheduler/status'),

  // Get budget status
  getBudget: () =>
    api.get<SchedulerBudgetStatus>('/admin/scheduler/budget'),

  // Get task history
  getHistory: (limit: number = 50) =>
    api.get<{ history: SchedulerHistoryEntry[] }>('/admin/scheduler/history', { params: { limit } }),

  // Pause a queue
  pauseQueue: (category: string) =>
    api.post<{ status: string; category: string }>(`/admin/scheduler/pause/${category}`),

  // Resume a queue
  resumeQueue: (category: string) =>
    api.post<{ status: string; category: string }>(`/admin/scheduler/resume/${category}`),

  // Record activity (resets idle timer)
  recordActivity: () =>
    api.post<{ status: string; is_idle: boolean }>('/admin/scheduler/activity'),

  // Get system tasks configuration
  getSystemTasks: () =>
    api.get<{ enabled: boolean; tasks: Record<string, SchedulerTaskConfig & { registered: boolean; status: string | null; last_run: string | null; next_run: string | null; run_count: number }> }>('/admin/scheduler/tasks/system'),

  // Manually trigger a task
  triggerTask: (taskId: string) =>
    api.post<{ status: string; task_id: string; message: string }>(`/admin/scheduler/run/${taskId}`),

  // Approvals - unified "what needs attention?"
  getApprovals: (type?: string) =>
    api.get<{
      approvals: ApprovalItem[];
      count: number;
      counts_by_type: Record<string, number>;
    }>('/admin/scheduler/approvals', { params: type ? { type } : undefined }),

  getApprovalCounts: () =>
    api.get<Record<string, number>>('/admin/scheduler/approvals/counts'),

  approveItem: (approvalType: string, sourceId: string, approvedBy: string = 'admin') =>
    api.post<{ success: boolean; message?: string; error?: string }>(
      `/admin/scheduler/approvals/${approvalType}/${sourceId}/approve`,
      { approved_by: approvedBy }
    ),

  rejectItem: (approvalType: string, sourceId: string, rejectedBy: string = 'admin', reason: string = '') =>
    api.post<{ success: boolean; message?: string; error?: string }>(
      `/admin/scheduler/approvals/${approvalType}/${sourceId}/reject`,
      { rejected_by: rejectedBy, reason }
    ),
};

// Approval types
export interface ApprovalItem {
  approval_id: string;
  type: string;
  title: string;
  description: string;
  source_id: string;
  created_at: string;
  created_by: string;
  priority: string;
  source_data: Record<string, unknown>;
}

export const stateApi = {
  // Get current global state
  getCurrentState: () =>
    api.get<GlobalState>('/admin/state'),

  // Get state events (event stream)
  getEvents: (params?: {
    event_type?: string;
    limit?: number;
    since_hours?: number;
  }) => api.get<{
    daemon_id: string;
    events: StateEvent[];
    total: number;
  }>('/admin/state/events', { params }),

  // Get emotional arc for visualization
  getEmotionalArc: (hours: number = 24) =>
    api.get<{
      daemon_id: string;
      hours: number;
      arc_points: EmotionalArcPoint[];
      current_state: EmotionalState;
      total_deltas: number;
    }>('/admin/state/emotional-arc', { params: { hours } }),

  // Get activity timeline
  getActivityTimeline: (hours: number = 24) =>
    api.get<{
      daemon_id: string;
      hours: number;
      timeline: ActivityTimelineEvent[];
      total_events: number;
    }>('/admin/state/activity-timeline', { params: { hours } }),

  // Get relational state for a specific user
  getRelationalState: (userId: string) =>
    api.get<{
      daemon_id: string;
      user_id: string;
      exists: boolean;
      state: RelationalState | null;
    }>(`/admin/state/relational/${userId}`),
};
