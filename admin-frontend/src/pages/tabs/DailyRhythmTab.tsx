import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { rhythmApi, sessionsApi, researchNotesApi, goalsApi } from '../../api/client';
import { TabbedPanel, type Tab } from '../../components/TabbedPanel';
import { ResearchNoteViewer } from '../../components/ResearchNoteViewer';

type ContextView = 'daily' | 'phase';

interface AgendaItem {
  id: string;
  topic: string;
  why: string;
  priority: 'high' | 'medium' | 'low';
  status: 'not_started' | 'in_progress' | 'blocked' | 'complete';
}

interface RhythmPhase {
  id: string;
  name: string;
  activity_type: string;
  start_time: string;
  end_time: string;
  description?: string;
}

interface PhaseStatus {
  id: string;
  name: string;
  activity_type: string;
  window: string;
  status: 'completed' | 'pending' | 'missed' | 'active';
  completed_at: string | null;
  summary: string | null;
  findings: string[] | null;
  session_id: string | null;
  notes_created: string[] | null;
}

interface RhythmStatus {
  date: string;
  current_time: string | null;
  current_phase: string | null;
  phases: PhaseStatus[];
  completed_count: number;
  total_phases: number;
  temporal_context: string | null;
  daily_summary: string | null;
  daily_summary_updated_at: string | null;
  is_today: boolean;
}

interface ResearchNote {
  note_id: string;
  title: string;
  content: string;
  created_at: string;
  sources: Array<{ url: string; title: string }>;
  session_id: string | null;
}

interface RhythmStats {
  days_analyzed: number;
  total_completions: number;
  completions_by_phase: Record<string, number>;
  avg_completions_per_day: number;
}

// Unified session response from /admin/sessions endpoint
interface UnifiedSession {
  session_id: string;
  session_type: string;
  started_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  status: string;
  summary: string | null;
  findings: string[];
  artifacts: Array<{
    type: string;
    content?: string;
    [key: string]: unknown;
  }>;
  metadata: Record<string, unknown>;
}

export function DailyRhythmTab() {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [editedPhases, setEditedPhases] = useState<RhythmPhase[]>([]);
  const [expandedPhase, setExpandedPhase] = useState<string | null>(null);
  const [contextView, setContextView] = useState<ContextView>('daily');
  const [isConfigCollapsed, setIsConfigCollapsed] = useState(true);
  const [selectedDate, setSelectedDate] = useState<string | null>(null); // null = today
  const [triggerPhaseId, setTriggerPhaseId] = useState<string | null>(null); // Phase being triggered
  const [selectedAgendaItem, setSelectedAgendaItem] = useState<string>(''); // '' = self-directed

  // Get available dates for the calendar
  const { data: availableDates } = useQuery<{ dates: string[] }>({
    queryKey: ['rhythm-dates'],
    queryFn: () => rhythmApi.getDates().then((r) => r.data),
  });

  const { data: status, isLoading: statusLoading } = useQuery<RhythmStatus>({
    queryKey: ['rhythm-status', selectedDate],
    queryFn: () => rhythmApi.getStatus(selectedDate || undefined).then((r) => r.data),
    refetchInterval: selectedDate ? false : 60000, // Only auto-refresh for today
  });

  const { data: phasesData } = useQuery<{ phases: RhythmPhase[] }>({
    queryKey: ['rhythm-phases'],
    queryFn: () => rhythmApi.getPhases().then((r) => r.data),
  });

  const { data: stats } = useQuery<RhythmStats>({
    queryKey: ['rhythm-stats'],
    queryFn: () => rhythmApi.getStats(7).then((r) => r.data),
  });

  // Get research agenda items for trigger modal
  const { data: agendaData } = useQuery<{ items: AgendaItem[] }>({
    queryKey: ['research-agenda'],
    queryFn: () => goalsApi.getAgenda().then((r) => r.data),
    enabled: triggerPhaseId !== null, // Only fetch when modal is open
  });

  // Filter to available agenda items (not complete)
  const availableAgendaItems = agendaData?.items?.filter(
    item => item.status !== 'complete'
  ) || [];

  // Get expanded phase data
  const expandedPhaseData = status?.phases.find(p => p.id === expandedPhase);

  // Fetch unified session details for any activity type
  const { data: unifiedSession } = useQuery<UnifiedSession>({
    queryKey: ['unified-session', expandedPhaseData?.session_id, expandedPhaseData?.activity_type],
    queryFn: () => sessionsApi.getSession(
      expandedPhaseData!.session_id!,
      expandedPhaseData!.activity_type
    ).then((r) => r.data),
    enabled: !!expandedPhaseData?.session_id && !!expandedPhaseData?.activity_type,
  });

  // Fetch notes for research-type phases (for note viewer tabs)
  const { data: phaseNotes } = useQuery<{ notes: ResearchNote[] }>({
    queryKey: ['phase-notes', expandedPhaseData?.session_id],
    queryFn: () => researchNotesApi.getBySession(expandedPhaseData!.session_id!).then((r) => r.data),
    enabled: !!expandedPhaseData?.session_id &&
             (expandedPhaseData?.activity_type === 'research' || expandedPhaseData?.activity_type === 'any') &&
             (expandedPhaseData?.notes_created?.length ?? 0) > 0,
  });

  // Build tabs for phase detail panel - now uses unified session data
  const buildPhaseTabs = (): Tab[] => {
    if (!expandedPhaseData) return [];

    const activityType = expandedPhaseData.activity_type;
    const isResearch = activityType === 'research' || activityType === 'any';

    // Get icon based on activity type
    const getIcon = () => {
      switch (activityType) {
        case 'reflection': return '~';
        case 'meta_reflection': return '◎';
        case 'research':
        case 'curiosity': return '*';
        case 'synthesis': return '⟁';
        case 'consolidation': return '▣';
        case 'growth_edge': return '↗';
        case 'knowledge_building': return '📖';
        case 'writing': return '✎';
        case 'world_state': return '🌍';
        case 'creative':
        case 'creative_output': return '✧';
        default: return '*';
      }
    };

    const tabs: Tab[] = [
      {
        id: 'summary',
        label: 'Summary',
        icon: getIcon(),
        content: (
          <div className="unified-session-summary">
            {/* Summary */}
            {(unifiedSession?.summary || expandedPhaseData.summary) && (
              <div className="session-summary-text">
                <ReactMarkdown>
                  {unifiedSession?.summary || expandedPhaseData.summary || ''}
                </ReactMarkdown>
              </div>
            )}

            {/* Findings/Insights */}
            {(unifiedSession?.findings?.length || expandedPhaseData.findings?.length) ? (
              <div className="session-findings">
                <h4>Key Insights</h4>
                <ul>
                  {(unifiedSession?.findings || expandedPhaseData.findings || []).map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* Metadata specific to session type */}
            {unifiedSession?.metadata && (
              <div className="session-metadata">
                {unifiedSession.metadata.theme ? (
                  <div className="metadata-item">
                    <span className="label">Theme:</span> {String(unifiedSession.metadata.theme)}
                  </div>
                ) : null}
                {unifiedSession.metadata.focus ? (
                  <div className="metadata-item">
                    <span className="label">Focus:</span> {String(unifiedSession.metadata.focus)}
                  </div>
                ) : null}
                {unifiedSession.metadata.mode ? (
                  <div className="metadata-item">
                    <span className="label">Mode:</span> {String(unifiedSession.metadata.mode)}
                  </div>
                ) : null}
                {(unifiedSession.metadata.questions_raised as string[])?.length > 0 ? (
                  <div className="metadata-questions">
                    <h4>Questions Raised</h4>
                    <ul>
                      {(unifiedSession.metadata.questions_raised as string[]).map((q, i) => (
                        <li key={i}>{q}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}

            {/* No content fallback */}
            {!unifiedSession?.summary && !expandedPhaseData.summary && (
              <div className="empty-summary">
                <p>Session completed. Summary not available.</p>
              </div>
            )}
          </div>
        ),
      },
    ];

    // Add artifacts tab if there are artifacts
    if (unifiedSession?.artifacts && unifiedSession.artifacts.length > 0) {
      tabs.push({
        id: 'artifacts',
        label: `Artifacts (${unifiedSession.artifacts.length})`,
        icon: '⬡',
        content: (
          <div className="session-artifacts">
            {unifiedSession.artifacts.map((artifact, i) => (
              <div key={i} className="artifact-item">
                <span className="artifact-type">{artifact.type}</span>
                {artifact.content && (
                  <div className="artifact-content">{artifact.content}</div>
                )}
              </div>
            ))}
          </div>
        ),
      });
    }

    // Add tabs for each note (research or 'any' types)
    if (isResearch) {
      const notes = phaseNotes?.notes || [];
      notes.forEach((note, i) => {
        tabs.push({
          id: note.note_id,
          label: note.title?.slice(0, 15) || `Note ${i + 1}`,
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
    }

    return tabs;
  };

  const updateMutation = useMutation({
    mutationFn: (phases: RhythmPhase[]) => rhythmApi.updatePhases(phases),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rhythm-phases'] });
      queryClient.invalidateQueries({ queryKey: ['rhythm-status'] });
      setIsEditing(false);
    },
  });

  const triggerMutation = useMutation({
    mutationFn: ({ phaseId, agendaItemId }: { phaseId: string; agendaItemId?: string }) =>
      rhythmApi.triggerPhase(phaseId, agendaItemId ? { agenda_item_id: agendaItemId } : undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rhythm-status'] });
      queryClient.invalidateQueries({ queryKey: ['rhythm-stats'] });
      queryClient.invalidateQueries({ queryKey: ['research-agenda'] });
      setTriggerPhaseId(null);
      setSelectedAgendaItem('');
    },
  });

  const regenerateSummaryMutation = useMutation({
    mutationFn: () => rhythmApi.regenerateSummary(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rhythm-status'] });
    },
  });

  const handleTriggerClick = (phaseId: string, activityType: string) => {
    // Types that can use agenda items for focus
    const agendaFocusTypes = ['research', 'any', 'knowledge_building', 'curiosity'];

    if (agendaFocusTypes.includes(activityType)) {
      // Show agenda selection modal for research-like activities
      setTriggerPhaseId(phaseId);
      setSelectedAgendaItem('');
    } else {
      // Trigger directly for reflection, synthesis, meta_reflection, etc.
      triggerMutation.mutate({ phaseId });
    }
  };

  const handleTriggerConfirm = () => {
    if (triggerPhaseId) {
      triggerMutation.mutate({
        phaseId: triggerPhaseId,
        agendaItemId: selectedAgendaItem || undefined,
      });
    }
  };

  const handleEditStart = () => {
    if (phasesData?.phases) {
      setEditedPhases([...phasesData.phases]);
      setIsEditing(true);
    }
  };

  const handleEditCancel = () => {
    setIsEditing(false);
    setEditedPhases([]);
  };

  const handleEditSave = () => {
    updateMutation.mutate(editedPhases);
  };

  const handlePhaseChange = (index: number, field: keyof RhythmPhase, value: string) => {
    const updated = [...editedPhases];
    updated[index] = { ...updated[index], [field]: value };
    setEditedPhases(updated);
  };

  const getStatusIcon = (phaseStatus: string) => {
    switch (phaseStatus) {
      case 'completed': return '\u2713'; // checkmark
      case 'pending': return '\u25cb';   // circle
      case 'missed': return '\u2717';    // x
      case 'active': return '\u25cf';    // filled circle
      default: return '\u25cb';
    }
  };

  const getStatusColor = (phaseStatus: string) => {
    switch (phaseStatus) {
      case 'completed': return '#c3e88d';
      case 'pending': return '#888';
      case 'missed': return '#f07178';
      case 'active': return '#89ddff';
      default: return '#888';
    }
  };

  const getActivityTypeColor = (type: string) => {
    switch (type) {
      case 'reflection': return '#c792ea';       // purple - contemplation
      case 'research': return '#89ddff';         // cyan - exploration
      case 'synthesis': return '#82aaff';        // blue - integration
      case 'meta_reflection': return '#f78c6c';  // orange - analysis
      case 'consolidation': return '#c3e88d';    // green - organization
      case 'growth_edge': return '#ff5370';      // red - practice
      case 'knowledge_building': return '#ffcb6b'; // yellow - learning
      case 'writing': return '#f07178';          // coral - expression
      case 'curiosity': return '#89ddff';        // cyan - exploration (same as research)
      case 'world_state': return '#b2ccd6';      // slate - grounding
      case 'creative':
      case 'creative_output': return '#c792ea';  // purple - creativity
      case 'any': return '#888';                 // gray - flexible
      default: return '#888';
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
  };

  const formatShortDate = (dateStr: string) => {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const getTodayStr = () => {
    const now = new Date();
    return now.toISOString().split('T')[0];
  };

  const navigateDate = (direction: 'prev' | 'next') => {
    const dates = availableDates?.dates || [];
    const currentDate = selectedDate || getTodayStr();
    const currentIndex = dates.indexOf(currentDate);

    if (direction === 'prev') {
      // Go to previous date in the list
      if (currentIndex > 0) {
        setSelectedDate(dates[currentIndex - 1]);
      } else if (currentIndex === -1 && dates.length > 0) {
        // Not in list (viewing today but today has no record), go to most recent
        const mostRecent = dates[dates.length - 1];
        if (mostRecent < currentDate) {
          setSelectedDate(mostRecent);
        }
      }
    } else {
      // Go to next date
      if (currentIndex < dates.length - 1) {
        setSelectedDate(dates[currentIndex + 1]);
      } else if (currentIndex === dates.length - 1) {
        // At the end of the list, go to today if we're not already there
        const today = getTodayStr();
        if (currentDate < today) {
          setSelectedDate(null); // null = today
        }
      }
    }
  };

  const canNavigatePrev = () => {
    const dates = availableDates?.dates || [];
    if (dates.length === 0) return false;
    const currentDate = selectedDate || getTodayStr();
    const currentIndex = dates.indexOf(currentDate);
    // Can go prev if there are earlier dates
    if (currentIndex > 0) return true;
    if (currentIndex === -1 && dates.length > 0) {
      return dates[dates.length - 1] < currentDate;
    }
    return false;
  };

  const canNavigateNext = () => {
    const dates = availableDates?.dates || [];
    const currentDate = selectedDate || getTodayStr();
    const today = getTodayStr();
    // Can go next if not viewing today and there are later dates
    if (currentDate >= today) return false;
    const currentIndex = dates.indexOf(currentDate);
    return currentIndex < dates.length - 1 || currentDate < today;
  };

  // Handle phase click - switch to phase view
  const handlePhaseClick = (phaseId: string) => {
    if (expandedPhase === phaseId) {
      // Clicking same phase - toggle back to daily view
      setExpandedPhase(null);
      setContextView('daily');
    } else {
      setExpandedPhase(phaseId);
      setContextView('phase');
    }
  };

  return (
    <div className="rhythm-tab">
      <div className="rhythm-layout-v2">
        {/* Sidebar */}
        <div className="sidebar-column">
          {/* Date Navigation */}
          <div className="date-nav-panel">
            <button
              className="date-nav-btn"
              onClick={() => navigateDate('prev')}
              disabled={!canNavigatePrev()}
              title="Previous day with activity"
            >
              &lt;
            </button>
            <div className="date-nav-center">
              <span className="date-nav-label">
                {selectedDate ? formatShortDate(selectedDate) : 'Today'}
              </span>
              {selectedDate && (
                <button
                  className="today-btn"
                  onClick={() => setSelectedDate(null)}
                  title="Go to today"
                >
                  Today
                </button>
              )}
            </div>
            <button
              className="date-nav-btn"
              onClick={() => navigateDate('next')}
              disabled={!canNavigateNext()}
              title="Next day with activity"
            >
              &gt;
            </button>
          </div>

          {/* Progress + Stats Combined */}
          <div className="progress-stats-panel">
            <div className="progress-section">
              <h3>{status?.is_today ? "Today's Progress" : "Progress"}</h3>
              {statusLoading ? (
                <div className="loading-state small">Loading...</div>
              ) : status ? (
                <>
                  <div className="progress-bar-container">
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${(status.completed_count / status.total_phases) * 100}%` }}
                    />
                  </div>
                  <div className="progress-text">
                    {status.completed_count} of {status.total_phases} phases completed
                  </div>
                </>
              ) : null}
            </div>

            {/* Horizontal Stats Row */}
            {stats && (
              <div className="stats-row-horizontal">
                <div className="stat-item">
                  <span className="stat-value">{stats.total_completions}</span>
                  <span className="stat-label">Total</span>
                </div>
                <div className="stat-item">
                  <span className="stat-value">{(stats.avg_completions_per_day ?? 0).toFixed(1)}</span>
                  <span className="stat-label">Avg/Day</span>
                </div>
                <div className="stat-item">
                  <span className="stat-value">{stats.days_analyzed ?? 0}</span>
                  <span className="stat-label">Days</span>
                </div>
                <div className="stat-item">
                  <span className="stat-value">
                    {stats.days_analyzed ? Math.round((stats.total_completions / (stats.days_analyzed * 4)) * 100) : 0}%
                  </span>
                  <span className="stat-label">Rate</span>
                </div>
              </div>
            )}
          </div>

          {/* Collapsible Phase Configuration */}
          <div className={`config-panel ${isConfigCollapsed ? 'collapsed' : ''}`}>
            <div
              className="config-header clickable"
              onClick={() => !isEditing && setIsConfigCollapsed(!isConfigCollapsed)}
            >
              <div className="config-header-left">
                <span className="collapse-icon">{isConfigCollapsed ? '▶' : '▼'}</span>
                <h3>Phase Configuration</h3>
              </div>
              {!isEditing ? (
                <button
                  className="edit-btn"
                  onClick={(e) => { e.stopPropagation(); handleEditStart(); setIsConfigCollapsed(false); }}
                >
                  Edit
                </button>
              ) : (
                <div className="edit-actions" onClick={(e) => e.stopPropagation()}>
                  <button className="save-btn" onClick={handleEditSave} disabled={updateMutation.isPending}>
                    {updateMutation.isPending ? 'Saving...' : 'Save'}
                  </button>
                  <button className="cancel-btn" onClick={handleEditCancel}>Cancel</button>
                </div>
              )}
            </div>
            {!isConfigCollapsed && (
              isEditing ? (
                <div className="phase-editor">
                  {editedPhases.map((phase, i) => (
                    <div key={phase.id} className="phase-edit-row">
                      <input
                        type="text"
                        value={phase.name}
                        onChange={(e) => handlePhaseChange(i, 'name', e.target.value)}
                        className="phase-name-input"
                      />
                      <div className="time-inputs">
                        <input
                          type="time"
                          value={phase.start_time}
                          onChange={(e) => handlePhaseChange(i, 'start_time', e.target.value)}
                        />
                        <span>-</span>
                        <input
                          type="time"
                          value={phase.end_time}
                          onChange={(e) => handlePhaseChange(i, 'end_time', e.target.value)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="phases-list">
                  {phasesData?.phases.map((phase) => (
                    <div key={phase.id} className="phase-config-item">
                      <span className="phase-name">{phase.name}</span>
                      <span className="phase-time">{phase.start_time}-{phase.end_time}</span>
                      <span
                        className="phase-type"
                        style={{ color: getActivityTypeColor(phase.activity_type) }}
                      >
                        {phase.activity_type}
                      </span>
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        </div>

        {/* Main Content - Timeline */}
        <div className="detail-column">
          {statusLoading ? (
            <div className="loading-state">Loading rhythm status...</div>
          ) : status ? (
            <div className="rhythm-detail">
              <div className="detail-header">
                <h2>{formatDate(status.date)}</h2>
                {status.is_today && status.current_time && (
                  <span className="current-time">Current time: {status.current_time}</span>
                )}
              </div>

              {/* Timeline */}
              <div className="rhythm-timeline">
                {status.phases.map((phase, i) => (
                  <div
                    key={phase.id}
                    className={`timeline-phase ${phase.status} ${status.current_phase === phase.id ? 'current' : ''} ${expandedPhase === phase.id ? 'expanded' : ''}`}
                  >
                    <div className="phase-indicator">
                      <span
                        className="status-icon"
                        style={{ color: getStatusColor(phase.status) }}
                      >
                        {getStatusIcon(phase.status)}
                      </span>
                      {i < status.phases.length - 1 && <div className="timeline-connector" />}
                    </div>
                    <div className="phase-content">
                      <div
                        className="phase-header clickable"
                        onClick={() => handlePhaseClick(phase.id)}
                      >
                        <span className="phase-name">{phase.name}</span>
                        <span className="phase-window">{phase.window}</span>
                        {(phase.summary || phase.notes_created?.length) && (
                          <span className="expand-indicator">{expandedPhase === phase.id ? '▼' : '▶'}</span>
                        )}
                      </div>
                      <div className="phase-meta">
                        <span
                          className="activity-type"
                          style={{ color: getActivityTypeColor(phase.activity_type) }}
                        >
                          {phase.activity_type}
                        </span>
                        <span
                          className="phase-status"
                          style={{ color: getStatusColor(phase.status) }}
                        >
                          {phase.status}
                        </span>
                        {phase.completed_at && (
                          <span className="completed-at">
                            completed at {new Date(phase.completed_at).toLocaleTimeString()}
                          </span>
                        )}
                        {phase.notes_created && phase.notes_created.length > 0 && (
                          <span className="notes-count">
                            {phase.notes_created.length} note{phase.notes_created.length > 1 ? 's' : ''}
                          </span>
                        )}
                        {(phase.status === 'missed' || phase.status === 'pending') && status?.is_today && (
                          <button
                            className="trigger-btn"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleTriggerClick(phase.id, phase.activity_type);
                            }}
                            disabled={triggerMutation.isPending}
                            title={`Start ${phase.activity_type === 'reflection' ? 'reflection' : 'research'} session for this phase`}
                          >
                            {triggerMutation.isPending ? '...' : '▶ Trigger'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Temporal Context - only shown for today */}
              {status.is_today && status.temporal_context && (
                <div className="temporal-context">
                  <h4>Temporal Context</h4>
                  <pre className="context-text">{status.temporal_context}</pre>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">#</div>
              <p>No rhythm data available</p>
            </div>
          )}
        </div>

        {/* Context Panel - Unified Phase Detail + Daily Summary */}
        <div className="context-panel">
          {/* View Toggle */}
          <div className="context-header">
            <div className="context-tabs">
              <button
                className={`context-tab ${contextView === 'daily' ? 'active' : ''}`}
                onClick={() => { setContextView('daily'); setExpandedPhase(null); }}
              >
                {status?.is_today ? "Today's Summary" : "Daily Summary"}
              </button>
              <button
                className={`context-tab ${contextView === 'phase' ? 'active' : ''}`}
                onClick={() => setContextView('phase')}
                disabled={!expandedPhase}
              >
                Phase Detail {expandedPhaseData && `(${expandedPhaseData.name})`}
              </button>
            </div>
          </div>

          <div className="context-content">
            {contextView === 'daily' ? (
              /* Daily Summary View */
              status?.daily_summary ? (
                <div className="daily-summary-view">
                  <div className="summary-content markdown-content">
                    <ReactMarkdown>{status.daily_summary}</ReactMarkdown>
                  </div>
                  <div className="summary-footer">
                    {status.daily_summary_updated_at && (
                      <span className="summary-updated">
                        Last updated: {new Date(status.daily_summary_updated_at).toLocaleTimeString()}
                      </span>
                    )}
                    {status.is_today && status.completed_count > 0 && (
                      <button
                        className="regenerate-btn"
                        onClick={() => regenerateSummaryMutation.mutate()}
                        disabled={regenerateSummaryMutation.isPending}
                        title="Regenerate daily summary from completed phases"
                      >
                        {regenerateSummaryMutation.isPending ? 'Regenerating...' : '↻ Regenerate'}
                      </button>
                    )}
                  </div>
                </div>
              ) : status?.is_today && status?.completed_count > 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">*</div>
                  <p>Summary not generated yet</p>
                  <button
                    className="regenerate-btn"
                    onClick={() => regenerateSummaryMutation.mutate()}
                    disabled={regenerateSummaryMutation.isPending}
                  >
                    {regenerateSummaryMutation.isPending ? 'Generating...' : 'Generate Summary'}
                  </button>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">*</div>
                  <p>No activities completed yet</p>
                  <p className="empty-hint">Summary will appear after phases complete</p>
                </div>
              )
            ) : expandedPhaseData ? (
              /* Phase Detail View */
              <div className="phase-detail-view">
                <div className="phase-detail-meta">
                  <span
                    className="phase-type-badge"
                    style={{
                      color: getActivityTypeColor(expandedPhaseData.activity_type),
                      borderColor: getActivityTypeColor(expandedPhaseData.activity_type)
                    }}
                  >
                    {expandedPhaseData.activity_type}
                  </span>
                  <span className="phase-window-badge">{expandedPhaseData.window}</span>
                  <span
                    className="phase-status-badge"
                    style={{ color: getStatusColor(expandedPhaseData.status) }}
                  >
                    {expandedPhaseData.status}
                  </span>
                </div>
                <div className="phase-detail-body">
                  {expandedPhaseData.summary || expandedPhaseData.notes_created?.length || unifiedSession?.summary ? (
                    <TabbedPanel tabs={buildPhaseTabs()} defaultTab="summary" className="compact" />
                  ) : (
                    <div className="empty-state">
                      <div className="empty-icon">~</div>
                      <p>No summary available yet</p>
                      <p className="empty-hint">Summary will appear after the phase completes</p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-icon">▶</div>
                <p>Select a phase to view details</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Trigger Modal for Research Agenda Selection */}
      {triggerPhaseId && (
        <div className="trigger-modal-overlay" onClick={() => setTriggerPhaseId(null)}>
          <div className="trigger-modal" onClick={e => e.stopPropagation()}>
            <div className="trigger-modal-header">
              <h3>Start Research Session</h3>
              <button className="modal-close-btn" onClick={() => setTriggerPhaseId(null)}>×</button>
            </div>
            <div className="trigger-modal-body">
              <label className="agenda-select-label">
                Research Focus
              </label>
              <select
                className="agenda-select"
                value={selectedAgendaItem}
                onChange={e => setSelectedAgendaItem(e.target.value)}
              >
                <option value="">Self-directed research</option>
                {availableAgendaItems.length > 0 && (
                  <optgroup label="Research Agenda">
                    {availableAgendaItems.map(item => (
                      <option key={item.id} value={item.id}>
                        [{item.priority}] {item.topic}
                        {item.status === 'in_progress' ? ' (in progress)' : ''}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {selectedAgendaItem && (
                <div className="agenda-item-why">
                  {availableAgendaItems.find(i => i.id === selectedAgendaItem)?.why}
                </div>
              )}
            </div>
            <div className="trigger-modal-footer">
              <button
                className="modal-cancel-btn"
                onClick={() => setTriggerPhaseId(null)}
              >
                Cancel
              </button>
              <button
                className="modal-confirm-btn"
                onClick={handleTriggerConfirm}
                disabled={triggerMutation.isPending}
              >
                {triggerMutation.isPending ? 'Starting...' : 'Start Session'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
