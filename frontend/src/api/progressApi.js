import api from "./axios";

// Matches backend/api/routes_progress.py exactly.
export const getTracks = () => api.get("/tracks");

export const getProgress = (track) => api.get("/progress", { params: { track } });

export const getWeakTopics = (track) => api.get("/weak-topics", { params: { track } });

export const getRevisionPlan = (track) => api.get("/revision-plan", { params: { track } });

export const getHistory = (track, limit = 20) => api.get("/history", { params: { track, limit } });
