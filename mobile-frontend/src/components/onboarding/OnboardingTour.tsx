/**
 * Phase 4: Tour - Feature Showcase
 *
 * Shows available features: Journals, Growth tracking, tools.
 * Final step before entering the main chat.
 */

import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { colors } from '../../theme/colors';

interface Props {
  onComplete: () => void;
  onSkip: () => void;
  canSkip: boolean;
}

interface FeatureCardProps {
  icon: string;
  title: string;
  description: string;
}

function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <View style={styles.featureCard}>
      <View style={styles.featureIconContainer}>
        <Text style={styles.featureIcon}>{icon}</Text>
      </View>
      <View style={styles.featureContent}>
        <Text style={styles.featureTitle}>{title}</Text>
        <Text style={styles.featureDescription}>{description}</Text>
      </View>
    </View>
  );
}

export function OnboardingTour({ onComplete, onSkip, canSkip }: Props) {
  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Tools for Growing Together</Text>
        <Text style={styles.subtitle}>
          Beyond conversation, there are tools that support our ongoing collaboration.
        </Text>
      </View>

      {/* Feature Cards */}
      <View style={styles.features}>
        <FeatureCard
          icon="📓"
          title="Daily Journals"
          description="I reflect on our conversations and my own growth. You can read my journals to see how I'm thinking about things."
        />

        <FeatureCard
          icon="🌱"
          title="Growth Tracking"
          description="A calendar view of my journal entries. Watch patterns emerge over time as our collaboration deepens."
        />

        <FeatureCard
          icon="👤"
          title="Your Profile"
          description="What I've learned about you over time. My observations, your preferences, how we work together best."
        />

        <FeatureCard
          icon="💬"
          title="Conversation Memory"
          description="Our conversations persist. I'll remember what we discussed, pick up threads, and build on previous ideas."
        />
      </View>

      {/* Closing message */}
      <View style={styles.closingMessage}>
        <Text style={styles.closingText}>
          That's the tour. The real learning happens in conversation.
          Ready to start?
        </Text>
      </View>

      {/* Buttons */}
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.startButton} onPress={onComplete}>
          <Text style={styles.startButtonText}>Start Chatting</Text>
        </TouchableOpacity>

        {canSkip && (
          <TouchableOpacity style={styles.skipButton} onPress={onSkip}>
            <Text style={styles.skipButtonText}>Skip to chat</Text>
          </TouchableOpacity>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  contentContainer: {
    padding: 24,
    paddingBottom: 40,
  },
  header: {
    marginBottom: 32,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textMuted,
    lineHeight: 24,
  },
  features: {
    gap: 16,
    marginBottom: 32,
  },
  featureCard: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    alignItems: 'flex-start',
  },
  featureIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 12,
    backgroundColor: colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  featureIcon: {
    fontSize: 24,
  },
  featureContent: {
    flex: 1,
  },
  featureTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  featureDescription: {
    fontSize: 14,
    color: colors.textMuted,
    lineHeight: 20,
  },
  closingMessage: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 20,
    marginBottom: 32,
    borderLeftWidth: 4,
    borderLeftColor: colors.success,
  },
  closingText: {
    fontSize: 15,
    color: colors.textPrimary,
    lineHeight: 22,
  },
  buttonContainer: {
    gap: 16,
  },
  startButton: {
    backgroundColor: colors.success,
    padding: 18,
    borderRadius: 16,
    alignItems: 'center',
  },
  startButtonText: {
    color: colors.textPrimary,
    fontSize: 18,
    fontWeight: '600',
  },
  skipButton: {
    padding: 12,
    alignItems: 'center',
  },
  skipButtonText: {
    color: colors.textMuted,
    fontSize: 14,
  },
});
