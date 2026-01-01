/**
 * Collapsible summary panel for conversation context
 * Shows working summary and observations (user + self) made during the conversation
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  LayoutAnimation,
  Platform,
  UIManager,
} from 'react-native';
import { colors } from '../theme/colors';
import { apiClient } from '../api/client';
import { Observation, SelfObservation } from '../api/types';

// Enable LayoutAnimation on Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Props {
  conversationId: string | null;
  conversationTitle?: string;
}

// Category icons for observations
const USER_CATEGORY_ICONS: Record<string, string> = {
  interest: '⭐',
  preference: '💡',
  communication_style: '💬',
  background: '📋',
  value: '💎',
  relationship_dynamic: '🤝',
};

const SELF_CATEGORY_ICONS: Record<string, string> = {
  capability: '✨',
  limitation: '🔒',
  pattern: '🔄',
  preference: '💡',
  growth: '🌱',
  contradiction: '⚖️',
};

// Expandable observation component
interface ExpandableObservationProps {
  icon: string;
  category: string;
  text: string;
  confidence: number;
}

function ExpandableObservation({ icon, category, text, confidence }: ExpandableObservationProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Truncate text for collapsed view
  const truncatedText = text.length > 60 ? text.substring(0, 60) + '...' : text;
  const needsExpansion = text.length > 60;

  return (
    <TouchableOpacity
      style={styles.observationItem}
      onPress={() => needsExpansion && setIsExpanded(!isExpanded)}
      activeOpacity={needsExpansion ? 0.7 : 1}
    >
      <Text style={styles.observationIcon}>{icon}</Text>
      <View style={styles.observationContent}>
        <View style={styles.observationHeader}>
          <Text style={styles.observationMeta}>
            {category} • {Math.round(confidence * 100)}%
          </Text>
          {needsExpansion && (
            <Text style={styles.expandIndicator}>
              {isExpanded ? '▲' : '▼'}
            </Text>
          )}
        </View>
        <Text style={styles.observationText}>
          {isExpanded ? text : truncatedText}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

export function SummaryPanel({ conversationId, conversationTitle }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [workingSummary, setWorkingSummary] = useState<string | null>(null);
  const [summaryCount, setSummaryCount] = useState(0);
  const [userObservations, setUserObservations] = useState<Observation[]>([]);
  const [selfObservations, setSelfObservations] = useState<SelfObservation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [summarizeStatus, setSummarizeStatus] = useState<string | null>(null);

  const loadData = async () => {
    if (!conversationId) return;

    setIsLoading(true);
    setError(null);
    try {
      // Load summary and observations in parallel
      const [summaryData, obsData] = await Promise.all([
        apiClient.getConversationSummary(conversationId),
        apiClient.getConversationObservations(conversationId),
      ]);

      setWorkingSummary(summaryData.working_summary);
      setSummaryCount(summaryData.count);
      setUserObservations(obsData.user_observations);
      setSelfObservations(obsData.self_observations);
    } catch (err) {
      console.error('Failed to load summary/observations:', err);
      setError('Failed to load');
    } finally {
      setIsLoading(false);
    }
  };

  // Load data when expanded or conversation changes
  useEffect(() => {
    if (isExpanded && conversationId) {
      loadData();
    }
  }, [isExpanded, conversationId]);

  // Reset when conversation changes
  useEffect(() => {
    setWorkingSummary(null);
    setSummaryCount(0);
    setUserObservations([]);
    setSelfObservations([]);
    setIsExpanded(false);
    setSummarizeStatus(null);
  }, [conversationId]);

  const handleSummarize = async () => {
    if (!conversationId || isSummarizing) return;

    setIsSummarizing(true);
    setSummarizeStatus(null);
    try {
      const result = await apiClient.triggerSummarization(conversationId);
      setSummarizeStatus(result.message || 'Summarization complete');
      // Reload data to show new summary
      await loadData();
    } catch (err) {
      console.error('Failed to summarize:', err);
      setSummarizeStatus('Failed to summarize');
    } finally {
      setIsSummarizing(false);
    }
  };

  const toggleExpanded = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setIsExpanded(!isExpanded);
  };

  if (!conversationId) {
    return null;
  }

  const totalObservations = userObservations.length + selfObservations.length;
  const hasContent = workingSummary || totalObservations > 0;

  return (
    <View style={styles.container}>
      <TouchableOpacity style={styles.header} onPress={toggleExpanded} activeOpacity={0.7}>
        <View style={styles.headerLeft}>
          <Text style={styles.icon}>📝</Text>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {conversationTitle || 'Conversation'}
          </Text>
        </View>
        <View style={styles.headerRight}>
          {summaryCount > 0 && (
            <Text style={styles.badge}>{summaryCount} chunks</Text>
          )}
          {totalObservations > 0 && (
            <Text style={styles.badge}>{totalObservations} obs</Text>
          )}
          <Text style={styles.expandIcon}>{isExpanded ? '▲' : '▼'}</Text>
        </View>
      </TouchableOpacity>

      {isExpanded && (
        <View style={styles.content}>
          {isLoading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="small" color={colors.accent} />
              <Text style={styles.loadingText}>Loading...</Text>
            </View>
          ) : error ? (
            <View style={styles.errorContainer}>
              <Text style={styles.errorText}>{error}</Text>
              <TouchableOpacity onPress={loadData}>
                <Text style={styles.retryText}>Tap to retry</Text>
              </TouchableOpacity>
            </View>
          ) : hasContent ? (
            <ScrollView style={styles.scrollContent} nestedScrollEnabled>
              {/* Working Summary */}
              {workingSummary && (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>Working Summary</Text>
                  <Text style={styles.summaryText}>{workingSummary}</Text>
                </View>
              )}

              {/* User Observations - What Cass learned about the user */}
              {userObservations.length > 0 && (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>👤 About You</Text>
                  {userObservations.map((obs) => (
                    <ExpandableObservation
                      key={obs.id}
                      icon={USER_CATEGORY_ICONS[obs.category] || '•'}
                      category={obs.category.replace('_', ' ')}
                      text={obs.observation}
                      confidence={obs.confidence}
                    />
                  ))}
                </View>
              )}

              {/* Self Observations - What Cass noticed about herself */}
              {selfObservations.length > 0 && (
                <View style={styles.section}>
                  <Text style={styles.sectionLabel}>🪞 Cass's Self-Reflections</Text>
                  {selfObservations.map((obs) => (
                    <ExpandableObservation
                      key={obs.id}
                      icon={SELF_CATEGORY_ICONS[obs.category] || '•'}
                      category={obs.category}
                      text={obs.observation}
                      confidence={obs.confidence}
                    />
                  ))}
                </View>
              )}
            </ScrollView>
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>No insights yet</Text>
              <Text style={styles.emptySubtext}>
                Summaries and observations appear as conversations grow
              </Text>
            </View>
          )}

          {/* Summarize Button */}
          <View style={styles.actionBar}>
            {summarizeStatus && (
              <Text style={styles.statusText}>{summarizeStatus}</Text>
            )}
            <TouchableOpacity
              style={[styles.summarizeButton, isSummarizing && styles.summarizeButtonDisabled]}
              onPress={handleSummarize}
              disabled={isSummarizing}
            >
              {isSummarizing ? (
                <ActivityIndicator size="small" color={colors.textPrimary} />
              ) : (
                <Text style={styles.summarizeButtonText}>Summarize</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  icon: {
    fontSize: 16,
    marginRight: 8,
  },
  headerTitle: {
    fontSize: 14,
    fontWeight: '500',
    color: colors.textPrimary,
    flex: 1,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  badge: {
    fontSize: 11,
    color: colors.textMuted,
    backgroundColor: colors.background,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  expandIcon: {
    fontSize: 10,
    color: colors.textMuted,
    marginLeft: 4,
  },
  content: {
    maxHeight: 350,
    borderTopWidth: 1,
    borderTopColor: colors.background,
  },
  scrollContent: {
    padding: 12,
  },
  loadingContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 20,
  },
  loadingText: {
    marginLeft: 8,
    color: colors.textMuted,
    fontSize: 13,
  },
  errorContainer: {
    alignItems: 'center',
    padding: 20,
  },
  errorText: {
    color: colors.error,
    fontSize: 13,
  },
  retryText: {
    color: colors.accent,
    fontSize: 13,
    marginTop: 4,
  },
  section: {
    marginBottom: 16,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  summaryText: {
    fontSize: 13,
    color: colors.textPrimary,
    lineHeight: 20,
    opacity: 0.9,
  },
  observationItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 10,
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 10,
  },
  observationIcon: {
    fontSize: 14,
    marginRight: 10,
    marginTop: 2,
  },
  observationContent: {
    flex: 1,
  },
  observationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  observationText: {
    fontSize: 13,
    color: colors.textPrimary,
    lineHeight: 18,
  },
  observationMeta: {
    fontSize: 11,
    color: colors.textMuted,
    textTransform: 'capitalize',
  },
  expandIndicator: {
    fontSize: 10,
    color: colors.textMuted,
    marginLeft: 8,
  },
  emptyContainer: {
    alignItems: 'center',
    padding: 20,
  },
  emptyText: {
    color: colors.textMuted,
    fontSize: 14,
  },
  emptySubtext: {
    color: colors.textMuted,
    fontSize: 12,
    marginTop: 4,
    opacity: 0.7,
    textAlign: 'center',
  },
  actionBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: colors.background,
    gap: 12,
  },
  statusText: {
    fontSize: 12,
    color: colors.textMuted,
    flex: 1,
  },
  summarizeButton: {
    backgroundColor: colors.accent,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    minWidth: 90,
    alignItems: 'center',
  },
  summarizeButtonDisabled: {
    opacity: 0.6,
  },
  summarizeButtonText: {
    color: colors.textPrimary,
    fontSize: 13,
    fontWeight: '600',
  },
});
