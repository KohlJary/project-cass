/**
 * Typing indicator - shows "Cass is thinking..." during response generation
 */

import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { useChatStore } from '../store/chatStore';
import { colors } from '../theme/colors';

export function TypingIndicator() {
  const { isThinking, thinkingStatus } = useChatStore();
  const dot1 = useRef(new Animated.Value(0)).current;
  const dot2 = useRef(new Animated.Value(0)).current;
  const dot3 = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!isThinking) return;

    const createAnimation = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, {
            toValue: 1,
            duration: 300,
            useNativeDriver: true,
          }),
          Animated.timing(dot, {
            toValue: 0,
            duration: 300,
            useNativeDriver: true,
          }),
        ])
      );

    const animation = Animated.parallel([
      createAnimation(dot1, 0),
      createAnimation(dot2, 150),
      createAnimation(dot3, 300),
    ]);

    animation.start();

    return () => animation.stop();
  }, [isThinking, dot1, dot2, dot3]);

  if (!isThinking) return null;

  return (
    <View style={styles.container}>
      <View style={styles.bubble}>
        <Text style={styles.text}>
          {thinkingStatus || 'Cass is thinking'}
        </Text>
        <View style={styles.dots}>
          <Animated.View
            style={[
              styles.dot,
              { opacity: dot1, transform: [{ scale: Animated.add(0.5, Animated.multiply(dot1, 0.5)) }] },
            ]}
          />
          <Animated.View
            style={[
              styles.dot,
              { opacity: dot2, transform: [{ scale: Animated.add(0.5, Animated.multiply(dot2, 0.5)) }] },
            ]}
          />
          <Animated.View
            style={[
              styles.dot,
              { opacity: dot3, transform: [{ scale: Animated.add(0.5, Animated.multiply(dot3, 0.5)) }] },
            ]}
          />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  bubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.assistantBubble,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    alignSelf: 'flex-start',
    maxWidth: '80%',
  },
  text: {
    color: colors.textOnAssistant,
    fontSize: 14,
    fontStyle: 'italic',
  },
  dots: {
    flexDirection: 'row',
    marginLeft: 8,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.textOnAssistant,
    marginHorizontal: 2,
  },
});
