/**
 * API Domains - Barrel file re-exporting all domain APIs
 *
 * This file provides clean imports from domain-specific modules.
 * Each domain module contains related API endpoints grouped logically.
 */

// Base exports (axios instance, API_BASE)
export { api, API_BASE } from './base';

// Core (Daemons, Auth, Users, System)
export { daemonsApi, authApi, usersApi, systemApi } from './core';

// Memory (Memory, Journals, Conversations)
export { memoryApi, journalsApi, conversationsApi } from './memory';

// Self-Model (Self-model, Sentience, Development)
export { selfModelApi, sentienceApi, developmentApi } from './self-model';

// Knowledge (Wiki, Research, Goals)
export {
  wikiApi,
  researchApi,
  researchNotesApi,
  autonomousResearchApi,
  goalsApi,
} from './knowledge';

// Thymos (Homeostatic emotional system)
export {
  thymosApi,
  type ThymosAffectState,
  type ThymosNeedState,
  type ThymosFeltState,
  type ThymosState,
  type ThymosSuggestion,
  type ThymosSnapshot,
  type ThymosHealth,
  type ThymosEvent,
  type ThymosCareEvent,
  type AutoCareSettings,
  type ThymosShadowLogEntry,
  type ThymosShadowLogStats,
  type ThymosNeedActionMap,
  type ThymosTimingConfig,
} from './thymos';

// Grimoire (Spell system)
export {
  grimoireApi,
  type GrimoireStatus,
  type SpellSummary,
  type TriggerInfo,
  type StatementInfo,
  type SpellDetail,
  type SpellSource,
  type CompileRequest,
  type CompileResponse,
  type CastRequest,
  type CastResponse,
  type ExecutionLogEntry,
  type CooldownEntry,
  type SpellTriggerIndex,
  type TriggersIndex,
} from './grimoire';

// Scheduler (Background task orchestration)
export {
  schedulerApi,
  type SchedulerBudgetCategory,
  type SchedulerBudgetStatus,
  type SchedulerSystemTask,
  type SchedulerQueueStatus,
  type SchedulerStatus,
  type SchedulerHistoryEntry,
  type SchedulerTaskConfig,
  type ApprovalItem,
} from './scheduler';

// State (Global State Bus)
export {
  stateApi,
  type EmotionalState,
  type ActivityState,
  type CoherenceState,
  type RelationalState,
  type GlobalState,
  type StateEvent,
  type EmotionalArcPoint,
  type ActivityTimelineEvent,
  type DailyReportTimelineEvent,
  type DailyReportCategory,
  type DailyActivityReport,
} from './state';

// Outreach (Drafts, Review Queue)
export {
  outreachApi,
  type OutreachDraft,
  type TrackRecord,
  type OutreachStats,
} from './outreach';

// Testing (Consciousness Health, Solo Reflection)
export { testingApi, soloReflectionApi } from './testing';

// Art Study
export {
  artStudyApi,
  type ArtistResponse,
  type ArtworkResponse,
  type StudyResponse,
  type SynthesisResponse,
  type ArtistObservation,
  type AdoptedElementResponse,
  type PersonalStyleResponse,
  type HouseStyleStats,
  type HouseStyleCreatedPiece,
} from './art-study';

// Narrative (Threads, Questions)
export {
  narrativeApi,
  type ThreadResponse,
  type QuestionResponse,
  type NarrativeStats,
} from './narrative';

// Chain (Prompt chain composition)
export {
  chainApi,
  type NodeTemplateResponse,
  type ConditionModel,
  type ChainNodeResponse,
  type ChainResponse,
  type ChainDetailResponse,
  type ContextSection,
  type PreviewResponse,
} from './chain';

// Music (Cass's compositions)
export {
  musicApi,
  type MusicMetadata,
  type MusicComposition,
  type MusicListResponse,
  type MusicServiceStatus,
} from './music';

// RSS (Feed subscriptions)
export {
  rssApi,
  type RSSFeed,
  type RSSItem,
  type RSSStatus,
  type FeedCreateRequest,
  type FeedUpdateRequest,
  type CheckResult,
  type CheckAllResult,
} from './rss';

// Daily Activity (Aggregated daily dashboard)
// Note: EmotionalArcPoint not re-exported here to avoid conflict with state module
// Import directly from './daily-activity' if needed
export {
  dailyActivityApi,
  type ActivityItem,
  type CategorySummary,
  type TokenSummary,
  type DailyActivityResponse,
  type DailySummaryResponse,
  type DateRangeSummaryResponse,
  type ActivitySource,
  type AvailableSourcesResponse,
} from './daily-activity';

// Voice (STT/TTS)
export {
  voiceApi,
  type TranscribeRequest,
  type TranscribeResponse,
  type TTSRequest,
  type STTStatus,
} from './voice';

// Miscellaneous APIs
export {
  exportApi,
  schedulesApi,
  githubApi,
  usageApi,
  filesApi,
  projectsApi,
  roadmapApi,
  rhythmApi,
  sessionsApi,
  settingsApi,
  dreamsApi,
  feedbackApi,
  genesisApi,
  geocassApi,
  homepageApi,
  attachmentsApi,
  galleryApi,
  promptConfigApi,
  llmConfigApi,
  type GeneratedImage,
  type ImageRevisionsResponse,
  type ModelAssignment,
  type AvailableModel,
} from './misc';
