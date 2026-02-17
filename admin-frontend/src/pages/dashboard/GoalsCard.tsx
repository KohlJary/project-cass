/**
 * GoalsCard - Goals overview (Column 3)
 */
import type { DashboardData } from '../../api/graphql';

interface GoalsCardProps {
  data: DashboardData;
}

export function GoalsCard({ data }: GoalsCardProps) {
  const { stats, byType } = data.goals;

  const hasGoals = stats.total > 0;

  return (
    <div className="dashboard-card goals-card">
      <h3>Goals</h3>

      {!hasGoals ? (
        <div className="no-goals">
          <div className="no-goals-icon">~</div>
          <p>No goals defined yet</p>
          <p className="no-goals-hint">Cass can propose goals autonomously</p>
        </div>
      ) : (
        <>
          <div className="goals-summary">
            <div className="goal-stat primary">
              <span className="goal-count">{stats.active}</span>
              <span className="goal-label">Active</span>
            </div>
            <div className="goal-stat">
              <span className="goal-count">{stats.blocked}</span>
              <span className="goal-label">Blocked</span>
            </div>
            <div className="goal-stat">
              <span className="goal-count">{stats.pendingApproval}</span>
              <span className="goal-label">Pending</span>
            </div>
          </div>

          <div className="goals-section">
            <h4>By Type</h4>
            <div className="goal-types">
              {byType.work > 0 && <span className="goal-type">Work: {byType.work}</span>}
              {byType.learning > 0 && <span className="goal-type">Learning: {byType.learning}</span>}
              {byType.research > 0 && <span className="goal-type">Research: {byType.research}</span>}
              {byType.growth > 0 && <span className="goal-type">Growth: {byType.growth}</span>}
              {byType.initiative > 0 && <span className="goal-type">Initiative: {byType.initiative}</span>}
            </div>
          </div>

          {stats.openCapabilityGaps > 0 && (
            <div className="capability-gaps">
              <span className="gaps-icon">!</span>
              <span>{stats.openCapabilityGaps} capability gaps</span>
            </div>
          )}

          <div className="goals-metrics">
            <div className="metric">
              <span className="metric-value">{stats.completionRate.toFixed(0)}%</span>
              <span className="metric-label">Completion</span>
            </div>
            <div className="metric">
              <span className="metric-value">{(stats.averageAlignment * 100).toFixed(0)}%</span>
              <span className="metric-label">Alignment</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
