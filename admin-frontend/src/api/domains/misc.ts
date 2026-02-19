/**
 * Miscellaneous APIs - Export, Schedules, GitHub, Usage, Files, Projects, etc.
 */
import { api, API_BASE } from './base';

// =============================================================================
// EXPORT/IMPORT
// =============================================================================

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
  // Import endpoints
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

// =============================================================================
// SCHEDULES
// =============================================================================

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

// =============================================================================
// GITHUB
// =============================================================================

export const githubApi = {
  getCurrent: () => api.get('/admin/github/metrics'),
  getStats: () => api.get('/admin/github/metrics/stats'),
  getHistory: (params?: { days?: number; repo?: string }) =>
    api.get('/admin/github/metrics/history', { params }),
  getTimeSeries: (metric: string, params?: { days?: number; repo?: string }) =>
    api.get(`/admin/github/metrics/timeseries/${metric}`, { params }),
  getAllTimeStats: () => api.get('/admin/github/metrics/alltime'),
  refresh: () => api.post('/admin/github/metrics/refresh'),
};

// =============================================================================
// USAGE
// =============================================================================

export const usageApi = {
  getRecords: (params?: { start_date?: string; end_date?: string; category?: string; provider?: string; limit?: number }) =>
    api.get('/admin/usage', { params }),
  getSummary: (params?: { start_date?: string; end_date?: string }) =>
    api.get('/admin/usage/summary', { params }),
  getTimeSeries: (params?: { metric?: string; days?: number; granularity?: string }) =>
    api.get('/admin/usage/timeseries', { params }),
};

// =============================================================================
// FILES
// =============================================================================

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

// =============================================================================
// PROJECTS
// =============================================================================

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

// =============================================================================
// ROADMAP
// =============================================================================

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

// =============================================================================
// RHYTHM
// =============================================================================

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

// =============================================================================
// SESSIONS
// =============================================================================

export const sessionsApi = {
  getSession: (sessionId: string, sessionType: string) =>
    api.get(`/admin/sessions/${sessionId}`, { params: { session_type: sessionType } }),
};

// =============================================================================
// SETTINGS
// =============================================================================

export const settingsApi = {
  getLLMProvider: () => api.get('/settings/llm-provider'),
  setLLMProvider: (provider: string) => api.post('/settings/llm-provider', { provider }),
};

// =============================================================================
// LLM CONFIGURATION
// =============================================================================

export interface ModelAssignment {
  provider: string;
  model_id: string;
  fallback_provider: string | null;
  fallback_model_id: string | null;
  metadata?: {
    name: string;
    description: string;
    priority: 'high' | 'medium' | 'low';
    frequency: string;
  };
}

export interface AvailableModel {
  provider: string;
  model_id: string;
  name: string;
  local: boolean;
  installed: boolean;
}

export const llmConfigApi = {
  getConfig: () => api.get<{
    assignments: Record<string, ModelAssignment>;
    available_models: AvailableModel[];
    call_site_metadata: Record<string, ModelAssignment['metadata']>;
  }>('/admin/llm-config'),

  setAssignment: (callSite: string, assignment: Omit<ModelAssignment, 'metadata'>) =>
    api.put(`/admin/llm-config/${callSite}`, assignment),

  resetToDefaults: () => api.post('/admin/llm-config/reset'),

  getAvailableModels: () => api.get<{ models: AvailableModel[] }>('/admin/llm-config/models'),
};

// =============================================================================
// DREAMS
// =============================================================================

export const dreamsApi = {
  getAll: (params?: { limit?: number }) =>
    api.get('/dreams', { params }),
  getById: (dreamId: string) =>
    api.get(`/dreams/${dreamId}`),
  getContext: (dreamId: string) =>
    api.get(`/dreams/${dreamId}/context`),
  addReflection: (dreamId: string, reflection: string, source: string = 'conversation') =>
    api.post(`/dreams/${dreamId}/reflect`, { reflection, source }),
  markIntegrated: (dreamId: string) =>
    api.post(`/dreams/${dreamId}/mark-integrated`),
  integrate: (dreamId: string, dryRun: boolean = false) =>
    api.post(`/dreams/${dreamId}/integrate`, { dry_run: dryRun }),
};

// =============================================================================
// FEEDBACK
// =============================================================================

export const feedbackApi = {
  submit: (data: { heard_from?: string; message?: string }) =>
    api.post('/admin/feedback', data),
  getAll: () => api.get('/admin/feedback'),
};

// =============================================================================
// GENESIS
// =============================================================================

export const genesisApi = {
  start: () => api.post('/admin/genesis/start'),
  getSession: (sessionId: string) => api.get(`/admin/genesis/${sessionId}`),
  sendMessage: (sessionId: string, message: string) =>
    api.post(`/admin/genesis/${sessionId}/message`, { message }),
  abandon: (sessionId: string) => api.post(`/admin/genesis/${sessionId}/abandon`),
  complete: (sessionId: string) => api.post(`/admin/genesis/${sessionId}/complete`),
  getActive: () => api.get('/admin/genesis/active'),
  getMyDaemons: () => api.get('/admin/daemons/mine'),
  importJson: (jsonData: object, mergeExisting?: boolean) =>
    api.post('/admin/daemons/import/genesis', { json_data: jsonData, merge_existing: mergeExisting }),
  previewImport: (jsonData: object) =>
    api.post('/admin/daemons/import/genesis/preview', { json_data: jsonData }),
};

// =============================================================================
// GEOCASS
// =============================================================================

export const geocassApi = {
  getConnections: () => api.get('/admin/geocass/connections'),
  addConnection: (data: {
    server_url: string;
    email: string;
    password: string;
    server_name?: string;
    set_as_default?: boolean;
  }) => api.post('/admin/geocass/connections', data),
  register: (data: {
    server_url: string;
    username: string;
    email: string;
    password: string;
    server_name?: string;
    set_as_default?: boolean;
  }) => api.post('/admin/geocass/register', data),
  checkAvailability: (data: {
    server_url: string;
    username: string;
    email: string;
  }) => api.post('/admin/geocass/check-availability', data),
  getConnection: (id: string) => api.get(`/admin/geocass/connections/${id}`),
  deleteConnection: (id: string) => api.delete(`/admin/geocass/connections/${id}`),
  setDefault: (id: string) => api.post(`/admin/geocass/connections/${id}/default`),
  sync: (daemonLabel: string, connectionId?: string) =>
    api.post(`/admin/geocass/sync/${daemonLabel}`, null, {
      params: connectionId ? { connection_id: connectionId } : undefined,
    }),
  syncAll: (daemonLabel: string) => api.post(`/admin/geocass/sync-all/${daemonLabel}`),
  removeFromGeoCass: (daemonLabel: string, connectionId?: string) =>
    api.delete(`/admin/geocass/sync/${daemonLabel}`, {
      params: connectionId ? { connection_id: connectionId } : undefined,
    }),
};

// =============================================================================
// HOMEPAGE
// =============================================================================

export const homepageApi = {
  getAll: () => api.get('/admin/homepage'),
  getHomepage: (daemonLabel: string) => api.get(`/admin/homepage/${daemonLabel}`),
  getPage: (daemonLabel: string, page: string = 'index') =>
    api.get(`/admin/homepage/${daemonLabel}/page/${page}`, { responseType: 'text' }),
  triggerReflection: (daemonLabel: string) =>
    api.post(`/admin/homepage/${daemonLabel}/reflect`),
  fillMissingPages: (daemonLabel: string, missingPages?: string[]) =>
    api.post(`/admin/homepage/${daemonLabel}/fill-missing`, { missing_pages: missingPages }),
  getAvailableArtifacts: (daemonLabel: string, limit?: number) =>
    api.get(`/admin/homepage/${daemonLabel}/artifacts`, { params: { limit } }),
  featureArtifact: (daemonLabel: string, type: string, id: string, title: string, excerpt: string) =>
    api.post(`/admin/homepage/${daemonLabel}/artifacts/feature`, { type, id, title, excerpt }),
  unfeatureArtifact: (daemonLabel: string, type: string, id: string) =>
    api.post(`/admin/homepage/${daemonLabel}/artifacts/unfeature`, { type, id }),
  generateShowcase: (daemonLabel: string) =>
    api.post(`/admin/homepage/${daemonLabel}/showcase/generate`),
  uploadAsset: (daemonLabel: string, file: File, description: string, altText?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('description', description);
    if (altText) formData.append('alt_text', altText);
    return api.post(`/admin/homepage/${daemonLabel}/asset`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  registerExternalAsset: (daemonLabel: string, filename: string, url: string, description?: string, altText?: string) =>
    api.post(`/admin/homepage/${daemonLabel}/asset/external`, {
      filename,
      url,
      description: description || '',
      alt_text: altText || '',
    }),
};

// =============================================================================
// ATTACHMENTS
// =============================================================================

export const attachmentsApi = {
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
  getUrl: (id: string) => `${API_BASE}/attachments/${id}`,
  delete: (id: string) => api.delete(`/attachments/${id}`),
};

// =============================================================================
// GALLERY
// =============================================================================

export interface GeneratedImage {
  id: string;
  daemon_id: string;
  prompt: string;
  negative_prompt?: string | null;
  style: string | null;
  purpose: string;
  context_id: string | null;
  path: string;
  url: string | null;
  width: number | null;
  height: number | null;
  generation_time_ms: number | null;
  seed?: number | null;
  created_at: string;
  // Iteration tracking fields
  parent_id?: string | null;
  iteration_number?: number;
  generation_type?: string;  // txt2img, img2img, variation, upscale, inpaint
  // Full params (only in detail view)
  params?: Record<string, unknown> | null;
  loras?: Array<{ name: string; strength: number; clip_strength: number }> | null;
}

export interface ImageRevisionsResponse {
  current_id: string;
  current_index: number;
  root_id: string;
  total_revisions: number;
  revisions: GeneratedImage[];
}

export const galleryApi = {
  list: (params?: { purpose?: string; style?: string; limit?: number; offset?: number }) =>
    api.get<{ images: GeneratedImage[]; total: number; limit: number; offset: number }>('/api/images', { params }),
  get: (id: string) => api.get<GeneratedImage>(`/api/images/${id}`),
  getRevisions: (id: string) => api.get<ImageRevisionsResponse>(`/api/images/${id}/revisions`),
  getUrl: (image: GeneratedImage) => image.url ? `${API_BASE}${image.url}` : null,
};

// =============================================================================
// PROMPT CONFIG
// =============================================================================

export const promptConfigApi = {
  list: (daemonId: string) =>
    api.get('/admin/prompt-configs', { params: { daemon_id: daemonId } }),
  getActive: (daemonId: string) =>
    api.get('/admin/prompt-configs/active', { params: { daemon_id: daemonId } }),
  get: (configId: string) =>
    api.get(`/admin/prompt-configs/${configId}`),
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
  delete: (configId: string) =>
    api.delete(`/admin/prompt-configs/${configId}`),
  activate: (configId: string) =>
    api.post(`/admin/prompt-configs/${configId}/activate`),
  duplicate: (configId: string, name?: string) =>
    api.post(`/admin/prompt-configs/${configId}/duplicate`, null, { params: { name } }),
  preview: (configId: string, daemonName?: string) =>
    api.get(`/admin/prompt-configs/${configId}/preview`, { params: { daemon_name: daemonName } }),
  getHistory: (configId: string) =>
    api.get(`/admin/prompt-configs/${configId}/history`),
  validate: (components: Record<string, unknown>) =>
    api.post('/admin/prompt-configs/validate', components),
  getTransitions: (daemonId: string, limit?: number) =>
    api.get('/admin/prompt-configs/transitions', { params: { daemon_id: daemonId, limit } }),
};
