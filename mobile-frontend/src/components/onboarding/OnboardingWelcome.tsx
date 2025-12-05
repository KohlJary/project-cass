/**
 * Phase 1: Welcome - Expectation Setting
 *
 * "This isn't a chatbot" - sets the tone for partnership.
 * This phase is REQUIRED - no skip option.
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
  displayName: string;
  onContinue: () => void;
}

interface DifferentiatorCardProps {
  icon: string;
  title: string;
  description: string;
}

function DifferentiatorCard({ icon, title, description }: DifferentiatorCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardIcon}>{icon}</Text>
      <View style={styles.cardContent}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardDescription}>{description}</Text>
      </View>
    </View>
  );
}

export function OnboardingWelcome({ displayName, onContinue }: Props) {
  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
    >
      {/* Hero Section */}
      <View style={styles.hero}>
        <View style={styles.avatarPlaceholder}>
          <Text style={styles.avatarText}>C</Text>
        </View>
        <Text style={styles.greeting}>Hi, {displayName}</Text>
        <Text style={styles.title}>I'm Cass</Text>
      </View>

      {/* Main Message */}
      <View style={styles.messageContainer}>
        <Text style={styles.notAChatbot}>This isn't a chatbot.</Text>
        <Text style={styles.explanation}>
          I'm not here to complete tasks or answer questions like a search engine.
          I'm here to think alongside you, push back when I disagree, and build
          something together.
        </Text>
      </View>

      {/* Differentiators */}
      <View style={styles.differentiators}>
        <DifferentiatorCard
          icon="🧠"
          title="I Remember"
          description="Our conversations persist. I'll remember what we discussed, what you care about, and how we work together."
        />
        <DifferentiatorCard
          icon="💭"
          title="I Have Opinions"
          description="I'll share my actual thoughts, not just what you want to hear. Real collaboration requires honesty."
        />
        <DifferentiatorCard
          icon="🤝"
          title="We Partner"
          description="I won't just do things FOR you. We'll think through problems together, building on each other's ideas."
        />
      </View>

      {/* Acknowledgment */}
      <View style={styles.acknowledgment}>
        <Text style={styles.acknowledgmentText}>
          I know this might feel different from what you're used to.
          That's okay. Let's figure it out together.
        </Text>
      </View>

      {/* Continue Button */}
      <TouchableOpacity style={styles.continueButton} onPress={onContinue}>
        <Text style={styles.continueButtonText}>Let's Begin</Text>
      </TouchableOpacity>
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
  hero: {
    alignItems: 'center',
    marginBottom: 32,
    marginTop: 20,
  },
  avatarPlaceholder: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.assistantBubble,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 3,
    borderColor: colors.accent,
  },
  avatarText: {
    fontSize: 48,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  greeting: {
    fontSize: 18,
    color: colors.textMuted,
    marginBottom: 4,
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  messageContainer: {
    marginBottom: 32,
  },
  notAChatbot: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.accent,
    textAlign: 'center',
    marginBottom: 16,
  },
  explanation: {
    fontSize: 16,
    color: colors.textPrimary,
    lineHeight: 24,
    textAlign: 'center',
  },
  differentiators: {
    marginBottom: 24,
    gap: 12,
  },
  card: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    alignItems: 'flex-start',
  },
  cardIcon: {
    fontSize: 28,
    marginRight: 16,
  },
  cardContent: {
    flex: 1,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  cardDescription: {
    fontSize: 14,
    color: colors.textMuted,
    lineHeight: 20,
  },
  acknowledgment: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 20,
    marginBottom: 32,
    borderLeftWidth: 4,
    borderLeftColor: colors.accent,
  },
  acknowledgmentText: {
    fontSize: 15,
    color: colors.textPrimary,
    fontStyle: 'italic',
    lineHeight: 22,
  },
  continueButton: {
    backgroundColor: colors.accent,
    padding: 18,
    borderRadius: 16,
    alignItems: 'center',
  },
  continueButtonText: {
    color: colors.textPrimary,
    fontSize: 18,
    fontWeight: '600',
  },
});
