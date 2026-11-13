import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./context/AuthContext";
import AppHeader from "./components/AppHeader";
import DashboardPage from "./pages/DashboardPage";
import OnboardingPage from "./pages/OnboardingPage";
import TrackDetailPage from "./pages/TrackDetailPage";
import InterviewPage from "./pages/InterviewPage";
import ReportPage from "./pages/ReportPage";
import ProfilePage from "./pages/ProfilePage";
import ReadinessPage from "./pages/ReadinessPage";
import SignInPage from "./pages/SignInPage";
import AdminOverviewPage from "./pages/AdminOverviewPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import AdminUserDetailPage from "./pages/AdminUserDetailPage";

function AdminOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user?.is_admin) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  const isInterviewSession = /\/tracks\/[^/]+\/interview\//.test(pathname);
  const isOnboarding = pathname === "/onboarding";
  const isImmersive = isInterviewSession || isOnboarding;

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-page text-ink-soft">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <SignInPage />;
  }

  return (
    <div
      className={`flex flex-col overflow-x-clip bg-page text-ink ${
        isImmersive ? "h-dvh overflow-hidden" : "min-h-dvh"
      }`}
    >
      <AppHeader />
      <main
        className={
          isOnboarding
            ? "mx-auto flex min-h-0 w-full min-w-0 max-w-[90rem] flex-1 flex-col overflow-hidden px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-4 sm:py-3"
            : isImmersive
              ? "mx-auto flex min-h-0 w-full min-w-0 max-w-6xl flex-1 flex-col overflow-hidden px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4 sm:py-4"
              : "mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:py-8"
        }
      >
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/readiness" element={<ReadinessPage />} />
          <Route
            path="/admin"
            element={
              <AdminOnly>
                <AdminOverviewPage />
              </AdminOnly>
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminOnly>
                <AdminUsersPage />
              </AdminOnly>
            }
          />
          <Route
            path="/admin/users/:userId"
            element={
              <AdminOnly>
                <AdminUserDetailPage />
              </AdminOnly>
            }
          />
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
                <Link to="/" className="text-sm text-accent hover:underline">
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
