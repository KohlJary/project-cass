/**
 * SchedulePanel - Autonomous Schedule Display Panel
 *
 * Left panel of the 3-column dashboard showing:
 * - Phase timeline with work units
 * - Selected work unit details
 * - Daily summary stats
 */

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchAutonomousSchedule } from '../../api/graphql';
import type { WorkUnit, PhaseQueue } from '../../api/graphql';
import './SchedulePanel.css';

// Phase display configuration
const PHASE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  morning: { label: 'Morning', color: '#FF9800', icon: '🌅' },
  afternoon: { label: 'Afternoon', color: '#4CAF50', icon: '☀️' },
  evening: { label: 'Evening', color: '#9C27B0', icon: '🌆' },
  night: { label: 'Night', color: '#2196F3', icon: '🌙' },
};

// Work status to visual style mapping
const STATUS_STYLES: Record<string, { symbol: string; className: string }> = {
  queued: { symbol: '○', className: 'status-queued' },
  planned: { symbol: '○', className: 'status-queued' },
  running: { symbol: '◐', className: 'status-running' },
  completed: { symbol: '●', className: 'status-completed' },
  failed: { symbol: '✕', className: 'status-failed' },
};

interface SchedulePanelProps {
  className?: string;
}

export const SchedulePanel: React.FC<SchedulePanelProps> = ({ className }) => {
  const [selectedWorkUnit, setSelectedWorkUnit] = useState<WorkUnit | null>(null);
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ['autonomousSchedule'],
    queryFn: fetchAutonomousSchedule,
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const schedule = data?.autonomousSchedule;

  if (isLoading) {
    return (
      <div className={`schedule-panel ${className || ''}`}>
        <div className="schedule-panel-loading">Loading schedule...</div>
      </div>
    );
  }

  if (error || !schedule) {
    return (
      <div className={`schedule-panel ${className || ''}`}>
        <div className="schedule-panel-error">
          {error ? 'Failed to load schedule' : 'Schedule unavailable'}
        </div>
      </div>
    );
  }

  const handleWorkUnitClick = (workUnit: WorkUnit, phase: string) => {
    if (selectedWorkUnit?.id === workUnit.id) {
      setSelectedWorkUnit(null);
      setSelectedPhase(null);
    } else {
      setSelectedWorkUnit(workUnit);
      setSelectedPhase(phase);
    }
  };

  // Get stats for display
  const stats = schedule.dailySummary;
  const currentPhase = schedule.phaseQueues.find(q => q.isCurrent)?.phase || 'afternoon';

  return (
    <div className={`schedule-panel ${className || ''}`}>
      {/* Header */}
      <div className="schedule-panel-header">
        <h3>Autonomous Schedule</h3>
        {schedule.isWorking && schedule.currentWork && (
          <span className="working-indicator">
            ◐ Working: {schedule.currentWork.workUnit.name}
          </span>
        )}
        {!schedule.enabled && (
          <span className="disabled-indicator">Disabled</span>
        )}
      </div>

      {/* Top Section: Phase Timeline + Work Detail */}
      <div className="schedule-top-section">
        {/* Phase Timeline */}
        <div className="phase-timeline">
          {schedule.phaseQueues.map((phaseQueue) => (
            <PhaseBlock
              key={phaseQueue.phase}
              phaseQueue={phaseQueue}
              config={PHASE_CONFIG[phaseQueue.phase]}
              selectedWorkUnitId={selectedWorkUnit?.id}
              onWorkUnitClick={handleWorkUnitClick}
            />
          ))}
        </div>

        {/* Work Unit Detail (when selected) */}
        {selectedWorkUnit && (
          <div className="work-unit-detail">
            <WorkUnitDetail
              workUnit={selectedWorkUnit}
              phase={selectedPhase || ''}
              onClose={() => {
                setSelectedWorkUnit(null);
                setSelectedPhase(null);
              }}
            />
          </div>
        )}
      </div>

      {/* Bottom Section: Stats or Summary */}
      {!selectedWorkUnit && (
        <div className="schedule-bottom-section">
          <div className="day-stats">
            <div className="stat-item">
              <span className="stat-value">{schedule.todaysPlan.totalWorkUnits}</span>
              <span className="stat-label">Planned</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{stats.total_work_units}</span>
              <span className="stat-label">Completed</span>
            </div>
            <div className="stat-item">
              <span className="stat-value">{currentPhase}</span>
              <span className="stat-label">Phase</span>
            </div>
          </div>
          {schedule.todaysPlan.plannedAt && (
            <div className="plan-timestamp">
              Planned at {new Date(schedule.todaysPlan.plannedAt).toLocaleTimeString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// Phase Block Component
interface PhaseBlockProps {
  phaseQueue: PhaseQueue;
  config: { label: string; color: string; icon: string };
  selectedWorkUnitId?: string;
  onWorkUnitClick: (workUnit: WorkUnit, phase: string) => void;
}

const PhaseBlock: React.FC<PhaseBlockProps> = ({
  phaseQueue,
  config,
  selectedWorkUnitId,
  onWorkUnitClick,
}) => {
  const statusStyle = phaseQueue.isCurrent ? { borderLeftColor: 'var(--accent)' } : {};

  return (
    <div
      className={`phase-block ${phaseQueue.isCurrent ? 'phase-current' : ''}`}
      style={statusStyle}
    >
      <div className="phase-header" style={{ color: config.color }}>
        <span className="phase-icon">{config.icon}</span>
        <span className="phase-label">{config.label}</span>
        {phaseQueue.queueCount > 0 && (
          <span className="phase-count">{phaseQueue.queueCount}</span>
        )}
      </div>
      <div className="phase-work-list">
        {phaseQueue.workUnits.map((queuedUnit) => (
          <WorkUnitCard
            key={queuedUnit.workUnit.id}
            workUnit={queuedUnit.workUnit}
            priority={queuedUnit.priority}
            isSelected={selectedWorkUnitId === queuedUnit.workUnit.id}
            onClick={() => onWorkUnitClick(queuedUnit.workUnit, phaseQueue.phase)}
          />
        ))}
        {phaseQueue.workUnits.length === 0 && (
          <div className="phase-empty">No work queued</div>
        )}
      </div>
    </div>
  );
};

// Work Unit Card Component
interface WorkUnitCardProps {
  workUnit: WorkUnit;
  priority: number;
  isSelected: boolean;
  onClick: () => void;
}

const WorkUnitCard: React.FC<WorkUnitCardProps> = ({
  workUnit,
  isSelected,
  onClick,
}) => {
  const statusConfig = STATUS_STYLES[workUnit.status] || STATUS_STYLES.queued;

  return (
    <div
      className={`work-unit-card ${isSelected ? 'selected' : ''} ${statusConfig.className}`}
      onClick={onClick}
    >
      <span className="work-status-icon">{statusConfig.symbol}</span>
      <div className="work-unit-info">
        <span className="work-unit-name">{workUnit.name}</span>
        {workUnit.focus && (
          <span className="work-unit-focus">{workUnit.focus}</span>
        )}
      </div>
      <span className="work-unit-duration">{workUnit.estimatedDurationMinutes}m</span>
    </div>
  );
};

// Work Unit Detail Component
interface WorkUnitDetailProps {
  workUnit: WorkUnit;
  phase: string;
  onClose: () => void;
}

const WorkUnitDetail: React.FC<WorkUnitDetailProps> = ({ workUnit, phase, onClose }) => {
  return (
    <div className="work-detail-content">
      <div className="work-detail-header">
        <h4>{workUnit.name}</h4>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      <div className="work-detail-body">
        {workUnit.category && (
          <div className="detail-row">
            <span className="detail-label">Category</span>
            <span className="detail-value">{workUnit.category}</span>
          </div>
        )}
        <div className="detail-row">
          <span className="detail-label">Phase</span>
          <span className="detail-value">{phase}</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Duration</span>
          <span className="detail-value">{workUnit.estimatedDurationMinutes} min</span>
        </div>
        <div className="detail-row">
          <span className="detail-label">Status</span>
          <span className="detail-value">{workUnit.status}</span>
        </div>
        {workUnit.focus && (
          <div className="detail-section">
            <span className="detail-label">Focus</span>
            <p className="detail-text">{workUnit.focus}</p>
          </div>
        )}
        {workUnit.motivation && (
          <div className="detail-section">
            <span className="detail-label">Motivation</span>
            <p className="detail-text">{workUnit.motivation}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SchedulePanel;
