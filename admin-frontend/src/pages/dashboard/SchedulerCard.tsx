/**
 * SchedulerCard - Scheduler status and tasks (Row 3, Column 1)
 */
import type { SchedulerStatus } from '../../api/client';

interface SchedulerCardProps {
  data: SchedulerStatus | undefined;
  isLoading: boolean;
}

// Format relative time (past)
function formatRelative(isoString: string | null): string {
  if (!isoString) return 'never';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return date.toLocaleDateString();
}

// Format relative time (future)
function formatNext(isoString: string | null): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 0) return 'overdue';
  if (diffMin < 1) return 'now';
  if (diffMin < 60) return `in ${diffMin}m`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `in ${diffHr}h`;
  return date.toLocaleDateString();
}

export function SchedulerCard({ data }: SchedulerCardProps) {
  if (!data) {
    return (
      <div className="dashboard-card scheduler-card scheduler-disabled">
        <h3>Scheduler</h3>
        <div className="scheduler-status-message">
          <span className="status-icon">~</span>
          <span>Not initialized</span>
        </div>
      </div>
    );
  }

  if (!data.enabled) {
    return (
      <div className="dashboard-card scheduler-card scheduler-disabled">
        <h3>Scheduler</h3>
        <div className="scheduler-status-message">
          <span className="status-icon">~</span>
          <span>{data.message || 'Disabled'}</span>
        </div>
      </div>
    );
  }

  const systemTasks = data.system_tasks || {};
  const budget = data.budget;

  return (
    <div className="dashboard-card scheduler-card">
      <h3>
        Scheduler
        <span className={`scheduler-indicator ${data.running ? 'running' : 'stopped'}`}>
          {data.running ? '●' : '○'}
        </span>
      </h3>

      {/* Status bar */}
      <div className="scheduler-status-bar">
        <span className={`idle-status ${data.is_idle ? 'idle' : 'active'}`}>
          {data.is_idle ? 'Idle' : 'Active'}
        </span>
        {budget && (
          <span className="budget-status">
            ${budget.total_spent.toFixed(2)} / ${budget.daily_budget_usd.toFixed(2)}
          </span>
        )}
      </div>

      {/* System Tasks */}
      <div className="scheduler-tasks">
        <h4>System Tasks</h4>
        <div className="task-list">
          {Object.entries(systemTasks).map(([taskId, task]) => (
            <div key={taskId} className={`task-item ${task.status?.toLowerCase() || 'pending'}`}>
              <div className="task-name">{task.name.replace(/_/g, ' ')}</div>
              <div className="task-timing">
                <span className="task-last">{formatRelative(task.last_run)}</span>
                <span className="task-separator">→</span>
                <span className="task-next">{formatNext(task.next_run)}</span>
              </div>
            </div>
          ))}
          {Object.keys(systemTasks).length === 0 && (
            <div className="no-tasks">No tasks registered</div>
          )}
        </div>
      </div>

      {/* Budget breakdown */}
      {budget && (
        <div className="scheduler-budget">
          <h4>Budget</h4>
          <div className="budget-bar">
            <div
              className="budget-used"
              style={{ width: `${Math.min(100, (budget.total_spent / budget.daily_budget_usd) * 100)}%` }}
            />
          </div>
          <div className="budget-remaining">
            ${budget.total_remaining.toFixed(2)} remaining
          </div>
        </div>
      )}
    </div>
  );
}
