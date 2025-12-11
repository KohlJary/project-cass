import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { soloReflectionApi } from '../../api/client';

interface ThoughtEntry {
  timestamp: string;
  content: string;
  thought_type: string;
  confidence: string | number;
  related_concepts: string[];
}

interface ReflectionSession {
  session_id: string;
  started_at: string;
  ended_at?: string;
  duration_minutes: number;
  actual_duration_minutes?: number;
  trigger: string;
  theme?: string;
  status: string;
  summary?: string;
  model_used: string;
  thought_stream: ThoughtEntry[];
  insights: string[];
  questions_raised: string[];
}

interface ReflectionStats {
  total_sessions: number;
  completed_sessions: number;
  interrupted_sessions: number;
  active_session: string | null;
  total_thoughts_recorded: number;
  total_reflection_minutes: number;
  themes_explored: string[];
}

export function ReflectionTab() {
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [newSessionDuration, setNewSessionDuration] = useState(15);
  const [newSessionTheme, setNewSessionTheme] = useState('');
  const [isPolling, setIsPolling] = useState(false);

  const { data: stats, isLoading: statsLoading } = useQuery<ReflectionStats>({
    queryKey: ['solo-reflection-stats'],
    queryFn: () => soloReflectionApi.getStats().then((r) => r.data),
    refetchInterval: isPolling ? 3000 : false,
  });

  const { data: sessionsData, isLoading: sessionsLoading } = useQuery({
    queryKey: ['solo-reflection-sessions'],
    queryFn: () => soloReflectionApi.listSessions({ limit: 20 }).then((r) => r.data),
    refetchInterval: isPolling ? 3000 : false,
  });

  const { data: sessionDetail, isLoading: detailLoading } = useQuery<ReflectionSession>({
    queryKey: ['solo-reflection-session', selectedSessionId],
    queryFn: () => soloReflectionApi.getSession(selectedSessionId!).then((r) => r.data),
    enabled: !!selectedSessionId,
    refetchInterval: isPolling && stats?.active_session === selectedSessionId ? 2000 : false,
  });

  const startMutation = useMutation({
    mutationFn: (data: { duration_minutes: number; theme?: string }) =>
      soloReflectionApi.startSession(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-stats'] });
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-sessions'] });
      setSelectedSessionId(response.data.session_id);
      setIsPolling(true);
      setNewSessionTheme('');
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => soloReflectionApi.stopSession(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-stats'] });
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-sessions'] });
      setIsPolling(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => soloReflectionApi.deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-sessions'] });
      queryClient.invalidateQueries({ queryKey: ['solo-reflection-stats'] });
      setSelectedSessionId(null);
    },
  });

  useEffect(() => {
    if (stats?.active_session) {
      setIsPolling(true);
      setSelectedSessionId(stats.active_session);
    } else {
      setIsPolling(false);
    }
  }, [stats?.active_session]);

  const handleStartSession = () => {
    startMutation.mutate({
      duration_minutes: newSessionDuration,
      theme: newSessionTheme.trim() || undefined,
    });
  };

  const getThoughtTypeColor = (type: string) => {
    switch (type) {
      case 'observation': return '#89ddff';
      case 'question': return '#82aaff';
      case 'connection': return '#c792ea';
      case 'uncertainty': return '#ffcb6b';
      case 'realization': return '#c3e88d';
      default: return '#888';
    }
  };

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const formatDate = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  };

  return (
    <div className="reflection-tab">
      <div className="reflection-layout">
        <div className="sidebar-column">
          <div className="stats-panel">
            <h3>Statistics</h3>
            {statsLoading ? (
              <div className="loading-state small">Loading...</div>
            ) : stats ? (
              <div className="stats-grid">
                <div className="stat">
                  <span className="stat-value">{stats.total_sessions}</span>
                  <span className="stat-label">Sessions</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{stats.completed_sessions}</span>
                  <span className="stat-label">Completed</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{stats.total_thoughts_recorded}</span>
                  <span className="stat-label">Thoughts</span>
                </div>
                <div className="stat">
                  <span className="stat-value">{stats.total_reflection_minutes}</span>
                  <span className="stat-label">Minutes</span>
                </div>
              </div>
            ) : null}

            {stats?.active_session && (
              <div className="active-indicator">
                <span className="pulse" />
                Session Active
              </div>
            )}
          </div>

          <div className="new-session-panel">
            <h3>Start New Session</h3>
            <div className="form-group">
              <label>Duration (minutes)</label>
              <input
                type="number"
                min={5}
                max={60}
                value={newSessionDuration}
                onChange={(e) => setNewSessionDuration(parseInt(e.target.value) || 15)}
              />
            </div>
            <div className="form-group">
              <label>Theme (optional)</label>
              <input
                type="text"
                placeholder="Open reflection..."
                value={newSessionTheme}
                onChange={(e) => setNewSessionTheme(e.target.value)}
              />
            </div>
            <button
              className="start-btn"
              onClick={handleStartSession}
              disabled={startMutation.isPending || !!stats?.active_session}
            >
              {startMutation.isPending ? 'Starting...' : stats?.active_session ? 'Session Active' : 'Start Reflection'}
            </button>
            {stats?.active_session && (
              <button
                className="stop-btn"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending}
              >
                {stopMutation.isPending ? 'Stopping...' : 'Stop Session'}
              </button>
            )}
          </div>

          <div className="sessions-panel">
            <h3>Sessions</h3>
            {sessionsLoading ? (
              <div className="loading-state small">Loading...</div>
            ) : sessionsData?.sessions?.length > 0 ? (
              <div className="sessions-list">
                {sessionsData.sessions.map((s: ReflectionSession) => (
                  <div
                    key={s.session_id}
                    className={`session-item ${selectedSessionId === s.session_id ? 'selected' : ''} ${s.status === 'active' ? 'active' : ''}`}
                    onClick={() => setSelectedSessionId(s.session_id)}
                  >
                    <div className="session-info">
                      <span className="session-date">{formatDate(s.started_at)}</span>
                      <span className={`session-status ${s.status}`}>{s.status}</span>
                    </div>
                    <div className="session-meta">
                      {s.theme && <span className="session-theme">{s.theme}</span>}
                      <span className="session-thoughts">{s.thought_stream?.length || 0} thoughts</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state small">No sessions yet</div>
            )}
          </div>
        </div>

        <div className="detail-column">
          {selectedSessionId ? (
            detailLoading ? (
              <div className="loading-state">Loading session...</div>
            ) : sessionDetail ? (
              <div className="session-detail">
                <div className="detail-header">
                  <div className="header-info">
                    <h2>{sessionDetail.theme || 'Open Reflection'}</h2>
                    <div className="header-meta">
                      <span className={`status-badge ${sessionDetail.status}`}>
                        {sessionDetail.status}
                      </span>
                      <span className="meta-item">{formatDate(sessionDetail.started_at)}</span>
                      <span className="meta-item">
                        {sessionDetail.actual_duration_minutes != null
                          ? `${sessionDetail.actual_duration_minutes.toFixed(1)} min`
                          : `${sessionDetail.duration_minutes} min (target)`}
                      </span>
                      <span className="meta-item model">{sessionDetail.model_used}</span>
                    </div>
                  </div>
                  {sessionDetail.status !== 'active' && (
                    <button
                      className="delete-btn"
                      onClick={() => deleteMutation.mutate(sessionDetail.session_id)}
                      disabled={deleteMutation.isPending}
                    >
                      Delete
                    </button>
                  )}
                </div>

                {sessionDetail.summary && (
                  <div className="summary-section">
                    <h4>Summary</h4>
                    <p>{sessionDetail.summary}</p>
                  </div>
                )}

                {sessionDetail.insights && sessionDetail.insights.length > 0 && (
                  <div className="insights-section">
                    <h4>Key Insights</h4>
                    <ul>
                      {sessionDetail.insights.map((insight, i) => (
                        <li key={i}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {sessionDetail.questions_raised && sessionDetail.questions_raised.length > 0 && (
                  <div className="questions-section">
                    <h4>Questions Raised</h4>
                    <ul>
                      {sessionDetail.questions_raised.map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="thought-stream-section">
                  <h4>Thought Stream ({sessionDetail.thought_stream?.length || 0})</h4>
                  <div className="thought-stream">
                    {sessionDetail.thought_stream?.map((thought, i) => (
                      <div key={i} className="thought-entry">
                        <div className="thought-header">
                          <span
                            className="thought-type"
                            style={{ color: getThoughtTypeColor(thought.thought_type) }}
                          >
                            {thought.thought_type}
                          </span>
                          <span className="thought-time">{formatTimestamp(thought.timestamp)}</span>
                          <span className="thought-confidence">
                            {Math.round(parseFloat(String(thought.confidence)) * 100)}%
                          </span>
                        </div>
                        <p className="thought-content">{thought.content}</p>
                        {thought.related_concepts && thought.related_concepts.length > 0 && (
                          <div className="thought-concepts">
                            {thought.related_concepts.map((c, j) => (
                              <span key={j} className="concept-tag">{c}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="error-state">Failed to load session</div>
            )
          ) : (
            <div className="empty-state">
              <div className="empty-icon">~</div>
              <p>Select a session to view its thought stream</p>
              <p className="empty-hint">Or start a new reflection session</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
