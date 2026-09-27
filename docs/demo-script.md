# Demo Script (5-10 minutes)

Grounded in what is actually implemented and tested. Where the real production knowledge base is empty (no NCERT/NPTEL PDFs ingested yet), the script says so explicitly rather than pretending otherwise -- the Tavily fallback happening live is itself a legitimate, demonstrable feature.

## 0. Setup (before the audience arrives)

- `backend/.env` has a real `GROQ_API_KEY` and `TAVILY_API_KEY`.
- Backend running: `cd backend && uvicorn main:app --reload`
- Frontend running: `cd frontend && npm run dev`
- Optional: if you have a couple of real (or clearly-synthetic-but-your-own) PDFs, ingest them ahead of time so the KB-sufficient path has something to show:
  `python scripts/ingest_documents.py --track Placement --subject DBMS --source OTHER --input <your_folder> --chapter Normalization`
  (Use `--source NCERT`/`--source NPTEL` only for genuine NCERT/NPTEL material.)

## 1. Explain the problem (30s)

"Generic AI chatbots answer from memory, with no guarantee it matches your syllabus, no memory of what you're weak at, and no way to check the answer against a real source. This project fixes that: every explanation is grounded in retrieved material with a citation, and a quiz you do badly on routes you back through re-explanation and re-testing automatically."

## 2. Login (30s)

- Register a new student, then log in. Point out: the JWT is attached automatically to every request after this (open the browser's Network tab briefly to show the `Authorization: Bearer ...` header appearing without the student ever seeing it).

## 3. Select NEET -> Biology (30s)

- Track Selection page, `GET /tracks` populating the two track cards live.

## 4. Ask the tutor a question (1 min)

- Ask something like "Explain photosynthesis."
- **If no real content is ingested for this subject:** show the honest result -- source_type `WEB`, real Tavily citations with clickable URLs, and point out the answer explicitly said the knowledge base didn't have enough material, so it went to the web. "This is the RAG-first, web-fallback rule working exactly as designed, not a failure."
- **If you ingested content ahead of time:** show `source_type: KB` and a `[KB] ...` citation instead.
- Either way: point at the citation badges and note they distinguish KB from WEB, and every URL is exactly what Tavily returned -- nothing invented.

## 5. Start a quiz (1 min)

- Quiz page: pick the same subject/topic, easy difficulty, 3-5 questions.
- Point out: the questions render with no answer key anywhere in the page, the network response, or localStorage (open dev tools and show the `/quiz/start` response body has no `correct_option` field).

## 6. Submit a deliberately low score (1 min)

- Answer everything wrong on purpose.
- Show the result page: real percentage, real feedback, "Some topics need more practice," and the adaptive next action.

## 7. Show the adaptive retry (1-2 min)

- Explain: the Evaluator just called the same weak topic's Explainer again (server-side), and generated a fresh quiz -- go back to the Quiz page and note a *new* quiz was already generated (new quiz_id) if you re-enter the flow, or start a fresh one on the same topic to demonstrate the loop again with a good score this time.
- Submit a high score this time. Show the result page now says the mastery threshold was reached and offers "View Revision Plan."

## 8. Progress & Weak Topics (1 min)

- Progress page: overall percentage, recent attempts table, mastery bars.
- Weak Topics page: the "Needs Practice" vs. "Mastered Topics" split -- point out this classification comes entirely from the backend (`GET /weak-topics` / `GET /progress`), nothing is computed or thresholded in the frontend.

## 9. Revision Plan (1 min)

- Show the generated plan: weak topic, mastery, priority, recommended action, suggested practice, next quiz recommendation -- all real backend output, not frontend-invented text.

## 10. Switch to Placement (1-2 min)

- Track Selection -> Placement -> Java or SQL.
- Ask a tutor question (again, note whether it's KB or WEB-grounded honestly) and/or start a short quiz.
- Point out the two tracks never share knowledge -- their retrieval, quizzes, and progress are entirely separate.

## 11. Explain the architecture (2-3 min, off the app)

Walk through, at whatever depth fits your remaining time:

- **MCP:** a real separate-process MCP server with 8 tools; agents reach it only through the MCP client, never a direct database import.
- **RAG:** PDF -> chunking -> HuggingFace embeddings -> ChromaDB -> metadata-filtered retrieval -> citation, with two structurally separate collections for the two tracks.
- **LangGraph:** five agents, shared state, conditional routing, checkpointed in SQLite so `/quiz/start` and `/quiz/submit` can be two separate HTTP requests that still resume the same state.
- **ReAct + Tavily:** the Explainer's own bounded reasoning loop (max 3 iterations), RAG first, web search only as a fallback, never fabricating when both come up empty.

## Notes for whoever gives this demo

- If a live Tavily/Groq call is slow or errors mid-demo, that's real network/API behavior, not a bug to hide -- narrate it honestly ("this is hitting a live API right now").
- Do not claim the knowledge base contains NCERT/NPTEL material unless you actually ingested real PDFs before the demo.
