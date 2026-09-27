import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTrack } from "../context/TrackContext";
import { getProgress, getWeakTopics } from "../api/progressApi";
import { getSafeErrorMessage } from "../utils/apiError";
import { formatPercentage } from "../utils/formatters";
import ErrorMessage from "../components/ErrorMessage";
import EmptyState from "../components/EmptyState";
import SkeletonCard from "../components/SkeletonCard";
import MasteryBar from "../components/MasteryBar";

// "Weak" vs "mastered" here is exactly the backend's own classification --
// GET /weak-topics already only returns topics below its configured
// MASTERY_THRESHOLD_PERCENT, and GET /progress's strong_topics only returns
// ones at/above it. Nothing on this page recomputes or hardcodes a
// different threshold; it just renders each backend-classified list under
// its own heading.
export default function WeakTopics() {
  const { track } = useTrack();
  const [weakTopics, setWeakTopics] = useState(null);
  const [strongTopics, setStrongTopics] = useState(null);
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
      const [weakResponse, progressResponse] = await Promise.all([getWeakTopics(track), getProgress(track)]);
      setWeakTopics(weakResponse.data.weak_topics);
      setStrongTopics(progressResponse.data.strong_topics);
    } catch (err) {
      setError(getSafeErrorMessage(err, "Unable to load weak topics. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  if (!track) {
    return (
      <div className="card">
        <p>Select a track to view weak topics.</p>
        <Link to="/track-selection" className="btn btn--primary">
          Choose your track
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="weak-topics-page">
        <div className="page-header">
          <h1>Weak Topics</h1>
          <p className="page-subtitle">Track: {track}</p>
        </div>
        <SkeletonCard count={3} lines={2} />
      </div>
    );
  }
  if (error) return <ErrorMessage message={error} onRetry={load} />;
  // Guards the one render tick between mount and the fetch effect actually
  // starting (loading is still false, but weakTopics hasn't been set yet) --
  // without this, weakTopics.length below throws on null and blanks the
  // whole page (see WeakTopics.test.jsx). Matches the same guard already
  // used by Progress.jsx (`if (!data) return null`) and RevisionPlan.jsx
  // (`if (!plan) return null`).
  if (!weakTopics) return null;

  return (
    <div className="weak-topics-page">
      <div className="page-header">
        <h1>Weak Topics</h1>
        <p className="page-subtitle">
          Track: {track}
          {weakTopics.length > 0
            ? ` · You have ${weakTopics.length} topic${weakTopics.length === 1 ? "" : "s"} that need attention.`
            : ""}
        </p>
      </div>

      <section className="weak-topics-page__section">
        <div className="section-header">
          <h2>Needs Practice</h2>
        </div>
        {weakTopics.length === 0 ? (
          <EmptyState title="You're doing well">Great! No weak topics have been identified yet.</EmptyState>
        ) : (
          <div className="weak-topic-list">
            {weakTopics.map((t, i) => (
              <div key={i} className="weak-topic-card">
                <div className="weak-topic-card__info">
                  <div className="weak-topic-card__subject">{t.subject}</div>
                  <h3 className="weak-topic-card__topic">{t.topic}</h3>
                  <div className="weak-topic-card__mastery">
                    <span className="weak-topic-card__mastery-label">Mastery</span>
                    <MasteryBar value={t.mastery} />
                  </div>
                  <div className="weak-topic-card__meta">
                    <span>{t.attempts}</span> attempt{t.attempts === 1 ? "" : "s"} &middot; Needs Review
                  </div>
                </div>
                <Link to="/quiz" className="btn btn--secondary">
                  Review Topic →
                </Link>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="weak-topics-page__section">
        <div className="section-header">
          <h2>Mastered Topics</h2>
        </div>
        {!strongTopics || strongTopics.length === 0 ? (
          <EmptyState title="No mastered topics yet" inline>
            Keep practicing to build up your mastered topics.
          </EmptyState>
        ) : (
          <ul className="mastered-list">
            {strongTopics.map((t, i) => (
              <li key={i}>
                <span>
                  {t.subject} &middot; {t.topic}
                </span>
                <span className="mastered-list__value">{formatPercentage(t.percentage)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
