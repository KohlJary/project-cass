import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '../api/client';
import './MemorySystem.css';

// Import existing components as tab content
import { MemoryBrowseTab } from './tabs/MemoryBrowseTab';
import { MemoryRetrievalTab } from './tabs/MemoryRetrievalTab';
import { MemoryVectorsTab } from './tabs/MemoryVectorsTab';

type TabId = 'browse' | 'retrieval' | 'vectors' | 'stats';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'browse', label: 'Browse', icon: '*' },
  { id: 'retrieval', label: 'Retrieval Test', icon: '?' },
  { id: 'vectors', label: 'Vector Space', icon: 'o' },
  { id: 'stats', label: 'Stats', icon: '#' },
];

export function MemorySystem() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'browse'
  );

  // Sync tab state with URL
  useEffect(() => {
    const tabParam = searchParams.get('tab') as TabId;
    if (tabParam && tabs.some((t) => t.id === tabParam)) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  // Fetch stats for the stats tab and header summary
  const { data: statsData } = useQuery({
    queryKey: ['memory-stats'],
    queryFn: () => memoryApi.getStats().then((r) => r.data),
    retry: false,
  });

  return (
    <div className="memory-system-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Memory System</h1>
          <p className="subtitle">
            Explore, search, and analyze Cass's memory embeddings
          </p>
        </div>
        {statsData && (
          <div className="header-stats">
            <div className="stat-pill">
              <span className="stat-value">{statsData.total_memories?.toLocaleString() || 0}</span>
              <span className="stat-label">memories</span>
            </div>
            <div className="stat-pill">
              <span className="stat-value">{statsData.type_counts ? Object.keys(statsData.type_counts).length : 0}</span>
              <span className="stat-label">types</span>
            </div>
          </div>
        )}
      </header>

      <div className="tabs-container" role="tablist" aria-label="Memory system views">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </div>

      <div
        className="tab-content"
        role="tabpanel"
        id={`panel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        {activeTab === 'browse' && <MemoryBrowseTab />}
        {activeTab === 'retrieval' && <MemoryRetrievalTab />}
        {activeTab === 'vectors' && <MemoryVectorsTab />}
        {activeTab === 'stats' && <MemoryStatsTab statsData={statsData} />}
      </div>
    </div>
  );
}

// Stats tab component (new functionality)
function MemoryStatsTab({ statsData }: { statsData: any }) {
  if (!statsData) {
    return <div className="loading-state">Loading stats...</div>;
  }

  const typeCounts = statsData.type_counts || {};
  const sortedTypes = Object.entries(typeCounts).sort(
    ([, a], [, b]) => (b as number) - (a as number)
  );

  const typeColors: Record<string, string> = {
    summary: '#89ddff',
    journal: '#c792ea',
    user_observation: '#ffcb6b',
    cass_self_observation: '#c3e88d',
    per_user_journal: '#f78c6c',
    conversation: '#82aaff',
    attractor_marker: '#ff9cac',
    project_document: '#ffd580',
  };

  const totalMemories = statsData.total_memories || 0;

  return (
    <div className="stats-tab">
      <div className="stats-grid">
        <div className="stat-card large">
          <div className="stat-card-value">{totalMemories.toLocaleString()}</div>
          <div className="stat-card-label">Total Memories</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-value">{sortedTypes.length}</div>
          <div className="stat-card-label">Memory Types</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-value">1536</div>
          <div className="stat-card-label">Embedding Dimensions</div>
        </div>
      </div>

      <div className="type-breakdown-section">
        <h3>Memory Type Distribution</h3>
        <div className="type-bars">
          {sortedTypes.map(([type, count]) => {
            const percentage = totalMemories > 0 ? ((count as number) / totalMemories) * 100 : 0;
            const color = typeColors[type] || '#888';
            return (
              <div key={type} className="type-bar-row">
                <div className="type-bar-label">
                  <span className="type-dot" style={{ backgroundColor: color }} />
                  <span className="type-name">{type.replace(/_/g, ' ')}</span>
                </div>
                <div className="type-bar-container">
                  <div
                    className="type-bar-fill"
                    style={{ width: `${percentage}%`, backgroundColor: color }}
                  />
                </div>
                <div className="type-bar-stats">
                  <span className="type-count">{(count as number).toLocaleString()}</span>
                  <span className="type-percent">{percentage.toFixed(1)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {statsData.collection_info && (
        <div className="collection-info-section">
          <h3>Collection Info</h3>
          <div className="info-grid">
            {Object.entries(statsData.collection_info).map(([key, value]) => (
              <div key={key} className="info-item">
                <span className="info-label">{key.replace(/_/g, ' ')}</span>
                <span className="info-value">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
