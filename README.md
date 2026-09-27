# Adaptive AI Study Tutor

## At a Glance

This project is a full-stack adaptive learning app for NEET and placement preparation. Students sign in, choose a track/subject, ask learning questions, take quizzes, and get guided revision based on real weak spots.

### Overall flow

1. User signs up or logs in.
2. They choose a study track such as NEET or Placement and a subject.
3. The tutor answers questions using source-grounded retrieval from a local knowledge base.
4. The quiz engine creates questions for the selected topic.
5. Answers are checked server-side, not on the client.
6. Weak topics are identified from quiz performance.
7. The system explains the weak areas again and creates a revision plan.
8. The frontend shows progress, weak topics, and revision results in a simple dashboard.

### High-level architecture

Frontend (React + Vite) -> FastAPI backend -> LangGraph agents -> RAG + MCP tools -> SQLite + ChromaDB

- Frontend: login, dashboard, tutor UI, quiz flow, revision views
- Backend: auth, APIs, orchestration, grading, state management
- Agents: planner, explainer, quiz master, evaluator, revision planner
- Data layer: SQLite for app data + ChromaDB for document retrieval

## Extra Resources with Tavily

The app does not rely only on the local study materials. When the local knowledge base does not have enough relevant content for a question, the system can use Tavily to search for additional trustworthy learning resources on the web.

This is useful when:

- the student asks a question outside the current ingested material
- a topic is underrepresented in the local documents
- the system needs a second explanation source before answering or creating a revision path

### How it works

1. The explainer agent first tries the local RAG retrieval.
2. If the answer is weak or the material is insufficient, it performs a Tavily web search.
3. The results are used to provide additional context and source-backed explanations.
4. The app keeps the answer grounded by clearly distinguishing between local knowledge-base results and external web results.

### Environment setup

Add your Tavily key in `backend/.env`:

```bash
TAVILY_API_KEY=your_tavily_key_here
```

This allows the app to fetch supplemental resources without replacing the main RAG pipeline.

## Quick Start

### 1) Clone
```bash
git clone <YOUR_GITHUB_REPO_URL>
cd adaptive-study-tutor
```

### 2) Backend setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Then fill in the required keys in `backend/.env`:

- `JWT_SECRET_KEY`
- `GROQ_API_KEY`
- `TAVILY_API_KEY`
- optional tuning values already defined in `.env.example`

### 3) Frontend setup

```bash
cd frontend
npm install
copy .env.example .env
```

The frontend env file should contain:

```bash
VITE_API_BASE_URL=http://localhost:8000
```
### 3) load study material

If the knowledge base is empty, ingest documents before testing the tutor/quiz flow:

```bash
python scripts/download_materials.py --all --ingest
```

### 4) Run the app

Terminal 1:

```bash
cd backend
.venv\Scripts\activate
uvicorn main:app --reload
```

Open the API docs at http://127.0.0.1:8000/docs

Terminal 2:

```bash
cd frontend
npm run dev
```

Open the app at http://localhost:5173



This project expects the backend to be running before the frontend is used, and both need the appropriate `.env` values configured.
