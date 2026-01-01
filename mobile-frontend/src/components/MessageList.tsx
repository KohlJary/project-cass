/**
 * Scrollable list of chat messages with jump-to-present button
 */

import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  FlatList,
  StyleSheet,
  View,
  TouchableOpacity,
  Text,
  Animated,
  NativeSyntheticEvent,
  NativeScrollEvent,
} from 'react-native';
import { MessageBubble } from './MessageBubble';
import { Message } from '../api/types';
import { colors } from '../theme/colors';

interface Props {
  messages: Message[];
}

// How far from bottom before showing the button (in pixels)
const SCROLL_THRESHOLD = 200;

export function MessageList({ messages }: Props) {
  const flatListRef = useRef<FlatList>(null);
  const [showJumpButton, setShowJumpButton] = useState(false);
  const buttonOpacity = useRef(new Animated.Value(0)).current;

  // Animate button visibility
  useEffect(() => {
    Animated.timing(buttonOpacity, {
      toValue: showJumpButton ? 1 : 0,
      duration: 200,
      useNativeDriver: true,
    }).start();
  }, [showJumpButton, buttonOpacity]);

  // Auto-scroll to bottom when new messages arrive (only if already near bottom)
  useEffect(() => {
    if (messages.length > 0 && !showJumpButton) {
      setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 100);
    }
  }, [messages.length, showJumpButton]);

  const handleScroll = useCallback((event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceFromBottom = contentSize.height - layoutMeasurement.height - contentOffset.y;
    setShowJumpButton(distanceFromBottom > SCROLL_THRESHOLD);
  }, []);

  const jumpToPresent = useCallback(() => {
    flatListRef.current?.scrollToEnd({ animated: true });
    setShowJumpButton(false);
  }, []);

  return (
    <View style={styles.wrapper}>
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.content}
        style={styles.list}
        showsVerticalScrollIndicator={false}
        onScroll={handleScroll}
        scrollEventThrottle={16}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            {/* Empty state - just show nothing for now */}
          </View>
        }
      />

      {/* Jump to Present Button */}
      <Animated.View
        style={[styles.jumpButtonContainer, { opacity: buttonOpacity }]}
        pointerEvents={showJumpButton ? 'auto' : 'none'}
      >
        <TouchableOpacity
          style={styles.jumpButton}
          onPress={jumpToPresent}
          activeOpacity={0.8}
        >
          <Text style={styles.jumpButtonText}>↓ Jump to present</Text>
        </TouchableOpacity>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flex: 1,
    position: 'relative',
  },
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
  jumpButtonContainer: {
    position: 'absolute',
    bottom: 12,
    alignSelf: 'center',
  },
  jumpButton: {
    backgroundColor: colors.surface,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 4,
  },
  jumpButtonText: {
    color: colors.accent,
    fontSize: 13,
    fontWeight: '600',
  },
});
