import { createContext, useCallback, useContext, useState } from "react";
import { getItem, removeItem, setItem } from "../utils/storage";

const TrackContext = createContext(null);

const TRACK_KEY = "selected_track";
const SUBJECT_KEY = "selected_subject";

export function TrackProvider({ children }) {
  const [track, setTrackState] = useState(() => getItem(TRACK_KEY) || null);
  const [subject, setSubjectState] = useState(() => getItem(SUBJECT_KEY) || null);

  // Changing track always clears subject -- a stale subject from a
  // different track (e.g. "Biology" left over while now on Placement)
  // must never be silently carried forward into an API call.
  const setTrack = useCallback((value) => {
    setTrackState(value);
    setSubjectState(null);
    if (value) setItem(TRACK_KEY, value);
    else removeItem(TRACK_KEY);
    removeItem(SUBJECT_KEY);
  }, []);

  const setSubject = useCallback((value) => {
    setSubjectState(value);
    if (value) setItem(SUBJECT_KEY, value);
    else removeItem(SUBJECT_KEY);
  }, []);

  const value = { track, subject, setTrack, setSubject };
  return <TrackContext.Provider value={value}>{children}</TrackContext.Provider>;
}

export function useTrack() {
  const ctx = useContext(TrackContext);
  if (!ctx) throw new Error("useTrack must be used within a TrackProvider");
  return ctx;
}
