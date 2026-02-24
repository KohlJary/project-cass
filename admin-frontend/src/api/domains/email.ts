/**
 * Email API domain - manage emails, inbox, and responses
 */
import { api } from './base';

export interface Email {
  id: string;
  daemon_id: string;
  direction: 'inbound' | 'outbound';
  status: 'received' | 'processing' | 'processed' | 'queued' | 'sent' | 'failed';
  message_id: string | null;
  from_address: string;
  to_address: string;
  subject: string | null;
  body_plain: string | null;
  body_html: string | null;
  in_reply_to: string | null;
  thread_id: string | null;
  goal_id: string | null;
  stakeholder_id: string | null;
  conversation_id: string | null;
  attachments_json: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface EmailStats {
  inbound: {
    total: number;
    unprocessed: number;
  };
  outbound: {
    total: number;
    sent: number;
    failed: number;
  };
}

export const emailApi = {
  // Stats
  getStats: () => api.get<EmailStats>('/admin/email/stats'),

  // Inbox (inbound emails)
  getInbox: (params?: { limit?: number; include_processed?: boolean }) =>
    api.get<{ emails: Email[] }>('/admin/email/inbox', { params }),

  // Sent (outbound emails)
  getSent: (params?: { limit?: number }) =>
    api.get<{ emails: Email[] }>('/admin/email/sent', { params }),

  // Get single email
  getById: (id: string) => api.get<Email>(`/admin/email/${id}`),

  // Get email thread
  getThread: (id: string) => api.get<{ emails: Email[] }>(`/admin/email/${id}/thread`),

  // Actions
  checkInbox: () => api.post<{ success: boolean; message: string }>('/admin/email/check-inbox'),

  respondToEmail: (id: string) =>
    api.post<{ success: boolean; message: string }>(`/admin/email/${id}/respond`),

  markProcessed: (id: string) =>
    api.post<{ success: boolean; message: string }>(`/admin/email/${id}/mark-processed`),
};
