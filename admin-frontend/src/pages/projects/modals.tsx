// Modal components for Projects page
import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { projectsApi, roadmapApi } from '../../api/client';
import type { Milestone } from './types';

// ---------------------------------------------------------------------------
// New Project Modal
// ---------------------------------------------------------------------------

export function NewProjectModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (projectId: string) => void;
}) {
  const [name, setName] = useState('');
  const [workingDirectory, setWorkingDirectory] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const firstInput = modalRef.current?.querySelector('input');
    firstInput?.focus();

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const createMutation = useMutation({
    mutationFn: () =>
      projectsApi.create({ name, working_directory: workingDirectory, description }),
    onSuccess: (response) => {
      onCreated(response.data.project?.id || response.data.id);
    },
    onError: () => setError('Failed to create project'),
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3>New Project</h3>
        {error && <div className="modal-error">{error}</div>}
        <div className="form-group">
          <label>Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My Project"
            autoFocus
          />
        </div>
        <div className="form-group">
          <label>Working Directory</label>
          <input
            type="text"
            value={workingDirectory}
            onChange={(e) => setWorkingDirectory(e.target.value)}
            placeholder="/path/to/project"
          />
        </div>
        <div className="form-group">
          <label>Description (optional)</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Project description..."
            rows={3}
          />
        </div>
        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="save-btn"
            onClick={() => createMutation.mutate()}
            disabled={!name || !workingDirectory || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating...' : 'Create Project'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New Document Modal
// ---------------------------------------------------------------------------

export function NewDocumentModal({
  projectId,
  onClose,
  onCreated,
}: {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [docType, setDocType] = useState('note');
  const [error, setError] = useState('');
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const firstInput = modalRef.current?.querySelector('input');
    firstInput?.focus();

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const createMutation = useMutation({
    mutationFn: () =>
      projectsApi.createDocument(projectId, { title, content, doc_type: docType }),
    onSuccess: () => onCreated(),
    onError: () => setError('Failed to create document'),
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3>New Document</h3>
        {error && <div className="modal-error">{error}</div>}
        <div className="form-group">
          <label>Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Document title"
            autoFocus
          />
        </div>
        <div className="form-group">
          <label>Type</label>
          <select value={docType} onChange={(e) => setDocType(e.target.value)}>
            <option value="note">Note</option>
            <option value="spec">Specification</option>
            <option value="architecture">Architecture</option>
            <option value="todo">Todo</option>
            <option value="reference">Reference</option>
          </select>
        </div>
        <div className="form-group">
          <label>Content</label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Document content..."
            rows={8}
          />
        </div>
        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="save-btn"
            onClick={() => createMutation.mutate()}
            disabled={!title || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating...' : 'Create Document'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New Roadmap Item Modal
// ---------------------------------------------------------------------------

export function NewRoadmapItemModal({
  projectId,
  milestones,
  onClose,
  onCreated,
}: {
  projectId: string;
  milestones: Milestone[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('P2');
  const [itemType, setItemType] = useState('feature');
  const [milestoneId, setMilestoneId] = useState('');
  const [error, setError] = useState('');
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const firstInput = modalRef.current?.querySelector('input');
    firstInput?.focus();

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const createMutation = useMutation({
    mutationFn: () =>
      roadmapApi.createItem({
        title,
        description,
        priority,
        item_type: itemType,
        status: 'backlog',
        project_id: projectId,
        milestone_id: milestoneId || undefined,
        created_by: 'daedalus',
      }),
    onSuccess: () => onCreated(),
    onError: () => setError('Failed to create item'),
  });

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-content"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3>New Roadmap Item</h3>
        {error && <div className="modal-error">{error}</div>}
        <div className="form-group">
          <label>Title</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Item title"
            autoFocus
          />
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>Priority</label>
            <select value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="P0">P0 - Critical</option>
              <option value="P1">P1 - High</option>
              <option value="P2">P2 - Medium</option>
              <option value="P3">P3 - Low</option>
            </select>
          </div>
          <div className="form-group">
            <label>Type</label>
            <select value={itemType} onChange={(e) => setItemType(e.target.value)}>
              <option value="feature">Feature</option>
              <option value="bug">Bug</option>
              <option value="research">Research</option>
              <option value="chore">Chore</option>
              <option value="enhancement">Enhancement</option>
            </select>
          </div>
        </div>
        <div className="form-group">
          <label>Milestone (optional)</label>
          <select value={milestoneId} onChange={(e) => setMilestoneId(e.target.value)}>
            <option value="">No milestone</option>
            {milestones.map((m) => (
              <option key={m.id} value={m.id}>{m.title}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label>Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Item description..."
            rows={4}
          />
        </div>
        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="save-btn"
            onClick={() => createMutation.mutate()}
            disabled={!title || createMutation.isPending}
          >
            {createMutation.isPending ? 'Creating...' : 'Create Item'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Milestone Detail Modal
// ---------------------------------------------------------------------------

export function MilestoneDetailModal({
  milestone,
  itemCount,
  doneCount,
  onClose,
}: {
  milestone: Milestone;
  itemCount: number;
  doneCount: number;
  onClose: () => void;
}) {
  const modalRef = useRef<HTMLDivElement>(null);

  // Fetch milestone plan content if plan_path exists
  const { data: planData, isLoading: isLoadingPlan } = useQuery({
    queryKey: ['milestone-plan', milestone.id],
    queryFn: () => roadmapApi.getMilestonePlan(milestone.id).then((r) => r.data),
    enabled: !!milestone.plan_path,
    retry: false,
  });

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const statusColors: Record<string, string> = {
    planned: '#89ddff',
    in_progress: '#ffcb6b',
    completed: '#c3e88d',
  };

  const progressPercent = itemCount > 0 ? Math.round((doneCount / itemCount) * 100) : 0;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={modalRef}
        className="modal-content milestone-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="milestone-modal-header">
          <div className="milestone-badge" style={{ backgroundColor: statusColors[milestone.status] + '30', color: statusColors[milestone.status] }}>
            {milestone.status.replace('_', ' ')}
          </div>
          <h3>{milestone.title}</h3>
          <button className="close-btn" onClick={onClose} aria-label="Close">×</button>
        </div>

        {milestone.description && (
          <p className="milestone-description">{milestone.description}</p>
        )}

        <div className="milestone-stats">
          <div className="progress-section">
            <div className="progress-header">
              <span>Progress</span>
              <span>{doneCount}/{itemCount} items ({progressPercent}%)</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
            </div>
          </div>

          {milestone.target_date && (
            <div className="target-date">
              <span className="label">Target Date</span>
              <span className="value">{new Date(milestone.target_date).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        {milestone.plan_path && (
          <div className="milestone-plan-section">
            <h4>Plan</h4>
            {isLoadingPlan ? (
              <div className="loading-state small">Loading plan...</div>
            ) : planData?.content ? (
              <pre className="plan-content">{planData.content}</pre>
            ) : (
              <div className="plan-path">
                <span className="label">Plan file:</span>
                <code>{milestone.plan_path}</code>
              </div>
            )}
          </div>
        )}

        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
