/**
 * Connection status indicator - shows green/red dot for WebSocket state
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useChatStore } from '../store/chatStore';
import { colors } from '../theme/colors';

export function ConnectionStatus() {
  const { isConnected, isConnecting } = useChatStore();

  const statusColor = isConnected
    ? colors.success
    : isConnecting
    ? colors.warning
    : colors.error;

  const statusText = isConnected
    ? 'Connected'
    : isConnecting
    ? 'Connecting...'
    : 'Disconnected';

  return (
    <View style={styles.container}>
      <View style={[styles.dot, { backgroundColor: statusColor }]} />
      <Text style={styles.text}>{statusText}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: colors.surface,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 8,
  },
  text: {
    color: colors.textMuted,
    fontSize: 12,
  },
});
