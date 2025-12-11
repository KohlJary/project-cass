import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsApi, roadmapApi, filesApi } from '../api/client';
import './Projects.css';

interface Project {
  id: string;
  name: string;
  description: string;
  working_directory: string;
  created_at: string;
  github_repo?: string;
  github_token?: string;
}

interface Document {
  id: string;
  title: string;
  content: string;
  doc_type: string;
  created_at: string;
  updated_at: string;
}

interface RoadmapItem {
  id: string;
  title: string;
  description: string;
  priority: string;
  item_type: string;
  status: string;
  milestone_id?: string;
  assigned_to?: string;
  created_at: string;
  updated_at: string;
}

interface Milestone {
  id: string;
  title: string;
  description: string;
  status: string;
  target_date?: string;
  plan_path?: string;
}

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  modified: number;
}

type TabId = 'overview' | 'documents' | 'roadmap' | 'files' | 'metrics';

export function Projects() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    searchParams.get('project') || null
  );
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'overview'
  );
  const [showNewProjectModal, setShowNewProjectModal] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');

  const queryClient = useQueryClient();

  // Update URL when tab or project changes
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedProjectId) params.set('project', selectedProjectId);
    if (activeTab !== 'overview') params.set('tab', activeTab);
    setSearchParams(params, { replace: true });
  }, [selectedProjectId, activeTab, setSearchParams]);

  const { data: projectsData, isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.getAll().then((r) => r.data),
    retry: false,
  });

  const selectedProject = projectsData?.projects?.find((p: Project) => p.id === selectedProjectId);

  // Filter projects by search term
  const filteredProjects = projectsData?.projects?.filter((project: Project) => {
    if (!searchFilter.trim()) return true;
    const term = searchFilter.toLowerCase();
    return (
      project.name.toLowerCase().includes(term) ||
      project.description?.toLowerCase().includes(term) ||
      project.working_directory?.toLowerCase().includes(term)
    );
  }) || [];

  return (
    <div className="projects-page">
      <header className="page-header">
        <h1>Projects</h1>
        <p className="subtitle">Manage project workspaces, documents, and roadmap items</p>
      </header>

      <div className="projects-layout">
        {/* Project list sidebar */}
        <div className="projects-list-panel">
          <div className="panel-header">
            <h2>All Projects</h2>
            <button
              className="new-btn"
              onClick={() => setShowNewProjectModal(true)}
              aria-label="Create new project"
            >
              +
            </button>
          </div>

          {projectsData?.projects?.length > 0 && (
            <div className="search-filter">
              <input
                type="text"
                placeholder="Filter projects..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="filter-input"
              />
              {searchFilter && (
                <button
                  className="clear-filter"
                  onClick={() => setSearchFilter('')}
                  aria-label="Clear filter"
                >
                  ×
                </button>
              )}
            </div>
          )}

          {isLoading ? (
            <div className="loading-state">Loading projects...</div>
          ) : error ? (
            <div className="error-state">Failed to load projects</div>
          ) : filteredProjects.length > 0 ? (
            <div className="project-list">
              {filteredProjects.map((project: Project) => (
                <div
                  key={project.id}
                  className={`project-item ${selectedProjectId === project.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedProjectId(project.id);
                    setActiveTab('overview');
                  }}
                >
                  <div className="project-icon">
                    {project.name?.charAt(0).toUpperCase() || 'P'}
                  </div>
                  <div className="project-info">
                    <div className="project-name">{project.name}</div>
                    {project.description && (
                      <div className="project-description-preview">
                        {project.description.length > 80
                          ? project.description.substring(0, 80) + '...'
                          : project.description}
                      </div>
                    )}
                    <div className="project-path" title={project.working_directory}>
                      {project.working_directory}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : projectsData?.projects?.length > 0 && searchFilter ? (
            <div className="empty-state">
              <p>No projects match "{searchFilter}"</p>
              <button className="create-btn" onClick={() => setSearchFilter('')}>
                Clear Filter
              </button>
            </div>
          ) : (
            <div className="empty-state">
              <p>No projects yet</p>
              <button className="create-btn" onClick={() => setShowNewProjectModal(true)}>
                Create Project
              </button>
            </div>
          )}
        </div>

        {/* Project detail panel */}
        <div className="project-detail-panel">
          {selectedProject ? (
            <>
              <div className="detail-tabs" role="tablist" aria-label="Project sections">
                <button
                  className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab('overview')}
                  role="tab"
                  id="tab-overview"
                  aria-selected={activeTab === 'overview'}
                  aria-controls="tabpanel-overview"
                >
                  Overview
                </button>
                <button
                  className={`tab ${activeTab === 'documents' ? 'active' : ''}`}
                  onClick={() => setActiveTab('documents')}
                  role="tab"
                  id="tab-documents"
                  aria-selected={activeTab === 'documents'}
                  aria-controls="tabpanel-documents"
                >
                  Documents
                </button>
                <button
                  className={`tab ${activeTab === 'roadmap' ? 'active' : ''}`}
                  onClick={() => setActiveTab('roadmap')}
                  role="tab"
                  id="tab-roadmap"
                  aria-selected={activeTab === 'roadmap'}
                  aria-controls="tabpanel-roadmap"
                >
                  Roadmap
                </button>
                <button
                  className={`tab ${activeTab === 'files' ? 'active' : ''}`}
                  onClick={() => setActiveTab('files')}
                  role="tab"
                  id="tab-files"
                  aria-selected={activeTab === 'files'}
                  aria-controls="tabpanel-files"
                >
                  Files
                </button>
                <button
                  className={`tab ${activeTab === 'metrics' ? 'active' : ''}`}
                  onClick={() => setActiveTab('metrics')}
                  role="tab"
                  id="tab-metrics"
                  aria-selected={activeTab === 'metrics'}
                  aria-controls="tabpanel-metrics"
                >
                  Metrics
                </button>
              </div>

              <div
                className="detail-content"
                role="tabpanel"
                id={`tabpanel-${activeTab}`}
                aria-labelledby={`tab-${activeTab}`}
              >
                {activeTab === 'overview' && (
                  <OverviewTab
                    project={selectedProject}
                    onRefresh={() => queryClient.invalidateQueries({ queryKey: ['projects'] })}
                  />
                )}
                {activeTab === 'documents' && (
                  <DocumentsTab projectId={selectedProject.id} />
                )}
                {activeTab === 'roadmap' && (
                  <RoadmapTab projectId={selectedProject.id} />
                )}
                {activeTab === 'files' && (
                  <FilesTab workingDirectory={selectedProject.working_directory} />
                )}
                {activeTab === 'metrics' && (
                  <MetricsTab projectId={selectedProject.id} project={selectedProject} />
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="project-icon large">P</div>
              <p>Select a project to view details</p>
            </div>
          )}
        </div>
      </div>

      {showNewProjectModal && (
        <NewProjectModal
          onClose={() => setShowNewProjectModal(false)}
          onCreated={(projectId) => {
            setShowNewProjectModal(false);
            setSelectedProjectId(projectId);
            queryClient.invalidateQueries({ queryKey: ['projects'] });
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview Tab
// ---------------------------------------------------------------------------

function OverviewTab({ project, onRefresh }: { project: Project; onRefresh: () => void }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(project.name);
  const [editDescription, setEditDescription] = useState(project.description || '');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const queryClient = useQueryClient();

  const { data: docsData } = useQuery({
    queryKey: ['project-documents', project.id],
    queryFn: () => projectsApi.getDocuments(project.id).then((r) => r.data),
    retry: false,
  });

  const { data: roadmapData } = useQuery({
    queryKey: ['project-roadmap', project.id],
    queryFn: () => roadmapApi.getItems({ project_id: project.id }).then((r) => r.data),
    retry: false,
  });

  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string }) =>
      projectsApi.update(project.id, data),
    onSuccess: () => {
      setIsEditing(false);
      onRefresh();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => projectsApi.delete(project.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });

  const handleCopyPath = () => {
    navigator.clipboard.writeText(project.working_directory);
  };

  return (
    <div className="overview-tab">
      <div className="overview-header">
        {isEditing ? (
          <div className="edit-form">
            <input
              type="text"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              placeholder="Project name"
              className="edit-name"
            />
            <textarea
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              placeholder="Description"
              className="edit-description"
              rows={3}
            />
            <div className="edit-actions">
              <button
                className="cancel-btn"
                onClick={() => {
                  setIsEditing(false);
                  setEditName(project.name);
                  setEditDescription(project.description || '');
                }}
              >
                Cancel
              </button>
              <button
                className="save-btn"
                onClick={() => updateMutation.mutate({ name: editName, description: editDescription })}
                disabled={updateMutation.isPending}
              >
                {updateMutation.isPending ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="project-title">
              <h2>{project.name}</h2>
              <button className="edit-btn" onClick={() => setIsEditing(true)}>Edit</button>
            </div>
            {project.description && (
              <p className="project-description">{project.description}</p>
            )}
          </>
        )}
      </div>

      <div className="overview-sections">
        <div className="overview-section">
          <h3>Working Directory</h3>
          <div className="path-display">
            <code title={project.working_directory}>{project.working_directory}</code>
            <button className="copy-btn" onClick={handleCopyPath} title="Copy path">
              Copy
            </button>
          </div>
        </div>

        <div className="overview-section">
          <h3>Quick Stats</h3>
          <div className="stats-grid">
            <div className="stat-card">
              <span className="stat-value">{docsData?.documents?.length || 0}</span>
              <span className="stat-label">Documents</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">{roadmapData?.items?.length || 0}</span>
              <span className="stat-label">Roadmap Items</span>
            </div>
            <div className="stat-card">
              <span className="stat-value">
                {roadmapData?.items?.filter((i: RoadmapItem) => i.status === 'in_progress').length || 0}
              </span>
              <span className="stat-label">In Progress</span>
            </div>
          </div>
        </div>

        <div className="overview-section">
          <h3>Created</h3>
          <p className="created-date">{new Date(project.created_at).toLocaleString()}</p>
        </div>

        <div className="overview-section danger-zone">
          <h3>Danger Zone</h3>
          {showDeleteConfirm ? (
            <div className="delete-confirm">
              <p>Are you sure you want to delete this project? This cannot be undone.</p>
              <div className="confirm-actions">
                <button className="cancel-btn" onClick={() => setShowDeleteConfirm(false)}>
                  Cancel
                </button>
                <button
                  className="delete-btn"
                  onClick={() => deleteMutation.mutate()}
                  disabled={deleteMutation.isPending}
                >
                  {deleteMutation.isPending ? 'Deleting...' : 'Delete Project'}
                </button>
              </div>
            </div>
          ) : (
            <button className="delete-trigger" onClick={() => setShowDeleteConfirm(true)}>
              Delete Project
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Documents Tab
// ---------------------------------------------------------------------------

function DocumentsTab({ projectId }: { projectId: string }) {
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [showNewDocModal, setShowNewDocModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const queryClient = useQueryClient();

  // Fetch document list
  const { data: docsData, isLoading } = useQuery({
    queryKey: ['project-documents', projectId],
    queryFn: () => projectsApi.getDocuments(projectId).then((r) => r.data),
    retry: false,
  });

  // Fetch full document content when selected
  const { data: fullDocData, isLoading: isLoadingDoc } = useQuery({
    queryKey: ['project-document', projectId, selectedDocId],
    queryFn: () => projectsApi.getDocument(projectId, selectedDocId!).then((r) => r.data),
    enabled: !!selectedDocId,
    retry: false,
  });

  // Use list data for title/metadata, full data for content
  const selectedDocMeta = docsData?.documents?.find((d: Document) => d.id === selectedDocId);
  const selectedDoc = fullDocData || selectedDocMeta;

  const updateMutation = useMutation({
    mutationFn: (content: string) =>
      projectsApi.updateDocument(projectId, selectedDocId!, { content }),
    onSuccess: () => {
      setIsEditing(false);
      queryClient.invalidateQueries({ queryKey: ['project-documents', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project-document', projectId, selectedDocId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => projectsApi.deleteDocument(projectId, selectedDocId!),
    onSuccess: () => {
      setSelectedDocId(null);
      queryClient.invalidateQueries({ queryKey: ['project-documents', projectId] });
    },
  });

  return (
    <div className="documents-tab">
      <div className="documents-layout">
        <div className="documents-list">
          <div className="list-header">
            <span>Documents</span>
            <button
              className="new-btn"
              onClick={() => setShowNewDocModal(true)}
              aria-label="Create new document"
            >
              +
            </button>
          </div>
          {isLoading ? (
            <div className="loading-state small">Loading...</div>
          ) : docsData?.documents?.length > 0 ? (
            <div className="doc-items">
              {docsData.documents.map((doc: Document) => (
                <div
                  key={doc.id}
                  className={`doc-item ${selectedDocId === doc.id ? 'selected' : ''}`}
                  onClick={() => {
                    setSelectedDocId(doc.id);
                    setIsEditing(false);
                  }}
                >
                  <span className="doc-title">{doc.title}</span>
                  {doc.doc_type && <span className="doc-type">{doc.doc_type}</span>}
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state small">No documents</div>
          )}
        </div>

        <div className="document-content">
          {selectedDoc ? (
            <>
              <div className="doc-header">
                <h3>{selectedDoc.title}</h3>
                <div className="doc-actions">
                  {isEditing ? (
                    <>
                      <button
                        className="cancel-btn"
                        onClick={() => {
                          setIsEditing(false);
                          setEditContent('');
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        className="save-btn"
                        onClick={() => updateMutation.mutate(editContent)}
                        disabled={updateMutation.isPending}
                      >
                        Save
                      </button>
                    </>
                  ) : showDeleteConfirm ? (
                    <>
                      <button
                        className="cancel-btn"
                        onClick={() => setShowDeleteConfirm(false)}
                      >
                        Cancel
                      </button>
                      <button
                        className="delete-btn"
                        onClick={() => {
                          deleteMutation.mutate();
                          setShowDeleteConfirm(false);
                        }}
                        disabled={deleteMutation.isPending}
                      >
                        {deleteMutation.isPending ? 'Deleting...' : 'Confirm Delete'}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="edit-btn"
                        onClick={() => {
                          setEditContent(selectedDoc.content);
                          setIsEditing(true);
                        }}
                      >
                        Edit
                      </button>
                      <button
                        className="delete-btn"
                        onClick={() => setShowDeleteConfirm(true)}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
              <div className="doc-body">
                {isEditing ? (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="doc-editor"
                  />
                ) : isLoadingDoc ? (
                  <div className="loading-state small">Loading content...</div>
                ) : selectedDoc.content ? (
                  <pre className="doc-content">{selectedDoc.content}</pre>
                ) : (
                  <div className="empty-state small">No content</div>
                )}
              </div>
              <div className="doc-meta">
                {selectedDoc.doc_type && <span>Type: {selectedDoc.doc_type}</span>}
                <span>Updated: {new Date(selectedDoc.updated_at).toLocaleDateString()}</span>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p>Select a document to view</p>
            </div>
          )}
        </div>
      </div>

      {showNewDocModal && (
        <NewDocumentModal
          projectId={projectId}
          onClose={() => setShowNewDocModal(false)}
          onCreated={() => {
            setShowNewDocModal(false);
            queryClient.invalidateQueries({ queryKey: ['project-documents', projectId] });
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Roadmap Tab
// ---------------------------------------------------------------------------

type RoadmapView = 'list' | 'kanban';

function RoadmapTab({ projectId }: { projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showNewItemModal, setShowNewItemModal] = useState(false);
  const [selectedMilestone, setSelectedMilestone] = useState<Milestone | null>(null);
  const [viewMode, setViewMode] = useState<RoadmapView>('list');

  const queryClient = useQueryClient();

  const { data: itemsData, isLoading } = useQuery({
    queryKey: ['project-roadmap', projectId, statusFilter],
    queryFn: () =>
      roadmapApi.getItems({
        project_id: projectId,
        status: statusFilter || undefined,
      }).then((r) => r.data),
    retry: false,
  });

  const { data: milestonesData } = useQuery({
    queryKey: ['project-milestones', projectId],
    queryFn: () => roadmapApi.getMilestones({ project_id: projectId }).then((r) => r.data),
    retry: false,
  });

  const statusColors: Record<string, string> = {
    backlog: '#666',
    ready: '#89ddff',
    in_progress: '#ffcb6b',
    review: '#c792ea',
    done: '#c3e88d',
  };

  const priorityColors: Record<string, string> = {
    P0: '#f07178',
    P1: '#ffcb6b',
    P2: '#89ddff',
    P3: '#666',
  };

  // Group items by milestone
  const itemsByMilestone: Record<string, RoadmapItem[]> = {};
  const unassignedItems: RoadmapItem[] = [];

  itemsData?.items?.forEach((item: RoadmapItem) => {
    if (item.milestone_id) {
      if (!itemsByMilestone[item.milestone_id]) {
        itemsByMilestone[item.milestone_id] = [];
      }
      itemsByMilestone[item.milestone_id].push(item);
    } else {
      unassignedItems.push(item);
    }
  });

  const getMilestone = (id: string): Milestone | undefined => {
    return milestonesData?.milestones?.find((m: Milestone) => m.id === id);
  };

  // Group items by status for Kanban view
  const itemsByStatus: Record<string, RoadmapItem[]> = {
    backlog: [],
    ready: [],
    in_progress: [],
    review: [],
    done: [],
  };

  itemsData?.items?.forEach((item: RoadmapItem) => {
    if (itemsByStatus[item.status]) {
      itemsByStatus[item.status].push(item);
    }
  });

  const statuses = ['backlog', 'ready', 'in_progress', 'review', 'done'];

  return (
    <div className="roadmap-tab">
      <div className="roadmap-header">
        <div className="view-toggle">
          <button
            className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
            aria-label="List view"
            title="List view"
          >
            <span className="view-icon">☰</span>
          </button>
          <button
            className={`view-btn ${viewMode === 'kanban' ? 'active' : ''}`}
            onClick={() => setViewMode('kanban')}
            aria-label="Kanban view"
            title="Kanban view"
          >
            <span className="view-icon">▦</span>
          </button>
        </div>
        {viewMode === 'list' && (
          <div className="status-filters">
            <button
              className={`filter-btn ${statusFilter === '' ? 'active' : ''}`}
              onClick={() => setStatusFilter('')}
            >
              All
            </button>
            {statuses.map((status) => (
              <button
                key={status}
                className={`filter-btn ${statusFilter === status ? 'active' : ''}`}
                onClick={() => setStatusFilter(status)}
                style={{ '--status-color': statusColors[status] } as React.CSSProperties}
              >
                {status.replace('_', ' ')}
              </button>
            ))}
          </div>
        )}
        <button
          className="new-btn"
          onClick={() => setShowNewItemModal(true)}
          aria-label="Create new roadmap item"
        >
          + New Item
        </button>
      </div>

      {isLoading ? (
        <div className="loading-state">Loading roadmap...</div>
      ) : itemsData?.items?.length > 0 ? (
        viewMode === 'kanban' ? (
          /* Kanban Board View */
          <div className="kanban-board">
            {statuses.map((status) => (
              <div key={status} className="kanban-column">
                <div
                  className="kanban-column-header"
                  style={{ borderTopColor: statusColors[status] }}
                >
                  <span
                    className="status-indicator"
                    style={{ backgroundColor: statusColors[status] }}
                  />
                  <span className="column-title">{status.replace('_', ' ')}</span>
                  <span className="column-count">{itemsByStatus[status].length}</span>
                </div>
                <div className="kanban-column-content">
                  {itemsByStatus[status].map((item) => (
                    <KanbanCard
                      key={item.id}
                      item={item}
                      priorityColors={priorityColors}
                      onUpdate={() => queryClient.invalidateQueries({ queryKey: ['project-roadmap', projectId] })}
                    />
                  ))}
                  {itemsByStatus[status].length === 0 && (
                    <div className="kanban-empty">No items</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* List View */
          <div className="roadmap-content">
            {/* Items grouped by milestone */}
            {Object.entries(itemsByMilestone).map(([milestoneId, items]) => {
              const milestone = getMilestone(milestoneId);
              return (
              <div key={milestoneId} className="milestone-group">
                <div
                  className="milestone-header clickable"
                  onClick={() => milestone && setSelectedMilestone(milestone)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && milestone) {
                      e.preventDefault();
                      setSelectedMilestone(milestone);
                    }
                  }}
                  title="Click to view milestone details"
                >
                  <span className="milestone-icon">M</span>
                  <span className="milestone-title">{milestone?.title || 'Unknown Milestone'}</span>
                  <span className="item-count">{items.length}</span>
                  <span className="view-milestone">View</span>
                </div>
                <div className="roadmap-items">
                  {items.map((item) => (
                    <RoadmapItemCard
                      key={item.id}
                      item={item}
                      statusColors={statusColors}
                      priorityColors={priorityColors}
                      onUpdate={() => queryClient.invalidateQueries({ queryKey: ['project-roadmap', projectId] })}
                    />
                  ))}
                </div>
              </div>
            );
            })}

            {/* Unassigned items */}
            {unassignedItems.length > 0 && (
              <div className="milestone-group">
                <div className="milestone-header">
                  <span className="milestone-icon unassigned">-</span>
                  <span className="milestone-title">No Milestone</span>
                  <span className="item-count">{unassignedItems.length}</span>
                </div>
                <div className="roadmap-items">
                  {unassignedItems.map((item) => (
                    <RoadmapItemCard
                      key={item.id}
                      item={item}
                      statusColors={statusColors}
                      priorityColors={priorityColors}
                      onUpdate={() => queryClient.invalidateQueries({ queryKey: ['project-roadmap', projectId] })}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      ) : (
        <div className="empty-state">
          <p>No roadmap items for this project</p>
          <button className="create-btn" onClick={() => setShowNewItemModal(true)}>
            Create Item
          </button>
        </div>
      )}

      {showNewItemModal && (
        <NewRoadmapItemModal
          projectId={projectId}
          milestones={milestonesData?.milestones || []}
          onClose={() => setShowNewItemModal(false)}
          onCreated={() => {
            setShowNewItemModal(false);
            queryClient.invalidateQueries({ queryKey: ['project-roadmap', projectId] });
          }}
        />
      )}

      {selectedMilestone && (
        <MilestoneDetailModal
          milestone={selectedMilestone}
          itemCount={itemsByMilestone[selectedMilestone.id]?.length || 0}
          doneCount={itemsByMilestone[selectedMilestone.id]?.filter((i) => i.status === 'done').length || 0}
          onClose={() => setSelectedMilestone(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Files Tab
// ---------------------------------------------------------------------------

function FilesTab({ workingDirectory }: { workingDirectory: string }) {
  const [currentPath, setCurrentPath] = useState(workingDirectory);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [showHidden, setShowHidden] = useState(false);

  const { data: listData, isLoading, error } = useQuery({
    queryKey: ['files-list', currentPath, showHidden],
    queryFn: () => filesApi.list(currentPath, showHidden).then((r) => r.data),
    retry: false,
  });

  const { data: fileContent, isLoading: isLoadingFile } = useQuery({
    queryKey: ['file-content', selectedFile],
    queryFn: () => filesApi.read(selectedFile!).then((r) => r.data),
    enabled: !!selectedFile,
    retry: false,
  });

  const navigateUp = () => {
    const parent = currentPath.split('/').slice(0, -1).join('/') || '/';
    setCurrentPath(parent);
    setSelectedFile(null);
  };

  const navigateTo = (entry: FileEntry) => {
    if (entry.is_dir) {
      setCurrentPath(entry.path);
      setSelectedFile(null);
    } else {
      setSelectedFile(entry.path);
    }
  };

  const formatSize = (size: number | null) => {
    if (size === null) return '-';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString();
  };

  // Check if we're above the working directory
  const canGoUp = currentPath !== '/' && currentPath.startsWith(workingDirectory.split('/').slice(0, -1).join('/'));

  return (
    <div className="files-tab">
      <div className="files-header">
        <div className="path-nav">
          <button
            className="nav-btn"
            onClick={navigateUp}
            disabled={!canGoUp}
            title="Go up"
          >
            ↑
          </button>
          <button
            className="nav-btn"
            onClick={() => { setCurrentPath(workingDirectory); setSelectedFile(null); }}
            title="Go to project root"
          >
            ⌂
          </button>
          <span className="current-path" title={currentPath}>
            {currentPath.replace(workingDirectory, '.') || '/'}
          </span>
        </div>
        <label className="show-hidden">
          <input
            type="checkbox"
            checked={showHidden}
            onChange={(e) => setShowHidden(e.target.checked)}
          />
          Show hidden
        </label>
      </div>

      <div className="files-layout">
        <div className="file-list">
          {isLoading ? (
            <div className="loading-state small">Loading...</div>
          ) : error ? (
            <div className="error-state small">Failed to load directory</div>
          ) : listData?.entries?.length > 0 ? (
            <table className="files-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Size</th>
                  <th>Modified</th>
                </tr>
              </thead>
              <tbody>
                {listData.entries.map((entry: FileEntry) => (
                  <tr
                    key={entry.path}
                    className={`file-row ${entry.is_dir ? 'directory' : 'file'} ${selectedFile === entry.path ? 'selected' : ''}`}
                    onClick={() => navigateTo(entry)}
                  >
                    <td className="file-name">
                      <span className="file-icon">{entry.is_dir ? '📁' : '📄'}</span>
                      {entry.name}
                    </td>
                    <td className="file-size">{formatSize(entry.size)}</td>
                    <td className="file-date">{formatDate(entry.modified)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty-state small">Empty directory</div>
          )}
        </div>

        {selectedFile && (
          <div className="file-preview">
            <div className="preview-header">
              <span className="preview-name">{selectedFile.split('/').pop()}</span>
            </div>
            <div className="preview-content">
              {isLoadingFile ? (
                <div className="loading-state small">Loading...</div>
              ) : fileContent?.content ? (
                <pre className="file-content">{fileContent.content}</pre>
              ) : (
                <div className="empty-state small">Cannot preview file</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metrics Tab
// ---------------------------------------------------------------------------

function MetricsTab({ projectId, project }: { projectId: string; project: Project }) {
  const [showConfig, setShowConfig] = useState(false);
  const [repoInput, setRepoInput] = useState(project.github_repo || '');
  const [tokenInput, setTokenInput] = useState('');
  const queryClient = useQueryClient();

  const { data: metricsData, isLoading, error, refetch } = useQuery({
    queryKey: ['project-github-metrics', projectId],
    queryFn: () => projectsApi.getGitHubMetrics(projectId).then((r) => r.data),
    retry: false,
    enabled: !!project.github_repo,
  });

  const refreshMutation = useMutation({
    mutationFn: () => projectsApi.refreshGitHubMetrics(projectId),
    onSuccess: () => refetch(),
  });

  const updateConfigMutation = useMutation({
    mutationFn: (data: { github_repo?: string; github_token?: string; clear_github_token?: boolean }) =>
      projectsApi.update(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['project-github-metrics', projectId] });
      setShowConfig(false);
      setTokenInput('');
    },
  });

  const handleSaveConfig = () => {
    const data: { github_repo?: string; github_token?: string } = {};
    if (repoInput !== project.github_repo) {
      data.github_repo = repoInput || '';
    }
    if (tokenInput) {
      data.github_token = tokenInput;
    }
    if (Object.keys(data).length > 0) {
      updateConfigMutation.mutate(data);
    } else {
      setShowConfig(false);
    }
  };

  const handleClearToken = () => {
    updateConfigMutation.mutate({ clear_github_token: true });
  };

  const metrics = metricsData?.metrics;

  return (
    <div className="metrics-tab">
      <div className="metrics-header">
        <h3>GitHub Metrics</h3>
        <div className="header-actions">
          {project.github_repo && (
            <button
              className="refresh-btn"
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending}
            >
              {refreshMutation.isPending ? 'Refreshing...' : 'Refresh'}
            </button>
          )}
          <button
            className="config-btn"
            onClick={() => setShowConfig(!showConfig)}
          >
            {showConfig ? 'Cancel' : 'Configure'}
          </button>
        </div>
      </div>

      {showConfig && (
        <div className="github-config">
          <div className="config-field">
            <label>GitHub Repository</label>
            <input
              type="text"
              value={repoInput}
              onChange={(e) => setRepoInput(e.target.value)}
              placeholder="owner/repo"
            />
            <span className="field-hint">Format: owner/repo (e.g., KohlJary/cass-vessel)</span>
          </div>
          <div className="config-field">
            <label>
              Personal Access Token
              {project.github_token ? (
                <span className="token-status configured"> (configured)</span>
              ) : (
                <span className="token-status"> (using system default)</span>
              )}
            </label>
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder={project.github_token ? '••••••••' : 'Leave empty to use system default'}
            />
            <span className="field-hint">
              Optional. Set a project-specific PAT for private repos or higher rate limits.
            </span>
            {project.github_token && (
              <button className="clear-token-btn" onClick={handleClearToken}>
                Clear project token (use system default)
              </button>
            )}
          </div>
          <div className="config-actions">
            <button
              className="save-btn"
              onClick={handleSaveConfig}
              disabled={updateConfigMutation.isPending}
            >
              {updateConfigMutation.isPending ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      )}

      {!project.github_repo ? (
        <div className="empty-state">
          <p>No GitHub repository configured</p>
          <p className="hint">Click "Configure" to link a GitHub repository to this project.</p>
        </div>
      ) : isLoading ? (
        <div className="loading-state">Loading metrics...</div>
      ) : error ? (
        <div className="error-state">
          <p>Failed to load GitHub metrics</p>
          <p className="error-hint">Check your repository name and token permissions.</p>
        </div>
      ) : metrics ? (
        <>
          <div className="repo-info">
            <span className="repo-name-display">{metrics.repo}</span>
            {metricsData?.has_project_token && (
              <span className="token-badge">Using project token</span>
            )}
          </div>

          <div className="metrics-summary">
            <div className="summary-card">
              <span className="summary-value">{metrics.stars}</span>
              <span className="summary-label">Stars</span>
            </div>
            <div className="summary-card">
              <span className="summary-value">{metrics.forks}</span>
              <span className="summary-label">Forks</span>
            </div>
            <div className="summary-card">
              <span className="summary-value">{metrics.watchers}</span>
              <span className="summary-label">Watchers</span>
            </div>
            <div className="summary-card">
              <span className="summary-value">{metrics.open_issues}</span>
              <span className="summary-label">Open Issues</span>
            </div>
          </div>

          {(metrics.clones_count > 0 || metrics.views_count > 0) && (
            <div className="traffic-stats">
              <h4>Traffic (Last 14 Days)</h4>
              <div className="traffic-grid">
                <div className="traffic-card">
                  <span className="traffic-value">{metrics.clones_count}</span>
                  <span className="traffic-label">Clones</span>
                  <span className="traffic-unique">{metrics.clones_uniques} unique</span>
                </div>
                <div className="traffic-card">
                  <span className="traffic-value">{metrics.views_count}</span>
                  <span className="traffic-label">Views</span>
                  <span className="traffic-unique">{metrics.views_uniques} unique</span>
                </div>
              </div>
            </div>
          )}

          <div className="last-updated">
            Last updated: {new Date(metrics.last_updated).toLocaleString()}
          </div>
        </>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Milestone Detail Modal
// ---------------------------------------------------------------------------

function MilestoneDetailModal({
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

function RoadmapItemCard({
  item,
  statusColors,
  priorityColors,
  onUpdate,
}: {
  item: RoadmapItem;
  statusColors: Record<string, string>;
  priorityColors: Record<string, string>;
  onUpdate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const pickMutation = useMutation({
    mutationFn: () => roadmapApi.pickItem(item.id, 'daedalus'),
    onSuccess: onUpdate,
  });

  const completeMutation = useMutation({
    mutationFn: () => roadmapApi.completeItem(item.id),
    onSuccess: onUpdate,
  });

  return (
    <div
      className="roadmap-item"
      onClick={() => setExpanded(!expanded)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setExpanded(!expanded);
        }
      }}
      role="button"
      tabIndex={0}
      aria-expanded={expanded}
    >
      <div className="item-main">
        <span
          className="status-dot"
          style={{ backgroundColor: statusColors[item.status] }}
          title={item.status}
        />
        <span
          className="priority-badge"
          style={{ backgroundColor: priorityColors[item.priority] + '30', color: priorityColors[item.priority] }}
        >
          {item.priority}
        </span>
        <span className="item-title">{item.title}</span>
        <span className="item-type">{item.item_type}</span>
      </div>
      {expanded && (
        <div className="item-details">
          {item.description ? (
            <p className="item-description">{item.description}</p>
          ) : (
            <p className="item-description empty">No description provided</p>
          )}

          <div className="item-info-grid">
            <div className="info-item">
              <span className="info-label">Status</span>
              <span className="info-value status-value" style={{ color: statusColors[item.status] }}>
                {item.status.replace('_', ' ')}
              </span>
            </div>
            <div className="info-item">
              <span className="info-label">Type</span>
              <span className="info-value">{item.item_type}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Assigned To</span>
              <span className="info-value">{item.assigned_to || 'Unassigned'}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Created</span>
              <span className="info-value">{new Date(item.created_at).toLocaleDateString()}</span>
            </div>
            {item.updated_at !== item.created_at && (
              <div className="info-item">
                <span className="info-label">Updated</span>
                <span className="info-value">{new Date(item.updated_at).toLocaleDateString()}</span>
              </div>
            )}
          </div>

          <div className="item-actions">
            {item.status === 'ready' && (
              <button
                className="action-btn pick"
                onClick={(e) => {
                  e.stopPropagation();
                  pickMutation.mutate();
                }}
                disabled={pickMutation.isPending}
              >
                Pick Up
              </button>
            )}
            {item.status === 'in_progress' && (
              <button
                className="action-btn complete"
                onClick={(e) => {
                  e.stopPropagation();
                  completeMutation.mutate();
                }}
                disabled={completeMutation.isPending}
              >
                Complete
              </button>
            )}
            {item.status === 'backlog' && (
              <button
                className="action-btn ready"
                onClick={(e) => {
                  e.stopPropagation();
                  // Move to ready status
                  roadmapApi.updateItem(item.id, { status: 'ready' }).then(onUpdate);
                }}
              >
                Mark Ready
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function KanbanCard({
  item,
  priorityColors,
  onUpdate,
}: {
  item: RoadmapItem;
  priorityColors: Record<string, string>;
  onUpdate: () => void;
}) {
  const pickMutation = useMutation({
    mutationFn: () => roadmapApi.pickItem(item.id, 'daedalus'),
    onSuccess: onUpdate,
  });

  const completeMutation = useMutation({
    mutationFn: () => roadmapApi.completeItem(item.id),
    onSuccess: onUpdate,
  });

  const advanceStatus = (newStatus: string) => {
    roadmapApi.updateItem(item.id, { status: newStatus }).then(onUpdate);
  };

  return (
    <div className="kanban-card">
      <div className="kanban-card-header">
        <span
          className="priority-badge"
          style={{ backgroundColor: priorityColors[item.priority] + '30', color: priorityColors[item.priority] }}
        >
          {item.priority}
        </span>
        <span className="item-type">{item.item_type}</span>
      </div>
      <div className="kanban-card-title">{item.title}</div>
      {item.description && (
        <div className="kanban-card-description">
          {item.description.length > 100 ? item.description.substring(0, 100) + '...' : item.description}
        </div>
      )}
      <div className="kanban-card-footer">
        {item.assigned_to && (
          <span className="assignee" title={`Assigned to ${item.assigned_to}`}>
            {item.assigned_to.charAt(0).toUpperCase()}
          </span>
        )}
        <div className="kanban-actions">
          {item.status === 'backlog' && (
            <button className="kanban-action" onClick={() => advanceStatus('ready')} title="Mark Ready">
              →
            </button>
          )}
          {item.status === 'ready' && (
            <button
              className="kanban-action"
              onClick={() => pickMutation.mutate()}
              disabled={pickMutation.isPending}
              title="Pick Up"
            >
              ▶
            </button>
          )}
          {item.status === 'in_progress' && (
            <button className="kanban-action" onClick={() => advanceStatus('review')} title="Move to Review">
              →
            </button>
          )}
          {item.status === 'review' && (
            <button
              className="kanban-action"
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
              title="Complete"
            >
              ✓
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------

function NewProjectModal({
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

function NewDocumentModal({
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

function NewRoadmapItemModal({
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
