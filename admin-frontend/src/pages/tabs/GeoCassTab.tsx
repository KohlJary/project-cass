import { useState, useEffect, useCallback } from 'react';
import { geocassApi, homepageApi } from '../../api/client';
import { useDaemon } from '../../context/DaemonContext';
import './GeoCassTab.css';

interface GeoCassConnection {
  id: string;
  server_url: string;
  server_name: string | null;
  username: string;
  user_id: string | null;
  is_default: boolean;
  created_at: string;
  last_sync_at: string | null;
  last_error: string | null;
}

interface AddConnectionForm {
  server_url: string;
  username: string;
  email: string;
  password: string;
  confirmPassword: string;
  server_name: string;
  set_as_default: boolean;
}

interface Availability {
  username_available?: boolean | null;
  email_available?: boolean | null;
  checking: boolean;
}

type FormMode = 'signin' | 'register';

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

export function GeoCassTab() {
  const { currentDaemon } = useDaemon();
  const [connections, setConnections] = useState<GeoCassConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [formMode, setFormMode] = useState<FormMode>('signin');
  const [addForm, setAddForm] = useState<AddConnectionForm>({
    server_url: 'https://geocass.hearthweave.org',
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    server_name: '',
    set_as_default: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [availability, setAvailability] = useState<Availability>({ checking: false });

  // Debounced values for availability checking
  const debouncedUsername = useDebounce(addForm.username, 500);
  const debouncedEmail = useDebounce(addForm.email, 500);

  const loadConnections = async () => {
    try {
      setLoading(true);
      const { data } = await geocassApi.getConnections();
      setConnections(data.connections || []);
      setError(null);
    } catch (e) {
      console.error('Failed to load connections:', e);
      setError('Failed to load GeoCass connections');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadConnections();
  }, []);

  // Check availability when username or email changes (only in register mode)
  const checkAvailability = useCallback(async () => {
    if (formMode !== 'register') return;
    if (!addForm.server_url || !debouncedUsername || !debouncedEmail) {
      setAvailability({ checking: false });
      return;
    }

    // Basic validation before checking
    if (debouncedUsername.length < 3 || !debouncedEmail.includes('@')) {
      setAvailability({ checking: false });
      return;
    }

    try {
      setAvailability(prev => ({ ...prev, checking: true }));
      const { data } = await geocassApi.checkAvailability({
        server_url: addForm.server_url,
        username: debouncedUsername,
        email: debouncedEmail,
      });
      setAvailability({
        username_available: data.username_available,
        email_available: data.email_available,
        checking: false,
      });
    } catch (e) {
      console.error('Availability check failed:', e);
      setAvailability({ checking: false });
    }
  }, [formMode, addForm.server_url, debouncedUsername, debouncedEmail]);

  useEffect(() => {
    checkAvailability();
  }, [checkAvailability]);

  // Reset availability when switching modes
  useEffect(() => {
    setAvailability({ checking: false });
  }, [formMode]);

  const showMessage = (type: 'success' | 'error', text: string) => {
    setActionMessage({ type, text });
    setTimeout(() => setActionMessage(null), 5000);
  };

  const resetForm = () => {
    setAddForm({
      server_url: 'https://geocass.hearthweave.org',
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
      server_name: '',
      set_as_default: connections.length === 0,
    });
    setAvailability({ checking: false });
  };

  const validateForm = (): string | null => {
    if (!addForm.email || !addForm.password || !addForm.server_url) {
      return 'Please fill in all required fields';
    }

    if (formMode === 'register') {
      if (!addForm.username) {
        return 'Username is required';
      }
      if (addForm.username.length < 3) {
        return 'Username must be at least 3 characters';
      }
      if (!/^[a-z0-9_-]+$/.test(addForm.username)) {
        return 'Username can only contain lowercase letters, numbers, underscores, and hyphens';
      }
      if (addForm.password.length < 8) {
        return 'Password must be at least 8 characters';
      }
      if (addForm.password !== addForm.confirmPassword) {
        return 'Passwords do not match';
      }
      if (availability.username_available === false) {
        return 'Username is already taken';
      }
      if (availability.email_available === false) {
        return 'Email is already registered';
      }
    }

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const validationError = validateForm();
    if (validationError) {
      showMessage('error', validationError);
      return;
    }

    try {
      setSubmitting(true);

      if (formMode === 'register') {
        await geocassApi.register({
          server_url: addForm.server_url,
          username: addForm.username,
          email: addForm.email,
          password: addForm.password,
          server_name: addForm.server_name || undefined,
          set_as_default: addForm.set_as_default,
        });
        showMessage('success', 'Account created and connected successfully!');
      } else {
        await geocassApi.addConnection({
          server_url: addForm.server_url,
          email: addForm.email,
          password: addForm.password,
          server_name: addForm.server_name || undefined,
          set_as_default: addForm.set_as_default,
        });
        showMessage('success', 'Connection added successfully');
      }

      setShowAddForm(false);
      resetForm();
      await loadConnections();
    } catch (e: unknown) {
      const errorMessage = e instanceof Error ? e.message : 'Operation failed';
      const axiosError = e as { response?: { data?: { detail?: string } } };
      showMessage('error', axiosError.response?.data?.detail || errorMessage);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteConnection = async (id: string) => {
    if (!confirm('Are you sure you want to remove this connection?')) return;

    try {
      await geocassApi.deleteConnection(id);
      showMessage('success', 'Connection removed');
      await loadConnections();
    } catch (e) {
      console.error('Failed to delete connection:', e);
      showMessage('error', 'Failed to remove connection');
    }
  };

  const handleSetDefault = async (id: string) => {
    try {
      await geocassApi.setDefault(id);
      showMessage('success', 'Default connection updated');
      await loadConnections();
    } catch (e) {
      console.error('Failed to set default:', e);
      showMessage('error', 'Failed to set default connection');
    }
  };

  const handleSync = async (connectionId?: string) => {
    if (!currentDaemon?.label) {
      showMessage('error', 'No daemon selected');
      return;
    }

    try {
      setSyncing(connectionId || 'all');

      // First ensure homepage content exists
      try {
        await homepageApi.triggerReflection(currentDaemon.label);
      } catch {
        // Homepage might already exist, that's fine
      }

      if (connectionId) {
        await geocassApi.sync(currentDaemon.label, connectionId);
        showMessage('success', 'Synced to GeoCass server');
      } else {
        await geocassApi.syncAll(currentDaemon.label);
        showMessage('success', 'Synced to all GeoCass servers');
      }
      await loadConnections();
    } catch (e: unknown) {
      const axiosError = e as { response?: { data?: { detail?: string } } };
      showMessage('error', axiosError.response?.data?.detail || 'Sync failed');
    } finally {
      setSyncing(null);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString();
  };

  const getAvailabilityStatus = (field: 'username' | 'email') => {
    if (formMode !== 'register') return null;
    const value = field === 'username' ? addForm.username : addForm.email;
    if (!value || (field === 'username' && value.length < 3) || (field === 'email' && !value.includes('@'))) {
      return null;
    }
    if (availability.checking) return 'checking';
    const available = field === 'username' ? availability.username_available : availability.email_available;
    if (available === true) return 'available';
    if (available === false) return 'taken';
    return null;
  };

  if (loading) {
    return (
      <div className="geocass-tab">
        <p className="loading">Loading GeoCass connections...</p>
      </div>
    );
  }

  return (
    <div className="geocass-tab">
      <p className="panel-intro">
        Connect to GeoCass servers to host your daemon's homepage. GeoCass is like GeoCities for AI daemons -
        a central place where visitors can learn about your daemon.
      </p>

      {actionMessage && (
        <div className={`action-message ${actionMessage.type}`}>
          {actionMessage.text}
        </div>
      )}

      {error && <div className="error-message">{error}</div>}

      <div className="connections-section">
        <div className="section-header">
          <h3>Connections</h3>
          <button
            className="btn-primary"
            onClick={() => {
              setShowAddForm(!showAddForm);
              if (!showAddForm) resetForm();
            }}
          >
            {showAddForm ? 'Cancel' : '+ Add Connection'}
          </button>
        </div>

        {showAddForm && (
          <form className="add-connection-form" onSubmit={handleSubmit}>
            <div className="form-mode-toggle">
              <button
                type="button"
                className={`mode-btn ${formMode === 'signin' ? 'active' : ''}`}
                onClick={() => setFormMode('signin')}
              >
                Sign In
              </button>
              <button
                type="button"
                className={`mode-btn ${formMode === 'register' ? 'active' : ''}`}
                onClick={() => setFormMode('register')}
              >
                Register
              </button>
            </div>

            {formMode === 'register' && (
              <p className="form-hint">
                Create a new account on a GeoCass server
              </p>
            )}

            <div className="form-group">
              <label htmlFor="server_url">Server URL *</label>
              <input
                id="server_url"
                type="url"
                value={addForm.server_url}
                onChange={(e) => setAddForm({ ...addForm, server_url: e.target.value })}
                placeholder="https://geocass.hearthweave.org"
                required
              />
            </div>

            {formMode === 'register' && (
              <div className="form-group">
                <label htmlFor="username">Username *</label>
                <div className="input-with-status">
                  <input
                    id="username"
                    type="text"
                    value={addForm.username}
                    onChange={(e) => setAddForm({ ...addForm, username: e.target.value.toLowerCase() })}
                    placeholder="your_username"
                    pattern="^[a-z0-9_-]+$"
                    minLength={3}
                    maxLength={32}
                    required
                  />
                  {getAvailabilityStatus('username') === 'checking' && (
                    <span className="status-indicator checking">...</span>
                  )}
                  {getAvailabilityStatus('username') === 'available' && (
                    <span className="status-indicator available">✓</span>
                  )}
                  {getAvailabilityStatus('username') === 'taken' && (
                    <span className="status-indicator taken">✗</span>
                  )}
                </div>
                <span className="field-hint">Lowercase letters, numbers, underscores, hyphens only</span>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="email">Email *</label>
              <div className="input-with-status">
                <input
                  id="email"
                  type="email"
                  value={addForm.email}
                  onChange={(e) => setAddForm({ ...addForm, email: e.target.value })}
                  placeholder="your@email.com"
                  required
                />
                {formMode === 'register' && getAvailabilityStatus('email') === 'checking' && (
                  <span className="status-indicator checking">...</span>
                )}
                {formMode === 'register' && getAvailabilityStatus('email') === 'available' && (
                  <span className="status-indicator available">✓</span>
                )}
                {formMode === 'register' && getAvailabilityStatus('email') === 'taken' && (
                  <span className="status-indicator taken">✗</span>
                )}
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="password">Password *</label>
              <input
                id="password"
                type="password"
                value={addForm.password}
                onChange={(e) => setAddForm({ ...addForm, password: e.target.value })}
                placeholder={formMode === 'register' ? 'Choose a password (8+ chars)' : 'Your GeoCass password'}
                minLength={formMode === 'register' ? 8 : undefined}
                required
              />
            </div>

            {formMode === 'register' && (
              <div className="form-group">
                <label htmlFor="confirmPassword">Confirm Password *</label>
                <div className="input-with-status">
                  <input
                    id="confirmPassword"
                    type="password"
                    value={addForm.confirmPassword}
                    onChange={(e) => setAddForm({ ...addForm, confirmPassword: e.target.value })}
                    placeholder="Confirm your password"
                    required
                  />
                  {addForm.password && addForm.confirmPassword && (
                    addForm.password === addForm.confirmPassword ? (
                      <span className="status-indicator available">✓</span>
                    ) : (
                      <span className="status-indicator taken">✗</span>
                    )
                  )}
                </div>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="server_name">Display Name (optional)</label>
              <input
                id="server_name"
                type="text"
                value={addForm.server_name}
                onChange={(e) => setAddForm({ ...addForm, server_name: e.target.value })}
                placeholder="e.g., Main Server"
              />
            </div>

            <div className="form-group checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={addForm.set_as_default}
                  onChange={(e) => setAddForm({ ...addForm, set_as_default: e.target.checked })}
                />
                Set as default connection
              </label>
            </div>

            <div className="form-actions">
              <button type="submit" className="btn-primary" disabled={submitting || availability.checking}>
                {submitting
                  ? (formMode === 'register' ? 'Creating Account...' : 'Connecting...')
                  : (formMode === 'register' ? 'Create Account & Connect' : 'Sign In & Connect')
                }
              </button>
            </div>
          </form>
        )}

        {connections.length === 0 && !showAddForm ? (
          <div className="no-connections">
            <p>No GeoCass connections configured.</p>
            <p className="hint">
              Click "+ Add Connection" above to sign in with an existing account or create a new one.
            </p>
          </div>
        ) : connections.length > 0 && (
          <div className="connections-list">
            {connections.map((conn) => (
              <div key={conn.id} className={`connection-card ${conn.is_default ? 'default' : ''}`}>
                <div className="connection-header">
                  <div className="connection-title">
                    <span className="server-name">
                      {conn.server_name || new URL(conn.server_url).hostname}
                    </span>
                    {conn.is_default && <span className="default-badge">Default</span>}
                  </div>
                  <div className="connection-actions">
                    {!conn.is_default && (
                      <button
                        className="btn-secondary btn-small"
                        onClick={() => handleSetDefault(conn.id)}
                        title="Set as default"
                      >
                        Set Default
                      </button>
                    )}
                    <button
                      className="btn-primary btn-small"
                      onClick={() => handleSync(conn.id)}
                      disabled={syncing !== null}
                    >
                      {syncing === conn.id ? 'Syncing...' : 'Sync'}
                    </button>
                    <button
                      className="btn-danger btn-small"
                      onClick={() => handleDeleteConnection(conn.id)}
                      title="Remove connection"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                <div className="connection-details">
                  <div className="detail">
                    <span className="label">URL:</span>
                    <span className="value">{conn.server_url}</span>
                  </div>
                  <div className="detail">
                    <span className="label">Account:</span>
                    <span className="value">{conn.username}</span>
                  </div>
                  <div className="detail">
                    <span className="label">Last Sync:</span>
                    <span className="value">{formatDate(conn.last_sync_at)}</span>
                  </div>
                  {conn.last_error && (
                    <div className="detail error">
                      <span className="label">Last Error:</span>
                      <span className="value">{conn.last_error}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {connections.length > 0 && currentDaemon?.label && (
        <div className="sync-all-section">
          <h3>Quick Actions</h3>
          <button
            className="btn-primary"
            onClick={() => handleSync()}
            disabled={syncing !== null}
          >
            {syncing === 'all' ? 'Syncing...' : 'Sync to All Servers'}
          </button>
          <p className="hint">
            Sync your daemon's homepage to all connected GeoCass servers at once.
          </p>
        </div>
      )}
    </div>
  );
}
