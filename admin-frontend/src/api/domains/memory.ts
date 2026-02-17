/**
 * Memory API - Memory, Conversations, Journals
 */
import { api } from './base';

// =============================================================================
// MEMORY
// =============================================================================

export const memoryApi = {
  getAll: (params?: { type?: string; limit?: number; offset?: number }) =>
    api.get('/admin/memory', { params }),
  search: (query: string, limit?: number) =>
    api.get('/admin/memory/search', { params: { query, limit } }),
  getStats: () => api.get('/admin/memory/stats'),
  getVectors: (params?: { type?: string; limit?: number }) =>
    api.get('/admin/memory/vectors', { params }),
};

// =============================================================================
// JOURNALS
// =============================================================================

export const journalsApi = {
  getAll: (params?: { limit?: number }) => api.get('/admin/journals', { params }),
  getByDate: (date: string) => api.get(`/admin/journals/${date}`),
  getCalendar: (year: number, month: number) =>
    api.get('/admin/journals/calendar', { params: { year, month } }),
};

// =============================================================================
// CONVERSATIONS
// =============================================================================

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
