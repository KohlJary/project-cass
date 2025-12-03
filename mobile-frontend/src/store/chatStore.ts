/**
 * Zustand store for chat state
 */

import { create } from 'zustand';
import { Message, Conversation } from '../api/types';

interface ChatState {
  // State
  messages: Message[];
  conversations: Conversation[];
  currentConversationId: string | null;
  isThinking: boolean;
  thinkingStatus: string;
  isConnected: boolean;
  isConnecting: boolean;
  isLoadingConversations: boolean;

  // Actions
  addMessage: (message: Omit<Message, 'id'>) => void;
  setMessages: (messages: Message[]) => void;
  clearMessages: () => void;
  setConversations: (conversations: Conversation[]) => void;
  setCurrentConversationId: (id: string | null) => void;
  setThinking: (thinking: boolean) => void;
  setThinkingStatus: (status: string) => void;
  setConnected: (connected: boolean) => void;
  setConnecting: (connecting: boolean) => void;
  setLoadingConversations: (loading: boolean) => void;
}

let messageIdCounter = 0;

export const useChatStore = create<ChatState>((set) => ({
  // Initial state
  messages: [],
  conversations: [],
  currentConversationId: null,
  isThinking: false,
  thinkingStatus: '',
  isConnected: false,
  isConnecting: false,
  isLoadingConversations: false,

  // Actions
  addMessage: (message) =>
    set((state) => ({
      messages: [
        ...state.messages,
        { ...message, id: `msg-${++messageIdCounter}` },
      ],
    })),

  setMessages: (messages) => set({ messages }),

  clearMessages: () => set({ messages: [] }),

  setConversations: (conversations) => set({ conversations }),

  setCurrentConversationId: (id) => set({ currentConversationId: id }),

  setThinking: (thinking) =>
    set({ isThinking: thinking, thinkingStatus: thinking ? 'Thinking...' : '' }),

  setThinkingStatus: (status) => set({ thinkingStatus: status }),

  setConnected: (connected) =>
    set({ isConnected: connected, isConnecting: false }),

  setConnecting: (connecting) => set({ isConnecting: connecting }),

  setLoadingConversations: (loading) => set({ isLoadingConversations: loading }),
}));
