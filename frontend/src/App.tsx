import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import DashboardPage from "./pages/DashboardPage";
import OnboardingPage from "./pages/OnboardingPage";
import TrackDetailPage from "./pages/TrackDetailPage";
import InterviewPage from "./pages/InterviewPage";
import ReportPage from "./pages/ReportPage";
import SignInPage from "./pages/SignInPage";

export default function App() {
  const { user, loading, signOut } = useAuth();
  const navigate = useNavigate();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-stone-500">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <SignInPage />;
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
          <span className="font-semibold tracking-tight">
            Interview<span className="text-indigo-600">Copilot</span>
          </span>
          <nav className="flex gap-1 text-sm">
            <NavLink
              to="/"
              className={({ isActive }) =>
                `rounded-md px-3 py-1.5 ${
                  isActive ? "bg-stone-100 font-medium" : "text-stone-600 hover:bg-stone-50"
                }`
              }
            >
              Tracks
            </NavLink>
            <NavLink
              to="/onboarding"
              className={({ isActive }) =>
                `rounded-md px-3 py-1.5 ${
                  isActive ? "bg-stone-100 font-medium" : "text-stone-600 hover:bg-stone-50"
                }`
              }
            >
              Onboarding
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-stone-500">{user.email}</span>
            <button
              onClick={async () => {
                await signOut();
                navigate("/");
              }}
              className="rounded-md border border-stone-200 px-3 py-1.5 hover:bg-stone-50"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/tracks/:trackId" element={<TrackDetailPage />} />
          <Route
            path="/tracks/:trackId/interview/:sessionId"
            element={<InterviewPage />}
          />
          <Route
            path="/tracks/:trackId/report/:sessionId"
            element={<ReportPage />}
          />
        </Routes>
      </main>
    </div>
  );
}
