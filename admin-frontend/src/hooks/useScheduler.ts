/**
 * useScheduler - Hook for scheduler status polling
 */
import { useQuery } from '@tanstack/react-query';
import { schedulerApi } from '../api/client';
import type { SchedulerStatus } from '../api/client';

interface UseSchedulerOptions {
  refetchInterval?: number;
  enabled?: boolean;
}

export function useScheduler(options: UseSchedulerOptions = {}) {
  const { refetchInterval = 10000, enabled = true } = options;

  return useQuery<SchedulerStatus>({
    queryKey: ['scheduler-status'],
    queryFn: async () => {
      const response = await schedulerApi.getStatus();
      return response.data;
    },
    refetchInterval,
    enabled,
  });
}
