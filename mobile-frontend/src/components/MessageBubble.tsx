/**
 * Message bubble component with markdown rendering and token display
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { Message } from '../api/types';
import { colors } from '../theme/colors';

interface Props {
  message: Message;
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function shortenModel(model?: string): string {
  if (!model) return '';
  if (model.includes('claude')) {
    return model.replace('claude-', '').split('-2')[0];
  }
  return model;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <View style={styles.systemContainer}>
        <Text style={styles.systemText}>{message.content}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, isUser ? styles.userContainer : styles.assistantContainer]}>
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.assistantBubble]}>
        <Markdown style={isUser ? userMarkdownStyles : assistantMarkdownStyles}>
          {message.content}
        </Markdown>

        <View style={styles.footer}>
          <Text style={styles.timestamp}>{formatTime(message.timestamp)}</Text>

          {!isUser && message.outputTokens !== undefined && (
            <Text style={styles.tokenInfo}>
              {message.inputTokens}/{message.outputTokens}
              {message.model && ` • ${shortenModel(message.model)}`}
            </Text>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 4,
    marginHorizontal: 12,
  },
  userContainer: {
    alignItems: 'flex-end',
  },
  assistantContainer: {
    alignItems: 'flex-start',
  },
  bubble: {
    maxWidth: '85%',
    padding: 12,
    borderRadius: 16,
  },
  userBubble: {
    backgroundColor: colors.userBubble,
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    backgroundColor: colors.assistantBubble,
    borderBottomLeftRadius: 4,
  },
  systemContainer: {
    alignItems: 'center',
    marginVertical: 8,
    paddingHorizontal: 20,
  },
  systemText: {
    color: colors.textMuted,
    fontSize: 12,
    textAlign: 'center',
    fontStyle: 'italic',
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 6,
    gap: 8,
  },
  timestamp: {
    fontSize: 10,
    color: colors.textMuted,
  },
  tokenInfo: {
    fontSize: 10,
    color: colors.textMuted,
  },
});

const baseMarkdownStyles = {
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  code_inline: {
    backgroundColor: 'rgba(0,0,0,0.2)',
    paddingHorizontal: 4,
    borderRadius: 4,
    fontFamily: 'monospace',
  },
  code_block: {
    backgroundColor: 'rgba(0,0,0,0.3)',
    padding: 12,
    borderRadius: 8,
    fontFamily: 'monospace',
  },
  fence: {
    backgroundColor: 'rgba(0,0,0,0.3)',
    padding: 12,
    borderRadius: 8,
    fontFamily: 'monospace',
  },
};

const userMarkdownStyles = {
  ...baseMarkdownStyles,
  body: { ...baseMarkdownStyles.body, color: colors.textOnUser },
  code_inline: { ...baseMarkdownStyles.code_inline, color: colors.textOnUser },
  code_block: { ...baseMarkdownStyles.code_block, color: colors.textOnUser },
  fence: { ...baseMarkdownStyles.fence, color: colors.textOnUser },
};

const assistantMarkdownStyles = {
  ...baseMarkdownStyles,
  body: { ...baseMarkdownStyles.body, color: colors.textOnAssistant },
  code_inline: { ...baseMarkdownStyles.code_inline, color: colors.textOnAssistant },
  code_block: { ...baseMarkdownStyles.code_block, color: colors.textOnAssistant },
  fence: { ...baseMarkdownStyles.fence, color: colors.textOnAssistant },
};
