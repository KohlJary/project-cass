import axios from 'axios';

// In dev with proxy, use relative URLs. In production, use VITE_API_URL or default.
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

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

  // Daemon export/import endpoints
  listSeedExports: () => api.get('/admin/daemons/exports/seeds'),
  exportDaemon: (daemonId: string) =>
    api.post(`/admin/daemons/${daemonId}/export`, {}, { responseType: 'blob' }),
  importDaemon: (file: File, daemonName?: string, skipEmbeddings?: boolean) => {
    const formData = new FormData();
    formData.append('file', file);
    if (daemonName) formData.append('daemon_name', daemonName);
    if (skipEmbeddings) formData.append('skip_embeddings', 'true');
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
  importSeed: (filename: string, daemonName?: string, skipEmbeddings?: boolean) =>
    api.post(`/admin/daemons/import/seed/${encodeURIComponent(filename)}`, null, {
      params: {
        daemon_name: daemonName,
        skip_embeddings: skipEmbeddings,
      },
    }),
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
  register: (data: { username: string; password: string }) =>
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
  getMessages: (id: string) => api.get(`/admin/conversations/${id}/messages`),
  getSummaries: (id: string) => api.get(`/admin/conversations/${id}/summaries`),
  getObservations: (id: string) => api.get(`/conversations/${id}/observations`),
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

  // Historical data
  getHistory: (params?: { days?: number; repo?: string }) =>
    api.get('/admin/github/metrics/history', { params }),

  // Time series for specific metric
  getTimeSeries: (metric: string, params?: { days?: number; repo?: string }) =>
    api.get(`/admin/github/metrics/timeseries/${metric}`, { params }),

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
