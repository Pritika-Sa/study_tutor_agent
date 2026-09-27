import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { fetchCurrentUser, loginUser, registerUser } from "../api/authApi";
import { getItem, removeItem, setItem } from "../utils/storage";
import { TOKEN_KEY } from "../api/axios";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  // On startup: restore the token, call /auth/me to validate the session,
  // and populate the user -- never trust a stored token without re-checking
  // it against the backend (it could be expired or revoked).
  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      const existingToken = getItem(TOKEN_KEY);
      if (!existingToken) {
        setLoading(false);
        return;
      }
      try {
        const response = await fetchCurrentUser();
        if (!cancelled) {
          setUser(response.data);
          setToken(existingToken);
        }
      } catch {
        removeItem(TOKEN_KEY);
        if (!cancelled) {
          setUser(null);
          setToken(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const response = await loginUser(email, password);
    setItem(TOKEN_KEY, response.data.access_token);
    setToken(response.data.access_token);
    setUser(response.data.user);
    return response.data.user;
  }, []);

  const register = useCallback(async (name, email, password) => {
    // Backend register does NOT return a token (see api/authApi.js) -- the
    // caller (pages/Register.jsx) redirects to /login afterwards.
    const response = await registerUser(name, email, password);
    return response.data;
  }, []);

  const logout = useCallback(() => {
    removeItem(TOKEN_KEY);
    setUser(null);
    setToken(null);
  }, []);

  const value = {
    user,
    token,
    loading,
    isAuthenticated: Boolean(token && user),
    login,
    register,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
