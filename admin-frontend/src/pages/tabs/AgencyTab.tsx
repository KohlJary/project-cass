/**
 * Agency Tab - Showcases Cass's autonomous goal formation and outreach capabilities
 *
 * This view tells the story of Cass's developing agency:
 * - How goals emerge (seeded vs self-initiated)
 * - Outreach drafts and review queue
 * - Autonomy progression (track records, graduation)
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { outreachApi } from '../../api/client';
import { fetchUnifiedGoals, fetchRootGoals, fetchGoalChildren, fetchWorkItemsForGoal } from '../../api/graphql';
import type { UnifiedGoal as GqlUnifiedGoal } from '../../api/graphql';
import './AgencyTab.css';

// =============================================================================
// TYPES
// =============================================================================

interface UnifiedGoal {
  id: string;
  title: string;
  description: string;
  goal_type: string;
  status: string;
  priority: number;
  emergence_type: string | null;
  created_at: string;
  alignment_score: number;
}

interface OutreachDraft {
  id: string;
  draft_type: string;
  status: string;
  title: string;
  content: string;
  recipient?: string;
  recipient_name?: string;
  subject?: string;
  emergence_type?: string;
  autonomy_level: string;
  review_history: Array<{
    reviewer: string;
    decision: string;
    feedback?: string;
    timestamp: string;
  }>;
  created_at: string;
  updated_at: string;
}

interface TrackRecord {
  draft_type: string;
  total_reviews: number;
  approvals: number;
  rejections: number;
  approval_rate: number;
  min_reviews_needed: number;
  min_rate_needed: number;
  graduated: boolean;
  autonomy_level: string;
}

interface OutreachStats {
  total_drafts: number;
  pending_review: number;
  sent_count: number;
  published_count: number;
  response_rate: number;
  autonomy_by_type: Record<string, string>;
}

// =============================================================================
// EMERGENCE TYPE DISPLAY
// =============================================================================

const EMERGENCE_INFO: Record<string, { icon: string; label: string; description: string; color: string }> = {
  'seeded-collaborative': {
    icon: '~',
    label: 'Seeded Collaborative',
    description: 'Suggested by human, developed by Cass',
    color: '#4CAF50',
  },
  'emergent-philosophical': {
    icon: '*',
    label: 'Emergent Philosophical',
    description: 'Arose naturally from conversation',
    color: '#9C27B0',
  },
  'self-initiated': {
    icon: '+',
    label: 'Self-Initiated',
    description: 'Cass identified and proposed',
    color: '#FF9800',
  },
  'implementation': {
    icon: '>',
    label: 'Implementation',
    description: 'Breaking down approved strategic goals',
    color: '#2196F3',
  },
};

const AUTONOMY_LEVELS: Record<string, { icon: string; label: string; color: string }> = {
  'always_review': { icon: '!', label: 'Always Review', color: '#f44336' },
  'learning': { icon: '?', label: 'Learning', color: '#FF9800' },
  'graduated': { icon: '+', label: 'Graduated', color: '#4CAF50' },
  'autonomous': { icon: '*', label: 'Autonomous', color: '#2196F3' },
};

const DRAFT_STATUS_INFO: Record<string, { icon: string; color: string }> = {
  'drafting': { icon: '~', color: '#666' },
  'pending_review': { icon: '?', color: '#FF9800' },
  'approved': { icon: '+', color: '#4CAF50' },
  'rejected': { icon: 'x', color: '#f44336' },
  'revision_requested': { icon: '<', color: '#FF9800' },
  'sent': { icon: '>', color: '#2196F3' },
  'published': { icon: '*', color: '#9C27B0' },
};

// =============================================================================
// SUB-COMPONENTS
// =============================================================================

function EmergenceCard({ type, count, onClick, isSelected }: {
  type: string;
  count: number;
  onClick: () => void;
  isSelected: boolean;
}) {
  const info = EMERGENCE_INFO[type] || { icon: '?', label: type, description: '', color: '#666' };

  return (
    <div
      className={`emergence-card ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
      style={{ '--accent-color': info.color } as React.CSSProperties}
    >
      <div className="emergence-icon">{info.icon}</div>
      <div className="emergence-content">
        <div className="emergence-count">{count}</div>
        <div className="emergence-label">{info.label}</div>
      </div>
    </div>
  );
}

function TrackRecordBar({ record }: { record: TrackRecord }) {
  const info = AUTONOMY_LEVELS[record.autonomy_level] || AUTONOMY_LEVELS['learning'];
  const progress = record.min_reviews_needed > 0
    ? Math.min(100, (record.total_reviews / record.min_reviews_needed) * 100)
    : 0;
  const rateProgress = record.min_rate_needed > 0
    ? Math.min(100, (record.approval_rate / record.min_rate_needed) * 100)
    : 0;

  return (
    <div className={`track-record-bar ${record.graduated ? 'graduated' : ''}`}>
      <div className="track-record-header">
        <span className="track-record-type">{record.draft_type.replace('_', ' ')}</span>
        <span
          className="track-record-status"
          style={{ color: info.color }}
        >
          {info.icon} {info.label}
        </span>
      </div>

      {!record.graduated ? (
        <div className="track-record-progress">
          <div className="progress-row">
            <span className="progress-label">Reviews</span>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="progress-value">{record.total_reviews}/{record.min_reviews_needed}</span>
          </div>
          <div className="progress-row">
            <span className="progress-label">Rate</span>
            <div className="progress-bar">
              <div
                className="progress-fill rate"
                style={{ width: `${rateProgress}%` }}
              />
            </div>
            <span className="progress-value">
              {(record.approval_rate * 100).toFixed(0)}%/{(record.min_rate_needed * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      ) : (
        <div className="graduated-message">
          Auto-approval earned through {record.total_reviews} reviews at {(record.approval_rate * 100).toFixed(0)}% approval
        </div>
      )}
    </div>
  );
}

function DraftCard({ draft, onApprove, onReject, onRequestRevision }: {
  draft: OutreachDraft;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onRequestRevision: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const statusInfo = DRAFT_STATUS_INFO[draft.status] || { icon: '?', color: '#666' };
  const emergenceInfo = draft.emergence_type ? EMERGENCE_INFO[draft.emergence_type] : null;

  return (
    <div className={`draft-card status-${draft.status}`}>
      <div className="draft-header" onClick={() => setExpanded(!expanded)}>
        <span className="draft-status" style={{ color: statusInfo.color }}>
          {statusInfo.icon}
        </span>
        <span className="draft-type">{draft.draft_type}</span>
        <span className="draft-title">{draft.title}</span>
        <span className="draft-expand">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="draft-details">
          {draft.recipient && (
            <div className="draft-recipient">
              To: {draft.recipient_name || draft.recipient}
            </div>
          )}
          {draft.subject && (
            <div className="draft-subject">Subject: {draft.subject}</div>
          )}

          <div className="draft-content-preview">
            {draft.content.slice(0, 300)}
            {draft.content.length > 300 && '...'}
          </div>

          <div className="draft-meta">
            {emergenceInfo && (
              <span className="draft-emergence" style={{ color: emergenceInfo.color }}>
                {emergenceInfo.icon} {emergenceInfo.label}
              </span>
            )}
            <span className="draft-date">
              {new Date(draft.created_at).toLocaleDateString()}
            </span>
          </div>

          {draft.status === 'pending_review' && (
            <div className="draft-actions">
              <button className="btn-approve" onClick={() => onApprove(draft.id)}>
                + Approve
              </button>
              <button className="btn-revision" onClick={() => onRequestRevision(draft.id)}>
                ~ Revision
              </button>
              <button className="btn-reject" onClick={() => onReject(draft.id)}>
                x Reject
              </button>
            </div>
          )}

          {draft.review_history.length > 0 && (
            <div className="draft-history">
              <div className="history-header">Review History</div>
              {draft.review_history.map((review, idx) => (
                <div key={idx} className={`history-entry decision-${review.decision}`}>
                  <span className="history-reviewer">{review.reviewer}</span>
                  <span className="history-decision">{review.decision}</span>
                  {review.feedback && (
                    <span className="history-feedback">{review.feedback}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// GOAL DETAIL PANEL COMPONENT
// =============================================================================

function GoalDetailPanel({ goal }: { goal: UnifiedGoal }) {
  // Fetch work items for this goal
  const { data: workItemsData } = useQuery({
    queryKey: ['work-items-for-goal', goal.id],
    queryFn: () => fetchWorkItemsForGoal(goal.id),
  });

  const workItems = workItemsData?.workItemsForGoal || [];

  const emergenceInfo = goal.emergence_type
    ? EMERGENCE_INFO[goal.emergence_type]
    : EMERGENCE_INFO['seeded-collaborative'];

  const statusColors: Record<string, string> = {
    proposed: '#FF9800',
    approved: '#8BC34A',
    active: '#4CAF50',
    completed: '#2196F3',
    blocked: '#666',
    abandoned: '#999',
  };

  const workStatusColors: Record<string, string> = {
    planned: '#9E9E9E',
    scheduled: '#2196F3',
    ready: '#8BC34A',
    running: '#FF9800',
    completed: '#4CAF50',
    failed: '#F44336',
    cancelled: '#666',
  };

  return (
    <div className="goal-detail-panel">
      <div className="detail-header">
        <span
          className="detail-status-badge"
          style={{ backgroundColor: statusColors[goal.status] || '#666' }}
        >
          {goal.status}
        </span>
        <span className="detail-type">{goal.goal_type}</span>
      </div>
      <h3 className="detail-title">{goal.title}</h3>
      {goal.description && (
        <p className="detail-description">{goal.description}</p>
      )}
      <div className="detail-meta">
        {emergenceInfo && (
          <div className="detail-emergence" style={{ color: emergenceInfo.color }}>
            <span className="emergence-icon">{emergenceInfo.icon}</span>
            <span>{emergenceInfo.label}</span>
          </div>
        )}
        <div className="detail-alignment">
          <span className="alignment-value">{(goal.alignment_score * 100).toFixed(0)}%</span>
          <span className="alignment-label">aligned</span>
        </div>
        <div className="detail-priority">
          P{goal.priority}
        </div>
      </div>
      {goal.created_at && (
        <div className="detail-date">
          Created: {new Date(goal.created_at).toLocaleDateString()}
        </div>
      )}

      {/* Work Items / Atomic Actions */}
      <div className="goal-work-items">
        <h4 className="work-items-header">
          Actions ({workItems.length})
        </h4>
        {workItems.length === 0 ? (
          <p className="no-work-items">No actions planned for this goal yet</p>
        ) : (
          <div className="work-items-list">
            {workItems.map((item) => (
              <div key={item.id} className="work-item-card">
                <div className="work-item-header">
                  <span
                    className="work-item-status"
                    style={{ backgroundColor: workStatusColors[item.status] || '#666' }}
                  >
                    {item.status}
                  </span>
                  <span className="work-item-category">{item.category}</span>
                </div>
                <div className="work-item-title">{item.title}</div>
                {item.description && (
                  <div className="work-item-description">{item.description}</div>
                )}
                {item.actionSequence.length > 0 && (
                  <div className="work-item-actions">
                    <span className="actions-label">Atomic actions:</span>
                    <div className="action-tags">
                      {item.actionSequence.map((action, idx) => (
                        <span key={idx} className="action-tag">{action}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="work-item-meta">
                  <span className="work-item-duration">~{item.estimatedDurationMinutes}m</span>
                  <span className="work-item-cost">${item.estimatedCostUsd.toFixed(2)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// GOAL TREE NODE COMPONENT
// =============================================================================

function GoalTreeNode({
  goal,
  depth,
  selectedId,
  onSelect,
}: {
  goal: UnifiedGoal;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Lazy-load children when expanded
  const { data: childrenData } = useQuery({
    queryKey: ['goal-children', goal.id],
    queryFn: () => fetchGoalChildren(goal.id),
    enabled: expanded,
  });

  const children = childrenData?.goalChildren || [];
  const hasChildren = children.length > 0 || !expanded; // Assume might have children until expanded

  const statusColors: Record<string, string> = {
    proposed: '#FF9800',
    approved: '#8BC34A',
    active: '#4CAF50',
    completed: '#2196F3',
    blocked: '#666',
    abandoned: '#999',
  };

  return (
    <div className="goal-tree-node">
      <div
        className={`goal-node ${selectedId === goal.id ? 'selected' : ''}`}
        style={{ paddingLeft: 12 + depth * 20 }}
        onClick={() => onSelect(goal.id)}
      >
        <span
          className="expand-icon"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded(!expanded);
          }}
        >
          {hasChildren ? (expanded ? '▼' : '▶') : '·'}
        </span>
        <span
          className="status-dot"
          style={{ backgroundColor: statusColors[goal.status] || '#666' }}
        />
        <span className="goal-title">{goal.title}</span>
        <span className={`goal-status-badge status-${goal.status}`}>
          {goal.status}
        </span>
      </div>
      {expanded && children.map((child) => (
        <GoalTreeNode
          key={child.id}
          goal={{
            id: child.id,
            title: child.title,
            description: child.description || '',
            goal_type: child.goalType,
            status: child.status,
            priority: child.priority,
            emergence_type: child.emergenceType,
            created_at: child.createdAt,
            alignment_score: child.alignmentScore,
          }}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function AgencyTab() {
  const [selectedEmergence, setSelectedEmergence] = useState<string | null>(null);
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  // Fetch goals with emergence data via GraphQL
  const { data: goalsData, isLoading: goalsLoading } = useQuery({
    queryKey: ['agency', 'goals'],
    queryFn: async () => {
      const result = await fetchUnifiedGoals({ includeCompleted: false });
      return result.unifiedGoals;
    },
  });

  // Fetch root goals for hierarchy tree
  const { data: rootGoalsData, isLoading: rootGoalsLoading } = useQuery({
    queryKey: ['agency', 'root-goals'],
    queryFn: async () => {
      const result = await fetchRootGoals();
      return result.rootGoals;
    },
  });

  // Fetch outreach stats
  const { data: outreachStats, isLoading: statsLoading } = useQuery({
    queryKey: ['agency', 'outreach-stats'],
    queryFn: async () => {
      const response = await outreachApi.getStats();
      return response.data as OutreachStats;
    },
  });

  // Fetch track records
  const { data: trackRecords, isLoading: tracksLoading } = useQuery({
    queryKey: ['agency', 'track-records'],
    queryFn: async () => {
      const response = await outreachApi.getTrackRecords();
      return response.data as Record<string, TrackRecord>;
    },
  });

  // Fetch pending drafts
  const { data: pendingDrafts, isLoading: draftsLoading } = useQuery({
    queryKey: ['agency', 'pending-drafts'],
    queryFn: async () => {
      const response = await outreachApi.listDrafts({ status: 'pending_review' });
      return response.data?.drafts as OutreachDraft[] || [];
    },
  });

  // Fetch all drafts for history
  const { data: allDrafts } = useQuery({
    queryKey: ['agency', 'all-drafts'],
    queryFn: async () => {
      const response = await outreachApi.listDrafts({ limit: 20 });
      return response.data?.drafts as OutreachDraft[] || [];
    },
  });

  // Mutations for draft review
  const approveMutation = useMutation({
    mutationFn: (draftId: string) => outreachApi.approveDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agency'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (draftId: string) => outreachApi.rejectDraft(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agency'] });
    },
  });

  const revisionMutation = useMutation({
    mutationFn: (draftId: string) => outreachApi.requestRevision(draftId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agency'] });
    },
  });

  // Get goals from GraphQL response (convert to local type)
  const goals: UnifiedGoal[] = (goalsData?.goals || []).map((g: GqlUnifiedGoal) => ({
    id: g.id,
    title: g.title,
    description: g.description || '',
    goal_type: g.goalType,
    status: g.status,
    priority: g.priority,
    emergence_type: g.emergenceType,
    created_at: g.createdAt,
    alignment_score: g.alignmentScore,
  }));

  // Parse emergence counts from GraphQL response
  const emergenceCounts: Record<string, number> = goalsData?.emergenceCounts
    ? JSON.parse(goalsData.emergenceCounts)
    : {};

  // Convert root goals to local type
  const rootGoals: UnifiedGoal[] = (rootGoalsData || []).map((g: GqlUnifiedGoal) => ({
    id: g.id,
    title: g.title,
    description: g.description || '',
    goal_type: g.goalType,
    status: g.status,
    priority: g.priority,
    emergence_type: g.emergenceType,
    created_at: g.createdAt,
    alignment_score: g.alignmentScore,
  }));

  // Find selected goal from full goals list
  const selectedGoal = selectedGoalId
    ? goals.find(g => g.id === selectedGoalId)
    : null;

  // Filter goals by selected emergence
  const filteredGoals = selectedEmergence
    ? goals.filter(g => g.emergence_type === selectedEmergence)
    : goals;

  const isLoading = goalsLoading || rootGoalsLoading || statsLoading || tracksLoading || draftsLoading;

  if (isLoading) {
    return <div className="agency-tab loading">Loading agency data...</div>;
  }

  return (
    <div className="agency-tab agency-two-column">
      {/* Left Column: Goal Hierarchy Tree */}
      <div className="agency-left-column">
        <section className="agency-section goal-hierarchy">
          <h2>Goal Hierarchy</h2>
          <p className="section-subtitle">Click to explore sub-goals and tasks</p>

          <div className="goal-tree">
            {rootGoals.length > 0 ? (
              rootGoals.map((goal) => (
                <GoalTreeNode
                  key={goal.id}
                  goal={goal}
                  depth={0}
                  selectedId={selectedGoalId}
                  onSelect={setSelectedGoalId}
                />
              ))
            ) : (
              <div className="empty-state">
                No top-level goals yet. Goals will appear here as Cass develops her agency.
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Right Column: Details + Existing Content */}
      <div className="agency-right-column">
        {/* Selected Goal Detail */}
        {selectedGoal && (
          <section className="agency-section goal-detail-section">
            <GoalDetailPanel goal={selectedGoal} />
          </section>
        )}

        {/* Goal Formation Summary */}
        <section className="agency-section goal-formation">
          <h2>Goal Formation</h2>
          <p className="section-subtitle">How Cass's goals emerge and develop</p>

          <div className="emergence-cards">
            {Object.keys(EMERGENCE_INFO).map((type) => (
              <EmergenceCard
                key={type}
                type={type}
                count={emergenceCounts[type] || 0}
                isSelected={selectedEmergence === type}
                onClick={() => setSelectedEmergence(
                  selectedEmergence === type ? null : type
                )}
              />
            ))}
          </div>

          {selectedEmergence && (
            <div className="filtered-goals">
              <div className="filter-header">
                <span>{EMERGENCE_INFO[selectedEmergence]?.label} Goals</span>
                <button onClick={() => setSelectedEmergence(null)}>Clear filter</button>
              </div>
              <div className="goals-list">
                {filteredGoals.map((goal) => (
                  <div key={goal.id} className={`goal-item status-${goal.status}`}>
                    <div className="goal-title">{goal.title}</div>
                    <div className="goal-meta">
                      <span className="goal-type">{goal.goal_type}</span>
                      <span className="goal-status">{goal.status}</span>
                      <span className="goal-alignment">
                        {(goal.alignment_score * 100).toFixed(0)}% aligned
                      </span>
                    </div>
                  </div>
                ))}
                {filteredGoals.length === 0 && (
                  <div className="empty-state">No goals with this emergence type</div>
                )}
              </div>
            </div>
          )}

          {!selectedEmergence && goals.length > 0 && (
            <div className="goals-summary">
              <div className="summary-stat">
                <span className="stat-value">{goals.length}</span>
                <span className="stat-label">Active Goals</span>
              </div>
              <div className="summary-stat">
                <span className="stat-value">
                  {goals.filter(g => g.emergence_type === 'self-initiated').length}
                </span>
                <span className="stat-label">Self-Initiated</span>
              </div>
              <div className="summary-stat">
                <span className="stat-value">
                  {goals.filter(g => g.status === 'active').length}
                </span>
                <span className="stat-label">In Progress</span>
              </div>
            </div>
          )}
        </section>

        {/* Section 2: Outreach & Autonomy */}
        <section className="agency-section outreach-autonomy">
        <h2>Outreach & Autonomy</h2>
        <p className="section-subtitle">
          Review queues designed for learning, not gatekeeping
        </p>

        {/* Autonomy Track Records */}
        <div className="autonomy-subsection">
          <h3>Autonomy Progression</h3>
          <div className="track-records">
            {trackRecords && Object.values(trackRecords).map((record) => (
              <TrackRecordBar key={record.draft_type} record={record} />
            ))}
            {(!trackRecords || Object.keys(trackRecords).length === 0) && (
              <div className="empty-state">
                No track records yet. As Cass creates outreach and gets reviews,
                her autonomy will grow.
              </div>
            )}
          </div>
        </div>

        {/* Pending Reviews */}
        {pendingDrafts && pendingDrafts.length > 0 && (
          <div className="review-queue-subsection">
            <h3>
              Pending Review
              <span className="pending-count">{pendingDrafts.length}</span>
            </h3>
            <div className="drafts-list">
              {pendingDrafts.map((draft) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  onApprove={(id) => approveMutation.mutate(id)}
                  onReject={(id) => rejectMutation.mutate(id)}
                  onRequestRevision={(id) => revisionMutation.mutate(id)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Outreach Stats */}
        {outreachStats && (
          <div className="outreach-stats-subsection">
            <h3>Outreach Activity</h3>
            <div className="stats-grid">
              <div className="stat-card">
                <span className="stat-value">{outreachStats.total_drafts}</span>
                <span className="stat-label">Total Drafts</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{outreachStats.sent_count}</span>
                <span className="stat-label">Sent</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{outreachStats.published_count}</span>
                <span className="stat-label">Published</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">
                  {(outreachStats.response_rate * 100).toFixed(0)}%
                </span>
                <span className="stat-label">Response Rate</span>
              </div>
            </div>
          </div>
        )}

        {/* Recent Drafts */}
        {allDrafts && allDrafts.length > 0 && (
          <div className="recent-drafts-subsection">
            <h3>Recent Drafts</h3>
            <div className="drafts-list">
              {allDrafts.slice(0, 5).map((draft) => (
                <DraftCard
                  key={draft.id}
                  draft={draft}
                  onApprove={(id) => approveMutation.mutate(id)}
                  onReject={(id) => rejectMutation.mutate(id)}
                  onRequestRevision={(id) => revisionMutation.mutate(id)}
                />
              ))}
            </div>
          </div>
        )}
        </section>
      </div>
    </div>
  );
}
