import { Link, useLocation, useNavigate } from "react-router-dom";
import { formatPercentage } from "../utils/formatters";
import MasteryBar from "../components/MasteryBar";

function resultTag(percentage) {
  if (percentage >= 80) return "Excellent work";
  if (percentage >= 60) return "Good progress";
  return "Keep practicing";
}

// The backend result is authoritative -- this page only ever displays
// `result` exactly as /quiz/submit returned it (see api/quizApi.js); it
// never recomputes a score or invents an adaptive recommendation.
export default function QuizResult() {
  const location = useLocation();
  const navigate = useNavigate();
  const result = location.state?.result;
  const subject = location.state?.subject;
  const topic = location.state?.topic;

  if (!result) {
    return (
      <div className="card">
        <p>No quiz result to display.</p>
        <Link to="/quiz" className="btn btn--primary">
          Start a quiz
        </Link>
      </div>
    );
  }

  const masteryReached = result.next_action === "revision";

  return (
    <div className="quiz-result">
      <div className="page-header">
        <h1>Quiz Complete</h1>
        <p className="page-subtitle">
          {subject} {topic ? `· ${topic}` : ""}
        </p>
      </div>

      <div className="quiz-result__score-card">
        <div className="quiz-result__score-value">{formatPercentage(result.percentage)}</div>
        <div className="quiz-result__score-tag">{resultTag(result.percentage)}</div>
        <div className="quiz-result__score-detail">
          {result.score} / {result.total_questions} correct
        </div>
      </div>

      <p className="quiz-result__feedback">{result.feedback}</p>

      {masteryReached && (
        <div className="quiz-result__banner quiz-result__banner--success">
          <p>Topic mastery threshold reached.</p>
        </div>
      )}

      {result.weak_topics?.length > 0 && (
        <section className="quiz-result__section">
          <div className="section-header">
            <h2>Areas to Review</h2>
          </div>
          <div className="quiz-result__weak-topics">
            {result.weak_topics.map((weak, i) => (
              <div key={i} className="mastery-row">
                <span className="mastery-row__label">{weak.topic}</span>
                <MasteryBar value={weak.mastery} />
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="quiz-result__actions">
        <Link to="/weak-topics" className="btn btn--secondary">
          Review Weak Topics
        </Link>
        <button type="button" className="btn btn--secondary" onClick={() => navigate("/quiz")}>
          Try Again
        </button>
        <Link to="/tutor" className="btn btn--primary">
          Ask Tutor
        </Link>
      </div>
    </div>
  );
}
