import { useQuery } from '@tanstack/react-query';
import { systemApi, memoryApi } from '../api/client';
import './Dashboard.css';

export function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['system-stats'],
    queryFn: () => systemApi.getStats().then((r) => r.data),
    retry: false,
  });

  const { data: memoryStats, isLoading: memoryLoading } = useQuery({
    queryKey: ['memory-stats'],
    queryFn: () => memoryApi.getStats().then((r) => r.data),
    retry: false,
  });

  return (
    <div className="dashboard">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Cass instance overview</p>
      </header>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">*</div>
          <div className="stat-content">
            <div className="stat-value">
              {memoryLoading ? '...' : memoryStats?.total_memories ?? '--'}
            </div>
            <div className="stat-label">Total Memories</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">#</div>
          <div className="stat-content">
            <div className="stat-value">
              {memoryLoading ? '...' : memoryStats?.journals ?? '--'}
            </div>
            <div className="stat-label">Journals</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">@</div>
          <div className="stat-content">
            <div className="stat-value">
              {statsLoading ? '...' : stats?.users ?? '--'}
            </div>
            <div className="stat-label">Users</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon">&gt;</div>
          <div className="stat-content">
            <div className="stat-value">
              {statsLoading ? '...' : stats?.conversations ?? '--'}
            </div>
            <div className="stat-label">Conversations</div>
          </div>
        </div>
      </div>

      <section className="dashboard-section">
        <h2>Memory Breakdown</h2>
        <div className="breakdown-list">
          {memoryLoading ? (
            <p className="loading">Loading...</p>
          ) : memoryStats?.by_type ? (
            Object.entries(memoryStats.by_type).map(([type, count]) => (
              <div key={type} className="breakdown-item">
                <span className="breakdown-type">{type}</span>
                <span className="breakdown-count">{count as number}</span>
              </div>
            ))
          ) : (
            <p className="empty">No memory data available</p>
          )}
        </div>
      </section>

      <section className="dashboard-section">
        <h2>Quick Actions</h2>
        <div className="actions-grid">
          <a href="/memory" className="action-card">
            <span className="action-icon">*</span>
            <span>Explore Memory</span>
          </a>
          <a href="/retrieval" className="action-card">
            <span className="action-icon">?</span>
            <span>Test Retrieval</span>
          </a>
          <a href="/journals" className="action-card">
            <span className="action-icon">#</span>
            <span>View Journals</span>
          </a>
        </div>
      </section>
    </div>
  );
}
