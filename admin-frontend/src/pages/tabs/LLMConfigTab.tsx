import { useState, useEffect, useCallback } from 'react';
import { llmConfigApi, type ModelAssignment, type AvailableModel } from '../../api/domains/misc';
import './LLMConfigTab.css';

interface CallSiteConfig {
  callSite: string;
  assignment: ModelAssignment;
  isDirty: boolean;
}

export function LLMConfigTab() {
  const [configs, setConfigs] = useState<CallSiteConfig[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [filterPriority, setFilterPriority] = useState<string>('all');

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const { data } = await llmConfigApi.getConfig();

      const configList: CallSiteConfig[] = Object.entries(data.assignments)
        .map(([callSite, assignment]) => ({
          callSite,
          assignment,
          isDirty: false,
        }))
        .sort((a, b) => {
          // Sort by priority (high first), then alphabetically
          const priorityOrder = { high: 0, medium: 1, low: 2 };
          const aPriority = priorityOrder[a.assignment.metadata?.priority || 'medium'];
          const bPriority = priorityOrder[b.assignment.metadata?.priority || 'medium'];
          if (aPriority !== bPriority) return aPriority - bPriority;
          return a.callSite.localeCompare(b.callSite);
        });

      setConfigs(configList);
      setAvailableModels(data.available_models || []);
    } catch (e) {
      console.error('Failed to fetch LLM config:', e);
      setError('Failed to load LLM configuration');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleModelChange = (callSite: string, field: 'provider' | 'model_id' | 'fallback_provider' | 'fallback_model_id', value: string | null) => {
    setConfigs(prev => prev.map(config => {
      if (config.callSite !== callSite) return config;

      const newAssignment = { ...config.assignment };

      if (field === 'provider' || field === 'model_id') {
        // When changing provider, also update model_id to first available model for that provider
        if (field === 'provider') {
          const firstModel = availableModels.find(m => m.provider === value && m.installed);
          newAssignment.provider = value || 'anthropic';
          newAssignment.model_id = firstModel?.model_id || '';
        } else {
          newAssignment.model_id = value || '';
        }
      } else {
        // Fallback fields
        if (field === 'fallback_provider') {
          if (value) {
            const firstModel = availableModels.find(m => m.provider === value && m.installed);
            newAssignment.fallback_provider = value;
            newAssignment.fallback_model_id = firstModel?.model_id || null;
          } else {
            newAssignment.fallback_provider = null;
            newAssignment.fallback_model_id = null;
          }
        } else {
          newAssignment.fallback_model_id = value;
        }
      }

      return { ...config, assignment: newAssignment, isDirty: true };
    }));
  };

  const handleSave = async (callSite: string) => {
    const config = configs.find(c => c.callSite === callSite);
    if (!config) return;

    setSaving(callSite);
    setError(null);
    setSuccessMessage(null);

    try {
      await llmConfigApi.setAssignment(callSite, {
        provider: config.assignment.provider,
        model_id: config.assignment.model_id,
        fallback_provider: config.assignment.fallback_provider,
        fallback_model_id: config.assignment.fallback_model_id,
      });

      setConfigs(prev => prev.map(c =>
        c.callSite === callSite ? { ...c, isDirty: false } : c
      ));
      setSuccessMessage(`Updated ${config.assignment.metadata?.name || callSite}`);
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (e) {
      console.error('Failed to save:', e);
      setError(`Failed to save ${callSite}`);
    } finally {
      setSaving(null);
    }
  };

  const handleResetAll = async () => {
    if (!confirm('Reset all LLM assignments to defaults? This cannot be undone.')) return;

    setSaving('reset');
    setError(null);
    try {
      await llmConfigApi.resetToDefaults();
      await fetchConfig();
      setSuccessMessage('Reset all assignments to defaults');
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (e) {
      console.error('Failed to reset:', e);
      setError('Failed to reset to defaults');
    } finally {
      setSaving(null);
    }
  };

  const getModelsForProvider = (provider: string) => {
    return availableModels.filter(m => m.provider === provider);
  };

  const getUniqueProviders = () => {
    return [...new Set(availableModels.map(m => m.provider))];
  };

  const filteredConfigs = filterPriority === 'all'
    ? configs
    : configs.filter(c => c.assignment.metadata?.priority === filterPriority);

  const dirtyCount = configs.filter(c => c.isDirty).length;

  if (loading) {
    return <div className="llm-config-tab loading">Loading LLM configuration...</div>;
  }

  return (
    <div className="llm-config-tab">
      <div className="llm-config-header">
        <div className="header-info">
          <h2>LLM Model Configuration</h2>
          <p className="description">
            Configure which model handles each internal function.
            Local models reduce API costs; cloud models ensure quality for creative tasks.
          </p>
        </div>
        <div className="header-actions">
          <select
            value={filterPriority}
            onChange={e => setFilterPriority(e.target.value)}
            className="filter-select"
          >
            <option value="all">All priorities</option>
            <option value="high">High priority</option>
            <option value="medium">Medium priority</option>
            <option value="low">Low priority</option>
          </select>
          <button
            className="reset-button"
            onClick={handleResetAll}
            disabled={saving === 'reset'}
          >
            {saving === 'reset' ? 'Resetting...' : 'Reset All to Defaults'}
          </button>
        </div>
      </div>

      {error && <div className="message error">{error}</div>}
      {successMessage && <div className="message success">{successMessage}</div>}
      {dirtyCount > 0 && (
        <div className="message warning">
          {dirtyCount} unsaved change{dirtyCount > 1 ? 's' : ''}
        </div>
      )}

      <div className="model-legend">
        <span className="legend-item local">Local</span>
        <span className="legend-item cloud">Cloud</span>
        <span className="legend-item not-installed">Not Installed</span>
      </div>

      <div className="config-grid">
        {filteredConfigs.map(config => (
          <div
            key={config.callSite}
            className={`config-card ${config.isDirty ? 'dirty' : ''} priority-${config.assignment.metadata?.priority || 'medium'}`}
          >
            <div className="card-header">
              <div className="card-title">
                <h3>{config.assignment.metadata?.name || config.callSite}</h3>
                <span className={`priority-badge ${config.assignment.metadata?.priority || 'medium'}`}>
                  {config.assignment.metadata?.priority || 'medium'}
                </span>
              </div>
              <p className="card-description">
                {config.assignment.metadata?.description || config.callSite}
              </p>
              <span className="frequency">{config.assignment.metadata?.frequency || 'varies'}</span>
            </div>

            <div className="card-body">
              <div className="model-selector">
                <label>Primary Model</label>
                <div className="selector-row">
                  <select
                    value={config.assignment.provider}
                    onChange={e => handleModelChange(config.callSite, 'provider', e.target.value)}
                  >
                    {getUniqueProviders().map(provider => (
                      <option key={provider} value={provider}>
                        {provider.charAt(0).toUpperCase() + provider.slice(1)}
                      </option>
                    ))}
                  </select>
                  <select
                    value={config.assignment.model_id}
                    onChange={e => handleModelChange(config.callSite, 'model_id', e.target.value)}
                  >
                    {getModelsForProvider(config.assignment.provider).map(model => (
                      <option
                        key={model.model_id}
                        value={model.model_id}
                        disabled={!model.installed}
                      >
                        {model.name} {model.local ? '(local)' : ''} {!model.installed ? '[not installed]' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="model-selector fallback">
                <label>Fallback Model (optional)</label>
                <div className="selector-row">
                  <select
                    value={config.assignment.fallback_provider || ''}
                    onChange={e => handleModelChange(config.callSite, 'fallback_provider', e.target.value || null)}
                  >
                    <option value="">No fallback</option>
                    {getUniqueProviders().map(provider => (
                      <option key={provider} value={provider}>
                        {provider.charAt(0).toUpperCase() + provider.slice(1)}
                      </option>
                    ))}
                  </select>
                  {config.assignment.fallback_provider && (
                    <select
                      value={config.assignment.fallback_model_id || ''}
                      onChange={e => handleModelChange(config.callSite, 'fallback_model_id', e.target.value || null)}
                    >
                      {getModelsForProvider(config.assignment.fallback_provider).map(model => (
                        <option
                          key={model.model_id}
                          value={model.model_id}
                          disabled={!model.installed}
                        >
                          {model.name} {model.local ? '(local)' : ''} {!model.installed ? '[not installed]' : ''}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>
            </div>

            <div className="card-footer">
              <button
                className="save-button"
                onClick={() => handleSave(config.callSite)}
                disabled={!config.isDirty || saving === config.callSite}
              >
                {saving === config.callSite ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
