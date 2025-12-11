import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { developmentApi } from '../../api/client';

interface Milestone {
  id: string;
  timestamp: string;
  milestone_type: string;
  category: string;
  title: string;
  description: string;
  significance: string;
  acknowledged: boolean;
  developmental_stage: string;
  evidence_summary?: string;
}

interface Snapshot {
  id: string;
  timestamp: string;
  period_start: string;
  period_end: string;
  developmental_stage: string;
  avg_response_length: number;
  question_frequency: number;
  self_reference_rate: number;
  experience_claims: number;
  opinions_expressed: number;
  conversations_analyzed: number;
  messages_analyzed: number;
  unique_users: number;
}

interface Observation {
  id: string;
  timestamp: string;
  observation: string;
  category: string;
  confidence: number;
  developmental_stage: string;
  influence_source: string;
}

interface TrendPoint {
  timestamp: string;
  period_start: string;
  period_end: string;
  value: number;
}

type ViewType = 'timeline' | 'snapshots' | 'observations';
type MetricType = 'avg_response_length' | 'question_frequency' | 'self_reference_rate' | 'opinions_expressed';

interface DevelopmentTimelineTabProps {
  view: ViewType;
}

export function DevelopmentTimelineTab({ view }: DevelopmentTimelineTabProps) {
  const [selectedMetric, setSelectedMetric] = useState<MetricType>('avg_response_length');
  const queryClient = useQueryClient();

  const { data: milestonesData } = useQuery({
    queryKey: ['milestones'],
    queryFn: () => developmentApi.getMilestones({ limit: 50 }).then(r => r.data),
    retry: false,
  });

  const { data: snapshotsData } = useQuery({
    queryKey: ['snapshots'],
    queryFn: () => developmentApi.getSnapshots(20).then(r => r.data),
    retry: false,
  });

  const { data: latestSnapshot } = useQuery({
    queryKey: ['latest-snapshot'],
    queryFn: () => developmentApi.getLatestSnapshot().then(r => r.data).catch(() => null),
    retry: false,
    enabled: view === 'snapshots',
  });

  const { data: trendData } = useQuery({
    queryKey: ['trend', selectedMetric],
    queryFn: () => developmentApi.getSnapshotTrend(selectedMetric, 10).then(r => r.data),
    retry: false,
    enabled: view === 'snapshots',
  });

  const { data: observationsData } = useQuery({
    queryKey: ['observations'],
    queryFn: () => developmentApi.getObservations({ limit: 50 }).then(r => r.data),
    retry: false,
    enabled: view === 'observations',
  });

  const checkMilestonesMutation = useMutation({
    mutationFn: () => developmentApi.checkMilestones(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['milestones'] });
      queryClient.invalidateQueries({ queryKey: ['milestone-summary'] });
    },
  });

  const acknowledgeMilestone = useMutation({
    mutationFn: (id: string) => developmentApi.acknowledgeMilestone(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['milestones'] });
    },
  });

  const milestones: Milestone[] = milestonesData?.milestones || [];
  const snapshots: Snapshot[] = snapshotsData?.snapshots || [];
  const observations: Observation[] = observationsData?.observations || [];
  const trend: TrendPoint[] = trendData?.trend || [];

  const significanceIcon = (sig: string) => {
    switch (sig) {
      case 'critical': return '★';
      case 'high': return '☆';
      case 'medium': return '✧';
      default: return '·';
    }
  };

  const formatDate = (iso: string) => {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString();
  };

  const metricLabels: Record<MetricType, string> = {
    avg_response_length: 'Avg Response Length',
    question_frequency: 'Question Frequency',
    self_reference_rate: 'Self-Reference Rate',
    opinions_expressed: 'Opinions Expressed',
  };

  if (view === 'timeline') {
    return (
      <div className="timeline-view">
        <div className="timeline-controls">
          <button
            className="check-btn"
            onClick={() => checkMilestonesMutation.mutate()}
            disabled={checkMilestonesMutation.isPending}
          >
            {checkMilestonesMutation.isPending ? 'Checking...' : 'Check for New Milestones'}
          </button>
        </div>

        <div className="timeline">
          {milestones.slice(0, 20).map((m) => (
            <div key={m.id} className={`timeline-item ${m.significance}`}>
              <div className="timeline-marker">
                <span className="timeline-icon">{significanceIcon(m.significance)}</span>
                <div className="timeline-line" />
              </div>
              <div className="timeline-content">
                <div className="timeline-header">
                  <span className="timeline-title">{m.title}</span>
                  <span className="timeline-date">{formatDate(m.timestamp)}</span>
                </div>
                <p className="timeline-desc">{m.description}</p>
                <div className="timeline-meta">
                  <span className="meta-tag type">{m.milestone_type}</span>
                  <span className="meta-tag stage">{m.developmental_stage}</span>
                  {!m.acknowledged && (
                    <button
                      className="ack-btn"
                      onClick={() => acknowledgeMilestone.mutate(m.id)}
                    >
                      Acknowledge
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
          {milestones.length === 0 && (
            <div className="empty-state">
              <p>No milestones recorded yet</p>
              <p className="hint">Click "Check for New Milestones" to detect them</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (view === 'snapshots') {
    return (
      <div className="snapshots-view">
        {/* Metric selector */}
        <div className="metric-selector">
          <span className="selector-label">Trend metric:</span>
          {(Object.keys(metricLabels) as MetricType[]).map(metric => (
            <button
              key={metric}
              className={`metric-btn ${selectedMetric === metric ? 'active' : ''}`}
              onClick={() => setSelectedMetric(metric)}
            >
              {metricLabels[metric]}
            </button>
          ))}
        </div>

        {/* Trend chart */}
        {trend.length > 0 && (
          <div className="trend-chart">
            <h3>Trend: {metricLabels[selectedMetric]}</h3>
            <div className="chart-bars">
              {trend.map((point, i) => {
                const maxValue = Math.max(...trend.map(p => p.value));
                const height = maxValue > 0 ? (point.value / maxValue) * 100 : 0;
                return (
                  <div key={i} className="chart-bar-container">
                    <div
                      className="chart-bar"
                      style={{ height: `${height}%` }}
                      title={`${point.value.toFixed(2)}`}
                    />
                    <span className="bar-label">{formatDate(point.period_start)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Latest snapshot */}
        {latestSnapshot?.snapshot && (
          <div className="latest-snapshot">
            <h3>Latest Snapshot</h3>
            <div className="snapshot-grid">
              <div className="snapshot-stat">
                <span className="stat-value">{latestSnapshot.snapshot.avg_response_length?.toFixed(0) || 0}</span>
                <span className="stat-label">Avg Response Length</span>
              </div>
              <div className="snapshot-stat">
                <span className="stat-value">{latestSnapshot.snapshot.question_frequency?.toFixed(2) || 0}</span>
                <span className="stat-label">Questions/Response</span>
              </div>
              <div className="snapshot-stat">
                <span className="stat-value">{((latestSnapshot.snapshot.self_reference_rate || 0) * 100).toFixed(2)}%</span>
                <span className="stat-label">Self-Reference Rate</span>
              </div>
              <div className="snapshot-stat">
                <span className="stat-value">{latestSnapshot.snapshot.opinions_expressed || 0}</span>
                <span className="stat-label">Opinions Expressed</span>
              </div>
            </div>
          </div>
        )}

        {/* Snapshot list */}
        <div className="snapshots-list">
          <h3>All Snapshots</h3>
          {snapshots.map(s => (
            <div key={s.id} className="snapshot-item">
              <div className="snapshot-header">
                <span className="snapshot-id">{s.id.slice(0, 8)}</span>
                <span className="snapshot-period">
                  {formatDate(s.period_start)} - {formatDate(s.period_end)}
                </span>
              </div>
              <div className="snapshot-mini-stats">
                <span>Stage: {s.developmental_stage}</span>
                <span>Messages: {s.messages_analyzed}</span>
                <span>Users: {s.unique_users}</span>
              </div>
            </div>
          ))}
          {snapshots.length === 0 && (
            <div className="empty-state small">
              <p>No snapshots yet</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (view === 'observations') {
    return (
      <div className="observations-view">
        {/* Category distribution */}
        <div className="category-summary">
          {Object.entries(
            observations.reduce((acc: Record<string, number>, obs) => {
              acc[obs.category] = (acc[obs.category] || 0) + 1;
              return acc;
            }, {})
          ).map(([cat, count]) => (
            <div key={cat} className="category-chip">
              <span className="cat-name">{cat}</span>
              <span className="cat-count">{count}</span>
            </div>
          ))}
        </div>

        {/* Observations list */}
        <div className="observations-list">
          {observations.map(obs => (
            <div key={obs.id} className="observation-item">
              <div className="obs-header">
                <span className={`obs-category ${obs.category}`}>{obs.category}</span>
                <span className="obs-confidence">{(obs.confidence * 100).toFixed(0)}%</span>
                <span className="obs-date">{formatDate(obs.timestamp)}</span>
              </div>
              <p className="obs-text">{obs.observation}</p>
              <div className="obs-meta">
                <span className="obs-stage">{obs.developmental_stage}</span>
                <span className="obs-source">{obs.influence_source}</span>
              </div>
            </div>
          ))}
          {observations.length === 0 && (
            <div className="empty-state">
              <p>No observations recorded</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}
