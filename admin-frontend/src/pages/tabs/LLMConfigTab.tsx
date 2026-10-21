import { useState, useEffect, useCallback } from 'react';
import {
  llmConfigApi,
  type AvailableModel,
  type CallSiteUsage,
  type CallSiteView,
  type ModelAssignment,
} from '../../api/domains/misc';
import './LLMConfigTab.css';

type Assignment = Omit<ModelAssignment, 'metadata'>;

interface CallSiteState {
  view: CallSiteView;
  draft: Assignment;
  isDirty: boolean;
}

const EMPTY: Assignment = { provider: 'anthropic', model_id: '', fallback_provider: null, fallback_model_id: null };

function describe(a: Assignment | null): string {
  if (!a) return 'skipped (no model)';
  const main = `${a.provider}:${a.model_id}`;
  return a.fallback_provider ? `${main} → ${a.fallback_provider}:${a.fallback_model_id}` : main;
}

function formatCost(usd: number): string {
  if (!usd) return '$0';
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function UsageLine({ usage }: { usage: CallSiteUsage }) {
  if (!usage.calls) return <div className="usage-line empty">No calls in this period</div>;
  return (
    <div className="usage-line">
      <span>{usage.calls} call{usage.calls === 1 ? '' : 's'}</span>
      <span>{formatTokens(usage.input_tokens)} in / {formatTokens(usage.output_tokens)} out</span>
      <span className="cost">{formatCost(usage.cost_usd)}</span>
      {usage.last_call && <span className="last">last {usage.last_call.slice(0, 16).replace('T', ' ')}</span>}
    </div>
  );
}

export function LLMConfigTab() {
  const [sites, setSites] = useState<CallSiteState[]>([]);
  const [otherUsage, setOtherUsage] = useState<Record<string, CallSiteUsage>>({});
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');

  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [{ data }, models] = await Promise.all([
        llmConfigApi.getConfig(days),
        llmConfigApi.getAvailableModels().catch(() => null),
      ]);
      const priorityOrder = { high: 0, medium: 1, low: 2 };
      const list = data.call_sites
        .map(view => ({ view, draft: { ...(view.effective || EMPTY) }, isDirty: false }))
        .sort((a, b) => {
          const pa = priorityOrder[a.view.metadata?.priority || 'medium'];
          const pb = priorityOrder[b.view.metadata?.priority || 'medium'];
          return pa !== pb ? pa - pb : a.view.call_site.localeCompare(b.view.call_site);
        });
      setSites(list);
      setOtherUsage(data.other_usage || {});
      setAvailableModels(models?.data.models || data.available_models || []);
    } catch (e) {
      console.error('Failed to fetch LLM config:', e);
      setError('Failed to load LLM configuration');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const flash = (msg: string) => {
    setSuccessMessage(msg);
    setTimeout(() => setSuccessMessage(null), 3000);
  };

  const modelsFor = (provider: string | null) => availableModels.filter(m => m.provider === provider);
  const providers = [...new Set(availableModels.map(m => m.provider))];

  const firstModel = (provider: string) =>
    modelsFor(provider).find(m => m.installed !== false)?.model_id || modelsFor(provider)[0]?.model_id || '';

  const edit = (callSite: string, change: (d: Assignment) => Assignment) => {
    setSites(prev => prev.map(s => (s.view.call_site === callSite ? { ...s, draft: change({ ...s.draft }), isDirty: true } : s)));
  };

  const handleSave = async (s: CallSiteState) => {
    setSaving(s.view.call_site);
    setError(null);
    try {
      await llmConfigApi.setAssignment(s.view.call_site, s.draft);
      flash(`${s.view.metadata?.name || s.view.call_site}: now ${describe(s.draft)}`);
      await fetchConfig();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(`Failed to save ${s.view.call_site}${detail ? `: ${detail}` : ''}`);
    } finally {
      setSaving(null);
    }
  };

  const handleRevert = async (s: CallSiteState) => {
    setSaving(s.view.call_site);
    setError(null);
    try {
      await llmConfigApi.clearAssignment(s.view.call_site);
      flash(`${s.view.metadata?.name || s.view.call_site}: back to its default`);
      await fetchConfig();
    } catch {
      setError(`Failed to revert ${s.view.call_site}`);
    } finally {
      setSaving(null);
    }
  };

  const handleResetAll = async () => {
    if (!confirm('Remove every override? Each subsystem goes back to its default model.')) return;
    setSaving('reset');
    setError(null);
    try {
      await llmConfigApi.resetToDefaults();
      await fetchConfig();
      flash('All overrides removed');
    } catch {
      setError('Failed to reset to defaults');
    } finally {
      setSaving(null);
    }
  };

  const filtered = sites.filter(s => {
    if (filter === 'all') return true;
    if (filter === 'overridden') return !!s.view.override;
    if (filter === 'used') return s.view.usage.calls > 0;
    return s.view.metadata?.priority === filter;
  });

  const totals = sites.reduce(
    (t, s) => ({ calls: t.calls + s.view.usage.calls, cost: t.cost + s.view.usage.cost_usd }),
    { calls: 0, cost: 0 },
  );
  const otherTotals = Object.values(otherUsage).reduce(
    (t, u) => ({ calls: t.calls + u.calls, cost: t.cost + u.cost_usd }),
    { calls: 0, cost: 0 },
  );
  const overrideCount = sites.filter(s => s.view.override).length;
  const dirtyCount = sites.filter(s => s.isDirty).length;

  if (loading && sites.length === 0) {
    return <div className="llm-config-tab loading">Loading LLM configuration...</div>;
  }

  return (
    <div className="llm-config-tab">
      <div className="llm-config-header">
        <div className="header-info">
          <h2>Model Routing</h2>
          <p className="description">
            Every LLM call site and the model it runs. With no override a call site runs its default,
            which is the model it used before routing. Usage comes from the token ledger.
          </p>
        </div>
        <div className="header-actions">
          <select value={days} onChange={e => setDays(Number(e.target.value))} className="filter-select">
            <option value={1}>Last 24 hours</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <select value={filter} onChange={e => setFilter(e.target.value)} className="filter-select">
            <option value="all">All call sites</option>
            <option value="used">Used in period</option>
            <option value="overridden">Overridden</option>
            <option value="high">High priority</option>
            <option value="medium">Medium priority</option>
            <option value="low">Low priority</option>
          </select>
          <button className="reset-button" onClick={handleResetAll} disabled={saving === 'reset' || overrideCount === 0}>
            {saving === 'reset' ? 'Resetting...' : 'Remove all overrides'}
          </button>
        </div>
      </div>

      <div className="routing-summary">
        <div><strong>{totals.calls}</strong> routed calls</div>
        <div><strong>{formatCost(totals.cost)}</strong> routed spend</div>
        <div><strong>{otherTotals.calls}</strong> other calls ({formatCost(otherTotals.cost)})</div>
        <div><strong>{overrideCount}</strong> override{overrideCount === 1 ? '' : 's'}</div>
      </div>

      {error && <div className="message error">{error}</div>}
      {successMessage && <div className="message success">{successMessage}</div>}
      {dirtyCount > 0 && (
        <div className="message warning">{dirtyCount} unsaved change{dirtyCount > 1 ? 's' : ''}</div>
      )}

      <div className="config-grid">
        {filtered.map(s => {
          const v = s.view;
          const meta = v.metadata;
          const locked = v.pinned;
          return (
            <div key={v.call_site} className={`config-card ${s.isDirty ? 'dirty' : ''} priority-${meta?.priority || 'medium'}`}>
              <div className="card-header">
                <div className="card-title">
                  <h3>{meta?.name || v.call_site}</h3>
                  {v.pinned ? (
                    <span className="state-badge pinned" title={v.pinned_reason}>pinned</span>
                  ) : v.override ? (
                    <span className="state-badge override">override</span>
                  ) : (
                    <span className="state-badge default">default</span>
                  )}
                </div>
                <code className="call-site-name">{v.call_site}</code>
                <p className="card-description">{meta?.description}</p>
                <span className="frequency">{meta?.frequency || 'varies'}</span>
              </div>

              <UsageLine usage={v.usage} />
              {v.usage.models.length > 0 && (
                <div className="models-seen">ran: {v.usage.models.join(', ')}</div>
              )}

              <div className="card-body">
                <div className="default-line">
                  Default: {v.default_from_caller ? v.default_note : describe(v.default)}
                  {!v.default_from_caller && v.default_note && v.default_note !== describe(v.default) && (
                    <span className="hint"> ({v.default_note})</span>
                  )}
                </div>
                {locked ? (
                  <div className="pinned-note">{v.pinned_reason}</div>
                ) : (
                  <>
                    {!v.text_only && (
                      <div className="hint">Uses tools or images: only Claude models can run it; others fall back to the default.</div>
                    )}
                    <div className="model-selector">
                      <label>Model</label>
                      <div className="selector-row">
                        <select
                          value={s.draft.provider}
                          onChange={e => {
                            const provider = e.target.value;
                            edit(v.call_site, d => ({ ...d, provider, model_id: firstModel(provider) }));
                          }}
                        >
                          {providers.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                        <select
                          value={s.draft.model_id}
                          onChange={e => edit(v.call_site, d => ({ ...d, model_id: e.target.value }))}
                        >
                          {!modelsFor(s.draft.provider).some(m => m.model_id === s.draft.model_id) && (
                            <option value={s.draft.model_id}>{s.draft.model_id || '(choose)'}</option>
                          )}
                          {modelsFor(s.draft.provider).map(m => (
                            <option key={m.model_id} value={m.model_id} disabled={m.installed === false}>
                              {m.name}{m.installed === false ? ' [not installed]' : ''}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="model-selector fallback">
                      <label>Fallback (optional)</label>
                      <div className="selector-row">
                        <select
                          value={s.draft.fallback_provider || ''}
                          onChange={e => {
                            const provider = e.target.value || null;
                            edit(v.call_site, d => ({
                              ...d,
                              fallback_provider: provider,
                              fallback_model_id: provider ? firstModel(provider) : null,
                            }));
                          }}
                        >
                          <option value="">No fallback</option>
                          {providers.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                        {s.draft.fallback_provider && (
                          <select
                            value={s.draft.fallback_model_id || ''}
                            onChange={e => edit(v.call_site, d => ({ ...d, fallback_model_id: e.target.value || null }))}
                          >
                            {!modelsFor(s.draft.fallback_provider).some(m => m.model_id === s.draft.fallback_model_id) && (
                              <option value={s.draft.fallback_model_id || ''}>{s.draft.fallback_model_id || '(choose)'}</option>
                            )}
                            {modelsFor(s.draft.fallback_provider).map(m => (
                              <option key={m.model_id} value={m.model_id} disabled={m.installed === false}>
                                {m.name}{m.installed === false ? ' [not installed]' : ''}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>

              {!locked && (
                <div className="card-footer">
                  {v.override && (
                    <button className="revert-button" onClick={() => handleRevert(s)} disabled={saving === v.call_site}>
                      Back to default
                    </button>
                  )}
                  <button
                    className="save-button"
                    onClick={() => handleSave(s)}
                    disabled={!s.isDirty || !s.draft.model_id || saving === v.call_site}
                  >
                    {saving === v.call_site ? 'Saving...' : 'Save override'}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {Object.keys(otherUsage).length > 0 && (
        <div className="other-usage">
          <h3>Other usage in the ledger</h3>
          <p className="description">
            Rows without a routed call site: chat turns (each user's model setting) and rows recorded before routing.
          </p>
          <table>
            <thead>
              <tr><th>Source</th><th>Calls</th><th>Tokens in / out</th><th>Spend</th><th>Models</th></tr>
            </thead>
            <tbody>
              {Object.entries(otherUsage)
                .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
                .map(([name, u]) => (
                  <tr key={name}>
                    <td><code>{name}</code></td>
                    <td>{u.calls}</td>
                    <td>{formatTokens(u.input_tokens)} / {formatTokens(u.output_tokens)}</td>
                    <td>{formatCost(u.cost_usd)}</td>
                    <td>{u.models.join(', ')}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
