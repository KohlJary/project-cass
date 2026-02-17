/**
 * Knowledge API - Wiki, Research, Goals
 */
import { api } from './base';

// =============================================================================
// WIKI
// =============================================================================

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

// =============================================================================
// RESEARCH
// =============================================================================

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

// Autonomous Research API
export const autonomousResearchApi = {
  getSessions: (params?: { limit?: number }) =>
    api.get('/admin/research/sessions', { params }),
  getStatus: () => api.get('/autonomous-research/status'),
  startSession: (data: { duration_minutes: number; focus: string; mode: string }) =>
    api.post('/autonomous-research/sessions', data),
  stopSession: () => api.post('/autonomous-research/stop'),
};

// =============================================================================
// GOALS
// =============================================================================

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

  // Unified Goals view (for Agency dashboard)
  getUnifiedGoals: (params?: { include_completed?: boolean; emergence_type?: string }) =>
    api.get('/admin/goals/unified', { params }),
};
