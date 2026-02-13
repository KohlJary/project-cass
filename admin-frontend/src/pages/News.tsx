/**
 * News - World State Consumption Dashboard
 *
 * Shows articles Cass has read with full extracted insights.
 */

import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchConsumedArticles, fetchConsumedArticlesDates } from '../api/graphql';
import type { ConsumedArticle } from '../api/graphql';
import './News.css';

// Simple calendar component
function Calendar({
  selectedDate,
  onSelectDate,
  highlightedDates,
}: {
  selectedDate: string;
  onSelectDate: (date: string) => void;
  highlightedDates: Set<string>;
}) {
  const [viewDate, setViewDate] = useState(() => {
    const d = selectedDate ? new Date(selectedDate + 'T12:00:00') : new Date();
    return { year: d.getFullYear(), month: d.getMonth() };
  });

  const daysInMonth = new Date(viewDate.year, viewDate.month + 1, 0).getDate();
  const firstDayOfMonth = new Date(viewDate.year, viewDate.month, 1).getDay();

  const prevMonth = () => {
    setViewDate(prev => {
      if (prev.month === 0) return { year: prev.year - 1, month: 11 };
      return { ...prev, month: prev.month - 1 };
    });
  };

  const nextMonth = () => {
    setViewDate(prev => {
      if (prev.month === 11) return { year: prev.year + 1, month: 0 };
      return { ...prev, month: prev.month + 1 };
    });
  };

  const monthName = new Date(viewDate.year, viewDate.month).toLocaleString('default', { month: 'long' });

  const days = [];
  // Empty cells for days before the first of the month
  for (let i = 0; i < firstDayOfMonth; i++) {
    days.push(<div key={`empty-${i}`} className="calendar-day empty" />);
  }
  // Actual days
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${viewDate.year}-${String(viewDate.month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const isSelected = dateStr === selectedDate;
    const hasArticles = highlightedDates.has(dateStr);
    const isToday = dateStr === new Date().toISOString().split('T')[0];

    days.push(
      <button
        key={day}
        className={`calendar-day ${isSelected ? 'selected' : ''} ${hasArticles ? 'has-articles' : ''} ${isToday ? 'today' : ''}`}
        onClick={() => onSelectDate(dateStr)}
      >
        {day}
        {hasArticles && <span className="article-indicator" />}
      </button>
    );
  }

  return (
    <div className="calendar">
      <div className="calendar-header">
        <button className="calendar-nav" onClick={prevMonth}>&lt;</button>
        <span className="calendar-title">{monthName} {viewDate.year}</span>
        <button className="calendar-nav" onClick={nextMonth}>&gt;</button>
      </div>
      <div className="calendar-weekdays">
        {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map(d => (
          <div key={d} className="calendar-weekday">{d}</div>
        ))}
      </div>
      <div className="calendar-days">
        {days}
      </div>
    </div>
  );
}

// Article card with expanded insights
function ArticleCard({ article }: { article: ConsumedArticle }) {
  const [expanded, setExpanded] = useState(false);

  const totalInsights =
    article.observations.length +
    article.questions.length +
    article.opinions.length +
    article.growth_edges.length;

  return (
    <div className={`article-card ${expanded ? 'expanded' : ''}`}>
      <div className="article-header" onClick={() => setExpanded(!expanded)}>
        <div className="article-main">
          <h3 className="article-headline">{article.headline}</h3>
          <div className="article-meta">
            {article.source && <span className="article-source">{article.source}</span>}
            {article.author_name && (
              <span className="article-author">by {article.author_name}</span>
            )}
            {article.consumed_at && (
              <span className="article-time">
                {new Date(article.consumed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        </div>
        <div className="article-stats">
          <span className="insight-count" title="Total insights extracted">
            {totalInsights} insights
          </span>
          <span className={`expand-icon ${expanded ? 'expanded' : ''}`}>
            {expanded ? '−' : '+'}
          </span>
        </div>
      </div>

      {expanded && (
        <div className="article-details">
          {/* Link */}
          <a href={article.url} target="_blank" rel="noopener noreferrer" className="article-link">
            {article.url}
          </a>

          {/* Side-by-side layout */}
          <div className="article-content-grid">
            {/* Left: Summary */}
            <div className="summary-column">
              <h4>Summary</h4>
              <div className="summary-scroll">
                <p className="article-summary">{article.summary || 'No summary available'}</p>
              </div>
            </div>

            {/* Right: Insights */}
            <div className="insights-column">
              <h4>Extracted Insights</h4>
              <div className="insights-scroll">
                {/* Observations */}
                {article.observations.length > 0 && (
                  <div className="insight-section">
                    <h5>Observations ({article.observations.length})</h5>
                    <ul className="insight-list">
                      {article.observations.map((obs, i) => (
                        <li key={i} className="observation-item">
                          <span className="insight-text">{obs.text}</span>
                          <span className="insight-meta">
                            <span className={`category-badge ${obs.category.replace(/:/g, '-')}`}>
                              {obs.category}
                            </span>
                            <span className="confidence">{Math.round(obs.confidence * 100)}%</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Questions */}
                {article.questions.length > 0 && (
                  <div className="insight-section">
                    <h5>Questions ({article.questions.length})</h5>
                    <ul className="insight-list">
                      {article.questions.map((q, i) => (
                        <li key={i} className="question-item">
                          <span className="insight-text">{q.question}</span>
                          <span className="insight-meta">
                            <span className="type-badge">{q.question_type}</span>
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Opinions */}
                {article.opinions.length > 0 && (
                  <div className="insight-section">
                    <h5>Opinions ({article.opinions.length})</h5>
                    <ul className="insight-list">
                      {article.opinions.map((op, i) => (
                        <li key={i} className="opinion-item">
                          <span className="opinion-topic">{op.topic}</span>
                          <span className="opinion-position">{op.position}</span>
                          {op.reasoning && <p className="insight-reasoning">{op.reasoning}</p>}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Growth Edges */}
                {article.growth_edges.length > 0 && (
                  <div className="insight-section">
                    <h5>Growth Edges ({article.growth_edges.length})</h5>
                    <ul className="insight-list">
                      {article.growth_edges.map((ge, i) => (
                        <li key={i} className="growth-edge-item">
                          <span className="growth-area">{ge.area}</span>
                          <div className="growth-states">
                            {ge.current_state && (
                              <span className="current-state">Now: {ge.current_state}</span>
                            )}
                            {ge.desired_state && (
                              <span className="desired-state">Goal: {ge.desired_state}</span>
                            )}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Processing meta */}
          <div className="processing-meta">
            {article.tokens_used && <span>{article.tokens_used.toLocaleString()} tokens</span>}
            {article.processing_time_ms && <span>{(article.processing_time_ms / 1000).toFixed(1)}s</span>}
          </div>
        </div>
      )}
    </div>
  );
}

export function News() {
  const [searchParams, setSearchParams] = useSearchParams();
  const today = new Date().toISOString().split('T')[0];
  const [selectedDate, setSelectedDate] = useState(searchParams.get('date') || today);

  // Update URL when date changes
  useEffect(() => {
    setSearchParams({ date: selectedDate });
  }, [selectedDate, setSearchParams]);

  // Fetch articles for selected date
  const { data: articlesData, isLoading: articlesLoading } = useQuery({
    queryKey: ['consumedArticles', selectedDate],
    queryFn: () => fetchConsumedArticles(selectedDate),
  });

  // Fetch dates with articles for calendar highlighting
  const { data: datesWithArticles } = useQuery({
    queryKey: ['consumedArticlesDates'],
    queryFn: () => fetchConsumedArticlesDates(60),
  });

  const highlightedDates = new Set(datesWithArticles || []);

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
  };

  return (
    <div className="news-page">
      <div className="page-header">
        <h1>World State Consumption</h1>
        <p className="page-subtitle">Articles Cass has read and insights extracted</p>
      </div>

      <div className="news-layout">
        {/* Left: Calendar */}
        <div className="calendar-panel">
          <Calendar
            selectedDate={selectedDate}
            onSelectDate={setSelectedDate}
            highlightedDates={highlightedDates}
          />
          <div className="calendar-legend">
            <span className="legend-item">
              <span className="legend-dot has-articles" />
              Has articles
            </span>
          </div>
        </div>

        {/* Right: Articles */}
        <div className="articles-panel">
          <div className="articles-header">
            <h2>{formatDate(selectedDate)}</h2>
            {articlesData && (
              <span className="articles-count">
                {articlesData.total} article{articlesData.total !== 1 ? 's' : ''} read
              </span>
            )}
          </div>

          {articlesLoading ? (
            <div className="loading-state">Loading articles...</div>
          ) : articlesData?.articles.length === 0 ? (
            <div className="empty-state">
              <p>No articles read on this day</p>
            </div>
          ) : (
            <div className="articles-list">
              {articlesData?.articles.map(article => (
                <ArticleCard key={article.id} article={article} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
