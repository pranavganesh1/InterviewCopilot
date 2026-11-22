import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { lazy, Suspense, type ReactNode } from "react";
import { useAuth } from "./context/AuthContext";
import AppHeader from "./components/AppHeader";
import DashboardSidebar from "./components/DashboardSidebar";
import DashboardPage from "./pages/DashboardPage";
import OnboardingPage from "./pages/OnboardingPage";
import TrackDetailPage from "./pages/TrackDetailPage";
import SignInPage from "./pages/SignInPage";

// Lazy-load heavier routes (Monaco editor in InterviewPage, reports, admin, readiness)
// to keep the initial dashboard bundle lightweight and fast.
const InterviewPage = lazy(() => import("./pages/InterviewPage"));
const ReportPage = lazy(() => import("./pages/ReportPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const ReadinessPage = lazy(() => import("./pages/ReadinessPage"));
const AdminOverviewPage = lazy(() => import("./pages/AdminOverviewPage"));
const AdminUsersPage = lazy(() => import("./pages/AdminUsersPage"));
const AdminUserDetailPage = lazy(() => import("./pages/AdminUserDetailPage"));

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

  if (isImmersive) {
    return (
      <div className="flex h-dvh flex-col overflow-hidden overflow-x-clip bg-page text-ink">
        <AppHeader />
        <main
          className={
            isOnboarding
              ? "mx-auto flex min-h-0 w-full min-w-0 max-w-[90rem] flex-1 flex-col overflow-hidden px-3 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-4 sm:py-3"
              : "mx-auto flex min-h-0 w-full min-w-0 max-w-6xl flex-1 flex-col overflow-hidden px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4 sm:py-4"
          }
        >
          <Routes>
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route
              path="/tracks/:trackId/interview/:sessionId"
              element={<InterviewPage />}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh overflow-x-clip bg-page text-ink">
      <DashboardSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader />
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5 sm:px-5 sm:py-6 lg:px-6">
          <Suspense fallback={null}>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
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
          </Suspense>
        </main>
      </div>
    </div>
  );
}
