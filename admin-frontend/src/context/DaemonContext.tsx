import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';

export interface Daemon {
  id: string;
  label: string;           // Display label (e.g., "cass")
  name: string;            // Entity name for prompts (e.g., "Cass")
  created_at: string;
  kernel_version: string | null;
  status: string;
}

interface DaemonContextType {
  currentDaemon: Daemon | null;
  availableDaemons: Daemon[];
  isLoading: boolean;
  error: string | null;
  setDaemon: (daemonId: string) => void;
  refreshDaemons: () => Promise<void>;
}

const DaemonContext = createContext<DaemonContextType | null>(null);

const DAEMON_KEY = 'cass_admin_daemon';

export function DaemonProvider({ children }: { children: ReactNode }) {
  const [currentDaemon, setCurrentDaemon] = useState<Daemon | null>(null);
  const [availableDaemons, setAvailableDaemons] = useState<Daemon[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const fetchDaemons = useCallback(async () => {
    try {
      setError(null);
      const response = await api.get('/admin/daemons');
      const daemons: Daemon[] = response.data.daemons;
      setAvailableDaemons(daemons);

      // Restore saved daemon or use first available
      const savedDaemonId = localStorage.getItem(DAEMON_KEY);
      const savedDaemon = daemons.find((d) => d.id === savedDaemonId);

      if (savedDaemon) {
        setCurrentDaemon(savedDaemon);
      } else if (daemons.length > 0) {
        // Default to first daemon (usually "cass")
        setCurrentDaemon(daemons[0]);
        localStorage.setItem(DAEMON_KEY, daemons[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch daemons:', err);
      setError('Failed to load daemons');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Load daemons on mount
  useEffect(() => {
    fetchDaemons();
  }, [fetchDaemons]);

  const setDaemon = useCallback(
    (daemonId: string) => {
      const daemon = availableDaemons.find((d) => d.id === daemonId);
      if (daemon) {
        setCurrentDaemon(daemon);
        localStorage.setItem(DAEMON_KEY, daemonId);
        // Invalidate all queries to refetch with new daemon
        queryClient.invalidateQueries();
      }
    },
    [availableDaemons, queryClient]
  );

  const refreshDaemons = useCallback(async () => {
    setIsLoading(true);
    await fetchDaemons();
  }, [fetchDaemons]);

  return (
    <DaemonContext.Provider
      value={{
        currentDaemon,
        availableDaemons,
        isLoading,
        error,
        setDaemon,
        refreshDaemons,
      }}
    >
      {children}
    </DaemonContext.Provider>
  );
}

export function useDaemon() {
  const context = useContext(DaemonContext);
  if (!context) {
    throw new Error('useDaemon must be used within a DaemonProvider');
  }
  return context;
}

// Export the daemon ID for use in API client interceptor
export function getStoredDaemonId(): string | null {
  return localStorage.getItem(DAEMON_KEY);
}
