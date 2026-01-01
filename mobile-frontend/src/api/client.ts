/**
 * HTTP API client for Cass Vessel backend
 */

import {
  Conversation,
  Message,
  UserProfileData,
  AuthResponse,
  AuthTokens,
  AuthUser,
  RegisterRequest,
  LoginRequest,
  JournalEntry,
  JournalListItem,
  UserWithObservations,
  ConversationObservations,
  UserJournalsResponse,
} from './types';
import { config } from '../config';

// Use configured API base URL
const API_BASE = config.apiBaseUrl;

// Token getter function - will be set by auth store
let getAccessToken: (() => string | null) | null = null;
let onTokenRefreshNeeded: (() => Promise<boolean>) | null = null;

export function setAuthTokenGetter(getter: () => string | null) {
  getAccessToken = getter;
}

export function setTokenRefreshHandler(handler: () => Promise<boolean>) {
  onTokenRefreshNeeded = handler;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(path: string, options?: RequestInit & { skipAuth?: boolean }): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options?.headers as Record<string, string>,
    };

    // Add Authorization header if we have a token and this isn't an auth endpoint
    if (!options?.skipAuth && getAccessToken) {
      const token = getAccessToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    }

    let response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    // Handle 401 - try to refresh token and retry
    if (response.status === 401 && onTokenRefreshNeeded && !options?.skipAuth) {
      const refreshed = await onTokenRefreshNeeded();
      if (refreshed) {
        // Retry with new token
        const newToken = getAccessToken?.();
        if (newToken) {
          headers['Authorization'] = `Bearer ${newToken}`;
        }
        response = await fetch(`${this.baseUrl}${path}`, {
          ...options,
          headers,
        });
      }
    }

    if (!response.ok) {
      const errorBody = await response.text().catch(() => '');
      throw new Error(`API error: ${response.status} ${response.statusText}${errorBody ? ` - ${errorBody}` : ''}`);
    }

    return response.json();
  }

  // === Auth Endpoints ===

  async register(data: RegisterRequest): Promise<AuthResponse> {
    return this.fetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
      skipAuth: true,
    });
  }

  async login(data: LoginRequest): Promise<AuthResponse> {
    return this.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: data.email,
        password: data.password,
      }),
      skipAuth: true,
    });
  }

  async refreshToken(refreshToken: string): Promise<AuthTokens> {
    return this.fetch('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      skipAuth: true,
    });
  }

  async getMe(): Promise<AuthUser> {
    return this.fetch('/auth/me');
  }

  // Conversations
  async listConversations(userId?: string): Promise<Conversation[]> {
    const params = userId ? `?user_id=${userId}` : '';
    const data = await this.fetch<{ conversations: Conversation[]; count: number }>(`/conversations${params}`);
    return data.conversations;
  }

  async getConversation(id: string): Promise<{ conversation: any; messages: Message[] }> {
    return this.fetch(`/conversations/${id}`);
  }

  async createConversation(title?: string, userId?: string): Promise<{ id: string; title: string }> {
    return this.fetch('/conversations/new', {
      method: 'POST',
      body: JSON.stringify({ title, user_id: userId }),
    });
  }

  async getContinuousConversation(): Promise<{
    id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    is_continuous: boolean;
  }> {
    return this.fetch('/conversations/continuous');
  }

  async renameConversation(id: string, title: string): Promise<{ id: string; title: string }> {
    return this.fetch(`/conversations/${id}/title`, {
      method: 'PUT',
      body: JSON.stringify({ title }),
    });
  }

  async getConversationSummary(id: string): Promise<{ working_summary: string | null; summaries: any[]; count: number }> {
    return this.fetch(`/conversations/${id}/summaries`);
  }

  async getConversationMessages(
    id: string,
    options?: { limit?: number; sinceHours?: number }
  ): Promise<{ messages: Message[]; count: number }> {
    const params = new URLSearchParams();
    if (options?.limit) params.append('limit', options.limit.toString());
    if (options?.sinceHours) params.append('since_hours', options.sinceHours.toString());
    const query = params.toString() ? `?${params.toString()}` : '';
    return this.fetch(`/conversations/${id}/messages${query}`);
  }

  async getConversationObservations(id: string): Promise<ConversationObservations> {
    return this.fetch(`/conversations/${id}/observations`);
  }

  async triggerSummarization(id: string): Promise<{ status: string; message: string }> {
    return this.fetch(`/conversations/${id}/summarize`, {
      method: 'POST',
    });
  }

  // Status
  async getStatus(): Promise<{ online: boolean; sdk_mode: boolean }> {
    return this.fetch('/status');
  }

  // Users
  async listUsers(): Promise<{ user_id: string; display_name: string; relationship: string }[]> {
    const data = await this.fetch<{ users: { user_id: string; display_name: string; relationship: string }[] }>('/users');
    return data.users;
  }

  async getUser(userId: string): Promise<{ user_id: string; display_name: string; relationship: string }> {
    const data = await this.fetch<{ profile: { user_id: string; display_name: string; relationship: string } }>(`/users/${userId}`);
    return data.profile;
  }

  async createUser(profile: UserProfileData): Promise<{ user_id: string; display_name: string }> {
    const data = await this.fetch<{ user: { user_id: string; display_name: string } }>('/users', {
      method: 'POST',
      body: JSON.stringify(profile),
    });
    return data.user;
  }

  async setCurrentUser(userId: string): Promise<void> {
    await this.fetch('/users/current', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    });
  }

  async deleteUser(userId: string): Promise<void> {
    await this.fetch(`/users/${userId}`, {
      method: 'DELETE',
    });
  }

  async getUserWithObservations(userId: string): Promise<UserWithObservations> {
    return this.fetch(`/users/${userId}`);
  }

  // === Journal Endpoints ===

  async listJournals(limit?: number): Promise<{ journals: JournalListItem[]; count: number }> {
    const params = limit ? `?limit=${limit}` : '';
    return this.fetch(`/journal${params}`);
  }

  async getJournal(date: string): Promise<JournalEntry> {
    return this.fetch(`/journal/${date}`);
  }

  // === User Journal Endpoints (Cass's journals about specific users) ===

  async getUserJournals(userId: string, limit?: number): Promise<UserJournalsResponse> {
    const params = limit ? `?limit=${limit}` : '';
    return this.fetch(`/users/${userId}/journals${params}`);
  }
}

export const apiClient = new ApiClient();
