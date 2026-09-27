import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTrack } from "../context/TrackContext";
import { getProgress } from "../api/progressApi";
import { getSafeErrorMessage } from "../utils/apiError";
import { formatDate, formatPercentage } from "../utils/formatters";
import ErrorMessage from "../components/ErrorMessage";
import EmptyState from "../components/EmptyState";
import SkeletonCard from "../components/SkeletonCard";
import ProgressCard from "../components/ProgressCard";
import MasteryBar from "../components/MasteryBar";

export default function Progress() {
  const { track } = useTrack();
  const [data, setData] = useState(null);
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
      const response = await getProgress(track);
      setData(response.data);
    } catch (err) {
      setError(getSafeErrorMessage(err, "Unable to load your progress. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  if (!track) {
    return (
      <div className="card">
        <p>Select a track to view your progress.</p>
        <Link to="/track-selection" className="btn btn--primary">
          Choose your track
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="progress-page">
        <div className="page-header">
          <h1>Progress</h1>
          <p className="page-subtitle">Track: {track}</p>
        </div>
        <SkeletonCard count={3} lines={2} />
      </div>
    );
  }

  if (error) return <ErrorMessage message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="progress-page">
      <div className="page-header">
        <h1>Progress</h1>
        <p className="page-subtitle">Track: {track}</p>
      </div>

      <div className="stat-row">
        <ProgressCard label="Overall mastery" value={formatPercentage(data.overall_percentage)} />
        <ProgressCard label="Weak topics" value={data.weak_topics.length} />
        <ProgressCard label="Strong topics" value={data.strong_topics.length} />
        <ProgressCard label="Recent attempts" value={data.recent_attempts.length} />
      </div>

      <section className="progress-page__section">
        <div className="section-header">
          <h2>Topic Mastery</h2>
        </div>
        {data.weak_topics.length === 0 && data.strong_topics.length === 0 ? (
          <EmptyState title="No topic mastery data yet" inline>
            Take a quiz to get started.
          </EmptyState>
        ) : (
          <>
            {data.weak_topics.map((t, i) => (
              <div key={`weak-${i}`} className="mastery-row">
                <span className="mastery-row__label">
                  {t.subject} &middot; {t.topic}
                </span>
                <MasteryBar value={t.mastery} />
              </div>
            ))}
            {data.strong_topics.map((t, i) => (
              <div key={`strong-${i}`} className="mastery-row">
                <span className="mastery-row__label">
                  {t.subject} &middot; {t.topic}
                </span>
                <MasteryBar value={t.percentage} />
              </div>
            ))}
          </>
        )}
      </section>

      <section className="progress-page__section">
        <div className="section-header">
          <h2>Recent Attempts</h2>
        </div>
        {data.recent_attempts.length === 0 ? (
          <EmptyState title="No quiz attempts yet" inline>
            Start your first quiz to build your learning history.
          </EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Track</th>
                <th>Subject</th>
                <th>Topic</th>
                <th>Score</th>
                <th>Percentage</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_attempts.map((attempt, i) => (
                <tr key={i}>
                  <td>{formatDate(attempt.created_at)}</td>
                  <td>{attempt.track}</td>
                  <td>{attempt.subject}</td>
                  <td>{attempt.topic}</td>
                  <td>
                    {attempt.score}/{attempt.total_questions}
                  </td>
                  <td>{formatPercentage(attempt.percentage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
