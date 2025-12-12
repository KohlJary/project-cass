import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { selfModelApi, developmentApi } from '../api/client';
import './SelfDevelopment.css';

// Import existing components as tab content
import { SelfModelTab } from './tabs/SelfModelTab';
import { DevelopmentTimelineTab } from './tabs/DevelopmentTimelineTab';
import { StakesTab } from './tabs/StakesTab';
import { ConsistencyTab } from './tabs/ConsistencyTab';
import { NarrationPatternsTab } from './tabs/NarrationPatternsTab';

type TabId = 'identity' | 'timeline' | 'snapshots' | 'observations' | 'stakes' | 'consistency' | 'narration';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'identity', label: 'Identity & Opinions', icon: '%' },
  { id: 'timeline', label: 'Timeline', icon: '↑' },
  { id: 'snapshots', label: 'Snapshots', icon: 'S' },
  { id: 'observations', label: 'Observations', icon: 'O' },
  { id: 'stakes', label: 'Stakes', icon: '♥' },
  { id: 'consistency', label: 'Consistency', icon: '⟷' },
  { id: 'narration', label: 'Narration', icon: '⋯' },
];

export function SelfDevelopment() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'identity'
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

  // Fetch summary stats for header
  const { data: selfModel } = useQuery({
    queryKey: ['self-model-summary'],
    queryFn: () => selfModelApi.get().then((r) => r.data),
    retry: false,
  });

  const { data: milestoneSummary } = useQuery({
    queryKey: ['milestone-summary'],
    queryFn: () => developmentApi.getMilestoneSummary().then((r) => r.data),
    retry: false,
  });

  const { data: pendingEdges } = useQuery({
    queryKey: ['pending-edges'],
    queryFn: () => selfModelApi.getPendingEdges().then((r) => r.data),
    retry: false,
  });

  const profile = selfModel?.profile;
  const summary = milestoneSummary?.summary || {};
  const pendingCount = pendingEdges?.pending_edges?.length || 0;

  return (
    <div className="self-development-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Self-Development</h1>
          <p className="subtitle">
            Cass's identity, growth edges, and cognitive evolution
          </p>
        </div>
        <div className="header-stats">
          <div className="stat-pill">
            <span className="stat-value">{profile?.identity_statements?.length || 0}</span>
            <span className="stat-label">identity</span>
          </div>
          <div className="stat-pill">
            <span className="stat-value">{summary.total_milestones || 0}</span>
            <span className="stat-label">milestones</span>
          </div>
          {pendingCount > 0 && (
            <div className="stat-pill pending">
              <span className="stat-value">{pendingCount}</span>
              <span className="stat-label">pending</span>
            </div>
          )}
        </div>
      </header>

      <div className="tabs-container" role="tablist" aria-label="Self-development views">
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
        {activeTab === 'identity' && <SelfModelTab />}
        {activeTab === 'timeline' && <DevelopmentTimelineTab view="timeline" />}
        {activeTab === 'snapshots' && <DevelopmentTimelineTab view="snapshots" />}
        {activeTab === 'observations' && <DevelopmentTimelineTab view="observations" />}
        {activeTab === 'stakes' && <StakesTab />}
        {activeTab === 'consistency' && <ConsistencyTab />}
        {activeTab === 'narration' && <NarrationPatternsTab />}
      </div>
    </div>
  );
}
