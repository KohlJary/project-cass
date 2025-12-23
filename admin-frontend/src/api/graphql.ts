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

export interface ContinuousConversation {
  conversationId: string;
  userId: string;
  messageCount: number;
  createdAt: string;
  updatedAt: string;
  hasWorkingSummary: boolean;
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
  userId: string | null;
  contactStarted: string | null;
  messagesThisContact: number;
  currentTopics: string[];
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

export interface ApprovalItem {
  approvalId: string;
  approvalType: string;
  title: string;
  description: string;
  sourceId: string;
  createdAt: string;
  createdBy: string;
  priority: string;
}

export interface ApprovalCounts {
  goal: number;
  research: number;
  action: number;
  user: number;
  total: number;
}

export interface Approvals {
  items: ApprovalItem[];
  count: number;
  counts: ApprovalCounts;
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
  approvals: Approvals;
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
        userId
        contactStarted
        messagesThisContact
        currentTopics
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
    approvals {
      count
      counts {
        goal
        research
        action
        user
        total
      }
      items {
        approvalId
        approvalType
        title
        description
        sourceId
        createdAt
        createdBy
        priority
      }
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

// =============================================================================
// PEOPLEDEX TYPES
// =============================================================================

export interface PeopleDexEntity {
  id: string;
  entityType: string;
  primaryName: string;
  realm: string;
  userId: string | null;
  npcId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PeopleDexAttribute {
  id: string;
  entityId: string;
  attributeType: string;
  attributeKey: string | null;
  value: string;
  isPrimary: boolean;
  sourceType: string | null;
  sourceId: string | null;
  confidence: number;
  createdAt: string;
  updatedAt: string;
}

export interface PeopleDexRelatedEntity {
  id: string;
  entityType: string;
  primaryName: string;
  realm: string;
}

export interface PeopleDexRelationship {
  relationshipId: string;
  relationshipType: string;
  relationshipLabel: string | null;
  direction: string;
  relatedEntity: PeopleDexRelatedEntity;
}

export interface PeopleDexProfile {
  entity: PeopleDexEntity;
  attributes: PeopleDexAttribute[];
  relationships: PeopleDexRelationship[];
}

export interface PeopleDexStats {
  totalEntities: number;
  byType: Record<string, number>;
  byRealm: Record<string, number>;
}

export interface MutationResult {
  success: boolean;
  message: string;
  id: string | null;
}

// =============================================================================
// PEOPLEDEX QUERIES
// =============================================================================

export const PEOPLEDEX_STATS_QUERY = gql`
  query PeopleDexStats {
    peopledexStats {
      totalEntities
      byType
      byRealm
    }
  }
`;

export const PEOPLEDEX_ENTITIES_QUERY = gql`
  query PeopleDexEntities($entityType: String, $realm: String, $search: String, $limit: Int, $offset: Int) {
    peopledexEntities(entityType: $entityType, realm: $realm, search: $search, limit: $limit, offset: $offset) {
      id
      entityType
      primaryName
      realm
      userId
      npcId
      createdAt
      updatedAt
    }
  }
`;

export const PEOPLEDEX_ENTITY_QUERY = gql`
  query PeopleDexEntity($entityId: String!) {
    peopledexEntity(entityId: $entityId) {
      entity {
        id
        entityType
        primaryName
        realm
        userId
        npcId
        createdAt
        updatedAt
      }
      attributes {
        id
        entityId
        attributeType
        attributeKey
        value
        isPrimary
        sourceType
        sourceId
        confidence
        createdAt
        updatedAt
      }
      relationships {
        relationshipId
        relationshipType
        relationshipLabel
        direction
        relatedEntity {
          id
          entityType
          primaryName
          realm
        }
      }
    }
  }
`;

// =============================================================================
// PEOPLEDEX MUTATIONS
// =============================================================================

export const CREATE_PEOPLEDEX_ENTITY = gql`
  mutation CreatePeopleDexEntity($input: CreateEntityInput!) {
    createPeopledexEntity(input: $input) {
      success
      message
      id
    }
  }
`;

export const UPDATE_PEOPLEDEX_ENTITY = gql`
  mutation UpdatePeopleDexEntity($entityId: String!, $input: UpdateEntityInput!) {
    updatePeopledexEntity(entityId: $entityId, input: $input) {
      success
      message
      id
    }
  }
`;

export const DELETE_PEOPLEDEX_ENTITY = gql`
  mutation DeletePeopleDexEntity($entityId: String!) {
    deletePeopledexEntity(entityId: $entityId) {
      success
      message
    }
  }
`;

export const ADD_PEOPLEDEX_ATTRIBUTE = gql`
  mutation AddPeopleDexAttribute($entityId: String!, $input: AddAttributeInput!) {
    addPeopledexAttribute(entityId: $entityId, input: $input) {
      success
      message
      id
    }
  }
`;

export const DELETE_PEOPLEDEX_ATTRIBUTE = gql`
  mutation DeletePeopleDexAttribute($attrId: String!) {
    deletePeopledexAttribute(attrId: $attrId) {
      success
      message
    }
  }
`;

export const ADD_PEOPLEDEX_RELATIONSHIP = gql`
  mutation AddPeopleDexRelationship($input: AddRelationshipInput!) {
    addPeopledexRelationship(input: $input) {
      success
      message
      id
    }
  }
`;

export const DELETE_PEOPLEDEX_RELATIONSHIP = gql`
  mutation DeletePeopleDexRelationship($relId: String!) {
    deletePeopledexRelationship(relId: $relId) {
      success
      message
    }
  }
`;

export const MERGE_PEOPLEDEX_ENTITIES = gql`
  mutation MergePeopleDexEntities($input: MergeEntitiesInput!) {
    mergePeopledexEntities(input: $input) {
      success
      message
      id
    }
  }
`;

// =============================================================================
// PEOPLEDEX QUERY FUNCTIONS
// =============================================================================

export const fetchPeopleDexStats = async (): Promise<{ peopledexStats: PeopleDexStats }> => {
  return getGraphQLClient().request(PEOPLEDEX_STATS_QUERY);
};

export const fetchPeopleDexEntities = async (params: {
  entityType?: string;
  realm?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ peopledexEntities: PeopleDexEntity[] }> => {
  return getGraphQLClient().request(PEOPLEDEX_ENTITIES_QUERY, params);
};

export const fetchPeopleDexEntity = async (entityId: string): Promise<{ peopledexEntity: PeopleDexProfile | null }> => {
  return getGraphQLClient().request(PEOPLEDEX_ENTITY_QUERY, { entityId });
};

// Mutation functions
export const createPeopleDexEntity = async (input: {
  entityType: string;
  primaryName: string;
  realm?: string;
  userId?: string;
  npcId?: string;
}): Promise<{ createPeopledexEntity: MutationResult }> => {
  return getGraphQLClient().request(CREATE_PEOPLEDEX_ENTITY, { input });
};

export const deletePeopleDexEntity = async (entityId: string): Promise<{ deletePeopledexEntity: MutationResult }> => {
  return getGraphQLClient().request(DELETE_PEOPLEDEX_ENTITY, { entityId });
};

export const addPeopleDexAttribute = async (
  entityId: string,
  input: {
    attributeType: string;
    value: string;
    attributeKey?: string;
    isPrimary?: boolean;
    sourceType?: string;
  }
): Promise<{ addPeopledexAttribute: MutationResult }> => {
  return getGraphQLClient().request(ADD_PEOPLEDEX_ATTRIBUTE, { entityId, input });
};

export const deletePeopleDexAttribute = async (attrId: string): Promise<{ deletePeopledexAttribute: MutationResult }> => {
  return getGraphQLClient().request(DELETE_PEOPLEDEX_ATTRIBUTE, { attrId });
};

export const addPeopleDexRelationship = async (input: {
  fromEntityId: string;
  toEntityId: string;
  relationshipType: string;
  relationshipLabel?: string;
  sourceType?: string;
}): Promise<{ addPeopledexRelationship: MutationResult }> => {
  return getGraphQLClient().request(ADD_PEOPLEDEX_RELATIONSHIP, { input });
};

export const deletePeopleDexRelationship = async (relId: string): Promise<{ deletePeopledexRelationship: MutationResult }> => {
  return getGraphQLClient().request(DELETE_PEOPLEDEX_RELATIONSHIP, { relId });
};

// =============================================================================
// AUTONOMOUS SCHEDULE TYPES
// =============================================================================

export interface WorkUnit {
  id: string;
  name: string;
  templateId: string | null;
  category: string | null;
  focus: string | null;
  motivation: string | null;
  estimatedDurationMinutes: number;
  estimatedCostUsd: number;
  status: string;
}

export interface QueuedWorkUnit {
  workUnit: WorkUnit;
  targetPhase: string;
  queuedAt: string;
  priority: number;
}

export interface PhaseQueue {
  phase: string;
  isCurrent: boolean;
  queueCount: number;
  workUnits: QueuedWorkUnit[];
}

export interface TodaysPlanByPhase {
  phase: string;
  workUnits: WorkUnit[];
}

export interface TodaysPlan {
  dayIntention: string | null;
  plannedAt: string | null;
  phases: TodaysPlanByPhase[];
  totalWorkUnits: number;
}

export interface CurrentWork {
  workUnit: WorkUnit;
  startedAt: string;
  elapsedMinutes: number;
}

export interface DailySummary {
  date: string;
  total_work_units: number;
  by_category: Record<string, { count: number; total_minutes: number }>;
  current_work: object | null;
}

export interface AutonomousScheduleState {
  enabled: boolean;
  isWorking: boolean;
  currentWork: CurrentWork | null;
  todaysPlan: TodaysPlan;
  phaseQueues: PhaseQueue[];
  dailySummary: DailySummary;
}

// =============================================================================
// AUTONOMOUS SCHEDULE QUERY
// =============================================================================

export const AUTONOMOUS_SCHEDULE_QUERY = gql`
  query AutonomousSchedule {
    autonomousSchedule {
      enabled
      isWorking
      currentWork {
        workUnit {
          id
          name
          templateId
          category
          focus
          motivation
          estimatedDurationMinutes
          estimatedCostUsd
          status
        }
        startedAt
        elapsedMinutes
      }
      todaysPlan {
        dayIntention
        plannedAt
        totalWorkUnits
        phases {
          phase
          workUnits {
            id
            name
            templateId
            category
            focus
            motivation
            estimatedDurationMinutes
            estimatedCostUsd
            status
          }
        }
      }
      phaseQueues {
        phase
        isCurrent
        queueCount
        workUnits {
          workUnit {
            id
            name
            templateId
            category
            focus
            motivation
            estimatedDurationMinutes
            estimatedCostUsd
            status
          }
          targetPhase
          queuedAt
          priority
        }
      }
      dailySummary
    }
  }
`;

// =============================================================================
// AUTONOMOUS SCHEDULE QUERY FUNCTION
// =============================================================================

export const fetchAutonomousSchedule = async (): Promise<{ autonomousSchedule: AutonomousScheduleState }> => {
  return getGraphQLClient().request(AUTONOMOUS_SCHEDULE_QUERY);
};

// =============================================================================
// CONTINUOUS CONVERSATION QUERY
// =============================================================================

export const CONTINUOUS_CONVERSATION_QUERY = gql`
  query ContinuousConversation($userId: String!) {
    continuousConversation(userId: $userId) {
      conversationId
      userId
      messageCount
      createdAt
      updatedAt
      hasWorkingSummary
    }
  }
`;

export const fetchContinuousConversation = async (
  userId: string
): Promise<{ continuousConversation: ContinuousConversation }> => {
  return getGraphQLClient().request(CONTINUOUS_CONVERSATION_QUERY, { userId });
};

// =============================================================================
// UNIFIED GOALS (for Agency Tab)
// =============================================================================

export interface UnifiedGoal {
  id: string;
  title: string;
  description: string | null;
  goalType: string;
  status: string;
  priority: number;
  emergenceType: string | null;
  createdAt: string;
  createdBy: string;
  alignmentScore: number;
}

export interface UnifiedGoalsResult {
  goals: UnifiedGoal[];
  total: number;
  emergenceCounts: string; // JSON string of Record<string, number>
}

export const UNIFIED_GOALS_QUERY = gql`
  query UnifiedGoals($includeCompleted: Boolean, $emergenceType: String) {
    unifiedGoals(includeCompleted: $includeCompleted, emergenceType: $emergenceType) {
      goals {
        id
        title
        description
        goalType
        status
        priority
        emergenceType
        createdAt
        createdBy
        alignmentScore
      }
      total
      emergenceCounts
    }
  }
`;

export const fetchUnifiedGoals = async (params?: {
  includeCompleted?: boolean;
  emergenceType?: string;
}): Promise<{ unifiedGoals: UnifiedGoalsResult }> => {
  return getGraphQLClient().request(UNIFIED_GOALS_QUERY, params || {});
};

// Root goals (top-level, no parent)
export const ROOT_GOALS_QUERY = gql`
  query RootGoals {
    rootGoals {
      id
      title
      description
      goalType
      status
      priority
      emergenceType
      createdAt
      createdBy
      alignmentScore
    }
  }
`;

export const fetchRootGoals = async (): Promise<{ rootGoals: UnifiedGoal[] }> => {
  return getGraphQLClient().request(ROOT_GOALS_QUERY);
};

// Goal children (direct children of a goal)
export const GOAL_CHILDREN_QUERY = gql`
  query GoalChildren($goalId: String!) {
    goalChildren(goalId: $goalId) {
      id
      title
      description
      goalType
      status
      priority
      emergenceType
      createdAt
      createdBy
      alignmentScore
    }
  }
`;

export const fetchGoalChildren = async (goalId: string): Promise<{ goalChildren: UnifiedGoal[] }> => {
  return getGraphQLClient().request(GOAL_CHILDREN_QUERY, { goalId });
};

// Work items for a goal (atomic actions to achieve the goal)
export interface WorkItemSummary {
  id: string;
  title: string;
  description: string | null;
  category: string;
  priority: number;
  status: string;
  estimatedDurationMinutes: number;
  estimatedCostUsd: number;
  requiresApproval: boolean;
  approvalStatus: string;
  goalId: string | null;
  createdAt: string;
  actionSequence: string[];
}

export const WORK_ITEMS_FOR_GOAL_QUERY = gql`
  query WorkItemsForGoal($goalId: String!) {
    workItemsForGoal(goalId: $goalId) {
      id
      title
      description
      category
      priority
      status
      estimatedDurationMinutes
      estimatedCostUsd
      requiresApproval
      approvalStatus
      goalId
      createdAt
      actionSequence
    }
  }
`;

export const fetchWorkItemsForGoal = async (goalId: string): Promise<{ workItemsForGoal: WorkItemSummary[] }> => {
  return getGraphQLClient().request(WORK_ITEMS_FOR_GOAL_QUERY, { goalId });
};

// =============================================================================
// WORK HISTORY / SUMMARIES (Completed scheduled work)
// =============================================================================

export interface ActionSummary {
  actionId: string;
  actionType: string;
  slug: string;
  summary: string;
  startedAt: string | null;
  completedAt: string | null;
  artifacts: string[];
}

export interface WorkSummary {
  workUnitId: string;
  slug: string;
  name: string;
  templateId: string | null;
  phase: string;
  category: string;
  focus: string | null;
  motivation: string | null;
  date: string;
  startedAt: string | null;
  completedAt: string | null;
  durationMinutes: number;
  summary: string;
  keyInsights: string[];
  questionsAddressed: string[];
  questionsRaised: string[];
  actionSummaries: ActionSummary[];
  artifacts: Array<{ type: string; id: string; title?: string }>;
  success: boolean;
  error: string | null;
  costUsd: number;
  brief: string;
}

export const WORK_HISTORY_QUERY = gql`
  query WorkHistory($date: String, $phase: String, $limit: Int) {
    workHistory(date: $date, phase: $phase, limit: $limit) {
      workUnitId
      slug
      name
      templateId
      phase
      category
      focus
      motivation
      date
      startedAt
      completedAt
      durationMinutes
      summary
      keyInsights
      questionsAddressed
      questionsRaised
      actionSummaries {
        actionId
        actionType
        slug
        summary
        startedAt
        completedAt
        artifacts
      }
      artifacts
      success
      error
      costUsd
      brief
    }
  }
`;

export const WORK_SUMMARY_QUERY = gql`
  query WorkSummary($slug: String!) {
    workSummary(slug: $slug) {
      workUnitId
      slug
      name
      templateId
      phase
      category
      focus
      motivation
      date
      startedAt
      completedAt
      durationMinutes
      summary
      keyInsights
      questionsAddressed
      questionsRaised
      actionSummaries {
        actionId
        actionType
        slug
        summary
        startedAt
        completedAt
        artifacts
      }
      artifacts
      success
      error
      costUsd
      brief
    }
  }
`;

export const fetchWorkHistory = async (params?: {
  date?: string;
  phase?: string;
  limit?: number;
}): Promise<{ workHistory: WorkSummary[] }> => {
  return getGraphQLClient().request(WORK_HISTORY_QUERY, params || {});
};

export const fetchWorkSummary = async (slug: string): Promise<{ workSummary: WorkSummary | null }> => {
  return getGraphQLClient().request(WORK_SUMMARY_QUERY, { slug });
};
