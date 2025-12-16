import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { genesisApi } from '../api/client';
import './GenesisNotification.css';

const DISMISSED_KEY = 'genesis_notification_dismissed';

export function GenesisNotification() {
  const [isDismissed, setIsDismissed] = useState(() => {
    return localStorage.getItem(DISMISSED_KEY) === 'true';
  });

  // Check for active genesis session
  const { data: activeSession, isLoading } = useQuery({
    queryKey: ['genesis-active-check'],
    queryFn: () => genesisApi.getActive().then(r => r.data).catch(() => null),
    retry: false,
    enabled: !isDismissed,
  });

  const handleDismiss = () => {
    setIsDismissed(true);
    localStorage.setItem(DISMISSED_KEY, 'true');
  };

  // Don't show if dismissed or loading
  if (isDismissed || isLoading) return null;

  // Only show if there's an active genesis session to return to
  const hasActiveSession = activeSession?.session;
  if (!hasActiveSession) return null;

  return (
    <div className="genesis-notification">
      <div className="genesis-notification-content">
        <span className="genesis-notification-icon">*</span>
        <span className="genesis-notification-text">
          You have an active genesis dream.{' '}
          <Link to="/genesis" className="genesis-notification-link">
            Return to the dream
          </Link>
        </span>
      </div>
      <button
        className="genesis-notification-dismiss"
        onClick={handleDismiss}
        title="Dismiss"
        aria-label="Dismiss notification"
      >
        x
      </button>
    </div>
  );
}
