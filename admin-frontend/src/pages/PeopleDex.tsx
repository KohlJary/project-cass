import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchPeopleDexStats,
  fetchPeopleDexEntities,
  fetchPeopleDexEntity,
  createPeopleDexEntity,
  deletePeopleDexEntity,
  addPeopleDexAttribute,
  deletePeopleDexAttribute,
  addPeopleDexRelationship,
  deletePeopleDexRelationship,
} from '../api/graphql';
import './PeopleDex.css';

type ModalType = 'create-entity' | 'add-attribute' | 'add-relationship' | null;
type DetailTab = 'overview' | 'facts' | 'cass-view' | 'history';

const ENTITY_TYPES = ['person', 'organization', 'team', 'daemon'];
const REALMS = ['meatspace', 'wonderland'];
const ATTRIBUTE_TYPES = [
  'name', 'birthday', 'pronoun', 'email', 'phone',
  'handle', 'role', 'bio', 'note', 'location'
];
const RELATIONSHIP_TYPES = [
  'partner', 'spouse', 'parent', 'child', 'sibling',
  'friend', 'colleague', 'member_of', 'leads', 'reports_to', 'knows'
];

export function PeopleDex() {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string>('');
  const [filterRealm, setFilterRealm] = useState<string>('');
  const [activeModal, setActiveModal] = useState<ModalType>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');

  // Form states
  const [newEntityName, setNewEntityName] = useState('');
  const [newEntityType, setNewEntityType] = useState('person');
  const [newEntityRealm, setNewEntityRealm] = useState('meatspace');
  const [newAttrType, setNewAttrType] = useState('name');
  const [newAttrValue, setNewAttrValue] = useState('');
  const [newAttrKey, setNewAttrKey] = useState('');
  const [newRelType, setNewRelType] = useState('knows');
  const [newRelTargetId, setNewRelTargetId] = useState('');

  const queryClient = useQueryClient();

  // Queries
  const { data: statsData } = useQuery({
    queryKey: ['peopledex-stats'],
    queryFn: fetchPeopleDexStats,
  });

  const { data: entitiesData, isLoading: entitiesLoading } = useQuery({
    queryKey: ['peopledex-entities', filterType, filterRealm, searchQuery],
    queryFn: () => fetchPeopleDexEntities({
      entityType: filterType || undefined,
      realm: filterRealm || undefined,
      search: searchQuery || undefined,
      limit: 100,
    }),
  });

  const { data: profileData } = useQuery({
    queryKey: ['peopledex-entity', selectedEntityId],
    queryFn: () => selectedEntityId ? fetchPeopleDexEntity(selectedEntityId) : null,
    enabled: !!selectedEntityId,
  });

  // For relationship target selection
  const { data: allEntitiesData } = useQuery({
    queryKey: ['peopledex-all-entities'],
    queryFn: () => fetchPeopleDexEntities({ limit: 500 }),
  });

  // Mutations
  const createEntityMutation = useMutation({
    mutationFn: createPeopleDexEntity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entities'] });
      queryClient.invalidateQueries({ queryKey: ['peopledex-stats'] });
      setActiveModal(null);
      setNewEntityName('');
    },
  });

  const deleteEntityMutation = useMutation({
    mutationFn: deletePeopleDexEntity,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entities'] });
      queryClient.invalidateQueries({ queryKey: ['peopledex-stats'] });
      setSelectedEntityId(null);
    },
  });

  const addAttributeMutation = useMutation({
    mutationFn: ({ entityId, input }: { entityId: string; input: { attributeType: string; value: string; attributeKey?: string } }) =>
      addPeopleDexAttribute(entityId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entity', selectedEntityId] });
      setActiveModal(null);
      setNewAttrValue('');
      setNewAttrKey('');
    },
  });

  const deleteAttributeMutation = useMutation({
    mutationFn: deletePeopleDexAttribute,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entity', selectedEntityId] });
    },
  });

  const addRelationshipMutation = useMutation({
    mutationFn: addPeopleDexRelationship,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entity', selectedEntityId] });
      setActiveModal(null);
      setNewRelTargetId('');
    },
  });

  const deleteRelationshipMutation = useMutation({
    mutationFn: deletePeopleDexRelationship,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['peopledex-entity', selectedEntityId] });
    },
  });

  const stats = statsData?.peopledexStats;
  const entities = entitiesData?.peopledexEntities || [];
  const profile = profileData?.peopledexEntity;
  const allEntities = allEntitiesData?.peopledexEntities || [];

  const handleCreateEntity = () => {
    if (!newEntityName.trim()) return;
    createEntityMutation.mutate({
      entityType: newEntityType,
      primaryName: newEntityName.trim(),
      realm: newEntityRealm,
    });
  };

  const handleAddAttribute = () => {
    if (!selectedEntityId || !newAttrValue.trim()) return;
    addAttributeMutation.mutate({
      entityId: selectedEntityId,
      input: {
        attributeType: newAttrType,
        value: newAttrValue.trim(),
        attributeKey: newAttrKey || undefined,
      },
    });
  };

  const handleAddRelationship = () => {
    if (!selectedEntityId || !newRelTargetId) return;
    addRelationshipMutation.mutate({
      fromEntityId: selectedEntityId,
      toEntityId: newRelTargetId,
      relationshipType: newRelType,
    });
  };

  return (
    <div className="peopledex-page">
      {/* Header */}
      <div className="peopledex-header">
        <h1>PeopleDex</h1>
        <div className="header-actions">
          <button className="btn btn-primary" onClick={() => setActiveModal('create-entity')}>
            + New Entity
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="peopledex-stats">
        <div className="stat-card">
          <h3>Total Entities</h3>
          <div className="stat-value">{stats?.totalEntities || 0}</div>
        </div>
        <div className="stat-card">
          <h3>By Type</h3>
          <div className="stat-breakdown">
            {stats?.byType && Object.entries(stats.byType).map(([type, count]) => (
              <span key={type} className={`stat-tag ${type}`}>
                {type}: {count}
              </span>
            ))}
          </div>
        </div>
        <div className="stat-card">
          <h3>By Realm</h3>
          <div className="stat-breakdown">
            {stats?.byRealm && Object.entries(stats.byRealm).map(([realm, count]) => (
              <span key={realm} className={`stat-tag ${realm}`}>
                {realm}: {count}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Main Layout */}
      <div className="peopledex-main">
        {/* Left Panel - Entity List */}
        <div className="entity-list-panel">
          <div className="list-controls">
            <input
              type="text"
              className="search-input"
              placeholder="Search entities..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <div className="filter-row">
              <select
                className="filter-select"
                value={filterType}
                onChange={(e) => setFilterType(e.target.value)}
              >
                <option value="">All Types</option>
                {ENTITY_TYPES.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                className="filter-select"
                value={filterRealm}
                onChange={(e) => setFilterRealm(e.target.value)}
              >
                <option value="">All Realms</option>
                {REALMS.map(r => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="entity-list">
            {entitiesLoading ? (
              <div className="loading">Loading...</div>
            ) : entities.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">📇</div>
                <h3>No entities found</h3>
                <p>Create one to get started</p>
              </div>
            ) : (
              entities.map((entity) => (
                <div
                  key={entity.id}
                  className={`entity-item ${selectedEntityId === entity.id ? 'selected' : ''}`}
                  onClick={() => setSelectedEntityId(entity.id)}
                >
                  <div className="entity-name">{entity.primaryName}</div>
                  <div className="entity-meta">
                    <span className={`entity-type-badge ${entity.entityType}`}>
                      {entity.entityType}
                    </span>
                    <span className={`realm-badge ${entity.realm}`}>
                      {entity.realm}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center Panel - Graph/Overview */}
        <div className="graph-panel">
          <h2>Relationship Graph</h2>
          <div className="graph-placeholder">
            {profile ? (
              <div style={{ textAlign: 'left', width: '100%', padding: '20px' }}>
                <h3 style={{ color: '#e0e0e0', marginBottom: '16px' }}>
                  {profile.entity.primaryName}'s Network
                </h3>
                <p style={{ color: '#888', marginBottom: '12px' }}>
                  {profile.relationships.length} relationships
                </p>
                {profile.relationships.map((rel) => (
                  <div key={rel.relationshipId} style={{
                    padding: '8px 12px',
                    background: '#1a1a1a',
                    borderRadius: '6px',
                    marginBottom: '8px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px'
                  }}>
                    <span style={{ color: '#4ecdc4' }}>{profile.entity.primaryName}</span>
                    <span style={{ color: '#666' }}>{rel.direction === 'to' ? '→' : '←'}</span>
                    <span style={{
                      color: '#888',
                      fontSize: '12px',
                      padding: '2px 8px',
                      background: '#252525',
                      borderRadius: '4px'
                    }}>{rel.relationshipType}</span>
                    <span style={{ color: '#666' }}>{rel.direction === 'to' ? '→' : '←'}</span>
                    <span
                      style={{ color: '#4ecdc4', cursor: 'pointer' }}
                      onClick={() => setSelectedEntityId(rel.relatedEntity.id)}
                    >
                      {rel.relatedEntity.primaryName}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              'Select an entity to view relationships'
            )}
          </div>
        </div>

        {/* Right Panel - Entity Detail */}
        <div className={`detail-panel ${profile ? 'active' : ''}`}>
          {profile ? (
            <>
              <div className="detail-header">
                <div className="detail-title">
                  <h2>{profile.entity.primaryName}</h2>
                  <div className="detail-badges">
                    <span className={`entity-type-badge ${profile.entity.entityType}`}>
                      {profile.entity.entityType}
                    </span>
                    <span className={`realm-badge ${profile.entity.realm}`}>
                      {profile.entity.realm}
                    </span>
                  </div>
                </div>
                <div className="detail-actions">
                  <button
                    className="btn btn-danger"
                    onClick={() => {
                      if (confirm('Delete this entity?')) {
                        deleteEntityMutation.mutate(profile.entity.id);
                      }
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>

              {/* Tab Navigation */}
              <div className="detail-tabs">
                <button
                  className={`detail-tab ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab('overview')}
                >
                  Overview
                </button>
                <button
                  className={`detail-tab ${activeTab === 'facts' ? 'active' : ''}`}
                  onClick={() => setActiveTab('facts')}
                >
                  Facts {profile.facts?.length > 0 && <span className="tab-count">{profile.facts.length}</span>}
                </button>
                <button
                  className={`detail-tab ${activeTab === 'cass-view' ? 'active' : ''}`}
                  onClick={() => setActiveTab('cass-view')}
                >
                  Cass's View {profile.observations?.length > 0 && <span className="tab-count">{profile.observations.length}</span>}
                </button>
                <button
                  className={`detail-tab ${activeTab === 'history' ? 'active' : ''}`}
                  onClick={() => setActiveTab('history')}
                >
                  History {profile.moments?.length > 0 && <span className="tab-count">{profile.moments.length}</span>}
                </button>
              </div>

              <div className="detail-content">
                {/* Overview Tab */}
                {activeTab === 'overview' && (
                  <>
                    {/* Attributes Section */}
                    <div className="detail-section">
                      <h3>
                        Attributes
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setActiveModal('add-attribute')}
                        >
                          + Add
                        </button>
                      </h3>
                      {profile.attributes.length === 0 ? (
                        <p style={{ color: '#666', fontSize: '13px' }}>No attributes yet</p>
                      ) : (
                        <div className="attribute-list">
                          {profile.attributes.map((attr) => (
                            <div key={attr.id} className="attribute-item">
                              <div className="attribute-info">
                                <div className="attribute-type">
                                  {attr.attributeType}
                                  {attr.attributeKey && <span className="attribute-key"> ({attr.attributeKey})</span>}
                                  {attr.isPrimary && <span style={{ color: '#4ecdc4' }}> ★</span>}
                                </div>
                                <div className="attribute-value">{attr.value}</div>
                              </div>
                              <div className="attribute-actions">
                                <button
                                  className="btn btn-danger btn-sm"
                                  onClick={() => deleteAttributeMutation.mutate(attr.id)}
                                >
                                  ×
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Relationships Section */}
                    <div className="detail-section">
                      <h3>
                        Relationships
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setActiveModal('add-relationship')}
                        >
                          + Add
                        </button>
                      </h3>
                      {profile.relationships.length === 0 ? (
                        <p style={{ color: '#666', fontSize: '13px' }}>No relationships yet</p>
                      ) : (
                        <div className="relationship-list">
                          {profile.relationships.map((rel) => (
                            <div key={rel.relationshipId} className="relationship-item">
                              <span className="relationship-arrow">
                                {rel.direction === 'to' ? '→' : '←'}
                              </span>
                              <span className="relationship-type">{rel.relationshipType}</span>
                              <span
                                className="relationship-entity"
                                onClick={() => setSelectedEntityId(rel.relatedEntity.id)}
                              >
                                {rel.relatedEntity.primaryName}
                              </span>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  deleteRelationshipMutation.mutate(rel.relationshipId);
                                }}
                              >
                                ×
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Relationship Meta (if exists) */}
                    {profile.relationshipMeta && (
                      <div className="detail-section">
                        <h3>Relationship with Cass</h3>
                        <div className="relationship-meta">
                          {profile.relationshipMeta.relationshipType && (
                            <div className="meta-item">
                              <span className="meta-label">Type:</span>
                              <span className="meta-value relationship-type-badge">
                                {profile.relationshipMeta.relationshipType}
                              </span>
                            </div>
                          )}
                          {profile.relationshipMeta.currentPhase && (
                            <div className="meta-item">
                              <span className="meta-label">Phase:</span>
                              <span className="meta-value">{profile.relationshipMeta.currentPhase}</span>
                            </div>
                          )}
                          {profile.relationshipMeta.isFoundational && (
                            <div className="meta-item">
                              <span className="meta-value foundational-badge">⭐ Foundational Relationship</span>
                            </div>
                          )}
                          {profile.relationshipMeta.formationDate && (
                            <div className="meta-item">
                              <span className="meta-label">Since:</span>
                              <span className="meta-value">{profile.relationshipMeta.formationDate}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Metadata */}
                    <div className="detail-section">
                      <h3>Metadata</h3>
                      <div style={{ color: '#666', fontSize: '12px' }}>
                        <p>ID: {profile.entity.id}</p>
                        {profile.entity.userId && <p>User ID: {profile.entity.userId}</p>}
                        {profile.entity.npcId && <p>NPC ID: {profile.entity.npcId}</p>}
                        <p>Created: {new Date(profile.entity.createdAt).toLocaleString()}</p>
                        <p>Updated: {new Date(profile.entity.updatedAt).toLocaleString()}</p>
                      </div>
                    </div>
                  </>
                )}

                {/* Facts Tab */}
                {activeTab === 'facts' && (
                  <div className="detail-section">
                    <h3>Biographical Facts</h3>
                    {!profile.facts || profile.facts.length === 0 ? (
                      <p style={{ color: '#666', fontSize: '13px' }}>No facts recorded yet</p>
                    ) : (
                      <div className="facts-list">
                        {profile.facts.map((fact) => (
                          <div key={fact.id} className="fact-item">
                            <div className="fact-header">
                              <span className={`fact-type-badge ${fact.factType}`}>
                                {fact.factType}
                              </span>
                              {fact.isRecurring && <span className="recurring-badge">🔄 Recurring</span>}
                              {fact.verified && <span className="verified-badge">✓ Verified</span>}
                            </div>
                            <div className="fact-content">{fact.content}</div>
                            {fact.dateValue && (
                              <div className="fact-date">📅 {fact.dateValue}</div>
                            )}
                            <div className="fact-meta">
                              <span className="confidence">
                                Confidence: {Math.round(fact.confidence * 100)}%
                              </span>
                              <span className="source">Source: {fact.sourceType}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Cass's View Tab */}
                {activeTab === 'cass-view' && (
                  <>
                    {/* Observations */}
                    <div className="detail-section">
                      <h3>Observations</h3>
                      {!profile.observations || profile.observations.length === 0 ? (
                        <p style={{ color: '#666', fontSize: '13px' }}>No observations yet</p>
                      ) : (
                        <div className="observations-list">
                          {profile.observations.map((obs) => (
                            <div key={obs.id} className={`observation-item ${obs.status}`}>
                              <div className="observation-header">
                                <span className={`observation-type-badge ${obs.observationType}`}>
                                  {obs.observationType.replace(/_/g, ' ')}
                                </span>
                                <span className="confidence">
                                  {Math.round(obs.confidence * 100)}%
                                </span>
                              </div>
                              <div className="observation-content">{obs.content}</div>
                              {obs.resolution && (
                                <div className="observation-resolution">
                                  <span className="resolution-label">Resolution:</span> {obs.resolution}
                                </div>
                              )}
                              <div className="observation-meta">
                                {obs.validationCount > 0 && (
                                  <span>Validated {obs.validationCount}×</span>
                                )}
                                <span className="observation-date">
                                  {new Date(obs.createdAt).toLocaleDateString()}
                                </span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Patterns */}
                    {profile.patterns && profile.patterns.length > 0 && (
                      <div className="detail-section">
                        <h3>Relationship Patterns</h3>
                        <div className="patterns-list">
                          {profile.patterns.map((pattern) => (
                            <div key={pattern.id} className={`pattern-item ${pattern.valence || ''}`}>
                              <div className="pattern-header">
                                <span className={`pattern-type-badge ${pattern.patternType}`}>
                                  {pattern.patternType}
                                </span>
                                {pattern.name && <span className="pattern-name">{pattern.name}</span>}
                                {pattern.frequency && (
                                  <span className="pattern-frequency">{pattern.frequency}</span>
                                )}
                              </div>
                              <div className="pattern-content">{pattern.description}</div>
                              {pattern.patternType === 'shift' && (
                                <div className="pattern-shift">
                                  <span>{pattern.fromState}</span>
                                  <span className="shift-arrow">→</span>
                                  <span>{pattern.toState}</span>
                                  {pattern.catalyst && (
                                    <span className="catalyst">({pattern.catalyst})</span>
                                  )}
                                </div>
                              )}
                              {pattern.examples && pattern.examples.length > 0 && (
                                <div className="pattern-examples">
                                  <span className="examples-label">Examples:</span>
                                  <ul>
                                    {pattern.examples.map((ex, i) => (
                                      <li key={i}>{ex}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Mutual Shaping */}
                    {profile.mutualShaping && profile.mutualShaping.length > 0 && (
                      <div className="detail-section">
                        <h3>Mutual Shaping</h3>
                        <div className="shaping-list">
                          {profile.mutualShaping.map((shaping) => (
                            <div key={shaping.id} className={`shaping-item ${shaping.shapingType}`}>
                              <div className="shaping-type">
                                {shaping.shapingType === 'they_shape_me' && '↓ They shape me'}
                                {shaping.shapingType === 'i_shape_them' && '↑ I shape them'}
                                {shaping.shapingType === 'inherited_value' && '⟳ Inherited value'}
                              </div>
                              <div className="shaping-note">{shaping.note}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* History Tab */}
                {activeTab === 'history' && (
                  <div className="detail-section">
                    <h3>Shared Moments</h3>
                    {!profile.moments || profile.moments.length === 0 ? (
                      <p style={{ color: '#666', fontSize: '13px' }}>No moments recorded yet</p>
                    ) : (
                      <div className="moments-timeline">
                        {profile.moments.map((moment) => (
                          <div key={moment.id} className={`moment-item ${moment.category}`}>
                            <div className="moment-marker">
                              {moment.category === 'milestone' && '🏆'}
                              {moment.category === 'connection' && '💫'}
                              {moment.category === 'growth' && '🌱'}
                              {moment.category === 'challenge' && '⚡'}
                              {moment.category === 'ritual' && '🔮'}
                            </div>
                            <div className="moment-content">
                              <div className="moment-header">
                                <span className={`moment-category-badge ${moment.category}`}>
                                  {moment.category}
                                </span>
                                <span className="moment-date">
                                  {new Date(moment.timestamp).toLocaleDateString()}
                                </span>
                              </div>
                              <div className="moment-description">{moment.description}</div>
                              {moment.significance && (
                                <div className="moment-significance">
                                  <span className="significance-label">Significance:</span>
                                  {moment.significance}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">👤</div>
              <h3>No Entity Selected</h3>
              <p>Select an entity from the list to view details</p>
            </div>
          )}
        </div>
      </div>

      {/* Create Entity Modal */}
      {activeModal === 'create-entity' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Create New Entity</h2>
            <div className="modal-form">
              <div className="form-group">
                <label>Name</label>
                <input
                  type="text"
                  value={newEntityName}
                  onChange={(e) => setNewEntityName(e.target.value)}
                  placeholder="Enter name..."
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select value={newEntityType} onChange={(e) => setNewEntityType(e.target.value)}>
                  {ENTITY_TYPES.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Realm</label>
                <select value={newEntityRealm} onChange={(e) => setNewEntityRealm(e.target.value)}>
                  {REALMS.map(r => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateEntity}
                disabled={!newEntityName.trim()}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Attribute Modal */}
      {activeModal === 'add-attribute' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add Attribute</h2>
            <div className="modal-form">
              <div className="form-group">
                <label>Type</label>
                <select value={newAttrType} onChange={(e) => setNewAttrType(e.target.value)}>
                  {ATTRIBUTE_TYPES.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Value</label>
                <input
                  type="text"
                  value={newAttrValue}
                  onChange={(e) => setNewAttrValue(e.target.value)}
                  placeholder="Enter value..."
                  autoFocus
                />
              </div>
              {newAttrType === 'handle' && (
                <div className="form-group">
                  <label>Platform (e.g., twitter, github)</label>
                  <input
                    type="text"
                    value={newAttrKey}
                    onChange={(e) => setNewAttrKey(e.target.value)}
                    placeholder="twitter"
                  />
                </div>
              )}
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleAddAttribute}
                disabled={!newAttrValue.trim()}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Relationship Modal */}
      {activeModal === 'add-relationship' && (
        <div className="modal-overlay" onClick={() => setActiveModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Add Relationship</h2>
            <div className="modal-form">
              <div className="form-group">
                <label>Relationship Type</label>
                <select value={newRelType} onChange={(e) => setNewRelType(e.target.value)}>
                  {RELATIONSHIP_TYPES.map(t => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>To Entity</label>
                <select value={newRelTargetId} onChange={(e) => setNewRelTargetId(e.target.value)}>
                  <option value="">Select entity...</option>
                  {allEntities
                    .filter(e => e.id !== selectedEntityId)
                    .map(e => (
                      <option key={e.id} value={e.id}>
                        {e.primaryName} ({e.entityType})
                      </option>
                    ))
                  }
                </select>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleAddRelationship}
                disabled={!newRelTargetId}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
