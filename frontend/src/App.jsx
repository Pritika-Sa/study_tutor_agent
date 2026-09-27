import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { TrackProvider } from "./context/TrackContext";
import ProtectedRoute from "./components/ProtectedRoute";
import AppLayout from "./components/AppLayout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import Dashboard from "./pages/Dashboard";
import TrackSelection from "./pages/TrackSelection";
import Tutor from "./pages/Tutor";
import Quiz from "./pages/Quiz";
import QuizResult from "./pages/QuizResult";
import Progress from "./pages/Progress";
import WeakTopics from "./pages/WeakTopics";
import RevisionPlan from "./pages/RevisionPlan";

export default function App() {
  return (
    <AuthProvider>
      <TrackProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/track-selection" element={<TrackSelection />} />
              <Route path="/tutor" element={<Tutor />} />
              <Route path="/quiz" element={<Quiz />} />
              <Route path="/quiz/result" element={<QuizResult />} />
              <Route path="/progress" element={<Progress />} />
              <Route path="/weak-topics" element={<WeakTopics />} />
              <Route path="/revision-plan" element={<RevisionPlan />} />
            </Route>
          </Route>

          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </TrackProvider>
    </AuthProvider>
  );
}
