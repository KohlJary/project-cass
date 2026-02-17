// Shared types for Projects page components

export interface Project {
  id: string;
  name: string;
  description: string;
  working_directory: string;
  created_at: string;
  github_repo?: string;
  github_token?: string;
}

export interface Document {
  id: string;
  title: string;
  content: string;
  doc_type: string;
  created_at: string;
  updated_at: string;
}

export interface RoadmapItem {
  id: string;
  title: string;
  description: string;
  priority: string;
  item_type: string;
  status: string;
  milestone_id?: string;
  assigned_to?: string;
  created_at: string;
  updated_at: string;
}

export interface Milestone {
  id: string;
  title: string;
  description: string;
  status: string;
  target_date?: string;
  plan_path?: string;
}

export interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  modified: number;
}

export type TabId = 'overview' | 'documents' | 'roadmap' | 'files' | 'metrics';
