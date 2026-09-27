export function formatPercentage(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return `${Math.round(value * 10) / 10}%`;
}

export function formatDate(isoString) {
  if (!isoString) return "--";
  try {
    return new Date(isoString).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

// Positionally assigns letters to a question's options -- the backend
// never sends letters attached to options (see api/quizApi.js's note); the
// frontend is the single place this mapping happens.
export function optionLetter(index) {
  return String.fromCharCode(65 + index); // 0 -> "A", 1 -> "B", ...
}
