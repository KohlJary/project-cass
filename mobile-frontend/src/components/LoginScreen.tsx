/**
 * Login/Onboarding screen for new users
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import { colors } from '../theme/colors';
import { apiClient } from '../api/client';
import { OnboardingForm } from './OnboardingForm';
import { UserProfileData } from '../api/types';

// Protected user IDs that can't be deleted
const PROTECTED_USER_NAMES = ['Kohl', 'kohl'];

interface User {
  user_id: string;
  display_name: string;
  relationship: string;
}

interface Props {
  onLogin: (userId: string, displayName: string, isNewUser?: boolean) => void;
}

export function LoginScreen({ onLogin }: Props) {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const userList = await apiClient.listUsers();
      setUsers(userList);
    } catch (err) {
      setError('Failed to connect to server');
      console.error('Failed to load users:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectUser = (user: User) => {
    onLogin(user.user_id, user.display_name);
  };

  const handleCreateUser = async (profile: UserProfileData) => {
    setIsCreating(true);
    setError(null);
    try {
      const newUser = await apiClient.createUser(profile);
      // Set as current user on backend
      await apiClient.setCurrentUser(newUser.user_id);
      // Pass isNewUser=true to trigger onboarding flow
      onLogin(newUser.user_id, newUser.display_name, true);
    } catch (err: any) {
      setError(err.message || 'Failed to create user');
      console.error('Failed to create user:', err);
    } finally {
      setIsCreating(false);
    }
  };

  const handleDeleteUser = (user: User) => {
    Alert.alert(
      'Delete User',
      `Are you sure you want to delete "${user.display_name}"? This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiClient.deleteUser(user.user_id);
              await loadUsers();
            } catch (err: any) {
              setError(err.message || 'Failed to delete user');
            }
          },
        },
      ]
    );
  };

  const isProtectedUser = (user: User) => {
    return PROTECTED_USER_NAMES.includes(user.display_name);
  };

  const renderUser = ({ item }: { item: User }) => (
    <View style={styles.userItemContainer}>
      <TouchableOpacity
        style={styles.userItem}
        onPress={() => handleSelectUser(item)}
      >
        <Text style={styles.userName}>{item.display_name}</Text>
        <Text style={styles.userRelationship}>{item.relationship}</Text>
      </TouchableOpacity>
      {!isProtectedUser(item) && (
        <TouchableOpacity
          style={styles.deleteButton}
          onPress={() => handleDeleteUser(item)}
        >
          <Text style={styles.deleteButtonText}>X</Text>
        </TouchableOpacity>
      )}
    </View>
  );

  if (isLoading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color={colors.accent} />
        <Text style={styles.loadingText}>Connecting...</Text>
      </View>
    );
  }

  // When showing onboarding form, render it directly without the login screen wrapper
  if (showCreateForm) {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        {error && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}
        <OnboardingForm
          onSubmit={handleCreateUser}
          onCancel={() => {
            setShowCreateForm(false);
            setError(null);
          }}
          isSubmitting={isCreating}
        />
      </KeyboardAvoidingView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={styles.header}>
        <Text style={styles.title}>Cass Vessel</Text>
        <Text style={styles.subtitle}>Select your profile</Text>
      </View>

      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity onPress={loadUsers} style={styles.retryButton}>
            <Text style={styles.retryButtonText}>Retry</Text>
          </TouchableOpacity>
        </View>
      )}

      {users.length > 0 ? (
        <FlatList
          data={users}
          keyExtractor={(item) => item.user_id}
          renderItem={renderUser}
          style={styles.userList}
          contentContainerStyle={styles.userListContent}
        />
      ) : (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No users yet</Text>
          <Text style={styles.emptySubtext}>Create your profile to get started</Text>
        </View>
      )}

      <TouchableOpacity
        style={styles.createButton}
        onPress={() => setShowCreateForm(true)}
      >
        <Text style={styles.createButtonText}>+ New User</Text>
      </TouchableOpacity>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    paddingHorizontal: 20,
  },
  header: {
    marginTop: 60,
    marginBottom: 40,
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: colors.textMuted,
  },
  loadingText: {
    marginTop: 16,
    color: colors.textMuted,
    fontSize: 16,
  },
  errorContainer: {
    backgroundColor: colors.error + '20',
    padding: 16,
    borderRadius: 12,
    marginBottom: 20,
    alignItems: 'center',
  },
  errorText: {
    color: colors.error,
    fontSize: 14,
    marginBottom: 8,
  },
  retryButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  retryButtonText: {
    color: colors.accent,
    fontWeight: '600',
  },
  userList: {
    flex: 1,
  },
  userListContent: {
    paddingBottom: 20,
  },
  userItemContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  userItem: {
    flex: 1,
    backgroundColor: colors.surface,
    padding: 16,
    borderRadius: 12,
  },
  userName: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  userRelationship: {
    fontSize: 14,
    color: colors.textMuted,
    textTransform: 'capitalize',
  },
  deleteButton: {
    backgroundColor: colors.error,
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: 12,
  },
  deleteButtonText: {
    color: colors.textPrimary,
    fontSize: 14,
    fontWeight: '700',
  },
  emptyState: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 18,
    color: colors.textPrimary,
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: colors.textMuted,
  },
  createButton: {
    backgroundColor: colors.accent,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    marginBottom: 40,
  },
  createButtonText: {
    color: colors.textPrimary,
    fontSize: 16,
    fontWeight: '600',
  },
  createForm: {
    flex: 1,
    justifyContent: 'center',
  },
  formTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 24,
    textAlign: 'center',
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: colors.textPrimary,
    marginBottom: 16,
  },
  formButtons: {
    flexDirection: 'row',
    gap: 12,
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
    flex: 1,
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
