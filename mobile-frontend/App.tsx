/**
 * Cass Vessel Mobile - Main App
 */

// IMPORTANT: gesture-handler must be imported at the very top for Android
import 'react-native-gesture-handler';

import React, { useState, useCallback } from 'react';
import { StyleSheet, View, ActivityIndicator } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { AuthScreen } from './src/screens/AuthScreen';
import { OnboardingScreen } from './src/screens/OnboardingScreen';
import { TabNavigator } from './src/navigation/TabNavigator';
import { useAuth } from './src/hooks/useAuth';
import { useChatStore } from './src/store/chatStore';
import { apiClient } from './src/api/client';
import { colors } from './src/theme/colors';
import { UserProfileData } from './src/api/types';

export default function App() {
  const { user, isLoading, isAuthenticated, login, register, logout } = useAuth();
  const { setCurrentConversationId } = useChatStore();
  const [pendingOnboarding, setPendingOnboarding] = useState(false);
  const [onboardingProfile, setOnboardingProfile] = useState<Partial<UserProfileData>>({});
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);

  const handleLogin = async (email: string, password: string) => {
    setAuthError(null);
    setIsAuthLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      console.error('Login error:', err);
      setAuthError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleRegister = async (email: string, password: string, displayName: string, profile?: UserProfileData) => {
    setAuthError(null);
    setIsAuthLoading(true);
    try {
      // Create the full profile with display_name from the auth form
      const fullProfile: UserProfileData = {
        display_name: displayName,
        relationship: profile?.relationship || 'curious_visitor',
        ...profile,
      };
      await register({ email, password, display_name: displayName, profile: fullProfile });
      // Store initial profile for onboarding and show onboarding screen
      setOnboardingProfile({ display_name: displayName });
      setPendingOnboarding(true);
    } catch (err: any) {
      console.error('Register error:', err);
      setAuthError(err.message || 'Registration failed. Please try again.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleOnboardingComplete = async (profile?: UserProfileData) => {
    // Create first conversation for the new user
    try {
      const conversation = await apiClient.createConversation('First Conversation', user?.user_id);
      setCurrentConversationId(conversation.id);
    } catch (err) {
      console.error('Failed to create first conversation:', err);
    }
    setPendingOnboarding(false);
    setOnboardingProfile({});
  };

  const handleOnboardingSkip = async () => {
    // Create first conversation even if they skip
    try {
      const conversation = await apiClient.createConversation('First Conversation', user?.user_id);
      setCurrentConversationId(conversation.id);
    } catch (err) {
      console.error('Failed to create first conversation:', err);
    }
    setPendingOnboarding(false);
    setOnboardingProfile({});
  };

  const handleLogout = useCallback(async () => {
    await logout();
  }, [logout]);

  if (isLoading) {
    return (
      <SafeAreaProvider>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.accent} />
        </View>
      </SafeAreaProvider>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <SafeAreaProvider>
        <StatusBar style="light" />
        <AuthScreen
          onLogin={handleLogin}
          onRegister={handleRegister}
          isLoading={isAuthLoading}
          error={authError}
        />
      </SafeAreaProvider>
    );
  }

  // Show onboarding for new users
  if (pendingOnboarding) {
    return (
      <SafeAreaProvider>
        <StatusBar style="light" />
        <OnboardingScreen
          displayName={user.display_name}
          userId={user.user_id}
          onComplete={handleOnboardingComplete}
          onSkip={handleOnboardingSkip}
        />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <NavigationContainer>
        <TabNavigator
          userId={user.user_id}
          displayName={user.display_name}
          onLogout={handleLogout}
        />
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: colors.background,
  },
});
