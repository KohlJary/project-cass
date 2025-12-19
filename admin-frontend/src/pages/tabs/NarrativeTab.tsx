import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { narrativeApi } from '../../api/client';
import type { ThreadResponse, QuestionResponse } from '../../api/client';
import './NarrativeTab.css';

type ThreadType = 'topic' | 'question' | 'project' | 'relational';
type QuestionType = 'curiosity' | 'decision' | 'blocker' | 'philosophical';

const threadTypeConfig: Record<ThreadType, { color: string; icon: string; label: string }> = {
  topic: { color: '#89ddff', icon: 'T', label: 'Topic' },
  question: { color: '#c792ea', icon: '?', label: 'Question' },
  project: { color: '#c3e88d', icon: 'P', label: 'Project' },
  relational: { color: '#f78c6c', icon: 'R', label: 'Relational' },
};

const questionTypeConfig: Record<QuestionType, { color: string; icon: string; label: string }> = {
  curiosity: { color: '#c792ea', icon: '?', label: 'Curiosity' },
  decision: { color: '#ffcb6b', icon: '!', label: 'Decision' },
  blocker: { color: '#ff5370', icon: 'X', label: 'Blocker' },
  philosophical: { color: '#82aaff', icon: '~', label: 'Philosophical' },
};

export function NarrativeTab() {
  const [activeSection, setActiveSection] = useState<'threads' | 'questions'>('threads');
  const [threadFilter, setThreadFilter] = useState<string>('active');
  const [questionFilter, setQuestionFilter] = useState<string>('open');
  const queryClient = useQueryClient();

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['narrative-stats'],
    queryFn: () => narrativeApi.getStats().then((r) => r.data),
    retry: false,
  });

  // Fetch threads
  const { data: threadsData, isLoading: threadsLoading } = useQuery({
    queryKey: ['narrative-threads', threadFilter],
    queryFn: () =>
      narrativeApi.getThreads({ status: threadFilter === 'all' ? undefined : threadFilter, limit: 50 }).then((r) => r.data),
    retry: false,
    enabled: activeSection === 'threads',
  });

  // Fetch questions
  const { data: questionsData, isLoading: questionsLoading } = useQuery({
    queryKey: ['narrative-questions', questionFilter],
    queryFn: () =>
      narrativeApi.getQuestions({ status: questionFilter === 'all' ? undefined : questionFilter, limit: 50 }).then((r) => r.data),
    retry: false,
    enabled: activeSection === 'questions',
  });

  // Mutations
  const resolveThreadMutation = useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution: string }) =>
      narrativeApi.resolveThread(id, resolution),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['narrative-threads'] });
      queryClient.invalidateQueries({ queryKey: ['narrative-stats'] });
    },
  });

  const resolveQuestionMutation = useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution: string }) =>
      narrativeApi.resolveQuestion(id, resolution),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['narrative-questions'] });
      queryClient.invalidateQueries({ queryKey: ['narrative-stats'] });
    },
  });

  // Extraction status polling
  const [isPollingExtraction, setIsPollingExtraction] = useState(false);

  const { data: extractionStatus, refetch: refetchExtractionStatus } = useQuery({
    queryKey: ['narrative-extraction-status'],
    queryFn: () => narrativeApi.getExtractionStatus().then((r) => r.data),
    retry: false,
    refetchInterval: isPollingExtraction ? 1000 : false,
  });

  // Start/stop polling based on extraction status
  useEffect(() => {
    if (extractionStatus?.running) {
      setIsPollingExtraction(true);
    } else if (isPollingExtraction && !extractionStatus?.running) {
      setIsPollingExtraction(false);
      // Refresh data when extraction completes
      queryClient.invalidateQueries({ queryKey: ['narrative-threads'] });
      queryClient.invalidateQueries({ queryKey: ['narrative-questions'] });
      queryClient.invalidateQueries({ queryKey: ['narrative-stats'] });
    }
  }, [extractionStatus?.running, isPollingExtraction, queryClient]);

  const extractMutation = useMutation({
    mutationFn: (source: 'journals' | 'conversations' | 'all') =>
      narrativeApi.extractFromHistory(source),
    onSuccess: () => {
      setIsPollingExtraction(true);
      refetchExtractionStatus();
    },
  });

  return (
    <div className="narrative-tab">
      {/* Stats overview */}
      <div className="narrative-stats">
        <div className="stat-card">
          <div className="stat-value">{stats?.threads.active ?? '-'}</div>
          <div className="stat-label">Active Threads</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.threads.resolved ?? '-'}</div>
          <div className="stat-label">Resolved</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats?.questions.open ?? '-'}</div>
          <div className="stat-label">Open Questions</div>
        </div>
      </div>

      {/* Extraction controls */}
      <div className="extraction-section">
        <div className="extraction-controls">
          <button
            className="action-btn extract-btn"
            onClick={() => extractMutation.mutate('all')}
            disabled={extractionStatus?.running || extractMutation.isPending}
          >
            {extractionStatus?.running ? 'Extracting...' : 'Extract from History'}
          </button>
          {extractionStatus?.running && (
            <span className="extraction-status">Analyzing journals and conversations...</span>
          )}
        </div>
        {extractionStatus?.results && !extractionStatus.running && (
          <div className={`extraction-results ${extractionStatus.results.error ? 'error' : 'success'}`}>
            {extractionStatus.results.error ? (
              <span>Error: {extractionStatus.results.error}</span>
            ) : (
              <span>
                Created {extractionStatus.results.threads_created} threads and{' '}
                {extractionStatus.results.questions_created} questions from{' '}
                {extractionStatus.results.chunks_analyzed} entries
              </span>
            )}
          </div>
        )}
      </div>

      {/* Section toggle */}
      <div className="section-toggle">
        <button
          className={`toggle-btn ${activeSection === 'threads' ? 'active' : ''}`}
          onClick={() => setActiveSection('threads')}
        >
          Threads ({threadsData?.count ?? 0})
        </button>
        <button
          className={`toggle-btn ${activeSection === 'questions' ? 'active' : ''}`}
          onClick={() => setActiveSection('questions')}
        >
          Questions ({questionsData?.count ?? 0})
        </button>
      </div>

      {/* Threads section */}
      {activeSection === 'threads' && (
        <div className="threads-section">
          <div className="filter-row">
            <select
              value={threadFilter}
              onChange={(e) => setThreadFilter(e.target.value)}
              className="filter-select"
            >
              <option value="active">Active</option>
              <option value="resolved">Resolved</option>
              <option value="dormant">Dormant</option>
              <option value="all">All</option>
            </select>
          </div>

          {threadsLoading ? (
            <div className="loading">Loading threads...</div>
          ) : threadsData?.threads.length === 0 ? (
            <div className="empty-state">
              No threads found. Threads will be created as Cass tracks ongoing topics in conversations.
            </div>
          ) : (
            <div className="items-list">
              {threadsData?.threads.map((thread) => (
                <ThreadCard
                  key={thread.id}
                  thread={thread}
                  onResolve={(resolution) =>
                    resolveThreadMutation.mutate({ id: thread.id, resolution })
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Questions section */}
      {activeSection === 'questions' && (
        <div className="questions-section">
          <div className="filter-row">
            <select
              value={questionFilter}
              onChange={(e) => setQuestionFilter(e.target.value)}
              className="filter-select"
            >
              <option value="open">Open</option>
              <option value="resolved">Resolved</option>
              <option value="all">All</option>
            </select>
          </div>

          {questionsLoading ? (
            <div className="loading">Loading questions...</div>
          ) : questionsData?.questions.length === 0 ? (
            <div className="empty-state">
              No open questions. Questions will appear as Cass tracks unresolved curiosities.
            </div>
          ) : (
            <div className="items-list">
              {questionsData?.questions.map((question) => (
                <QuestionCard
                  key={question.id}
                  question={question}
                  onResolve={(resolution) =>
                    resolveQuestionMutation.mutate({ id: question.id, resolution })
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ThreadCard({
  thread,
  onResolve,
}: {
  thread: ThreadResponse;
  onResolve: (resolution: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolution, setResolution] = useState('');

  const config = threadTypeConfig[thread.thread_type as ThreadType] || threadTypeConfig.topic;
  const isActive = thread.status === 'active';

  const handleResolve = () => {
    if (resolution.trim()) {
      onResolve(resolution);
      setResolving(false);
      setResolution('');
    }
  };

  return (
    <div className={`narrative-card thread-card ${expanded ? 'expanded' : ''} status-${thread.status}`}>
      <div className="card-header" onClick={() => setExpanded(!expanded)}>
        <div
          className="type-badge"
          style={{ backgroundColor: config.color + '20', color: config.color }}
        >
          <span className="type-icon">{config.icon}</span>
          <span className="type-label">{config.label}</span>
        </div>

        <div className="card-title">{thread.title}</div>

        <div className="card-meta">
          <span className={`status-badge status-${thread.status}`}>{thread.status}</span>
          <span className="importance" title="Importance">
            {(thread.importance * 100).toFixed(0)}%
          </span>
        </div>

        <span className="expand-icon">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="card-content">
          {thread.description && <p className="description">{thread.description}</p>}

          <div className="card-details">
            <div className="detail-row">
              <span className="detail-label">Created:</span>
              <span className="detail-value">
                {new Date(thread.created_at).toLocaleDateString()}
              </span>
            </div>
            {thread.last_touched && (
              <div className="detail-row">
                <span className="detail-label">Last touched:</span>
                <span className="detail-value">
                  {new Date(thread.last_touched).toLocaleDateString()}
                </span>
              </div>
            )}
            {thread.resolution_summary && (
              <div className="detail-row">
                <span className="detail-label">Resolution:</span>
                <span className="detail-value">{thread.resolution_summary}</span>
              </div>
            )}
          </div>

          {isActive && !resolving && (
            <button className="action-btn resolve-btn" onClick={() => setResolving(true)}>
              Resolve Thread
            </button>
          )}

          {resolving && (
            <div className="resolve-form">
              <textarea
                placeholder="How was this thread resolved?"
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
              <div className="resolve-actions">
                <button className="action-btn" onClick={handleResolve}>
                  Resolve
                </button>
                <button className="action-btn cancel-btn" onClick={() => setResolving(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function QuestionCard({
  question,
  onResolve,
}: {
  question: QuestionResponse;
  onResolve: (resolution: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolution, setResolution] = useState('');

  const config = questionTypeConfig[question.question_type as QuestionType] || questionTypeConfig.curiosity;
  const isOpen = question.status === 'open';

  const handleResolve = () => {
    if (resolution.trim()) {
      onResolve(resolution);
      setResolving(false);
      setResolution('');
    }
  };

  return (
    <div className={`narrative-card question-card ${expanded ? 'expanded' : ''} status-${question.status}`}>
      <div className="card-header" onClick={() => setExpanded(!expanded)}>
        <div
          className="type-badge"
          style={{ backgroundColor: config.color + '20', color: config.color }}
        >
          <span className="type-icon">{config.icon}</span>
          <span className="type-label">{config.label}</span>
        </div>

        <div className="card-title">{question.question}</div>

        <div className="card-meta">
          <span className={`status-badge status-${question.status}`}>{question.status}</span>
        </div>

        <span className="expand-icon">{expanded ? '-' : '+'}</span>
      </div>

      {expanded && (
        <div className="card-content">
          {question.context && <p className="context">Context: {question.context}</p>}

          <div className="card-details">
            <div className="detail-row">
              <span className="detail-label">Created:</span>
              <span className="detail-value">
                {new Date(question.created_at).toLocaleDateString()}
              </span>
            </div>
            {question.resolved_at && (
              <div className="detail-row">
                <span className="detail-label">Resolved:</span>
                <span className="detail-value">
                  {new Date(question.resolved_at).toLocaleDateString()}
                </span>
              </div>
            )}
            {question.resolution && (
              <div className="detail-row">
                <span className="detail-label">Resolution:</span>
                <span className="detail-value">{question.resolution}</span>
              </div>
            )}
          </div>

          {isOpen && !resolving && (
            <button className="action-btn resolve-btn" onClick={() => setResolving(true)}>
              Resolve Question
            </button>
          )}

          {resolving && (
            <div className="resolve-form">
              <textarea
                placeholder="How was this question answered?"
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              />
              <div className="resolve-actions">
                <button className="action-btn" onClick={handleResolve}>
                  Resolve
                </button>
                <button className="action-btn cancel-btn" onClick={() => setResolving(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
