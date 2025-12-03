/**
 * Cass Vessel Mobile - Main App
 */

import React, { useCallback, useState, useEffect } from 'react';
import { StyleSheet, View, TouchableOpacity, Text, KeyboardAvoidingView, Platform, ActivityIndicator, Modal, Pressable } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { ConnectionStatus } from './src/components/ConnectionStatus';
import { MessageList } from './src/components/MessageList';
import { TypingIndicator } from './src/components/TypingIndicator';
import { InputBar } from './src/components/InputBar';
import { ConversationList } from './src/components/ConversationList';
import { LoginScreen } from './src/components/LoginScreen';
import { SummaryPanel } from './src/components/SummaryPanel';
import { useWebSocket } from './src/hooks/useWebSocket';
import { useChatStore } from './src/store/chatStore';
import { useUserStore } from './src/store/userStore';
import { apiClient } from './src/api/client';
import { colors } from './src/theme/colors';

interface ChatScreenProps {
  onLogout: () => void;
  pendingOnboarding: boolean;
  onOnboardingComplete: () => void;
}

function ChatScreen({ onLogout, pendingOnboarding, onOnboardingComplete }: ChatScreenProps) {
  const { sendMessage, sendOnboardingIntro, reconnect, isConnected } = useWebSocket();
  const { messages, addMessage, conversations, currentConversationId, setCurrentConversationId } = useChatStore();
  const { userId, displayName } = useUserStore();

  // Get current conversation title
  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const conversationTitle = currentConversation?.title;
  const [showConversations, setShowConversations] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [onboardingTriggered, setOnboardingTriggered] = useState(false);
  const [awaitingConnection, setAwaitingConnection] = useState(false);

  // Step 1: When pendingOnboarding, force a fresh WebSocket connection
  useEffect(() => {
    if (pendingOnboarding && !onboardingTriggered && !awaitingConnection) {
      console.log('New user onboarding: forcing WebSocket reconnection');
      setAwaitingConnection(true);
      reconnect();
    }
  }, [pendingOnboarding, onboardingTriggered, awaitingConnection, reconnect]);

  // Step 2: When connected (after reconnect), trigger the onboarding
  useEffect(() => {
    const triggerOnboarding = async () => {
      if (pendingOnboarding && isConnected && awaitingConnection && !onboardingTriggered) {
        console.log('WebSocket connected, triggering onboarding intro');
        setOnboardingTriggered(true);
        try {
          // Create a new conversation for the intro (with user_id)
          const conversation = await apiClient.createConversation('First Conversation', userId || undefined);
          setCurrentConversationId(conversation.id);

          // Small delay before sending to ensure conversation is set in state
          await new Promise(resolve => setTimeout(resolve, 100));

          // Send onboarding intro message
          const sent = sendOnboardingIntro(conversation.id);
          console.log('Onboarding intro sent:', sent, 'conversation:', conversation.id);

          // Mark onboarding as complete
          onOnboardingComplete();
          setAwaitingConnection(false);
        } catch (err) {
          console.error('Failed to trigger onboarding:', err);
          setOnboardingTriggered(false);
          setAwaitingConnection(false);
        }
      }
    };
    triggerOnboarding();
  }, [pendingOnboarding, isConnected, awaitingConnection, onboardingTriggered]);

  const handleSend = useCallback(
    (text: string) => {
      // Add user message locally
      addMessage({
        role: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      });

      // Send via WebSocket with conversation ID
      sendMessage(text, currentConversationId);
    },
    [sendMessage, addMessage, currentConversationId]
  );

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity
          style={styles.menuButton}
          onPress={() => setShowConversations(true)}
        >
          <Text style={styles.menuButtonText}>☰</Text>
        </TouchableOpacity>
        <ConnectionStatus />
        <View style={styles.headerSpacer} />
        <TouchableOpacity
          style={styles.userMenuButton}
          onPress={() => setShowUserMenu(true)}
        >
          <Text style={styles.userIndicator}>{displayName}</Text>
          <Text style={styles.userMenuIcon}>▼</Text>
        </TouchableOpacity>
      </View>

      {/* User Menu Modal */}
      <Modal
        visible={showUserMenu}
        transparent
        animationType="fade"
        onRequestClose={() => setShowUserMenu(false)}
      >
        <Pressable style={styles.menuOverlay} onPress={() => setShowUserMenu(false)}>
          <View style={styles.userMenuContainer}>
            <Text style={styles.userMenuHeader}>{displayName}</Text>
            <TouchableOpacity
              style={styles.userMenuItem}
              onPress={() => {
                setShowUserMenu(false);
                onLogout();
              }}
            >
              <Text style={styles.userMenuItemText}>Logout</Text>
            </TouchableOpacity>
          </View>
        </Pressable>
      </Modal>

      <SummaryPanel
        conversationId={currentConversationId}
        conversationTitle={conversationTitle}
      />

      <KeyboardAvoidingView
        style={styles.chatContainer}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
      >
        <MessageList messages={messages} />
        <TypingIndicator />
        <InputBar onSend={handleSend} disabled={!isConnected} />
      </KeyboardAvoidingView>
      <ConversationList
        visible={showConversations}
        onClose={() => setShowConversations(false)}
      />
    </SafeAreaView>
  );
}

export default function App() {
  const { userId, isLoading, loadUserId, setUser } = useUserStore();
  const [isValidating, setIsValidating] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [pendingOnboarding, setPendingOnboarding] = useState(false);

  useEffect(() => {
    const initUser = async () => {
      await loadUserId();
      const { userId: storedId } = useUserStore.getState();

      if (!storedId) {
        // No stored user - show login
        setNeedsLogin(true);
        return;
      }

      // Validate stored user still exists on backend
      setIsValidating(true);
      try {
        const user = await apiClient.getUser(storedId);
        // User exists, update display name and proceed to chat
        await setUser(storedId, user.display_name);
        setNeedsLogin(false);
      } catch (err) {
        // User doesn't exist or server error - show login
        console.log('Stored user not found, showing login');
        setNeedsLogin(true);
      } finally {
        setIsValidating(false);
      }
    };
    initUser();
  }, []);

  const handleLogin = async (selectedUserId: string, displayName: string, isNewUser = false) => {
    await setUser(selectedUserId, displayName);
    setNeedsLogin(false);
    if (isNewUser) {
      setPendingOnboarding(true);
    }
  };

  const handleOnboardingComplete = () => {
    setPendingOnboarding(false);
  };

  const handleLogout = async () => {
    const { clearUserId } = useUserStore.getState();
    await clearUserId();
    setNeedsLogin(true);
  };

  if (isLoading || isValidating) {
    return (
      <SafeAreaProvider>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.accent} />
        </View>
      </SafeAreaProvider>
    );
  }

  if (needsLogin || !userId) {
    return (
      <SafeAreaProvider>
        <StatusBar style="light" />
        <LoginScreen onLogin={handleLogin} />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <ChatScreen
        onLogout={handleLogout}
        pendingOnboarding={pendingOnboarding}
        onOnboardingComplete={handleOnboardingComplete}
      />
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
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  menuButton: {
    padding: 8,
    marginRight: 8,
  },
  menuButtonText: {
    fontSize: 24,
    color: colors.textPrimary,
  },
  headerSpacer: {
    flex: 1,
  },
  userMenuButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
  },
  userIndicator: {
    fontSize: 14,
    color: colors.textMuted,
  },
  userMenuIcon: {
    fontSize: 10,
    color: colors.textMuted,
    marginLeft: 4,
  },
  menuOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-start',
    alignItems: 'flex-end',
    paddingTop: 60,
    paddingRight: 12,
  },
  userMenuContainer: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    minWidth: 150,
    overflow: 'hidden',
  },
  userMenuHeader: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.textPrimary,
    padding: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.background,
  },
  userMenuItem: {
    padding: 12,
  },
  userMenuItemText: {
    fontSize: 14,
    color: colors.error,
  },
  chatContainer: {
    flex: 1,
  },
});
