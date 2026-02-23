/**
 * Music API domain - Cass's music compositions
 */

import { api, API_BASE } from './base';

// Types
export interface MusicMetadata {
  bpm: number | null;
  duration: number | null;
  genres: string | null;
  keyscale: string | null;
  timesignature: string | null;
  language: string | null;
  seed_value: string | null;
  lm_model: string | null;
  dit_model: string | null;
}

export interface MusicComposition {
  id: string;
  created_at: string;
  title: string | null;
  prompt: string;
  lyrics: string | null;
  purpose: 'whistle' | 'song' | 'ambient' | 'general';
  audio_path: string | null;
  audio_url: string | null;
  status: 'completed' | 'failed' | 'pending';
  error: string | null;
  generation_info: string | null;
  metadata: MusicMetadata | null;
}

export interface MusicListResponse {
  count: number;
  compositions: MusicComposition[];
  genres: string[];
}

export interface MusicServiceStatus {
  available: boolean;
  api_url: string;
}

// API functions
export const musicApi = {
  /**
   * List compositions with optional filtering
   */
  list: (params?: {
    purpose?: string;
    genre?: string;
    limit?: number;
  }) => api.get<MusicListResponse>('/music/compositions', { params }),

  /**
   * Get a single composition by ID
   */
  get: (id: string) => api.get<MusicComposition>(`/music/compositions/${id}`),

  /**
   * Get list of available genres
   */
  getGenres: () => api.get<string[]>('/music/genres'),

  /**
   * Check if ACE-Step service is running
   */
  checkService: () => api.get<MusicServiceStatus>('/music/status'),

  /**
   * Get audio URL for a composition
   */
  getAudioUrl: (composition: MusicComposition): string | null => {
    if (composition.audio_path) {
      // Convert local path to API URL
      const filename = composition.audio_path.split('/').pop();
      return `${API_BASE}/music/audio/${filename}`;
    }
    return composition.audio_url;
  },
};
