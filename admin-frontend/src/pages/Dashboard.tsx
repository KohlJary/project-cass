import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchDashboardData } from '../api/graphql';
import type { DashboardData, Approvals } from '../api/graphql';
import { schedulerApi } from '../api/client';
import type { SchedulerStatus } from '../api/client';
import { SchedulePanel } from '../components/SchedulePanel';
import { ChatWidget } from '../components/ChatWidget';
import { GoalsTab } from './tabs/GoalsTab';
import { AgencyTab } from './tabs/AgencyTab';
import './Dashboard.css';

// =============================================================================
// HELPER COMPONENTS
// =============================================================================

function EmotionalBar({ label, value, color }: { label: string; value: number; color: string }) {
  const percentage = Math.round(value * 100);
  return (
    <div className="emotional-bar">
      <div className="bar-label">{label}</div>
      <div className="bar-track">
        <div
          className="bar-fill"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
      <div className="bar-value">{percentage}%</div>
    </div>
  );
}

function StatCard({ icon, value, label }: { icon: string; value: string | number; label: string }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
}

// =============================================================================
// STATE CARD (Column 1)
// =============================================================================

function StateCard({ data }: { data: DashboardData }) {
  const { emotional, activity, coherence } = data.state;

  const activityIcons: Record<string, string> = {
    idle: '~',
    chat: '>',
    research: '*',
    reflection: '#',
    synthesis: '+',
    dreaming: '@',
    writing: '%',
  };

  return (
    <div className="dashboard-card state-card">
      <h3>Global State</h3>

      {/* Activity */}
      <div className="state-section">
        <div className="activity-display">
          <span className="activity-icon">{activityIcons[activity.current] || '?'}</span>
          <span className="activity-label">{activity.current}</span>
        </div>
        {activity.rhythmPhase && (
          <div className="rhythm-phase">Phase: {activity.rhythmPhase}</div>
        )}
      </div>

      {/* Emotional Dimensions */}
      <div className="state-section">
        <h4>Core Dimensions</h4>
        <EmotionalBar label="Clarity" value={emotional.clarity} color="#4CAF50" />
        <EmotionalBar label="Generativity" value={emotional.generativity} color="#9C27B0" />
        <EmotionalBar label="Integration" value={emotional.integration} color="#FF9800" />
      </div>

      {/* Valence */}
      <div className="state-section">
        <h4>Valence</h4>
        <EmotionalBar label="Curiosity" value={emotional.curiosity} color="#00BCD4" />
        <EmotionalBar label="Contentment" value={emotional.contentment} color="#8BC34A" />
        {emotional.concern > 0.1 && (
          <EmotionalBar label="Concern" value={emotional.concern} color="#F44336" />
        )}
      </div>

      {/* Coherence */}
      <div className="state-section">
        <h4>Coherence</h4>
        <div className="coherence-meters">
          <div className="coherence-item">
            <span className="coherence-label">Local</span>
            <span className="coherence-value">{Math.round(coherence.local * 100)}%</span>
          </div>
          <div className="coherence-item">
            <span className="coherence-label">Pattern</span>
            <span className="coherence-value">{Math.round(coherence.pattern * 100)}%</span>
          </div>
        </div>
        <div className="sessions-today">Sessions today: {coherence.sessionsToday}</div>
      </div>
    </div>
  );
}

// =============================================================================
// STATS CARD (Column 2 - existing dashboard content)
// =============================================================================

function StatsCard({ data }: { data: DashboardData }) {
  const { memory, conversations, selfModel } = data;

  return (
    <div className="dashboard-card stats-card">
      <h3>System Stats</h3>

      <div className="stats-grid">
        <StatCard icon="*" value={memory.totalEmbeddings} label="Memories" />
        <StatCard icon="#" value={memory.totalJournals} label="Journals" />
        <StatCard icon=">" value={conversations.totalConversations} label="Conversations" />
        <StatCard icon="@" value={selfModel.observations} label="Observations" />
      </div>

      <div className="stats-section">
        <h4>Self-Model Graph</h4>
        <div className="graph-stats">
          <span>{selfModel.totalNodes} nodes</span>
          <span className="separator">|</span>
          <span>{selfModel.totalEdges} edges</span>
        </div>
      </div>

      <div className="stats-section">
        <h4>Narrative</h4>
        <div className="narrative-stats">
          <div className="narrative-item">
            <span className="narrative-count">{memory.threadsActive}</span>
            <span className="narrative-label">Active Threads</span>
          </div>
          <div className="narrative-item">
            <span className="narrative-count">{memory.questionsOpen}</span>
            <span className="narrative-label">Open Questions</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// GOALS CARD (Column 3)
// =============================================================================

function GoalsCard({ data }: { data: DashboardData }) {
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

// =============================================================================
// METRICS CARD (Row 2, Column 1)
// =============================================================================

function MetricsCard({ data }: { data: DashboardData }) {
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

// =============================================================================
// DAILY SUMMARY CARD (Row 2, Column 2)
// =============================================================================

function DailySummaryCard({ data }: { data: DashboardData }) {
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

// =============================================================================
// SCHEDULER CARD (Row 3)
// =============================================================================

function SchedulerCard({ data }: { data: SchedulerStatus | undefined; isLoading: boolean }) {
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

  // Format relative time
  const formatRelative = (isoString: string | null): string => {
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
  };

  const formatNext = (isoString: string | null): string => {
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
  };

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

// =============================================================================
// APPROVALS CARD (Row 3, Column 2) - "What needs my attention?"
// =============================================================================

function ApprovalsCard({ data, onApprove, onReject }: {
  data: Approvals | undefined;
  onApprove: (type: string, sourceId: string) => void;
  onReject: (type: string, sourceId: string) => void;
}) {
  if (!data || data.count === 0) {
    return (
      <div className="dashboard-card approvals-card approvals-empty">
        <h3>Approvals</h3>
        <div className="empty-state">
          <span className="empty-icon">✓</span>
          <p>Nothing needs your attention</p>
        </div>
      </div>
    );
  }

  const priorityOrder: Record<string, number> = { high: 0, normal: 1, low: 2 };
  const typeIcons: Record<string, string> = {
    goal: '◎',
    research: '◈',
    action: '◆',
    user: '◉',
  };

  const sortedApprovals = [...data.items].sort((a, b) =>
    (priorityOrder[a.priority] ?? 1) - (priorityOrder[b.priority] ?? 1)
  );

  const formatRelativeTime = (isoString: string): string => {
    if (!isoString) return 'unknown';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDays = Math.floor(diffHr / 24);
    return `${diffDays}d ago`;
  };

  // Build counts from the counts object
  const countEntries = Object.entries(data.counts).filter(
    ([key, count]) => key !== 'total' && (count as number) > 0
  );

  return (
    <div className="dashboard-card approvals-card">
      <h3>
        Approvals
        <span className="approval-count">{data.count}</span>
      </h3>

      {/* Type counts */}
      {countEntries.length > 0 && (
        <div className="approval-type-counts">
          {countEntries.map(([type, count]) => (
            <span key={type} className={`type-badge ${type}`}>
              {typeIcons[type] || '◇'} {count as number} {type}
            </span>
          ))}
        </div>
      )}

      {/* Approval list */}
      <div className="approval-list">
        {sortedApprovals.slice(0, 5).map((item) => (
          <div key={item.approvalId} className={`approval-item priority-${item.priority}`}>
            <div className="approval-header">
              <span className="approval-type-icon">{typeIcons[item.approvalType] || '◇'}</span>
              <span className="approval-title">{item.title}</span>
              <span className="approval-time">{formatRelativeTime(item.createdAt)}</span>
            </div>
            {item.description && (
              <div className="approval-description">{item.description.slice(0, 80)}{item.description.length > 80 ? '...' : ''}</div>
            )}
            <div className="approval-actions">
              <button
                className="approve-btn"
                onClick={() => onApprove(item.approvalType, item.sourceId)}
                title="Approve"
              >
                ✓
              </button>
              <button
                className="reject-btn"
                onClick={() => onReject(item.approvalType, item.sourceId)}
                title="Reject"
              >
                ✗
              </button>
            </div>
          </div>
        ))}
        {data.count > 5 && (
          <div className="approval-more">
            +{data.count - 5} more items
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// OVERVIEW TAB CONTENT
// =============================================================================

function OverviewTabContent({
  data,
  schedulerData,
  schedulerLoading,
  onApprove,
  onReject,
}: {
  data: DashboardData;
  schedulerData: SchedulerStatus | undefined;
  schedulerLoading: boolean;
  onApprove: (type: string, sourceId: string) => void;
  onReject: (type: string, sourceId: string) => void;
}) {
  return (
    <div className="overview-tab-content">
      {/* Row 1: State | Stats | Goals */}
      <div className="dashboard-row row-1">
        <StateCard data={data} />
        <StatsCard data={data} />
        <GoalsCard data={data} />
      </div>

      {/* Row 2: Metrics | Daily Summary */}
      <div className="dashboard-row row-2">
        <MetricsCard data={data} />
        <DailySummaryCard data={data} />
      </div>

      {/* Row 3: Scheduler | Approvals */}
      <div className="dashboard-row row-3">
        <SchedulerCard data={schedulerData} isLoading={schedulerLoading} />
        <ApprovalsCard
          data={data.approvals}
          onApprove={onApprove}
          onReject={onReject}
        />
      </div>
    </div>
  );
}

// =============================================================================
// MAIN DASHBOARD
// =============================================================================

type DashboardTab = 'overview' | 'goals' | 'agency';

export function Dashboard() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: schedulerData, isLoading: schedulerLoading } = useQuery({
    queryKey: ['scheduler-status'],
    queryFn: async () => {
      const response = await schedulerApi.getStatus();
      return response.data;
    },
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  const handleApprove = async (type: string, sourceId: string) => {
    try {
      await schedulerApi.approveItem(type, sourceId);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      console.error('Failed to approve:', err);
    }
  };

  const handleReject = async (type: string, sourceId: string) => {
    try {
      await schedulerApi.rejectItem(type, sourceId, 'admin', '');
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      console.error('Failed to reject:', err);
    }
  };

  if (isLoading) {
    return (
      <div className="dashboard loading">
        <div className="loading-spinner">Loading dashboard...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard error">
        <div className="error-message">Failed to load dashboard: {String(error)}</div>
        <button className="refresh-btn" onClick={() => refetch()}>Retry</button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="dashboard error">
        <div className="error-message">No data available</div>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      {/* Left Panel: Autonomous Schedule */}
      <aside className="dashboard-left-panel">
        <SchedulePanel />
      </aside>

      {/* Center: Main Dashboard with Tabs */}
      <main className="dashboard-center">
        <header className="dashboard-header">
          <div className="header-content">
            <h1>Dashboard</h1>
            <div className="dashboard-tabs">
              <button
                className={`dashboard-tab ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
              >
                <span className="tab-icon">◎</span>
                Overview
              </button>
              <button
                className={`dashboard-tab ${activeTab === 'goals' ? 'active' : ''}`}
                onClick={() => setActiveTab('goals')}
              >
                <span className="tab-icon">◈</span>
                Goals
              </button>
              <button
                className={`dashboard-tab ${activeTab === 'agency' ? 'active' : ''}`}
                onClick={() => setActiveTab('agency')}
              >
                <span className="tab-icon">◆</span>
                Agency
              </button>
            </div>
          </div>
          <button className="refresh-btn" onClick={() => refetch()}>Refresh</button>
        </header>

        <div className="dashboard-tab-content">
          {activeTab === 'overview' && (
            <OverviewTabContent
              data={data}
              schedulerData={schedulerData}
              schedulerLoading={schedulerLoading}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          )}
          {activeTab === 'goals' && (
            <div className="goals-tab-wrapper">
              <GoalsTab />
            </div>
          )}
          {activeTab === 'agency' && (
            <div className="agency-tab-wrapper">
              <AgencyTab />
            </div>
          )}
        </div>
      </main>

      {/* Right Panel: Chat Widget */}
      <aside className="dashboard-right-panel">
        <ChatWidget />
      </aside>
    </div>
  );
}
