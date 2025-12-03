/**
 * Scrollable list of chat messages
 */

import React, { useRef, useEffect } from 'react';
import { FlatList, StyleSheet, View } from 'react-native';
import { MessageBubble } from './MessageBubble';
import { Message } from '../api/types';
import { colors } from '../theme/colors';

interface Props {
  messages: Message[];
}

export function MessageList({ messages }: Props) {
  const flatListRef = useRef<FlatList>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages.length]);

  return (
    <FlatList
      ref={flatListRef}
      data={messages}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <MessageBubble message={item} />}
      contentContainerStyle={styles.content}
      style={styles.list}
      showsVerticalScrollIndicator={false}
      ListEmptyComponent={
        <View style={styles.emptyContainer}>
          {/* Empty state - just show nothing for now */}
        </View>
      }
    />
  );
}

const styles = StyleSheet.create({
  list: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    paddingVertical: 8,
    flexGrow: 1,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
