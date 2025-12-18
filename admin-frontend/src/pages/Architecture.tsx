import { useState, useEffect, useCallback, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { chainApi, conversationsApi } from '../api/client';
import type {
  ChainResponse,
  ChainDetailResponse,
  ChainNodeResponse,
  NodeTemplateResponse,
  PreviewResponse,
  ConditionModel,
} from '../api/client';
import { useDaemon } from '../context/DaemonContext';
import './Architecture.css';

// =============================================================================
// REUSABLE TYPES
// =============================================================================

type TabId = 'prompts' | 'global-state' | 'orchestration';

const tabs = [
  { id: 'prompts' as TabId, label: 'System Prompts', icon: 'P' },
  { id: 'global-state' as TabId, label: 'Global State', icon: 'G', disabled: true },
  { id: 'orchestration' as TabId, label: 'Orchestration', icon: 'O', disabled: true },
];

// Category display configuration
const CATEGORY_META: Record<string, { icon: string; label: string; description: string }> = {
  core: { icon: '🏛️', label: 'Core Identity', description: 'Fundamental identity and architecture' },
  vow: { icon: '💜', label: 'Vows', description: 'Ethical scaffolding as load-bearing architecture' },
  context: { icon: '🌐', label: 'Context', description: 'Runtime context injections' },
  feature: { icon: '⚡', label: 'Features', description: 'Behavioral capabilities' },
  tools: { icon: '🔧', label: 'Tools', description: 'Tool definitions and categories' },
  runtime: { icon: '⏱️', label: 'Runtime', description: 'Dynamically injected context' },
  custom: { icon: '✨', label: 'Custom', description: 'User-defined nodes' },
};

// =============================================================================
// REUSABLE COMPONENTS
// =============================================================================

/**
 * ChainSidebar - Reusable sidebar for listing chains/configs
 */
interface ChainSidebarProps {
  chains: ChainResponse[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (chain: ChainResponse) => void;
  onActivate: (chainId: string) => void;
  onDuplicate: (chainId: string) => void;
  onDelete: (chainId: string) => void;
  onCreate?: () => void;
}

function ChainSidebar({
  chains,
  selectedId,
  loading,
  onSelect,
  onActivate,
  onDuplicate,
  onDelete,
  onCreate,
}: ChainSidebarProps) {
  return (
    <aside className="configs-sidebar">
      <div className="sidebar-header">
        <h3>Prompt Chains</h3>
        {onCreate && (
          <button className="new-chain-btn" onClick={onCreate} title="Create new chain">
            +
          </button>
        )}
      </div>
      {loading ? (
        <div className="loading">Loading...</div>
      ) : (
        <ul className="config-list">
          {chains.map((chain) => (
            <li
              key={chain.id}
              className={`config-item ${selectedId === chain.id ? 'selected' : ''} ${chain.is_active ? 'active' : ''}`}
              onClick={() => onSelect(chain)}
            >
              <div className="config-info">
                <span className="config-name">
                  {chain.name}
                  {chain.is_default && <span className="badge default">Default</span>}
                  {chain.is_active && <span className="badge active">Active</span>}
                </span>
                <span className="token-count">
                  {chain.node_count} nodes · ~{chain.token_estimate ?? '?'} tokens
                </span>
              </div>
              <div className="config-actions">
                {!chain.is_active && (
                  <button
                    className="action-btn activate"
                    onClick={(e) => { e.stopPropagation(); onActivate(chain.id); }}
                    title="Activate"
                  >
                    ✓
                  </button>
                )}
                <button
                  className="action-btn duplicate"
                  onClick={(e) => { e.stopPropagation(); onDuplicate(chain.id); }}
                  title="Duplicate"
                >
                  📋
                </button>
                {!chain.is_default && !chain.is_active && (
                  <button
                    className="action-btn delete"
                    onClick={(e) => { e.stopPropagation(); onDelete(chain.id); }}
                    title="Delete"
                  >
                    ×
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

/**
 * NodeCard - Reusable card component for displaying a chain node
 */
interface NodeCardProps {
  node: ChainNodeResponse;
  isDragging?: boolean;
  isLocked?: boolean;
  isDefault?: boolean;
  onToggleEnabled?: (enabled: boolean) => void;
  onEditConditions?: () => void;
  onRemove?: () => void;
  dragHandleProps?: Record<string, unknown>;
}

function NodeCard({
  node,
  isDragging,
  isLocked,
  isDefault,
  onToggleEnabled,
  onEditConditions,
  onRemove,
  dragHandleProps,
}: NodeCardProps) {
  const categoryMeta = CATEGORY_META[node.template_category || 'custom'];
  const hasConditions = node.conditions && node.conditions.length > 0;

  return (
    <div
      className={`node-card ${isDragging ? 'dragging' : ''} ${!node.enabled ? 'disabled' : ''} ${node.locked ? 'locked' : ''}`}
    >
      <div className="node-drag-handle" {...dragHandleProps}>
        ⠿
      </div>
      <div className="node-content">
        <div className="node-header">
          <span className="node-category-icon" title={categoryMeta?.label}>
            {categoryMeta?.icon || '📄'}
          </span>
          <span className="node-name">{node.template_name}</span>
          {node.locked && <span className="lock-icon" title="Safety-critical">🔒</span>}
          {hasConditions && (
            <span className="condition-badge" title={`${node.conditions.length} condition(s)`}>
              ⚡{node.conditions.length}
            </span>
          )}
        </div>
        <div className="node-meta">
          <span className="node-slug">{node.template_slug}</span>
          {node.token_estimate && (
            <span className="node-tokens">~{node.token_estimate} tokens</span>
          )}
        </div>
      </div>
      <div className="node-actions">
        {!isDefault && !isLocked && (
          <>
            <label className="node-toggle" title={node.enabled ? 'Enabled' : 'Disabled'}>
              <input
                type="checkbox"
                checked={node.enabled}
                onChange={(e) => onToggleEnabled?.(e.target.checked)}
                disabled={node.locked}
              />
              <span className="toggle-slider"></span>
            </label>
            {onEditConditions && (
              <button className="node-action-btn" onClick={onEditConditions} title="Edit conditions">
                ⚙️
              </button>
            )}
            {!node.locked && onRemove && (
              <button className="node-action-btn danger" onClick={onRemove} title="Remove node">
                ×
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/**
 * NodeList - Reusable list of nodes with drag-and-drop reordering
 */
interface NodeListProps {
  nodes: ChainNodeResponse[];
  isDefault: boolean;
  onReorder: (nodeIds: string[]) => void;
  onToggleEnabled: (nodeId: string, enabled: boolean) => void;
  onEditConditions: (node: ChainNodeResponse) => void;
  onRemoveNode: (nodeId: string) => void;
}

function NodeList({
  nodes,
  isDefault,
  onReorder,
  onToggleEnabled,
  onEditConditions,
  onRemoveNode,
}: NodeListProps) {
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const handleDragStart = (index: number) => {
    if (isDefault) return;
    setDraggedIndex(index);
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    if (isDefault || draggedIndex === null) return;
    setDragOverIndex(index);
  };

  const handleDragEnd = () => {
    if (draggedIndex !== null && dragOverIndex !== null && draggedIndex !== dragOverIndex) {
      const newNodes = [...nodes];
      const [draggedNode] = newNodes.splice(draggedIndex, 1);
      newNodes.splice(dragOverIndex, 0, draggedNode);
      onReorder(newNodes.map(n => n.id));
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  };

  // Group nodes by category for better organization
  const groupedNodes = nodes.reduce((acc, node) => {
    const cat = node.template_category || 'custom';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(node);
    return acc;
  }, {} as Record<string, ChainNodeResponse[]>);

  const categoryOrder = ['core', 'vow', 'context', 'feature', 'tools', 'runtime', 'custom'];

  return (
    <div className="node-list">
      {categoryOrder.map(cat => {
        const catNodes = groupedNodes[cat];
        if (!catNodes || catNodes.length === 0) return null;
        const meta = CATEGORY_META[cat];
        return (
          <div key={cat} className="node-category-group">
            <div className="category-header">
              <span className="category-icon">{meta?.icon}</span>
              <span className="category-label">{meta?.label}</span>
              <span className="category-count">{catNodes.length}</span>
            </div>
            <div className="category-nodes">
              {catNodes.map((node) => {
                const globalIndex = nodes.indexOf(node);
                return (
                  <div
                    key={node.id}
                    draggable={!isDefault}
                    onDragStart={() => handleDragStart(globalIndex)}
                    onDragOver={(e) => handleDragOver(e, globalIndex)}
                    onDragEnd={handleDragEnd}
                    className={`node-wrapper ${dragOverIndex === globalIndex ? 'drag-over' : ''}`}
                  >
                    <NodeCard
                      node={node}
                      isDragging={draggedIndex === globalIndex}
                      isLocked={node.locked}
                      isDefault={isDefault}
                      onToggleEnabled={(enabled) => onToggleEnabled(node.id, enabled)}
                      onEditConditions={() => onEditConditions(node)}
                      onRemove={() => onRemoveNode(node.id)}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * TemplateDrawer - Drawer for browsing and adding templates
 */
interface TemplateDrawerProps {
  templates: NodeTemplateResponse[];
  existingTemplateIds: string[];
  isOpen: boolean;
  onClose: () => void;
  onAddTemplate: (slug: string) => void;
}

function TemplateDrawer({
  templates,
  existingTemplateIds,
  isOpen,
  onClose,
  onAddTemplate,
}: TemplateDrawerProps) {
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const categories = [...new Set(templates.map(t => t.category))];

  const filteredTemplates = templates.filter(t => {
    const matchesSearch = !search ||
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.slug.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = !selectedCategory || t.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  if (!isOpen) return null;

  return (
    <div className="template-drawer-backdrop" onClick={onClose}>
      <div className="template-drawer" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <h3>Add Node Template</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="drawer-filters">
          <input
            type="text"
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="template-search"
          />
          <div className="category-filters">
            <button
              className={`category-filter ${!selectedCategory ? 'active' : ''}`}
              onClick={() => setSelectedCategory(null)}
            >
              All
            </button>
            {categories.map(cat => (
              <button
                key={cat}
                className={`category-filter ${selectedCategory === cat ? 'active' : ''}`}
                onClick={() => setSelectedCategory(cat)}
              >
                {CATEGORY_META[cat]?.icon} {CATEGORY_META[cat]?.label || cat}
              </button>
            ))}
          </div>
        </div>

        <div className="drawer-templates">
          {filteredTemplates.map(template => {
            const isAdded = existingTemplateIds.includes(template.id);
            return (
              <div
                key={template.id}
                className={`template-card ${isAdded ? 'added' : ''} ${template.is_locked ? 'locked' : ''}`}
              >
                <div className="template-info">
                  <div className="template-header">
                    <span className="template-icon">{CATEGORY_META[template.category]?.icon}</span>
                    <span className="template-name">{template.name}</span>
                    {template.is_locked && <span className="lock-badge">🔒</span>}
                  </div>
                  <div className="template-slug">{template.slug}</div>
                  {template.description && (
                    <div className="template-description">{template.description}</div>
                  )}
                  <div className="template-meta">
                    <span>~{template.token_estimate} tokens</span>
                  </div>
                </div>
                <button
                  className="add-template-btn"
                  onClick={() => onAddTemplate(template.slug)}
                  disabled={isAdded}
                >
                  {isAdded ? 'Added' : '+ Add'}
                </button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/**
 * ConditionEditorModal - Modal for editing node conditions
 */
interface ConditionEditorModalProps {
  node: ChainNodeResponse | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (conditions: ConditionModel[]) => void;
}

function ConditionEditorModal({
  node,
  isOpen,
  onClose,
  onSave,
}: ConditionEditorModalProps) {
  const [conditions, setConditions] = useState<ConditionModel[]>([]);

  useEffect(() => {
    if (node) {
      setConditions(node.conditions || []);
    }
  }, [node]);

  const handleAddCondition = () => {
    setConditions([...conditions, { type: 'context', key: '', op: 'exists' }]);
  };

  const handleRemoveCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index));
  };

  const handleUpdateCondition = (index: number, updates: Partial<ConditionModel>) => {
    setConditions(conditions.map((c, i) => i === index ? { ...c, ...updates } : c));
  };

  if (!isOpen || !node) return null;

  return (
    <div className="condition-modal-backdrop" onClick={onClose}>
      <div className="condition-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Edit Conditions: {node.template_name}</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="conditions-info">
          <p>Conditions determine when this node is included in the prompt. All conditions must be met (AND logic).</p>
        </div>

        <div className="conditions-list">
          {conditions.length === 0 ? (
            <div className="no-conditions">
              No conditions - node always included when enabled
            </div>
          ) : (
            conditions.map((cond, index) => (
              <div key={index} className="condition-row">
                <select
                  value={cond.type}
                  onChange={(e) => handleUpdateCondition(index, { type: e.target.value })}
                  className="condition-type"
                >
                  <option value="context">Context</option>
                  <option value="time">Time</option>
                  <option value="rhythm">Rhythm</option>
                  <option value="model">Model</option>
                  <option value="always">Always</option>
                  <option value="never">Never</option>
                </select>

                {cond.type === 'context' && (
                  <>
                    <input
                      type="text"
                      placeholder="key (e.g., has_memories)"
                      value={cond.key || ''}
                      onChange={(e) => handleUpdateCondition(index, { key: e.target.value })}
                      className="condition-key"
                    />
                    <select
                      value={cond.op}
                      onChange={(e) => handleUpdateCondition(index, { op: e.target.value })}
                      className="condition-op"
                    >
                      <option value="exists">exists</option>
                      <option value="not_exists">not exists</option>
                      <option value="eq">equals</option>
                      <option value="neq">not equals</option>
                      <option value="gt">greater than</option>
                      <option value="gte">greater or equal</option>
                      <option value="lt">less than</option>
                      <option value="lte">less or equal</option>
                    </select>
                    {!['exists', 'not_exists'].includes(cond.op) && (
                      <input
                        type="text"
                        placeholder="value"
                        value={String(cond.value || '')}
                        onChange={(e) => handleUpdateCondition(index, { value: e.target.value })}
                        className="condition-value"
                      />
                    )}
                  </>
                )}

                {cond.type === 'time' && (
                  <>
                    <input
                      type="time"
                      value={cond.start || ''}
                      onChange={(e) => handleUpdateCondition(index, { start: e.target.value })}
                      className="condition-time"
                    />
                    <span>to</span>
                    <input
                      type="time"
                      value={cond.end || ''}
                      onChange={(e) => handleUpdateCondition(index, { end: e.target.value })}
                      className="condition-time"
                    />
                  </>
                )}

                {cond.type === 'rhythm' && (
                  <select
                    value={cond.phase || ''}
                    onChange={(e) => handleUpdateCondition(index, { phase: e.target.value })}
                    className="condition-phase"
                  >
                    <option value="">Select phase...</option>
                    <option value="morning">Morning</option>
                    <option value="afternoon">Afternoon</option>
                    <option value="evening">Evening</option>
                    <option value="night">Night</option>
                  </select>
                )}

                {cond.type === 'model' && (
                  <>
                    <input
                      type="text"
                      placeholder="model pattern"
                      value={cond.key || ''}
                      onChange={(e) => handleUpdateCondition(index, { key: e.target.value })}
                      className="condition-key"
                    />
                    <select
                      value={cond.op}
                      onChange={(e) => handleUpdateCondition(index, { op: e.target.value })}
                      className="condition-op"
                    >
                      <option value="eq">equals</option>
                      <option value="contains">contains</option>
                    </select>
                  </>
                )}

                <button
                  className="remove-condition-btn"
                  onClick={() => handleRemoveCondition(index)}
                  title="Remove condition"
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>

        <button className="add-condition-btn" onClick={handleAddCondition}>
          + Add Condition
        </button>

        <div className="modal-actions">
          <button className="cancel-btn" onClick={onClose}>Cancel</button>
          <button className="save-btn" onClick={() => onSave(conditions)}>Save Conditions</button>
        </div>
      </div>
    </div>
  );
}

/**
 * PreviewModal - Reusable modal for previewing assembled prompt with memory retrieval testing
 */
interface PreviewModalProps {
  preview: PreviewResponse | null;
  isOpen: boolean;
  onClose: () => void;
  chainId: string | null;
  daemonName?: string;
  onRefresh: (testMessage?: string, conversationId?: string) => Promise<void>;
  conversations?: Array<{ id: string; title: string }>;
  loadingRefresh?: boolean;
}

function PreviewModal({
  preview,
  isOpen,
  onClose,
  chainId: _chainId,
  daemonName: _daemonName,
  onRefresh,
  conversations = [],
  loadingRefresh = false,
}: PreviewModalProps) {
  // Note: chainId and daemonName reserved for future use (e.g., refresh with different daemon)
  void _chainId;
  void _daemonName;
  const [testMessage, setTestMessage] = useState('');
  const [selectedConversation, setSelectedConversation] = useState('');
  const [showContextDetails, setShowContextDetails] = useState(false);

  if (!isOpen || !preview) return null;

  const handleRetrieve = async () => {
    await onRefresh(testMessage || undefined, selectedConversation || undefined);
  };

  const totalContextChars = preview.context_sections
    ? Object.values(preview.context_sections).reduce((sum, s) => sum + s.char_count, 0)
    : 0;

  return (
    <div className="preview-modal-backdrop" onClick={onClose}>
      <div className="preview-modal preview-modal-large" onClick={(e) => e.stopPropagation()}>
        <div className="preview-header">
          <h3>Prompt Preview: {preview.chain_name}</h3>
          <div className="preview-meta">
            <span className="token-estimate">~{preview.token_estimate} tokens</span>
            <span className="section-count">{preview.included_nodes.length} nodes included</span>
            {preview.excluded_nodes.length > 0 && (
              <span className="excluded-count">{preview.excluded_nodes.length} excluded</span>
            )}
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        {/* Memory Retrieval Test Section */}
        <div className="preview-test-section">
          <h4>Test Memory Retrieval</h4>
          <div className="test-controls">
            <div className="test-input-group">
              <label>Test Message:</label>
              <input
                type="text"
                value={testMessage}
                onChange={(e) => setTestMessage(e.target.value)}
                placeholder="Enter a message to test memory retrieval..."
                className="test-message-input"
              />
            </div>
            <div className="test-input-group">
              <label>Conversation Context:</label>
              <select
                value={selectedConversation}
                onChange={(e) => setSelectedConversation(e.target.value)}
                className="conversation-selector"
              >
                <option value="">-- No conversation context --</option>
                {conversations.map((conv) => (
                  <option key={conv.id} value={conv.id}>
                    {conv.title || conv.id.slice(0, 8)}
                  </option>
                ))}
              </select>
            </div>
            <button
              className="retrieve-btn"
              onClick={handleRetrieve}
              disabled={loadingRefresh || !testMessage}
            >
              {loadingRefresh ? 'Retrieving...' : 'Retrieve Context'}
            </button>
          </div>

          {/* Context Sections Summary */}
          {preview.context_sections && totalContextChars > 0 && (
            <div className="context-summary">
              <div
                className="context-summary-header"
                onClick={() => setShowContextDetails(!showContextDetails)}
              >
                <span>Memory Context: {totalContextChars.toLocaleString()} chars retrieved</span>
                <span className="toggle-icon">{showContextDetails ? '▼' : '▶'}</span>
              </div>
              {showContextDetails && (
                <div className="context-details">
                  {Object.entries(preview.context_sections).map(([key, section]) => (
                    <div
                      key={key}
                      className={`context-item ${section.enabled ? 'enabled' : 'disabled'}`}
                    >
                      <span className="context-name">{section.name}</span>
                      <span className="context-chars">
                        {section.enabled ? `${section.char_count.toLocaleString()} chars` : 'empty'}
                      </span>
                      {section.content && (
                        <details className="context-content-details">
                          <summary>View content</summary>
                          <pre className="context-content-preview">{section.content}</pre>
                        </details>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {preview.warnings.length > 0 && (
          <div className="preview-warnings">
            {preview.warnings.map((w, i) => (
              <div key={i} className="warning">⚠️ {w}</div>
            ))}
          </div>
        )}

        <div className="preview-sections">
          <div className="included-nodes">
            <h4>Included Nodes:</h4>
            <div className="section-tags">
              {preview.included_nodes.map((slug) => (
                <span key={slug} className="section-tag included">{slug}</span>
              ))}
            </div>
          </div>
          {preview.excluded_nodes.length > 0 && (
            <div className="excluded-nodes">
              <h4>Excluded (conditions not met):</h4>
              <div className="section-tags">
                {preview.excluded_nodes.map((slug) => (
                  <span key={slug} className="section-tag excluded">{slug}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="preview-content">
          <pre>{preview.full_text}</pre>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function Architecture() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<TabId>(
    (searchParams.get('tab') as TabId) || 'prompts'
  );
  const { currentDaemon } = useDaemon();

  // Chain state
  const [chains, setChains] = useState<ChainResponse[]>([]);
  const [selectedChain, setSelectedChain] = useState<ChainDetailResponse | null>(null);
  const [templates, setTemplates] = useState<NodeTemplateResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // UI state
  const [showTemplateDrawer, setShowTemplateDrawer] = useState(false);
  const [editingNode, setEditingNode] = useState<ChainNodeResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Conversations for preview context selector
  const [conversations, setConversations] = useState<Array<{ id: string; title: string }>>([]);

  // Track pending operations for optimistic updates
  const pendingOps = useRef(new Set<string>());

  const handleTabChange = (tabId: TabId) => {
    const tab = tabs.find(t => t.id === tabId);
    if (tab?.disabled) return;
    setActiveTab(tabId);
    setSearchParams({ tab: tabId });
  };

  // Fetch chains and templates
  const fetchData = useCallback(async () => {
    if (!currentDaemon?.id) return;
    setLoading(true);
    setError(null);
    try {
      const [chainsRes, templatesRes] = await Promise.all([
        chainApi.listChains(currentDaemon.id),
        chainApi.listTemplates(),
      ]);
      setChains(chainsRes.data);
      setTemplates(templatesRes.data);

      // Select active chain by default
      const activeChain = chainsRes.data.find((c: ChainResponse) => c.is_active);
      if (activeChain && !selectedChain) {
        const { data } = await chainApi.getChain(activeChain.id);
        setSelectedChain(data);
      }
    } catch (e) {
      console.error('Failed to fetch data:', e);
      setError('Failed to load chain configurations');
    } finally {
      setLoading(false);
    }
  }, [currentDaemon?.id, selectedChain]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch conversations for preview context selector
  useEffect(() => {
    const fetchConversations = async () => {
      try {
        const { data } = await conversationsApi.getAll({ limit: 50 });
        setConversations(
          (data.conversations || []).map((c: { id: string; title?: string }) => ({
            id: c.id,
            title: c.title || `Conversation ${c.id.slice(0, 8)}`,
          }))
        );
      } catch (e) {
        console.error('Failed to fetch conversations:', e);
      }
    };
    fetchConversations();
  }, []);

  // Handle chain selection
  const handleSelectChain = async (chain: ChainResponse) => {
    try {
      const { data } = await chainApi.getChain(chain.id);
      setSelectedChain(data);
      setPreview(null);
    } catch (e) {
      console.error('Failed to load chain:', e);
      setError('Failed to load chain details');
    }
  };

  // Activate chain
  const handleActivate = async (chainId: string) => {
    try {
      await chainApi.activateChain(chainId);
      await fetchData();
    } catch (e) {
      console.error('Failed to activate:', e);
      setError('Failed to activate chain');
    }
  };

  // Duplicate chain
  const handleDuplicate = async (chainId: string) => {
    const name = prompt('Name for the new chain:');
    if (!name) return;
    try {
      await chainApi.duplicateChain(chainId, name);
      await fetchData();
    } catch (e) {
      console.error('Failed to duplicate:', e);
      setError('Failed to duplicate chain');
    }
  };

  // Delete chain
  const handleDelete = async (chainId: string) => {
    if (!confirm('Delete this chain?')) return;
    try {
      await chainApi.deleteChain(chainId);
      if (selectedChain?.id === chainId) {
        setSelectedChain(null);
      }
      await fetchData();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to delete chain');
    }
  };

  // Create new chain
  const handleCreate = async () => {
    if (!currentDaemon?.id) return;
    const name = prompt('Name for the new chain:');
    if (!name) return;
    try {
      const { data } = await chainApi.createChain(currentDaemon.id, { name });
      setSelectedChain(data);
      await fetchData();
    } catch (e) {
      console.error('Failed to create chain:', e);
      setError('Failed to create chain');
    }
  };

  // Reorder nodes
  const handleReorderNodes = async (nodeIds: string[]) => {
    if (!selectedChain || selectedChain.is_default) return;
    const opId = `reorder-${Date.now()}`;
    pendingOps.current.add(opId);
    try {
      await chainApi.reorderNodes(selectedChain.id, nodeIds);
      // Refresh chain data
      const { data } = await chainApi.getChain(selectedChain.id);
      setSelectedChain(data);
    } catch (e) {
      console.error('Failed to reorder:', e);
      setError('Failed to reorder nodes');
    } finally {
      pendingOps.current.delete(opId);
    }
  };

  // Toggle node enabled
  const handleToggleEnabled = async (nodeId: string, enabled: boolean) => {
    if (!selectedChain || selectedChain.is_default) return;
    try {
      await chainApi.updateNode(selectedChain.id, nodeId, { enabled });
      const { data } = await chainApi.getChain(selectedChain.id);
      setSelectedChain(data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to update node');
    }
  };

  // Remove node
  const handleRemoveNode = async (nodeId: string) => {
    if (!selectedChain || selectedChain.is_default) return;
    if (!confirm('Remove this node from the chain?')) return;
    try {
      await chainApi.removeNode(selectedChain.id, nodeId);
      const { data } = await chainApi.getChain(selectedChain.id);
      setSelectedChain(data);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to remove node');
    }
  };

  // Add template
  const handleAddTemplate = async (slug: string) => {
    if (!selectedChain || selectedChain.is_default) return;
    try {
      await chainApi.addNode(selectedChain.id, { template_slug: slug });
      const { data } = await chainApi.getChain(selectedChain.id);
      setSelectedChain(data);
      setShowTemplateDrawer(false);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to add node');
    }
  };

  // Save conditions
  const handleSaveConditions = async (conditions: ConditionModel[]) => {
    if (!selectedChain || !editingNode || selectedChain.is_default) return;
    try {
      await chainApi.updateNode(selectedChain.id, editingNode.id, { conditions });
      const { data } = await chainApi.getChain(selectedChain.id);
      setSelectedChain(data);
      setEditingNode(null);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      setError(err.response?.data?.detail || 'Failed to update conditions');
    }
  };

  // Load preview (optionally with test message and conversation context)
  const handlePreview = async (testMessage?: string, conversationId?: string) => {
    if (!selectedChain) return;
    setLoadingPreview(true);
    try {
      const { data } = await chainApi.previewChain(selectedChain.id, {
        daemon_name: currentDaemon?.name,
        test_message: testMessage,
        conversation_id: conversationId,
      });
      setPreview(data);
      setShowPreview(true);
    } catch (e) {
      console.error('Failed to load preview:', e);
      setError('Failed to load preview');
    } finally {
      setLoadingPreview(false);
    }
  };

  // Calculate totals
  const totalTokens = selectedChain?.nodes
    .filter(n => n.enabled)
    .reduce((sum, n) => sum + (n.token_estimate || 0), 0) || 0;

  const existingTemplateIds = selectedChain?.nodes.map(n => n.template_id) || [];

  return (
    <div className="architecture-page">
      <header className="page-header">
        <h1>Architecture</h1>
        <p className="subtitle">System prompts, global state, and orchestration</p>
      </header>

      <nav className="architecture-tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`arch-tab ${activeTab === tab.id ? 'active' : ''} ${tab.disabled ? 'disabled' : ''}`}
            onClick={() => handleTabChange(tab.id)}
            disabled={tab.disabled}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.disabled && <span className="coming-soon">Soon</span>}
          </button>
        ))}
      </nav>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="architecture-content">
        {activeTab === 'prompts' && (
          <div className="prompts-layout">
            <ChainSidebar
              chains={chains}
              selectedId={selectedChain?.id || null}
              loading={loading}
              onSelect={handleSelectChain}
              onActivate={handleActivate}
              onDuplicate={handleDuplicate}
              onDelete={handleDelete}
              onCreate={handleCreate}
            />

            <main className="config-editor chain-editor">
              {selectedChain ? (
                <>
                  <div className="editor-header">
                    <div className="editor-title">
                      <h2>{selectedChain.name}</h2>
                      {selectedChain.description && (
                        <p className="config-description">{selectedChain.description}</p>
                      )}
                      <div className="chain-stats">
                        <span className="stat">{selectedChain.nodes.length} nodes</span>
                        <span className="stat">~{totalTokens} tokens</span>
                      </div>
                    </div>
                    <div className="editor-actions">
                      {!selectedChain.is_default && (
                        <button
                          className="add-node-btn"
                          onClick={() => setShowTemplateDrawer(true)}
                        >
                          + Add Node
                        </button>
                      )}
                      <button
                        className="preview-btn"
                        onClick={() => handlePreview()}
                        disabled={loadingPreview}
                      >
                        {loadingPreview ? 'Loading...' : 'Preview Prompt'}
                      </button>
                    </div>
                  </div>

                  {selectedChain.is_default && (
                    <div className="info-banner">
                      Default chains cannot be edited. Use "Duplicate" to create an editable copy.
                    </div>
                  )}

                  <NodeList
                    nodes={selectedChain.nodes}
                    isDefault={selectedChain.is_default}
                    onReorder={handleReorderNodes}
                    onToggleEnabled={handleToggleEnabled}
                    onEditConditions={(node) => setEditingNode(node)}
                    onRemoveNode={handleRemoveNode}
                  />
                </>
              ) : (
                <div className="no-selection">
                  <p>Select a chain from the sidebar to edit</p>
                </div>
              )}
            </main>
          </div>
        )}

        {activeTab === 'global-state' && (
          <div className="coming-soon-panel">
            <h2>Global State</h2>
            <p>Persistent emotional and cognitive state that spans conversations.</p>
            <p className="future-note">Coming in a future update.</p>
          </div>
        )}

        {activeTab === 'orchestration' && (
          <div className="coming-soon-panel">
            <h2>Orchestration</h2>
            <p>Local model routing and automatic mode selection.</p>
            <p className="future-note">Coming in a future update.</p>
          </div>
        )}
      </div>

      {/* Template Drawer */}
      <TemplateDrawer
        templates={templates}
        existingTemplateIds={existingTemplateIds}
        isOpen={showTemplateDrawer}
        onClose={() => setShowTemplateDrawer(false)}
        onAddTemplate={handleAddTemplate}
      />

      {/* Condition Editor Modal */}
      <ConditionEditorModal
        node={editingNode}
        isOpen={!!editingNode}
        onClose={() => setEditingNode(null)}
        onSave={handleSaveConditions}
      />

      {/* Preview Modal */}
      <PreviewModal
        preview={preview}
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        chainId={selectedChain?.id || null}
        daemonName={currentDaemon?.name}
        onRefresh={handlePreview}
        conversations={conversations}
        loadingRefresh={loadingPreview}
      />
    </div>
  );
}
