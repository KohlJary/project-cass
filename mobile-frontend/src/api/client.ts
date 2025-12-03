/**
 * HTTP API client for Cass Vessel backend
 */

import { Conversation, Message, UserProfileData } from './types';

// Same base URL as WebSocket, just HTTP
const API_BASE = 'https://pushing-instructions-weather-ron.trycloudflare.com';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE) {
    this.baseUrl = baseUrl;
  }

  private async fetch<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    return response.json();
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

  async getConversationSummary(id: string): Promise<{ working_summary: string | null; summaries: any[]; count: number }> {
    return this.fetch(`/conversations/${id}/summaries`);
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
}

export const apiClient = new ApiClient();
