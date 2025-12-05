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
