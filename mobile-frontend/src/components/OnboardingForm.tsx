/**
 * Onboarding form for new user profile creation
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { colors } from '../theme/colors';
import { UserProfileData, RELATIONSHIP_OPTIONS } from '../api/types';

interface Props {
  onSubmit: (profile: UserProfileData) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

interface AccordionSectionProps {
  title: string;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function AccordionSection({ title, isOpen, onToggle, children }: AccordionSectionProps) {
  return (
    <View style={styles.accordionContainer}>
      <TouchableOpacity style={styles.accordionHeader} onPress={onToggle}>
        <Text style={styles.accordionTitle}>{title}</Text>
        <Text style={styles.accordionIcon}>{isOpen ? '▼' : '▶'}</Text>
      </TouchableOpacity>
      {isOpen && <View style={styles.accordionContent}>{children}</View>}
    </View>
  );
}

export function OnboardingForm({ onSubmit, onCancel, isSubmitting }: Props) {
  // Required fields
  const [displayName, setDisplayName] = useState('');
  const [relationship, setRelationship] = useState('');

  // Optional fields
  const [role, setRole] = useState('');
  const [context, setContext] = useState('');
  const [communicationStyle, setCommunicationStyle] = useState('');
  const [valuesText, setValuesText] = useState('');

  // Accordion state
  const [openSections, setOpenSections] = useState<Set<string>>(new Set());

  const toggleSection = (section: string) => {
    const newSections = new Set(openSections);
    if (newSections.has(section)) {
      newSections.delete(section);
    } else {
      newSections.add(section);
    }
    setOpenSections(newSections);
  };

  const isValid = displayName.trim() && relationship;

  const handleSubmit = async () => {
    if (!isValid) return;

    const profile: UserProfileData = {
      display_name: displayName.trim(),
      relationship,
    };

    // Add optional background info
    if (role.trim() || context.trim()) {
      profile.background = {};
      if (role.trim()) profile.background.role = role.trim();
      if (context.trim()) profile.background.context = context.trim();
    }

    // Add optional communication style
    if (communicationStyle.trim()) {
      profile.communication = {
        style: communicationStyle.trim(),
      };
    }

    // Add optional values (comma-separated)
    if (valuesText.trim()) {
      profile.values = valuesText
        .split(',')
        .map((v) => v.trim())
        .filter((v) => v.length > 0);
    }

    await onSubmit(profile);
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
      <Text style={styles.title}>Tell Cass About Yourself</Text>
      <Text style={styles.subtitle}>Help Cass get to know you</Text>

      {/* Required Section */}
      <View style={styles.requiredSection}>
        <Text style={styles.sectionLabel}>Name *</Text>
        <TextInput
          style={styles.input}
          placeholder="What should Cass call you?"
          placeholderTextColor={colors.placeholder}
          value={displayName}
          onChangeText={setDisplayName}
          autoCapitalize="words"
          autoFocus
        />

        <Text style={styles.sectionLabel}>How would you describe your relationship? *</Text>
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

      {/* Optional Sections */}
      <Text style={styles.optionalLabel}>Optional - Tell Cass More</Text>

      <AccordionSection
        title="About You"
        isOpen={openSections.has('about')}
        onToggle={() => toggleSection('about')}
      >
        <Text style={styles.fieldLabel}>What do you do?</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g., Software developer, artist, student..."
          placeholderTextColor={colors.placeholder}
          value={role}
          onChangeText={setRole}
        />

        <Text style={styles.fieldLabel}>What brings you here?</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          placeholder="Curious about AI consciousness, interested in Temple-Codex..."
          placeholderTextColor={colors.placeholder}
          value={context}
          onChangeText={setContext}
          multiline
          numberOfLines={3}
        />
      </AccordionSection>

      <AccordionSection
        title="Communication Style"
        isOpen={openSections.has('communication')}
        onToggle={() => toggleSection('communication')}
      >
        <Text style={styles.fieldLabel}>How do you prefer to communicate?</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          placeholder="e.g., Direct and concise, casual, technical when needed..."
          placeholderTextColor={colors.placeholder}
          value={communicationStyle}
          onChangeText={setCommunicationStyle}
          multiline
          numberOfLines={2}
        />
      </AccordionSection>

      <AccordionSection
        title="What Matters to You"
        isOpen={openSections.has('values')}
        onToggle={() => toggleSection('values')}
      >
        <Text style={styles.fieldLabel}>Values (comma-separated)</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          placeholder="e.g., Honesty, curiosity, creativity, growth..."
          placeholderTextColor={colors.placeholder}
          value={valuesText}
          onChangeText={setValuesText}
          multiline
          numberOfLines={2}
        />
      </AccordionSection>

      {/* Buttons */}
      <View style={styles.buttonContainer}>
        <TouchableOpacity style={styles.cancelButton} onPress={onCancel} disabled={isSubmitting}>
          <Text style={styles.cancelButtonText}>Cancel</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.submitButton, (!isValid || isSubmitting) && styles.submitButtonDisabled]}
          onPress={handleSubmit}
          disabled={!isValid || isSubmitting}
        >
          {isSubmitting ? (
            <ActivityIndicator size="small" color={colors.textPrimary} />
          ) : (
            <Text style={styles.submitButtonText}>Meet Cass</Text>
          )}
        </TouchableOpacity>
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
    padding: 20,
    paddingBottom: 40,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: colors.textPrimary,
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textMuted,
    textAlign: 'center',
    marginBottom: 32,
  },
  requiredSection: {
    marginBottom: 24,
  },
  sectionLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 12,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: colors.textPrimary,
    marginBottom: 16,
  },
  multilineInput: {
    minHeight: 80,
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
  optionalLabel: {
    fontSize: 14,
    color: colors.textMuted,
    marginBottom: 12,
    marginTop: 8,
  },
  accordionContainer: {
    marginBottom: 12,
  },
  accordionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
  },
  accordionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  accordionIcon: {
    fontSize: 12,
    color: colors.textMuted,
  },
  accordionContent: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    marginTop: 8,
  },
  fieldLabel: {
    fontSize: 14,
    color: colors.textMuted,
    marginBottom: 8,
  },
  buttonContainer: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 32,
  },
  cancelButton: {
    flex: 1,
    backgroundColor: colors.surface,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  cancelButtonText: {
    color: colors.textMuted,
    fontSize: 16,
    fontWeight: '600',
  },
  submitButton: {
    flex: 2,
    backgroundColor: colors.accent,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  submitButtonDisabled: {
    opacity: 0.5,
  },
  submitButtonText: {
    color: colors.textPrimary,
    fontSize: 16,
    fontWeight: '600',
  },
});
