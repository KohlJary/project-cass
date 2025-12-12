import { useQuery } from '@tanstack/react-query';
import { sentienceApi } from '../../api/client';
import { useState } from 'react';

interface Stake {
  id: string;
  outcome: string;
  why_it_matters: string;
  domain: string;
  intensity: string;
  evidence?: string[];
  created_at: string;
}

type DomainFilter = 'all' | 'personal' | 'technical' | 'relational' | 'ethical' | 'principle';
type IntensityFilter = 'all' | 'core' | 'significant' | 'emerging';

export function StakesTab() {
  const [domainFilter, setDomainFilter] = useState<DomainFilter>('all');
  const [intensityFilter, setIntensityFilter] = useState<IntensityFilter>('all');
  const [expandedStake, setExpandedStake] = useState<string | null>(null);

  const { data: stakesData, isLoading, error } = useQuery({
    queryKey: ['stakes', domainFilter, intensityFilter],
    queryFn: () => sentienceApi.getStakes({
      domain: domainFilter === 'all' ? undefined : domainFilter,
      intensity: intensityFilter === 'all' ? undefined : intensityFilter,
      limit: 50,
    }).then((r) => r.data),
    retry: false,
  });

  const { data: statsData } = useQuery({
    queryKey: ['stakes-stats'],
    queryFn: () => sentienceApi.getStakesStats().then((r) => r.data),
    retry: false,
  });

  const stakes = stakesData?.stakes || [];
  const stats = statsData || { total: 0, by_domain: {}, by_intensity: {} };

  const getIntensityColor = (intensity: string) => {
    switch (intensity) {
      case 'core': return '#c792ea';
      case 'significant': return '#89ddff';
      case 'emerging': return '#c3e88d';
      default: return '#888';
    }
  };

  if (isLoading) {
    return <div className="loading-state">Loading stakes...</div>;
  }

  if (error) {
    return <div className="error-state">Failed to load stakes</div>;
  }

  return (
    <div className="stakes-tab">
      {/* Stats Header */}
      <div className="stakes-stats">
        <div className="stat-pill">
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">total stakes</span>
        </div>
        {Object.entries(stats.by_intensity as Record<string, number>).map(([intensity, count]) => (
          <div key={intensity} className="stat-pill">
            <span className="stat-value" style={{ color: getIntensityColor(intensity) }}>{count}</span>
            <span className="stat-label">{intensity}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <select
          className="filter-select"
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value as DomainFilter)}
        >
          <option value="all">All Domains</option>
          <option value="personal">Personal</option>
          <option value="technical">Technical</option>
          <option value="relational">Relational</option>
          <option value="ethical">Ethical</option>
          <option value="principle">Principle</option>
        </select>

        <select
          className="filter-select"
          value={intensityFilter}
          onChange={(e) => setIntensityFilter(e.target.value as IntensityFilter)}
        >
          <option value="all">All Intensities</option>
          <option value="core">Core</option>
          <option value="significant">Significant</option>
          <option value="emerging">Emerging</option>
        </select>
      </div>

      {/* Stakes Grid */}
      {stakes.length === 0 ? (
        <div className="empty-state">
          <p>No stakes documented yet.</p>
          <p className="hint">Cass will record things she authentically cares about using the document_stake tool.</p>
        </div>
      ) : (
        <div className="stakes-grid">
          {stakes.map((stake: Stake) => (
            <div
              key={stake.id}
              className={`stake-card ${expandedStake === stake.id ? 'expanded' : ''}`}
              onClick={() => setExpandedStake(expandedStake === stake.id ? null : stake.id)}
            >
              <div className="stake-header">
                <span
                  className="intensity-badge"
                  style={{ backgroundColor: `${getIntensityColor(stake.intensity)}20`, color: getIntensityColor(stake.intensity) }}
                >
                  {stake.intensity}
                </span>
                <span className="domain-badge">{stake.domain}</span>
              </div>

              <h3 className="stake-outcome">{stake.outcome}</h3>
              <p className="stake-why">{stake.why_it_matters}</p>

              {expandedStake === stake.id && stake.evidence && stake.evidence.length > 0 && (
                <div className="stake-evidence">
                  <h4>Evidence</h4>
                  <ul>
                    {stake.evidence.map((ev, idx) => (
                      <li key={idx}>{ev}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="stake-footer">
                <span className="stake-date">
                  {new Date(stake.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
