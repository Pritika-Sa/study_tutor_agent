// Renders exactly what the backend returned -- never invents a source. A
// citation is treated as "web" only if it actually carries a `url` (the
// shape backend/agents/explainer.py's web_citations use); otherwise it's
// rendered as a knowledge-base citation using whatever metadata fields are
// actually present (a missing chapter/page is simply omitted, never guessed).
export default function CitationBadge({ citation }) {
  if (!citation) return null;

  if (citation.url) {
    return (
      <a
        className="citation-badge citation-badge--web"
        href={citation.url}
        target="_blank"
        rel="noopener noreferrer"
      >
        <span className="citation-badge__tag">WEB</span>
        <span className="citation-badge__label">{citation.title || citation.url}</span>
      </a>
    );
  }

  const parts = [
    citation.source,
    citation.subject,
    citation.chapter || null,
    citation.page ? `Page ${citation.page}` : null,
  ].filter(Boolean);

  return (
    <span className="citation-badge citation-badge--kb">
      <span className="citation-badge__tag">KB</span>
      <span className="citation-badge__label">{parts.join(" · ") || "Knowledge base"}</span>
    </span>
  );
}
