/**
 * Dashboard - Main dashboard page with tabs
 *
 * Refactored to use extracted card components from ./dashboard
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchDashboardData } from '../api/graphql';
import type { DashboardData } from '../api/graphql';
import type { SchedulerStatus } from '../api/client';
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

type DashboardTab = 'overview' | 'goals';

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
