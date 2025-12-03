/**
 * Collapsible summary panel for conversation context
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

// Enable LayoutAnimation on Android
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Props {
  conversationId: string | null;
  conversationTitle?: string;
}

export function SummaryPanel({ conversationId, conversationTitle }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [workingSummary, setWorkingSummary] = useState<string | null>(null);
  const [summaryCount, setSummaryCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = async () => {
    if (!conversationId) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getConversationSummary(conversationId);
      setWorkingSummary(data.working_summary);
      setSummaryCount(data.count);
    } catch (err) {
      console.error('Failed to load summary:', err);
      setError('Failed to load');
    } finally {
      setIsLoading(false);
    }
  };

  // Load summary when expanded or conversation changes
  useEffect(() => {
    if (isExpanded && conversationId) {
      loadSummary();
    }
  }, [isExpanded, conversationId]);

  // Reset when conversation changes
  useEffect(() => {
    setWorkingSummary(null);
    setSummaryCount(0);
    setIsExpanded(false);
  }, [conversationId]);

  const toggleExpanded = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setIsExpanded(!isExpanded);
  };

  if (!conversationId) {
    return null;
  }

  return (
    <View style={styles.container}>
      <TouchableOpacity style={styles.header} onPress={toggleExpanded} activeOpacity={0.7}>
        <View style={styles.headerLeft}>
          <Text style={styles.icon}>&#128220;</Text>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {conversationTitle || 'Conversation'}
          </Text>
        </View>
        <View style={styles.headerRight}>
          {summaryCount > 0 && (
            <Text style={styles.chunkBadge}>{summaryCount} chunks</Text>
          )}
          <Text style={styles.expandIcon}>{isExpanded ? '▲' : '▼'}</Text>
        </View>
      </TouchableOpacity>

      {isExpanded && (
        <View style={styles.content}>
          {isLoading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="small" color={colors.accent} />
              <Text style={styles.loadingText}>Loading summary...</Text>
            </View>
          ) : error ? (
            <View style={styles.errorContainer}>
              <Text style={styles.errorText}>{error}</Text>
              <TouchableOpacity onPress={loadSummary}>
                <Text style={styles.retryText}>Tap to retry</Text>
              </TouchableOpacity>
            </View>
          ) : workingSummary ? (
            <ScrollView style={styles.summaryScroll} nestedScrollEnabled>
              <Text style={styles.summaryLabel}>Working Summary</Text>
              <Text style={styles.summaryText}>{workingSummary}</Text>
            </ScrollView>
          ) : (
            <View style={styles.emptyContainer}>
              <Text style={styles.emptyText}>No summary yet</Text>
              <Text style={styles.emptySubtext}>
                Summaries are generated as conversations grow
              </Text>
            </View>
          )}
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
  },
  chunkBadge: {
    fontSize: 11,
    color: colors.textMuted,
    backgroundColor: colors.background,
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
    marginRight: 8,
  },
  expandIcon: {
    fontSize: 10,
    color: colors.textMuted,
  },
  content: {
    maxHeight: 200,
    borderTopWidth: 1,
    borderTopColor: colors.background,
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
  summaryScroll: {
    padding: 12,
  },
  summaryLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  summaryText: {
    fontSize: 13,
    color: colors.textPrimary,
    lineHeight: 20,
    opacity: 0.9,
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
  },
});
