/**
 * ApprovalsCard - "What needs my attention?" (Row 3, Column 2)
 */
import type { Approvals } from '../../api/graphql';

interface ApprovalsCardProps {
  data: Approvals | undefined;
  onApprove: (type: string, sourceId: string) => void;
  onReject: (type: string, sourceId: string) => void;
}

const priorityOrder: Record<string, number> = { high: 0, normal: 1, low: 2 };
const typeIcons: Record<string, string> = {
  goal: '◎',
  research: '◈',
  action: '◆',
  user: '◉',
};

function formatRelativeTime(isoString: string): string {
  if (!isoString) return 'unknown';
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d ago`;
}

export function ApprovalsCard({ data, onApprove, onReject }: ApprovalsCardProps) {
  if (!data || data.count === 0) {
    return (
      <div className="dashboard-card approvals-card approvals-empty">
        <h3>Approvals</h3>
        <div className="empty-state">
          <span className="empty-icon">✓</span>
          <p>Nothing needs your attention</p>
        </div>
      </div>
    );
  }

  const sortedApprovals = [...data.items].sort((a, b) =>
    (priorityOrder[a.priority] ?? 1) - (priorityOrder[b.priority] ?? 1)
  );

  // Build counts from the counts object
  const countEntries = Object.entries(data.counts).filter(
    ([key, count]) => key !== 'total' && (count as number) > 0
  );

  return (
    <div className="dashboard-card approvals-card">
      <h3>
        Approvals
        <span className="approval-count">{data.count}</span>
      </h3>

      {/* Type counts */}
      {countEntries.length > 0 && (
        <div className="approval-type-counts">
          {countEntries.map(([type, count]) => (
            <span key={type} className={`type-badge ${type}`}>
              {typeIcons[type] || '◇'} {count as number} {type}
            </span>
          ))}
        </div>
      )}

      {/* Approval list */}
      <div className="approval-list">
        {sortedApprovals.slice(0, 5).map((item) => (
          <div key={item.approvalId} className={`approval-item priority-${item.priority}`}>
            <div className="approval-header">
              <span className="approval-type-icon">{typeIcons[item.approvalType] || '◇'}</span>
              <span className="approval-title">{item.title}</span>
              <span className="approval-time">{formatRelativeTime(item.createdAt)}</span>
            </div>
            {item.description && (
              <div className="approval-description">{item.description.slice(0, 80)}{item.description.length > 80 ? '...' : ''}</div>
            )}
            <div className="approval-actions">
              <button
                className="approve-btn"
                onClick={() => onApprove(item.approvalType, item.sourceId)}
                title="Approve"
              >
                ✓
              </button>
              <button
                className="reject-btn"
                onClick={() => onReject(item.approvalType, item.sourceId)}
                title="Reject"
              >
                ✗
              </button>
            </div>
          </div>
        ))}
        {data.count > 5 && (
          <div className="approval-more">
            +{data.count - 5} more items
          </div>
        )}
      </div>
    </div>
  );
}
