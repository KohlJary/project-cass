import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { wikiApi, researchApi } from '../api/client';
import './Research.css';

interface ResearchTask {
  task_id: string;
  task_type: string;
  target: string;
  context: string;
  priority: number;
  status: string;
  created_at: string;
  source_page?: string;
  rationale: {
    curiosity_score: number;
    connection_potential: number;
    foundation_relevance: number;
  };
  result?: {
    success: boolean;
    summary?: string;
    pages_created: string[];
    pages_updated: string[];
  };
}

interface QueueStats {
  total: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  queued_count: number;
  in_progress_count: number;
}

interface MaturityStats {
  total_pages: number;
  avg_depth_score: number;
  by_level: Record<string, number>;
  deepening_candidates: number;
}

interface DeepeningCandidate {
  page_name: string;
  trigger: string;
  priority: number;
  reason: string;
  connections_added: number;
  days_since_deepening?: number;
}

interface ProgressReport {
  report_id: string;
  created_at: string;
  session_type: string;
  tasks_completed: number;
  tasks_failed: number;
  pages_created: string[];
  pages_updated: string[];
  key_insights: string[];
}

export function Research() {
  const [activeTab, setActiveTab] = useState<'overview' | 'queue' | 'deepening' | 'history'>('overview');
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [lastReport, setLastReport] = useState<ProgressReport | null>(null);
  const [batchSize, setBatchSize] = useState(3);
  const queryClient = useQueryClient();

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ['research-stats'],
    queryFn: () => researchApi.getStats().then(r => r.data),
    refetchInterval: 10000, // Refresh every 10s
  });

  const { data: queueData } = useQuery({
    queryKey: ['research-queue'],
    queryFn: () => researchApi.getQueue({ limit: 50 }).then(r => r.data),
    refetchInterval: 10000,
  });

  const { data: maturityData } = useQuery({
    queryKey: ['maturity-stats'],
    queryFn: () => wikiApi.getMaturityStats().then(r => r.data),
  });

  const { data: candidatesData } = useQuery({
    queryKey: ['deepening-candidates'],
    queryFn: () => wikiApi.detectDeepeningCandidates(20).then(r => r.data),
  });

  // Mutations
  const refreshMutation = useMutation({
    mutationFn: () => researchApi.refreshQueue(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
    },
  });

  const runSingleMutation = useMutation({
    mutationFn: () => researchApi.runSingle(),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
      if (response.data.report) {
        setLastReport(response.data.report);
      }
    },
  });

  const runBatchMutation = useMutation({
    mutationFn: (maxTasks: number) => researchApi.runBatch(maxTasks),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
      queryClient.invalidateQueries({ queryKey: ['deepening-candidates'] });
      if (response.data.report) {
        setLastReport(response.data.report);
      }
    },
  });

  const removeTaskMutation = useMutation({
    mutationFn: (taskId: string) => researchApi.removeTask(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
    },
  });

  const clearCompletedMutation = useMutation({
    mutationFn: () => researchApi.clearCompleted(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
    },
  });

  const deepenPageMutation = useMutation({
    mutationFn: (name: string) => wikiApi.deepenPage(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['deepening-candidates'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
    },
  });

  const stats: QueueStats = statsData?.queue_stats || { total: 0, by_status: {}, by_type: {}, queued_count: 0, in_progress_count: 0 };
  const tasks: ResearchTask[] = queueData?.tasks || [];
  const maturity: MaturityStats = maturityData || { total_pages: 0, avg_depth_score: 0, by_level: {}, deepening_candidates: 0 };
  const candidates: DeepeningCandidate[] = candidatesData?.candidates || [];

  // Group tasks by date for calendar
  const tasksByDate = useMemo(() => {
    const byDate: Record<string, ResearchTask[]> = {};
    for (const task of tasks) {
      if (task.status === 'completed' && task.result) {
        const date = task.created_at.split('T')[0];
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(task);
      }
    }
    return byDate;
  }, [tasks]);

  // Calendar generation
  const calendarDays = useMemo(() => {
    const [year, month] = selectedMonth.split('-').map(Number);
    const firstDay = new Date(year, month - 1, 1);
    const lastDay = new Date(year, month, 0);
    const days: { date: string; day: number; tasks: ResearchTask[]; isCurrentMonth: boolean }[] = [];

    // Pad start
    const startPad = firstDay.getDay();
    for (let i = startPad - 1; i >= 0; i--) {
      const d = new Date(year, month - 1, -i);
      const dateStr = d.toISOString().split('T')[0];
      days.push({ date: dateStr, day: d.getDate(), tasks: tasksByDate[dateStr] || [], isCurrentMonth: false });
    }

    // Current month
    for (let d = 1; d <= lastDay.getDate(); d++) {
      const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      days.push({ date: dateStr, day: d, tasks: tasksByDate[dateStr] || [], isCurrentMonth: true });
    }

    // Pad end
    const endPad = 42 - days.length;
    for (let i = 1; i <= endPad; i++) {
      const d = new Date(year, month, i);
      const dateStr = d.toISOString().split('T')[0];
      days.push({ date: dateStr, day: d.getDate(), tasks: tasksByDate[dateStr] || [], isCurrentMonth: false });
    }

    return days;
  }, [selectedMonth, tasksByDate]);

  const getTaskTypeColor = (type: string) => {
    switch (type) {
      case 'deepening': return '#a78bfa';
      case 'red_link': return '#f472b6';
      case 'question': return '#34d399';
      case 'exploration': return '#60a5fa';
      default: return '#9ca3af';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#34d399';
      case 'in_progress': return '#fbbf24';
      case 'failed': return '#f87171';
      case 'queued': return '#9ca3af';
      default: return '#9ca3af';
    }
  };

  return (
    <div className="research-page">
      <header className="page-header">
        <h1>Research & Learning</h1>
        <p>Monitor and manage Cass's autonomous research and knowledge deepening</p>
      </header>

      <div className="tabs">
        <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>
          Overview
        </button>
        <button className={activeTab === 'queue' ? 'active' : ''} onClick={() => setActiveTab('queue')}>
          Task Queue ({stats.queued_count})
        </button>
        <button className={activeTab === 'deepening' ? 'active' : ''} onClick={() => setActiveTab('deepening')}>
          Deepening ({candidates.length})
        </button>
        <button className={activeTab === 'history' ? 'active' : ''} onClick={() => setActiveTab('history')}>
          Calendar
        </button>
      </div>

      {activeTab === 'overview' && (
        <div className="overview-tab">
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Queue Status</h3>
              <div className="stat-value">{stats.queued_count}</div>
              <div className="stat-label">Tasks Queued</div>
              <div className="stat-breakdown">
                {Object.entries(stats.by_type).map(([type, count]) => (
                  <span key={type} className="stat-item" style={{ color: getTaskTypeColor(type) }}>
                    {type}: {count}
                  </span>
                ))}
              </div>
            </div>

            <div className="stat-card">
              <h3>Wiki Maturity</h3>
              <div className="stat-value">{maturity.total_pages}</div>
              <div className="stat-label">Total Pages</div>
              <div className="stat-breakdown">
                <span className="stat-item">Avg Depth: {(maturity.avg_depth_score || 0).toFixed(2)}</span>
                <span className="stat-item">Candidates: {candidates.length}</span>
              </div>
            </div>

            <div className="stat-card">
              <h3>Scheduler</h3>
              <div className="stat-value">{statsData?.mode || 'supervised'}</div>
              <div className="stat-label">Mode</div>
              <div className="stat-breakdown">
                <span className="stat-item">In Progress: {stats.in_progress_count}</span>
                <span className="stat-item">Completed: {stats.by_status.completed || 0}</span>
              </div>
            </div>
          </div>

          <div className="controls-section">
            <h3>Scheduler Controls</h3>
            <div className="control-buttons">
              <button
                className="btn btn-secondary"
                onClick={() => refreshMutation.mutate()}
                disabled={refreshMutation.isPending}
              >
                {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Queue'}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => runSingleMutation.mutate()}
                disabled={runSingleMutation.isPending || stats.queued_count === 0}
              >
                {runSingleMutation.isPending ? 'Running...' : 'Run Single Task'}
              </button>
              <div className="batch-control">
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={batchSize}
                  onChange={(e) => setBatchSize(parseInt(e.target.value) || 1)}
                />
                <button
                  className="btn btn-primary"
                  onClick={() => runBatchMutation.mutate(batchSize)}
                  disabled={runBatchMutation.isPending || stats.queued_count === 0}
                >
                  {runBatchMutation.isPending ? 'Running...' : `Run Batch (${batchSize})`}
                </button>
              </div>
              <button
                className="btn btn-secondary"
                onClick={() => clearCompletedMutation.mutate()}
                disabled={!stats.by_status.completed}
              >
                Clear Completed
              </button>
            </div>
          </div>

          {lastReport && (
            <div className="last-report">
              <h3>Last Report</h3>
              <div className="report-summary">
                <span className="report-stat success">
                  Completed: {lastReport.tasks_completed}
                </span>
                {lastReport.tasks_failed > 0 && (
                  <span className="report-stat failed">
                    Failed: {lastReport.tasks_failed}
                  </span>
                )}
                <span className="report-stat">
                  Pages Created: {lastReport.pages_created.length}
                </span>
                <span className="report-stat">
                  Pages Updated: {lastReport.pages_updated.length}
                </span>
              </div>
              {lastReport.key_insights.length > 0 && (
                <div className="insights">
                  <h4>Insights</h4>
                  <ul>
                    {lastReport.key_insights.map((insight, i) => (
                      <li key={i}>{insight}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          <div className="top-priorities">
            <h3>Top Priority Tasks</h3>
            <div className="task-list compact">
              {tasks.slice(0, 5).map((task) => (
                <div key={task.task_id} className="task-item">
                  <span className="task-priority" style={{ color: getTaskTypeColor(task.task_type) }}>
                    {task.priority.toFixed(2)}
                  </span>
                  <span className="task-type">{task.task_type}</span>
                  <span className="task-target">{task.target}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'queue' && (
        <div className="queue-tab">
          <div className="queue-header">
            <h3>Research Queue ({stats.total} tasks)</h3>
            <button
              className="btn btn-secondary"
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending}
            >
              Refresh
            </button>
          </div>

          <div className="task-list">
            {tasks.map((task) => (
              <div key={task.task_id} className={`task-card ${task.status}`}>
                <div className="task-header">
                  <span className="task-priority" style={{ background: getTaskTypeColor(task.task_type) }}>
                    {task.task_type}
                  </span>
                  <span className="task-priority-score">{task.priority.toFixed(2)}</span>
                  <span className="task-status" style={{ color: getStatusColor(task.status) }}>
                    {task.status}
                  </span>
                </div>
                <div className="task-target">{task.target}</div>
                <div className="task-context">{task.context}</div>
                <div className="task-meta">
                  <span>Curiosity: {task.rationale.curiosity_score.toFixed(2)}</span>
                  <span>Connections: {task.rationale.connection_potential.toFixed(2)}</span>
                  <span>Foundation: {task.rationale.foundation_relevance.toFixed(2)}</span>
                </div>
                {task.status === 'queued' && (
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() => removeTaskMutation.mutate(task.task_id)}
                  >
                    Remove
                  </button>
                )}
                {task.result && (
                  <div className="task-result">
                    <span className={task.result.success ? 'success' : 'failed'}>
                      {task.result.success ? 'Success' : 'Failed'}
                    </span>
                    {task.result.summary && <span>{task.result.summary}</span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'deepening' && (
        <div className="deepening-tab">
          <h3>Deepening Candidates</h3>
          <p className="tab-description">
            Pages ready for resynthesis based on PMD triggers (new connections, temporal decay, etc.)
          </p>

          <div className="candidates-list">
            {candidates.map((candidate) => (
              <div key={candidate.page_name} className="candidate-card">
                <div className="candidate-header">
                  <span className="candidate-name">{candidate.page_name}</span>
                  <span className="candidate-priority">{candidate.priority.toFixed(2)}</span>
                </div>
                <div className="candidate-trigger">
                  Trigger: {candidate.trigger.replace('_', ' ')}
                </div>
                <div className="candidate-reason">{candidate.reason}</div>
                <div className="candidate-meta">
                  <span>+{candidate.connections_added} connections</span>
                  {candidate.days_since_deepening !== null && (
                    <span>{candidate.days_since_deepening} days since last</span>
                  )}
                </div>
                <button
                  className="btn btn-primary btn-small"
                  onClick={() => deepenPageMutation.mutate(candidate.page_name)}
                  disabled={deepenPageMutation.isPending}
                >
                  Deepen Now
                </button>
              </div>
            ))}
            {candidates.length === 0 && (
              <div className="empty-state">No pages currently need deepening</div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <div className="history-tab">
          <div className="calendar-header">
            <button onClick={() => {
              const [y, m] = selectedMonth.split('-').map(Number);
              const prev = new Date(y, m - 2, 1);
              setSelectedMonth(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}`);
            }}>
              &larr;
            </button>
            <h3>{new Date(selectedMonth + '-01').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</h3>
            <button onClick={() => {
              const [y, m] = selectedMonth.split('-').map(Number);
              const next = new Date(y, m, 1);
              setSelectedMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`);
            }}>
              &rarr;
            </button>
          </div>

          <div className="calendar-grid">
            <div className="calendar-weekdays">
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                <div key={day} className="weekday">{day}</div>
              ))}
            </div>
            <div className="calendar-days">
              {calendarDays.map((day, i) => (
                <div
                  key={i}
                  className={`calendar-day ${day.isCurrentMonth ? '' : 'other-month'} ${day.tasks.length > 0 ? 'has-tasks' : ''}`}
                >
                  <span className="day-number">{day.day}</span>
                  {day.tasks.length > 0 && (
                    <div className="day-tasks">
                      {day.tasks.slice(0, 3).map((task, j) => (
                        <div
                          key={j}
                          className="day-task-dot"
                          style={{ background: getTaskTypeColor(task.task_type) }}
                          title={`${task.task_type}: ${task.target}`}
                        />
                      ))}
                      {day.tasks.length > 3 && (
                        <span className="more-tasks">+{day.tasks.length - 3}</span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="calendar-legend">
            <span style={{ color: getTaskTypeColor('deepening') }}>Deepening</span>
            <span style={{ color: getTaskTypeColor('red_link') }}>Red Link</span>
            <span style={{ color: getTaskTypeColor('question') }}>Question</span>
            <span style={{ color: getTaskTypeColor('exploration') }}>Exploration</span>
          </div>
        </div>
      )}
    </div>
  );
}
