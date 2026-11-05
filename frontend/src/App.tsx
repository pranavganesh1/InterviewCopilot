import { Link, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import AppHeader from "./components/AppHeader";
import DashboardPage from "./pages/DashboardPage";
import OnboardingPage from "./pages/OnboardingPage";
import TrackDetailPage from "./pages/TrackDetailPage";
import InterviewPage from "./pages/InterviewPage";
import ReportPage from "./pages/ReportPage";
import ProfilePage from "./pages/ProfilePage";
import SignInPage from "./pages/SignInPage";

export default function App() {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  const isInterviewSession = /\/tracks\/[^/]+\/interview\//.test(pathname);

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#f6f4fb] text-slate-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <SignInPage />;
  }

  return (
    <div className="flex min-h-dvh flex-col overflow-x-clip bg-[#f6f4fb] text-slate-900">
      <AppHeader />
      <main
        className={
          isInterviewSession
            ? "flex min-h-0 w-full min-w-0 flex-1 flex-col overflow-x-hidden"
            : "mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8"
        }
      >
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/tracks/:trackId" element={<TrackDetailPage />} />
          <Route
            path="/tracks/:trackId/interview/:sessionId"
            element={<InterviewPage />}
          />
          <Route
            path="/tracks/:trackId/report/:sessionId"
            element={<ReportPage />}
          />
          <Route
            path="*"
            element={
              <div className="py-20 text-center">
                <p className="text-lg font-medium">Page not found</p>
                <Link to="/" className="text-sm text-indigo-600 hover:underline">
                  ← Back to your tracks
                </Link>
              </div>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
