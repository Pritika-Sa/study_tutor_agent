// Renders exactly what the backend returned in `supplementary_resources`
// (see backend/tools/tavily_tool.py:get_supplementary_resources) -- never
// invents a title, description, or URL. Each link opens the real retrieved
// URL directly (no client-side URL construction).
const SECTIONS = [
  { key: "videos", icon: "🎥", heading: "Videos", linkLabel: "Watch" },
  { key: "articles", icon: "📄", heading: "Articles", linkLabel: "Read" },
  { key: "real_world_examples", icon: "🌍", heading: "Real-World Examples", linkLabel: "Explore" },
];

function ResourceCard({ resource, linkLabel }) {
  return (
    <div className="resource-card">
      <p className="resource-card__title">{resource.title}</p>
      {resource.description && <p className="resource-card__description">{resource.description}</p>}
      {resource.source && <p className="resource-card__source">{resource.source}</p>}
      <a
        className="resource-card__link"
        href={resource.url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {linkLabel} ↗
      </a>
    </div>
  );
}

export default function SupplementaryResources({ resources }) {
  if (!resources) return null;

  const sections = SECTIONS.map((section) => ({
    ...section,
    items: resources[section.key] || [],
  })).filter((section) => section.items.length > 0);

  if (sections.length === 0) return null;

  return (
    <div className="supplementary-resources">
      <h3 className="supplementary-resources__heading">Explore More</h3>
      {sections.map((section) => (
        <div key={section.key} className="resource-section">
          <h4 className="resource-section__heading">
            {section.icon} {section.heading}
          </h4>
          <div className="resource-section__grid">
            {section.items.map((resource, i) => (
              <ResourceCard key={`${section.key}-${i}`} resource={resource} linkLabel={section.linkLabel} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
