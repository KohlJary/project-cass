/**
 * Dashboard - Main dashboard page with tabs
 *
 * Refactored to use extracted card components from ./dashboard
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData } from '../api/graphql';
import type { DashboardData } from '../api/graphql';
import type { SchedulerStatus, ExecutionLogEntry } from '../api/client';
import { grimoireApi } from '../api/client';
import { SchedulePanel } from '../components/SchedulePanel';
import { ChatWidget } from '../components/ChatWidget';
import { Goals } from './Goals';
import { useScheduler, useApprovals } from '../hooks';
import {
  StateCard,
  StatsCard,
  GoalsCard,
  MetricsCard,
  DailySummaryCard,
  SchedulerCard,
  ApprovalsCard,
  AgencyCard,
} from './dashboard';
import './Dashboard.css';

// =============================================================================
// ACTIVITY TAB CONTENT
// =============================================================================

function ActivityTabContent() {
  const { data: executionLog, isLoading: logLoading } = useQuery({
    queryKey: ['grimoireExecutionLog'],
    queryFn: () => grimoireApi.getExecutionLog(30),
    refetchInterval: 15000, // Refresh every 15 seconds
  });

  return (
    <div className="activity-tab-content">
      {/* Autonomous Schedule */}
      <div className="activity-section">
        <SchedulePanel className="embedded-schedule" />
      </div>

      {/* Grimoire Executions */}
      <div className="activity-section grimoire-section">
        <div className="section-header">
          <h3>🔮 Spell Executions</h3>
        </div>
        {logLoading ? (
          <div className="loading-message">Loading spell log...</div>
        ) : !executionLog?.data || executionLog.data.length === 0 ? (
          <div className="empty-message">No spell executions yet</div>
        ) : (
          <div className="execution-log">
            {executionLog.data.map((entry: ExecutionLogEntry, i: number) => (
              <div
                key={`${entry.spell_name}-${entry.timestamp || i}`}
                className={`execution-entry ${entry.status}`}
              >
                <div className="entry-header">
                  <span className="spell-name">{entry.spell_name}</span>
                  <span className={`status-badge ${entry.status}`}>
                    {entry.status}
                  </span>
                </div>
                <div className="entry-details">
                  <span className="trigger-type">{entry.trigger_type}</span>
                  {entry.reason && (
                    <span className="reason">{entry.reason}</span>
                  )}
                  <span className="duration">
                    {entry.execution_time_ms.toFixed(0)}ms
                  </span>
                </div>
                {entry.timestamp && (
                  <div className="entry-time">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </div>
                )}
              </div>
            ))}
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

      {/* Row 4: Agency */}
      <div className="dashboard-row row-4">
        <AgencyCard />
      </div>
    </div>
  );
}

// =============================================================================
// MAIN DASHBOARD
// =============================================================================

type DashboardTab = 'overview' | 'activity' | 'goals';

export function Dashboard() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboardData,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: schedulerData, isLoading: schedulerLoading } = useScheduler({
    refetchInterval: 10000,
  });

  const { approve, reject } = useApprovals();

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
    <div className="dashboard-layout two-column">
      {/* Main Dashboard with Tabs */}
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
                className={`dashboard-tab ${activeTab === 'activity' ? 'active' : ''}`}
                onClick={() => setActiveTab('activity')}
              >
                <span className="tab-icon">◐</span>
                Activity
              </button>
              <button
                className={`dashboard-tab ${activeTab === 'goals' ? 'active' : ''}`}
                onClick={() => setActiveTab('goals')}
              >
                <span className="tab-icon">◈</span>
                Goals
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
              onApprove={approve}
              onReject={reject}
            />
          )}
          {activeTab === 'activity' && <ActivityTabContent />}
          {activeTab === 'goals' && (
            <div className="goals-tab-wrapper">
              <Goals />
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
