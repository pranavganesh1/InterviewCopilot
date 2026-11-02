export default function SignInPage() {
  const start = () => {
    window.location.href = "/api/v1/auth/google/url";
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
