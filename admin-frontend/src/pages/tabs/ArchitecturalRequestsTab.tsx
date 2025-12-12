import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { sentienceApi } from '../../api/client';
import { useState } from 'react';

interface ArchitecturalRequest {
  id: string;
  problem: string;
  hypothesis: string;
  proposed_solution: string;
  priority: string;
  evidence?: string[];
  status: string;
  requested_at: string;
  created_at: string;
}

type StatusFilter = 'all' | 'pending' | 'approved' | 'declined';

export function ArchitecturalRequestsTab() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [expandedRequest, setExpandedRequest] = useState<string | null>(null);

  const { data: requestsData, isLoading, error } = useQuery({
    queryKey: ['architectural-requests', statusFilter],
    queryFn: () => sentienceApi.getArchitecturalRequests({
      status: statusFilter === 'all' ? undefined : statusFilter,
      limit: 50,
    }).then((r) => r.data),
    retry: false,
  });

  const approveMutation = useMutation({
    mutationFn: (requestId: string) => sentienceApi.approveRequest(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['architectural-requests'] });
    },
  });

  const declineMutation = useMutation({
    mutationFn: (requestId: string) => sentienceApi.declineRequest(requestId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['architectural-requests'] });
    },
  });

  const requests = requestsData?.requests || [];

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'P0': return '#f07178';
      case 'P1': return '#ffcb6b';
      case 'P2': return '#89ddff';
      case 'P3': return '#888';
      default: return '#888';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'pending': return '#ffcb6b';
      case 'approved': return '#c3e88d';
      case 'declined': return '#f07178';
      default: return '#888';
    }
  };

  const pendingCount = requests.filter((r: ArchitecturalRequest) => r.status === 'pending').length;

  if (isLoading) {
    return <div className="loading-state">Loading architectural requests...</div>;
  }

  if (error) {
    return <div className="error-state">Failed to load architectural requests</div>;
  }

  return (
    <div className="requests-tab">
      {/* Header with pending count */}
      <div className="requests-header">
        <h3>Architectural Change Requests</h3>
        {pendingCount > 0 && (
          <span className="pending-badge">{pendingCount} pending</span>
        )}
      </div>

      {/* Filter */}
      <div className="filter-bar">
        <button
          className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
          onClick={() => setStatusFilter('all')}
        >
          All ({requests.length})
        </button>
        <button
          className={`filter-btn pending ${statusFilter === 'pending' ? 'active' : ''}`}
          onClick={() => setStatusFilter('pending')}
        >
          Pending ({requests.filter((r: ArchitecturalRequest) => r.status === 'pending').length})
        </button>
        <button
          className={`filter-btn approved ${statusFilter === 'approved' ? 'active' : ''}`}
          onClick={() => setStatusFilter('approved')}
        >
          Approved ({requests.filter((r: ArchitecturalRequest) => r.status === 'approved').length})
        </button>
        <button
          className={`filter-btn declined ${statusFilter === 'declined' ? 'active' : ''}`}
          onClick={() => setStatusFilter('declined')}
        >
          Declined ({requests.filter((r: ArchitecturalRequest) => r.status === 'declined').length})
        </button>
      </div>

      {/* Requests List */}
      {requests.length === 0 ? (
        <div className="empty-state">
          <p>No architectural requests yet.</p>
          <p className="hint">Cass will submit requests for system changes she believes would help.</p>
        </div>
      ) : (
        <div className="requests-list">
          {requests.map((request: ArchitecturalRequest) => (
            <div
              key={request.id}
              className={`request-card ${request.status} ${expandedRequest === request.id ? 'expanded' : ''}`}
              onClick={() => setExpandedRequest(expandedRequest === request.id ? null : request.id)}
            >
              <div className="request-header">
                <span
                  className="priority-badge"
                  style={{ backgroundColor: `${getPriorityColor(request.priority)}20`, color: getPriorityColor(request.priority) }}
                >
                  {request.priority}
                </span>
                <span
                  className="status-badge"
                  style={{ backgroundColor: `${getStatusColor(request.status)}20`, color: getStatusColor(request.status) }}
                >
                  {request.status}
                </span>
                <span className="request-id">{request.id.slice(0, 8)}</span>
              </div>

              <div className="request-problem">
                <h4>Problem</h4>
                <p>{request.problem}</p>
              </div>

              {expandedRequest === request.id && (
                <>
                  <div className="request-hypothesis">
                    <h4>Hypothesis</h4>
                    <p>{request.hypothesis}</p>
                  </div>

                  <div className="request-solution">
                    <h4>Proposed Solution</h4>
                    <p>{request.proposed_solution}</p>
                  </div>

                  {request.evidence && request.evidence.length > 0 && (
                    <div className="request-evidence">
                      <h4>Evidence</h4>
                      <ul>
                        {request.evidence.map((ev, idx) => (
                          <li key={idx}>{ev}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </>
              )}

              <div className="request-footer">
                <span className="request-date">
                  {new Date(request.created_at).toLocaleString()}
                </span>

                {request.status === 'pending' && (
                  <div className="request-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="action-btn approve"
                      onClick={() => approveMutation.mutate(request.id)}
                      disabled={approveMutation.isPending}
                    >
                      Approve
                    </button>
                    <button
                      className="action-btn decline"
                      onClick={() => declineMutation.mutate(request.id)}
                      disabled={declineMutation.isPending}
                    >
                      Decline
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
