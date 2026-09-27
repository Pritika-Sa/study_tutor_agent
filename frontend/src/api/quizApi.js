import api from "./axios";

// Matches backend/api/routes_quiz.py exactly. /quiz/submit's `answers` maps
// question_id -> a letter ("A", "B", ...) matching the position of that
// question's `options` array -- the backend never sends letters attached to
// options, the frontend assigns them positionally when rendering (see
// components/QuizQuestion.jsx). The backend computes score/percentage; this
// layer never sends or trusts a client-side score.

export const startQuiz = ({ track, subject, topic, difficulty, numberOfQuestions }) =>
  api.post("/quiz/start", {
    track,
    subject,
    topic,
    difficulty,
    number_of_questions: numberOfQuestions,
  });

export const submitQuiz = ({ quizId, answers }) =>
  api.post("/quiz/submit", { quiz_id: quizId, answers });
