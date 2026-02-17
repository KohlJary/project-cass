/**
 * Self-Model API - Self-model, Sentience, Development
 */
import { api } from './base';

// =============================================================================
// SELF MODEL
// =============================================================================

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

// =============================================================================
// SENTIENCE
// =============================================================================

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

// =============================================================================
// DEVELOPMENT
// =============================================================================

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
