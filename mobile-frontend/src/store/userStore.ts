/**
 * User identity store with secure persistence
 */

import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';

const USER_ID_KEY = 'cass_user_id';
const DISPLAY_NAME_KEY = 'cass_display_name';

interface UserState {
  userId: string | null;
  displayName: string | null;
  isLoading: boolean;

  // Actions
  loadUserId: () => Promise<void>;
  setUser: (id: string, displayName: string) => Promise<void>;
  setUserId: (id: string) => Promise<void>;
  clearUserId: () => Promise<void>;
}

export const useUserStore = create<UserState>((set, get) => ({
  userId: null,
  displayName: null,
  isLoading: true,

  loadUserId: async () => {
    try {
      const [storedId, storedName] = await Promise.all([
        SecureStore.getItemAsync(USER_ID_KEY),
        SecureStore.getItemAsync(DISPLAY_NAME_KEY),
      ]);
      set({ userId: storedId, displayName: storedName, isLoading: false });
    } catch (error) {
      console.error('Failed to load user ID:', error);
      set({ isLoading: false });
    }
  },

  setUser: async (id: string, displayName: string) => {
    try {
      await Promise.all([
        SecureStore.setItemAsync(USER_ID_KEY, id),
        SecureStore.setItemAsync(DISPLAY_NAME_KEY, displayName),
      ]);
      set({ userId: id, displayName });
    } catch (error) {
      console.error('Failed to save user:', error);
    }
  },

  setUserId: async (id: string) => {
    try {
      await SecureStore.setItemAsync(USER_ID_KEY, id);
      set({ userId: id });
    } catch (error) {
      console.error('Failed to save user ID:', error);
    }
  },

  clearUserId: async () => {
    try {
      await Promise.all([
        SecureStore.deleteItemAsync(USER_ID_KEY),
        SecureStore.deleteItemAsync(DISPLAY_NAME_KEY),
      ]);
      set({ userId: null, displayName: null });
    } catch (error) {
      console.error('Failed to clear user ID:', error);
    }
  },
}));
