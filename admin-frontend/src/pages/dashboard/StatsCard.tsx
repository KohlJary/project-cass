/**
 * StatsCard - System statistics (Column 2)
 */
import type { DashboardData } from '../../api/graphql';
import { StatCard } from '../../components/shared';

interface StatsCardProps {
  data: DashboardData;
}

export function StatsCard({ data }: StatsCardProps) {
  const { memory, conversations, selfModel } = data;

  return (
    <div className="dashboard-card stats-card">
      <h3>System Stats</h3>

      <div className="stats-grid">
        <StatCard icon="*" value={memory.totalEmbeddings} label="Memories" />
        <StatCard icon="#" value={memory.totalJournals} label="Journals" />
        <StatCard icon=">" value={conversations.totalConversations} label="Conversations" />
        <StatCard icon="@" value={selfModel.observations} label="Observations" />
      </div>

      <div className="stats-section">
        <h4>Self-Model Graph</h4>
        <div className="graph-stats">
          <span>{selfModel.totalNodes} nodes</span>
          <span className="separator">|</span>
          <span>{selfModel.totalEdges} edges</span>
        </div>
      </div>

      <div className="stats-section">
        <h4>Narrative</h4>
        <div className="narrative-stats">
          <div className="narrative-item">
            <span className="narrative-count">{memory.threadsActive}</span>
            <span className="narrative-label">Active Threads</span>
          </div>
          <div className="narrative-item">
            <span className="narrative-count">{memory.questionsOpen}</span>
            <span className="narrative-label">Open Questions</span>
          </div>
        </div>
      </div>
    </div>
  );
}
