/**
 * Core API - Daemons, Auth, Users, System
 */
import { api } from './base';

// =============================================================================
// DAEMONS
// =============================================================================

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

// =============================================================================
// AUTH
// =============================================================================

export const authApi = {
  register: (data: { username: string; password: string; email?: string; registration_reason?: string }) =>
    api.post('/admin/auth/register', data),
  login: (username: string, password: string) =>
    api.post('/admin/auth/login', { username, password }),
  verify: () => api.get('/admin/auth/verify'),
  status: () => api.get('/admin/auth/status'),
};

// =============================================================================
// USERS
// =============================================================================

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

// =============================================================================
// SYSTEM
// =============================================================================

export const systemApi = {
  getHealth: () => api.get('/admin/system/health'),
  getStats: () => api.get('/admin/system/stats'),
  getActiveSessions: () => api.get('/admin/system/sessions'),
};
