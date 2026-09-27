// Extracts a safe, user-facing message from an Axios error. FastAPI's
// HTTPException responses are always {"detail": "..."} -- this project's
// backend never returns a raw traceback, SQL error, or internal file path
// in a response body, but this function is deliberately defensive anyway:
// it only ever surfaces `detail` (a string) or a generic fallback, never
// the raw error object, a stack, or anything from error.request/error.config.
export function getSafeErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (!error?.response) {
    return "Unable to reach the server. Please check your connection and try again.";
  }
  return fallback;
}
