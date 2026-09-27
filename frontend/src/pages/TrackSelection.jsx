import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTracks } from "../api/progressApi";
import { useTrack } from "../context/TrackContext";
import { getSafeErrorMessage } from "../utils/apiError";
import Loading from "../components/Loading";
import ErrorMessage from "../components/ErrorMessage";

const TRACK_DESCRIPTIONS = {
  NEET: "Physics, Chemistry, and Biology for NEET preparation.",
  Placement: "Java, SQL, Aptitude, DBMS, and DSA for placement preparation.",
};

export default function TrackSelection() {
  const navigate = useNavigate();
  const { track, subject, setTrack, setSubject } = useTrack();

  const [tracks, setTracks] = useState(null); // { NEET: [...], Placement: [...] } from GET /tracks
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadTracks();
  }, []);

  async function loadTracks() {
    setLoading(true);
    setError(null);
    try {
      const response = await getTracks();
      setTracks(response.data);
    } catch (err) {
      setError(getSafeErrorMessage(err, "Unable to load tracks. Please try again."));
    } finally {
      setLoading(false);
    }
  }

  function handleSelectSubject(trackName, subjectName) {
    setTrack(trackName);
    setSubject(subjectName);
    navigate("/dashboard");
  }

  if (loading) return <Loading label="Loading tracks..." />;
  if (error) return <ErrorMessage message={error} onRetry={loadTracks} />;
  if (!tracks) return null;

  return (
    <div className="track-selection">
      <h1>Choose your learning track</h1>
      <p className="page-subtitle">Select a track, then a subject, to personalize your tutor and quizzes.</p>

      <div className="track-selection__grid">
        {Object.entries(tracks).map(([trackName, subjects]) => (
          <div key={trackName} className={`track-card${track === trackName ? " track-card--active" : ""}`}>
            <div className="track-card__icon" aria-hidden="true">
              {trackName === "NEET" ? "NE" : "PL"}
            </div>
            <h2>{trackName === "NEET" ? "NEET Preparation" : "College Placement Preparation"}</h2>
            <p>{TRACK_DESCRIPTIONS[trackName] || ""}</p>
            <div className="track-card__subjects">
              {subjects.map((subjectName) => (
                <button
                  key={subjectName}
                  type="button"
                  className={`subject-pill${track === trackName && subject === subjectName ? " subject-pill--active" : ""}`}
                  onClick={() => handleSelectSubject(trackName, subjectName)}
                >
                  {subjectName}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
