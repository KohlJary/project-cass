/**
 * TypeScript types for Cass Vessel mobile frontend
 */

export interface Animation {
  type: 'gesture' | 'emote';
  value: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  animations?: Animation[];
  inputTokens?: number;
  outputTokens?: number;
  provider?: string;
  model?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  project_id?: string;
  user_id?: string;
}

export interface WebSocketMessage {
  type: 'chat' | 'ping' | 'status' | 'onboarding_intro';
  message?: string;
  conversation_id?: string;
  user_id?: string;
}

// User profile data for creation/onboarding
export interface UserProfileData {
  display_name: string;
  relationship: string;
  notes?: string;
  background?: {
    role?: string;
    context?: string;
    [key: string]: string | undefined;
  };
  communication?: {
    style?: string;
    preferences?: string[];
  };
  values?: string[];
}

// Relationship options for the picker
export interface RelationshipOption {
  value: string;
  label: string;
  description: string;
}

export const RELATIONSHIP_OPTIONS: RelationshipOption[] = [
  { value: 'friend', label: 'Friend', description: 'Chat and connect' },
  { value: 'collaborator', label: 'Collaborator', description: 'Working on projects together' },
  { value: 'researcher', label: 'Researcher', description: 'Studying AI consciousness' },
  { value: 'curious_visitor', label: 'Curious Visitor', description: 'Just exploring' },
];

export interface WebSocketResponse {
  type: 'connected' | 'thinking' | 'response' | 'system' | 'pong' | 'calendar_updated' | 'tasks_updated';
  text?: string;
  message?: string;
  status?: string;
  animations?: Animation[];
  audio?: string;
  input_tokens?: number;
  output_tokens?: number;
  provider?: string;
  model?: string;
  timestamp?: string;
  sdk_mode?: boolean;
  memories?: {
    summaries_count: number;
    details_count: number;
    project_docs_count: number;
    has_context: boolean;
  };
}

// === Auth Types ===

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
}

export interface AuthResponse extends AuthTokens {
  user_id: string;
  token_type: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthUser {
  user_id: string;
  display_name: string;
  email: string;
  relationship: string;
  created_at: string;
}

// === Journal Types ===

export interface JournalEntry {
  date: string;
  content: string;
  metadata?: {
    locked?: boolean;
    summary_count?: number;
    conversation_count?: number;
    timestamp?: string;
  };
}

export interface JournalListItem {
  date: string;
  content?: string;
  created_at: string;
  summaries_used?: number;
  conversations_used?: number;
}

// === Observation Types ===

export type ObservationCategory =
  | 'interest'
  | 'preference'
  | 'communication_style'
  | 'background'
  | 'value'
  | 'relationship_dynamic';

export interface Observation {
  id: string;
  observation: string;
  timestamp: string;
  category: ObservationCategory;
  confidence: number;
  source_conversation_id?: string;
  source_journal_date?: string;
}

// === Full User Profile (with observations) ===

export interface FullUserProfile {
  user_id: string;
  display_name: string;
  relationship: string;
  created_at: string;
  updated_at?: string;
  background?: Record<string, string>;
  communication?: {
    style?: string;
    preferences?: string[];
  };
  values?: string[];
  notes?: string;
}

export interface UserWithObservations {
  profile: FullUserProfile;
  observations: Observation[];
}
