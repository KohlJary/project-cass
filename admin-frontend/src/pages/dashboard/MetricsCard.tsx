/**
 * MetricsCard - Token usage and GitHub metrics (Row 2, Column 1)
 */
import type { DashboardData } from '../../api/graphql';

interface MetricsCardProps {
  data: DashboardData;
}

export function MetricsCard({ data }: MetricsCardProps) {
  const { tokens, github } = data;

  return (
    <div className="dashboard-card metrics-card">
      <h3>Metrics</h3>

      <div className="metrics-section">
        <h4>Token Usage</h4>
        <div className="metrics-row">
          <div className="metric-item">
            <span className="metric-value">${tokens.todayCostUsd.toFixed(2)}</span>
            <span className="metric-label">Today</span>
          </div>
          <div className="metric-item">
            <span className="metric-value">${tokens.monthCostUsd.toFixed(2)}</span>
            <span className="metric-label">This Month</span>
          </div>
          <div className="metric-item">
            <span className="metric-value">{tokens.totalRequests}</span>
            <span className="metric-label">Total Requests</span>
          </div>
        </div>
      </div>

      <div className="metrics-section">
        <h4>GitHub</h4>
        <div className="metrics-row">
          <div className="metric-item">
            <span className="metric-value">{github.starsTotal}</span>
            <span className="metric-label">Stars</span>
          </div>
          <div className="metric-item">
            <span className="metric-value">{github.views14d}</span>
            <span className="metric-label">Views (14d)</span>
          </div>
          <div className="metric-item">
            <span className="metric-value">{github.clones14d}</span>
            <span className="metric-label">Clones (14d)</span>
          </div>
          <div className="metric-item">
            <span className="metric-value">{github.reposTracked}</span>
            <span className="metric-label">Repos</span>
          </div>
        </div>
      </div>
    </div>
  );
}
