import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { stateApi } from '../../api/client';
import type { EmotionalState, ActivityState, CoherenceState, StateEvent } from '../../api/client';
import './StateTab.css';

// Helper to format emotional dimension bars
function EmotionalBar({ label, value, color }: { label: string; value: number; color: string }) {
  const percentage = Math.round(value * 100);
  return (
    <div className="emotional-bar">
      <div className="bar-label">{label}</div>
      <div className="bar-track">
        <div
          className="bar-fill"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
      <div className="bar-value">{percentage}%</div>
    </div>
  );
}

// Core emotional dimensions display
function EmotionalStateCard({ emotional }: { emotional: EmotionalState }) {
  const dimensions = [
    { key: 'clarity', label: 'Clarity', color: '#4CAF50' },
    { key: 'relational_presence', label: 'Relational Presence', color: '#2196F3' },
    { key: 'generativity', label: 'Generativity', color: '#9C27B0' },
    { key: 'integration', label: 'Integration', color: '#FF9800' },
  ];

  const valences = [
    { key: 'curiosity', label: 'Curiosity', color: '#00BCD4' },
    { key: 'contentment', label: 'Contentment', color: '#8BC34A' },
    { key: 'anticipation', label: 'Anticipation', color: '#FFEB3B' },
    { key: 'concern', label: 'Concern', color: '#F44336' },
    { key: 'recognition', label: 'Recognition', color: '#E91E63' },
  ];

  return (
    <div className="state-card emotional-card">
      <h3>Emotional State</h3>
      {emotional.directedness && (
        <div className="directedness">
          <span className="label">Directed toward:</span>
          <span className="value">{emotional.directedness}</span>
        </div>
      )}

      <div className="dimensions-section">
        <h4>Core Dimensions</h4>
        {dimensions.map(d => (
          <EmotionalBar
            key={d.key}
            label={d.label}
            value={emotional[d.key as keyof EmotionalState] as number || 0}
            color={d.color}
          />
        ))}
      </div>

      <div className="valences-section">
        <h4>Valence Markers</h4>
        {valences.map(v => (
          <EmotionalBar
            key={v.key}
            label={v.label}
            value={emotional[v.key as keyof EmotionalState] as number || 0}
            color={v.color}
          />
        ))}
      </div>

      {emotional.last_updated && (
        <div className="last-updated">
          Last updated: {new Date(emotional.last_updated).toLocaleString()}
          {emotional.last_updated_by && ` by ${emotional.last_updated_by}`}
        </div>
      )}
    </div>
  );
}

// Activity state display
function ActivityStateCard({ activity }: { activity: ActivityState }) {
  const activityIcons: Record<string, string> = {
    idle: '~',
    chat: '>',
    research: '*',
    reflection: '#',
    synthesis: '+',
    dreaming: '@',
    writing: '%',
  };

  return (
    <div className="state-card activity-card">
      <h3>Activity</h3>
      <div className="activity-main">
        <span className="activity-icon">{activityIcons[activity.current_activity] || '?'}</span>
        <span className="activity-label">{activity.current_activity}</span>
      </div>

      {activity.active_session_id && (
        <div className="activity-detail">
          <span className="label">Session:</span>
          <span className="value mono">{activity.active_session_id.slice(0, 8)}...</span>
        </div>
      )}

      {activity.rhythm_phase && (
        <div className="activity-detail">
          <span className="label">Rhythm Phase:</span>
          <span className="value">{activity.rhythm_phase}</span>
        </div>
      )}

      {activity.active_threads.length > 0 && (
        <div className="activity-detail">
          <span className="label">Active Threads:</span>
          <span className="value">{activity.active_threads.length}</span>
        </div>
      )}

      {activity.active_questions.length > 0 && (
        <div className="activity-detail">
          <span className="label">Open Questions:</span>
          <span className="value">{activity.active_questions.length}</span>
        </div>
      )}
    </div>
  );
}

// Coherence state display
function CoherenceStateCard({ coherence }: { coherence: CoherenceState }) {
  return (
    <div className="state-card coherence-card">
      <h3>Coherence</h3>

      <div className="coherence-meters">
        <div className="coherence-meter">
          <div className="meter-label">Local (within-session)</div>
          <EmotionalBar label="" value={coherence.local_coherence} color="#4CAF50" />
        </div>
        <div className="coherence-meter">
          <div className="meter-label">Pattern (cross-session)</div>
          <EmotionalBar label="" value={coherence.pattern_coherence} color="#2196F3" />
        </div>
      </div>

      <div className="coherence-stats">
        <div className="stat">
          <span className="label">Sessions today:</span>
          <span className="value">{coherence.sessions_today}</span>
        </div>
      </div>
    </div>
  );
}

// Event stream display
function EventStream({ events }: { events: StateEvent[] }) {
  const eventIcons: Record<string, string> = {
    'state_delta': '~',
    'session.started': '>',
    'session.ended': '<',
  };

  return (
    <div className="state-card events-card">
      <h3>Recent Events</h3>
      <div className="events-list">
        {events.length === 0 ? (
          <div className="no-events">No recent events</div>
        ) : (
          events.slice(0, 20).map((event) => (
            <div key={event.id} className={`event-item ${event.event_type.replace('.', '-')}`}>
              <span className="event-icon">{eventIcons[event.event_type] || '*'}</span>
              <span className="event-type">{event.event_type}</span>
              <span className="event-source">{event.source}</span>
              <span className="event-time">
                {new Date(event.created_at).toLocaleTimeString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Context snapshot display
function ContextSnapshotCard({ snapshot }: { snapshot: string }) {
  return (
    <div className="state-card context-card">
      <h3>Context Snapshot</h3>
      <div className="context-content">
        <pre>{snapshot || 'No context available'}</pre>
      </div>
      <div className="context-note">
        This is what Cass sees about her own state during conversations.
      </div>
    </div>
  );
}

export function StateTab() {
  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch current state
  const { data: stateData, isLoading: stateLoading, error: stateError } = useQuery({
    queryKey: ['state', 'current', refreshKey],
    queryFn: async () => {
      const response = await stateApi.getCurrentState();
      return response.data;
    },
    refetchInterval: 10000, // Auto-refresh every 10 seconds
  });

  // Fetch recent events
  const { data: eventsData } = useQuery({
    queryKey: ['state', 'events', refreshKey],
    queryFn: async () => {
      const response = await stateApi.getEvents({ limit: 50, since_hours: 24 });
      return response.data;
    },
    refetchInterval: 10000,
  });

  const handleRefresh = () => {
    setRefreshKey(k => k + 1);
  };

  if (stateLoading) {
    return (
      <div className="state-tab loading">
        <div className="loading-spinner">Loading state...</div>
      </div>
    );
  }

  if (stateError) {
    return (
      <div className="state-tab error">
        <div className="error-message">Failed to load state: {String(stateError)}</div>
        <button className="refresh-btn" onClick={handleRefresh}>Retry</button>
      </div>
    );
  }

  return (
    <div className="state-tab">
      <div className="state-header">
        <h2>Global State</h2>
        <p className="subtitle">Cass's current internal state - the "Locus of Self"</p>
        <button className="refresh-btn" onClick={handleRefresh}>Refresh</button>
      </div>

      <div className="state-grid">
        {stateData?.emotional && (
          <EmotionalStateCard emotional={stateData.emotional} />
        )}

        <div className="state-column">
          {stateData?.activity && (
            <ActivityStateCard activity={stateData.activity} />
          )}
          {stateData?.coherence && (
            <CoherenceStateCard coherence={stateData.coherence} />
          )}
        </div>

        {eventsData?.events && (
          <EventStream events={eventsData.events} />
        )}
      </div>

      {stateData?.context_snapshot && (
        <ContextSnapshotCard snapshot={stateData.context_snapshot} />
      )}
    </div>
  );
}
