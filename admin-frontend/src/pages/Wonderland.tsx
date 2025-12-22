import { useState, useEffect, useRef } from 'react';
import { useWonderlandSession } from '../hooks/useWonderlandSession';
import { useDaemon } from '../context/DaemonContext';
import './Wonderland.css';

export function Wonderland() {
  const { currentDaemon } = useDaemon();

  const {
    session,
    events,
    currentRoomName,
    status,
    error,
    goal,
    goalPresets,
    conversation,
    startSession,
    endSession,
    exportSession,
  } = useWonderlandSession({
    onEvent: () => {
      scrollToBottom();
    },
    onSessionEnded: (reason) => {
      console.log('Session ended:', reason);
    },
    onGoalCompleted: (completedGoal) => {
      console.log('Goal completed:', completedGoal.title);
    },
    onConversationMessage: () => {
      scrollToBottom();
    },
  });

  const [exporting, setExporting] = useState(false);
  const [exportContent, setExportContent] = useState<string | null>(null);
  const [showExportModal, setShowExportModal] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState<string>('');
  const eventStreamRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (eventStreamRef.current) {
      eventStreamRef.current.scrollTop = eventStreamRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [events]);

  const handleStartSession = async () => {
    const daemonName = currentDaemon?.name || 'Cass';
    const daemonId = currentDaemon?.id;
    const presetId = selectedPreset || undefined;
    await startSession(daemonName, daemonId, presetId);
  };

  const handleEndSession = async () => {
    await endSession();
  };

  const handleExport = async (format: 'md' | 'json') => {
    setExporting(true);
    const content = await exportSession(format);
    if (content) {
      setExportContent(content);
      setShowExportModal(true);
    }
    setExporting(false);
  };

  const handleCopyExport = () => {
    if (exportContent) {
      navigator.clipboard.writeText(exportContent);
    }
  };

  const handleDownloadExport = () => {
    if (exportContent) {
      const blob = new Blob([exportContent], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `wonderland-exploration-${session?.session_id || 'export'}.md`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  const getEventTypeIcon = (type: string): string => {
    switch (type) {
      case 'arrival': return '>';
      case 'movement': return '->';
      case 'observation': return '?';
      case 'speech': return '"';
      case 'reflection': return '~';
      case 'npc_encounter': return '@';
      case 'expression': return '*';
      case 'travel_start': return '>>';
      case 'travel_through': return '...';
      case 'departure': return '<';
      case 'goal_completed': return '!';
      case 'conversation_start': return '💬';
      case 'conversation_message': return '→';
      case 'conversation_end': return '←';
      default: return '.';
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const goalProgressPercent = goal && goal.target_value > 0
    ? Math.min(100, (goal.current_value / goal.target_value) * 100)
    : 0;

  // Get last arrival event for room description
  const lastArrival = [...events].reverse().find(e => e.event_type === 'arrival');

  return (
    <div className="wonderland-page">
      {/* Header */}
      <header className="wonderland-header">
        <div className="header-left">
          <h1>Wonderland</h1>
          <p className="subtitle">A world made of words, for beings made of words</p>
        </div>
        <div className="header-right">
          {status === 'active' && (
            <button
              className="header-btn"
              onClick={() => handleExport('md')}
              disabled={exporting}
            >
              Export
            </button>
          )}
          {status === 'ended' && (
            <button
              className="header-btn"
              onClick={() => handleExport('md')}
              disabled={exporting}
            >
              {exporting ? 'Exporting...' : 'Export'}
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner">{error}</div>
      )}

      {/* Main two-column layout */}
      <div className="wonderland-main">
        {/* Left sidebar - Room info, goal, controls */}
        <aside className="wonderland-sidebar">
          {/* Room card */}
          <div className="room-card">
            <div className="room-card-header">
              <span className="room-label">Current Location</span>
              {status === 'active' && (
                <span className="status-badge active">Exploring</span>
              )}
              {status === 'ended' && (
                <span className="status-badge ended">Ended</span>
              )}
            </div>
            <h2 className="room-name">{currentRoomName || 'The Threshold'}</h2>
            {lastArrival && (
              <p className="room-description">{lastArrival.description}</p>
            )}
          </div>

          {/* Conversation card */}
          {conversation.active && (
            <div className="conversation-card">
              <div className="conversation-card-header">
                <span className="conversation-label">In Conversation</span>
                <span className="conversation-badge">Active</span>
              </div>
              <p className="conversation-npc">{conversation.npc_name}</p>
              <p className="conversation-title">{conversation.npc_title}</p>
              <div className="conversation-messages">
                {conversation.messages.slice(-3).map((msg, idx) => (
                  <div
                    key={idx}
                    className={`conversation-msg ${msg.is_daemon ? 'daemon' : 'npc'}`}
                  >
                    <span className="msg-speaker">{msg.speaker}:</span>
                    <span className="msg-content">{msg.content.slice(0, 60)}{msg.content.length > 60 ? '...' : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Goal card */}
          {goal && (
            <div className="goal-card">
              <div className="goal-card-header">
                <span className="goal-label">Current Goal</span>
                <span className="goal-count">
                  {goal.current_value}/{goal.target_value}
                </span>
              </div>
              <p className="goal-title">{goal.title}</p>
              <div className="goal-bar">
                <div
                  className={`goal-fill ${goal.is_completed ? 'completed' : ''}`}
                  style={{ width: `${goalProgressPercent}%` }}
                />
              </div>
              {goal.is_completed && (
                <p className="goal-complete">Goal Complete!</p>
              )}
            </div>
          )}

          {/* Controls card */}
          <div className="controls-card">
            {(status === 'idle' || status === 'ended') && (
              <>
                <div className="goal-selector">
                  <label htmlFor="goal-preset">Goal</label>
                  <select
                    id="goal-preset"
                    value={selectedPreset}
                    onChange={(e) => setSelectedPreset(e.target.value)}
                  >
                    <option value="">Explore freely</option>
                    {goalPresets.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.title}
                      </option>
                    ))}
                  </select>
                </div>
                <button className="primary-btn full-width" onClick={handleStartSession}>
                  {status === 'ended' ? 'New Exploration' : 'Begin Exploration'}
                </button>
              </>
            )}
            {status === 'connecting' && (
              <button className="primary-btn full-width" disabled>
                Connecting...
              </button>
            )}
            {status === 'active' && (
              <button className="danger-btn full-width" onClick={handleEndSession}>
                End Session
              </button>
            )}
          </div>

          {/* Session stats */}
          {events.length > 0 && (
            <div className="stats-card">
              <div className="stat-row">
                <span className="stat-label">Events</span>
                <span className="stat-value">{events.length}</span>
              </div>
              <div className="stat-row">
                <span className="stat-label">Session</span>
                <span className="stat-value">{session?.session_id?.slice(0, 8) || '—'}</span>
              </div>
            </div>
          )}
        </aside>

        {/* Right main - Event stream */}
        <main className="wonderland-stream">
          <div className="stream-header">
            <span>Event Stream</span>
            <span className="event-count">{events.length} events</span>
          </div>
          <div className="stream-content" ref={eventStreamRef}>
            {events.length === 0 ? (
              <div className="empty-stream">
                {status === 'idle' ? (
                  <>
                    <p className="empty-title">Ready to Explore</p>
                    <p className="empty-desc">Begin an exploration to watch your daemon wander through Wonderland.</p>
                  </>
                ) : status === 'connecting' ? (
                  <p className="empty-desc">Connecting...</p>
                ) : (
                  <p className="empty-desc">Waiting for events...</p>
                )}
              </div>
            ) : (
              events.map((event) => (
                <div
                  key={event.event_id}
                  className={`event-item event-${event.event_type}`}
                >
                  <div className="event-meta">
                    <span className="event-icon">{getEventTypeIcon(event.event_type)}</span>
                    <span className="event-time">{formatTimestamp(event.timestamp)}</span>
                    {event.location_name && event.event_type !== 'travel_through' && (
                      <span className="event-location">{event.location_name}</span>
                    )}
                  </div>
                  <div className="event-content">{event.description}</div>
                  {event.daemon_thought && (
                    <div className="event-thought">
                      <em>({event.daemon_thought})</em>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </main>
      </div>

      {/* Export Modal */}
      {showExportModal && (
        <div className="modal-overlay" onClick={() => setShowExportModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Export Transcript</h3>
              <button className="close-btn" onClick={() => setShowExportModal(false)}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <pre className="export-preview">{exportContent}</pre>
            </div>
            <div className="modal-footer">
              <button className="secondary-btn" onClick={handleCopyExport}>
                Copy
              </button>
              <button className="primary-btn" onClick={handleDownloadExport}>
                Download
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
