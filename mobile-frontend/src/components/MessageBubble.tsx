/**
 * Message bubble component with markdown rendering, token display, and internal thoughts
 */

import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { Message } from '../api/types';
import { colors } from '../theme/colors';
import { parseGestureTags } from '../utils/gestures';

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
  const [showThinking, setShowThinking] = useState(false);
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  // Parse gesture tags for assistant messages
  const parsed = !isUser && !isSystem ? parseGestureTags(message.content) : null;
  const displayContent = parsed ? parsed.text : message.content;

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
        {/* Internal thinking/reasoning section */}
        {parsed?.thinking && (
          <View style={styles.thinkingContainer}>
            <TouchableOpacity
              style={styles.thinkingHeader}
              onPress={() => setShowThinking(!showThinking)}
              activeOpacity={0.7}
            >
              <Text style={styles.thinkingToggle}>
                {showThinking ? '▼' : '▶'} Internal reasoning
              </Text>
            </TouchableOpacity>
            {showThinking && (
              <View style={styles.thinkingContent}>
                <Text style={styles.thinkingText}>{parsed.thinking}</Text>
              </View>
            )}
          </View>
        )}

        {/* Main message content */}
        <Markdown style={isUser ? userMarkdownStyles : assistantMarkdownStyles}>
          {displayContent}
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
  // Internal thinking styles
  thinkingContainer: {
    marginBottom: 10,
    backgroundColor: 'rgba(0, 0, 0, 0.15)',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    overflow: 'hidden',
  },
  thinkingHeader: {
    padding: 8,
    paddingHorizontal: 10,
  },
  thinkingToggle: {
    color: 'rgba(255, 255, 255, 0.6)',
    fontSize: 12,
    fontStyle: 'italic',
  },
  thinkingContent: {
    padding: 10,
    paddingTop: 0,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
  },
  thinkingText: {
    color: 'rgba(255, 255, 255, 0.5)',
    fontSize: 13,
    lineHeight: 18,
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
