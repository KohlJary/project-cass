/**
 * Outreach API - Drafts, Review Queue, Autonomy Progression
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface OutreachDraft {
  id: string;
  draft_type: string;
  status: string;
  title: string;
  content: string;
  recipient?: string;
  recipient_name?: string;
  subject?: string;
  emergence_type?: string;
  autonomy_level: string;
  review_history: Array<{
    reviewer: string;
    decision: string;
    feedback?: string;
    timestamp: string;
  }>;
  created_at: string;
  updated_at: string;
}

export interface TrackRecord {
  draft_type: string;
  total_reviews: number;
  approvals: number;
  rejections: number;
  approval_rate: number;
  min_reviews_needed: number;
  min_rate_needed: number;
  graduated: boolean;
  autonomy_level: string;
}

export interface OutreachStats {
  total_drafts: number;
  pending_review: number;
  sent_count: number;
  published_count: number;
  response_rate: number;
  autonomy_by_type: Record<string, string>;
}

// =============================================================================
// API
// =============================================================================

export const outreachApi = {
  // Get outreach statistics
  getStats: () =>
    api.get<OutreachStats>('/admin/outreach/stats'),

  // Get all track records (autonomy progression by type)
  getTrackRecords: () =>
    api.get<Record<string, TrackRecord>>('/admin/outreach/track-records'),

  // Get specific track record
  getTrackRecord: (draftType: string) =>
    api.get<TrackRecord>(`/admin/outreach/track-records/${draftType}`),

  // List drafts with optional filters
  listDrafts: (params?: { status?: string; draft_type?: string; limit?: number }) =>
    api.get<{ drafts: OutreachDraft[]; count: number }>('/admin/outreach/drafts', { params }),

  // Get single draft
  getDraft: (draftId: string) =>
    api.get<OutreachDraft>(`/admin/outreach/drafts/${draftId}`),

  // Review actions
  approveDraft: (draftId: string, feedback?: string) =>
    api.post(`/admin/outreach/drafts/${draftId}/approve`, { feedback }),

  rejectDraft: (draftId: string, feedback?: string) =>
    api.post(`/admin/outreach/drafts/${draftId}/reject`, { feedback }),

  requestRevision: (draftId: string, feedback?: string) =>
    api.post(`/admin/outreach/drafts/${draftId}/revision`, { feedback }),

  // Mark as sent/published (post-approval)
  markSent: (draftId: string) =>
    api.post(`/admin/outreach/drafts/${draftId}/sent`),

  markPublished: (draftId: string) =>
    api.post(`/admin/outreach/drafts/${draftId}/published`),
};
