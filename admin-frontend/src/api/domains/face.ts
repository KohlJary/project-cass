/**
 * Face API - Face identification and enrollment endpoints
 */
import { api } from './base';

export interface FaceStatus {
  available: boolean;
  model: string | null;
  error?: string;
}

export interface EnrollmentSession {
  session_id: string;
  required_samples: number;
  instructions: string[];
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
  enrollment_id?: string;
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

export const faceApi = {
  /**
   * Check face identification service status
   */
  getStatus: () =>
    api.get<FaceStatus>('/admin/face/status'),

  /**
   * Get enrollment instructions
   */
  getInstructions: () =>
    api.get<{ instructions: string[]; count: number }>('/admin/face/instructions'),

  /**
   * Check enrollment status for a user
   */
  getEnrollmentStatus: (userId: string) =>
    api.get<EnrollmentStatus>(`/admin/face/enroll/status?user_id=${userId}`),

  /**
   * Start a face enrollment session
   */
  startEnrollment: (userId: string) =>
    api.post<EnrollmentSession>(`/admin/face/enroll/start?user_id=${userId}`),

  /**
   * Add a face sample to an enrollment session
   */
  addEnrollmentSample: (sessionId: string, imageBase64: string) =>
    api.post<AddSampleResponse>('/admin/face/enroll/sample', {
      session_id: sessionId,
      image: imageBase64,
    }),

  /**
   * Complete enrollment and generate faceprint
   */
  completeEnrollment: (sessionId: string) =>
    api.post<CompleteEnrollmentResponse>('/admin/face/enroll/complete', {
      session_id: sessionId,
    }),

  /**
   * Delete face enrollment for a user
   */
  deleteEnrollment: (userId: string) =>
    api.delete<{ success: boolean; message: string }>(`/admin/face/enroll?user_id=${userId}`),

  /**
   * Identify face from image
   */
  identifyFace: (imageBase64: string) =>
    api.post<IdentifyResponse>('/admin/face/identify', { image: imageBase64 }),
};
