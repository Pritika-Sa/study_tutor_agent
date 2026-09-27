// Polished empty state -- a title + short body copy, optionally with an
// action link/button. Used wherever a list/section legitimately has
// nothing to show yet (no data invented, nothing hidden that shouldn't be).
export default function EmptyState({ title, children, action, inline = false }) {
  return (
    <div className={`empty-state${inline ? " empty-state--inline" : ""}`}>
      {title && <div className="empty-state__title">{title}</div>}
      {children && <div className="empty-state__body">{children}</div>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
