import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { goalsApi, schedulesApi } from '../../api/client';
import ReactMarkdown from 'react-markdown';

type TabType = 'overview' | 'questions' | 'agenda' | 'schedules' | 'artifacts' | 'initiatives' | 'progress';

interface ResearchSchedule {
  schedule_id: string;
  created_at: string;
  status: string;
  requested_by: string;
  focus_description: string;
  focus_item_id: string | null;
  recurrence: string;
  preferred_time: string;
  duration_minutes: number;
  mode: string;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  last_run: string | null;
  next_run: string | null;
  run_count: number;
  last_session_id: string | null;
  notes: string;
}

interface WorkingQuestion {
  id: string;
  question: string;
  context: string;
  status: string;
  created_at: string;
  insights: Array<{ timestamp: string; insight: string; source: string }>;
  next_steps: string[];
  related_artifacts: string[];
  related_agenda_items: string[];
}

interface ResearchAgendaItem {
  id: string;
  topic: string;
  why: string;
  priority: string;
  status: string;
  created_at: string;
  sources_reviewed: Array<{ timestamp: string; source: string; summary: string; useful: boolean }>;
  key_findings: Array<{ timestamp: string; finding: string }>;
  blockers: Array<{ timestamp: string; blocker: string; resolved: boolean; resolved_at?: string }>;
  related_questions: string[];
}

interface SynthesisArtifact {
  slug: string;
  title: string;
  status: string;
  confidence: string;
  updated: string;
}

interface Initiative {
  id: string;
  description: string;
  goal_context: string;
  urgency: string;
  created_at: string;
  status: string;
  response?: string;
  responded_at?: string;
}

interface ProgressEntry {
  id: string;
  timestamp: string;
  type: string;
  description: string;
  related_items: string[];
  outcome?: string;
}

interface ReviewSummary {
  active_questions: number;
  stalled_questions: number;
  research_in_progress: number;
  research_blocked: number;
  synthesis_artifacts: number;
  pending_initiatives: number;
}

interface GoalReview {
  summary: ReviewSummary;
  active_questions: WorkingQuestion[];
  stalled_questions: WorkingQuestion[];
  research_in_progress: ResearchAgendaItem[];
  blocked_research: ResearchAgendaItem[];
  artifacts: SynthesisArtifact[];
  pending_initiatives: Initiative[];
  recent_progress?: ProgressEntry[];
}

export function GoalsTab() {
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [selectedAgendaItem, setSelectedAgendaItem] = useState<string | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [initiativeResponse, setInitiativeResponse] = useState<{ id: string; status: string; response: string } | null>(null);
  const [scheduleRejection, setScheduleRejection] = useState<{ id: string; reason: string } | null>(null);

  const queryClient = useQueryClient();

  // Queries
  const { data: reviewData, isLoading: reviewLoading } = useQuery({
    queryKey: ['goals', 'review'],
    queryFn: () => goalsApi.getReview(true),
  });

  const { data: questionsData } = useQuery({
    queryKey: ['goals', 'questions'],
    queryFn: () => goalsApi.getQuestions(),
    enabled: activeTab === 'questions',
  });

  const { data: agendaData } = useQuery({
    queryKey: ['goals', 'agenda'],
    queryFn: () => goalsApi.getAgenda(),
    enabled: activeTab === 'agenda',
  });

  const { data: artifactsData } = useQuery({
    queryKey: ['goals', 'artifacts'],
    queryFn: () => goalsApi.getArtifacts(),
    enabled: activeTab === 'artifacts',
  });

  const { data: selectedArtifactData } = useQuery({
    queryKey: ['goals', 'artifact', selectedArtifact],
    queryFn: () => goalsApi.getArtifact(selectedArtifact!),
    enabled: !!selectedArtifact,
  });

  const { data: initiativesData } = useQuery({
    queryKey: ['goals', 'initiatives'],
    queryFn: () => goalsApi.getInitiatives(),
    enabled: activeTab === 'initiatives' || activeTab === 'overview',
  });

  const { data: progressData } = useQuery({
    queryKey: ['goals', 'progress'],
    queryFn: () => goalsApi.getProgress({ limit: 50 }),
    enabled: activeTab === 'progress',
  });

  const { data: nextActionsData } = useQuery({
    queryKey: ['goals', 'next-actions'],
    queryFn: () => goalsApi.getNextActions(),
    enabled: activeTab === 'overview',
  });

  const { data: schedulesData } = useQuery({
    queryKey: ['research', 'schedules'],
    queryFn: () => schedulesApi.getAll(),
    enabled: activeTab === 'schedules' || activeTab === 'overview',
  });

  // Mutations
  const respondMutation = useMutation({
    mutationFn: ({ id, status, response }: { id: string; status: string; response: string }) =>
      goalsApi.respondToInitiative(id, status, response),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals'] });
      setInitiativeResponse(null);
    },
  });

  const approveScheduleMutation = useMutation({
    mutationFn: (id: string) => schedulesApi.approve(id, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research', 'schedules'] });
    },
  });

  const rejectScheduleMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => schedulesApi.reject(id, reason || 'No reason provided'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research', 'schedules'] });
      setScheduleRejection(null);
    },
  });

  const pauseScheduleMutation = useMutation({
    mutationFn: (id: string) => schedulesApi.pause(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research', 'schedules'] });
    },
  });

  const resumeScheduleMutation = useMutation({
    mutationFn: (id: string) => schedulesApi.resume(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research', 'schedules'] });
    },
  });

  const review: GoalReview | undefined = reviewData?.data?.review;

  const renderOverview = () => {
    if (reviewLoading || !review) {
      return <div className="loading">Loading goals overview...</div>;
    }

    const pendingInitiatives = initiativesData?.data?.initiatives?.filter(
      (i: Initiative) => i.status === 'proposed'
    ) || [];

    return (
      <div className="goals-overview">
        {/* Summary Cards */}
        <div className="summary-cards">
          <div className="summary-card">
            <div className="card-value">{review.summary.active_questions}</div>
            <div className="card-label">Active Questions</div>
            {review.summary.stalled_questions > 0 && (
              <div className="card-warning">{review.summary.stalled_questions} stalled</div>
            )}
          </div>
          <div className="summary-card">
            <div className="card-value">{review.summary.research_in_progress}</div>
            <div className="card-label">Research In Progress</div>
            {review.summary.research_blocked > 0 && (
              <div className="card-warning">{review.summary.research_blocked} blocked</div>
            )}
          </div>
          <div className="summary-card">
            <div className="card-value">{review.summary.synthesis_artifacts}</div>
            <div className="card-label">Synthesis Artifacts</div>
          </div>
          <div className="summary-card initiatives">
            <div className="card-value">{review.summary.pending_initiatives}</div>
            <div className="card-label">Pending Initiatives</div>
          </div>
        </div>

        {/* Pending Initiatives Alert */}
        {pendingInitiatives.length > 0 && (
          <div className="initiatives-alert">
            <h3>Cass Needs Your Attention</h3>
            <div className="initiative-list">
              {pendingInitiatives.map((init: Initiative) => (
                <div key={init.id} className={`initiative-item urgency-${init.urgency}`}>
                  <div className="initiative-header">
                    <span className="urgency-badge">{init.urgency}</span>
                    <span className="initiative-date">
                      {new Date(init.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <div className="initiative-description">{init.description}</div>
                  <div className="initiative-context">Context: {init.goal_context}</div>
                  <div className="initiative-actions">
                    <button
                      onClick={() => setInitiativeResponse({ id: init.id, status: 'acknowledged', response: '' })}
                      className="btn-acknowledge"
                    >
                      Acknowledge
                    </button>
                    <button
                      onClick={() => setInitiativeResponse({ id: init.id, status: 'completed', response: '' })}
                      className="btn-complete"
                    >
                      Complete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Next Actions */}
        {(nextActionsData?.data?.actions?.length ?? 0) > 0 && (
          <div className="next-actions-section">
            <h3>Next Actions</h3>
            <div className="actions-list">
              {nextActionsData?.data?.actions?.slice(0, 5).map((action: {
                type: string;
                action: string;
                context: string;
                priority: string;
              }, idx: number) => (
                <div key={idx} className={`action-item priority-${action.priority}`}>
                  <span className="action-type">{action.type.replace('_', ' ')}</span>
                  <span className="action-text">{action.action}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active Questions Preview */}
        {review.active_questions.length > 0 && (
          <div className="section-preview">
            <h3>Active Working Questions</h3>
            <div className="questions-preview">
              {review.active_questions.slice(0, 3).map((q) => (
                <div key={q.id} className="question-preview-item">
                  <div className="question-text">{q.question}</div>
                  <div className="question-meta">
                    {q.insights.length} insights | {q.next_steps.length} next steps
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Progress */}
        {review.recent_progress && review.recent_progress.length > 0 && (
          <div className="section-preview">
            <h3>Recent Progress</h3>
            <div className="progress-preview">
              {review.recent_progress.slice(0, 5).map((entry) => (
                <div key={entry.id} className="progress-entry">
                  <span className={`progress-type type-${entry.type}`}>{entry.type}</span>
                  <span className="progress-desc">{entry.description}</span>
                  <span className="progress-time">
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderQuestions = () => {
    const questions: WorkingQuestion[] = questionsData?.data?.questions || [];

    if (questions.length === 0) {
      return <div className="empty-state">No working questions yet. Cass will create them as she explores.</div>;
    }

    return (
      <div className="questions-view">
        <div className="questions-list">
          {questions.map((q) => (
            <div
              key={q.id}
              className={`question-card ${selectedQuestion === q.id ? 'selected' : ''} status-${q.status}`}
              onClick={() => setSelectedQuestion(q.id === selectedQuestion ? null : q.id)}
            >
              <div className="question-header">
                <span className={`status-badge status-${q.status}`}>{q.status}</span>
                <span className="question-date">{new Date(q.created_at).toLocaleDateString()}</span>
              </div>
              <div className="question-text">{q.question}</div>
              <div className="question-stats">
                <span>{q.insights.length} insights</span>
                <span>{q.next_steps.length} next steps</span>
              </div>

              {selectedQuestion === q.id && (
                <div className="question-details">
                  <div className="detail-section">
                    <h4>Context</h4>
                    <p>{q.context}</p>
                  </div>

                  {q.insights.length > 0 && (
                    <div className="detail-section">
                      <h4>Insights</h4>
                      {q.insights.map((insight, idx) => (
                        <div key={idx} className="insight-item">
                          <div className="insight-text">{insight.insight}</div>
                          <div className="insight-meta">
                            Source: {insight.source} | {new Date(insight.timestamp).toLocaleDateString()}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {q.next_steps.length > 0 && (
                    <div className="detail-section">
                      <h4>Next Steps</h4>
                      <ul>
                        {q.next_steps.map((step, idx) => (
                          <li key={idx}>{step}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderAgenda = () => {
    const items: ResearchAgendaItem[] = agendaData?.data?.items || [];

    if (items.length === 0) {
      return <div className="empty-state">No research agenda items yet.</div>;
    }

    const byPriority = {
      high: items.filter(i => i.priority === 'high'),
      medium: items.filter(i => i.priority === 'medium'),
      low: items.filter(i => i.priority === 'low'),
    };

    return (
      <div className="agenda-view">
        {(['high', 'medium', 'low'] as const).map((priority) => (
          byPriority[priority].length > 0 && (
            <div key={priority} className="priority-section">
              <h3 className={`priority-header priority-${priority}`}>{priority.charAt(0).toUpperCase() + priority.slice(1)} Priority</h3>
              <div className="agenda-items">
                {byPriority[priority].map((item) => (
                  <div
                    key={item.id}
                    className={`agenda-card ${selectedAgendaItem === item.id ? 'selected' : ''} status-${item.status}`}
                    onClick={() => setSelectedAgendaItem(item.id === selectedAgendaItem ? null : item.id)}
                  >
                    <div className="agenda-header">
                      <span className={`status-badge status-${item.status}`}>{item.status.replace('_', ' ')}</span>
                    </div>
                    <div className="agenda-topic">{item.topic}</div>
                    <div className="agenda-why">{item.why}</div>
                    <div className="agenda-stats">
                      <span>{item.sources_reviewed.length} sources</span>
                      <span>{item.key_findings.length} findings</span>
                      {item.blockers.filter(b => !b.resolved).length > 0 && (
                        <span className="blocker-count">
                          {item.blockers.filter(b => !b.resolved).length} blockers
                        </span>
                      )}
                    </div>

                    {selectedAgendaItem === item.id && (
                      <div className="agenda-details">
                        {item.sources_reviewed.length > 0 && (
                          <div className="detail-section">
                            <h4>Sources Reviewed</h4>
                            {item.sources_reviewed.map((src, idx) => (
                              <div key={idx} className={`source-item ${src.useful ? 'useful' : 'not-useful'}`}>
                                <div className="source-name">{src.source}</div>
                                <div className="source-summary">{src.summary}</div>
                              </div>
                            ))}
                          </div>
                        )}

                        {item.key_findings.length > 0 && (
                          <div className="detail-section">
                            <h4>Key Findings</h4>
                            <ul>
                              {item.key_findings.map((f, idx) => (
                                <li key={idx}>{f.finding}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {item.blockers.length > 0 && (
                          <div className="detail-section">
                            <h4>Blockers</h4>
                            {item.blockers.map((b, idx) => (
                              <div key={idx} className={`blocker-item ${b.resolved ? 'resolved' : 'active'}`}>
                                {b.blocker}
                                {b.resolved && <span className="resolved-badge">Resolved</span>}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )
        ))}
      </div>
    );
  };

  const renderArtifacts = () => {
    const artifacts: SynthesisArtifact[] = artifactsData?.data?.artifacts || [];

    if (artifacts.length === 0) {
      return <div className="empty-state">No synthesis artifacts yet. Cass will create them as she develops positions.</div>;
    }

    return (
      <div className="artifacts-view">
        <div className="artifacts-list">
          {artifacts.map((a) => (
            <div
              key={a.slug}
              className={`artifact-card ${selectedArtifact === a.slug ? 'selected' : ''}`}
              onClick={() => setSelectedArtifact(a.slug === selectedArtifact ? null : a.slug)}
            >
              <div className="artifact-header">
                <span className={`status-badge status-${a.status}`}>{a.status}</span>
                <span className="artifact-confidence">Confidence: {a.confidence}</span>
              </div>
              <div className="artifact-title">{a.title}</div>
              <div className="artifact-updated">Updated: {a.updated}</div>
            </div>
          ))}
        </div>

        {selectedArtifact && selectedArtifactData?.data?.artifact && (
          <div className="artifact-content">
            <h3>{selectedArtifactData.data.artifact.metadata?.title || selectedArtifact}</h3>
            <div className="artifact-meta">
              Status: {selectedArtifactData.data.artifact.metadata?.status} |
              Confidence: {selectedArtifactData.data.artifact.metadata?.confidence} |
              Updated: {selectedArtifactData.data.artifact.metadata?.updated}
            </div>
            <div className="artifact-body">
              <ReactMarkdown>{selectedArtifactData.data.artifact.content}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderInitiatives = () => {
    const initiatives: Initiative[] = initiativesData?.data?.initiatives || [];

    if (initiatives.length === 0) {
      return <div className="empty-state">No initiatives yet. Cass will propose them when she needs your input.</div>;
    }

    const pending = initiatives.filter(i => i.status === 'proposed');
    const responded = initiatives.filter(i => i.status !== 'proposed');

    return (
      <div className="initiatives-view">
        {pending.length > 0 && (
          <div className="initiatives-section">
            <h3>Pending</h3>
            {pending.map((init) => (
              <div key={init.id} className={`initiative-card urgency-${init.urgency}`}>
                <div className="initiative-header">
                  <span className="urgency-badge">{init.urgency}</span>
                  <span className="initiative-date">{new Date(init.created_at).toLocaleString()}</span>
                </div>
                <div className="initiative-description">{init.description}</div>
                <div className="initiative-context">Context: {init.goal_context}</div>
                <div className="initiative-actions">
                  <button
                    onClick={() => setInitiativeResponse({ id: init.id, status: 'acknowledged', response: '' })}
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => setInitiativeResponse({ id: init.id, status: 'completed', response: '' })}
                  >
                    Complete
                  </button>
                  <button
                    onClick={() => setInitiativeResponse({ id: init.id, status: 'declined', response: '' })}
                    className="btn-decline"
                  >
                    Decline
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {responded.length > 0 && (
          <div className="initiatives-section">
            <h3>Responded</h3>
            {responded.map((init) => (
              <div key={init.id} className={`initiative-card status-${init.status}`}>
                <div className="initiative-header">
                  <span className={`status-badge status-${init.status}`}>{init.status}</span>
                  <span className="initiative-date">{new Date(init.created_at).toLocaleString()}</span>
                </div>
                <div className="initiative-description">{init.description}</div>
                {init.response && (
                  <div className="initiative-response">Response: {init.response}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderSchedules = () => {
    const schedules: ResearchSchedule[] = schedulesData?.data?.schedules || [];

    if (schedules.length === 0) {
      return <div className="empty-state">No research schedules yet. Cass will request them when she wants recurring research sessions.</div>;
    }

    const pending = schedules.filter(s => s.status === 'pending_approval');
    const active = schedules.filter(s => s.status === 'active');
    const paused = schedules.filter(s => s.status === 'paused');
    const rejected = schedules.filter(s => s.status === 'rejected');

    const formatRecurrence = (recurrence: string) => {
      const map: Record<string, string> = {
        'daily': 'Daily',
        'weekly': 'Weekly',
        'biweekly': 'Every 2 weeks',
        'monthly': 'Monthly',
        'once': 'One-time',
      };
      return map[recurrence] || recurrence;
    };

    const renderScheduleCard = (schedule: ResearchSchedule) => (
      <div key={schedule.schedule_id} className={`schedule-card status-${schedule.status}`}>
        <div className="schedule-header">
          <span className={`status-badge status-${schedule.status}`}>
            {schedule.status.replace('_', ' ')}
          </span>
          <span className="schedule-mode">{schedule.mode}</span>
          <span className="schedule-date">
            {new Date(schedule.created_at).toLocaleDateString()}
          </span>
        </div>
        <div className="schedule-focus">{schedule.focus_description}</div>
        <div className="schedule-meta">
          <span>{formatRecurrence(schedule.recurrence)}</span>
          <span>at {schedule.preferred_time}</span>
          <span>{schedule.duration_minutes} min</span>
          {schedule.run_count > 0 && <span>{schedule.run_count} runs</span>}
        </div>
        {schedule.next_run && (
          <div className="schedule-next">
            Next run: {new Date(schedule.next_run).toLocaleString()}
          </div>
        )}
        {schedule.rejection_reason && (
          <div className="schedule-rejection">
            Rejection reason: {schedule.rejection_reason}
          </div>
        )}
        {schedule.notes && (
          <div className="schedule-notes">Notes: {schedule.notes}</div>
        )}
        <div className="schedule-actions">
          {schedule.status === 'pending_approval' && (
            <>
              <button
                onClick={() => approveScheduleMutation.mutate(schedule.schedule_id)}
                className="btn-approve"
                disabled={approveScheduleMutation.isPending}
              >
                Approve
              </button>
              <button
                onClick={() => setScheduleRejection({ id: schedule.schedule_id, reason: '' })}
                className="btn-reject"
              >
                Reject
              </button>
            </>
          )}
          {schedule.status === 'active' && (
            <button
              onClick={() => pauseScheduleMutation.mutate(schedule.schedule_id)}
              className="btn-pause"
              disabled={pauseScheduleMutation.isPending}
            >
              Pause
            </button>
          )}
          {schedule.status === 'paused' && (
            <button
              onClick={() => resumeScheduleMutation.mutate(schedule.schedule_id)}
              className="btn-resume"
              disabled={resumeScheduleMutation.isPending}
            >
              Resume
            </button>
          )}
        </div>
      </div>
    );

    return (
      <div className="schedules-view">
        {pending.length > 0 && (
          <div className="schedules-section">
            <h3>Pending Approval</h3>
            <div className="schedules-list">
              {pending.map(renderScheduleCard)}
            </div>
          </div>
        )}

        {active.length > 0 && (
          <div className="schedules-section">
            <h3>Active</h3>
            <div className="schedules-list">
              {active.map(renderScheduleCard)}
            </div>
          </div>
        )}

        {paused.length > 0 && (
          <div className="schedules-section">
            <h3>Paused</h3>
            <div className="schedules-list">
              {paused.map(renderScheduleCard)}
            </div>
          </div>
        )}

        {rejected.length > 0 && (
          <div className="schedules-section">
            <h3>Rejected</h3>
            <div className="schedules-list">
              {rejected.map(renderScheduleCard)}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderProgress = () => {
    const entries: ProgressEntry[] = progressData?.data?.entries || [];

    if (entries.length === 0) {
      return <div className="empty-state">No progress entries yet.</div>;
    }

    return (
      <div className="progress-view">
        <div className="progress-list">
          {entries.map((entry) => (
            <div key={entry.id} className={`progress-card type-${entry.type}`}>
              <div className="progress-header">
                <span className={`type-badge type-${entry.type}`}>{entry.type}</span>
                <span className="progress-time">{new Date(entry.timestamp).toLocaleString()}</span>
              </div>
              <div className="progress-description">{entry.description}</div>
              {entry.outcome && (
                <div className="progress-outcome">Outcome: {entry.outcome}</div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="goals-page">
      <nav className="goals-tabs">
        <button
          className={activeTab === 'overview' ? 'active' : ''}
          onClick={() => setActiveTab('overview')}
        >
          Overview
        </button>
        <button
          className={activeTab === 'questions' ? 'active' : ''}
          onClick={() => setActiveTab('questions')}
        >
          Working Questions
        </button>
        <button
          className={activeTab === 'agenda' ? 'active' : ''}
          onClick={() => setActiveTab('agenda')}
        >
          Research Agenda
        </button>
        <button
          className={activeTab === 'schedules' ? 'active' : ''}
          onClick={() => setActiveTab('schedules')}
        >
          Schedules
          {(schedulesData?.data?.schedules?.filter((s: ResearchSchedule) => s.status === 'pending_approval').length ?? 0) > 0 && (
            <span className="badge">
              {schedulesData?.data?.schedules?.filter((s: ResearchSchedule) => s.status === 'pending_approval').length}
            </span>
          )}
        </button>
        <button
          className={activeTab === 'artifacts' ? 'active' : ''}
          onClick={() => setActiveTab('artifacts')}
        >
          Synthesis
        </button>
        <button
          className={activeTab === 'initiatives' ? 'active' : ''}
          onClick={() => setActiveTab('initiatives')}
        >
          Initiatives
          {(initiativesData?.data?.initiatives?.filter((i: Initiative) => i.status === 'proposed').length ?? 0) > 0 && (
            <span className="badge">
              {initiativesData?.data?.initiatives?.filter((i: Initiative) => i.status === 'proposed').length}
            </span>
          )}
        </button>
        <button
          className={activeTab === 'progress' ? 'active' : ''}
          onClick={() => setActiveTab('progress')}
        >
          Progress
        </button>
      </nav>

      <main className="goals-content">
        {activeTab === 'overview' && renderOverview()}
        {activeTab === 'questions' && renderQuestions()}
        {activeTab === 'agenda' && renderAgenda()}
        {activeTab === 'schedules' && renderSchedules()}
        {activeTab === 'artifacts' && renderArtifacts()}
        {activeTab === 'initiatives' && renderInitiatives()}
        {activeTab === 'progress' && renderProgress()}
      </main>

      {/* Initiative Response Modal */}
      {initiativeResponse && (
        <div className="modal-overlay" onClick={() => setInitiativeResponse(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Respond to Initiative</h3>
            <div className="modal-body">
              <label>
                Response:
                <textarea
                  value={initiativeResponse.response}
                  onChange={(e) => setInitiativeResponse({ ...initiativeResponse, response: e.target.value })}
                  placeholder="Optional response message..."
                />
              </label>
            </div>
            <div className="modal-actions">
              <button onClick={() => setInitiativeResponse(null)}>Cancel</button>
              <button
                onClick={() => respondMutation.mutate(initiativeResponse)}
                className="btn-primary"
                disabled={respondMutation.isPending}
              >
                {respondMutation.isPending ? 'Sending...' : `Mark as ${initiativeResponse.status}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Schedule Rejection Modal */}
      {scheduleRejection && (
        <div className="modal-overlay" onClick={() => setScheduleRejection(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Reject Research Schedule</h3>
            <div className="modal-body">
              <label>
                Reason (optional):
                <textarea
                  value={scheduleRejection.reason}
                  onChange={(e) => setScheduleRejection({ ...scheduleRejection, reason: e.target.value })}
                  placeholder="Why are you rejecting this schedule?"
                />
              </label>
            </div>
            <div className="modal-actions">
              <button onClick={() => setScheduleRejection(null)}>Cancel</button>
              <button
                onClick={() => rejectScheduleMutation.mutate({ id: scheduleRejection.id, reason: scheduleRejection.reason })}
                className="btn-reject"
                disabled={rejectScheduleMutation.isPending}
              >
                {rejectScheduleMutation.isPending ? 'Rejecting...' : 'Reject Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
