export default function ProgressCard({ label, value, sublabel }) {
  return (
    <div className="progress-card">
      <div className="progress-card__value">{value}</div>
      <div className="progress-card__label">{label}</div>
      {sublabel && <div className="progress-card__sublabel">{sublabel}</div>}
    </div>
  );
}
