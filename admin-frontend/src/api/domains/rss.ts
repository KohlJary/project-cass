/**
 * RSS Feed Management API
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface RSSFeed {
  id: string;
  url: string;
  title: string | null;
  description: string | null;
  category: string | null;
  check_interval_minutes: number;
  last_checked_at: string | null;
  last_item_at: string | null;
  error_count: number;
  last_error: string | null;
  active: boolean;
  created_at: string;
}

export interface RSSItem {
  id: string;
  feed_id: string;
  guid: string;
  title: string | null;
  link: string | null;
  summary: string | null;
  author: string | null;
  published_at: string | null;
  seen_at: string;
  processed: boolean;
  processed_at: string | null;
  skip_reason: string | null;
}

export interface RSSStatus {
  active_feeds: number;
  total_feeds: number;
  unprocessed_items: number;
  error_feeds: number;
}

export interface FeedCreateRequest {
  url: string;
  title?: string;
  description?: string;
  category?: string;
  check_interval_minutes?: number;
}

export interface FeedUpdateRequest {
  title?: string;
  description?: string;
  category?: string;
  check_interval_minutes?: number;
  active?: boolean;
}

export interface CheckResult {
  message: string;
  items_found: number;
  new_items: number;
}

export interface CheckAllResult {
  message: string;
  feeds_checked: number;
  new_items: number;
  results: Array<{
    feed_id: string;
    title: string;
    items_found?: number;
    new_items?: number;
    error?: string;
  }>;
}

// =============================================================================
// API
// =============================================================================

export const rssApi = {
  // Get overall RSS status
  getStatus: () =>
    api.get<RSSStatus>('/admin/rss/status'),

  // List all feeds
  listFeeds: (params?: { active_only?: boolean; category?: string }) =>
    api.get<RSSFeed[]>('/admin/rss/feeds', { params }),

  // Create a new feed subscription
  createFeed: (data: FeedCreateRequest) =>
    api.post<RSSFeed>('/admin/rss/feeds', data),

  // Get a specific feed
  getFeed: (feedId: string) =>
    api.get<RSSFeed>(`/admin/rss/feeds/${feedId}`),

  // Update a feed
  updateFeed: (feedId: string, data: FeedUpdateRequest) =>
    api.patch<RSSFeed>(`/admin/rss/feeds/${feedId}`, data),

  // Delete or deactivate a feed
  deleteFeed: (feedId: string, hard?: boolean) =>
    api.delete(`/admin/rss/feeds/${feedId}`, { params: { hard } }),

  // Manually check a specific feed
  checkFeed: (feedId: string) =>
    api.post<CheckResult>(`/admin/rss/feeds/${feedId}/check`),

  // Check all feeds due for refresh
  checkAllFeeds: () =>
    api.post<CheckAllResult>('/admin/rss/check-all'),

  // List items
  listItems: (params?: { feed_id?: string; processed?: boolean; limit?: number }) =>
    api.get<RSSItem[]>('/admin/rss/items', { params }),

  // Skip/mark an item as processed
  skipItem: (itemId: string, reason?: string) =>
    api.post(`/admin/rss/items/${itemId}/skip`, null, { params: { reason } }),
};
