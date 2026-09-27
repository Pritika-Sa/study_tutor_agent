import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTrack } from "../context/TrackContext";
import { getRevisionPlan } from "../api/progressApi";
import { getSafeErrorMessage } from "../utils/apiError";
import { formatDate, formatPercentage } from "../utils/formatters";
import ErrorMessage from "../components/ErrorMessage";
import EmptyState from "../components/EmptyState";
import SkeletonCard from "../components/SkeletonCard";

// Renders exactly what GET /revision-plan returned (see
// agents/revision_planner.py for how the backend builds it) -- no study
// recommendation here is invented independently of that response.
export default function RevisionPlan() {
  const { track } = useTrack();
  const [plan, setPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (track) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await getRevisionPlan(track);
      setPlan(response.data.plan);
    } catch (err) {
      setError(getSafeErrorMessage(err, "No revision plan has been generated yet."));
    } finally {
      setLoading(false);
    }
  }

  if (!track) {
    return (
      <div className="card">
        <p>Select a track to view your revision plan.</p>
        <Link to="/track-selection" className="btn btn--primary">
          Choose your track
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="revision-plan-page">
        <div className="page-header">
          <h1>Your Revision Plan</h1>
          <p className="page-subtitle">Focus on these topics based on your recent performance.</p>
        </div>
        <SkeletonCard count={3} lines={2} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="revision-plan-page">
        <div className="page-header">
          <h1>Your Revision Plan</h1>
        </div>
        <EmptyState title="No revision plan yet" action={
          <Link to="/quiz" className="btn btn--primary">
            Take a quiz
          </Link>
        }>
          {error}
        </EmptyState>
      </div>
    );
  }

  if (!plan) return null;

  const items = plan.items || [];
  const isEmptyPlan = items.length === 1 && items[0].message;

  return (
    <div className="revision-plan-page">
      <div className="page-header">
        <h1>Your Revision Plan</h1>
        <p className="page-subtitle">
          Focus on these topics based on your recent performance.
          {plan.generated_at ? ` Generated ${formatDate(plan.generated_at)}.` : ""}
        </p>
      </div>

      {isEmptyPlan ? (
        <EmptyState title="You're on track">{items[0].message}</EmptyState>
      ) : (
        <>
          <div className="section-header">
            <h2>Today's Focus</h2>
          </div>
          <ol className="revision-plan__items">
            {items.map((item, i) => (
              <li key={i} className={`revision-item revision-item--${item.priority || "medium"}`}>
                <div className="revision-item__index">{i + 1}</div>
                <div className="revision-item__body">
                  <div className="revision-item__header">
                    <h3>
                      {item.subject} &middot; {item.topic}
                    </h3>
                    <span className={`priority-badge priority-badge--${item.priority || "medium"}`}>
                      {item.priority || "medium"} priority
                    </span>
                  </div>
                  <p className="revision-item__mastery">
                    Mastery: {formatPercentage(item.mastery)} ({item.attempts} attempt{item.attempts === 1 ? "" : "s"})
                  </p>
                  {(item.recommended_action || item.suggested_practice || item.next_quiz_recommendation) && (
                    <ul className="revision-item__actions">
                      {item.recommended_action && <li>{item.recommended_action}</li>}
                      {item.suggested_practice && <li>{item.suggested_practice}</li>}
                      {item.next_quiz_recommendation && <li>{item.next_quiz_recommendation}</li>}
                    </ul>
                  )}
                  <Link to="/quiz" className="btn btn--secondary btn--small">
                    Practice this topic
                  </Link>
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
