/**
 * Cass Vessel Mobile - Main App
 */

// IMPORTANT: gesture-handler must be imported at the very top for Android
import 'react-native-gesture-handler';

import React, { useState } from 'react';
import { StyleSheet, View, ActivityIndicator } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer } from '@react-navigation/native';
import { AuthScreen } from './src/screens/AuthScreen';
import { TabNavigator } from './src/navigation/TabNavigator';
import { useAuth } from './src/hooks/useAuth';
import { colors } from './src/theme/colors';
import { UserProfileData } from './src/api/types';

export default function App() {
  const { user, isLoading, isAuthenticated, login, register, logout } = useAuth();
  const [pendingOnboarding, setPendingOnboarding] = useState(false);
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
      setPendingOnboarding(true);
    } catch (err: any) {
      console.error('Register error:', err);
      setAuthError(err.message || 'Registration failed. Please try again.');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleOnboardingComplete = () => {
    setPendingOnboarding(false);
  };

  const handleLogout = async () => {
    await logout();
  };

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

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <NavigationContainer>
        <TabNavigator
          userId={user.user_id}
          displayName={user.display_name}
          onLogout={handleLogout}
          pendingOnboarding={pendingOnboarding}
          onOnboardingComplete={handleOnboardingComplete}
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
