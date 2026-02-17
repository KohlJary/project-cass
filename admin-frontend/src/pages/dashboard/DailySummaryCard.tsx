/**
 * DailySummaryCard - Today's summary (Row 2, Column 2)
 */
import type { DashboardData } from '../../api/graphql';

interface DailySummaryCardProps {
  data: DashboardData;
}

export function DailySummaryCard({ data }: DailySummaryCardProps) {
  const { dailySummary } = data;

  return (
    <div className="dashboard-card daily-summary-card">
      <h3>Today's Summary</h3>
      <div className="summary-date">{dailySummary.date}</div>

      <div className="summary-grid">
        <div className="summary-item">
          <span className="summary-icon">&gt;</span>
          <span className="summary-value">{dailySummary.conversationsCount}</span>
          <span className="summary-label">Conversations</span>
        </div>
        <div className="summary-item">
          <span className="summary-icon">~</span>
          <span className="summary-value">{dailySummary.messagesCount}</span>
          <span className="summary-label">Messages</span>
        </div>
        <div className="summary-item">
          <span className="summary-icon">$</span>
          <span className="summary-value">${dailySummary.tokenCostUsd.toFixed(2)}</span>
          <span className="summary-label">Token Cost</span>
        </div>
        <div className="summary-item">
          <span className="summary-icon">+</span>
          <span className="summary-value">{dailySummary.commits}</span>
          <span className="summary-label">Commits</span>
        </div>
      </div>

      {dailySummary.goalsCompleted > 0 && (
        <div className="summary-highlight">
          Completed {dailySummary.goalsCompleted} goal{dailySummary.goalsCompleted > 1 ? 's' : ''}
        </div>
      )}

      {dailySummary.journalsWritten > 0 && (
        <div className="summary-highlight">
          Wrote {dailySummary.journalsWritten} journal entr{dailySummary.journalsWritten > 1 ? 'ies' : 'y'}
        </div>
      )}

      <div className="current-status">
        <span className="status-label">Current:</span>
        <span className="status-value">{dailySummary.currentActivity}</span>
        {dailySummary.rhythmPhase && (
          <span className="status-phase">({dailySummary.rhythmPhase})</span>
        )}
      </div>
    </div>
  );
}
