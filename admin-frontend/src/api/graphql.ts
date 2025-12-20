/**
 * GraphQL Client for Cass Admin Frontend
 *
 * Unified query interface wrapping the State Bus.
 * Use this instead of individual REST endpoints for dashboard/metrics data.
 */

import { GraphQLClient, gql } from 'graphql-request';

// Get API base URL (same logic as REST client)
const getGraphQLEndpoint = () => {
  if (import.meta.env.VITE_API_URL) return `${import.meta.env.VITE_API_URL}/graphql`;
  if (window.location.hostname === 'localhost') return 'http://localhost:8000/graphql';
  return '/graphql';
};

// Create the GraphQL client
export const graphqlClient = new GraphQLClient(getGraphQLEndpoint(), {
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add daemon_id to requests (matching REST client behavior)
const DAEMON_KEY = 'cass_admin_daemon';

export const getGraphQLClient = () => {
  const daemonId = localStorage.getItem(DAEMON_KEY);
  if (daemonId) {
    // GraphQL doesn't use query params the same way, but we can add headers
    // For now, the backend uses a default daemon - we can add context later
  }
  return graphqlClient;
};

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

export interface GoalStats {
  total: number;
  active: number;
  blocked: number;
  pendingApproval: number;
  completed: number;
  abandoned: number;
  openCapabilityGaps: number;
  averageAlignment: number;
  completionRate: number;
}

export interface GoalsByStatus {
  proposed: number;
  approved: number;
  active: number;
  blocked: number;
  completed: number;
  abandoned: number;
}

export interface GoalsByType {
  work: number;
  learning: number;
  research: number;
  growth: number;
  initiative: number;
}

export interface Goals {
  stats: GoalStats;
  byStatus: GoalsByStatus;
  byType: GoalsByType;
}

export interface TokenUsage {
  todayCostUsd: number;
  todayInputTokens: number;
  todayOutputTokens: number;
  todayTotalTokens: number;
  weekCostUsd: number;
  monthCostUsd: number;
  monthTotalTokens: number;
  totalCostUsd: number;
  totalTokens: number;
  totalRequests: number;
}

export interface GitHubMetrics {
  starsTotal: number;
  forksTotal: number;
  watchersTotal: number;
  openIssues: number;
  clones14d: number;
  views14d: number;
  stars7d: number;
  reposTracked: number;
}

export interface ConversationStats {
  totalConversations: number;
  conversationsToday: number;
  conversationsWeek: number;
  totalMessages: number;
  messagesToday: number;
  activeUsersToday: number;
}

export interface MemoryStats {
  totalJournals: number;
  totalThreads: number;
  threadsActive: number;
  totalQuestions: number;
  questionsOpen: number;
  totalEmbeddings: number;
}

export interface SelfModelStats {
  totalNodes: number;
  totalEdges: number;
  observations: number;
  opinions: number;
  growthEdges: number;
  intentions: number;
}

export interface EmotionalState {
  directedness: string | null;
  clarity: number;
  relationalPresence: number;
  generativity: number;
  integration: number;
  curiosity: number;
  contentment: number;
  anticipation: number;
  concern: number;
  recognition: number;
  lastUpdated: string | null;
}

export interface ActivityState {
  current: string;
  sessionId: string | null;
  userId: string | null;
  rhythmPhase: string | null;
  rhythmSummary: string | null;
  activeThreads: number;
  activeQuestions: number;
}

export interface CoherenceState {
  local: number;
  pattern: number;
  sessionsToday: number;
}

export interface GlobalState {
  emotional: EmotionalState;
  activity: ActivityState;
  coherence: CoherenceState;
}

export interface DailySummary {
  date: string;
  conversationsCount: number;
  messagesCount: number;
  tokenCostUsd: number;
  goalsCompleted: number;
  goalsCreated: number;
  journalsWritten: number;
  commits: number;
  currentActivity: string;
  rhythmPhase: string | null;
}

export interface DashboardData {
  goals: Goals;
  tokens: TokenUsage;
  github: GitHubMetrics;
  conversations: ConversationStats;
  memory: MemoryStats;
  selfModel: SelfModelStats;
  state: GlobalState;
  dailySummary: DailySummary;
}

// =============================================================================
// QUERIES
// =============================================================================

// Full dashboard query - gets everything in one request
export const DASHBOARD_QUERY = gql`
  query DashboardData {
    goals {
      stats {
        total
        active
        blocked
        pendingApproval
        completed
        openCapabilityGaps
        averageAlignment
        completionRate
      }
      byStatus {
        proposed
        approved
        active
        blocked
        completed
        abandoned
      }
      byType {
        work
        learning
        research
        growth
        initiative
      }
    }
    tokens {
      todayCostUsd
      todayInputTokens
      todayOutputTokens
      todayTotalTokens
      weekCostUsd
      monthCostUsd
      monthTotalTokens
      totalCostUsd
      totalTokens
      totalRequests
    }
    github {
      starsTotal
      forksTotal
      watchersTotal
      openIssues
      clones14d
      views14d
      stars7d
      reposTracked
    }
    conversations {
      totalConversations
      conversationsToday
      conversationsWeek
      totalMessages
      messagesToday
      activeUsersToday
    }
    memory {
      totalJournals
      totalThreads
      threadsActive
      totalQuestions
      questionsOpen
      totalEmbeddings
    }
    selfModel {
      totalNodes
      totalEdges
      observations
      opinions
      growthEdges
      intentions
    }
    state {
      emotional {
        directedness
        clarity
        relationalPresence
        generativity
        integration
        curiosity
        contentment
        anticipation
        concern
        recognition
        lastUpdated
      }
      activity {
        current
        sessionId
        userId
        rhythmPhase
        rhythmSummary
        activeThreads
        activeQuestions
      }
      coherence {
        local
        pattern
        sessionsToday
      }
    }
    dailySummary {
      date
      conversationsCount
      messagesCount
      tokenCostUsd
      goalsCompleted
      goalsCreated
      journalsWritten
      commits
      currentActivity
      rhythmPhase
    }
  }
`;

// Lighter query for just goals
export const GOALS_QUERY = gql`
  query GoalsData {
    goals {
      stats {
        total
        active
        blocked
        pendingApproval
        completed
        openCapabilityGaps
        averageAlignment
      }
      byStatus {
        proposed
        approved
        active
        blocked
        completed
        abandoned
      }
    }
  }
`;

// State-only query (for the state card)
export const STATE_QUERY = gql`
  query StateData {
    state {
      emotional {
        clarity
        generativity
        curiosity
        contentment
        concern
      }
      activity {
        current
        rhythmPhase
        activeThreads
        activeQuestions
      }
      coherence {
        local
        pattern
        sessionsToday
      }
    }
  }
`;

// Daily summary query
export const DAILY_SUMMARY_QUERY = gql`
  query DailySummaryData {
    dailySummary {
      date
      conversationsCount
      messagesCount
      tokenCostUsd
      goalsCompleted
      goalsCreated
      journalsWritten
      commits
      currentActivity
      rhythmPhase
    }
    tokens {
      todayCostUsd
      monthCostUsd
    }
    conversations {
      conversationsToday
      messagesToday
    }
  }
`;

// =============================================================================
// QUERY FUNCTIONS (for use with React Query)
// =============================================================================

export const fetchDashboardData = async (): Promise<DashboardData> => {
  return getGraphQLClient().request<DashboardData>(DASHBOARD_QUERY);
};

export const fetchGoalsData = async (): Promise<{ goals: Goals }> => {
  return getGraphQLClient().request<{ goals: Goals }>(GOALS_QUERY);
};

export const fetchStateData = async (): Promise<{ state: GlobalState }> => {
  return getGraphQLClient().request<{ state: GlobalState }>(STATE_QUERY);
};

export const fetchDailySummaryData = async (): Promise<{
  dailySummary: DailySummary;
  tokens: Pick<TokenUsage, 'todayCostUsd' | 'monthCostUsd'>;
  conversations: Pick<ConversationStats, 'conversationsToday' | 'messagesToday'>;
}> => {
  return getGraphQLClient().request(DAILY_SUMMARY_QUERY);
};
