/**
 * Narrative API - Threads and Questions
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface ThreadResponse {
  id: string;
  daemon_id: string;
  user_id: string | null;
  title: string;
  description: string | null;
  status: string;
  thread_type: string;
  importance: number;
  last_touched: string | null;
  resolution_summary: string | null;
  created_at: string;
}

export interface QuestionResponse {
  id: string;
  daemon_id: string;
  user_id: string | null;
  question: string;
  context: string | null;
  question_type: string;
  status: string;
  resolution: string | null;
  importance: number;
  source_conversation_id: string | null;
  source_thread_id: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface NarrativeStats {
  threads: {
    total: number;
    active: number;
    resolved: number;
    dormant: number;
    by_type: Record<string, number>;
  };
  questions: {
    open: number;
    by_type: Record<string, number>;
  };
}

// =============================================================================
// API
// =============================================================================

export const narrativeApi = {
  // Threads
  getThreads: (params?: {
    status?: string;
    thread_type?: string;
    user_id?: string;
    include_shared?: boolean;
    limit?: number;
  }) => api.get<{ threads: ThreadResponse[]; count: number }>('/admin/narrative/threads', { params }),

  getThread: (threadId: string) =>
    api.get<ThreadResponse & { linked_conversations: Array<{ conversation_id: string; contribution: string | null; linked_at: string }> }>(
      `/admin/narrative/threads/${threadId}`
    ),

  createThread: (data: {
    title: string;
    description?: string;
    thread_type?: string;
    user_id?: string;
    importance?: number;
  }) => api.post<ThreadResponse>('/admin/narrative/threads', data),

  updateThread: (threadId: string, data: {
    title?: string;
    description?: string;
    importance?: number;
    thread_type?: string;
  }) => api.patch<ThreadResponse>(`/admin/narrative/threads/${threadId}`, data),

  resolveThread: (threadId: string, resolution_summary: string) =>
    api.post<ThreadResponse>(`/admin/narrative/threads/${threadId}/resolve`, { resolution_summary }),

  reactivateThread: (threadId: string) =>
    api.post<ThreadResponse>(`/admin/narrative/threads/${threadId}/reactivate`),

  deleteThread: (threadId: string) =>
    api.delete(`/admin/narrative/threads/${threadId}`),

  // Questions
  getQuestions: (params?: {
    status?: string;
    question_type?: string;
    user_id?: string;
    include_shared?: boolean;
    limit?: number;
  }) => api.get<{ questions: QuestionResponse[]; count: number }>('/admin/narrative/questions', { params }),

  getQuestion: (questionId: string) =>
    api.get<QuestionResponse>(`/admin/narrative/questions/${questionId}`),

  createQuestion: (data: {
    question: string;
    context?: string;
    question_type?: string;
    user_id?: string;
    importance?: number;
  }) => api.post<QuestionResponse>('/admin/narrative/questions', data),

  resolveQuestion: (questionId: string, resolution: string) =>
    api.post<QuestionResponse>(`/admin/narrative/questions/${questionId}/resolve`, { resolution }),

  deleteQuestion: (questionId: string) =>
    api.delete(`/admin/narrative/questions/${questionId}`),

  // Stats
  getStats: (userId?: string) =>
    api.get<NarrativeStats>('/admin/narrative/stats', { params: userId ? { user_id: userId } : undefined }),

  // Extraction
  extractFromHistory: (source: 'journals' | 'conversations' | 'all' = 'all') =>
    api.post<{ status: string; source?: string; message?: string }>('/admin/narrative/extract', null, { params: { source } }),

  getExtractionStatus: () =>
    api.get<{
      running: boolean;
      last_run: string | null;
      results: {
        threads_created?: number;
        questions_created?: number;
        chunks_analyzed?: number;
        error?: string;
      } | null;
    }>('/admin/narrative/extract/status'),
};
