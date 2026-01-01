/**
 * Chat screen - main conversation interface
 */

import React, { useCallback, useState, useEffect, useRef } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Text,
  KeyboardAvoidingView,
  Platform,
  Modal,
  Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ConnectionStatus } from '../components/ConnectionStatus';
import { MessageList } from '../components/MessageList';
import { TypingIndicator } from '../components/TypingIndicator';
import { InputBar } from '../components/InputBar';
import { ConversationList } from '../components/ConversationList';
import { SummaryPanel } from '../components/SummaryPanel';
import { useWebSocket } from '../hooks/useWebSocket';
import { useChatStore } from '../store/chatStore';
import { apiClient } from '../api/client';
import { colors } from '../theme/colors';
import { Message } from '../api/types';

interface Props {
  userId: string;
  displayName: string;
  onLogout: () => void;
}

export function ChatScreen({
  userId,
  displayName,
  onLogout,
}: Props) {
  const { sendMessage, isConnected } = useWebSocket();
  const {
    messages,
    addMessage,
    setMessages,
    conversations,
    setConversations,
    currentConversationId,
    setCurrentConversationId,
  } = useChatStore();

  // Track if we've initialized to avoid duplicate loads
  const hasInitialized = useRef(false);

  // Get current conversation title
  const currentConversation = conversations.find(c => c.id === currentConversationId);
  const conversationTitle = currentConversation?.title;
  const [showConversations, setShowConversations] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  // Load continuous conversation and recent history on mount
  useEffect(() => {
    if (hasInitialized.current) return;
    hasInitialized.current = true;

    const initializeChat = async () => {
      try {
        // Get or create the continuous conversation (the main stream for this user)
        const continuousConv = await apiClient.getContinuousConversation();
        setCurrentConversationId(continuousConv.id);
        console.log(`Using continuous conversation: ${continuousConv.id}`);

        // Also load conversations list for the sidebar
        const convs = await apiClient.listConversations(userId);
        setConversations(convs);

        // Load recent messages from the past 2 hours
        try {
          const { messages: recentMessages } = await apiClient.getConversationMessages(
            continuousConv.id,
            { sinceHours: 2 }
          );

          if (recentMessages.length > 0) {
            // Map to our Message format
            const formattedMessages: Message[] = recentMessages.map((m, i) => ({
              id: `history-${i}`,
              role: m.role,
              content: m.content,
              timestamp: m.timestamp,
              inputTokens: m.inputTokens,
              outputTokens: m.outputTokens,
              provider: m.provider,
              model: m.model,
            }));
            setMessages(formattedMessages);
            console.log(`Loaded ${formattedMessages.length} recent messages from continuous conversation`);
          }
        } catch (err) {
          console.error('Failed to load recent messages:', err);
        }
      } catch (err) {
        console.error('Failed to initialize chat:', err);
      }
    };

    initializeChat();
  }, [userId, setConversations, setCurrentConversationId, setMessages]);

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
    <SafeAreaView style={styles.container} edges={['top']}>
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
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
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

const styles = StyleSheet.create({
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
