import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getSafeErrorMessage } from "../utils/apiError";
import ErrorMessage from "../components/ErrorMessage";
import AuthLayout from "../components/AuthLayout";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // Backend's /auth/register returns {message, user} with no token (see
      // api/authApi.js) -- redirect to login rather than pretending the
      // user is already authenticated.
      await register(name, email, password);
      navigate("/login", { state: { registered: true } });
    } catch (err) {
      setError(getSafeErrorMessage(err, "Registration failed. Please check your details and try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="auth-card" onSubmit={handleSubmit}>
        <h2 className="auth-card__title">Create your account</h2>
        <p className="auth-card__subtitle">Start your adaptive NEET or Placement prep.</p>

        <label className="field">
          <span className="field__label">Name</span>
          <input
            type="text"
            required
            minLength={1}
            maxLength={100}
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>

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
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className="field__hint">At least 8 characters.</span>
        </label>

        <ErrorMessage message={error} />

        <button type="submit" className="btn btn--primary btn--full" disabled={submitting}>
          {submitting ? "Creating account..." : "Register"}
        </button>

        <p className="auth-card__footer">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
