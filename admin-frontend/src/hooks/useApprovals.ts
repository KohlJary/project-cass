/**
 * useApprovals - Hook for approval actions
 */
import { useQueryClient } from '@tanstack/react-query';
import { schedulerApi } from '../api/client';

export function useApprovals() {
  const queryClient = useQueryClient();

  const handleApprove = async (type: string, sourceId: string) => {
    try {
      await schedulerApi.approveItem(type, sourceId);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      console.error('Failed to approve:', err);
      throw err;
    }
  };

  const handleReject = async (type: string, sourceId: string, reason: string = '') => {
    try {
      await schedulerApi.rejectItem(type, sourceId, 'admin', reason);
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    } catch (err) {
      console.error('Failed to reject:', err);
      throw err;
    }
  };

  return {
    approve: handleApprove,
    reject: handleReject,
  };
}
