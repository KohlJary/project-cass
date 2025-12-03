/**
 * Conversation list drawer/modal component
 */

import React, { useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Modal,
} from 'react-native';
import { useChatStore } from '../store/chatStore';
import { useUserStore } from '../store/userStore';
import { apiClient } from '../api/client';
import { colors } from '../theme/colors';
import { Conversation } from '../api/types';

interface Props {
  visible: boolean;
  onClose: () => void;
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } else if (diffDays === 1) {
    return 'Yesterday';
  } else if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: 'short' });
  } else {
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }
}

export function ConversationList({ visible, onClose }: Props) {
  const {
    conversations,
    setConversations,
    currentConversationId,
    setCurrentConversationId,
    setMessages,
    clearMessages,
    isLoadingConversations,
    setLoadingConversations,
  } = useChatStore();
  const { userId } = useUserStore();

  useEffect(() => {
    if (visible) {
      loadConversations();
    }
  }, [visible]);

  const loadConversations = async () => {
    setLoadingConversations(true);
    try {
      const convs = await apiClient.listConversations(userId || undefined);
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setLoadingConversations(false);
    }
  };

  const selectConversation = async (conv: Conversation) => {
    setCurrentConversationId(conv.id);
    clearMessages();

    // Load conversation messages
    try {
      const data = await apiClient.getConversation(conv.id);
      if (data.messages) {
        setMessages(
          data.messages.map((m: any, i: number) => ({
            id: `loaded-${i}`,
            role: m.role,
            content: m.content,
            timestamp: m.timestamp,
            inputTokens: m.input_tokens,
            outputTokens: m.output_tokens,
            provider: m.provider,
            model: m.model,
          }))
        );
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }

    onClose();
  };

  const createNewConversation = async () => {
    try {
      const conv = await apiClient.createConversation(undefined, userId || undefined);
      setCurrentConversationId(conv.id);
      clearMessages();
      await loadConversations();
      onClose();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const renderConversation = ({ item }: { item: Conversation }) => {
    const isSelected = item.id === currentConversationId;

    return (
      <TouchableOpacity
        style={[styles.conversationItem, isSelected && styles.selectedItem]}
        onPress={() => selectConversation(item)}
      >
        <View style={styles.conversationContent}>
          <Text style={styles.conversationTitle} numberOfLines={1}>
            {item.title}
          </Text>
          <Text style={styles.conversationMeta}>
            {item.message_count} messages • {formatDate(item.updated_at)}
          </Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={true}
      onRequestClose={onClose}
    >
      <View style={styles.overlay}>
        <View style={styles.container}>
          <View style={styles.header}>
            <Text style={styles.headerTitle}>Conversations</Text>
            <TouchableOpacity onPress={onClose} style={styles.closeButton}>
              <Text style={styles.closeButtonText}>✕</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={styles.newButton} onPress={createNewConversation}>
            <Text style={styles.newButtonText}>+ New Conversation</Text>
          </TouchableOpacity>

          {isLoadingConversations ? (
            <ActivityIndicator size="large" color={colors.accent} style={styles.loader} />
          ) : (
            <FlatList
              data={conversations}
              keyExtractor={(item) => item.id}
              renderItem={renderConversation}
              contentContainerStyle={styles.list}
              showsVerticalScrollIndicator={false}
            />
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  container: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '80%',
    paddingBottom: 30,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.background,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
  },
  closeButton: {
    padding: 4,
  },
  closeButtonText: {
    fontSize: 20,
    color: colors.textMuted,
  },
  newButton: {
    margin: 12,
    padding: 14,
    backgroundColor: colors.accent,
    borderRadius: 10,
    alignItems: 'center',
  },
  newButtonText: {
    color: colors.textPrimary,
    fontWeight: '600',
    fontSize: 15,
  },
  list: {
    padding: 12,
  },
  conversationItem: {
    padding: 14,
    borderRadius: 10,
    marginBottom: 8,
    backgroundColor: colors.background,
  },
  selectedItem: {
    backgroundColor: colors.userBubble,
  },
  conversationContent: {
    flex: 1,
  },
  conversationTitle: {
    fontSize: 15,
    fontWeight: '500',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  conversationMeta: {
    fontSize: 12,
    color: colors.textMuted,
  },
  loader: {
    marginTop: 40,
  },
});
