import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getSafeErrorMessage } from "../utils/apiError";
import ErrorMessage from "../components/ErrorMessage";
import AuthLayout from "../components/AuthLayout";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const registeredJustNow = location.state?.registered;

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      // Backend returns a generic "Invalid email or password" for both a
      // wrong password and an unknown email -- displayed as-is, never a
      // raw stack trace.
      setError(getSafeErrorMessage(err, "Invalid email or password."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="auth-card" onSubmit={handleSubmit}>
        <h2 className="auth-card__title">Welcome back</h2>
        <p className="auth-card__subtitle">Log in to continue your study plan.</p>

        {registeredJustNow && (
          <p className="auth-card__success">Registration successful — please log in.</p>
        )}

        <label className="field">
          <span className="field__label">Email</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>

        <label className="field">
          <span className="field__label">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        <ErrorMessage message={error} />

        <button type="submit" className="btn btn--primary btn--full" disabled={submitting}>
          {submitting ? "Logging in..." : "Log In"}
        </button>

        <p className="auth-card__footer">
          New here? <Link to="/register">Create an account</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
