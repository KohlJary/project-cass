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
};
