// Compact skeleton placeholder shown while a section's data is loading --
// used instead of a bare "Loading..." string for content-heavy sections
// (progress cards, quiz setup, revision plan).
export default function SkeletonCard({ lines = 2, count = 1 }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div className="skeleton-card" key={i} aria-hidden="true">
          {Array.from({ length: lines }).map((_, j) => (
            <div className="skeleton skeleton-line" key={j} />
          ))}
        </div>
      ))}
    </>
  );
}
