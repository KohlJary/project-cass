import { useState } from 'react';
import { GitHubMetricsTab } from './metrics/GitHubMetricsTab';
import { TokenUsageTab } from './metrics/TokenUsageTab';
import './Metrics.css';

type MetricsTab = 'github' | 'tokens';

export function Metrics() {
  const [activeTab, setActiveTab] = useState<MetricsTab>('github');

  return (
    <div className="metrics-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Metrics</h1>
          <p className="subtitle">System metrics and usage analytics</p>
        </div>
      </header>

      <div className="metrics-tabs">
        <button
          className={`tab-btn ${activeTab === 'github' ? 'active' : ''}`}
          onClick={() => setActiveTab('github')}
        >
          GitHub
        </button>
        <button
          className={`tab-btn ${activeTab === 'tokens' ? 'active' : ''}`}
          onClick={() => setActiveTab('tokens')}
        >
          Token Usage
        </button>
      </div>

      <div className="metrics-content">
        {activeTab === 'github' && <GitHubMetricsTab />}
        {activeTab === 'tokens' && <TokenUsageTab />}
      </div>
    </div>
  );
}
