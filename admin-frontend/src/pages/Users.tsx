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

export function Users() {
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.getAll().then((r) => r.data),
    retry: false,
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

  return (
    <div className="users-page">
      <header className="page-header">
        <h1>Users</h1>
        <p className="subtitle">Manage user profiles and observations</p>
      </header>

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
  isAdmin,
  hasPassword,
  onRefresh,
}: {
  profile: any;
  observations: Observation[];
  conversations?: any[];
  isAdmin: boolean;
  hasPassword: boolean;
  onRefresh: () => void;
}) {
  const [activeTab, setActiveTab] = useState<'observations' | 'conversations' | 'profile'>('observations');
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
