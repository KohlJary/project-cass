/**
 * ThymosPill - Compact emotional state indicator for the header
 *
 * Always visible so Kohl knows Cass's emotional state from any page.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { thymosApi } from '../api/client';
import type { ThymosState } from '../api/client';
import './ThymosPill.css';

function getValenceEmoji(valence: number): string {
  if (valence > 0.4) return '✦';  // Very positive
  if (valence > 0.2) return '◈';  // Positive
  if (valence < -0.4) return '◇'; // Very negative
  if (valence < -0.2) return '○'; // Negative
  return '◎';                     // Neutral
}

function getHealthColor(health: number): string {
  if (health >= 0.7) return 'excellent';
  if (health >= 0.5) return 'good';
  if (health >= 0.3) return 'warning';
  return 'critical';
}

function getValenceClass(valence: number): string {
  if (valence > 0.2) return 'positive';
  if (valence < -0.2) return 'negative';
  return 'neutral';
}

export function ThymosPill() {
  const { data: state, isLoading, isError } = useQuery<ThymosState>({
    queryKey: ['thymos-state'],
    queryFn: () => thymosApi.getState().then(r => r.data),
    refetchInterval: 15000, // Refresh every 15s
    retry: 2,
  });

  if (isLoading) {
    return (
      <div className="thymos-pill loading">
        <span className="pill-icon">◌</span>
        <span className="pill-text">...</span>
      </div>
    );
  }

  if (isError || !state) {
    return (
      <Link to="/mind" className="thymos-pill offline" title="Thymos unavailable">
        <span className="pill-icon">○</span>
        <span className="pill-text">--</span>
      </Link>
    );
  }

  const valenceClass = getValenceClass(state.valence);
  const healthClass = getHealthColor(state.overall_health);
  const emoji = getValenceEmoji(state.valence);

  // Check for urgent needs
  const hasUrgentNeeds = Object.values(state.needs).some(need => need.is_urgent);

  // Get dominant affect for tooltip
  const dominantAffect = state.felt_state?.dominant_affect?.replace(/_/g, ' ') || 'stable';

  const tooltipText = `${state.felt_state?.summary || `Valence: ${(state.valence * 100).toFixed(0)}%`}
Health: ${(state.overall_health * 100).toFixed(0)}%
Dominant: ${dominantAffect}`;

  return (
    <Link
      to="/mind"
      className={`thymos-pill ${valenceClass} ${hasUrgentNeeds ? 'urgent' : ''}`}
      title={tooltipText}
    >
      <span className={`pill-icon ${valenceClass}`}>{emoji}</span>
      <span className={`pill-health ${healthClass}`}>
        {(state.overall_health * 100).toFixed(0)}%
      </span>
      {hasUrgentNeeds && <span className="urgent-dot" />}
    </Link>
  );
}
