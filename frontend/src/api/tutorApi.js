import api from "./axios";

// Matches backend/api/routes_tutor.py's AskRequest exactly: track, subject,
// query are required; topic is optional. There is no "difficulty" field on
// this endpoint (only /quiz/start has one) -- verified against the actual
// backend schema before writing this, not assumed.
export const askTutor = ({ track, subject, query, topic }) =>
  api.post("/tutor/ask", { track, subject, query, topic: topic || null });
