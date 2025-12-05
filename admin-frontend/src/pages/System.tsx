import { useQuery } from '@tanstack/react-query';
import { systemApi, memoryApi } from '../api/client';
import './System.css';

export function System() {
  const { data: health, isLoading: healthLoading, error: healthError } = useQuery({
    queryKey: ['system-health'],
    queryFn: () => systemApi.getHealth().then((r) => r.data),
    refetchInterval: 10000, // Auto-refresh every 10s
    retry: false,
  });

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['system-stats'],
    queryFn: () => systemApi.getStats().then((r) => r.data),
    refetchInterval: 30000,
    retry: false,
  });

  const { data: memoryStats, isLoading: memoryLoading } = useQuery({
    queryKey: ['memory-stats'],
    queryFn: () => memoryApi.getStats().then((r) => r.data),
    refetchInterval: 30000,
    retry: false,
  });

  const isHealthy = health?.status === 'healthy';

  return (
    <div className="system-page">
      <header className="page-header">
        <h1>System Health</h1>
        <p className="subtitle">Monitor Cass instance status and resources</p>
      </header>

      {/* Health status banner */}
      <div className={`health-banner ${isHealthy ? 'healthy' : 'degraded'}`}>
        <div className="health-indicator">
          <span className="health-dot" />
          <span className="health-text">
            {healthLoading ? 'Checking...' : healthError ? 'Unreachable' : health?.status?.toUpperCase()}
          </span>
        </div>
        <span className="health-time">
          Last check: {new Date().toLocaleTimeString()}
        </span>
      </div>

      <div className="system-grid">
        {/* Components status */}
        <div className="system-card">
          <h2>Components</h2>
          {healthLoading ? (
            <div className="loading-state">Loading...</div>
          ) : healthError ? (
            <div className="error-state">Cannot reach backend</div>
          ) : (
            <div className="components-list">
              {Object.entries(health?.components || {}).map(([name, status]) => (
                <div key={name} className="component-item">
                  <span className={`component-status ${status ? 'up' : 'down'}`}>
                    {status ? '+' : 'x'}
                  </span>
                  <span className="component-name">{name}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick stats */}
        <div className="system-card">
          <h2>Quick Stats</h2>
          {statsLoading ? (
            <div className="loading-state">Loading...</div>
          ) : (
            <div className="quick-stats">
              <div className="quick-stat">
                <span className="stat-number">{stats?.users ?? '--'}</span>
                <span className="stat-name">Users</span>
              </div>
              <div className="quick-stat">
                <span className="stat-number">{stats?.conversations ?? '--'}</span>
                <span className="stat-name">Conversations</span>
              </div>
              <div className="quick-stat">
                <span className="stat-number">{stats?.memories ?? '--'}</span>
                <span className="stat-name">Memories</span>
              </div>
              <div className="quick-stat">
                <span className="stat-number">{stats?.journals ?? '--'}</span>
                <span className="stat-name">Journals</span>
              </div>
            </div>
          )}
        </div>

        {/* Memory breakdown */}
        <div className="system-card wide">
          <h2>Memory Breakdown</h2>
          {memoryLoading ? (
            <div className="loading-state">Loading...</div>
          ) : memoryStats?.by_type ? (
            <div className="memory-breakdown">
              <div className="breakdown-bars">
                {Object.entries(memoryStats.by_type).map(([type, count]) => {
                  const total = memoryStats.total_memories || 1;
                  const percentage = ((count as number) / total) * 100;
                  return (
                    <div key={type} className="breakdown-bar-container">
                      <div className="breakdown-label">
                        <span className="type-name">{type.replace(/_/g, ' ')}</span>
                        <span className="type-count">{count as number}</span>
                      </div>
                      <div className="breakdown-bar-bg">
                        <div
                          className={`breakdown-bar ${type}`}
                          style={{ width: `${percentage}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="total-memories">
                Total: <strong>{memoryStats.total_memories?.toLocaleString()}</strong> memories
              </div>
            </div>
          ) : (
            <div className="empty-state">No memory data</div>
          )}
        </div>

        {/* Backend info */}
        <div className="system-card">
          <h2>Backend Info</h2>
          <div className="info-list">
            <div className="info-item">
              <span className="info-label">API URL</span>
              <code className="info-value">{import.meta.env.VITE_API_URL || 'http://localhost:8000'}</code>
            </div>
            <div className="info-item">
              <span className="info-label">Status</span>
              <span className={`info-value status ${healthError ? 'offline' : 'online'}`}>
                {healthError ? 'Offline' : 'Online'}
              </span>
            </div>
          </div>
        </div>

        {/* Quick actions */}
        <div className="system-card">
          <h2>Quick Links</h2>
          <div className="quick-links">
            <a href="/memory" className="quick-link">
              <span className="link-icon">*</span>
              <span>Memory Explorer</span>
            </a>
            <a href="/retrieval" className="quick-link">
              <span className="link-icon">?</span>
              <span>Retrieval Debugger</span>
            </a>
            <a href="/journals" className="quick-link">
              <span className="link-icon">#</span>
              <span>Journals</span>
            </a>
            <a href="/users" className="quick-link">
              <span className="link-icon">@</span>
              <span>Users</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
