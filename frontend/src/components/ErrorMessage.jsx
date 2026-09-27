// Always shows a human-readable message (see utils/apiError.js) -- never a
// raw error object, stack trace, or backend implementation detail.
export default function ErrorMessage({ message, onRetry }) {
  if (!message) return null;
  return (
    <div className="error-state" role="alert">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn btn--small btn--secondary" onClick={onRetry}>
          Try Again
        </button>
      )}
    </div>
  );
}
