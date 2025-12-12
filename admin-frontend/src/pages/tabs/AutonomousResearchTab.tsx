import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { autonomousResearchApi, researchNotesApi } from '../../api/client';
import { TabbedPanel, type Tab } from '../../components/TabbedPanel';
import { SessionSummary } from '../../components/SessionSummary';
import { ResearchNoteViewer } from '../../components/ResearchNoteViewer';

interface ResearchSession {
  session_id: string;
  started_at: string;
  ended_at?: string;
  status: string;
  mode: string;
  duration_limit_minutes: number;
  focus_description: string;
  focus_item_id?: string;
  searches_performed: number;
  urls_fetched: number;
  notes_created: string[];
  summary?: string;
  findings_summary?: string;
  next_steps?: string[];
  elapsed_minutes: number;
  remaining_minutes: number;
  is_overtime: boolean;
}

interface ResearchStatus {
  is_running: boolean;
  current_session: ResearchSession | null;
}

interface ResearchNote {
  note_id: string;
  title: string;
  content: string;
  created_at: string;
  sources: Array<{ url: string; title: string }>;
  session_id: string | null;
}

export function AutonomousResearchTab() {
  const queryClient = useQueryClient();
  const [newSessionFocus, setNewSessionFocus] = useState('');
  const [newSessionDuration, setNewSessionDuration] = useState(30);
  const [newSessionMode, setNewSessionMode] = useState('explore');
  const [isPolling, setIsPolling] = useState(false);

  const { data: status, isLoading: statusLoading } = useQuery<ResearchStatus>({
    queryKey: ['autonomous-research-status'],
    queryFn: () => autonomousResearchApi.getStatus().then((r) => r.data),
    refetchInterval: isPolling ? 3000 : false,
  });

  const session = status?.current_session;

  // Fetch notes for current session
  const { data: sessionNotes } = useQuery<{ notes: ResearchNote[] }>({
    queryKey: ['research-notes', session?.session_id],
    queryFn: () => researchNotesApi.getBySession(session!.session_id).then((r) => r.data),
    enabled: !!session?.session_id && (session?.notes_created?.length ?? 0) > 0,
  });

  const startMutation = useMutation({
    mutationFn: (data: { duration_minutes: number; focus: string; mode: string }) =>
      autonomousResearchApi.startSession(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autonomous-research-status'] });
      setIsPolling(true);
      setNewSessionFocus('');
    },
  });

  const stopMutation = useMutation({
    mutationFn: () => autonomousResearchApi.stopSession(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['autonomous-research-status'] });
      setIsPolling(false);
    },
  });

  useEffect(() => {
    if (status?.is_running) {
      setIsPolling(true);
    } else {
      setIsPolling(false);
    }
  }, [status?.is_running]);

  const handleStartSession = () => {
    if (!newSessionFocus.trim()) return;
    startMutation.mutate({
      duration_minutes: newSessionDuration,
      focus: newSessionFocus.trim(),
      mode: newSessionMode,
    });
  };

  const formatTime = (minutes: number) => {
    const mins = Math.floor(minutes);
    const secs = Math.round((minutes - mins) * 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatDate = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return '#c3e88d';
      case 'completed': return '#89ddff';
      case 'terminated': return '#f07178';
      default: return '#888';
    }
  };

  // Build tabs for TabbedPanel
  const buildSessionTabs = (): Tab[] => {
    const tabs: Tab[] = [
      {
        id: 'summary',
        label: 'Summary',
        icon: '*',
        content: (
          <SessionSummary
            summary={session?.summary}
            findings={session?.findings_summary}
            nextSteps={session?.next_steps}
          />
        ),
      },
    ];

    // Add tabs for each note
    const notes = sessionNotes?.notes || [];
    notes.forEach((note, i) => {
      tabs.push({
        id: note.note_id,
        label: note.title?.slice(0, 20) || `Note ${i + 1}`,
        icon: '#',
        content: (
          <ResearchNoteViewer
            title={note.title}
            content={note.content}
            sources={note.sources}
            createdAt={note.created_at}
          />
        ),
      });
    });

    return tabs;
  };

  return (
    <div className="autonomous-research-tab">
      <div className="research-layout">
        <div className="sidebar-column">
          {/* Current Session Status */}
          <div className="status-panel">
            <h3>Session Status</h3>
            {statusLoading ? (
              <div className="loading-state small">Loading...</div>
            ) : status?.is_running ? (
              <div className="running-session">
                <div className="status-indicator running">
                  <span className="pulse" />
                  Running
                </div>
                <div className="session-progress">
                  <div className="progress-stat">
                    <span className="stat-value">{session?.searches_performed || 0}</span>
                    <span className="stat-label">Searches</span>
                  </div>
                  <div className="progress-stat">
                    <span className="stat-value">{session?.urls_fetched || 0}</span>
                    <span className="stat-label">Fetches</span>
                  </div>
                  <div className="progress-stat">
                    <span className="stat-value">{session?.notes_created?.length || 0}</span>
                    <span className="stat-label">Notes</span>
                  </div>
                </div>
                <div className="time-remaining">
                  <span className="time-label">Time Remaining:</span>
                  <span className="time-value">{formatTime(session?.remaining_minutes || 0)}</span>
                </div>
                <button
                  className="stop-btn"
                  onClick={() => stopMutation.mutate()}
                  disabled={stopMutation.isPending}
                >
                  {stopMutation.isPending ? 'Stopping...' : 'Stop Session'}
                </button>
              </div>
            ) : (
              <div className="status-indicator idle">
                <span className="idle-dot" />
                Idle
              </div>
            )}
          </div>

          {/* Start New Session */}
          <div className="new-session-panel">
            <h3>Start New Session</h3>
            <div className="form-group">
              <label>Research Focus</label>
              <input
                type="text"
                placeholder="What to research..."
                value={newSessionFocus}
                onChange={(e) => setNewSessionFocus(e.target.value)}
                disabled={status?.is_running}
              />
            </div>
            <div className="form-row">
              <div className="form-group half">
                <label>Duration (min)</label>
                <input
                  type="number"
                  min={5}
                  max={60}
                  value={newSessionDuration}
                  onChange={(e) => setNewSessionDuration(parseInt(e.target.value) || 30)}
                  disabled={status?.is_running}
                />
              </div>
              <div className="form-group half">
                <label>Mode</label>
                <select
                  value={newSessionMode}
                  onChange={(e) => setNewSessionMode(e.target.value)}
                  disabled={status?.is_running}
                >
                  <option value="explore">Explore</option>
                  <option value="deep">Deep</option>
                </select>
              </div>
            </div>
            <button
              className="start-btn"
              onClick={handleStartSession}
              disabled={startMutation.isPending || status?.is_running || !newSessionFocus.trim()}
            >
              {startMutation.isPending ? 'Starting...' : 'Start Research'}
            </button>
          </div>
        </div>

        {/* Session Detail */}
        <div className="detail-column">
          {session ? (
            <div className="session-detail">
              <div className="detail-header">
                <div className="header-info">
                  <h2>{session.focus_description || 'Research Session'}</h2>
                  <div className="header-meta">
                    <span
                      className="status-badge"
                      style={{
                        background: `${getStatusColor(session.status)}20`,
                        color: getStatusColor(session.status)
                      }}
                    >
                      {session.status}
                    </span>
                    <span className="meta-item">{formatDate(session.started_at)}</span>
                    <span className="meta-item">{formatTimestamp(session.started_at)}</span>
                    <span className="meta-item mode">{session.mode} mode</span>
                  </div>
                </div>
              </div>

              <div className="stats-row">
                <div className="stat-box">
                  <span className="stat-value">{session.searches_performed}</span>
                  <span className="stat-label">Searches</span>
                </div>
                <div className="stat-box">
                  <span className="stat-value">{session.urls_fetched}</span>
                  <span className="stat-label">URLs Fetched</span>
                </div>
                <div className="stat-box">
                  <span className="stat-value">{session.notes_created?.length || 0}</span>
                  <span className="stat-label">Notes Created</span>
                </div>
                <div className="stat-box">
                  <span className="stat-value">{session.elapsed_minutes.toFixed(1)}</span>
                  <span className="stat-label">Minutes</span>
                </div>
              </div>

              {/* Tabbed Summary + Notes */}
              <div className="session-tabs-container">
                <TabbedPanel tabs={buildSessionTabs()} defaultTab="summary" />
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">*</div>
              <p>No session data available</p>
              <p className="empty-hint">Start a research session to see activity</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
