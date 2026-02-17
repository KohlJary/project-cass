import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { grimoireApi } from '../api/client';
import type {
  GrimoireStatus,
  SpellSummary,
  SpellDetail,
  SpellSource,
  ExecutionLogEntry,
  CooldownEntry,
  TriggersIndex,
  CompileResponse,
  CastResponse,
} from '../api/client';
import './Grimoire.css';

type TabType = 'spells' | 'execution-log' | 'cooldowns' | 'triggers' | 'editor';

// =============================================================================
// MODULAR COMPONENTS - Extractable for standalone Grimoire app
// =============================================================================

/**
 * Status badge component - shows Grimoire operational status
 */
function GrimoireStatusBadge({ status }: { status: GrimoireStatus | undefined }) {
  if (!status) return <span className="status-badge loading">Loading...</span>;

  return (
    <div className="grimoire-status-badges">
      <span className={`status-badge ${status.shadow_mode ? 'shadow' : 'active'}`}>
        {status.shadow_mode ? 'Shadow Mode' : 'Active'}
      </span>
      {status.trace_enabled && (
        <span className="status-badge trace">Trace Enabled</span>
      )}
      <span className="status-badge spells">
        {status.spells_loaded} Spells
      </span>
    </div>
  );
}

/**
 * Spell list item - displays spell summary in list
 */
function SpellListItem({
  spell,
  selected,
  onClick
}: {
  spell: SpellSummary;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      className={`spell-list-item ${selected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <div className="spell-item-header">
        <span className="spell-name">{spell.name}</span>
        <span className="spell-priority">P{spell.priority}</span>
      </div>
      <div className="spell-item-meta">
        <span className="spell-triggers">{spell.trigger_count} triggers</span>
        <span className="spell-statements">{spell.statement_count} statements</span>
        {spell.cooldown_minutes > 0 && (
          <span className="spell-cooldown">{spell.cooldown_minutes}m cooldown</span>
        )}
      </div>
      {spell.tags.length > 0 && (
        <div className="spell-tags">
          {spell.tags.map(tag => (
            <span key={tag} className="spell-tag">{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Spell detail panel - shows full spell information
 */
function SpellDetailPanel({
  spell,
  source,
  onCast,
  castLoading,
  castResult,
}: {
  spell: SpellDetail | null;
  source: SpellSource | null;
  onCast: () => void;
  castLoading: boolean;
  castResult: CastResponse | null;
}) {
  const [showSource, setShowSource] = useState(false);

  if (!spell) {
    return (
      <div className="spell-detail-panel empty">
        <p>Select a spell to view details</p>
      </div>
    );
  }

  return (
    <div className="spell-detail-panel">
      <div className="spell-detail-header">
        <h2>{spell.name}</h2>
        {spell.author && <span className="spell-author">by {spell.author}</span>}
        {spell.version && <span className="spell-version">v{spell.version}</span>}
      </div>

      {spell.description && (
        <p className="spell-description">{spell.description}</p>
      )}

      <div className="spell-detail-grid">
        <div className="detail-item">
          <span className="detail-label">Priority</span>
          <span className="detail-value">{spell.priority}</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Cooldown</span>
          <span className="detail-value">{spell.cooldown_minutes} minutes</span>
        </div>
        <div className="detail-item">
          <span className="detail-label">Statements</span>
          <span className="detail-value">{spell.statement_count}</span>
        </div>
        {spell.last_executed && (
          <div className="detail-item">
            <span className="detail-label">Last Executed</span>
            <span className="detail-value">{new Date(spell.last_executed).toLocaleString()}</span>
          </div>
        )}
        {spell.cooldown_remaining_seconds !== null && spell.cooldown_remaining_seconds > 0 && (
          <div className="detail-item cooldown-active">
            <span className="detail-label">Cooldown Remaining</span>
            <span className="detail-value">{Math.ceil(spell.cooldown_remaining_seconds)}s</span>
          </div>
        )}
      </div>

      <section className="spell-triggers-section">
        <h3>Triggers ({spell.triggers.length})</h3>
        <div className="triggers-list">
          {spell.triggers.map((trigger, idx) => (
            <div key={idx} className={`trigger-item trigger-${trigger.type}`}>
              <span className="trigger-type">{trigger.type.toUpperCase()}</span>
              {trigger.target && <span className="trigger-target">{trigger.target}</span>}
              {trigger.condition && <span className="trigger-condition">{trigger.condition}</span>}
            </div>
          ))}
        </div>
      </section>

      <section className="spell-tags-section">
        <h3>Tags</h3>
        <div className="tags-list">
          {spell.tags.length > 0 ? (
            spell.tags.map(tag => <span key={tag} className="tag">{tag}</span>)
          ) : (
            <span className="no-tags">No tags</span>
          )}
        </div>
      </section>

      <section className="spell-statements-section">
        <h3>Statements ({spell.statements.length})</h3>
        <div className="statements-list">
          {spell.statements.map((stmt, idx) => (
            <div key={idx} className={`statement-item statement-${stmt.type}`}>
              <span className="statement-type">{stmt.type.toUpperCase()}</span>
              <span className="statement-summary">{stmt.summary}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="spell-actions">
        <button
          className="cast-btn"
          onClick={onCast}
          disabled={castLoading || (spell.cooldown_remaining_seconds !== null && spell.cooldown_remaining_seconds > 0)}
        >
          {castLoading ? 'Casting...' : 'Cast Spell'}
        </button>
        <button
          className="source-btn"
          onClick={() => setShowSource(!showSource)}
        >
          {showSource ? 'Hide Source' : 'View Source'}
        </button>
      </section>

      {castResult && (
        <div className={`cast-result ${castResult.success ? 'success' : 'failed'}`}>
          <div className="cast-result-header">
            <span className="cast-status">{castResult.status}</span>
            <span className="cast-time">{castResult.execution_time_ms.toFixed(1)}ms</span>
          </div>
          {castResult.reason && <p className="cast-reason">{castResult.reason}</p>}
          {castResult.trace && castResult.trace.length > 0 && (
            <div className="cast-trace">
              <h4>Trace:</h4>
              <pre>{castResult.trace.join('\n')}</pre>
            </div>
          )}
        </div>
      )}

      {showSource && source && (
        <section className="spell-source-section">
          <h3>Source Code</h3>
          {source.file_path && (
            <span className="source-path">{source.file_path}</span>
          )}
          <pre className="source-code">{source.source}</pre>
        </section>
      )}
    </div>
  );
}

/**
 * Execution log panel - shows recent spell executions
 */
function ExecutionLogPanel({ entries }: { entries: ExecutionLogEntry[] | undefined }) {
  if (!entries || entries.length === 0) {
    return (
      <div className="execution-log empty">
        <p>No spell executions recorded yet.</p>
      </div>
    );
  }

  return (
    <div className="execution-log">
      <table className="log-table">
        <thead>
          <tr>
            <th>Spell</th>
            <th>Trigger</th>
            <th>Status</th>
            <th>Time</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, idx) => (
            <tr key={idx} className={`log-entry status-${entry.status}`}>
              <td className="spell-name">{entry.spell_name}</td>
              <td className="trigger-type">{entry.trigger_type}</td>
              <td className="status">{entry.status}</td>
              <td className="exec-time">{entry.execution_time_ms.toFixed(1)}ms</td>
              <td className="reason">{entry.reason || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Cooldowns panel - shows spell cooldown status
 */
function CooldownsPanel({ cooldowns }: { cooldowns: CooldownEntry[] | undefined }) {
  if (!cooldowns || cooldowns.length === 0) {
    return (
      <div className="cooldowns-panel empty">
        <p>No spells with cooldowns.</p>
      </div>
    );
  }

  return (
    <div className="cooldowns-panel">
      <div className="cooldowns-grid">
        {cooldowns.map(cd => (
          <div
            key={cd.spell_name}
            className={`cooldown-item ${cd.can_execute ? 'ready' : 'cooling'}`}
          >
            <div className="cooldown-header">
              <span className="spell-name">{cd.spell_name}</span>
              <span className={`status-badge ${cd.can_execute ? 'ready' : 'cooling'}`}>
                {cd.can_execute ? 'Ready' : 'Cooling'}
              </span>
            </div>
            <div className="cooldown-details">
              <span className="cooldown-duration">{cd.cooldown_minutes}m cooldown</span>
              {cd.last_executed && (
                <span className="last-exec">Last: {new Date(cd.last_executed).toLocaleString()}</span>
              )}
              {!cd.can_execute && (
                <span className="remaining">
                  {Math.ceil(cd.remaining_seconds)}s remaining
                </span>
              )}
            </div>
            {!cd.can_execute && (
              <div className="cooldown-bar">
                <div
                  className="cooldown-progress"
                  style={{
                    width: `${100 - (cd.remaining_seconds / (cd.cooldown_minutes * 60)) * 100}%`
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Triggers index panel - shows all spell triggers by type
 */
function TriggersPanel({ triggers }: { triggers: TriggersIndex | undefined }) {
  if (!triggers) {
    return (
      <div className="triggers-panel empty">
        <p>Loading triggers...</p>
      </div>
    );
  }

  const sections = [
    { key: 'need_triggers', label: 'Need Triggers', color: '#4ecdc4' },
    { key: 'affect_triggers', label: 'Affect Triggers', color: '#e91e8c' },
    { key: 'event_triggers', label: 'Event Triggers', color: '#f39c12' },
    { key: 'timer_triggers', label: 'Timer Triggers', color: '#9b59b6' },
    { key: 'manual_triggers', label: 'Manual Triggers', color: '#27ae60' },
  ] as const;

  return (
    <div className="triggers-panel">
      {sections.map(section => {
        const items = triggers[section.key];
        return (
          <section key={section.key} className="trigger-section">
            <h3 style={{ borderLeftColor: section.color }}>
              {section.label} ({items.length})
            </h3>
            {items.length > 0 ? (
              <div className="trigger-list">
                {items.map((item, idx) => (
                  <div key={idx} className="trigger-entry">
                    <span className="trigger-spell">{item.spell}</span>
                    <span className="trigger-target">{item.trigger.target || '-'}</span>
                    {item.trigger.condition && (
                      <span className="trigger-condition">{item.trigger.condition}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="no-triggers">No {section.label.toLowerCase()}</p>
            )}
          </section>
        );
      })}
    </div>
  );
}

/**
 * Spell editor panel - compile and validate spell source
 */
function SpellEditorPanel() {
  const queryClient = useQueryClient();
  const [source, setSource] = useState(`' Example Spell
NAME "my-spell"
AUTHOR "admin"
DESCRIPTION "A sample spell"
PRIORITY 50
COOLDOWN 30
TAG "example"

ON MANUAL "Test Button"

' Body
LOG "Spell executed!"
`);
  const [compileResult, setCompileResult] = useState<CompileResponse | null>(null);

  const compileMutation = useMutation({
    mutationFn: ({ source, validateOnly }: { source: string; validateOnly: boolean }) =>
      grimoireApi.compileSpell(source, validateOnly),
    onSuccess: (response) => {
      setCompileResult(response.data);
      if (response.data.success) {
        queryClient.invalidateQueries({ queryKey: ['grimoire-spells'] });
      }
    },
  });

  return (
    <div className="spell-editor-panel">
      <div className="editor-header">
        <h2>Spell Editor</h2>
        <p className="editor-note">
          Write ThymosBASIC spells here. Use "Validate" to check syntax, "Load" to add to registry.
        </p>
      </div>

      <div className="editor-container">
        <textarea
          className="spell-source-editor"
          value={source}
          onChange={(e) => setSource(e.target.value)}
          spellCheck={false}
        />
      </div>

      <div className="editor-actions">
        <button
          className="validate-btn"
          onClick={() => compileMutation.mutate({ source, validateOnly: true })}
          disabled={compileMutation.isPending}
        >
          {compileMutation.isPending ? 'Validating...' : 'Validate'}
        </button>
        <button
          className="load-btn"
          onClick={() => compileMutation.mutate({ source, validateOnly: false })}
          disabled={compileMutation.isPending}
        >
          {compileMutation.isPending ? 'Loading...' : 'Load into Registry'}
        </button>
      </div>

      {compileResult && (
        <div className={`compile-result ${compileResult.success ? 'success' : 'error'}`}>
          {compileResult.success ? (
            <>
              <div className="result-header success">
                <span className="result-icon">✓</span>
                Spell "{compileResult.spell_name}" compiled successfully
              </div>
              <div className="result-stats">
                <span>{compileResult.trigger_count} triggers</span>
                <span>{compileResult.statement_count} statements</span>
              </div>
            </>
          ) : (
            <div className="result-header error">
              <span className="result-icon">✗</span>
              {compileResult.error}
            </div>
          )}
          {compileResult.warnings.length > 0 && (
            <div className="compile-warnings">
              <h4>Warnings:</h4>
              <ul>
                {compileResult.warnings.map((w, idx) => (
                  <li key={idx}>{w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function Grimoire() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('spells');
  const [selectedSpell, setSelectedSpell] = useState<string | null>(null);
  const [castResult, setCastResult] = useState<CastResponse | null>(null);

  // Queries
  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['grimoire-status'],
    queryFn: () => grimoireApi.getStatus().then(r => r.data),
    refetchInterval: 10000,
  });

  const { data: spells } = useQuery({
    queryKey: ['grimoire-spells'],
    queryFn: () => grimoireApi.listSpells().then(r => r.data),
  });

  const { data: spellDetail } = useQuery({
    queryKey: ['grimoire-spell', selectedSpell],
    queryFn: () => selectedSpell
      ? grimoireApi.getSpell(selectedSpell).then(r => r.data)
      : null,
    enabled: !!selectedSpell,
  });

  const { data: spellSource } = useQuery({
    queryKey: ['grimoire-spell-source', selectedSpell],
    queryFn: () => selectedSpell
      ? grimoireApi.getSpellSource(selectedSpell).then(r => r.data)
      : null,
    enabled: !!selectedSpell,
  });

  const { data: executionLog } = useQuery({
    queryKey: ['grimoire-execution-log'],
    queryFn: () => grimoireApi.getExecutionLog(50).then(r => r.data),
    enabled: activeTab === 'execution-log',
  });

  const { data: cooldowns, refetch: refetchCooldowns } = useQuery({
    queryKey: ['grimoire-cooldowns'],
    queryFn: () => grimoireApi.getCooldowns().then(r => r.data),
    enabled: activeTab === 'cooldowns' || activeTab === 'spells',
    refetchInterval: activeTab === 'cooldowns' ? 5000 : undefined,
  });

  const { data: triggers } = useQuery({
    queryKey: ['grimoire-triggers'],
    queryFn: () => grimoireApi.getTriggers().then(r => r.data),
    enabled: activeTab === 'triggers',
  });

  // Mutations
  const castMutation = useMutation({
    mutationFn: (spellName: string) => grimoireApi.castSpell(spellName),
    onSuccess: (response) => {
      setCastResult(response.data);
      queryClient.invalidateQueries({ queryKey: ['grimoire-spell', selectedSpell] });
      refetchCooldowns();
    },
  });

  const reloadMutation = useMutation({
    mutationFn: () => grimoireApi.reloadSpells(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['grimoire-spells'] });
      queryClient.invalidateQueries({ queryKey: ['grimoire-status'] });
      refetchStatus();
    },
  });

  return (
    <div className="grimoire-page">
      <header className="page-header">
        <div className="header-content">
          <h1>Grimoire</h1>
          <p className="subtitle">ThymosBASIC Spell System</p>
        </div>
        <div className="header-actions">
          <GrimoireStatusBadge status={status} />
          <button
            className="reload-btn"
            onClick={() => reloadMutation.mutate()}
            disabled={reloadMutation.isPending}
          >
            {reloadMutation.isPending ? 'Reloading...' : '↻ Reload Spells'}
          </button>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="grimoire-tabs">
        <button
          className={activeTab === 'spells' ? 'active' : ''}
          onClick={() => setActiveTab('spells')}
        >
          Spells
          {spells && <span className="tab-badge">{spells.length}</span>}
        </button>
        <button
          className={activeTab === 'execution-log' ? 'active' : ''}
          onClick={() => setActiveTab('execution-log')}
        >
          Execution Log
        </button>
        <button
          className={activeTab === 'cooldowns' ? 'active' : ''}
          onClick={() => setActiveTab('cooldowns')}
        >
          Cooldowns
        </button>
        <button
          className={activeTab === 'triggers' ? 'active' : ''}
          onClick={() => setActiveTab('triggers')}
        >
          Triggers
        </button>
        <button
          className={activeTab === 'editor' ? 'active' : ''}
          onClick={() => setActiveTab('editor')}
        >
          Editor
        </button>
      </nav>

      {/* Tab Content */}
      <div className="tab-content">
        {activeTab === 'spells' && (
          <div className="spells-tab">
            <div className="spells-list-panel">
              <h3>Loaded Spells</h3>
              <div className="spells-list">
                {spells?.length ? (
                  spells.map(spell => (
                    <SpellListItem
                      key={spell.name}
                      spell={spell}
                      selected={selectedSpell === spell.name}
                      onClick={() => {
                        setSelectedSpell(spell.name);
                        setCastResult(null);
                      }}
                    />
                  ))
                ) : (
                  <p className="empty">No spells loaded.</p>
                )}
              </div>
            </div>
            <SpellDetailPanel
              spell={spellDetail || null}
              source={spellSource || null}
              onCast={() => selectedSpell && castMutation.mutate(selectedSpell)}
              castLoading={castMutation.isPending}
              castResult={castResult}
            />
          </div>
        )}

        {activeTab === 'execution-log' && (
          <ExecutionLogPanel entries={executionLog} />
        )}

        {activeTab === 'cooldowns' && (
          <CooldownsPanel cooldowns={cooldowns} />
        )}

        {activeTab === 'triggers' && (
          <TriggersPanel triggers={triggers} />
        )}

        {activeTab === 'editor' && (
          <SpellEditorPanel />
        )}
      </div>

      {/* Stats Footer */}
      {status && (
        <footer className="grimoire-footer">
          <span className="stat">
            <strong>{status.spells_loaded}</strong> spells loaded
          </span>
          <span className="stat">
            <strong>{status.recent_executions}</strong> recent executions
          </span>
          {status.spells_directory && (
            <span className="stat directory">
              {status.spells_directory}
            </span>
          )}
        </footer>
      )}
    </div>
  );
}
