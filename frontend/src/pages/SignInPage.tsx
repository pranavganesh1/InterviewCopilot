import { AUTH_ORIGIN } from "../lib/apiBase";

export default function SignInPage() {
  const authError =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("auth_error") === "state";

  const start = () => {
    // Navigate to the API host directly (not via the Vite proxy) so the OAuth
    // state session cookie is set on the same host as the Google callback.
    window.location.href = `${AUTH_ORIGIN}/api/v1/auth/google/url`;
  };

  return (
    <div className="grid min-h-screen place-items-center bg-stone-50">
      <div className="w-full max-w-sm rounded-2xl border border-stone-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-2xl font-semibold tracking-tight">
          Interview<span className="text-indigo-600">Copilot</span>
        </h1>
        <p className="mt-2 text-sm text-stone-500">
          Know your story. Face your interview. Close your gaps.
        </p>
        {authError && (
          <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Sign-in was interrupted. Please try Continue with Google again.
          </p>
        )}
        <button
          onClick={start}
          className="mt-6 w-full rounded-xl bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-700"
        >
          Continue with Google
        </button>
        <p className="mt-4 text-xs text-stone-400">
          Mock interviews, evidence-based feedback, and a plan to improve.
        </p>
      </div>
    </div>
  );
}
