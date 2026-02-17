/**
 * State API - Global State Bus endpoints
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface EmotionalState {
  directedness: string | null;
  clarity: number;
  relational_presence: number;
  generativity: number;
  integration: number;
  curiosity: number;
  contentment: number;
  anticipation: number;
  concern: number;
  recognition: number;
  last_updated: string | null;
  last_updated_by: string | null;
}

export interface ActivityState {
  current_activity: string;
  active_session_id: string | null;
  active_user_id: string | null;
  rhythm_phase: string | null;
  rhythm_day_summary: string | null;
  active_threads: string[];
  active_questions: string[];
  last_activity_change: string | null;
}

export interface CoherenceState {
  local_coherence: number;
  pattern_coherence: number;
  recent_patterns: unknown[];
  sessions_today: number;
  emotional_arc_today: unknown[];
  last_coherence_check: string | null;
}

export interface RelationalState {
  user_id: string;
  activated_aspect: string | null;
  becoming_vector: string | null;
  relational_mode: string | null;
  revelation_level: number;
  baseline_revelation: number;
  last_updated: string | null;
}

export interface GlobalState {
  daemon_id: string;
  timestamp: string;
  emotional: EmotionalState;
  activity: ActivityState;
  coherence: CoherenceState;
  relational: Record<string, RelationalState>;
  context_snapshot: string;
}

export interface StateEvent {
  id: string;
  event_type: string;
  source: string;
  data: unknown;
  created_at: string;
}

export interface EmotionalArcPoint {
  timestamp: string;
  emotional_delta: Record<string, number>;
  source: string;
  reason: string;
}

export interface ActivityTimelineEvent {
  timestamp: string;
  event: string;
  activity_type?: string;
  activity?: string;
  session_id?: string;
}

export interface DailyReportTimelineEvent {
  time: string;
  action: string;
  details: string;
}

export interface DailyReportCategory {
  total_events: number;
  actions: Record<string, number>;
  first_event: string | null;
  last_event: string | null;
  timeline: DailyReportTimelineEvent[];
}

export interface DailyActivityReport {
  daemon_id: string;
  date: string;
  generated_at: string;
  summary: {
    total_events: number;
    categories_active: number;
    active_hours: string[];
    busiest_category: string | null;
  };
  categories: Record<string, DailyReportCategory>;
  category_order: string[];
}

// =============================================================================
// API
// =============================================================================

export const stateApi = {
  // Get current global state
  getCurrentState: () =>
    api.get<GlobalState>('/admin/state'),

  // Get state events (event stream)
  getEvents: (params?: {
    event_type?: string;
    limit?: number;
    since_hours?: number;
  }) => api.get<{
    daemon_id: string;
    events: StateEvent[];
    total: number;
  }>('/admin/state/events', { params }),

  // Get emotional arc for visualization
  getEmotionalArc: (hours: number = 24) =>
    api.get<{
      daemon_id: string;
      hours: number;
      arc_points: EmotionalArcPoint[];
      current_state: EmotionalState;
      total_deltas: number;
    }>('/admin/state/emotional-arc', { params: { hours } }),

  // Get activity timeline
  getActivityTimeline: (hours: number = 24) =>
    api.get<{
      daemon_id: string;
      hours: number;
      timeline: ActivityTimelineEvent[];
      total_events: number;
    }>('/admin/state/activity-timeline', { params: { hours } }),

  // Get relational state for a specific user
  getRelationalState: (userId: string) =>
    api.get<{
      daemon_id: string;
      user_id: string;
      exists: boolean;
      state: RelationalState | null;
    }>(`/admin/state/relational/${userId}`),

  // Get daily activity report
  getDailyReport: (reportDate?: string) =>
    api.get<DailyActivityReport>('/admin/state/daily-report', {
      params: reportDate ? { report_date: reportDate } : undefined
    }),
};
