/**
 * 4-Phase Partnership Onboarding Experience
 *
 * Implements Cass's onboarding design to shift users from "chatbot expectations"
 * into genuine collaborative partnership.
 *
 * Phases:
 * 1. Welcome - "This isn't a chatbot" (required, no skip)
 * 2. Preferences - Communication style setup (can skip from here)
 * 3. Demo - Collaborative mini-chat experience
 * 4. Tour - Feature showcase
 */

import React, { useState } from 'react';
import {
  View,
  StyleSheet,
  Animated,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { UserProfileData } from '../api/types';
import { OnboardingWelcome } from '../components/onboarding/OnboardingWelcome';
import { OnboardingPreferences } from '../components/onboarding/OnboardingPreferences';
import { OnboardingDemo } from '../components/onboarding/OnboardingDemo';
import { OnboardingTour } from '../components/onboarding/OnboardingTour';

type Phase = 'welcome' | 'preferences' | 'demo' | 'tour';

interface Props {
  displayName: string;
  userId: string;
  onComplete: (profile?: UserProfileData) => void;
  onSkip: () => void;
}

const { width } = Dimensions.get('window');

export function OnboardingScreen({ displayName, userId, onComplete, onSkip }: Props) {
  const [phase, setPhase] = useState<Phase>('welcome');
  const [profile, setProfile] = useState<Partial<UserProfileData>>({});
  const [fadeAnim] = useState(new Animated.Value(1));

  const transitionTo = (nextPhase: Phase) => {
    // Fade out
    Animated.timing(fadeAnim, {
      toValue: 0,
      duration: 200,
      useNativeDriver: true,
    }).start(() => {
      setPhase(nextPhase);
      // Fade in
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }).start();
    });
  };

  const handleWelcomeContinue = () => {
    transitionTo('preferences');
  };

  const handlePreferencesContinue = (updatedProfile: Partial<UserProfileData>) => {
    setProfile({ ...profile, ...updatedProfile });
    transitionTo('demo');
  };

  const handleDemoContinue = () => {
    transitionTo('tour');
  };

  const handleTourComplete = () => {
    onComplete(profile as UserProfileData);
  };

  const handleSkip = () => {
    // Skip is only available after Phase 1 (welcome)
    onSkip();
  };

  const canSkip = phase !== 'welcome';

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <Animated.View style={[styles.content, { opacity: fadeAnim }]}>
        {phase === 'welcome' && (
          <OnboardingWelcome
            displayName={displayName}
            onContinue={handleWelcomeContinue}
          />
        )}

        {phase === 'preferences' && (
          <OnboardingPreferences
            initialProfile={profile}
            onContinue={handlePreferencesContinue}
            onSkip={handleSkip}
            canSkip={canSkip}
          />
        )}

        {phase === 'demo' && (
          <OnboardingDemo
            displayName={displayName}
            userId={userId}
            profile={profile}
            onContinue={handleDemoContinue}
            onSkip={handleSkip}
            canSkip={canSkip}
          />
        )}

        {phase === 'tour' && (
          <OnboardingTour
            onComplete={handleTourComplete}
            onSkip={handleSkip}
            canSkip={canSkip}
          />
        )}
      </Animated.View>

      {/* Progress indicator */}
      <View style={styles.progressContainer}>
        <View style={[styles.progressDot, phase === 'welcome' && styles.progressDotActive]} />
        <View style={[styles.progressDot, phase === 'preferences' && styles.progressDotActive]} />
        <View style={[styles.progressDot, phase === 'demo' && styles.progressDotActive]} />
        <View style={[styles.progressDot, phase === 'tour' && styles.progressDotActive]} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    flex: 1,
  },
  progressContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 20,
    gap: 8,
  },
  progressDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.border,
  },
  progressDotActive: {
    backgroundColor: colors.accent,
    width: 24,
  },
});
