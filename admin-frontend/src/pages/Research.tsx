import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { wikiApi, researchApi } from '../api/client';
import './Research.css';

interface ExplorationContext {
  question: string;
  rationale: string;
  related_red_links: string[];
  source_pages: string[];
  domain_tags: string[];
  synthesis?: string;
  synthesis_page?: string;
  follow_up_questions: string[];
}

interface ResearchTask {
  task_id: string;
  task_type: string;
  target: string;
  context: string;
  priority: number;
  status: string;
  created_at: string;
  completed_at?: string;
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
  exploration?: ExplorationContext;
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
  graph_stats?: GraphStats;
}

interface GraphStats {
  node_count: number;
  edge_count: number;
  avg_connectivity: number;
  most_connected: { page: string; connections: number }[];
  orphan_count: number;
  sparse_count: number;
}

interface WeeklySummary {
  report: ProgressReport;
  markdown: string;
}

interface SchedulerConfig {
  mode: string;
  max_tasks_per_cycle: number;
  auto_queue_red_links: boolean;
  auto_queue_deepening: boolean;
  curiosity_threshold: number;
  available_modes: string[];
}

interface ResearchProposal {
  proposal_id: string;
  title: string;
  theme: string;
  rationale: string;
  tasks: ResearchTask[];
  status: string;
  created_at: string;
  approved_at?: string;
  completed_at?: string;
  execution_started_at?: string;
  tasks_completed: number;
  tasks_total: number;
  summary?: string;
  rejection_reason?: string;
}

export function Research() {
  const [activeTab, setActiveTab] = useState<'overview' | 'queue' | 'deepening' | 'history' | 'summary' | 'proposals'>('overview');
  const [proposalTheme, setProposalTheme] = useState('');
  const [selectedProposal, setSelectedProposal] = useState<ResearchProposal | null>(null);
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  });
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [lastReport, setLastReport] = useState<ProgressReport | null>(null);
  const [batchSize, setBatchSize] = useState(3);
  const [summaryDays, setSummaryDays] = useState(7);
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

  // Fetch exploration tasks separately (they may be lower priority than top 50)
  const { data: explorationData } = useQuery({
    queryKey: ['exploration-tasks'],
    queryFn: () => researchApi.getQueue({ task_type: 'exploration', limit: 50 }).then(r => r.data),
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

  // Parse year/month for history query
  const [historyYear, historyMonth] = useMemo(() => {
    const [y, m] = selectedMonth.split('-').map(Number);
    return [y, m];
  }, [selectedMonth]);

  const { data: historyData } = useQuery({
    queryKey: ['research-history', historyYear, historyMonth],
    queryFn: () => researchApi.getHistory({ year: historyYear, month: historyMonth, limit: 200 }).then(r => r.data),
    enabled: activeTab === 'history', // Only fetch when calendar tab is active
  });

  const { data: graphStatsData } = useQuery({
    queryKey: ['graph-stats'],
    queryFn: () => researchApi.getGraphStats().then(r => r.data),
    refetchInterval: 30000, // Refresh every 30s
  });

  const { data: weeklySummaryData } = useQuery({
    queryKey: ['weekly-summary', summaryDays],
    queryFn: () => researchApi.getWeeklySummary(summaryDays).then(r => r.data),
    enabled: activeTab === 'summary',
  });

  // Config and proposals queries
  const { data: configData } = useQuery<SchedulerConfig>({
    queryKey: ['research-config'],
    queryFn: () => researchApi.getConfig().then(r => r.data),
  });

  const { data: proposalsData } = useQuery({
    queryKey: ['research-proposals'],
    queryFn: () => researchApi.listProposals().then(r => r.data),
    enabled: activeTab === 'proposals' || activeTab === 'overview',
  });

  // Mutations
  const refreshMutation = useMutation({
    mutationFn: () => researchApi.refreshQueue(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
    },
  });

  const runSingleMutation = useMutation({
    mutationFn: () => researchApi.runSingle(),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
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
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
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
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
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

  const explorationMutation = useMutation({
    mutationFn: (maxTasks: number) => researchApi.generateExploration(maxTasks),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
    },
  });

  const runTaskMutation = useMutation({
    mutationFn: (taskId: string) => researchApi.runTask(taskId),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
      if (response.data.report) {
        setLastReport(response.data.report);
      }
    },
  });

  const runByTypeMutation = useMutation({
    mutationFn: ({ taskType, maxTasks }: { taskType: string; maxTasks: number }) =>
      researchApi.runByType(taskType, maxTasks),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
      queryClient.invalidateQueries({ queryKey: ['maturity-stats'] });
      queryClient.invalidateQueries({ queryKey: ['exploration-tasks'] });
      if (response.data.report) {
        setLastReport(response.data.report);
      }
    },
  });

  // Mode and proposal mutations
  const setModeMutation = useMutation({
    mutationFn: (mode: string) => researchApi.setMode(mode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-config'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
    },
  });

  const generateProposalMutation = useMutation({
    mutationFn: (params: { theme?: string; max_tasks?: number }) => researchApi.generateProposal(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] });
      setProposalTheme('');
    },
  });

  const approveProposalMutation = useMutation({
    mutationFn: (id: string) => researchApi.approveProposal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] });
    },
  });

  const rejectProposalMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => researchApi.rejectProposal(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] });
    },
  });

  const executeProposalMutation = useMutation({
    mutationFn: (id: string) => researchApi.executeProposal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] });
      queryClient.invalidateQueries({ queryKey: ['research-queue'] });
      queryClient.invalidateQueries({ queryKey: ['research-stats'] });
    },
  });

  const deleteProposalMutation = useMutation({
    mutationFn: (id: string) => researchApi.deleteProposal(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] });
      setSelectedProposal(null);
    },
  });

  const stats: QueueStats = statsData?.queue_stats || { total: 0, by_status: {}, by_type: {}, queued_count: 0, in_progress_count: 0 };
  const tasks: ResearchTask[] = queueData?.tasks || [];
  const maturity: MaturityStats = maturityData || { total_pages: 0, avg_depth_score: 0, by_level: {}, deepening_candidates: 0 };
  const candidates: DeepeningCandidate[] = candidatesData?.candidates || [];
  const historyTasks: ResearchTask[] = historyData?.history || [];
  const graphStats: GraphStats | null = graphStatsData || null;
  const weeklySummary: WeeklySummary | null = weeklySummaryData || null;
  const proposals: ResearchProposal[] = proposalsData?.proposals || [];
  const pendingProposals = proposals.filter(p => p.status === 'pending');
  const config = configData || { mode: 'supervised', available_modes: ['supervised', 'batched', 'continuous', 'triggered'] };

  // Get exploration tasks from dedicated query
  // Separate new-style (with exploration context) from old-style (just a target)
  const { newExplorationTasks, oldExplorationTasks } = useMemo(() => {
    const allExploration = (explorationData?.tasks || []).filter((t: ResearchTask) => t.status === 'queued');
    return {
      newExplorationTasks: allExploration.filter((t: ResearchTask) => t.exploration?.question),
      oldExplorationTasks: allExploration.filter((t: ResearchTask) => !t.exploration?.question),
    };
  }, [explorationData]);

  // Group history tasks by date for calendar (uses completed_at)
  const tasksByDate = useMemo(() => {
    const byDate: Record<string, ResearchTask[]> = {};
    for (const task of historyTasks) {
      const completedAt = task.completed_at || task.created_at;
      if (completedAt) {
        const date = completedAt.split('T')[0];
        if (!byDate[date]) byDate[date] = [];
        byDate[date].push(task);
      }
    }
    return byDate;
  }, [historyTasks]);

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
        <button className={activeTab === 'proposals' ? 'active' : ''} onClick={() => setActiveTab('proposals')}>
          Proposals {pendingProposals.length > 0 && <span className="badge">{pendingProposals.length}</span>}
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
        <button className={activeTab === 'summary' ? 'active' : ''} onClick={() => setActiveTab('summary')}>
          Summary
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

            <div className="stat-card scheduler-card">
              <h3>Scheduler</h3>
              <div className="mode-selector">
                <select
                  value={config.mode}
                  onChange={(e) => setModeMutation.mutate(e.target.value)}
                  disabled={setModeMutation.isPending}
                >
                  {(config.available_modes || ['supervised', 'batched', 'continuous', 'triggered']).map((mode: string) => (
                    <option key={mode} value={mode}>{mode}</option>
                  ))}
                </select>
              </div>
              <div className="stat-breakdown">
                <span className="stat-item">In Progress: {stats.in_progress_count}</span>
                <span className="stat-item">Completed: {stats.by_status.completed || 0}</span>
              </div>
              <div className="mode-description">
                {config.mode === 'supervised' && 'Manual approval required for all tasks'}
                {config.mode === 'batched' && 'Runs tasks in scheduled batches'}
                {config.mode === 'continuous' && 'Automatically runs queued tasks'}
                {config.mode === 'triggered' && 'Runs when triggered by events'}
              </div>
            </div>

            {graphStats && (
              <div className="stat-card graph-stats">
                <h3>Knowledge Graph</h3>
                <div className="stat-value">{graphStats.node_count}</div>
                <div className="stat-label">Nodes</div>
                <div className="stat-breakdown">
                  <span className="stat-item">{graphStats.edge_count} edges</span>
                  <span className="stat-item">Avg: {graphStats.avg_connectivity}</span>
                  <span className="stat-item">{graphStats.orphan_count} orphans</span>
                </div>
                {graphStats.most_connected.length > 0 && (
                  <div className="most-connected">
                    <span className="label">Most connected:</span>
                    <span className="value">{graphStats.most_connected[0].page} ({graphStats.most_connected[0].connections})</span>
                  </div>
                )}
              </div>
            )}
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
              <button
                className="btn btn-secondary explore-btn"
                onClick={() => explorationMutation.mutate(5)}
                disabled={explorationMutation.isPending}
              >
                {explorationMutation.isPending ? 'Finding...' : 'Find Exploration Tasks'}
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

          {newExplorationTasks.length > 0 && (
            <div className="exploration-tasks">
              <div className="exploration-header-bar">
                <div>
                  <h3>🔍 Research Questions ({newExplorationTasks.length})</h3>
                  <p className="section-description">Curiosity-driven research questions that explore gaps in the knowledge graph</p>
                </div>
                <button
                  className="btn btn-primary"
                  onClick={() => runByTypeMutation.mutate({ taskType: 'exploration', maxTasks: 1 })}
                  disabled={runByTypeMutation.isPending || newExplorationTasks.length === 0}
                >
                  {runByTypeMutation.isPending ? 'Running...' : 'Run Next'}
                </button>
              </div>
              <div className="exploration-list">
                {newExplorationTasks.map((task: ResearchTask) => (
                  <div key={task.task_id} className="exploration-item">
                    <div className="exploration-header">
                      <span className="exploration-question">
                        {task.exploration?.question || task.target}
                      </span>
                      <span className="exploration-priority">P{task.priority.toFixed(2)}</span>
                    </div>
                    {task.exploration && (
                      <>
                        <div className="exploration-rationale">
                          {task.exploration.rationale}
                        </div>
                        {task.exploration.related_red_links.length > 0 && (
                          <div className="exploration-red-links">
                            <span className="label">Red links to investigate:</span>
                            <div className="red-link-tags">
                              {task.exploration.related_red_links.map((link: string) => (
                                <span key={link} className="red-link-tag">{link}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {task.exploration.source_pages.length > 0 && (
                          <div className="exploration-sources">
                            <span className="label">From:</span>
                            {task.exploration.source_pages.join(', ')}
                          </div>
                        )}
                      </>
                    )}
                    <div className="exploration-actions">
                      <button
                        className="btn btn-small btn-primary"
                        onClick={() => runTaskMutation.mutate(task.task_id)}
                        disabled={runTaskMutation.isPending}
                      >
                        {runTaskMutation.isPending ? '...' : 'Run'}
                      </button>
                      <button
                        className="btn btn-small btn-secondary"
                        onClick={() => removeTaskMutation.mutate(task.task_id)}
                        disabled={removeTaskMutation.isPending}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {oldExplorationTasks.length > 0 && (
            <div className="exploration-tasks legacy">
              <h3>📦 Legacy Exploration Tasks ({oldExplorationTasks.length})</h3>
              <p className="section-description">Old-style concept explorations (will be replaced when you click "Find Exploration Tasks")</p>
              <div className="legacy-exploration-list">
                {oldExplorationTasks.slice(0, 10).map((task: ResearchTask) => (
                  <span key={task.task_id} className="legacy-tag">
                    {task.target}
                    <button
                      className="remove-btn"
                      onClick={() => removeTaskMutation.mutate(task.task_id)}
                      disabled={removeTaskMutation.isPending}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {oldExplorationTasks.length > 10 && (
                  <span className="more-count">+{oldExplorationTasks.length - 10} more</span>
                )}
              </div>
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
          <div className="calendar-layout">
            <div className="calendar-section">
              <div className="calendar-header">
                <button onClick={() => {
                  const [y, m] = selectedMonth.split('-').map(Number);
                  const prev = new Date(y, m - 2, 1);
                  setSelectedMonth(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, '0')}`);
                  setSelectedDate(null);
                }}>
                  &larr;
                </button>
                <h3>{new Date(selectedMonth + '-01').toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</h3>
                <button onClick={() => {
                  const [y, m] = selectedMonth.split('-').map(Number);
                  const next = new Date(y, m, 1);
                  setSelectedMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`);
                  setSelectedDate(null);
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
                      className={`calendar-day ${day.isCurrentMonth ? '' : 'other-month'} ${day.tasks.length > 0 ? 'has-tasks' : ''} ${selectedDate === day.date ? 'selected' : ''}`}
                      onClick={() => day.tasks.length > 0 && setSelectedDate(day.date)}
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

            <div className="day-detail-panel">
              {selectedDate && tasksByDate[selectedDate] ? (
                <>
                  <h3>
                    {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-US', {
                      weekday: 'long',
                      month: 'long',
                      day: 'numeric'
                    })}
                  </h3>
                  <div className="day-detail-summary">
                    {tasksByDate[selectedDate].length} task{tasksByDate[selectedDate].length !== 1 ? 's' : ''} completed
                  </div>
                  <div className="day-detail-tasks">
                    {tasksByDate[selectedDate].map((task, i) => (
                      <div key={i} className="day-detail-task">
                        <div className="detail-task-header">
                          <span
                            className="detail-task-type"
                            style={{ background: getTaskTypeColor(task.task_type) }}
                          >
                            {task.task_type.replace('_', ' ')}
                          </span>
                          <span className={`detail-task-status ${task.status}`}>
                            {task.status}
                          </span>
                        </div>
                        <div className="detail-task-target">{task.target}</div>
                        {task.context && (
                          <div className="detail-task-context">{task.context}</div>
                        )}
                        {task.result && (
                          <div className="detail-task-result">
                            {task.result.pages_created?.length > 0 && (
                              <span className="result-item created">
                                +{task.result.pages_created.length} page{task.result.pages_created.length !== 1 ? 's' : ''}
                              </span>
                            )}
                            {task.result.pages_updated?.length > 0 && (
                              <span className="result-item updated">
                                ~{task.result.pages_updated.length} updated
                              </span>
                            )}
                            {task.result.summary && (
                              <div className="result-summary">{task.result.summary}</div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="day-detail-empty">
                  <p>Select a day with tasks to see details</p>
                  <p className="hint">Days with colored dots have completed research tasks</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'summary' && (
        <div className="summary-tab">
          <div className="summary-header">
            <h3>Research Summary</h3>
            <div className="summary-controls">
              <label>
                Period:
                <select value={summaryDays} onChange={(e) => setSummaryDays(parseInt(e.target.value))}>
                  <option value={7}>Last 7 days</option>
                  <option value={14}>Last 14 days</option>
                  <option value={30}>Last 30 days</option>
                </select>
              </label>
            </div>
          </div>

          {weeklySummary ? (
            <div className="summary-content">
              <div className="summary-stats">
                <div className="summary-stat">
                  <span className="stat-number">{weeklySummary.report.tasks_completed}</span>
                  <span className="stat-label">Tasks Completed</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-number">{weeklySummary.report.pages_created.length}</span>
                  <span className="stat-label">Pages Created</span>
                </div>
                <div className="summary-stat">
                  <span className="stat-number">{weeklySummary.report.pages_updated.length}</span>
                  <span className="stat-label">Pages Deepened</span>
                </div>
                {weeklySummary.report.tasks_failed > 0 && (
                  <div className="summary-stat failed">
                    <span className="stat-number">{weeklySummary.report.tasks_failed}</span>
                    <span className="stat-label">Failed</span>
                  </div>
                )}
              </div>

              {weeklySummary.report.graph_stats && (
                <div className="summary-graph">
                  <h4>Knowledge Graph</h4>
                  <div className="graph-metrics">
                    <div className="metric">
                      <span className="value">{weeklySummary.report.graph_stats.node_count}</span>
                      <span className="label">Pages</span>
                    </div>
                    <div className="metric">
                      <span className="value">{weeklySummary.report.graph_stats.edge_count}</span>
                      <span className="label">Connections</span>
                    </div>
                    <div className="metric">
                      <span className="value">{weeklySummary.report.graph_stats.avg_connectivity}</span>
                      <span className="label">Avg Links/Page</span>
                    </div>
                  </div>
                  {weeklySummary.report.graph_stats.most_connected.length > 0 && (
                    <div className="most-connected-list">
                      <h5>Most Connected Pages</h5>
                      {weeklySummary.report.graph_stats.most_connected.slice(0, 5).map((item, i) => (
                        <div key={i} className="connected-item">
                          <span className="rank">#{i + 1}</span>
                          <span className="page-name">{item.page}</span>
                          <span className="connection-count">{item.connections} links</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {weeklySummary.report.pages_created.length > 0 && (
                <div className="summary-section">
                  <h4>New Pages</h4>
                  <div className="page-list">
                    {weeklySummary.report.pages_created.map((page, i) => (
                      <span key={i} className="page-tag">{page}</span>
                    ))}
                  </div>
                </div>
              )}

              {weeklySummary.report.pages_updated.length > 0 && (
                <div className="summary-section">
                  <h4>Pages Deepened</h4>
                  <div className="page-list">
                    {weeklySummary.report.pages_updated.map((page, i) => (
                      <span key={i} className="page-tag deepened">{page}</span>
                    ))}
                  </div>
                </div>
              )}

              {weeklySummary.report.key_insights.length > 0 && (
                <div className="summary-section">
                  <h4>Key Insights</h4>
                  <ul className="insights-list">
                    {weeklySummary.report.key_insights.slice(0, 10).map((insight, i) => (
                      <li key={i}>{insight}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">
              Loading summary...
            </div>
          )}
        </div>
      )}

      {activeTab === 'proposals' && (
        <div className="proposals-tab">
          <div className="proposals-header">
            <h3>Research Proposals</h3>
            <p className="tab-description">
              Cass can formulate research proposals with sets of exploration tasks. Review and approve proposals to queue them for automated execution.
            </p>
          </div>

          <div className="proposal-generator">
            <h4>Generate New Proposal</h4>
            <div className="generator-form">
              <input
                type="text"
                placeholder="Optional theme (e.g., 'consciousness', 'ethics')..."
                value={proposalTheme}
                onChange={(e) => setProposalTheme(e.target.value)}
              />
              <button
                className="btn btn-primary"
                onClick={() => generateProposalMutation.mutate({ theme: proposalTheme || undefined, max_tasks: 5 })}
                disabled={generateProposalMutation.isPending}
              >
                {generateProposalMutation.isPending ? 'Generating...' : 'Generate Proposal'}
              </button>
            </div>
          </div>

          <div className="proposals-layout">
            <div className="proposals-list">
              <h4>All Proposals ({proposals.length})</h4>
              {proposals.length === 0 ? (
                <div className="empty-state">No proposals yet. Generate one to get started.</div>
              ) : (
                proposals.map((proposal) => (
                  <div
                    key={proposal.proposal_id}
                    className={`proposal-item ${proposal.status} ${selectedProposal?.proposal_id === proposal.proposal_id ? 'selected' : ''}`}
                    onClick={() => setSelectedProposal(proposal)}
                  >
                    <div className="proposal-item-header">
                      <span className="proposal-title">{proposal.title}</span>
                      <span className={`proposal-status ${proposal.status}`}>{proposal.status}</span>
                    </div>
                    <div className="proposal-theme">{proposal.theme}</div>
                    <div className="proposal-meta">
                      <span>{proposal.tasks.length} tasks</span>
                      <span>{new Date(proposal.created_at).toLocaleDateString()}</span>
                    </div>
                    {proposal.status === 'in_progress' && (
                      <div className="proposal-progress">
                        <div className="progress-bar">
                          <div
                            className="progress-fill"
                            style={{ width: `${(proposal.tasks_completed / proposal.tasks_total) * 100}%` }}
                          />
                        </div>
                        <span className="progress-text">{proposal.tasks_completed}/{proposal.tasks_total}</span>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <div className="proposal-detail">
              {selectedProposal ? (
                <>
                  <div className="proposal-detail-header">
                    <h4>{selectedProposal.title}</h4>
                    <span className={`proposal-status ${selectedProposal.status}`}>{selectedProposal.status}</span>
                  </div>
                  <div className="proposal-theme-detail">{selectedProposal.theme}</div>
                  <div className="proposal-rationale">
                    <h5>Rationale</h5>
                    <p>{selectedProposal.rationale}</p>
                  </div>

                  <div className="proposal-tasks">
                    <h5>Research Tasks ({selectedProposal.tasks.length})</h5>
                    <div className="task-list compact">
                      {selectedProposal.tasks.map((task) => (
                        <div key={task.task_id} className="task-item">
                          <span className="task-type" style={{ color: getTaskTypeColor(task.task_type) }}>
                            {task.task_type}
                          </span>
                          <span className="task-target">{task.target}</span>
                          {task.context && <span className="task-context">{task.context}</span>}
                        </div>
                      ))}
                    </div>
                  </div>

                  {selectedProposal.summary && (
                    <div className="proposal-summary">
                      <h5>Summary of Findings</h5>
                      <div className="summary-content markdown">{selectedProposal.summary}</div>
                    </div>
                  )}

                  <div className="proposal-actions">
                    {selectedProposal.status === 'pending' && (
                      <>
                        <button
                          className="btn btn-primary"
                          onClick={() => approveProposalMutation.mutate(selectedProposal.proposal_id)}
                          disabled={approveProposalMutation.isPending}
                        >
                          {approveProposalMutation.isPending ? 'Approving...' : 'Approve'}
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={() => rejectProposalMutation.mutate({ id: selectedProposal.proposal_id })}
                          disabled={rejectProposalMutation.isPending}
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {selectedProposal.status === 'approved' && (
                      <button
                        className="btn btn-primary"
                        onClick={() => executeProposalMutation.mutate(selectedProposal.proposal_id)}
                        disabled={executeProposalMutation.isPending}
                      >
                        {executeProposalMutation.isPending ? 'Executing...' : 'Execute Proposal'}
                      </button>
                    )}
                    {(selectedProposal.status === 'completed' || selectedProposal.status === 'rejected') && (
                      <button
                        className="btn btn-danger"
                        onClick={() => deleteProposalMutation.mutate(selectedProposal.proposal_id)}
                        disabled={deleteProposalMutation.isPending}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <div className="empty-state">
                  Select a proposal to view details
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
