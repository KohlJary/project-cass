/**
 * Profile screen - user profile and Cass's observations
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { apiClient } from '../api/client';
import { FullUserProfile, Observation, ObservationCategory, UserWithObservations } from '../api/types';

// Category icons and colors
const CATEGORY_CONFIG: Record<ObservationCategory, { icon: string; color: string; label: string }> = {
  interest: { icon: '✨', color: '#FFD700', label: 'Interest' },
  preference: { icon: '💜', color: '#9B59B6', label: 'Preference' },
  communication_style: { icon: '💬', color: '#3498DB', label: 'Communication' },
  background: { icon: '📚', color: '#E67E22', label: 'Background' },
  value: { icon: '🌟', color: '#27AE60', label: 'Value' },
  relationship_dynamic: { icon: '🤝', color: '#E91E63', label: 'Relationship' },
};

interface Props {
  userId: string;
  displayName: string;
  onLogout: () => void;
}

export function ProfileScreen({ userId, displayName, onLogout }: Props) {
  const [profile, setProfile] = useState<FullUserProfile | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedCategories, setExpandedCategories] = useState<Set<ObservationCategory>>(new Set());

  const loadUserData = useCallback(async () => {
    try {
      setError(null);
      const data: UserWithObservations = await apiClient.getUserWithObservations(userId);
      setProfile(data.profile);
      setObservations(data.observations || []);
    } catch (err: any) {
      console.error('Failed to load user data:', err);
      setError('Failed to load profile data');
    } finally {
      setIsLoading(false);
      setRefreshing(false);
    }
  }, [userId]);

  useEffect(() => {
    loadUserData();
  }, [loadUserData]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadUserData();
  }, [loadUserData]);

  const toggleCategory = (category: ObservationCategory) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(category)) {
        newSet.delete(category);
      } else {
        newSet.add(category);
      }
      return newSet;
    });
  };

  // Group observations by category
  const groupedObservations = observations.reduce((acc, obs) => {
    if (!acc[obs.category]) {
      acc[obs.category] = [];
    }
    acc[obs.category].push(obs);
    return acc;
  }, {} as Record<ObservationCategory, Observation[]>);

  const formatConfidence = (confidence: number): string => {
    if (confidence >= 0.8) return 'High';
    if (confidence >= 0.5) return 'Medium';
    return 'Low';
  };

  const renderObservationGroup = (category: ObservationCategory, observations: Observation[]) => {
    const config = CATEGORY_CONFIG[category];
    const isExpanded = expandedCategories.has(category);

    return (
      <View key={category} style={styles.observationGroup}>
        <TouchableOpacity
          style={styles.observationGroupHeader}
          onPress={() => toggleCategory(category)}
        >
          <View style={styles.categoryBadge}>
            <Text style={styles.categoryIcon}>{config.icon}</Text>
            <Text style={[styles.categoryLabel, { color: config.color }]}>
              {config.label}
            </Text>
            <View style={[styles.countBadge, { backgroundColor: config.color + '30' }]}>
              <Text style={[styles.countText, { color: config.color }]}>
                {observations.length}
              </Text>
            </View>
          </View>
          <Text style={styles.expandIcon}>{isExpanded ? '▼' : '▶'}</Text>
        </TouchableOpacity>

        {isExpanded && (
          <View style={styles.observationList}>
            {observations.map((obs) => (
              <View key={obs.id} style={styles.observationItem}>
                <Text style={styles.observationText}>{obs.observation}</Text>
                <View style={styles.observationMeta}>
                  <Text style={styles.confidenceText}>
                    {formatConfidence(obs.confidence)} confidence
                  </Text>
                  <Text style={styles.timestampText}>
                    {new Date(obs.timestamp).toLocaleDateString()}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>
    );
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.accent} />
          <Text style={styles.loadingText}>Loading profile...</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <ScrollView
        style={styles.scrollView}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.title}>Profile</Text>
        </View>

        {error ? (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity onPress={onRefresh} style={styles.retryButton}>
              <Text style={styles.retryButtonText}>Retry</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {/* Profile Card */}
            <View style={styles.profileCard}>
              <View style={styles.avatarContainer}>
                <Text style={styles.avatarText}>
                  {displayName.charAt(0).toUpperCase()}
                </Text>
              </View>
              <Text style={styles.displayName}>{displayName}</Text>
              {profile?.relationship && (
                <View style={styles.relationshipBadge}>
                  <Text style={styles.relationshipText}>
                    {profile.relationship.replace('_', ' ')}
                  </Text>
                </View>
              )}
              {profile?.created_at && (
                <Text style={styles.memberSince}>
                  Member since {new Date(profile.created_at).toLocaleDateString()}
                </Text>
              )}
            </View>

            {/* Profile Details */}
            {profile && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>About You</Text>

                {profile.background && Object.keys(profile.background).length > 0 && (
                  <View style={styles.detailGroup}>
                    {profile.background.role && (
                      <View style={styles.detailItem}>
                        <Text style={styles.detailLabel}>Role</Text>
                        <Text style={styles.detailValue}>{profile.background.role}</Text>
                      </View>
                    )}
                    {profile.background.context && (
                      <View style={styles.detailItem}>
                        <Text style={styles.detailLabel}>Context</Text>
                        <Text style={styles.detailValue}>{profile.background.context}</Text>
                      </View>
                    )}
                  </View>
                )}

                {profile.communication?.style && (
                  <View style={styles.detailGroup}>
                    <View style={styles.detailItem}>
                      <Text style={styles.detailLabel}>Communication Style</Text>
                      <Text style={styles.detailValue}>{profile.communication.style}</Text>
                    </View>
                  </View>
                )}

                {profile.values && profile.values.length > 0 && (
                  <View style={styles.detailGroup}>
                    <Text style={styles.detailLabel}>Values</Text>
                    <View style={styles.tagsContainer}>
                      {profile.values.map((value, index) => (
                        <View key={index} style={styles.valueTag}>
                          <Text style={styles.valueTagText}>{value}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                {profile.notes && (
                  <View style={styles.detailGroup}>
                    <View style={styles.detailItem}>
                      <Text style={styles.detailLabel}>Notes</Text>
                      <Text style={styles.detailValue}>{profile.notes}</Text>
                    </View>
                  </View>
                )}
              </View>
            )}

            {/* Observations Section */}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>What Cass Knows About You</Text>
              <Text style={styles.sectionSubtitle}>
                These are observations Cass has made through your conversations
              </Text>

              {observations.length === 0 ? (
                <View style={styles.emptyObservations}>
                  <Text style={styles.emptyText}>No observations yet</Text>
                  <Text style={styles.emptySubtext}>
                    As you chat with Cass, she'll learn more about you
                  </Text>
                </View>
              ) : (
                <View style={styles.observationsContainer}>
                  {Object.entries(groupedObservations).map(([category, obs]) =>
                    renderObservationGroup(category as ObservationCategory, obs)
                  )}
                </View>
              )}
            </View>

            {/* Logout Button */}
            <TouchableOpacity style={styles.logoutButton} onPress={onLogout}>
              <Text style={styles.logoutButtonText}>Logout</Text>
            </TouchableOpacity>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: {
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    color: colors.textMuted,
    fontSize: 14,
  },
  header: {
    paddingHorizontal: 20,
    paddingVertical: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  errorContainer: {
    margin: 16,
    padding: 20,
    backgroundColor: colors.error + '20',
    borderRadius: 12,
    alignItems: 'center',
  },
  errorText: {
    color: colors.error,
    marginBottom: 12,
  },
  retryButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: colors.accent,
    borderRadius: 8,
  },
  retryButtonText: {
    color: colors.textPrimary,
    fontWeight: '600',
  },
  profileCard: {
    marginHorizontal: 16,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: colors.accent,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarText: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  displayName: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  relationshipBadge: {
    backgroundColor: colors.accent + '20',
    paddingHorizontal: 16,
    paddingVertical: 6,
    borderRadius: 20,
    marginBottom: 8,
  },
  relationshipText: {
    color: colors.accent,
    fontSize: 14,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  memberSince: {
    fontSize: 12,
    color: colors.textMuted,
  },
  section: {
    marginHorizontal: 16,
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  sectionSubtitle: {
    fontSize: 14,
    color: colors.textMuted,
    marginBottom: 16,
  },
  detailGroup: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
  },
  detailItem: {
    marginBottom: 8,
  },
  detailLabel: {
    fontSize: 12,
    color: colors.textMuted,
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  detailValue: {
    fontSize: 15,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  tagsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 8,
    gap: 8,
  },
  valueTag: {
    backgroundColor: colors.accent + '20',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  valueTagText: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: '500',
  },
  observationsContainer: {
    gap: 12,
  },
  observationGroup: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    overflow: 'hidden',
  },
  observationGroupHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
  },
  categoryBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  categoryIcon: {
    fontSize: 18,
  },
  categoryLabel: {
    fontSize: 15,
    fontWeight: '600',
  },
  countBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  countText: {
    fontSize: 12,
    fontWeight: '600',
  },
  expandIcon: {
    fontSize: 12,
    color: colors.textMuted,
  },
  observationList: {
    paddingHorizontal: 16,
    paddingBottom: 16,
    gap: 12,
  },
  observationItem: {
    backgroundColor: colors.background,
    borderRadius: 8,
    padding: 12,
  },
  observationText: {
    fontSize: 14,
    color: colors.textPrimary,
    lineHeight: 20,
    marginBottom: 8,
  },
  observationMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  confidenceText: {
    fontSize: 11,
    color: colors.textMuted,
  },
  timestampText: {
    fontSize: 11,
    color: colors.textMuted,
  },
  emptyObservations: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 16,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  emptySubtext: {
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
  },
  logoutButton: {
    marginHorizontal: 16,
    marginBottom: 40,
    backgroundColor: colors.error + '20',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  logoutButtonText: {
    color: colors.error,
    fontSize: 16,
    fontWeight: '600',
  },
});
