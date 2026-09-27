import axios from "axios";

// Centralized Axios instance -- every API call in this app goes through
// this one client, so the base URL and auth header are configured exactly
// once, not re-hardcoded on every page.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE_URL });

const TOKEN_KEY = "auth_token";

// Attach the JWT automatically -- no page ever sends it manually.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On a 401 (expired/invalid token), clear the stored session and send the
// user back to login -- a full reload so every context re-reads the now-
// empty localStorage instead of drifting out of sync with it.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem("auth_user");
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;
export { TOKEN_KEY };
