/**
 * Phase 3: Collaborative Demo
 *
 * A mini-chat experience where users experience genuine collaboration.
 * Cass proposes a collaborative exercise based on user preferences.
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { colors } from '../../theme/colors';
import { UserProfileData, WebSocketMessage, WebSocketResponse, Animation } from '../../api/types';
import { useAuthStore } from '../../store/authStore';

interface DemoMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  animations?: Animation[];
}

interface Props {
  displayName: string;
  userId: string;
  profile: Partial<UserProfileData>;
  onContinue: () => void;
  onSkip: () => void;
  canSkip: boolean;
}

// WebSocket URL - same as main app
const WS_BASE_URL = 'wss://serial-around-described-cut.trycloudflare.com/ws';

export function OnboardingDemo({
  displayName,
  userId,
  profile,
  onContinue,
  onSkip,
  canSkip,
}: Props) {
  const [messages, setMessages] = useState<DemoMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [exchangeCount, setExchangeCount] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  // Connect WebSocket and trigger initial demo
  useEffect(() => {
    const { accessToken } = useAuthStore.getState();
    if (!accessToken) return;

    const wsUrl = `${WS_BASE_URL}?token=${encodeURIComponent(accessToken)}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      console.log('Demo WebSocket connected');
      setIsConnected(true);

      // Send initial demo request
      const message: WebSocketMessage = {
        type: 'onboarding_demo',
        user_id: userId,
        profile: profile,
      };
      ws.current?.send(JSON.stringify(message));
      setIsThinking(true);
    };

    ws.current.onmessage = (event) => {
      try {
        const data: WebSocketResponse = JSON.parse(event.data);

        if (data.type === 'thinking') {
          setIsThinking(true);
        } else if (data.type === 'response') {
          setIsThinking(false);
          const newMessage: DemoMessage = {
            id: `cass-${Date.now()}`,
            role: 'assistant',
            content: stripGestureTags(data.text || ''),
            animations: data.animations,
          };
          setMessages((prev) => [...prev, newMessage]);
          setExchangeCount((prev) => prev + 1);
        } else if (data.type === 'error') {
          console.error('Demo error:', data.message);
          setIsThinking(false);
        }
      } catch (error) {
        console.error('Failed to parse demo message:', error);
      }
    };

    ws.current.onerror = (error) => {
      console.error('Demo WebSocket error:', error);
      setIsConnected(false);
    };

    ws.current.onclose = () => {
      console.log('Demo WebSocket closed');
      setIsConnected(false);
    };

    return () => {
      ws.current?.close();
    };
  }, [userId, profile]);

  // Strip gesture/emote tags from display text
  const stripGestureTags = (text: string): string => {
    return text.replace(/<(gesture|emote):[^>]+>/g, '').trim();
  };

  const handleSend = () => {
    if (!inputText.trim() || !ws.current || ws.current.readyState !== WebSocket.OPEN) return;

    // Add user message
    const userMessage: DemoMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: inputText.trim(),
    };
    setMessages((prev) => [...prev, userMessage]);

    // Send to backend
    const message: WebSocketMessage = {
      type: 'onboarding_demo',
      user_id: userId,
      profile: profile,
      message: inputText.trim(),
    };
    ws.current.send(JSON.stringify(message));

    setInputText('');
    setIsThinking(true);

    // Scroll to bottom
    setTimeout(() => {
      scrollViewRef.current?.scrollToEnd({ animated: true });
    }, 100);
  };

  // Show continue button after 2 exchanges
  const showContinue = exchangeCount >= 2;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 100 : 0}
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Let's Think Together</Text>
        <Text style={styles.subtitle}>
          This is what collaboration looks like. Not me doing things for you,
          but us thinking through something together.
        </Text>
      </View>

      {/* Chat Area */}
      <View style={styles.chatContainer}>
        <ScrollView
          ref={scrollViewRef}
          style={styles.messageList}
          contentContainerStyle={styles.messageListContent}
          showsVerticalScrollIndicator={false}
          onContentSizeChange={() => scrollViewRef.current?.scrollToEnd({ animated: true })}
        >
          {messages.map((msg) => (
            <View
              key={msg.id}
              style={[
                styles.messageBubble,
                msg.role === 'user' ? styles.userBubble : styles.assistantBubble,
              ]}
            >
              <Text
                style={[
                  styles.messageText,
                  msg.role === 'user' ? styles.userText : styles.assistantText,
                ]}
              >
                {msg.content}
              </Text>
            </View>
          ))}

          {isThinking && (
            <View style={[styles.messageBubble, styles.assistantBubble, styles.thinkingBubble]}>
              <ActivityIndicator size="small" color={colors.textOnAssistant} />
              <Text style={styles.thinkingText}>Cass is thinking...</Text>
            </View>
          )}
        </ScrollView>

        {/* Input Area */}
        <View style={styles.inputContainer}>
          <TextInput
            style={styles.input}
            placeholder="Share your thoughts..."
            placeholderTextColor={colors.placeholder}
            value={inputText}
            onChangeText={setInputText}
            multiline
            maxLength={500}
            editable={isConnected && !isThinking}
          />
          <TouchableOpacity
            style={[styles.sendButton, (!inputText.trim() || isThinking) && styles.sendButtonDisabled]}
            onPress={handleSend}
            disabled={!inputText.trim() || isThinking}
          >
            <Text style={styles.sendButtonText}>Send</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Footer */}
      <View style={styles.footer}>
        {showContinue ? (
          <TouchableOpacity style={styles.continueButton} onPress={onContinue}>
            <Text style={styles.continueButtonText}>Continue to Tour</Text>
          </TouchableOpacity>
        ) : (
          <Text style={styles.hintText}>
            Have a quick exchange with Cass to see how this works
          </Text>
        )}

        {canSkip && (
          <TouchableOpacity style={styles.skipButton} onPress={onSkip}>
            <Text style={styles.skipButtonText}>Skip to chat</Text>
          </TouchableOpacity>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    padding: 24,
    paddingBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: colors.textMuted,
    lineHeight: 20,
  },
  chatContainer: {
    flex: 1,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  messageList: {
    flex: 1,
  },
  messageListContent: {
    padding: 16,
    gap: 12,
  },
  messageBubble: {
    maxWidth: '85%',
    padding: 14,
    borderRadius: 16,
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: colors.userBubble,
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    backgroundColor: colors.assistantBubble,
    borderBottomLeftRadius: 4,
  },
  messageText: {
    fontSize: 15,
    lineHeight: 22,
  },
  userText: {
    color: colors.textOnUser,
  },
  assistantText: {
    color: colors.textOnAssistant,
  },
  thinkingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  thinkingText: {
    fontSize: 14,
    color: colors.textOnAssistant,
    fontStyle: 'italic',
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignItems: 'flex-end',
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.textPrimary,
    maxHeight: 100,
  },
  sendButton: {
    backgroundColor: colors.accent,
    borderRadius: 20,
    paddingHorizontal: 20,
    paddingVertical: 12,
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
  sendButtonText: {
    color: colors.textPrimary,
    fontWeight: '600',
    fontSize: 15,
  },
  footer: {
    padding: 24,
    paddingTop: 16,
    gap: 12,
    alignItems: 'center',
  },
  hintText: {
    fontSize: 14,
    color: colors.textMuted,
    textAlign: 'center',
  },
  continueButton: {
    width: '100%',
    backgroundColor: colors.accent,
    padding: 18,
    borderRadius: 16,
    alignItems: 'center',
  },
  continueButtonText: {
    color: colors.textPrimary,
    fontSize: 18,
    fontWeight: '600',
  },
  skipButton: {
    padding: 12,
  },
  skipButtonText: {
    color: colors.textMuted,
    fontSize: 14,
  },
});
