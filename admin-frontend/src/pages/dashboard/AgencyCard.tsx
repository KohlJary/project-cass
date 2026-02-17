/**
 * AgencyCard - Summary card for Dashboard with link to full Agency page
 */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { outreachApi } from '../../api/client';
import { fetchUnifiedGoals } from '../../api/graphql';
import type { UnifiedGoal } from '../../api/graphql';

interface OutreachStats {
  total_drafts: number;
  pending_review: number;
  sent_count: number;
  published_count: number;
  response_rate: number;
  autonomy_by_type: Record<string, string>;
}

interface TrackRecord {
  draft_type: string;
  total_reviews: number;
  approvals: number;
  approval_rate: number;
  graduated: boolean;
  autonomy_level: string;
}

export function AgencyCard() {
  // Fetch goals
  const { data: goalsData } = useQuery({
    queryKey: ['agency-card', 'goals'],
    queryFn: async () => {
      const result = await fetchUnifiedGoals({ includeCompleted: false });
      return result.unifiedGoals;
    },
    staleTime: 30000,
  });

  // Fetch outreach stats
  const { data: statsData } = useQuery<OutreachStats>({
    queryKey: ['outreach-stats'],
    queryFn: () => outreachApi.getStats().then(r => r.data),
    staleTime: 30000,
  });

  // Fetch track records
  const { data: trackRecordsData } = useQuery<Record<string, TrackRecord>>({
    queryKey: ['track-records'],
    queryFn: () => outreachApi.getTrackRecords().then(r => r.data),
    staleTime: 30000,
  });

  const goals: UnifiedGoal[] = goalsData?.goals || [];
  const stats = statsData;
  const trackRecords = trackRecordsData ? Object.values(trackRecordsData) : [];

  const activeGoals = goals.filter(g => g.status === 'active').length;
  const selfInitiated = goals.filter(g => g.emergenceType === 'self-initiated').length;
  const pendingReview = stats?.pending_review || 0;

  return (
    <div className="dashboard-card agency-card">
      <div className="card-header">
        <h3>Agency</h3>
        <Link to="/agency" className="view-all-link">View All →</Link>
      </div>

      <div className="agency-quick-stats">
        <div className="quick-stat">
          <span className="stat-value">{activeGoals}</span>
          <span className="stat-label">Active Goals</span>
        </div>
        <div className="quick-stat">
          <span className="stat-value">{selfInitiated}</span>
          <span className="stat-label">Self-Initiated</span>
        </div>
        <div className="quick-stat highlight">
          <span className="stat-value">{pendingReview}</span>
          <span className="stat-label">Pending Review</span>
        </div>
      </div>

      {/* Autonomy Progress */}
      {trackRecords.length > 0 && (
        <div className="autonomy-preview">
          <span className="preview-label">Autonomy:</span>
          <div className="autonomy-badges">
            {trackRecords.map(record => (
              <span
                key={record.draft_type}
                className={`autonomy-badge ${record.graduated ? 'graduated' : 'learning'}`}
                title={`${record.draft_type}: ${record.graduated ? 'Graduated' : `${(record.approval_rate * 100).toFixed(0)}% approval`}`}
              >
                {record.draft_type.replace('_', ' ')}
                {record.graduated && ' ✓'}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Call to action if pending reviews */}
      {pendingReview > 0 && (
        <Link to="/agency" className="review-cta">
          <span className="cta-icon">◈</span>
          <span className="cta-text">{pendingReview} item{pendingReview > 1 ? 's' : ''} need{pendingReview === 1 ? 's' : ''} review</span>
        </Link>
      )}

      {/* Empty state */}
      {goals.length === 0 && !stats && (
        <div className="agency-empty">
          <p>No agency activity yet.</p>
          <p className="empty-hint">Goals and outreach will appear here.</p>
        </div>
      )}
    </div>
  );
}
