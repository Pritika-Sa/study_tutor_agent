export default function Loading({ label = "Loading..." }) {
  return (
    <div className="loading" role="status">
      <span className="loading__spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
