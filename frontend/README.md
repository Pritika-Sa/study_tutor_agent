# Adaptive AI Study Tutor -- Frontend

React + React Router + Axios + vanilla CSS (no Tailwind, no Next.js). Talks to the FastAPI backend documented in the project root `README.md`.

## Setup

```bash
cd frontend
npm install
cp .env.example .env   # defaults to http://localhost:8000, matching the backend's default port
npm run dev
```

Open http://localhost:5173. The backend must be running (`uvicorn main:app --reload` from `backend/`) and must allow this origin via `CORS_ORIGINS` in `backend/.env` (defaults to `http://localhost:5173` already).

## Structure

```
src/
  api/        one file per backend resource (auth, tutor, quiz, progress) + the shared Axios instance
  context/    AuthContext (JWT session), TrackContext (selected track/subject, persisted to localStorage)
  components/ shared building blocks (Navbar, ProtectedRoute, QuizQuestion, CitationBadge, MasteryBar, ...)
  pages/      one per route
  styles/     plain CSS, one file per page area + global.css for the design system
  utils/      storage helpers, formatters, and the safe API-error extractor
```

## Security notes (matches the backend's own guarantees)

- The JWT is attached automatically by an Axios request interceptor (`api/axios.js`) -- no page ever sends it manually.
- A quiz's `correct_option` is never present anywhere in a response this app receives (see `backend/mcp_server/quiz_tools.py`), so there is no code path here that could display or store one.
- Quiz submission only ever sends `quiz_id` + the student's own selected answers (`api/quizApi.js`) -- never a score, percentage, or correctness flag.
- `student_id` is never sent by this app at all; every protected backend call authenticates via the JWT alone.

## Testing

```bash
npm run test
```

A small, focused suite (not exhaustive by design): `AuthContext` login/logout state, `ProtectedRoute` redirect behavior, `QuizQuestion` rendering (including that no correct-answer indicator ever appears), and the shared API-error-message extractor.

## Build

```bash
npm run build
```

Outputs to `dist/`.
