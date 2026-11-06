import { AUTH_ORIGIN } from "../lib/apiBase";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";

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
    <div className="grid min-h-screen place-items-center bg-page">
      <Card className="w-full max-w-sm p-8 text-center">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">
          Interview<span className="text-accent">Copilot</span>
        </h1>
        <p className="mt-2 text-sm text-ink-soft">
          Know your story. Face your interview. Close your gaps.
        </p>
        {authError && (
          <p className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Sign-in was interrupted. Please try Continue with Google again.
          </p>
        )}
        <Button onClick={start} className="mt-6 w-full" size="lg">
          Continue with Google
        </Button>
        <p className="mt-4 text-xs text-ink-faint">
          Mock interviews, evidence-based feedback, and a plan to improve.
        </p>
      </Card>
    </div>
  );
}
