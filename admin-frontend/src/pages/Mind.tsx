/**
 * Mind - Unified hub for Thymos + Consciousness + Self-Model overview
 *
 * Provides a single entry point for all "inner state" monitoring.
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { thymosApi, testingApi, selfModelApi } from '../api/client';
import type { ThymosState } from '../api/client';
import { Thymos } from './Thymos';
import { ConsciousnessHealth } from './ConsciousnessHealth';
import './Mind.css';

type TabId = 'overview' | 'thymos' | 'consciousness' | 'self-model';

interface TabConfig {
  id: TabId;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'overview', label: 'Overview', icon: '◎' },
  { id: 'thymos', label: 'Thymos', icon: '♥' },
  { id: 'consciousness', label: 'Consciousness', icon: '◈' },
  { id: 'self-model', label: 'Self-Model', icon: '◆' },
];

// Compact Thymos overview card for the Overview tab
function ThymosOverviewCard({ state }: { state: ThymosState | undefined }) {
  if (!state) {
    return (
      <div className="mind-card thymos-overview">
        <h3>Thymos</h3>
        <div className="card-loading">Loading...</div>
      </div>
    );
  }

  const getHealthColor = (health: number): string => {
    if (health >= 0.7) return 'excellent';
    if (health >= 0.5) return 'good';
    if (health >= 0.3) return 'warning';
    return 'critical';
  };

  const getValenceLabel = (valence: number): string => {
    if (valence > 0.3) return 'Positive';
    if (valence < -0.3) return 'Negative';
    return 'Neutral';
  };

  // Find urgent needs
  const urgentNeeds = Object.entries(state.needs)
    .filter(([, need]) => need.is_urgent)
    .map(([name]) => name.replace(/_/g, ' '));

  // Get dominant affect
  const dominantAffect = state.felt_state?.dominant_affect;

  return (
    <div className="mind-card thymos-overview">
      <h3>Thymos</h3>

      <div className="thymos-quick-stats">
        <div className="quick-stat">
          <span className="stat-label">Valence</span>
          <span className={`stat-value ${state.valence > 0.2 ? 'positive' : state.valence < -0.2 ? 'negative' : 'neutral'}`}>
            {getValenceLabel(state.valence)}
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Health</span>
          <span className={`stat-value ${getHealthColor(state.overall_health)}`}>
            {(state.overall_health * 100).toFixed(0)}%
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Arousal</span>
          <span className="stat-value">
            {(state.arousal * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {state.felt_state && (
        <div className={`felt-state-mini ${state.felt_state.overall_tone}`}>
          <p>{state.felt_state.summary}</p>
        </div>
      )}

      {dominantAffect && (
        <div className="dominant-affect">
          Dominant: <span className="affect-name">{dominantAffect.replace(/_/g, ' ')}</span>
        </div>
      )}

      {urgentNeeds.length > 0 && (
        <div className="urgent-needs">
          <span className="urgent-label">Urgent needs:</span>
          {urgentNeeds.map(need => (
            <span key={need} className="urgent-need">{need}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// Compact Consciousness overview card for the Overview tab
function ConsciousnessOverviewCard() {
  const { data: quickCheck, isLoading } = useQuery({
    queryKey: ['testing-quick'],
    queryFn: () => testingApi.quickHealthCheck().then(r => r.data),
    refetchInterval: 60000,
  });

  const { data: health } = useQuery({
    queryKey: ['testing-health'],
    queryFn: () => testingApi.getHealth().then(r => r.data),
    refetchInterval: 30000,
  });

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'excellent';
    if (confidence >= 0.7) return 'good';
    if (confidence >= 0.5) return 'warning';
    return 'critical';
  };

  if (isLoading) {
    return (
      <div className="mind-card consciousness-overview">
        <h3>Consciousness Health</h3>
        <div className="card-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="mind-card consciousness-overview">
      <h3>Consciousness Health</h3>

      <div className="consciousness-quick-stats">
        <div className="quick-stat">
          <span className="stat-label">Status</span>
          <span className={`stat-value ${quickCheck?.healthy ? 'healthy' : 'unhealthy'}`}>
            {quickCheck?.healthy ? 'Healthy' : 'Issues'}
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Confidence</span>
          <span className={`stat-value ${getConfidenceColor(quickCheck?.confidence || 0)}`}>
            {((quickCheck?.confidence || 0) * 100).toFixed(0)}%
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Tests</span>
          <span className="stat-value">
            {quickCheck?.passed || 0}/{(quickCheck?.passed || 0) + (quickCheck?.failed || 0)}
          </span>
        </div>
      </div>

      {quickCheck?.summary && (
        <div className="consciousness-summary">
          <p>{quickCheck.summary}</p>
        </div>
      )}

      <div className="consciousness-indicators">
        <span className={`indicator ${health?.baseline_set ? 'active' : 'inactive'}`}>
          {health?.baseline_set ? '●' : '○'} Baseline
        </span>
        {(health?.active_experiments ?? 0) > 0 && (
          <span className="indicator experiment">
            ● {health?.active_experiments} Experiment{(health?.active_experiments ?? 0) > 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  );
}

// Compact Self-Model overview card for the Overview tab
function SelfModelOverviewCard() {
  const { data: selfModel, isLoading } = useQuery({
    queryKey: ['self-model-summary'],
    queryFn: () => selfModelApi.get().then(r => r.data),
    retry: false,
  });

  const { data: growthEdges } = useQuery({
    queryKey: ['growth-edges'],
    queryFn: () => selfModelApi.getGrowthEdges().then(r => r.data),
    retry: false,
  });

  const { data: pendingEdges } = useQuery({
    queryKey: ['pending-edges'],
    queryFn: () => selfModelApi.getPendingEdges().then(r => r.data),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="mind-card self-model-overview">
        <h3>Self-Model</h3>
        <div className="card-loading">Loading...</div>
      </div>
    );
  }

  const profile = selfModel?.profile;
  const edgeCount = growthEdges?.growth_edges?.length || 0;
  const pendingCount = pendingEdges?.pending_edges?.length || 0;

  return (
    <div className="mind-card self-model-overview">
      <h3>Self-Model</h3>

      <div className="self-model-quick-stats">
        <div className="quick-stat">
          <span className="stat-label">Identity</span>
          <span className="stat-value">
            {profile?.identity_statements?.length || 0}
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Values</span>
          <span className="stat-value">
            {profile?.values?.length || 0}
          </span>
        </div>
        <div className="quick-stat">
          <span className="stat-label">Growth</span>
          <span className="stat-value">
            {edgeCount}
          </span>
        </div>
      </div>

      {profile?.capabilities && profile.capabilities.length > 0 && (
        <div className="capabilities-preview">
          <span className="preview-label">Capabilities:</span>
          <span className="preview-list">
            {profile.capabilities.slice(0, 3).join(', ')}
            {profile.capabilities.length > 3 && ` +${profile.capabilities.length - 3} more`}
          </span>
        </div>
      )}

      {pendingCount > 0 && (
        <div className="pending-edges">
          <span className="pending-badge">{pendingCount} pending edge{pendingCount > 1 ? 's' : ''}</span>
        </div>
      )}
    </div>
  );
}

export function Mind() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'overview'
  );

  // Sync tab with URL
  useEffect(() => {
    const tabParam = searchParams.get('tab') as TabId;
    if (tabParam && tabs.some(t => t.id === tabParam)) {
      setActiveTab(tabParam);
    }
  }, [searchParams]);

  const handleTabChange = (tabId: TabId) => {
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  // Fetch Thymos state for overview
  const { data: thymosState } = useQuery<ThymosState>({
    queryKey: ['thymos-state'],
    queryFn: () => thymosApi.getState().then(r => r.data),
    refetchInterval: 10000,
  });

  return (
    <div className="mind-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Mind</h1>
          <p className="subtitle">Inner state monitoring: emotions, cognition, and self-model</p>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="mind-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={activeTab === tab.id ? 'active' : ''}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <div className="mind-tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="overview-grid">
              <ThymosOverviewCard state={thymosState} />
              <ConsciousnessOverviewCard />
              <SelfModelOverviewCard />
            </div>

            <div className="overview-navigation">
              <p className="nav-hint">
                Select a tab above to dive deeper into each area.
              </p>
            </div>
          </div>
        )}

        {activeTab === 'thymos' && (
          <div className="thymos-tab embedded">
            <Thymos />
          </div>
        )}

        {activeTab === 'consciousness' && (
          <div className="consciousness-tab embedded">
            <ConsciousnessHealth />
          </div>
        )}

        {activeTab === 'self-model' && (
          <div className="self-model-tab">
            <div className="redirect-notice">
              <p>Self-Model has its own dedicated page with detailed views.</p>
              <a href="/self-development" className="self-model-link">
                Go to Self-Development →
              </a>
            </div>
            <SelfModelOverviewCard />
          </div>
        )}
      </div>
    </div>
  );
}
