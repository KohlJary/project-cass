/**
 * DailyActivity - Comprehensive Daily Activity Dashboard
 *
 * Shows everything Cass did in a given day:
 * - Chronological timeline of all activity
 * - Categorized views (autonomous, conversations, self-model, etc.)
 * - Token usage and costs
 * - Emotional arc throughout the day
 */

import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  dailyActivityApi,
  type DailyActivityResponse,
  type ActivityItem,
  type CategorySummary,
} from '../api/domains';
import type { EmotionalArcPoint } from '../api/domains/daily-activity';
import './DailyActivity.css';

// Category metadata for display
const CATEGORY_META: Record<string, { label: string; icon: string; color: string }> = {
  autonomous: { label: 'Autonomous Actions', icon: '⚡', color: '#f0b429' },
  conversations: { label: 'Conversations', icon: '💬', color: '#4dabf7' },
  self_model: { label: 'Self-Model', icon: '🧠', color: '#da77f2' },
  world: { label: 'World Consumption', icon: '🌍', color: '#69db7c' },
  journals: { label: 'Journals & Dreams', icon: '📖', color: '#ffa94d' },
  emotional: { label: 'Emotional State', icon: '💜', color: '#e599f7' },
  creative: { label: 'Creative Output', icon: '🎨', color: '#ff6b6b' },
  social: { label: 'Social', icon: '👥', color: '#74c0fc' },
  resources: { label: 'Resources', icon: '📊', color: '#868e96' },
  outreach: { label: 'Outreach', icon: '📧', color: '#82c91e' },
};

// Source icons
const SOURCE_ICONS: Record<string, string> = {
  spells: '🪄',
  research_sessions: '🔬',
  solo_reflections: '🧘',
  work_items: '📋',
  messages: '💬',
  observations: '👁',
  growth_edges: '📈',
  opinions: '💭',
  questions: '❓',
  milestones: '🏁',
  articles: '📰',
  rss_items: '📡',
  wiki_updates: '📚',
  journals: '📓',
  dreams: '🌙',
  thymos_snapshots: '💗',
  state_events: '⚡',
  images: '🖼',
  art_studies: '🎨',
  user_observations: '👤',
  token_usage: '🔢',
  outreach: '✉️',
};

// Calendar component
function Calendar({
  selectedDate,
  onSelectDate,
  activityData,
}: {
  selectedDate: string;
  onSelectDate: (date: string) => void;
  activityData?: Record<string, number>;
}) {
  const [viewDate, setViewDate] = useState(() => {
    const d = selectedDate ? new Date(selectedDate + 'T12:00:00') : new Date();
    return { year: d.getFullYear(), month: d.getMonth() };
  });

  const daysInMonth = new Date(viewDate.year, viewDate.month + 1, 0).getDate();
  const firstDayOfMonth = new Date(viewDate.year, viewDate.month, 1).getDay();

  const prevMonth = () => {
    setViewDate((prev) => {
      if (prev.month === 0) return { year: prev.year - 1, month: 11 };
      return { ...prev, month: prev.month - 1 };
    });
  };

  const nextMonth = () => {
    setViewDate((prev) => {
      if (prev.month === 11) return { year: prev.year + 1, month: 0 };
      return { ...prev, month: prev.month + 1 };
    });
  };

  const monthName = new Date(viewDate.year, viewDate.month).toLocaleString('default', {
    month: 'long',
  });

  const days = [];
  for (let i = 0; i < firstDayOfMonth; i++) {
    days.push(<div key={`empty-${i}`} className="calendar-day empty" />);
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${viewDate.year}-${String(viewDate.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const isSelected = dateStr === selectedDate;
    const activityCount = activityData?.[dateStr] || 0;
    const isToday = dateStr === new Date().toISOString().split('T')[0];

    // Intensity based on activity level
    const intensity = activityCount > 50 ? 'high' : activityCount > 20 ? 'medium' : activityCount > 0 ? 'low' : '';

    days.push(
      <button
        key={day}
        className={`calendar-day ${isSelected ? 'selected' : ''} ${intensity} ${isToday ? 'today' : ''}`}
        onClick={() => onSelectDate(dateStr)}
        title={activityCount ? `${activityCount} events` : undefined}
      >
        {day}
      </button>
    );
  }

  return (
    <div className="calendar">
      <div className="calendar-header">
        <button className="calendar-nav" onClick={prevMonth}>
          &lt;
        </button>
        <span className="calendar-title">
          {monthName} {viewDate.year}
        </span>
        <button className="calendar-nav" onClick={nextMonth}>
          &gt;
        </button>
      </div>
      <div className="calendar-weekdays">
        {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((d) => (
          <div key={d} className="calendar-weekday">
            {d}
          </div>
        ))}
      </div>
      <div className="calendar-days">{days}</div>
    </div>
  );
}

// Format timestamp for display
function formatTime(timestamp: string): string {
  if (!timestamp) return '';
  try {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

// Activity item card
function ActivityItemCard({ item }: { item: ActivityItem }) {
  const [expanded, setExpanded] = useState(false);
  const icon = SOURCE_ICONS[item.source] || '📄';

  // Extract a readable title/summary from the data
  const getTitle = () => {
    const d = item.data;
    if (d.spell_name) return d.spell_name as string;
    if (d.headline) return d.headline as string;
    if (d.title) return d.title as string;
    if (d.topic) return d.topic as string;
    if (d.question) return (d.question as string).slice(0, 100);
    if (d.observation) return (d.observation as string).slice(0, 100);
    if (d.content) return (d.content as string).slice(0, 100) + '...';
    if (d.event_type) return d.event_type as string;
    if (d.felt_state) return `Feeling: ${d.felt_state}`;
    if (d.prompt) return (d.prompt as string).slice(0, 100);
    return item.source;
  };

  // Get status badge if applicable
  const getStatus = () => {
    const d = item.data;
    if (d.status) return d.status as string;
    return null;
  };

  const status = getStatus();

  return (
    <div className={`activity-item-card ${expanded ? 'expanded' : ''}`}>
      <div className="item-header" onClick={() => setExpanded(!expanded)}>
        <span className="item-icon">{icon}</span>
        <span className="item-time">{formatTime(item.timestamp)}</span>
        <span className="item-title">{getTitle()}</span>
        {status && <span className={`item-status status-${status}`}>{status}</span>}
        <span className="item-source">{item.source}</span>
        <span className="expand-toggle">{expanded ? '−' : '+'}</span>
      </div>
      {expanded && (
        <div className="item-details">
          <pre>{JSON.stringify(item.data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

// Timeline view
function TimelineView({ items }: { items: ActivityItem[] }) {
  if (!items.length) {
    return <div className="empty-timeline">No activity recorded for this day</div>;
  }

  // Group by hour
  const byHour = useMemo(() => {
    const groups: Record<string, ActivityItem[]> = {};
    items.forEach((item) => {
      const hour = item.timestamp ? new Date(item.timestamp).getHours() : 0;
      const key = String(hour).padStart(2, '0') + ':00';
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  return (
    <div className="timeline-view">
      {byHour.map(([hour, hourItems]) => (
        <div key={hour} className="timeline-hour-group">
          <div className="hour-label">{hour}</div>
          <div className="hour-items">
            {hourItems.map((item, i) => (
              <ActivityItemCard key={`${item.source}-${i}`} item={item} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Category section
function CategorySection({
  category,
  summary,
}: {
  category: string;
  summary: CategorySummary;
}) {
  const [expanded, setExpanded] = useState(false);
  const meta = CATEGORY_META[category] || { label: category, icon: '📁', color: '#868e96' };

  return (
    <div className="category-section" style={{ '--cat-color': meta.color } as React.CSSProperties}>
      <div className="category-header" onClick={() => setExpanded(!expanded)}>
        <span className="category-icon">{meta.icon}</span>
        <span className="category-label">{meta.label}</span>
        <span className="category-count">{summary.count}</span>
        <span className="expand-toggle">{expanded ? '−' : '+'}</span>
      </div>
      {expanded && (
        <div className="category-items">
          {summary.items.map((item, i) => (
            <div key={i} className="category-item">
              <pre>{JSON.stringify(item, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Emotional arc visualization
function EmotionalArc({ arc }: { arc: EmotionalArcPoint[] }) {
  if (!arc.length) return null;

  return (
    <div className="emotional-arc">
      <h3>Emotional Arc</h3>
      <div className="arc-points">
        {arc.map((point, i) => (
          <div key={i} className="arc-point">
            <span className="arc-time">{formatTime(point.timestamp)}</span>
            {point.felt_state && <span className="arc-state">{point.felt_state}</span>}
            {point.affect?.valence !== undefined && (
              <span
                className="arc-valence"
                style={{
                  backgroundColor: point.affect.valence > 0 ? '#69db7c' : '#ff6b6b',
                  opacity: Math.abs(point.affect.valence) * 0.5 + 0.5,
                }}
              >
                {(point.affect.valence * 100).toFixed(0)}%
              </span>
            )}
            {point.trigger && <span className="arc-trigger">{point.trigger}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// Token usage summary
function TokenSummaryPanel({ data }: { data: DailyActivityResponse['token_summary'] }) {
  if (!data) return null;

  return (
    <div className="token-summary-panel">
      <h3>Resource Usage</h3>
      <div className="token-totals">
        <div className="token-stat">
          <span className="stat-value">{data.total_tokens.toLocaleString()}</span>
          <span className="stat-label">Total Tokens</span>
        </div>
        <div className="token-stat">
          <span className="stat-value">${data.total_cost_usd.toFixed(4)}</span>
          <span className="stat-label">Est. Cost</span>
        </div>
      </div>
      {data.by_category.length > 0 && (
        <div className="token-breakdown">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Tokens</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.by_category.slice(0, 10).map((row, i) => (
                <tr key={i}>
                  <td>{row.category}</td>
                  <td>{row.provider}</td>
                  <td className="model-cell">{row.model}</td>
                  <td>{(row.input_tokens + row.output_tokens).toLocaleString()}</td>
                  <td>${row.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// Main component
export function DailyActivity() {
  const [searchParams, setSearchParams] = useSearchParams();
  const today = new Date().toISOString().split('T')[0];
  const [selectedDate, setSelectedDate] = useState(searchParams.get('date') || today);
  const [activeView, setActiveView] = useState<'timeline' | 'categories'>('timeline');

  // Update URL when date changes
  useEffect(() => {
    setSearchParams({ date: selectedDate });
  }, [selectedDate, setSearchParams]);

  // Fetch full activity for selected date
  const { data: activityData, isLoading } = useQuery({
    queryKey: ['dailyActivity', selectedDate],
    queryFn: () => dailyActivityApi.getDaily(selectedDate, { includeContent: false }),
  });

  // Fetch date range for calendar heatmap (last 60 days)
  const startDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - 60);
    return d.toISOString().split('T')[0];
  }, []);

  const { data: rangeData } = useQuery({
    queryKey: ['dailyActivityRange', startDate, today],
    queryFn: () => dailyActivityApi.getDateRangeSummary(startDate, today),
  });

  // Compute total events per day for calendar
  const activityByDate = useMemo(() => {
    if (!rangeData?.activity) return {};
    const result: Record<string, number> = {};
    Object.values(rangeData.activity).forEach((categoryMap) => {
      Object.entries(categoryMap).forEach(([date, count]) => {
        result[date] = (result[date] || 0) + count;
      });
    });
    return result;
  }, [rangeData]);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  // Calculate total events
  const totalEvents = activityData?.timeline.length || 0;
  const categoryCount = Object.keys(activityData?.categories || {}).length;

  return (
    <div className="daily-activity-page">
      <div className="page-header">
        <h1>Daily Activity</h1>
        <p className="page-subtitle">Everything Cass did in a day</p>
      </div>

      <div className="daily-layout">
        {/* Left sidebar: Calendar + Summary */}
        <div className="sidebar-panel">
          <Calendar
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
            activityData={activityByDate}
          />

          <div className="date-summary">
            <h3>{formatDate(selectedDate)}</h3>
            {activityData && (
              <div className="summary-stats">
                <div className="summary-stat">
                  <span className="stat-value">{totalEvents}</span>
                  <span className="stat-label">Events</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-value">{categoryCount}</span>
                  <span className="stat-label">Categories</span>
                </div>
              </div>
            )}
          </div>

          {/* Source totals */}
          {activityData?.totals && Object.keys(activityData.totals).length > 0 && (
            <div className="source-totals">
              <h4>By Source</h4>
              <div className="totals-list">
                {Object.entries(activityData.totals)
                  .filter(([, count]) => count > 0)
                  .sort(([, a], [, b]) => b - a)
                  .map(([source, count]) => (
                    <div key={source} className="total-row">
                      <span className="total-icon">{SOURCE_ICONS[source] || '📄'}</span>
                      <span className="total-label">{source}</span>
                      <span className="total-count">{count}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Token summary in sidebar */}
          {activityData?.token_summary && (
            <TokenSummaryPanel data={activityData.token_summary} />
          )}
        </div>

        {/* Main content area */}
        <div className="main-panel">
          {/* View toggle */}
          <div className="view-toggle">
            <button
              className={activeView === 'timeline' ? 'active' : ''}
              onClick={() => setActiveView('timeline')}
            >
              Timeline
            </button>
            <button
              className={activeView === 'categories' ? 'active' : ''}
              onClick={() => setActiveView('categories')}
            >
              By Category
            </button>
          </div>

          {isLoading ? (
            <div className="loading-state">Loading activity...</div>
          ) : activeView === 'timeline' ? (
            <TimelineView items={activityData?.timeline || []} />
          ) : (
            <div className="categories-view">
              {Object.entries(activityData?.categories || {})
                .sort(([, a], [, b]) => b.count - a.count)
                .map(([category, summary]) => (
                  <CategorySection key={category} category={category} summary={summary} />
                ))}
            </div>
          )}

          {/* Emotional arc */}
          {activityData?.emotional_arc && activityData.emotional_arc.length > 0 && (
            <EmotionalArc arc={activityData.emotional_arc} />
          )}
        </div>
      </div>
    </div>
  );
}
