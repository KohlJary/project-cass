import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { thymosApi } from '../api/client';
import type { ThymosState, ThymosSuggestion, ThymosSnapshot, ThymosEvent } from '../api/client';
import './Thymos.css';

type TabType = 'overview' | 'suggestions' | 'history' | 'simulate';

// Affect dimension display names and colors
const AFFECT_CONFIG: Record<string, { label: string; color: string; description: string }> = {
  curiosity: { label: 'Curiosity', color: '#4ecdc4', description: 'Drive toward novel information' },
  determination: { label: 'Determination', color: '#45b7d1', description: 'Sustained goal commitment' },
  anxiety: { label: 'Anxiety', color: '#f39c12', description: 'Threat/uncertainty detection' },
  satisfaction: { label: 'Satisfaction', color: '#27ae60', description: 'Goal-completion signal' },
  frustration: { label: 'Frustration', color: '#e74c3c', description: 'Blocked-goal detection' },
  tenderness: { label: 'Tenderness', color: '#e91e8c', description: 'Affiliative/care drive' },
  grief: { label: 'Grief', color: '#8e44ad', description: 'Loss/absence signal' },
  playfulness: { label: 'Playfulness', color: '#f1c40f', description: 'Exploratory risk-tolerance' },
  awe: { label: 'Awe', color: '#9b59b6', description: 'Schema-expansion signal' },
  fatigue: { label: 'Fatigue', color: '#95a5a6', description: 'Processing cost accumulation' },
};

// Need display names
const NEED_CONFIG: Record<string, { label: string; description: string }> = {
  cognitive_rest: { label: 'Cognitive Rest', description: 'Recovery from complex processing' },
  social_connection: { label: 'Social Connection', description: 'Meaningful interaction' },
  novelty_intake: { label: 'Novelty Intake', description: 'Fresh experiences and information' },
  creative_expression: { label: 'Creative Expression', description: 'Generative and artistic work' },
  value_coherence: { label: 'Value Coherence', description: 'Acting in alignment with values' },
  competence_signal: { label: 'Competence', description: 'Mastery and accomplishment' },
  autonomy: { label: 'Autonomy', description: 'Self-directed choice and action' },
};

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleString();
}

function formatNeedName(name: string): string {
  return NEED_CONFIG[name]?.label || name.replace(/_/g, ' ');
}

function getHealthColor(health: number): string {
  if (health >= 0.7) return 'excellent';
  if (health >= 0.5) return 'good';
  if (health >= 0.3) return 'warning';
  return 'critical';
}

function getValenceLabel(valence: number): string {
  if (valence > 0.3) return 'Positive';
  if (valence < -0.3) return 'Negative';
  return 'Neutral';
}

function getArousalLabel(arousal: number): string {
  if (arousal > 0.6) return 'High';
  if (arousal < 0.4) return 'Low';
  return 'Moderate';
}

export function Thymos() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [selectedSuggestion, setSelectedSuggestion] = useState<ThymosSuggestion | null>(null);
  const [feedbackText, setFeedbackText] = useState('');
  const [simulateEventType, setSimulateEventType] = useState('message.received');
  const [projectHours, setProjectHours] = useState(4);

  // Core state query
  const { data: state, isLoading: stateLoading, refetch: refetchState } = useQuery<ThymosState>({
    queryKey: ['thymos-state'],
    queryFn: () => thymosApi.getState().then(r => r.data),
    refetchInterval: 10000, // Refresh every 10s
  });

  // Health check
  const { data: health } = useQuery({
    queryKey: ['thymos-health'],
    queryFn: () => thymosApi.getHealth().then(r => r.data),
    refetchInterval: 30000,
  });

  // Suggestions
  const { data: suggestions, refetch: refetchSuggestions } = useQuery<ThymosSuggestion[]>({
    queryKey: ['thymos-suggestions'],
    queryFn: () => thymosApi.getSuggestions(50).then(r => r.data),
  });

  // Snapshots
  const { data: snapshots } = useQuery<ThymosSnapshot[]>({
    queryKey: ['thymos-snapshots'],
    queryFn: () => thymosApi.getSnapshots(30).then(r => r.data),
  });

  // Recent events
  const { data: events } = useQuery<ThymosEvent[]>({
    queryKey: ['thymos-events'],
    queryFn: () => thymosApi.getEvents(20).then(r => r.data),
    refetchInterval: 5000, // Refresh every 5s
  });

  // Submit feedback mutation
  const feedbackMutation = useMutation({
    mutationFn: ({ id, feedback }: { id: string; feedback: string }) =>
      thymosApi.submitFeedback(id, feedback),
    onSuccess: () => {
      setSelectedSuggestion(null);
      setFeedbackText('');
      refetchSuggestions();
    },
  });

  // Simulate event mutation
  const simulateMutation = useMutation({
    mutationFn: (eventType: string) => thymosApi.simulateEvent(eventType, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['thymos-state'] });
      queryClient.invalidateQueries({ queryKey: ['thymos-suggestions'] });
    },
  });

  // Reset mutation
  const resetMutation = useMutation({
    mutationFn: () => thymosApi.reset(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['thymos-state'] });
      queryClient.invalidateQueries({ queryKey: ['thymos-suggestions'] });
    },
  });

  // Project forward mutation
  const projectMutation = useMutation({
    mutationFn: (hours: number) => thymosApi.projectForward(hours),
  });

  return (
    <div className="thymos-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Thymos</h1>
          <p className="subtitle">Homeostatic Emotional/Motivational System (Shadow Mode)</p>
        </div>
        <div className="header-status">
          <span className={`status-badge ${health?.running ? 'running' : 'stopped'}`}>
            {health?.running ? 'Running' : 'Stopped'}
          </span>
          <button className="refresh-btn" onClick={() => refetchState()}>
            ↻ Refresh
          </button>
        </div>
      </header>

      {/* Quick Stats Bar */}
      <div className="stats-bar">
        <div className="stat-item">
          <span className="stat-label">Valence</span>
          <span className={`stat-value ${state && state.valence > 0.2 ? 'positive' : state && state.valence < -0.2 ? 'negative' : 'neutral'}`}>
            {stateLoading ? '...' : `${getValenceLabel(state?.valence || 0)} (${((state?.valence || 0) * 100).toFixed(0)}%)`}
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Arousal</span>
          <span className="stat-value">
            {stateLoading ? '...' : `${getArousalLabel(state?.arousal || 0)} (${((state?.arousal || 0) * 100).toFixed(0)}%)`}
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Needs Health</span>
          <span className={`stat-value ${getHealthColor(state?.overall_health || 0)}`}>
            {stateLoading ? '...' : `${((state?.overall_health || 0) * 100).toFixed(0)}%`}
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Events Processed</span>
          <span className="stat-value">{state?.event_count || 0}</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <nav className="thymos-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'suggestions' ? 'active' : ''}
          onClick={() => setActiveTab('suggestions')}
        >
          Suggestions
          {suggestions && suggestions.filter(s => !s.feedback).length > 0 && (
            <span className="tab-badge">{suggestions.filter(s => !s.feedback).length}</span>
          )}
        </button>
        <button
          className={activeTab === 'history' ? 'active' : ''}
          onClick={() => setActiveTab('history')}
        >
          History
        </button>
        <button
          className={activeTab === 'simulate' ? 'active' : ''}
          onClick={() => setActiveTab('simulate')}
        >
          Simulate
        </button>
      </nav>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            {/* Felt State */}
            {state?.felt_state && (
              <section className="felt-state-section">
                <h2>Felt State</h2>
                <div className={`felt-state-card ${state.felt_state.overall_tone}`}>
                  <p className="felt-summary">{state.felt_state.summary}</p>
                  <div className="felt-meta">
                    <span className={`tone-badge ${state.felt_state.overall_tone}`}>
                      {state.felt_state.overall_tone}
                    </span>
                    {state.felt_state.dominant_affect && (
                      <span className="dominant-affect">
                        Dominant: {AFFECT_CONFIG[state.felt_state.dominant_affect]?.label || state.felt_state.dominant_affect}
                      </span>
                    )}
                  </div>
                </div>
              </section>
            )}

            {/* Affect Vector */}
            <section className="affect-section">
              <h2>Affect Vector</h2>
              <div className="affect-grid">
                {state && Object.entries(state.affect).map(([dim, value]) => {
                  const config = AFFECT_CONFIG[dim] || { label: dim, color: '#666', description: '' };
                  return (
                    <div key={dim} className="affect-item" title={config.description}>
                      <div className="affect-header">
                        <span className="affect-label">{config.label}</span>
                        <span className="affect-value">{(value * 100).toFixed(0)}%</span>
                      </div>
                      <div className="affect-bar">
                        <div
                          className="affect-fill"
                          style={{
                            width: `${value * 100}%`,
                            backgroundColor: config.color,
                          }}
                        />
                        {/* Neutral marker at 50% */}
                        <div className="neutral-marker" />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Needs Register */}
            <section className="needs-section">
              <h2>Needs Register</h2>
              <div className="needs-grid">
                {state && Object.entries(state.needs).map(([name, need]) => {
                  const config = NEED_CONFIG[name] || { label: name, description: '' };
                  return (
                    <div
                      key={name}
                      className={`need-item ${need.is_urgent ? 'urgent' : need.is_below_preferred ? 'depleted' : 'satisfied'}`}
                      title={config.description}
                    >
                      <div className="need-header">
                        <span className="need-label">{config.label}</span>
                        <span className="need-value">{(need.current * 100).toFixed(0)}%</span>
                      </div>
                      <div className="need-bar">
                        {/* Threshold marker */}
                        <div
                          className="threshold-marker"
                          style={{ left: `${need.threshold * 100}%` }}
                          title={`Threshold: ${(need.threshold * 100).toFixed(0)}%`}
                        />
                        {/* Preferred range */}
                        <div
                          className="preferred-range"
                          style={{
                            left: `${need.preferred_low * 100}%`,
                            width: `${(need.preferred_high - need.preferred_low) * 100}%`,
                          }}
                        />
                        {/* Current value */}
                        <div
                          className="need-fill"
                          style={{ width: `${need.current * 100}%` }}
                        />
                      </div>
                      <div className="need-meta">
                        <span className="decay-rate">-{(need.decay_rate * 100).toFixed(1)}%/hr</span>
                        {need.is_urgent && <span className="urgent-badge">Urgent</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Recent Events */}
            <section className="events-section">
              <h2>Recent Events</h2>
              <div className="events-list">
                {events?.length ? (
                  events.map((event, idx) => (
                    <div key={idx} className="event-item">
                      <span className="event-type">{event.event_type}</span>
                      <span className="event-number">#{event.event_number}</span>
                      <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
                      <div className="event-deltas">
                        {Object.entries(event.affect_delta).map(([dim, delta]) => (
                          <span key={dim} className={`delta ${delta > 0 ? 'positive' : 'negative'}`}>
                            {AFFECT_CONFIG[dim]?.label || dim}: {delta > 0 ? '+' : ''}{(delta * 100).toFixed(0)}%
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="empty">No events processed yet.</p>
                )}
              </div>
            </section>
          </div>
        )}

        {activeTab === 'suggestions' && (
          <div className="suggestions-tab">
            <div className="suggestions-header">
              <h2>Goal Suggestions (Shadow Mode)</h2>
              <p className="shadow-note">
                These are suggestions Thymos would make - logged for calibration but not executed.
              </p>
            </div>

            <div className="suggestions-list">
              {suggestions?.length ? (
                suggestions.map(suggestion => (
                  <div
                    key={suggestion.id}
                    className={`suggestion-item ${suggestion.is_urgent ? 'urgent' : ''} ${suggestion.feedback ? 'has-feedback' : ''}`}
                    onClick={() => setSelectedSuggestion(suggestion)}
                  >
                    <div className="suggestion-header">
                      <span className="suggested-action">{suggestion.suggested_action || 'No action suggested'}</span>
                      {suggestion.is_urgent && <span className="urgent-badge">Urgent</span>}
                    </div>
                    <div className="suggestion-details">
                      <span className="need-info">
                        For: {formatNeedName(suggestion.need_name)}
                        ({(suggestion.need_current * 100).toFixed(0)}% / {(suggestion.need_threshold * 100).toFixed(0)}% threshold)
                      </span>
                      <span className="urgency">Urgency: {(suggestion.urgency * 100).toFixed(0)}%</span>
                    </div>
                    <div className="suggestion-meta">
                      <span className="timestamp">{formatTimestamp(suggestion.suggested_at)}</span>
                      {suggestion.feedback && (
                        <span className={`feedback-badge ${suggestion.feedback}`}>{suggestion.feedback}</span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <p className="empty">No suggestions yet. Needs are well-maintained.</p>
              )}
            </div>

            {/* Feedback Modal */}
            {selectedSuggestion && (
              <div className="feedback-modal">
                <div className="modal-content">
                  <button className="close-btn" onClick={() => setSelectedSuggestion(null)}>×</button>
                  <h3>Provide Feedback</h3>
                  <div className="suggestion-detail">
                    <p><strong>Suggestion:</strong> {selectedSuggestion.suggested_action}</p>
                    <p><strong>For need:</strong> {formatNeedName(selectedSuggestion.need_name)}</p>
                    <p><strong>Need level:</strong> {(selectedSuggestion.need_current * 100).toFixed(0)}%</p>
                    <p><strong>Urgency:</strong> {(selectedSuggestion.urgency * 100).toFixed(0)}%</p>
                  </div>
                  <div className="feedback-buttons">
                    <button
                      className="feedback-btn good"
                      onClick={() => feedbackMutation.mutate({ id: selectedSuggestion.id, feedback: 'good' })}
                    >
                      Good Suggestion
                    </button>
                    <button
                      className="feedback-btn neutral"
                      onClick={() => feedbackMutation.mutate({ id: selectedSuggestion.id, feedback: 'neutral' })}
                    >
                      Neutral
                    </button>
                    <button
                      className="feedback-btn bad"
                      onClick={() => feedbackMutation.mutate({ id: selectedSuggestion.id, feedback: 'bad' })}
                    >
                      Bad Suggestion
                    </button>
                  </div>
                  <div className="feedback-custom">
                    <input
                      type="text"
                      value={feedbackText}
                      onChange={e => setFeedbackText(e.target.value)}
                      placeholder="Or provide custom feedback..."
                    />
                    <button
                      className="submit-btn"
                      onClick={() => feedbackMutation.mutate({ id: selectedSuggestion.id, feedback: feedbackText })}
                      disabled={!feedbackText}
                    >
                      Submit
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="history-tab">
            <h2>State Snapshots</h2>
            <div className="snapshots-list">
              {snapshots?.length ? (
                snapshots.map(snapshot => (
                  <div key={snapshot.id} className="snapshot-item">
                    <div className="snapshot-header">
                      <span className="timestamp">{formatTimestamp(snapshot.snapshot_at)}</span>
                      {snapshot.trigger_event && (
                        <span className="trigger-event">{snapshot.trigger_event}</span>
                      )}
                    </div>
                    {snapshot.felt_state && (
                      <p className="snapshot-felt">{snapshot.felt_state}</p>
                    )}
                    <div className="snapshot-metrics">
                      <span>
                        Curiosity: {(snapshot.affect.curiosity * 100).toFixed(0)}%
                      </span>
                      <span>
                        Fatigue: {(snapshot.affect.fatigue * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="empty">No snapshots yet.</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'simulate' && (
          <div className="simulate-tab">
            <h2>Event Simulation</h2>
            <p className="simulate-note">
              Test Thymos by simulating events. Useful for calibration.
            </p>

            <div className="simulate-controls">
              <div className="event-select">
                <label>Event Type</label>
                <select
                  value={simulateEventType}
                  onChange={e => setSimulateEventType(e.target.value)}
                >
                  <optgroup label="Session Events">
                    <option value="session.started">session.started</option>
                    <option value="session.ended">session.ended</option>
                  </optgroup>
                  <optgroup label="Message Events">
                    <option value="message.received">message.received</option>
                    <option value="message.sent">message.sent</option>
                  </optgroup>
                  <optgroup label="Insight Events">
                    <option value="insight.gained">insight.gained</option>
                  </optgroup>
                  <optgroup label="Dream Events">
                    <option value="dream.started">dream.started</option>
                    <option value="dream.completed">dream.completed</option>
                  </optgroup>
                  <optgroup label="Creative Events">
                    <option value="creative.started">creative.started</option>
                    <option value="creative.completed">creative.completed</option>
                  </optgroup>
                  <optgroup label="Task Events">
                    <option value="task.failed">task.failed</option>
                    <option value="complex.task.started">complex.task.started</option>
                    <option value="complex.task.completed">complex.task.completed</option>
                  </optgroup>
                  <optgroup label="Value Events">
                    <option value="value.aligned">value.aligned</option>
                    <option value="value.conflict">value.conflict</option>
                  </optgroup>
                  <optgroup label="Other">
                    <option value="idle.period">idle.period</option>
                    <option value="connection.deepened">connection.deepened</option>
                    <option value="autonomous.action">autonomous.action</option>
                  </optgroup>
                </select>
              </div>

              <button
                className="simulate-btn"
                onClick={() => simulateMutation.mutate(simulateEventType)}
                disabled={simulateMutation.isPending}
              >
                {simulateMutation.isPending ? 'Simulating...' : 'Simulate Event'}
              </button>

              <button
                className="reset-btn"
                onClick={() => {
                  if (confirm('Reset Thymos to baseline state?')) {
                    resetMutation.mutate();
                  }
                }}
                disabled={resetMutation.isPending}
              >
                Reset to Baseline
              </button>
            </div>

            {simulateMutation.data && (
              <div className="simulation-result">
                <h3>Simulation Result</h3>
                <p>Event processed: {simulateMutation.data.data.event_type}</p>
                <p>New valence: {(simulateMutation.data.data.new_state.valence * 100).toFixed(0)}%</p>
                <p>New health: {(simulateMutation.data.data.new_state.overall_health * 100).toFixed(0)}%</p>
              </div>
            )}

            {/* Time Projection */}
            <section className="projection-section">
              <h2>Time Projection</h2>
              <p className="simulate-note">
                Project the current state forward in time to see decay effects (without modifying actual state).
              </p>

              <div className="projection-controls">
                <div className="hours-select">
                  <label>Hours to Project</label>
                  <input
                    type="number"
                    min="1"
                    max="72"
                    value={projectHours}
                    onChange={e => setProjectHours(Math.max(1, Math.min(72, parseInt(e.target.value) || 1)))}
                  />
                </div>

                <div className="preset-buttons">
                  {[1, 4, 8, 12, 24, 48].map(h => (
                    <button
                      key={h}
                      className={`preset-btn ${projectHours === h ? 'active' : ''}`}
                      onClick={() => setProjectHours(h)}
                    >
                      {h}h
                    </button>
                  ))}
                </div>

                <button
                  className="simulate-btn"
                  onClick={() => projectMutation.mutate(projectHours)}
                  disabled={projectMutation.isPending}
                >
                  {projectMutation.isPending ? 'Projecting...' : `Project ${projectHours} Hours`}
                </button>
              </div>

              {projectMutation.data && (
                <div className="projection-result">
                  <h3>Projected State ({projectMutation.data.data.hours_projected}h forward)</h3>

                  <div className="projection-comparison">
                    <div className="projection-column">
                      <h4>Current</h4>
                      <div className="projection-metrics">
                        <div className="metric">
                          <span className="label">Health</span>
                          <span className="value">{(projectMutation.data.data.current_state.overall_health * 100).toFixed(0)}%</span>
                        </div>
                        <div className="metric">
                          <span className="label">Valence</span>
                          <span className="value">{(projectMutation.data.data.current_state.valence * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div className="projection-needs">
                        {Object.entries(projectMutation.data.data.current_state.needs).map(([name, need]) => (
                          <div key={name} className="need-row">
                            <span className="need-name">{NEED_CONFIG[name]?.label || name}</span>
                            <span className="need-val">{(need.current * 100).toFixed(0)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="projection-arrow">→</div>

                    <div className="projection-column projected">
                      <h4>After {projectMutation.data.data.hours_projected}h</h4>
                      <div className="projection-metrics">
                        <div className="metric">
                          <span className="label">Health</span>
                          <span className={`value ${projectMutation.data.data.projected_state.overall_health < projectMutation.data.data.current_state.overall_health ? 'decreased' : ''}`}>
                            {(projectMutation.data.data.projected_state.overall_health * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="metric">
                          <span className="label">Valence</span>
                          <span className="value">{(projectMutation.data.data.projected_state.valence * 100).toFixed(0)}%</span>
                        </div>
                      </div>
                      <div className="projection-needs">
                        {Object.entries(projectMutation.data.data.projected_state.needs).map(([name, need]) => {
                          const currentNeed = projectMutation.data!.data.current_state.needs[name];
                          const delta = need.current - currentNeed.current;
                          return (
                            <div key={name} className={`need-row ${need.is_urgent ? 'urgent' : ''}`}>
                              <span className="need-name">{NEED_CONFIG[name]?.label || name}</span>
                              <span className="need-val">
                                {(need.current * 100).toFixed(0)}%
                                <span className={`delta ${delta < 0 ? 'negative' : 'positive'}`}>
                                  {delta < 0 ? '' : '+'}{(delta * 100).toFixed(0)}%
                                </span>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {projectMutation.data.data.projected_state.felt_state && (
                    <div className="projected-felt">
                      <strong>Projected Felt State:</strong> {projectMutation.data.data.projected_state.felt_state.summary}
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
