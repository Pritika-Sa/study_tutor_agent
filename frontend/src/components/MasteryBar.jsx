import { formatPercentage } from "../utils/formatters";

// Plain CSS progress bar -- no charting library pulled in for one simple
// indicator (per project instructions). `threshold` draws the mastery-line
// marker so weak vs. mastered is visually obvious without a second widget.
export default function MasteryBar({ value, threshold }) {
  const clamped = Math.max(0, Math.min(100, value ?? 0));
  const isWeak = threshold != null && clamped < threshold;

  return (
    <div className="mastery-bar" role="img" aria-label={`Mastery ${formatPercentage(clamped)}`}>
      <div className="mastery-bar__track">
        <div
          className={`mastery-bar__fill${isWeak ? " mastery-bar__fill--weak" : ""}`}
          style={{ width: `${clamped}%` }}
        />
        {threshold != null && (
          <div className="mastery-bar__threshold" style={{ left: `${threshold}%` }} title={`Mastery threshold: ${threshold}%`} />
        )}
      </div>
      <span className="mastery-bar__value">{formatPercentage(clamped)}</span>
    </div>
  );
}
