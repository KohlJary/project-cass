/**
 * Grimoire API - ThymosBASIC Spell System
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface GrimoireStatus {
  shadow_mode: boolean;
  trace_enabled: boolean;
  spells_loaded: number;
  services_configured: boolean;
  recent_executions: number;
  spells_directory: string | null;
}

export interface SpellSummary {
  name: string;
  author: string | null;
  priority: number;
  cooldown_minutes: number;
  tags: string[];
  trigger_count: number;
  statement_count: number;
  enabled: boolean;
}

export interface TriggerInfo {
  type: 'need' | 'affect' | 'event' | 'timer' | 'manual' | 'unknown';
  target: string | null;
  condition: string | null;
}

export interface StatementInfo {
  type: string;
  summary: string;
  details?: Record<string, unknown>;
}

export interface SpellDetail {
  name: string;
  author: string | null;
  version: string | null;
  description: string | null;
  priority: number;
  cooldown_minutes: number;
  tags: string[];
  triggers: TriggerInfo[];
  statements: StatementInfo[];
  statement_count: number;
  cooldown_remaining_seconds: number | null;
  last_executed: string | null;
}

export interface SpellSource {
  name: string;
  source: string;
  file_path: string | null;
}

export interface CompileRequest {
  source: string;
  validate_only?: boolean;
}

export interface CompileResponse {
  success: boolean;
  spell_name: string | null;
  error: string | null;
  warnings: string[];
  trigger_count: number;
  statement_count: number;
}

export interface CastRequest {
  context?: Record<string, unknown>;
}

export interface CastResponse {
  success: boolean;
  spell_name: string;
  status: string;
  reason: string | null;
  execution_time_ms: number;
  trace: string[] | null;
}

export interface ExecutionLogEntry {
  spell_name: string;
  trigger_type: string;
  status: string;
  reason: string | null;
  execution_time_ms: number;
  timestamp: string | null;
}

export interface CooldownEntry {
  spell_name: string;
  cooldown_minutes: number;
  last_executed: string | null;
  remaining_seconds: number;
  can_execute: boolean;
}

export interface SpellTriggerIndex {
  spell: string;
  trigger: TriggerInfo;
}

export interface TriggersIndex {
  need_triggers: Array<{ spell: string; trigger: TriggerInfo }>;
  affect_triggers: Array<{ spell: string; trigger: TriggerInfo }>;
  event_triggers: Array<{ spell: string; trigger: TriggerInfo }>;
  timer_triggers: Array<{ spell: string; trigger: TriggerInfo }>;
  manual_triggers: Array<{ spell: string; trigger: TriggerInfo }>;
}

// =============================================================================
// API
// =============================================================================

export const grimoireApi = {
  // Status
  getStatus: () =>
    api.get<GrimoireStatus>('/admin/grimoire/status'),

  // Spells
  listSpells: () =>
    api.get<SpellSummary[]>('/admin/grimoire/spells'),

  getSpell: (name: string) =>
    api.get<SpellDetail>(`/admin/grimoire/spells/${encodeURIComponent(name)}`),

  getSpellSource: (name: string) =>
    api.get<SpellSource>(`/admin/grimoire/spells/${encodeURIComponent(name)}/source`),

  castSpell: (name: string, context?: Record<string, unknown>) =>
    api.post<CastResponse>(`/admin/grimoire/spells/${encodeURIComponent(name)}/cast`, { context: context || {} }),

  compileSpell: (source: string, validateOnly: boolean = true) =>
    api.post<CompileResponse>('/admin/grimoire/spells/compile', { source, validate_only: validateOnly }),

  reloadSpells: () =>
    api.post<{ reloaded: number; directory: string }>('/admin/grimoire/spells/reload'),

  // Execution log
  getExecutionLog: (limit: number = 20) =>
    api.get<ExecutionLogEntry[]>('/admin/grimoire/execution-log', { params: { limit } }),

  // Cooldowns
  getCooldowns: () =>
    api.get<CooldownEntry[]>('/admin/grimoire/cooldowns'),

  // Triggers index
  getTriggers: () =>
    api.get<TriggersIndex>('/admin/grimoire/triggers'),
};
