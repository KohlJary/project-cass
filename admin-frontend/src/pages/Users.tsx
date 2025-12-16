import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi, conversationsApi } from '../api/client';
import './Users.css';

interface User {
  id: string;
  display_name: string;
  observation_count: number;
  created_at: string;
  is_admin: boolean;
  has_password: boolean;
  status: 'pending' | 'approved' | 'rejected';
}

interface PendingUser {
  id: string;
  display_name: string;
  email?: string;
  registration_reason?: string;
  created_at: string;
}

interface Observation {
  id: string;
  timestamp: string;
  observation: string;
  category?: string;
  confidence?: number;
  source_type?: string;
  source_journal_date?: string;
}

interface IdentityStatement {
  statement: string;
  confidence: number;
  source: string;
  first_noticed: string;
  last_affirmed: string;
  evidence: string[];
}

interface SharedMoment {
  id: string;
  timestamp: string;
  description: string;
  significance: string;
  category: string;
  conversation_id?: string;
}

interface GrowthObservation {
  id: string;
  timestamp: string;
  area: string;
  observation: string;
  direction: string;
  evidence?: string;
}

interface Contradiction {
  id: string;
  timestamp: string;
  aspect_a: string;
  aspect_b: string;
  context?: string;
  resolved: boolean;
  resolution?: string;
}

interface RelationalPattern {
  id: string;
  name: string;
  description: string;
  frequency: string;
  valence: string;
  first_noticed: string;
  examples: string[];
}

interface RelationshipShift {
  id: string;
  timestamp: string;
  description: string;
  from_state: string;
  to_state: string;
  catalyst?: string;
}

interface UserModel {
  user_id: string;
  updated_at: string;
  identity_statements: IdentityStatement[];
  values: string[];
  shared_history: SharedMoment[];
  growth_observations: GrowthObservation[];
  open_questions: string[];
  contradictions: Contradiction[];
  communication_style: {
    style: string;
    preferences: string[];
    effective_approaches: string[];
    avoid: string[];
  };
}

interface RelationshipModel {
  user_id: string;
  updated_at: string;
  formation_date: string;
  current_phase: string;
  is_foundational: boolean;
  patterns: RelationalPattern[];
  significant_shifts: RelationshipShift[];
  rituals: string[];
  how_they_shape_me: string[];
  how_i_shape_them: string[];
  inherited_values: string[];
  growth_areas: string[];
}

export function Users() {
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);
  const [rejectModalUser, setRejectModalUser] = useState<PendingUser | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.getAll().then((r) => r.data),
    retry: false,
  });

  const { data: pendingData } = useQuery({
    queryKey: ['pending-users'],
    queryFn: () => usersApi.getPending().then((r) => r.data),
    retry: false,
  });

  const pendingUsers = pendingData?.users as PendingUser[] | undefined;

  const approveMutation = useMutation({
    mutationFn: (userId: string) => usersApi.approveUser(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['pending-users'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      usersApi.rejectUser(userId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['pending-users'] });
      setRejectModalUser(null);
      setRejectReason('');
    },
  });

  const selectedUser = data?.users?.find((u: User) => u.id === selectedUserId);

  const { data: userDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['user-detail', selectedUserId],
    queryFn: () =>
      selectedUserId ? usersApi.getById(selectedUserId).then((r) => r.data) : null,
    enabled: !!selectedUserId,
    retry: false,
  });

  const { data: userConversations } = useQuery({
    queryKey: ['user-conversations', selectedUserId],
    queryFn: () =>
      selectedUserId
        ? conversationsApi.getAll({ user_id: selectedUserId, limit: 20 }).then((r) => r.data)
        : null,
    enabled: !!selectedUserId,
    retry: false,
  });

  const { data: userModelData } = useQuery({
    queryKey: ['user-model', selectedUserId],
    queryFn: () =>
      selectedUserId ? usersApi.getUserModel(selectedUserId).then((r) => r.data) : null,
    enabled: !!selectedUserId,
    retry: false,
  });

  const { data: relationshipData } = useQuery({
    queryKey: ['relationship-model', selectedUserId],
    queryFn: () =>
      selectedUserId ? usersApi.getRelationshipModel(selectedUserId).then((r) => r.data) : null,
    enabled: !!selectedUserId,
    retry: false,
  });

  return (
    <div className="users-page">
      <header className="page-header">
        <h1>Users</h1>
        <p className="subtitle">Manage user profiles and observations</p>
      </header>

      {/* Pending Approval Section */}
      {pendingUsers && pendingUsers.length > 0 && (
        <div className="pending-users-section">
          <div className="pending-header">
            <h2>Pending Approval ({pendingUsers.length})</h2>
          </div>
          <div className="pending-list">
            {pendingUsers.map((user) => (
              <div key={user.id} className="pending-user-item">
                <div className="pending-user-info">
                  <div className="pending-user-header">
                    <span className="pending-user-name">{user.display_name}</span>
                    {user.email && <span className="pending-user-email">{user.email}</span>}
                  </div>
                  <span className="pending-user-date">
                    Registered {new Date(user.created_at).toLocaleDateString()}
                  </span>
                  {user.registration_reason && (
                    <div className="pending-user-reason">
                      <span className="reason-label">Why they want to join:</span>
                      <p className="reason-text">{user.registration_reason}</p>
                    </div>
                  )}
                </div>
                <div className="pending-user-actions">
                  <button
                    className="approve-btn"
                    onClick={() => approveMutation.mutate(user.id)}
                    disabled={approveMutation.isPending}
                  >
                    Approve
                  </button>
                  <button
                    className="reject-btn"
                    onClick={() => setRejectModalUser(user)}
                    disabled={rejectMutation.isPending}
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {rejectModalUser && (
        <div className="modal-overlay" onClick={() => setRejectModalUser(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3>Reject User</h3>
            <p>Provide a reason for rejecting {rejectModalUser.display_name}'s registration.</p>
            <textarea
              placeholder="Reason for rejection..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
            />
            <div className="modal-actions">
              <button
                className="cancel-btn"
                onClick={() => {
                  setRejectModalUser(null);
                  setRejectReason('');
                }}
              >
                Cancel
              </button>
              <button
                className="reject-confirm-btn"
                onClick={() => rejectMutation.mutate({ userId: rejectModalUser.id, reason: rejectReason })}
                disabled={!rejectReason || rejectMutation.isPending}
              >
                {rejectMutation.isPending ? 'Rejecting...' : 'Reject User'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="users-layout">
        {/* User list */}
        <div className="users-list-panel">
          <div className="panel-header">
            <h2>All Users</h2>
            <span className="count">{data?.users?.length || 0}</span>
          </div>

          {isLoading ? (
            <div className="loading-state">Loading users...</div>
          ) : error ? (
            <div className="error-state">Failed to load users</div>
          ) : data?.users?.length > 0 ? (
            <div className="user-list">
              {data.users.map((user: User) => (
                <div
                  key={user.id}
                  className={`user-item ${selectedUserId === user.id ? 'selected' : ''}`}
                  onClick={() => setSelectedUserId(user.id)}
                >
                  <div className="user-avatar">
                    {user.display_name?.charAt(0).toUpperCase() || '@'}
                  </div>
                  <div className="user-info">
                    <div className="user-name">
                      {user.display_name}
                      {user.is_admin && <span className="admin-badge">Admin</span>}
                    </div>
                    <div className="user-meta">
                      <span className="obs-count">{user.observation_count} observations</span>
                      <span className="join-date">
                        Joined {new Date(user.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">No users found</div>
          )}
        </div>

        {/* User detail panel */}
        <div className="user-detail-panel">
          {selectedUserId ? (
            detailLoading ? (
              <div className="loading-state">Loading user details...</div>
            ) : userDetail ? (
              <UserDetailView
                profile={userDetail.profile}
                observations={userDetail.observations}
                conversations={userConversations?.conversations}
                userModel={userModelData?.user_model}
                relationshipModel={relationshipData?.relationship_model}
                isAdmin={selectedUser?.is_admin || false}
                hasPassword={selectedUser?.has_password || false}
                onRefresh={() => queryClient.invalidateQueries({ queryKey: ['users'] })}
              />
            ) : (
              <div className="error-state">Failed to load user</div>
            )
          ) : (
            <div className="empty-state">
              <div className="empty-icon">@</div>
              <p>Select a user to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function UserDetailView({
  profile,
  observations,
  conversations,
  userModel,
  relationshipModel,
  isAdmin,
  hasPassword,
  onRefresh,
}: {
  profile: any;
  observations: Observation[];
  conversations?: any[];
  userModel?: UserModel;
  relationshipModel?: RelationshipModel;
  isAdmin: boolean;
  hasPassword: boolean;
  onRefresh: () => void;
}) {
  const [activeTab, setActiveTab] = useState<'understanding' | 'relationship' | 'observations' | 'conversations' | 'profile'>('understanding');
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const toggleAdminMutation = useMutation({
    mutationFn: (newStatus: boolean) =>
      usersApi.setAdminStatus(profile.user_id, newStatus),
    onSuccess: () => onRefresh(),
  });

  const setPasswordMutation = useMutation({
    mutationFn: (password: string) =>
      usersApi.setPassword(profile.user_id, password),
    onSuccess: () => {
      setShowPasswordModal(false);
      setNewPassword('');
      onRefresh();
    },
    onError: () => setPasswordError('Failed to set password'),
  });

  // Group observations by category
  const observationsByCategory = observations?.reduce((acc: Record<string, Observation[]>, obs) => {
    const category = obs.category || 'uncategorized';
    if (!acc[category]) acc[category] = [];
    acc[category].push(obs);
    return acc;
  }, {}) || {};

  const categoryColors: Record<string, string> = {
    background: '#89ddff',
    communication_style: '#c792ea',
    relationship_dynamic: '#f78c6c',
    value: '#c3e88d',
    interest: '#ffcb6b',
    uncategorized: '#888',
  };

  return (
    <div className="user-detail">
      <div className="detail-header">
        <div className="user-avatar large">
          {profile?.display_name?.charAt(0).toUpperCase() || '@'}
        </div>
        <div className="user-headline">
          <h2>{profile?.display_name || 'Unknown User'}</h2>
          <p className="user-relationship">{profile?.relationship || 'user'}</p>
        </div>
        <div className="admin-controls">
          <label className="admin-toggle">
            <input
              type="checkbox"
              checked={isAdmin}
              onChange={(e) => toggleAdminMutation.mutate(e.target.checked)}
              disabled={toggleAdminMutation.isPending}
            />
            <span className="toggle-label">Admin Access</span>
          </label>
          {isAdmin && (
            <button
              className="set-password-btn"
              onClick={() => setShowPasswordModal(true)}
            >
              {hasPassword ? 'Change Password' : 'Set Password'}
            </button>
          )}
        </div>
      </div>

      {showPasswordModal && (
        <div className="password-modal">
          <div className="modal-content">
            <h3>Set Admin Password</h3>
            <p>Set a password for {profile?.display_name} to access the admin dashboard.</p>
            {passwordError && <div className="modal-error">{passwordError}</div>}
            <input
              type="password"
              placeholder="New password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus
            />
            <div className="modal-actions">
              <button
                className="cancel-btn"
                onClick={() => {
                  setShowPasswordModal(false);
                  setNewPassword('');
                  setPasswordError('');
                }}
              >
                Cancel
              </button>
              <button
                className="save-btn"
                onClick={() => setPasswordMutation.mutate(newPassword)}
                disabled={!newPassword || setPasswordMutation.isPending}
              >
                {setPasswordMutation.isPending ? 'Saving...' : 'Save Password'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="detail-tabs">
        <button
          className={`tab ${activeTab === 'understanding' ? 'active' : ''}`}
          onClick={() => setActiveTab('understanding')}
        >
          Understanding
          {userModel && <span className="tab-badge">{userModel.identity_statements?.length || 0}</span>}
        </button>
        <button
          className={`tab ${activeTab === 'relationship' ? 'active' : ''}`}
          onClick={() => setActiveTab('relationship')}
        >
          Relationship
          {relationshipModel?.is_foundational && <span className="foundational-badge">★</span>}
        </button>
        <button
          className={`tab ${activeTab === 'observations' ? 'active' : ''}`}
          onClick={() => setActiveTab('observations')}
        >
          Observations ({observations?.length || 0})
        </button>
        <button
          className={`tab ${activeTab === 'conversations' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversations')}
        >
          Conversations ({conversations?.length || 0})
        </button>
        <button
          className={`tab ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          Profile
        </button>
      </div>

      <div className="detail-content">
        {activeTab === 'understanding' && (
          <div className="understanding-view">
            {userModel ? (
              <>
                {/* Identity Statements */}
                <div className="model-section">
                  <h3 className="section-title">
                    <span className="section-icon">◇</span>
                    Who They Are
                  </h3>
                  {userModel.identity_statements?.length > 0 ? (
                    <div className="identity-list">
                      {userModel.identity_statements.map((stmt, i) => (
                        <div key={i} className="identity-item">
                          <p className="identity-statement">{stmt.statement}</p>
                          <div className="identity-meta">
                            <span className="confidence" style={{ opacity: stmt.confidence }}>
                              {(stmt.confidence * 100).toFixed(0)}% confidence
                            </span>
                            <span className="source">{stmt.source}</span>
                            {stmt.evidence?.length > 0 && (
                              <span className="evidence-count">{stmt.evidence.length} evidence</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state small">No identity understandings yet</div>
                  )}
                </div>

                {/* Values */}
                {userModel.values?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">♡</span>
                      Values
                    </h3>
                    <div className="values-list">
                      {userModel.values.map((value, i) => (
                        <span key={i} className="value-tag">{value}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Shared Moments */}
                {userModel.shared_history?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">★</span>
                      Shared Moments
                    </h3>
                    <div className="moments-list">
                      {userModel.shared_history.map((moment) => (
                        <div key={moment.id} className="moment-item">
                          <div className="moment-header">
                            <span className={`moment-category ${moment.category}`}>{moment.category}</span>
                            <span className="moment-date">{new Date(moment.timestamp).toLocaleDateString()}</span>
                          </div>
                          <p className="moment-description">{moment.description}</p>
                          <p className="moment-significance">{moment.significance}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Growth Observations */}
                {userModel.growth_observations?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">↑</span>
                      Growth Observations
                    </h3>
                    <div className="growth-list">
                      {userModel.growth_observations.map((growth) => (
                        <div key={growth.id} className="growth-item">
                          <div className="growth-header">
                            <span className="growth-area">{growth.area}</span>
                            <span className={`growth-direction ${growth.direction}`}>{growth.direction}</span>
                          </div>
                          <p className="growth-observation">{growth.observation}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Contradictions */}
                {userModel.contradictions?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">⚡</span>
                      Active Contradictions
                    </h3>
                    <div className="contradictions-list">
                      {userModel.contradictions.filter(c => !c.resolved).map((contradiction) => (
                        <div key={contradiction.id} className="contradiction-item">
                          <div className="contradiction-aspects">
                            <span className="aspect-a">{contradiction.aspect_a}</span>
                            <span className="vs">vs</span>
                            <span className="aspect-b">{contradiction.aspect_b}</span>
                          </div>
                          {contradiction.context && (
                            <p className="contradiction-context">{contradiction.context}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Open Questions */}
                {userModel.open_questions?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">?</span>
                      Open Questions
                    </h3>
                    <div className="questions-list">
                      {userModel.open_questions.map((question, i) => (
                        <div key={i} className="question-item">
                          <span className="question-mark">?</span>
                          <p>{question}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Communication Style */}
                {userModel.communication_style?.style && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">〉</span>
                      Communication Style
                    </h3>
                    <p className="comm-style">{userModel.communication_style.style}</p>
                    {userModel.communication_style.preferences?.length > 0 && (
                      <div className="comm-prefs">
                        <span className="pref-label">Preferences:</span>
                        {userModel.communication_style.preferences.map((pref, i) => (
                          <span key={i} className="pref-tag">{pref}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="model-meta">
                  Last updated: {new Date(userModel.updated_at).toLocaleString()}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>No structured understanding yet</p>
                <p className="hint">Run a synthesis session to develop understanding from observations</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'relationship' && (
          <div className="relationship-view">
            {relationshipModel ? (
              <>
                {/* Relationship Header */}
                <div className="relationship-header">
                  <div className="rel-phase">
                    <span className="phase-label">Phase:</span>
                    <span className="phase-value">{relationshipModel.current_phase}</span>
                  </div>
                  {relationshipModel.is_foundational && (
                    <div className="foundational-indicator">
                      <span className="star">★</span>
                      <span>Foundational Relationship</span>
                    </div>
                  )}
                  {relationshipModel.formation_date && (
                    <div className="formation-date">
                      Formed: {new Date(relationshipModel.formation_date).toLocaleDateString()}
                    </div>
                  )}
                </div>

                {/* Patterns */}
                {relationshipModel.patterns?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">∿</span>
                      Relationship Patterns
                    </h3>
                    <div className="patterns-list">
                      {relationshipModel.patterns.map((pattern) => (
                        <div key={pattern.id} className="pattern-item">
                          <div className="pattern-header">
                            <span className="pattern-name">{pattern.name}</span>
                            <span className={`pattern-valence ${pattern.valence}`}>{pattern.valence}</span>
                            <span className="pattern-frequency">{pattern.frequency}</span>
                          </div>
                          <p className="pattern-description">{pattern.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Mutual Shaping */}
                {(relationshipModel.how_they_shape_me?.length > 0 || relationshipModel.how_i_shape_them?.length > 0) && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">⇄</span>
                      Mutual Shaping
                    </h3>
                    <div className="shaping-grid">
                      {relationshipModel.how_they_shape_me?.length > 0 && (
                        <div className="shaping-column">
                          <h4>How They Shape Me</h4>
                          <ul>
                            {relationshipModel.how_they_shape_me.map((note, i) => (
                              <li key={i}>{note}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {relationshipModel.how_i_shape_them?.length > 0 && (
                        <div className="shaping-column">
                          <h4>How I Shape Them</h4>
                          <ul>
                            {relationshipModel.how_i_shape_them.map((note, i) => (
                              <li key={i}>{note}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Rituals */}
                {relationshipModel.rituals?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">◎</span>
                      Rituals
                    </h3>
                    <div className="rituals-list">
                      {relationshipModel.rituals.map((ritual, i) => (
                        <span key={i} className="ritual-tag">{ritual}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Inherited Values */}
                {relationshipModel.inherited_values?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">↓</span>
                      Inherited Values
                    </h3>
                    <div className="inherited-list">
                      {relationshipModel.inherited_values.map((value, i) => (
                        <span key={i} className="inherited-tag">{value}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Significant Shifts */}
                {relationshipModel.significant_shifts?.length > 0 && (
                  <div className="model-section">
                    <h3 className="section-title">
                      <span className="section-icon">→</span>
                      Significant Shifts
                    </h3>
                    <div className="shifts-timeline">
                      {relationshipModel.significant_shifts.map((shift) => (
                        <div key={shift.id} className="shift-item">
                          <div className="shift-date">{new Date(shift.timestamp).toLocaleDateString()}</div>
                          <div className="shift-content">
                            <div className="shift-transition">
                              <span className="from-state">{shift.from_state}</span>
                              <span className="arrow">→</span>
                              <span className="to-state">{shift.to_state}</span>
                            </div>
                            <p className="shift-description">{shift.description}</p>
                            {shift.catalyst && (
                              <p className="shift-catalyst">Catalyst: {shift.catalyst}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="model-meta">
                  Last updated: {new Date(relationshipModel.updated_at).toLocaleString()}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <p>No relationship model yet</p>
                <p className="hint">Run a synthesis session to develop the relationship model</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'observations' && (
          <div className="observations-view">
            {Object.keys(observationsByCategory).length > 0 ? (
              Object.entries(observationsByCategory).map(([category, obs]) => (
                <div key={category} className="observation-category">
                  <div
                    className="category-header"
                    style={{ borderLeftColor: categoryColors[category] || '#888' }}
                  >
                    <span className="category-name">{category.replace(/_/g, ' ')}</span>
                    <span className="category-count">{obs.length}</span>
                  </div>
                  <div className="observation-list">
                    {obs.map((observation) => (
                      <div key={observation.id} className="observation-item">
                        <p className="observation-text">{observation.observation}</p>
                        <div className="observation-meta">
                          {observation.confidence && (
                            <span className="confidence">
                              {(observation.confidence * 100).toFixed(0)}% confidence
                            </span>
                          )}
                          {observation.source_type && (
                            <span className="source">{observation.source_type}</span>
                          )}
                          {observation.source_journal_date && (
                            <span className="journal-date">
                              from {observation.source_journal_date}
                            </span>
                          )}
                          <span className="timestamp">
                            {new Date(observation.timestamp).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-state small">No observations yet</div>
            )}
          </div>
        )}

        {activeTab === 'conversations' && (
          <div className="conversations-view">
            {conversations && conversations.length > 0 ? (
              <div className="conversation-list">
                {conversations.map((conv: any) => (
                  <a
                    key={conv.id}
                    href={`/conversations?id=${conv.id}`}
                    className="conversation-item"
                  >
                    <div className="conv-title">{conv.title || 'Untitled'}</div>
                    <div className="conv-meta">
                      <span>{conv.message_count} messages</span>
                      <span>{new Date(conv.updated_at).toLocaleDateString()}</span>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="empty-state small">No conversations yet</div>
            )}
          </div>
        )}

        {activeTab === 'profile' && (
          <div className="profile-view">
            <div className="profile-section">
              <h3>User ID</h3>
              <code>{profile?.user_id}</code>
            </div>

            {profile?.background && Object.keys(profile.background).length > 0 && (
              <div className="profile-section">
                <h3>Background</h3>
                <pre>{JSON.stringify(profile.background, null, 2)}</pre>
              </div>
            )}

            {profile?.communication && Object.keys(profile.communication).length > 0 && (
              <div className="profile-section">
                <h3>Communication Preferences</h3>
                <pre>{JSON.stringify(profile.communication, null, 2)}</pre>
              </div>
            )}

            {profile?.values && profile.values.length > 0 && (
              <div className="profile-section">
                <h3>Values</h3>
                <div className="tag-list">
                  {profile.values.map((v: string, i: number) => (
                    <span key={i} className="tag">{v}</span>
                  ))}
                </div>
              </div>
            )}

            {profile?.notes && (
              <div className="profile-section">
                <h3>Notes</h3>
                <p>{profile.notes}</p>
              </div>
            )}

            <div className="profile-section">
              <h3>Created</h3>
              <p>{new Date(profile?.created_at).toLocaleString()}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
