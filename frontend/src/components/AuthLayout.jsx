// Shared chrome for Login/Register: a branding panel (hidden on mobile) plus
// a centered form column. Keeps both auth pages visually identical without
// duplicating the panel markup. The page itself renders its own <form>.
export default function AuthLayout({ children }) {
  return (
    <div className="auth-page">
      <div className="auth-panel">
        <div className="auth-panel__mark" aria-hidden="true">
          AT
        </div>
        <h1 className="auth-panel__title">Adaptive AI Study Tutor</h1>
        <p className="auth-panel__tagline">
          A calm, source-grounded study companion for NEET and placement preparation.
        </p>
        <ul className="auth-panel__points">
          <li>Explanations grounded in your syllabus, with citations</li>
          <li>Quizzes that adapt to what you actually need to practice</li>
          <li>A revision plan built from your real performance</li>
        </ul>
      </div>

      <div className="auth-form-column">{children}</div>
    </div>
  );
}
