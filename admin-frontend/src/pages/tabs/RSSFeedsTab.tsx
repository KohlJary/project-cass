/**
 * RSS Feeds Tab - Manage RSS feed subscriptions
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { rssApi, type RSSFeed } from '../../api/domains';
import './RSSFeedsTab.css';

// Feed categories
const CATEGORIES = [
  { value: '', label: 'No category' },
  { value: 'tech', label: 'Technology' },
  { value: 'ai', label: 'AI / ML' },
  { value: 'art', label: 'Art' },
  { value: 'news', label: 'News' },
  { value: 'science', label: 'Science' },
  { value: 'philosophy', label: 'Philosophy' },
  { value: 'other', label: 'Other' },
];

// Check intervals
const INTERVALS = [
  { value: 15, label: '15 minutes' },
  { value: 30, label: '30 minutes' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 360, label: '6 hours' },
  { value: 720, label: '12 hours' },
  { value: 1440, label: '24 hours' },
];

function AddFeedForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('');
  const [interval, setInterval] = useState(60);
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => rssApi.createFeed({
      url,
      title: title || undefined,
      category: category || undefined,
      check_interval_minutes: interval,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['rss-status'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to add feed');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      setError('URL is required');
      return;
    }
    setError(null);
    createMutation.mutate();
  };

  return (
    <div className="add-feed-overlay" onClick={onClose}>
      <form className="add-feed-form" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>Add RSS Feed</h3>

        {error && <div className="form-error">{error}</div>}

        <div className="form-field">
          <label htmlFor="url">Feed URL *</label>
          <input
            id="url"
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://example.com/feed.xml"
            autoFocus
          />
        </div>

        <div className="form-field">
          <label htmlFor="title">Title (optional)</label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Will be fetched from feed if empty"
          />
        </div>

        <div className="form-row">
          <div className="form-field">
            <label htmlFor="category">Category</label>
            <select id="category" value={category} onChange={e => setCategory(e.target.value)}>
              {CATEGORIES.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="interval">Check Interval</label>
            <select id="interval" value={interval} onChange={e => setInterval(Number(e.target.value))}>
              {INTERVALS.map(i => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Adding...' : 'Add Feed'}
          </button>
        </div>
      </form>
    </div>
  );
}

function FeedCard({ feed, onEdit }: { feed: RSSFeed; onEdit: (feed: RSSFeed) => void }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const checkMutation = useMutation({
    mutationFn: () => rssApi.checkFeed(feed.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['rss-status'] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: () => rssApi.updateFeed(feed.id, { active: !feed.active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['rss-status'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => rssApi.deleteFeed(feed.id, true),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['rss-status'] });
    },
  });

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
  };

  return (
    <div className={`feed-card ${!feed.active ? 'inactive' : ''} ${feed.error_count > 0 ? 'has-error' : ''}`}>
      <div className="feed-header" onClick={() => setExpanded(!expanded)}>
        <div className="feed-main">
          <h4 className="feed-title">{feed.title || feed.url}</h4>
          <div className="feed-meta">
            {feed.category && <span className="feed-category">{feed.category}</span>}
            <span className="feed-interval">Every {feed.check_interval_minutes}m</span>
            <span className="feed-checked">Checked {formatDate(feed.last_checked_at)}</span>
            {!feed.active && <span className="feed-inactive-badge">Inactive</span>}
            {feed.error_count > 0 && (
              <span className="feed-error-badge" title={feed.last_error || undefined}>
                {feed.error_count} error{feed.error_count > 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
        <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>
          {expanded ? '-' : '+'}
        </span>
      </div>

      {expanded && (
        <div className="feed-details">
          <div className="feed-url">
            <a href={feed.url} target="_blank" rel="noopener noreferrer">{feed.url}</a>
          </div>

          {feed.description && (
            <p className="feed-description">{feed.description}</p>
          )}

          {feed.last_error && (
            <div className="feed-last-error">
              <strong>Last error:</strong> {feed.last_error}
            </div>
          )}

          <div className="feed-stats">
            <span>Created: {new Date(feed.created_at).toLocaleDateString()}</span>
            {feed.last_item_at && (
              <span>Latest item: {formatDate(feed.last_item_at)}</span>
            )}
          </div>

          <div className="feed-actions">
            <button
              className="btn-small"
              onClick={(e) => { e.stopPropagation(); checkMutation.mutate(); }}
              disabled={checkMutation.isPending}
            >
              {checkMutation.isPending ? 'Checking...' : 'Check Now'}
            </button>
            <button
              className="btn-small"
              onClick={(e) => { e.stopPropagation(); onEdit(feed); }}
            >
              Edit
            </button>
            <button
              className="btn-small"
              onClick={(e) => { e.stopPropagation(); toggleMutation.mutate(); }}
              disabled={toggleMutation.isPending}
            >
              {feed.active ? 'Deactivate' : 'Activate'}
            </button>
            <button
              className="btn-small btn-danger"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`Delete feed "${feed.title || feed.url}"? This will also delete all items.`)) {
                  deleteMutation.mutate();
                }
              }}
              disabled={deleteMutation.isPending}
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EditFeedForm({ feed, onClose }: { feed: RSSFeed; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(feed.title || '');
  const [description, setDescription] = useState(feed.description || '');
  const [category, setCategory] = useState(feed.category || '');
  const [interval, setInterval] = useState(feed.check_interval_minutes);
  const [error, setError] = useState<string | null>(null);

  const updateMutation = useMutation({
    mutationFn: () => rssApi.updateFeed(feed.id, {
      title: title || undefined,
      description: description || undefined,
      category: category || undefined,
      check_interval_minutes: interval,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Failed to update feed');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    updateMutation.mutate();
  };

  return (
    <div className="add-feed-overlay" onClick={onClose}>
      <form className="add-feed-form" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>Edit Feed</h3>

        {error && <div className="form-error">{error}</div>}

        <div className="form-field">
          <label>URL</label>
          <input type="text" value={feed.url} disabled className="disabled-input" />
        </div>

        <div className="form-field">
          <label htmlFor="title">Title</label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
          />
        </div>

        <div className="form-field">
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={2}
          />
        </div>

        <div className="form-row">
          <div className="form-field">
            <label htmlFor="category">Category</label>
            <select id="category" value={category} onChange={e => setCategory(e.target.value)}>
              {CATEGORIES.map(c => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label htmlFor="interval">Check Interval</label>
            <select id="interval" value={interval} onChange={e => setInterval(Number(e.target.value))}>
              {INTERVALS.map(i => (
                <option key={i.value} value={i.value}>{i.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-actions">
          <button type="button" className="btn-cancel" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  );
}

function RecentItemsPanel({ feedId }: { feedId?: string }) {
  const { data: items, isLoading } = useQuery({
    queryKey: ['rss-items', feedId, 'recent'],
    queryFn: () => rssApi.listItems({ feed_id: feedId, limit: 20 }).then(r => r.data),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return <div className="loading-items">Loading recent items...</div>;
  }

  if (!items?.length) {
    return <div className="empty-items">No items yet</div>;
  }

  return (
    <div className="recent-items">
      {items.map(item => (
        <div key={item.id} className={`item-row ${item.processed ? 'processed' : 'unprocessed'}`}>
          <div className="item-main">
            <a href={item.link || '#'} target="_blank" rel="noopener noreferrer" className="item-title">
              {item.title || 'Untitled'}
            </a>
            <div className="item-meta">
              {item.author && <span className="item-author">{item.author}</span>}
              {item.published_at && (
                <span className="item-date">
                  {new Date(item.published_at).toLocaleDateString()}
                </span>
              )}
              {item.processed ? (
                <span className="item-status processed">Processed</span>
              ) : (
                <span className="item-status pending">Pending</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function RSSFeedsTab() {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingFeed, setEditingFeed] = useState<RSSFeed | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [selectedFeedId, _setSelectedFeedId] = useState<string | null>(null);

  // Fetch status
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['rss-status'],
    queryFn: () => rssApi.getStatus().then(r => r.data),
    refetchInterval: 30000,
  });

  // Fetch feeds
  const { data: feeds, isLoading: feedsLoading } = useQuery({
    queryKey: ['rss-feeds', showInactive],
    queryFn: () => rssApi.listFeeds({ active_only: !showInactive }).then(r => r.data),
    refetchInterval: 30000,
  });

  // Check all feeds mutation
  const checkAllMutation = useMutation({
    mutationFn: () => rssApi.checkAllFeeds(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rss-feeds'] });
      queryClient.invalidateQueries({ queryKey: ['rss-status'] });
      queryClient.invalidateQueries({ queryKey: ['rss-items'] });
    },
  });

  return (
    <div className="rss-feeds-tab">
      {/* Status bar */}
      <div className="rss-status-bar">
        {statusLoading ? (
          <span>Loading...</span>
        ) : status ? (
          <>
            <div className="status-item">
              <span className="status-value">{status.active_feeds}</span>
              <span className="status-label">Active Feeds</span>
            </div>
            <div className="status-item">
              <span className="status-value">{status.unprocessed_items}</span>
              <span className="status-label">Unprocessed</span>
            </div>
            {status.error_feeds > 0 && (
              <div className="status-item error">
                <span className="status-value">{status.error_feeds}</span>
                <span className="status-label">With Errors</span>
              </div>
            )}
          </>
        ) : null}

        <div className="status-actions">
          <button
            className="btn-secondary"
            onClick={() => checkAllMutation.mutate()}
            disabled={checkAllMutation.isPending}
          >
            {checkAllMutation.isPending ? 'Checking...' : 'Check All Feeds'}
          </button>
          <button className="btn-primary" onClick={() => setShowAddForm(true)}>
            + Add Feed
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="rss-filters">
        <label className="filter-checkbox">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={e => setShowInactive(e.target.checked)}
          />
          Show inactive feeds
        </label>
      </div>

      {/* Main content */}
      <div className="rss-content">
        {/* Feeds list */}
        <div className="feeds-panel">
          <h3>Subscriptions</h3>
          {feedsLoading ? (
            <div className="loading-feeds">Loading feeds...</div>
          ) : !feeds?.length ? (
            <div className="empty-feeds">
              <p>No RSS feeds yet.</p>
              <button className="btn-primary" onClick={() => setShowAddForm(true)}>
                Add your first feed
              </button>
            </div>
          ) : (
            <div className="feeds-list">
              {feeds.map(feed => (
                <FeedCard
                  key={feed.id}
                  feed={feed}
                  onEdit={setEditingFeed}
                />
              ))}
            </div>
          )}
        </div>

        {/* Recent items panel */}
        <div className="items-panel">
          <h3>Recent Items</h3>
          <RecentItemsPanel feedId={selectedFeedId || undefined} />
        </div>
      </div>

      {/* Modals */}
      {showAddForm && <AddFeedForm onClose={() => setShowAddForm(false)} />}
      {editingFeed && <EditFeedForm feed={editingFeed} onClose={() => setEditingFeed(null)} />}
    </div>
  );
}
