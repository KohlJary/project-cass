/**
 * Chain API - Dynamic prompt chain composition
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

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

// =============================================================================
// API
// =============================================================================

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
