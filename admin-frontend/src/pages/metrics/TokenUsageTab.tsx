import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { usageApi } from '../../api/client';

interface UsageSummary {
  period: { start: string | null; end: string | null };
  totals: {
    records: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cache_read_tokens: number;
    estimated_cost_usd: number;
  };
  by_category: { [key: string]: { tokens: number; cost: number; count: number } };
  by_provider: { [key: string]: { tokens: number; cost: number; count: number } };
  by_model: { [key: string]: { tokens: number; cost: number; count: number } };
  by_operation: { [key: string]: { tokens: number; cost: number; count: number } };
}

interface TimeSeriesPoint {
  date: string;
  value: number;
  cost: number;
  count: number;
}

type TimeRange = '7d' | '14d' | '30d' | 'custom';
type MetricType = 'total_tokens' | 'cost' | 'count';

export function TokenUsageTab() {
  const [timeRange, setTimeRange] = useState<TimeRange>('14d');
  const [metric, setMetric] = useState<MetricType>('total_tokens');
  const [customStartDate, setCustomStartDate] = useState<string>(() => {
    const date = new Date();
    date.setDate(date.getDate() - 14);
    return date.toISOString().split('T')[0];
  });
  const [customEndDate, setCustomEndDate] = useState<string>(() => {
    return new Date().toISOString().split('T')[0];
  });

  const getDays = () => {
    switch (timeRange) {
      case '7d': return 7;
      case '14d': return 14;
      case '30d': return 30;
      case 'custom': {
        const start = new Date(customStartDate);
        const end = new Date(customEndDate);
        return Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
      }
    }
  };

  const { data: summary, isLoading: summaryLoading } = useQuery<UsageSummary>({
    queryKey: ['usage-summary', timeRange, customStartDate, customEndDate],
    queryFn: () => {
      const params: { start_date?: string; end_date?: string } = {};
      if (timeRange === 'custom') {
        params.start_date = customStartDate;
        params.end_date = customEndDate;
      } else {
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - getDays());
        params.start_date = start.toISOString().split('T')[0];
        params.end_date = end.toISOString().split('T')[0];
      }
      return usageApi.getSummary(params).then((r) => r.data);
    },
    refetchInterval: 60000,
  });

  const { data: timeSeries } = useQuery<{ data: TimeSeriesPoint[] }>({
    queryKey: ['usage-timeseries', metric, getDays()],
    queryFn: () => usageApi.getTimeSeries({ metric, days: getDays() }).then((r) => r.data),
    refetchInterval: 60000,
  });

  const formatNumber = (n: number) => {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toLocaleString();
  };

  const formatCost = (cost: number) => {
    return `$${cost.toFixed(4)}`;
  };

  const renderChart = (data: TimeSeriesPoint[] | undefined, metricType: MetricType) => {
    if (!data || data.length === 0) {
      return <div className="chart-empty">No usage data available</div>;
    }

    const width = 800;
    const height = 300;
    const padding = { top: 20, right: 20, bottom: 40, left: 60 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const values = data.map(d => metricType === 'cost' ? d.cost : d.value);
    const maxValue = Math.max(...values, 1);

    const xStep = chartWidth / (data.length - 1 || 1);

    const generatePath = () => {
      return values.map((value, i) => {
        const x = padding.left + i * xStep;
        const y = padding.top + chartHeight - (value / maxValue) * chartHeight;
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ');
    };

    const generateAreaPath = () => {
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

    const color = metricType === 'cost' ? '#c3e88d' : '#89ddff';

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
              {metricType === 'cost'
                ? `$${(maxValue * ratio).toFixed(2)}`
                : formatNumber(Math.round(maxValue * ratio))}
            </text>
          </g>
        ))}

        <path d={generateAreaPath()} fill={color} opacity={0.15} />
        <path d={generatePath()} fill="none" stroke={color} strokeWidth={2} />

        {data.map((d, i) => {
          const x = padding.left + i * xStep;
          const value = metricType === 'cost' ? d.cost : d.value;
          return (
            <circle
              key={i}
              cx={x}
              cy={padding.top + chartHeight - (value / maxValue) * chartHeight}
              r={4}
              fill={color}
            />
          );
        })}

        {data.map((d, i) => {
          if (data.length > 14 && i % 2 !== 0 && i !== data.length - 1) return null;
          const x = padding.left + i * xStep;
          const date = new Date(d.date);
          const label = `${date.getMonth() + 1}/${date.getDate()}`;
          return (
            <text key={i} x={x} y={height - 10} textAnchor="middle" fill="#666" fontSize="11">
              {label}
            </text>
          );
        })}
      </svg>
    );
  };

  const renderCategoryBreakdown = () => {
    if (!summary?.by_category) return null;

    const categories = Object.entries(summary.by_category).sort((a, b) => b[1].tokens - a[1].tokens);
    const totalTokens = summary.totals.total_tokens || 1;

    return (
      <div className="breakdown-section">
        <h3>By Category</h3>
        <div className="breakdown-bars">
          {categories.map(([category, data]) => {
            const percentage = (data.tokens / totalTokens) * 100;
            return (
              <div key={category} className="breakdown-item">
                <div className="breakdown-label">
                  <span className="category-name">{category}</span>
                  <span className="category-stats">{formatNumber(data.tokens)} tokens / {formatCost(data.cost)}</span>
                </div>
                <div className="breakdown-bar">
                  <div className="breakdown-fill" style={{ width: `${percentage}%` }} />
                </div>
                <span className="breakdown-count">{data.count} calls</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderProviderBreakdown = () => {
    if (!summary?.by_provider) return null;

    const providers = Object.entries(summary.by_provider).sort((a, b) => b[1].tokens - a[1].tokens);
    const colors: { [key: string]: string } = {
      anthropic: '#c792ea',
      openai: '#c3e88d',
      ollama: '#89ddff',
    };

    return (
      <div className="breakdown-section">
        <h3>By Provider</h3>
        <div className="provider-cards">
          {providers.map(([provider, data]) => (
            <div key={provider} className="provider-card" style={{ borderColor: colors[provider] || '#666' }}>
              <div className="provider-name">{provider}</div>
              <div className="provider-tokens">{formatNumber(data.tokens)}</div>
              <div className="provider-cost">{formatCost(data.cost)}</div>
              <div className="provider-calls">{data.count} calls</div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="token-usage-tab">
      <div className="tab-header">
        <h2>Token Usage Analytics</h2>
      </div>

      <div className="time-controls">
        <div className="time-range-selector">
          <button className={`toggle-btn ${timeRange === '7d' ? 'active' : ''}`} onClick={() => setTimeRange('7d')}>7 Days</button>
          <button className={`toggle-btn ${timeRange === '14d' ? 'active' : ''}`} onClick={() => setTimeRange('14d')}>14 Days</button>
          <button className={`toggle-btn ${timeRange === '30d' ? 'active' : ''}`} onClick={() => setTimeRange('30d')}>30 Days</button>
          <button className={`toggle-btn ${timeRange === 'custom' ? 'active' : ''}`} onClick={() => setTimeRange('custom')}>Custom</button>
        </div>
        {timeRange === 'custom' && (
          <div className="custom-date-range">
            <div className="date-input-group">
              <label>From:</label>
              <input type="date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} className="date-input" />
            </div>
            <div className="date-input-group">
              <label>To:</label>
              <input type="date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} className="date-input" />
            </div>
          </div>
        )}
      </div>

      {summaryLoading ? (
        <div className="loading-state">Loading usage data...</div>
      ) : (
        <>
          <div className="totals-grid">
            <div className="total-card tokens">
              <div className="total-number">{formatNumber(summary?.totals.total_tokens ?? 0)}</div>
              <div className="total-label">Total Tokens</div>
              <div className="total-sublabel">
                {formatNumber(summary?.totals.input_tokens ?? 0)} in / {formatNumber(summary?.totals.output_tokens ?? 0)} out
              </div>
            </div>
            <div className="total-card cost">
              <div className="total-number">{formatCost(summary?.totals.estimated_cost_usd ?? 0)}</div>
              <div className="total-label">Estimated Cost</div>
              <div className="total-sublabel">Based on current pricing</div>
            </div>
            <div className="total-card calls">
              <div className="total-number">{summary?.totals.records ?? 0}</div>
              <div className="total-label">API Calls</div>
              <div className="total-sublabel">Total LLM invocations</div>
            </div>
            <div className="total-card cache">
              <div className="total-number">{formatNumber(summary?.totals.cache_read_tokens ?? 0)}</div>
              <div className="total-label">Cache Hits</div>
              <div className="total-sublabel">Tokens from cache</div>
            </div>
          </div>

          <div className="chart-section">
            <div className="chart-header">
              <h3>Usage Over Time</h3>
              <div className="chart-toggle">
                <button className={`toggle-btn ${metric === 'total_tokens' ? 'active' : ''}`} onClick={() => setMetric('total_tokens')}>Tokens</button>
                <button className={`toggle-btn ${metric === 'cost' ? 'active' : ''}`} onClick={() => setMetric('cost')}>Cost</button>
                <button className={`toggle-btn ${metric === 'count' ? 'active' : ''}`} onClick={() => setMetric('count')}>Calls</button>
              </div>
            </div>
            <div className="chart-container">
              {renderChart(timeSeries?.data, metric)}
            </div>
          </div>

          <div className="breakdowns">
            {renderCategoryBreakdown()}
            {renderProviderBreakdown()}
          </div>
        </>
      )}
    </div>
  );
}
