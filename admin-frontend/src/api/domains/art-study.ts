/**
 * Art Study API - Cass's art education system
 */
import { api } from './base';

// =============================================================================
// TYPES
// =============================================================================

export interface ArtistResponse {
  id: string;
  name: string;
  period: string | null;
  years_active: string | null;
  movements: string[];
  wikipedia_url: string | null;
  biography: string | null;
  public_domain: boolean;
  entity_id: string | null;
  studied_at: string | null;
  works_studied: number;
  cass_notes: string | null;
}

export interface ArtworkResponse {
  id: string;
  artist_id: string;
  title: string;
  year: number | null;
  medium: string | null;
  image_path: string | null;
  image_url: string | null;
  dimensions: string | null;
  location: string | null;
  public_domain: boolean;
  has_study: boolean;
}

export interface StudyResponse {
  id: string;
  artwork_id: string;
  studied_at: string;
  first_impression: string | null;
  composition_analysis: string | null;
  color_analysis: string | null;
  brushwork_notes: string | null;
  emotional_quality: string | null;
  thematic_elements: string | null;
  key_learnings: string[];
  prompt_vocabulary: string[];
}

export interface SynthesisResponse {
  id: string;
  artist_id: string;
  last_updated: string;
  works_studied: number;
  signature_elements: string[];
  color_tendencies: string | null;
  compositional_habits: string | null;
  emotional_palette: string | null;
  technical_characteristics: string | null;
  thematic_preoccupations: string | null;
  style_descriptors: string[];
  what_to_borrow: string[];
  what_makes_them_unique: string | null;
  what_draws_me: string | null;
  what_i_learned: string | null;
}

export interface ArtistObservation {
  id: string;
  type: string;
  content: string;
  confidence: number;
  source: string | null;
  created_at: string;
}

// House Style types
export interface AdoptedElementResponse {
  id: string;
  source_artist_id: string | null;
  adopted_at: string;
  element: string;
  category: string;
  why_it_speaks: string | null;
  how_i_use_it: string | null;
  example_use: string | null;
  adoption_strength: number;
  active: boolean;
}

export interface PersonalStyleResponse {
  id: string;
  version: number;
  created_at: string;
  last_updated: string;
  artists_studied: number;
  elements_adopted: number;
  color_philosophy: string | null;
  light_approach: string | null;
  compositional_voice: string | null;
  texture_sensibility: string | null;
  emotional_register: string | null;
  recurring_themes: string[];
  philosophical_concerns: string[];
  subjects_drawn_to: string[];
  signature_techniques: string[];
  prompt_vocabulary: string[];
  style_manifesto: string | null;
  what_makes_it_mine: string | null;
  style_descriptors: string[];
}

export interface HouseStyleStats {
  artists_studied: number;
  elements_adopted: number;
  elements_by_category: Record<string, number>;
  style_version: number;
  has_manifesto: boolean;
}

export interface HouseStyleCreatedPiece {
  image_path: string;
  filename: string;
  seed: number;
  title: string;
  artist_statement: string;
  elements_used: string[];
  style_aspects: string[];
  prompt_used: string;
  process_id: string;
  style_version: number;
}

// =============================================================================
// API
// =============================================================================

export const artStudyApi = {
  // Artists
  listArtists: (studiedOnly?: boolean) =>
    api.get<ArtistResponse[]>('/admin/art-study/artists', { params: { studied_only: studiedOnly } }),

  getArtist: (artistId: string) =>
    api.get<ArtistResponse>(`/admin/art-study/artists/${artistId}`),

  createArtist: (data: {
    name: string;
    period?: string;
    years_active?: string;
    movements?: string[];
    wikipedia_url?: string;
    public_domain?: boolean;
  }) => api.post<ArtistResponse>('/admin/art-study/artists', data),

  fetchBiography: (artistId: string) =>
    api.post<{ status: string; biography: string; entity_id: string | null }>(
      `/admin/art-study/artists/${artistId}/fetch-biography`
    ),

  getArtistObservations: (artistId: string) =>
    api.get<{ entity_id: string | null; observations: ArtistObservation[] }>(
      `/admin/art-study/artists/${artistId}/observations`
    ),

  // Artworks
  listArtworks: (artistId: string) =>
    api.get<ArtworkResponse[]>(`/admin/art-study/artists/${artistId}/artworks`),

  createArtwork: (data: {
    artist_id: string;
    title: string;
    year?: number;
    medium?: string;
    image_url?: string;
    dimensions?: string;
    location?: string;
    public_domain?: boolean;
  }) => api.post<ArtworkResponse>('/admin/art-study/artworks', data),

  uploadArtworkImage: (artworkId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<{ status: string; image_path: string }>(
      `/admin/art-study/artworks/${artworkId}/upload-image`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  // Studies
  studyArtwork: (artworkId: string) =>
    api.post<StudyResponse>(`/admin/art-study/artworks/${artworkId}/study`),

  getArtworkStudy: (artworkId: string) =>
    api.get<StudyResponse>(`/admin/art-study/artworks/${artworkId}/study`),

  listArtistStudies: (artistId: string) =>
    api.get<StudyResponse[]>(`/admin/art-study/artists/${artistId}/studies`),

  // Synthesis
  synthesizeArtist: (artistId: string, minStudies?: number) =>
    api.post<SynthesisResponse>(
      `/admin/art-study/artists/${artistId}/synthesize`,
      null,
      { params: { min_studies: minStudies } }
    ),

  getArtistSynthesis: (artistId: string) =>
    api.get<SynthesisResponse>(`/admin/art-study/artists/${artistId}/synthesis`),

  // Create from synthesis
  createFromSynthesis: (artistId: string, numPieces?: number, aspectRatio?: string) =>
    api.post<{
      image_path: string;
      filename: string;
      seed: number;
      title: string;
      artist_statement: string;
      borrowed_elements: string[];
      prompt_used: string;
      process_id: string;
    }[]>(
      `/admin/art-study/artists/${artistId}/create`,
      { num_pieces: numPieces || 5, aspect_ratio: aspectRatio || 'square' }
    ),

  // List created pieces for an artist
  listCreations: (artistId: string) =>
    api.get<{
      image_path: string;
      filename: string;
      seed: number;
      title: string;
      artist_statement: string;
      borrowed_elements: string[];
      prompt_used: string;
      process_id: string;
    }[]>(`/admin/art-study/artists/${artistId}/creations`),

  // External import
  getProviders: () =>
    api.get<{ id: string; name: string; is_default: boolean }[]>('/admin/art-study/providers'),

  importArtworks: (artistId: string, maxWorks?: number, provider?: string) =>
    api.post<{
      status: string;
      provider: string;
      provider_name: string;
      imported: number;
      skipped: number;
      failed: number;
      message: string;
    }>(
      `/admin/art-study/artists/${artistId}/import`,
      { max_works: maxWorks || 10, provider }
    ),

  getProviderUrl: (artistId: string, provider?: string) =>
    api.get<{ url: string; provider: string }>(
      `/admin/art-study/artists/${artistId}/provider-url`,
      { params: { provider } }
    ),

  // Legacy aliases
  importFromWikiArt: (artistId: string, maxWorks?: number) =>
    api.post<{ status: string; imported: number; skipped: number; failed: number; message: string }>(
      `/admin/art-study/artists/${artistId}/import-wikiart`,
      { max_works: maxWorks || 10 }
    ),

  // House Style
  getHouseStyleStats: () =>
    api.get<HouseStyleStats>('/admin/art-study/house-style/stats'),

  getHouseStyle: () =>
    api.get<PersonalStyleResponse | null>('/admin/art-study/house-style'),

  getAdoptedElements: (params?: { artist_id?: string; category?: string; active_only?: boolean }) =>
    api.get<AdoptedElementResponse[]>('/admin/art-study/house-style/elements', { params }),

  extractAdoptedElements: (artistId: string) =>
    api.post<AdoptedElementResponse[]>(`/admin/art-study/house-style/extract/${artistId}`),

  synthesizeHouseStyle: (minArtists?: number) =>
    api.post<PersonalStyleResponse>(
      '/admin/art-study/house-style/synthesize',
      null,
      { params: { min_artists: minArtists } }
    ),

  createFromHouseStyle: (numPieces?: number, aspectRatio?: string) =>
    api.post<HouseStyleCreatedPiece[]>(
      '/admin/art-study/house-style/create',
      { num_pieces: numPieces || 5, aspect_ratio: aspectRatio || 'square' }
    ),

  listHouseStyleCreations: () =>
    api.get<HouseStyleCreatedPiece[]>('/admin/art-study/house-style/creations'),

  updateElementStrength: (elementId: string, strength: number) =>
    api.put<{ status: string; new_strength: number }>(
      `/admin/art-study/house-style/elements/${elementId}/strength`,
      null,
      { params: { strength } }
    ),

  deactivateElement: (elementId: string) =>
    api.delete<{ status: string; element_id: string }>(
      `/admin/art-study/house-style/elements/${elementId}`
    ),
};
