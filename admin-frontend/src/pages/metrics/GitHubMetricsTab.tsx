import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { githubApi } from '../../api/client';
import '../GitHubMetrics.css';

interface DailyData {
  timestamp: string;
  count: number;
  uniques: number;
}

interface RepoMetrics {
  repo: string;
  clones_count: number;
  clones_uniques: number;
  views_count: number;
  views_uniques: number;
  stars: number;
  forks: number;
  watchers: number;
  open_issues: number;
  clones_daily?: { timestamp: string; count: number; uniques: number }[];
  views_daily?: { timestamp: string; count: number; uniques: number }[];
}

interface MetricsData {
  timestamp: string;
  repos: { [key: string]: RepoMetrics };
  api_calls_remaining?: number;
}

interface StatsData {
  tracked_repos: string[];
  has_token: boolean;
  last_fetch: string | null;
  rate_limit_remaining: number | null;
  historical_days_available: number;
  current: {
    timestamp: string;
    total_clones: number;
    total_unique_cloners: number;
    total_stars: number;
    total_forks: number;
  };
}

interface TimeSeriesPoint {
  date: string;
  value: number;
}

type TimeRange = '7d' | '14d' | 'all' | 'custom';

interface AllTimeRepoStats {
  [key: string]: {
    repo: string;
    clones_count: number;
    clones_uniques: number;
    views_count: number;
    views_uniques: number;
    stars: number;
    forks: number;
    watchers: number;
    open_issues: number;
  };
}

function filterByDateRange(
  data: DailyData[],
  timeRange: TimeRange,
  customStartDate: string,
  customEndDate: string
): DailyData[] {
  // 'all' means no filtering
  if (timeRange === 'all') {
    return data;
  }

  const now = new Date();
  let startDate: Date;
  let endDate: Date;

  if (timeRange === '7d') {
    startDate = new Date(now);
    startDate.setDate(startDate.getDate() - 7);
    endDate = now;
  } else if (timeRange === '14d') {
    startDate = new Date(now);
    startDate.setDate(startDate.getDate() - 14);
    endDate = now;
  } else {
    startDate = new Date(customStartDate);
    endDate = new Date(customEndDate);
  }

  const startStr = startDate.toISOString().split('T')[0];
  const endStr = endDate.toISOString().split('T')[0];

  return data.filter(d => {
    const date = d.timestamp.split('T')[0];
    return date >= startStr && date <= endStr;
  });
}

function combineDailyData(repos: { [key: string]: RepoMetrics }, field: 'clones_daily' | 'views_daily'): DailyData[] {
  const byDate: { [date: string]: { count: number; uniques: number } } = {};

  Object.values(repos).forEach(repo => {
    const dailyData = repo[field] || [];
    dailyData.forEach(d => {
      const date = d.timestamp.split('T')[0];
      if (!byDate[date]) {
        byDate[date] = { count: 0, uniques: 0 };
      }
      byDate[date].count += d.count;
      byDate[date].uniques += d.uniques;
    });
  });

  return Object.entries(byDate)
    .map(([date, data]) => ({ timestamp: date, ...data }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
}

export function GitHubMetricsTab() {
  const queryClient = useQueryClient();
  const [chartMetric, setChartMetric] = useState<'clones' | 'views'>('clones');
  const [selectedRepo, setSelectedRepo] = useState<string>('all');
  const [timeRange, setTimeRange] = useState<TimeRange>('14d');
  const [customStartDate, setCustomStartDate] = useState<string>(() => {
    const date = new Date();
    date.setDate(date.getDate() - 14);
    return date.toISOString().split('T')[0];
  });
  const [customEndDate, setCustomEndDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });

  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useQuery<MetricsData>({
    queryKey: ['github-metrics'],
    queryFn: () => githubApi.getCurrent().then((r) => r.data),
    refetchInterval: 60000,
    retry: false,
  });

  const { data: stats, isLoading: statsLoading } = useQuery<StatsData>({
    queryKey: ['github-stats'],
    queryFn: () => githubApi.getStats().then((r) => r.data),
    refetchInterval: 60000,
    retry: false,
  });

  const { data: clonesTimeSeries } = useQuery<{ data: TimeSeriesPoint[] }>({
    queryKey: ['github-timeseries-clones'],
    queryFn: () => githubApi.getTimeSeries('clones_uniques', { days: 14 }).then((r) => r.data),
    refetchInterval: 300000,
  });

  const { data: viewsTimeSeries } = useQuery<{ data: TimeSeriesPoint[] }>({
    queryKey: ['github-timeseries-views'],
    queryFn: () => githubApi.getTimeSeries('views_uniques', { days: 14 }).then((r) => r.data),
    refetchInterval: 300000,
  });

  // All-time stats for repository breakdown
  const { data: allTimeStats } = useQuery<AllTimeRepoStats>({
    queryKey: ['github-alltime-stats'],
    queryFn: () => githubApi.getAllTimeStats().then((r) => r.data),
    refetchInterval: 300000,
  });

  const refreshMutation = useMutation({
    mutationFn: () => githubApi.refresh(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['github-metrics'] });
      queryClient.invalidateQueries({ queryKey: ['github-stats'] });
      queryClient.invalidateQueries({ queryKey: ['github-timeseries-clones'] });
      queryClient.invalidateQueries({ queryKey: ['github-timeseries-views'] });
      queryClient.invalidateQueries({ queryKey: ['github-alltime-stats'] });
    },
  });

  const formatTimestamp = (ts: string | null) => {
    if (!ts) return 'Never';
    const date = new Date(ts);
    return date.toLocaleString();
  };

  const renderMiniChart = (data: TimeSeriesPoint[] | undefined, color: string) => {
    if (!data || data.length === 0) return <div className="mini-chart-empty">No data</div>;

    const values = data.map(d => d.value);
    const max = Math.max(...values, 1);
    const width = 200;
    const height = 40;
    const barWidth = width / values.length - 2;

    return (
      <svg className="mini-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {values.map((value, i) => (
          <rect
            key={i}
            x={i * (barWidth + 2)}
            y={height - (value / max) * height}
            width={barWidth}
            height={(value / max) * height}
            fill={color}
            opacity={0.8}
          />
        ))}
      </svg>
    );
  };

  const renderFullChart = (data: DailyData[], primaryColor: string, secondaryColor: string) => {
    if (!data || data.length === 0) {
      return <div className="chart-empty">No daily data available</div>;
    }

    const width = 800;
    const height = 300;
    const padding = { top: 20, right: 20, bottom: 40, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const maxCount = Math.max(...data.map(d => d.count), 1);
    const maxUniques = Math.max(...data.map(d => d.uniques), 1);
    const maxValue = Math.max(maxCount, maxUniques);

    const xStep = chartWidth / (data.length - 1 || 1);

    const generatePath = (values: number[]) => {
      return values.map((value, i) => {
        const x = padding.left + i * xStep;
        const y = padding.top + chartHeight - (value / maxValue) * chartHeight;
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ');
    };

    const generateAreaPath = (values: number[]) => {
      const linePath = values.map((value, i) => {
        const x = padding.left + i * xStep;
        const y = padding.top + chartHeight - (value / maxValue) * chartHeight;
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ');

      const lastX = padding.left + (values.length - 1) * xStep;
      const firstX = padding.left;
      const baseY = padding.top + chartHeight;

      return `${linePath} L ${lastX} ${baseY} L ${firstX} ${baseY} Z`;
    };

    const countValues = data.map(d => d.count);
    const uniqueValues = data.map(d => d.uniques);

    return (
      <svg className="full-chart" viewBox={`0 0 ${width} ${height}`}>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => (
          <g key={i}>
            <line
              x1={padding.left}
              y1={padding.top + chartHeight * (1 - ratio)}
              x2={width - padding.right}
              y2={padding.top + chartHeight * (1 - ratio)}
              stroke="#222"
              strokeDasharray={ratio === 0 ? "0" : "4,4"}
            />
            <text
              x={padding.left - 8}
              y={padding.top + chartHeight * (1 - ratio) + 4}
              textAnchor="end"
              fill="#666"
              fontSize="11"
            >
              {Math.round(maxValue * ratio)}
            </text>
          </g>
        ))}

        <path d={generateAreaPath(countValues)} fill={primaryColor} opacity={0.15} />
        <path d={generateAreaPath(uniqueValues)} fill={secondaryColor} opacity={0.15} />
        <path d={generatePath(countValues)} fill="none" stroke={primaryColor} strokeWidth={2} />
        <path d={generatePath(uniqueValues)} fill="none" stroke={secondaryColor} strokeWidth={2} strokeDasharray="6,3" />

        {data.map((d, i) => {
          const x = padding.left + i * xStep;
          return (
            <g key={i}>
              <circle cx={x} cy={padding.top + chartHeight - (d.count / maxValue) * chartHeight} r={4} fill={primaryColor} />
              <circle cx={x} cy={padding.top + chartHeight - (d.uniques / maxValue) * chartHeight} r={3} fill={secondaryColor} />
            </g>
          );
        })}

        {data.map((d, i) => {
          if (data.length > 10 && i % 2 !== 0 && i !== data.length - 1) return null;
          const x = padding.left + i * xStep;
          const date = new Date(d.timestamp);
          const label = `${date.getMonth() + 1}/${date.getDate()}`;
          return (
            <text key={i} x={x} y={height - 10} textAnchor="middle" fill="#666" fontSize="11">
              {label}
            </text>
          );
        })}

        <g transform={`translate(${width - 150}, ${padding.top})`}>
          <line x1={0} y1={0} x2={20} y2={0} stroke={primaryColor} strokeWidth={2} />
          <text x={25} y={4} fill="#888" fontSize="11">Total</text>
          <line x1={0} y1={18} x2={20} y2={18} stroke={secondaryColor} strokeWidth={2} strokeDasharray="6,3" />
          <text x={25} y={22} fill="#888" fontSize="11">Unique</text>
        </g>
      </svg>
    );
  };

  return (
    <div className="github-metrics-tab">
      <div className="tab-header">
        <h2>GitHub Repository Metrics</h2>
        <button
          className="refresh-button"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
        >
          {refreshMutation.isPending ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <div className="repo-selector">
        <label htmlFor="repo-select">View:</label>
        <select
          id="repo-select"
          value={selectedRepo}
          onChange={(e) => setSelectedRepo(e.target.value)}
          className="repo-select"
        >
          <option value="all">All Repositories</option>
          {Object.keys(metrics?.repos ?? {}).map((repoName) => (
            <option key={repoName} value={repoName}>{repoName}</option>
          ))}
        </select>
      </div>

      <div className="status-banner">
        <div className="status-item">
          <span className="status-label">Last Fetch:</span>
          <span className="status-value">{formatTimestamp(stats?.last_fetch ?? null)}</span>
        </div>
        <div className="status-item">
          <span className="status-label">API Token:</span>
          <span className={`status-value ${stats?.has_token ? 'ok' : 'warning'}`}>
            {stats?.has_token ? 'Configured' : 'Not Set'}
          </span>
        </div>
        <div className="status-item">
          <span className="status-label">Rate Limit:</span>
          <span className="status-value">{stats?.rate_limit_remaining ?? '--'} remaining</span>
        </div>
        <div className="status-item">
          <span className="status-label">History:</span>
          <span className="status-value">{stats?.historical_days_available ?? 0} days</span>
        </div>
      </div>

      {metricsLoading || statsLoading ? (
        <div className="loading-state">Loading metrics...</div>
      ) : metricsError ? (
        <div className="error-state">Failed to load metrics. Is GITHUB_TOKEN configured?</div>
      ) : (
        <>
          <div className="totals-grid">
            <div className="total-card clones">
              <div className="total-number">
                {selectedRepo === 'all' ? stats?.current?.total_clones ?? 0 : metrics?.repos?.[selectedRepo]?.clones_count ?? 0}
              </div>
              <div className="total-label">Total Clones (14d)</div>
              <div className="total-sublabel">
                {selectedRepo === 'all' ? stats?.current?.total_unique_cloners ?? 0 : metrics?.repos?.[selectedRepo]?.clones_uniques ?? 0} unique
              </div>
              {renderMiniChart(clonesTimeSeries?.data, '#89ddff')}
            </div>
            <div className="total-card stars">
              <div className="total-number">
                {selectedRepo === 'all' ? stats?.current?.total_stars ?? 0 : metrics?.repos?.[selectedRepo]?.stars ?? 0}
              </div>
              <div className="total-label">Stars</div>
              <div className="total-icon">*</div>
            </div>
            <div className="total-card forks">
              <div className="total-number">
                {selectedRepo === 'all' ? stats?.current?.total_forks ?? 0 : metrics?.repos?.[selectedRepo]?.forks ?? 0}
              </div>
              <div className="total-label">Forks</div>
              <div className="total-icon">Y</div>
            </div>
            <div className="total-card views">
              <div className="total-number">
                {selectedRepo === 'all'
                  ? Object.values(metrics?.repos ?? {}).reduce((sum, r) => sum + (r.views_count || 0), 0)
                  : metrics?.repos?.[selectedRepo]?.views_count ?? 0}
              </div>
              <div className="total-label">Views (14d)</div>
              <div className="total-sublabel">
                {selectedRepo === 'all'
                  ? Object.values(metrics?.repos ?? {}).reduce((sum, r) => sum + (r.views_uniques || 0), 0)
                  : metrics?.repos?.[selectedRepo]?.views_uniques ?? 0} unique
              </div>
              {renderMiniChart(viewsTimeSeries?.data, '#c792ea')}
            </div>
          </div>

          <div className="chart-section">
            <div className="chart-header">
              <h3>Daily Trends</h3>
              <div className="chart-controls">
                <div className="time-range-selector">
                  <button className={`toggle-btn ${timeRange === '7d' ? 'active' : ''}`} onClick={() => setTimeRange('7d')}>7 Days</button>
                  <button className={`toggle-btn ${timeRange === '14d' ? 'active' : ''}`} onClick={() => setTimeRange('14d')}>14 Days</button>
                  <button className={`toggle-btn ${timeRange === 'custom' ? 'active' : ''}`} onClick={() => setTimeRange('custom')}>Custom</button>
                  <button className={`toggle-btn ${timeRange === 'all' ? 'active' : ''}`} onClick={() => setTimeRange('all')}>All-Time</button>
                </div>
                <div className="chart-toggle">
                  <button className={`toggle-btn ${chartMetric === 'clones' ? 'active' : ''}`} onClick={() => setChartMetric('clones')}>Clones</button>
                  <button className={`toggle-btn ${chartMetric === 'views' ? 'active' : ''}`} onClick={() => setChartMetric('views')}>Views</button>
                </div>
              </div>
            </div>
            {timeRange === 'custom' && (
              <div className="custom-date-range">
                <div className="date-input-group">
                  <label htmlFor="start-date">From:</label>
                  <input type="date" id="start-date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} className="date-input" />
                </div>
                <div className="date-input-group">
                  <label htmlFor="end-date">To:</label>
                  <input type="date" id="end-date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} className="date-input" />
                </div>
              </div>
            )}
            <div className="chart-container">
              {chartMetric === 'clones'
                ? renderFullChart(
                    filterByDateRange(
                      combineDailyData(selectedRepo === 'all' ? metrics?.repos ?? {} : { [selectedRepo]: metrics?.repos?.[selectedRepo] } as { [key: string]: RepoMetrics }, 'clones_daily'),
                      timeRange, customStartDate, customEndDate
                    ),
                    '#89ddff', '#5fb3d5'
                  )
                : renderFullChart(
                    filterByDateRange(
                      combineDailyData(selectedRepo === 'all' ? metrics?.repos ?? {} : { [selectedRepo]: metrics?.repos?.[selectedRepo] } as { [key: string]: RepoMetrics }, 'views_daily'),
                      timeRange, customStartDate, customEndDate
                    ),
                    '#c792ea', '#9966cc'
                  )
              }
            </div>
          </div>

          <div className="repos-section">
            <h3>Repository Breakdown (All-Time)</h3>
            <div className="repos-grid">
              {Object.entries(allTimeStats ?? metrics?.repos ?? {})
                .filter(([repoName]) => selectedRepo === 'all' || repoName === selectedRepo)
                .map(([repoName, repo]) => (
                <div key={repoName} className="repo-card">
                  <h4 className="repo-name">
                    <a href={`https://github.com/${repoName}`} target="_blank" rel="noopener noreferrer">{repoName}</a>
                  </h4>
                  <div className="repo-stats">
                    <div className="repo-stat"><span className="stat-value">{repo.clones_count}</span><span className="stat-label">Clones</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.clones_uniques}</span><span className="stat-label">Unique Cloners</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.views_count}</span><span className="stat-label">Views</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.views_uniques}</span><span className="stat-label">Unique Visitors</span></div>
                    <div className="repo-stat highlight"><span className="stat-value">{repo.stars}</span><span className="stat-label">Stars</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.forks}</span><span className="stat-label">Forks</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.watchers}</span><span className="stat-label">Watchers</span></div>
                    <div className="repo-stat"><span className="stat-value">{repo.open_issues}</span><span className="stat-label">Issues</span></div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="info-notice">
            <strong>Note:</strong> GitHub only retains traffic data (clones, views) for 14 days.
            This dashboard stores daily snapshots to build historical trends.
          </div>
        </>
      )}
    </div>
  );
}
