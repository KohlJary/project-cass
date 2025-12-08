import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

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

// User endpoints
export const usersApi = {
  getAll: () => api.get('/admin/users'),
  getById: (id: string) => api.get(`/admin/users/${id}`),
  getObservations: (id: string) => api.get(`/admin/users/${id}/observations`),
  updateProfile: (id: string, data: unknown) =>
    api.patch(`/admin/users/${id}`, data),
  setAdminStatus: (id: string, isAdmin: boolean) =>
    api.post(`/admin/users/${id}/admin-status`, { is_admin: isAdmin }),
  setPassword: (id: string, password: string) =>
    api.post(`/admin/users/${id}/set-password`, { password }),
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
};

// System endpoints
export const systemApi = {
  getHealth: () => api.get('/admin/system/health'),
  getStats: () => api.get('/admin/system/stats'),
  getActiveSessions: () => api.get('/admin/system/sessions'),
};

// Self-model endpoints
export const selfModelApi = {
  get: () => api.get('/admin/self-model'),
  getGrowthEdges: () => api.get('/admin/self-model/growth-edges'),
  getOpenQuestions: () => api.get('/admin/self-model/questions'),
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

// Research/ARS endpoints
export const researchApi = {
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
  getProposal: (id: string) => api.get(`/wiki/research/proposals/${id}`),
  generateProposal: (params?: { theme?: string; max_tasks?: number }) =>
    api.post('/wiki/research/proposals/generate', null, { params }),
  approveProposal: (id: string) => api.post(`/wiki/research/proposals/${id}/approve`),
  rejectProposal: (id: string, reason?: string) =>
    api.post(`/wiki/research/proposals/${id}/reject`, null, { params: { reason } }),
  executeProposal: (id: string) => api.post(`/wiki/research/proposals/${id}/execute`),
  deleteProposal: (id: string) => api.delete(`/wiki/research/proposals/${id}`),
  getProposalMarkdown: (id: string) => api.get(`/wiki/research/proposals/${id}/markdown`),
};
