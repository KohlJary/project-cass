/**
 * Authentication store with secure token persistence
 */

import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { AuthTokens, AuthUser } from '../api/types';

const ACCESS_TOKEN_KEY = 'cass_access_token';
const REFRESH_TOKEN_KEY = 'cass_refresh_token';
const USER_DATA_KEY = 'cass_user_data';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  // Actions
  loadTokens: () => Promise<void>;
  setTokens: (tokens: AuthTokens) => Promise<void>;
  setUser: (user: AuthUser) => Promise<void>;
  setAuth: (tokens: AuthTokens, user: AuthUser) => Promise<void>;
  clearAuth: () => Promise<void>;
  getAccessToken: () => string | null;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  isLoading: true,
  isAuthenticated: false,

  loadTokens: async () => {
    try {
      const [accessToken, refreshToken, userData] = await Promise.all([
        SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
        SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
        SecureStore.getItemAsync(USER_DATA_KEY),
      ]);

      const user = userData ? JSON.parse(userData) : null;
      const isAuthenticated = !!(accessToken && refreshToken && user);

      set({
        accessToken,
        refreshToken,
        user,
        isAuthenticated,
        isLoading: false,
      });
    } catch (error) {
      console.error('Failed to load auth tokens:', error);
      set({ isLoading: false, isAuthenticated: false });
    }
  },

  setTokens: async (tokens: AuthTokens) => {
    try {
      // Save sequentially to avoid Android SecureStore issues
      await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, tokens.access_token);
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refresh_token);
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
    } catch (error) {
      console.error('Failed to save tokens:', error);
      // Still update state even if storage fails
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
      });
    }
  },

  setUser: async (user: AuthUser) => {
    try {
      await SecureStore.setItemAsync(USER_DATA_KEY, JSON.stringify(user));
      set({ user, isAuthenticated: true });
    } catch (error) {
      console.error('Failed to save user data:', error);
    }
  },

  setAuth: async (tokens: AuthTokens, user: AuthUser) => {
    try {
      // Save sequentially to avoid Android SecureStore issues
      await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, tokens.access_token);
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, tokens.refresh_token);
      await SecureStore.setItemAsync(USER_DATA_KEY, JSON.stringify(user));
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user,
        isAuthenticated: true,
      });
    } catch (error) {
      console.error('Failed to save auth data:', error);
      // Still update state even if storage fails
      set({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user,
        isAuthenticated: true,
      });
    }
  },

  clearAuth: async () => {
    try {
      await Promise.all([
        SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
        SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
        SecureStore.deleteItemAsync(USER_DATA_KEY),
      ]);
      set({
        accessToken: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
      });
    } catch (error) {
      console.error('Failed to clear auth data:', error);
    }
  },

  getAccessToken: () => {
    return get().accessToken;
  },
}));
