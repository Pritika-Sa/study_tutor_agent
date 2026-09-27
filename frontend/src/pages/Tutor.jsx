import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTrack } from "../context/TrackContext";
import { askTutor } from "../api/tutorApi";
import { getSafeErrorMessage } from "../utils/apiError";
import CitationBadge from "../components/CitationBadge";
import ErrorMessage from "../components/ErrorMessage";
import EmptyState from "../components/EmptyState";
import SupplementaryResources from "../components/SupplementaryResources";

const SOURCE_NOTES = {
  "KB+WEB": "Knowledge base coverage was limited, so a supplementary web search was also used.",
  WEB: "No sufficient knowledge-base match was found — this answer relies on a supplementary web search.",
  NONE: "Source coverage was limited for this question.",
};

export default function Tutor() {
  const { track, subject } = useTrack();

  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [exchanges, setExchanges] = useState([]); // {question, answer, citations, webCitations, sourceType}
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!query.trim()) return;

    setError(null);
    setAsking(true);
    const askedQuery = query;
    try {
      const response = await askTutor({ track, subject, query: askedQuery, topic: topic || undefined });
      setExchanges((prev) => [
        ...prev,
        {
          question: askedQuery,
          answer: response.data.answer,
          topic: response.data.topic,
          citations: response.data.citations || [],
          webCitations: response.data.web_citations || [],
          sourceType: response.data.source_type,
          supplementaryResources: response.data.supplementary_resources || null,
        },
      ]);
      setQuery("");
    } catch (err) {
      setError(getSafeErrorMessage(err, "Your tutor is unavailable right now. Please try again."));
    } finally {
      setAsking(false);
    }
  }

  if (!track || !subject) {
    return (
      <div className="card">
        <p>Select a track and subject before asking the tutor.</p>
      </div>
    );
  }

  return (
    <div className="tutor-page">
      <div className="page-header">
        <h1>Tutor</h1>
        <p className="page-subtitle">
          Ask anything about {subject}. <span className="tutor-page__track">{track}</span>
        </p>
      </div>

      <label className="field tutor-page__topic-field">
        <span className="field__label">Topic (optional)</span>
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="e.g. Normalization"
        />
      </label>

      <div className="tutor-conversation">
        {exchanges.length === 0 && !asking && (
          <EmptyState title="Ask your first question">
            Get a clear, source-grounded explanation tailored to {subject}.
          </EmptyState>
        )}

        {exchanges.map((exchange, i) => (
          <div key={i} className="tutor-exchange">
            <div className="tutor-message tutor-message--student">
              <div className="tutor-message__author">You</div>
              <div className="tutor-message__bubble">{exchange.question}</div>
            </div>

            <div className="tutor-message">
              <div className="tutor-message__author">AI Tutor</div>
              <div className="tutor-answer">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{exchange.answer}</ReactMarkdown>
              </div>

              {SOURCE_NOTES[exchange.sourceType] && (
                <p className="tutor-exchange__note">{SOURCE_NOTES[exchange.sourceType]}</p>
              )}

              {(exchange.citations.length > 0 || exchange.webCitations.length > 0) && (
                <div className="tutor-exchange__sources">
                  <div className="tutor-exchange__sources-heading">Sources</div>
                  <div className="tutor-exchange__citations">
                    {exchange.citations.map((citation, ci) => (
                      <CitationBadge key={`kb-${ci}`} citation={citation} />
                    ))}
                    {exchange.webCitations.map((citation, ci) => (
                      <CitationBadge key={`web-${ci}`} citation={citation} />
                    ))}
                  </div>
                </div>
              )}

              <SupplementaryResources resources={exchange.supplementaryResources} />
            </div>
          </div>
        ))}

        {asking && (
          <div className="tutor-message">
            <div className="tutor-message__author">AI Tutor</div>
            <div className="tutor-thinking">
              <span className="tutor-thinking__dot" />
              <span className="tutor-thinking__dot" />
              <span className="tutor-thinking__dot" />
              <span>Thinking...</span>
            </div>
          </div>
        )}
      </div>

      <ErrorMessage message={error} />

      <form className="tutor-form" onSubmit={handleSubmit}>
        <label className="field tutor-form__field">
          <span className="field__label">Ask a follow-up</span>
          <textarea
            required
            rows={2}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Explain database normalization"
          />
        </label>
        <button type="submit" className="btn btn--primary tutor-form__submit" disabled={asking}>
          {asking ? "Asking..." : "Send"}
        </button>
      </form>
    </div>
  );
}
