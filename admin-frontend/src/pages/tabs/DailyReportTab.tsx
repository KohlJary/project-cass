import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { stateApi } from '../../api/client';
import type { DailyReportCategory } from '../../api/client';
import './DailyReportTab.css';

// Category display with icon mapping
const categoryIcons: Record<string, string> = {
  scheduler: 'S',
  calendar: '@',
  conversation: '>',
  task: '#',
  goal: '*',
  memory: '~',
  attachment: '+',
  user: '&',
  project: '%',
  wiki: '=',
  session: '<',
  day_phase: '^',
  work_unit: '!',
  phase_queue: '|',
  day: 'D',
  peopledex: 'P',
  state: '~',
  other: '?',
};

const categoryLabels: Record<string, string> = {
  scheduler: 'Scheduler',
  calendar: 'Calendar',
  conversation: 'Conversations',
  task: 'Tasks',
  goal: 'Goals',
  memory: 'Memory',
  attachment: 'Attachments',
  user: 'Users',
  project: 'Projects',
  wiki: 'Wiki',
  session: 'Sessions',
  day_phase: 'Day Phases',
  work_unit: 'Work Units',
  phase_queue: 'Phase Queue',
  day: 'Daily Planning',
  peopledex: 'PeopleDex',
  state: 'State Changes',
  other: 'Other',
};

function CategoryCard({
  category,
  data,
  isExpanded,
  onToggle
}: {
  category: string;
  data: DailyReportCategory;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const icon = categoryIcons[category] || '?';
  const label = categoryLabels[category] || category;

  return (
    <div className={`category-card ${isExpanded ? 'expanded' : ''}`}>
      <div className="category-header" onClick={onToggle}>
        <span className="category-icon">{icon}</span>
        <span className="category-name">{label}</span>
        <span className="category-count">{data.total_events}</span>
        <span className="expand-icon">{isExpanded ? '-' : '+'}</span>
      </div>

      {isExpanded && (
        <div className="category-content">
          <div className="action-summary">
            {Object.entries(data.actions).map(([action, count]) => (
              <span key={action} className="action-badge">
                {action}: {count}
              </span>
            ))}
          </div>

          <div className="timeline">
            {data.timeline.map((event, idx) => (
              <div key={idx} className="timeline-event">
                <span className="event-time">{event.time}</span>
                <span className="event-action">{event.action}</span>
                {event.details && (
                  <span className="event-details">{event.details}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DatePicker({
  value,
  onChange
}: {
  value: string;
  onChange: (date: string) => void;
}) {
  const goToday = () => onChange(new Date().toISOString().split('T')[0]);
  const goPrev = () => {
    const d = new Date(value);
    d.setDate(d.getDate() - 1);
    onChange(d.toISOString().split('T')[0]);
  };
  const goNext = () => {
    const d = new Date(value);
    d.setDate(d.getDate() + 1);
    const today = new Date().toISOString().split('T')[0];
    const next = d.toISOString().split('T')[0];
    if (next <= today) onChange(next);
  };

  const isToday = value === new Date().toISOString().split('T')[0];

  return (
    <div className="date-picker">
      <button className="date-nav" onClick={goPrev}>&lt;</button>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        max={new Date().toISOString().split('T')[0]}
      />
      <button className="date-nav" onClick={goNext} disabled={isToday}>&gt;</button>
      {!isToday && (
        <button className="today-btn" onClick={goToday}>Today</button>
      )}
    </div>
  );
}

export function DailyReportTab() {
  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().split('T')[0]
  );
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());

  const { data: report, isLoading, error, refetch } = useQuery({
    queryKey: ['daily-report', selectedDate],
    queryFn: async () => {
      const response = await stateApi.getDailyReport(selectedDate);
      return response.data;
    },
  });

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  const expandAll = () => {
    if (report) {
      setExpandedCategories(new Set(Object.keys(report.categories)));
    }
  };

  const collapseAll = () => {
    setExpandedCategories(new Set());
  };

  if (isLoading) {
    return (
      <div className="daily-report-tab loading">
        <div className="loading-spinner">Loading report...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="daily-report-tab error">
        <div className="error-message">Failed to load report: {String(error)}</div>
        <button className="retry-btn" onClick={() => refetch()}>Retry</button>
      </div>
    );
  }

  return (
    <div className="daily-report-tab">
      <div className="report-header">
        <h2>Daily Activity Report</h2>
        <p className="subtitle">Comprehensive view of Cass's activity for a given day</p>

        <div className="header-controls">
          <DatePicker value={selectedDate} onChange={setSelectedDate} />
          <div className="expand-controls">
            <button onClick={expandAll}>Expand All</button>
            <button onClick={collapseAll}>Collapse All</button>
          </div>
        </div>
      </div>

      {report && (
        <>
          <div className="summary-section">
            <div className="summary-stat">
              <span className="stat-value">{report.summary.total_events}</span>
              <span className="stat-label">Total Events</span>
            </div>
            <div className="summary-stat">
              <span className="stat-value">{report.summary.categories_active}</span>
              <span className="stat-label">Active Categories</span>
            </div>
            <div className="summary-stat">
              <span className="stat-value">{report.summary.active_hours.length}</span>
              <span className="stat-label">Active Hours</span>
            </div>
            {report.summary.busiest_category && (
              <div className="summary-stat">
                <span className="stat-value">
                  {categoryLabels[report.summary.busiest_category] || report.summary.busiest_category}
                </span>
                <span className="stat-label">Busiest Category</span>
              </div>
            )}
          </div>

          <div className="hours-bar">
            <span className="hours-label">Active hours:</span>
            <div className="hours-grid">
              {Array.from({ length: 24 }, (_, i) => {
                const hour = i.toString().padStart(2, '0');
                const isActive = report.summary.active_hours.includes(hour);
                return (
                  <div
                    key={hour}
                    className={`hour-block ${isActive ? 'active' : ''}`}
                    title={`${hour}:00`}
                  />
                );
              })}
            </div>
          </div>

          <div className="categories-grid">
            {report.category_order.map((category) => (
              <CategoryCard
                key={category}
                category={category}
                data={report.categories[category]}
                isExpanded={expandedCategories.has(category)}
                onToggle={() => toggleCategory(category)}
              />
            ))}
          </div>

          {report.summary.total_events === 0 && (
            <div className="no-activity">
              <p>No activity recorded for this date.</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
