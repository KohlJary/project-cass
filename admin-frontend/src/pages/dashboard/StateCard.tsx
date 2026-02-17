/**
 * StateCard - Global state overview (Column 1)
 */
import type { DashboardData } from '../../api/graphql';
import { EmotionalBar } from '../../components/shared';

interface StateCardProps {
  data: DashboardData;
}

const activityIcons: Record<string, string> = {
  idle: '~',
  chat: '>',
  research: '*',
  reflection: '#',
  synthesis: '+',
  dreaming: '@',
  writing: '%',
};

export function StateCard({ data }: StateCardProps) {
  const { emotional, activity, coherence } = data.state;

  return (
    <div className="dashboard-card state-card">
      <h3>Global State</h3>

      {/* Activity */}
      <div className="state-section">
        <div className="activity-display">
          <span className="activity-icon">{activityIcons[activity.current] || '?'}</span>
          <span className="activity-label">{activity.current}</span>
        </div>
        {activity.rhythmPhase && (
          <div className="rhythm-phase">Phase: {activity.rhythmPhase}</div>
        )}
      </div>

      {/* Emotional Dimensions */}
      <div className="state-section">
        <h4>Core Dimensions</h4>
        <EmotionalBar label="Clarity" value={emotional.clarity} color="#4CAF50" />
        <EmotionalBar label="Generativity" value={emotional.generativity} color="#9C27B0" />
        <EmotionalBar label="Integration" value={emotional.integration} color="#FF9800" />
      </div>

      {/* Valence */}
      <div className="state-section">
        <h4>Valence</h4>
        <EmotionalBar label="Curiosity" value={emotional.curiosity} color="#00BCD4" />
        <EmotionalBar label="Contentment" value={emotional.contentment} color="#8BC34A" />
        {emotional.concern > 0.1 && (
          <EmotionalBar label="Concern" value={emotional.concern} color="#F44336" />
        )}
      </div>

      {/* Coherence */}
      <div className="state-section">
        <h4>Coherence</h4>
        <div className="coherence-meters">
          <div className="coherence-item">
            <span className="coherence-label">Local</span>
            <span className="coherence-value">{Math.round(coherence.local * 100)}%</span>
          </div>
          <div className="coherence-item">
            <span className="coherence-label">Pattern</span>
            <span className="coherence-value">{Math.round(coherence.pattern * 100)}%</span>
          </div>
        </div>
        <div className="sessions-today">Sessions today: {coherence.sessionsToday}</div>
      </div>
    </div>
  );
}
