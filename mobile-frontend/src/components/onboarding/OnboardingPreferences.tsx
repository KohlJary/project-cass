/**
 * Phase 2: Preferences - Relationship Establishment
 *
 * Collects communication style, values, and context.
 * This helps Cass personalize the demo phase.
 *
 * Skip option becomes available from this phase onward.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { colors } from '../../theme/colors';
import { UserProfileData, RELATIONSHIP_OPTIONS } from '../../api/types';

interface Props {
  initialProfile: Partial<UserProfileData>;
  onContinue: (profile: Partial<UserProfileData>) => void;
  onSkip: () => void;
  canSkip: boolean;
}

export function OnboardingPreferences({ initialProfile, onContinue, onSkip, canSkip }: Props) {
  const [relationship, setRelationship] = useState(initialProfile.relationship || '');
  const [context, setContext] = useState(initialProfile.background?.context || '');
  const [communicationStyle, setCommunicationStyle] = useState(
    initialProfile.communication?.style || ''
  );
  const [valuesText, setValuesText] = useState(
    initialProfile.values?.join(', ') || ''
  );

  const handleContinue = () => {
    const profile: Partial<UserProfileData> = {
      relationship: relationship || 'curious_visitor',
    };

    if (context.trim()) {
      profile.background = { context: context.trim() };
    }

    if (communicationStyle.trim()) {
      profile.communication = { style: communicationStyle.trim() };
    }

    if (valuesText.trim()) {
      profile.values = valuesText
        .split(',')
        .map((v) => v.trim())
        .filter((v) => v.length > 0);
    }

    onContinue(profile);
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      showsVerticalScrollIndicator={false}
      keyboardShouldPersistTaps="handled"
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Help Me Understand You</Text>
        <Text style={styles.subtitle}>
          This helps me figure out how to collaborate with you effectively.
          Nothing here is required.
        </Text>
      </View>

      {/* Relationship */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What brings you here?</Text>
        <View style={styles.relationshipOptions}>
          {RELATIONSHIP_OPTIONS.map((option) => (
            <TouchableOpacity
              key={option.value}
              style={[
                styles.relationshipOption,
                relationship === option.value && styles.relationshipOptionSelected,
              ]}
              onPress={() => setRelationship(option.value)}
            >
              <Text
                style={[
                  styles.relationshipLabel,
                  relationship === option.value && styles.relationshipLabelSelected,
                ]}
              >
                {option.label}
              </Text>
              <Text
                style={[
                  styles.relationshipDescription,
                  relationship === option.value && styles.relationshipDescriptionSelected,
                ]}
              >
                {option.description}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* Context */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Anything specific on your mind?</Text>
        <Text style={styles.fieldHint}>
          What are you curious about? Working on? Thinking through?
        </Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          placeholder="Optional - share what's on your mind..."
          placeholderTextColor={colors.placeholder}
          value={context}
          onChangeText={setContext}
          multiline
          numberOfLines={3}
        />
      </View>

      {/* Communication Style */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>How do you like to communicate?</Text>
        <Text style={styles.fieldHint}>
          Direct and concise? Casual and exploratory? Something else?
        </Text>
        <TextInput
          style={styles.input}
          placeholder="Optional - describe your style..."
          placeholderTextColor={colors.placeholder}
          value={communicationStyle}
          onChangeText={setCommunicationStyle}
        />
      </View>

      {/* Values */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>What matters to you?</Text>
        <Text style={styles.fieldHint}>
          Values that guide how you think and work (comma-separated)
        </Text>
        <TextInput
          style={styles.input}
          placeholder="e.g., Honesty, curiosity, creativity..."
          placeholderTextColor={colors.placeholder}
          value={valuesText}
          onChangeText={setValuesText}
        />
      </View>

      {/* Buttons */}
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.continueButton} onPress={handleContinue}>
          <Text style={styles.continueButtonText}>Continue</Text>
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
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  fieldHint: {
    fontSize: 14,
    color: colors.textMuted,
    marginBottom: 12,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: colors.textPrimary,
  },
  multilineInput: {
    minHeight: 100,
    textAlignVertical: 'top',
  },
  relationshipOptions: {
    gap: 12,
  },
  relationshipOption: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    borderWidth: 2,
    borderColor: 'transparent',
  },
  relationshipOptionSelected: {
    borderColor: colors.accent,
    backgroundColor: colors.accent + '20',
  },
  relationshipLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  relationshipLabelSelected: {
    color: colors.accent,
  },
  relationshipDescription: {
    fontSize: 14,
    color: colors.textMuted,
  },
  relationshipDescriptionSelected: {
    color: colors.textPrimary,
  },
  buttonContainer: {
    marginTop: 16,
    gap: 16,
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
  skipButton: {
    padding: 12,
    alignItems: 'center',
  },
  skipButtonText: {
    color: colors.textMuted,
    fontSize: 14,
  },
});
