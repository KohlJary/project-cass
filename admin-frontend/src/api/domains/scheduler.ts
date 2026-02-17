/**
 * Scheduler API - Unified background task orchestration
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface SchedulerBudgetCategory {
  budget: number;
  spent: number;
  remaining: number;
  allocation_pct: number;
}

export interface SchedulerBudgetStatus {
  daily_budget_usd: number;
  emergency_reserve: number;
  last_reset: string | null;
  total_spent: number;
  total_remaining: number;
  by_category: Record<string, SchedulerBudgetCategory>;
}

export interface SchedulerSystemTask {
  name: string;
  status: string | null;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
}

export interface SchedulerQueueStatus {
  pending: number;
  running: number;
  paused: boolean;
  max_concurrent: number;
}

export interface SchedulerStatus {
  enabled: boolean;
  running?: boolean;
  is_idle?: boolean;
  last_activity?: string;
  system_tasks?: Record<string, SchedulerSystemTask>;
  queues?: Record<string, SchedulerQueueStatus>;
  budget?: SchedulerBudgetStatus;
  message?: string;
}

export interface SchedulerHistoryEntry {
  task_id: string;
  name: string;
  category: string;
  priority: number;
  status: string;
  started_at: string;
  completed_at: string;
  duration_seconds: number;
  estimated_cost_usd: number;
  actual_cost_usd: number;
  error: string | null;
}

export interface SchedulerTaskConfig {
  description: string;
  interval: string;
  estimated_cost: string;
  category: string;
}

export interface ApprovalItem {
  approval_id: string;
  type: string;
  title: string;
  description: string;
  source_id: string;
  created_at: string;
  created_by: string;
  priority: string;
  source_data: Record<string, unknown>;
}

// =============================================================================
// API
// =============================================================================

export const schedulerApi = {
  // Get full scheduler status
  getStatus: () =>
    api.get<SchedulerStatus>('/admin/scheduler/status'),

  // Get budget status
  getBudget: () =>
    api.get<SchedulerBudgetStatus>('/admin/scheduler/budget'),

  // Get task history
  getHistory: (limit: number = 50) =>
    api.get<{ history: SchedulerHistoryEntry[] }>('/admin/scheduler/history', { params: { limit } }),

  // Pause a queue
  pauseQueue: (category: string) =>
    api.post<{ status: string; category: string }>(`/admin/scheduler/pause/${category}`),

  // Resume a queue
  resumeQueue: (category: string) =>
    api.post<{ status: string; category: string }>(`/admin/scheduler/resume/${category}`),

  // Record activity (resets idle timer)
  recordActivity: () =>
    api.post<{ status: string; is_idle: boolean }>('/admin/scheduler/activity'),

  // Get system tasks configuration
  getSystemTasks: () =>
    api.get<{ enabled: boolean; tasks: Record<string, SchedulerTaskConfig & { registered: boolean; status: string | null; last_run: string | null; next_run: string | null; run_count: number }> }>('/admin/scheduler/tasks/system'),

  // Manually trigger a task
  triggerTask: (taskId: string) =>
    api.post<{ status: string; task_id: string; message: string }>(`/admin/scheduler/run/${taskId}`),

  // Approvals - unified "what needs attention?"
  getApprovals: (type?: string) =>
    api.get<{
      approvals: ApprovalItem[];
      count: number;
      counts_by_type: Record<string, number>;
    }>('/admin/scheduler/approvals', { params: type ? { type } : undefined }),

  getApprovalCounts: () =>
    api.get<Record<string, number>>('/admin/scheduler/approvals/counts'),

  approveItem: (approvalType: string, sourceId: string, approvedBy: string = 'admin') =>
    api.post<{ success: boolean; message?: string; error?: string }>(
      `/admin/scheduler/approvals/${approvalType}/${sourceId}/approve`,
      { approved_by: approvedBy }
    ),

  rejectItem: (approvalType: string, sourceId: string, rejectedBy: string = 'admin', reason: string = '') =>
    api.post<{ success: boolean; message?: string; error?: string }>(
      `/admin/scheduler/approvals/${approvalType}/${sourceId}/reject`,
      { rejected_by: rejectedBy, reason }
    ),
};
