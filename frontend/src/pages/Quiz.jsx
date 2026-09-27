import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTrack } from "../context/TrackContext";
import { startQuiz, submitQuiz } from "../api/quizApi";
import { getSafeErrorMessage } from "../utils/apiError";
import QuizQuestion from "../components/QuizQuestion";
import ErrorMessage from "../components/ErrorMessage";
import Loading from "../components/Loading";

const DIFFICULTIES = ["easy", "medium", "hard"];

export default function Quiz() {
  const { track, subject } = useTrack();
  const navigate = useNavigate();

  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("medium");
  const [numberOfQuestions, setNumberOfQuestions] = useState(5);

  const [quiz, setQuiz] = useState(null); // { quiz_id, topic, questions }
  const [answers, setAnswers] = useState({}); // question_id -> letter
  const [currentIndex, setCurrentIndex] = useState(0);
  const [confirming, setConfirming] = useState(false);

  const [starting, setStarting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleStart(event) {
    event.preventDefault();
    if (!topic.trim()) return;

    setError(null);
    setStarting(true);
    try {
      const response = await startQuiz({ track, subject, topic, difficulty, numberOfQuestions });
      setQuiz(response.data);
      setAnswers({});
      setCurrentIndex(0);
      setConfirming(false);
    } catch (err) {
      setError(getSafeErrorMessage(err, "Unable to start a quiz right now. Please try again."));
    } finally {
      setStarting(false);
    }
  }

  function handleSelect(questionId, letter) {
    setAnswers((prev) => ({ ...prev, [questionId]: letter }));
  }

  const answeredCount = Object.keys(answers).length;
  const allAnswered = quiz && answeredCount === quiz.questions.length;
  const isLastQuestion = quiz && currentIndex === quiz.questions.length - 1;

  async function handleConfirmSubmit() {
    setError(null);
    setSubmitting(true);
    try {
      // Only quiz_id + the student's own answers are ever sent -- never a
      // score, never a percentage, never a "correct" flag (see api/quizApi.js).
      const response = await submitQuiz({ quizId: quiz.quiz_id, answers });
      navigate("/quiz/result", { state: { result: response.data, track, subject, topic: quiz.topic } });
    } catch (err) {
      setError(getSafeErrorMessage(err, "Unable to submit your quiz right now. Please try again."));
      setConfirming(false);
    } finally {
      setSubmitting(false);
    }
  }

  if (!track || !subject) {
    return (
      <div className="card">
        <p>Select a track and subject before starting a quiz.</p>
      </div>
    );
  }

  if (!quiz) {
    return (
      <div className="quiz-page">
        <div className="page-header">
          <h1>Start a Quiz</h1>
          <p className="page-subtitle">
            {track} &middot; {subject}
          </p>
        </div>

        <form className="quiz-setup-form" onSubmit={handleStart}>
          <label className="field">
            <span className="field__label">Topic</span>
            <input
              type="text"
              required
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. Normalization"
            />
          </label>

          <label className="field">
            <span className="field__label">Difficulty</span>
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              {DIFFICULTIES.map((d) => (
                <option key={d} value={d}>
                  {d[0].toUpperCase() + d.slice(1)}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span className="field__label">Number of questions</span>
            <input
              type="number"
              min={1}
              max={20}
              value={numberOfQuestions}
              onChange={(e) => setNumberOfQuestions(Number(e.target.value))}
            />
          </label>

          <ErrorMessage message={error} onRetry={topic ? handleStart : undefined} />

          <button type="submit" className="btn btn--primary btn--full" disabled={starting}>
            {starting ? "Generating quiz..." : "Start Quiz"}
          </button>
        </form>
      </div>
    );
  }

  const currentQuestion = quiz.questions[currentIndex];

  return (
    <div className="quiz-page">
      <div className="quiz-page__header">
        <div>
          <h1>{quiz.subject} Quiz</h1>
          <p className="page-subtitle quiz-page__meta">Topic: {quiz.topic}</p>
        </div>
        <div className="quiz-progress">
          <span className="quiz-progress__count">
            Question {currentIndex + 1} of {quiz.questions.length}
          </span>
          <div className="quiz-progress__track">
            <div
              className="quiz-progress__fill"
              style={{ width: `${((currentIndex + 1) / quiz.questions.length) * 100}%` }}
            />
          </div>
        </div>
      </div>

      <QuizQuestion
        key={currentQuestion.question_id}
        question={currentQuestion}
        index={currentIndex}
        selectedAnswer={answers[currentQuestion.question_id]}
        onSelect={handleSelect}
      />

      <ErrorMessage message={error} />

      {!confirming ? (
        <div className="quiz-nav">
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
            disabled={currentIndex === 0}
          >
            ← Previous
          </button>
          <span className="quiz-nav__answered">{answeredCount}/{quiz.questions.length} answered</span>
          {isLastQuestion ? (
            <button type="button" className="btn btn--primary" onClick={() => setConfirming(true)}>
              Review &amp; Submit
            </button>
          ) : (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setCurrentIndex((i) => Math.min(quiz.questions.length - 1, i + 1))}
            >
              Next →
            </button>
          )}
        </div>
      ) : (
        <div className="quiz-confirm">
          <p>
            {allAnswered
              ? "Submit your quiz? You cannot change your answers afterwards."
              : `You've only answered ${answeredCount} of ${quiz.questions.length} questions. Submit anyway?`}
          </p>
          <div className="quiz-confirm__actions">
            <button type="button" className="btn btn--primary" onClick={handleConfirmSubmit} disabled={submitting}>
              {submitting ? "Submitting..." : "Confirm Submit"}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => setConfirming(false)}
              disabled={submitting}
            >
              Cancel
            </button>
          </div>
          {submitting && <Loading label="Grading your quiz..." />}
        </div>
      )}
    </div>
  );
}
