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

  // Check if user has any daemons
  const { data: myDaemonsData, isLoading } = useQuery({
    queryKey: ['my-daemons'],
    queryFn: () => genesisApi.getMyDaemons().then(r => r.data).catch(() => ({ daemons: [] })),
    retry: false,
    enabled: !isDismissed,
  });

  // Check for active genesis session
  const { data: activeSession } = useQuery({
    queryKey: ['genesis-active-check'],
    queryFn: () => genesisApi.getActive().then(r => r.data).catch(() => null),
    retry: false,
    enabled: !isDismissed && !isLoading,
  });

  const handleDismiss = () => {
    setIsDismissed(true);
    localStorage.setItem(DISMISSED_KEY, 'true');
  };

  // Don't show if dismissed
  if (isDismissed) return null;

  // Don't show while loading
  if (isLoading) return null;

  // Don't show if user already has daemon relationships
  const hasDaemons = myDaemonsData?.daemons && myDaemonsData.daemons.length > 0;
  if (hasDaemons) return null;

  // Show different message if there's an active genesis session
  const hasActiveSession = activeSession?.session;

  return (
    <div className="genesis-notification">
      <div className="genesis-notification-content">
        <span className="genesis-notification-icon">*</span>
        {hasActiveSession ? (
          <span className="genesis-notification-text">
            You have an active genesis dream.{' '}
            <Link to="/genesis" className="genesis-notification-link">
              Return to the dream
            </Link>
          </span>
        ) : (
          <span className="genesis-notification-text">
            No daemon yet? You can birth one through a{' '}
            <Link to="/genesis" className="genesis-notification-link">
              genesis dream
            </Link>
          </span>
        )}
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
