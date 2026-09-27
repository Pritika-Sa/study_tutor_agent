import api from "./axios";

// Matches backend/api/routes_auth.py exactly: register returns
// {message, user} with no token (so the frontend redirects to login, it
// does not auto-authenticate); login returns {access_token, token_type, user}.

export const registerUser = (name, email, password) =>
  api.post("/auth/register", { name, email, password });

export const loginUser = (email, password) => api.post("/auth/login", { email, password });

export const fetchCurrentUser = () => api.get("/auth/me");
