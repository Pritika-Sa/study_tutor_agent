import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTrack } from "../context/TrackContext";
import { getProgress, getRevisionPlan } from "../api/progressApi";
import { getSafeErrorMessage } from "../utils/apiError";
import { formatDate, formatPercentage } from "../utils/formatters";
import ErrorMessage from "../components/ErrorMessage";
import EmptyState from "../components/EmptyState";
import SkeletonCard from "../components/SkeletonCard";
import ProgressCard from "../components/ProgressCard";

const QUICK_ACTIONS = [
  { to: "/tutor", label: "Ask Tutor" },
  { to: "/quiz", label: "Take Quiz" },
  { to: "/weak-topics", label: "Weak Topics" },
  { to: "/revision-plan", label: "Revision Plan" },
];

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const { user } = useAuth();
  const { track, subject } = useTrack();

  const [progress, setProgress] = useState(null);
  const [progressLoading, setProgressLoading] = useState(false);
  const [progressError, setProgressError] = useState(null);

  // Revision plan loads independently -- generating one on demand (when
  // none exists yet) calls the real LangGraph Revision Planner agent, which
  // can take a few seconds; it must never block the rest of the dashboard.
  const [plan, setPlan] = useState(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState(null);

  useEffect(() => {
    if (!track) return;
    loadProgress();
    loadPlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track]);

  async function loadProgress() {
    setProgressLoading(true);
    setProgressError(null);
    try {
      const response = await getProgress(track);
      setProgress(response.data);
    } catch (err) {
      setProgressError(getSafeErrorMessage(err, "Unable to load your progress."));
    } finally {
      setProgressLoading(false);
    }
  }

  async function loadPlan() {
    setPlanLoading(true);
    setPlanError(null);
    try {
      const response = await getRevisionPlan(track);
      setPlan(response.data.plan);
    } catch (err) {
      setPlanError(getSafeErrorMessage(err, "No revision plan available yet."));
    } finally {
      setPlanLoading(false);
    }
  }

  const weakestTopic = progress?.weak_topics?.[0] || null;

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1>
          {greeting()}
          {user ? `, ${user.name}` : ""}
        </h1>
        <p className="page-subtitle">Continue your learning journey.</p>
      </div>

      {!track ? (
        <div className="card">
          <p>You haven&apos;t selected a learning track yet.</p>
          <Link to="/track-selection" className="btn btn--primary">
            Choose your track
          </Link>
        </div>
      ) : (
        <div className="dashboard__track-banner">
          <span className="dashboard__track-label">Current Track</span>
          <span className="navbar__track dashboard__track-pill">{track}</span>
          {subject && <span className="dashboard__track-subject">{subject}</span>}
        </div>
      )}

      {track && (
        <>
          <section className="dashboard__section">
            <div className="section-header">
              <h2>Your Progress</h2>
            </div>
            {progressLoading && <SkeletonCard count={1} lines={1} />}
            {progressError && <ErrorMessage message={progressError} onRetry={loadProgress} />}
            {!progressLoading && !progressError && progress && (
              <>
                <div className="stat-row">
                  <ProgressCard label="Overall mastery" value={formatPercentage(progress.overall_percentage)} />
                  <ProgressCard label="Weak topics" value={progress.weak_topics.length} />
                  <ProgressCard label="Strong topics" value={progress.strong_topics.length} />
                  <ProgressCard label="Recent attempts" value={progress.recent_attempts.length} />
                </div>

                {progress.recent_attempts.length === 0 ? (
                  <EmptyState title="No quiz attempts yet" inline>
                    Start your first quiz to build your learning history.
                  </EmptyState>
                ) : (
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Subject</th>
                        <th>Topic</th>
                        <th>Score</th>
                        <th>Percentage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {progress.recent_attempts.slice(0, 5).map((attempt, i) => (
                        <tr key={i}>
                          <td>{formatDate(attempt.created_at)}</td>
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
              </>
            )}
          </section>

          {weakestTopic && (
            <section className="dashboard__section">
              <div className="section-header">
                <h2>Continue Learning</h2>
              </div>
              <div className="card dashboard__continue-card">
                <div>
                  <div className="dashboard__continue-subject">{weakestTopic.subject}</div>
                  <div className="dashboard__continue-topic">{weakestTopic.topic}</div>
                  <div className="dashboard__continue-meta">
                    Mastery {formatPercentage(weakestTopic.mastery)} &middot; needs more practice
                  </div>
                </div>
                <Link to="/tutor" className="btn btn--primary">
                  Continue →
                </Link>
              </div>
            </section>
          )}

          <section className="dashboard__section">
            <div className="section-header">
              <h2>Revision Plan</h2>
            </div>
            {planLoading && <SkeletonCard count={1} lines={2} />}
            {!planLoading && planError && (
              <EmptyState title="No revision plan yet" inline>
                {planError}
              </EmptyState>
            )}
            {!planLoading && !planError && plan && (
              <div className="card dashboard__plan-card">
                <p>
                  {plan.items?.[0]?.message
                    ? plan.items[0].message
                    : `${plan.weak_topics_considered} weak topic(s) considered, based on ${plan.recent_attempts_considered} recent attempt(s).`}
                </p>
                <Link to="/revision-plan" className="btn btn--secondary">
                  View full plan
                </Link>
              </div>
            )}
          </section>

          <section className="dashboard__section">
            <div className="section-header">
              <h2>Quick Actions</h2>
            </div>
            <div className="quick-actions">
              {QUICK_ACTIONS.map((action) => (
                <Link key={action.to} to={action.to} className="quick-action">
                  {action.label}
                </Link>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
