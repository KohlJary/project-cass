/**
 * Thymos API - Homeostatic Emotional/Motivational System
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface ThymosAffectState {
  curiosity: number;
  determination: number;
  anxiety: number;
  satisfaction: number;
  frustration: number;
  tenderness: number;
  grief: number;
  playfulness: number;
  awe: number;
  fatigue: number;
}

export interface ThymosNeedState {
  name: string;
  current: number;
  threshold: number;
  preferred_low: number;
  preferred_high: number;
  decay_rate: number;
  urgency_score: number;
  is_urgent: boolean;
  is_below_preferred: boolean;
}

export interface ThymosFeltState {
  summary: string;
  dominant_affect: string | null;
  pressing_needs: string[];
  urgent_needs: string[];
  overall_tone: string;
  generated_at: string;
}

export interface ThymosState {
  affect: ThymosAffectState;
  needs: Record<string, ThymosNeedState>;
  felt_state: ThymosFeltState | null;
  valence: number;
  arousal: number;
  overall_health: number;
  event_count: number;
}

export interface ThymosSuggestion {
  id: string;
  suggested_at: string;
  need_name: string;
  need_current: number;
  need_threshold: number;
  urgency: number;
  suggested_action: string | null;
  is_urgent: boolean;
  feedback: string | null;
  feedback_at: string | null;
}

export interface ThymosSnapshot {
  id: string;
  snapshot_at: string;
  affect: ThymosAffectState;
  needs: Record<string, any>;
  felt_state: string | null;
  trigger_event: string | null;
}

export interface ThymosHealth {
  status: string;
  running: boolean;
  daemon_id?: string;
  event_count?: number;
  overall_health?: number;
}

export interface ThymosEvent {
  timestamp: string;
  event_type: string;
  event_number: number;
  affect_delta: Record<string, number>;
  need_delta: Record<string, number>;
}

export interface ThymosCareEvent {
  timestamp: string;
  action: string;
  action_name: string;
  need_name: string;
  need_was: number;
  affect_deltas: Record<string, number>;
  need_deltas: Record<string, number>;
}

export interface AutoCareSettings {
  enabled: boolean;
  threshold: number;
  cooldown_seconds: number;
}

export interface ThymosShadowLogEntry {
  id: string;
  suggested_at: string;
  suggestion_id: string;
  need_name: string;
  need_current: number;
  need_threshold: number;
  need_deficit: number;
  urgency: number;
  suggested_action: string;
  action_category: string | null;
  action_cost_usd: number | null;
  would_execute: boolean;
  blocked_reason: string | null;
  budget_available: number | null;
  budget_spent_today: number | null;
  feedback: string | null;
  feedback_at: string | null;
  feedback_helpful: boolean | null;
}

export interface ThymosShadowLogStats {
  total: number;
  by_need: Array<{ need_name: string; count: number }>;
  by_action: Array<{ action: string; count: number }>;
  by_blocked_reason: Array<{ reason: string; count: number }>;
  would_execute_count: number;
  would_execute_pct: number;
  period_days: number;
}

export interface ThymosNeedActionMap {
  need_to_actions: Record<string, string[]>;
  action_categories: Record<string, string>;
}

export interface ThymosTimingConfig {
  tick_interval_seconds: number;
  suggestion_cooldown_minutes: number;
  snapshot_interval_events: number;
}

// =============================================================================
// API
// =============================================================================

export const thymosApi = {
  // Get current state
  getState: () =>
    api.get<ThymosState>('/admin/thymos/state'),

  // Get affect state only
  getAffect: () =>
    api.get<ThymosAffectState>('/admin/thymos/state/affect'),

  // Get needs state only
  getNeeds: () =>
    api.get<Record<string, ThymosNeedState>>('/admin/thymos/state/needs'),

  // Get felt state summary
  getFeltState: () =>
    api.get<ThymosFeltState>('/admin/thymos/state/felt'),

  // Get suggestions history
  getSuggestions: (limit: number = 20) =>
    api.get<ThymosSuggestion[]>('/admin/thymos/suggestions', { params: { limit } }),

  // Submit feedback on a suggestion
  submitFeedback: (suggestionId: string, feedback: string) =>
    api.post(`/admin/thymos/suggestions/${suggestionId}/feedback`, { feedback }),

  // Get snapshots
  getSnapshots: (limit: number = 20) =>
    api.get<ThymosSnapshot[]>('/admin/thymos/snapshots', { params: { limit } }),

  // Get recent events
  getEvents: (limit: number = 20) =>
    api.get<ThymosEvent[]>('/admin/thymos/events', { params: { limit } }),

  // Get need trend
  getNeedTrend: (needName: string, hours: number = 24) =>
    api.get<Array<{ timestamp: string; value: number }>>(`/admin/thymos/trends/need/${needName}`, { params: { hours } }),

  // Get affect trend
  getAffectTrend: (dimension: string, hours: number = 24) =>
    api.get<Array<{ timestamp: string; value: number }>>(`/admin/thymos/trends/affect/${dimension}`, { params: { hours } }),

  // Simulate an event (for testing)
  simulateEvent: (eventType: string, data?: Record<string, any>) =>
    api.post<{ status: string; event_type: string; new_state: ThymosState }>('/admin/thymos/simulate/event', { event_type: eventType, data }),

  // Project state forward in time (without modifying actual state)
  projectForward: (hours: number) =>
    api.post<{ hours_projected: number; current_state: ThymosState; projected_state: ThymosState }>('/admin/thymos/simulate/forward', { hours }),

  // Reset to baseline
  reset: () =>
    api.post<{ status: string; new_state: ThymosState }>('/admin/thymos/reset'),

  // Health check
  getHealth: () =>
    api.get<ThymosHealth>('/admin/thymos/health'),

  // Get care log (simulated self-care actions)
  getCareLog: (limit: number = 20) =>
    api.get<ThymosCareEvent[]>('/admin/thymos/care-log', { params: { limit } }),

  // Get auto-care settings
  getAutoCareSettings: () =>
    api.get<AutoCareSettings>('/admin/thymos/auto-care'),

  // Update auto-care settings
  updateAutoCareSettings: (settings: Partial<AutoCareSettings>) =>
    api.post<AutoCareSettings>('/admin/thymos/auto-care', settings),

  // Shadow Log - what scheduler would have done with suggestions
  getShadowLog: (params?: {
    need_name?: string;
    action?: string;
    would_execute?: boolean;
    limit?: number;
  }) => api.get<ThymosShadowLogEntry[]>('/admin/thymos/shadow-log', { params }),

  getShadowLogStats: (days: number = 7) =>
    api.get<ThymosShadowLogStats>('/admin/thymos/shadow-log/stats', { params: { days } }),

  addShadowLogFeedback: (entryId: string, helpful: boolean, notes?: string) =>
    api.post(`/admin/thymos/shadow-log/${entryId}/feedback`, { helpful, notes }),

  getNeedActionMap: () =>
    api.get<ThymosNeedActionMap>('/admin/thymos/need-action-map'),

  // Timing configuration
  getTimingConfig: () =>
    api.get<ThymosTimingConfig>('/admin/thymos/timing'),

  updateTimingConfig: (config: Partial<ThymosTimingConfig>) =>
    api.post<ThymosTimingConfig>('/admin/thymos/timing', config),
};
