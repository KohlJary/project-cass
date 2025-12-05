/**
 * Authentication hook for login, register, logout, and token refresh
 */

import { useCallback, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { apiClient, setAuthTokenGetter, setTokenRefreshHandler } from '../api/client';
import { RegisterRequest, LoginRequest, UserProfileData } from '../api/types';

export function useAuth() {
  const {
    accessToken,
    refreshToken,
    user,
    isLoading,
    isAuthenticated,
    loadTokens,
    setAuth,
    setTokens,
    clearAuth,
    getAccessToken,
  } = useAuthStore();

  // Set up token getter for API client
  useEffect(() => {
    setAuthTokenGetter(getAccessToken);
  }, [getAccessToken]);

  // Set up token refresh handler
  useEffect(() => {
    const handleRefresh = async (): Promise<boolean> => {
      const currentRefreshToken = useAuthStore.getState().refreshToken;
      if (!currentRefreshToken) {
        await clearAuth();
        return false;
      }

      try {
        const tokens = await apiClient.refreshToken(currentRefreshToken);
        await setTokens(tokens);
        return true;
      } catch (error) {
        console.error('Token refresh failed:', error);
        await clearAuth();
        return false;
      }
    };

    setTokenRefreshHandler(handleRefresh);
  }, [setTokens, clearAuth]);

  // Load tokens on mount
  useEffect(() => {
    loadTokens();
  }, [loadTokens]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiClient.login({ email, password });
    // Save tokens first so getMe() can use them
    await setTokens({ access_token: response.access_token, refresh_token: response.refresh_token });
    const userInfo = await apiClient.getMe();
    await setAuth(
      { access_token: response.access_token, refresh_token: response.refresh_token },
      userInfo
    );
    return { user: userInfo, isNewUser: false };
  }, [setAuth, setTokens]);

  const register = useCallback(async (data: RegisterRequest & { profile?: UserProfileData }) => {
    // Register the user
    const response = await apiClient.register({
      email: data.email,
      password: data.password,
      display_name: data.display_name,
    });

    // Save tokens first so subsequent calls can use them
    await setTokens({ access_token: response.access_token, refresh_token: response.refresh_token });

    // Get user info
    const userInfo = await apiClient.getMe();

    // If profile data was provided, create the user profile
    if (data.profile) {
      await apiClient.createUser(data.profile);
    }

    await setAuth(
      { access_token: response.access_token, refresh_token: response.refresh_token },
      userInfo
    );

    return { user: userInfo, isNewUser: true };
  }, [setAuth, setTokens]);

  const logout = useCallback(async () => {
    await clearAuth();
  }, [clearAuth]);

  return {
    user,
    isLoading,
    isAuthenticated,
    login,
    register,
    logout,
  };
}
