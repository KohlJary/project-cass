// Types for ArtStudy page

export type ModalType = 'create-artist' | 'create-artwork' | 'view-study' | 'view-created' | 'view-house-style-created' | null;
export type TabType = 'overview' | 'artworks' | 'observations' | 'synthesis';
export type MainViewType = 'artists' | 'house-style' | 'gallery';

// Unified gallery item type
export interface GalleryItem {
  id: string;
  filename: string;
  title: string;
  artist_statement: string;
  prompt_used: string;
  source: 'artist' | 'house-style';
  source_name?: string;  // Artist name if source is 'artist'
  elements: string[];    // borrowed_elements or elements_used
  style_aspects?: string[];
  style_version?: number;
}
