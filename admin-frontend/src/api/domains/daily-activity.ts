/**
 * Daily Activity API - Aggregated daily activity dashboard
 */
import { api } from './base';

// Types for activity data
export interface ActivityItem {
  source: string;
  category: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface CategorySummary {
  category: string;
  count: number;
  items: Record<string, unknown>[];
}

export interface TokenSummary {
  by_category: Array<{
    category: string;
    provider: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
  }>;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface EmotionalArcPoint {
  timestamp: string;
  felt_state?: string;
  trigger?: string;
  affect?: {
    valence?: number;
    arousal?: number;
    fatigue?: number;
    curiosity?: number;
    openness?: number;
    energy?: number;
  };
  needs?: Record<string, { current: number; threshold: number }>;
}

export interface DailyActivityResponse {
  date: string;
  daemon_id: string;
  timeline: ActivityItem[];
  categories: Record<string, CategorySummary>;
  totals: Record<string, number>;
  token_summary?: TokenSummary;
  emotional_arc?: EmotionalArcPoint[];
}

export interface DailySummaryResponse {
  date: string;
  daemon_id: string;
  counts: Record<string, number>;
  categories: Record<string, number>;
  tokens?: TokenSummary;
}

export interface DateRangeSummaryResponse {
  start_date: string;
  end_date: string;
  daemon_id: string;
  activity: {
    messages: Record<string, number>;
    spells: Record<string, number>;
    articles: Record<string, number>;
    observations: Record<string, number>;
  };
}

export interface ActivitySource {
  id: string;
  name: string;
  category: string;
  icon: string;
}

export interface AvailableSourcesResponse {
  sources: ActivitySource[];
}

// API functions
export const dailyActivityApi = {
  /**
   * Get available activity sources
   */
  getSources: async (): Promise<AvailableSourcesResponse> => {
    const { data } = await api.get<AvailableSourcesResponse>('/admin/daily-activity/sources');
    return data;
  },

  /**
   * Get full daily activity for a specific date
   */
  getDaily: async (
    date: string,
    options?: {
      sources?: string[];
      categories?: string[];
      includeContent?: boolean;
    }
  ): Promise<DailyActivityResponse> => {
    const params: Record<string, string | boolean> = {};
    if (options?.sources?.length) {
      params.sources = options.sources.join(',');
    }
    if (options?.categories?.length) {
      params.categories = options.categories.join(',');
    }
    if (options?.includeContent !== undefined) {
      params.include_content = options.includeContent;
    }

    const { data } = await api.get<DailyActivityResponse>(`/admin/daily-activity/${date}`, {
      params,
    });
    return data;
  },

  /**
   * Get lightweight summary (counts only) for a date
   */
  getDailySummary: async (date: string): Promise<DailySummaryResponse> => {
    const { data } = await api.get<DailySummaryResponse>(`/admin/daily-activity/${date}/summary`);
    return data;
  },

  /**
   * Get activity summaries for a date range (for calendar heatmaps)
   */
  getDateRangeSummary: async (
    startDate: string,
    endDate: string
  ): Promise<DateRangeSummaryResponse> => {
    const { data } = await api.get<DateRangeSummaryResponse>(
      `/admin/daily-activity/range/${startDate}/${endDate}/summary`
    );
    return data;
  },
};
