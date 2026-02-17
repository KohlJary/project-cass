/**
 * EmotionalBar - Horizontal bar visualization for emotional/state dimensions
 * Used by: Dashboard, StateTab, Thymos
 */

interface EmotionalBarProps {
  label: string;
  value: number;
  color: string;
}

export function EmotionalBar({ label, value, color }: EmotionalBarProps) {
  const percentage = Math.round(value * 100);
  return (
    <div className="emotional-bar">
      <div className="bar-label">{label}</div>
      <div className="bar-track">
        <div
          className="bar-fill"
          style={{ width: `${percentage}%`, backgroundColor: color }}
        />
      </div>
      <div className="bar-value">{percentage}%</div>
    </div>
  );
}
