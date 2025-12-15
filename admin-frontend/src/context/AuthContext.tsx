import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { api, authApi } from '../api/client';

interface AuthUser {
  user_id: string;
  display_name: string;
  is_admin: boolean;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isDemoMode: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  register: (username: string, password: string) => Promise<{ success: boolean; message: string }>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const TOKEN_KEY = 'cass_admin_token';
const USER_KEY = 'cass_admin_user';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isDemoMode, setIsDemoMode] = useState(false);

  // Check for demo mode and load saved auth on mount
  useEffect(() => {
    const initAuth = async () => {
      try {
        // Check if demo mode is enabled
        const statusResponse = await api.get('/admin/auth/status');
        const { demo_mode } = statusResponse.data;

        if (demo_mode) {
          // Demo mode - auto-authenticate as demo user
          setIsDemoMode(true);
          setUser({ user_id: 'demo', display_name: 'Demo User', is_admin: true });
          setToken('demo-token');
          setIsLoading(false);
          return;
        }

        // Normal mode - check for saved token
        const savedToken = localStorage.getItem(TOKEN_KEY);
        const savedUser = localStorage.getItem(USER_KEY);

        if (savedToken && savedUser) {
          setToken(savedToken);
          setUser(JSON.parse(savedUser));
          // Set default auth header
          api.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`;
          // Verify token is still valid
          await verifyToken(savedToken);
        } else {
          setIsLoading(false);
        }
      } catch {
        // If status check fails, continue with normal auth flow
        const savedToken = localStorage.getItem(TOKEN_KEY);
        const savedUser = localStorage.getItem(USER_KEY);

        if (savedToken && savedUser) {
          setToken(savedToken);
          setUser(JSON.parse(savedUser));
          api.defaults.headers.common['Authorization'] = `Bearer ${savedToken}`;
          await verifyToken(savedToken);
        } else {
          setIsLoading(false);
        }
      }
    };

    initAuth();
  }, []);

  const verifyToken = async (tokenToVerify: string) => {
    try {
      const response = await api.get('/admin/auth/verify', {
        headers: { Authorization: `Bearer ${tokenToVerify}` }
      });
      // Update user with is_admin from verify response
      const savedUser = localStorage.getItem(USER_KEY);
      if (savedUser) {
        const parsedUser = JSON.parse(savedUser);
        // Update with is_admin if returned from verify
        if (response.data.is_admin !== undefined) {
          parsedUser.is_admin = response.data.is_admin;
          setUser(parsedUser);
          localStorage.setItem(USER_KEY, JSON.stringify(parsedUser));
        }
      }
      setIsLoading(false);
    } catch {
      // Token invalid, clear auth
      logout();
    }
  };

  const login = async (username: string, password: string) => {
    const response = await api.post('/admin/auth/login', { username, password });
    const { token: newToken, user_id, display_name, is_admin } = response.data;

    const newUser = { user_id, display_name, is_admin: is_admin ?? false };

    setIsDemoMode(false);  // Clear demo mode on real login
    setToken(newToken);
    setUser(newUser);

    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(USER_KEY, JSON.stringify(newUser));

    api.defaults.headers.common['Authorization'] = `Bearer ${newToken}`;
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    delete api.defaults.headers.common['Authorization'];
    setIsLoading(false);
  };

  const register = async (username: string, password: string): Promise<{ success: boolean; message: string }> => {
    try {
      const response = await authApi.register({ username, password });
      return {
        success: response.data.success,
        message: response.data.message
      };
    } catch (error: unknown) {
      // Extract error message from axios error
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const message = axiosError.response?.data?.detail || 'Registration failed';
      return {
        success: false,
        message
      };
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        isDemoMode,
        isAdmin: user?.is_admin ?? false,
        login,
        logout,
        register
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
