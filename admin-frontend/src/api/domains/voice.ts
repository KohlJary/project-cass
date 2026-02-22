/**
 * Voice API - STT and TTS endpoints
 */
import { api } from './base';

export interface TranscribeRequest {
  audio: string;  // Base64-encoded audio
  format: string; // wav, webm, mp3, etc.
  language?: string;
}

export interface SpeakerInfo {
  user_id: string | null;
  display_name: string | null;
  confidence: number;
  confidence_level: 'high' | 'medium' | 'low' | 'none';
}

export interface TranscribeResponse {
  text: string;
  language: string;
  duration: number;
  speaker?: SpeakerInfo;
}

export interface TTSRequest {
  text: string;
  provider?: 'piper' | 'xtts';
  voice?: string;
  format?: 'mp3' | 'wav';
}

export interface STTStatus {
  available: boolean;
  model: string | null;
  loaded: boolean;
  error?: string;
}

export interface TTSSettings {
  current_provider: 'piper' | 'xtts';
  available_providers: string[];
  voices: Record<string, Record<string, string>>;
}

// Voice Identification types
export interface EnrollmentSession {
  session_id: string;
  required_samples: number;
  phrases: string[];
  expires_at: string;
}

export interface AddSampleResponse {
  accepted: boolean;
  quality_score: number;
  sample_count: number;
  required_samples: number;
  feedback: string;
}

export interface CompleteEnrollmentResponse {
  success: boolean;
  enrollment_id: string;
  sample_count: number;
  quality_score: number;
}

export interface EnrollmentStatus {
  enrolled: boolean;
  sample_count?: number;
  quality_score?: number;
  created_at?: string;
}

export interface IdentifyResponse {
  identified: boolean;
  user_id?: string;
  display_name?: string;
  confidence: number;
  confidence_level: 'high' | 'medium' | 'low' | 'none';
}

export const voiceApi = {
  /**
   * Transcribe audio to text using Whisper
   */
  transcribe: (audio: string, format: string, language?: string, identifySpeaker?: boolean) =>
    api.post<TranscribeResponse>('/admin/stt/transcribe', {
      audio,
      format,
      language,
      identify_speaker: identifySpeaker,
    }),

  /**
   * Check STT service status
   */
  getSTTStatus: () =>
    api.get<STTStatus>('/admin/stt/status'),

  /**
   * Synthesize text to speech
   * Note: TTS is typically returned inline with chat responses,
   * but this endpoint can be used for standalone synthesis
   */
  synthesize: (text: string, provider?: string, voice?: string, format?: string) =>
    api.post<Blob>('/admin/tts/synthesize', {
      text,
      provider,
      voice,
      format,
    }, { responseType: 'blob' }),

  /**
   * Get TTS settings and available providers
   */
  getTTSSettings: () =>
    api.get<TTSSettings>('/admin/tts/settings'),

  /**
   * Set the active TTS provider
   */
  setTTSProvider: (provider: 'piper' | 'xtts') =>
    api.post<{ success: boolean; provider: string }>('/admin/tts/settings/provider', {
      provider,
    }),

  // =========================================================================
  // Voice Identification / Enrollment
  // =========================================================================

  /**
   * Get enrollment phrases for voice enrollment
   */
  getEnrollmentPhrases: () =>
    api.get<{ phrases: string[]; count: number }>('/admin/voice/phrases'),

  /**
   * Check enrollment status for a user
   */
  getEnrollmentStatus: (userId: string) =>
    api.get<EnrollmentStatus>(`/admin/voice/enroll/status?user_id=${userId}`),

  /**
   * Start a voice enrollment session
   */
  startEnrollment: (userId: string) =>
    api.post<EnrollmentSession>(`/admin/voice/enroll/start?user_id=${userId}`),

  /**
   * Add a voice sample to an enrollment session
   */
  addEnrollmentSample: (sessionId: string, phraseIndex: number, audio: string) =>
    api.post<AddSampleResponse>('/admin/voice/enroll/sample', {
      session_id: sessionId,
      phrase_index: phraseIndex,
      audio,
    }),

  /**
   * Complete enrollment and generate voiceprint
   */
  completeEnrollment: (sessionId: string) =>
    api.post<CompleteEnrollmentResponse>('/admin/voice/enroll/complete', {
      session_id: sessionId,
    }),

  /**
   * Delete voice enrollment for a user
   */
  deleteEnrollment: (userId: string) =>
    api.delete<{ success: boolean; message: string }>(`/admin/voice/enroll?user_id=${userId}`),

  /**
   * Identify speaker from audio
   */
  identifySpeaker: (audio: string) =>
    api.post<IdentifyResponse>('/admin/voice/identify', { audio }),
};
