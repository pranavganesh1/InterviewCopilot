import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Track } from "../lib/api";

type Props = {
  track: Track;
  attempts: number;
  reports: number;
  onCancel: () => void;
  onDeleted: () => void;
  onResume: (sessionId: string) => void;
  onFinished: (sessionId: string) => void;
};

function focusable(root: HTMLElement) {
  return [
    ...root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((el) => !el.hasAttribute("disabled"));
}

function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

export default function DeleteTrackDialog({
  track,
  attempts,
  reports,
  onCancel,
  onDeleted,
  onResume,
  onFinished,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCancelRef = useRef(onCancel);
  const [busy, setBusy] = useState<"delete" | "finish" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);

  useEffect(() => {
    onCancelRef.current = onCancel;
  }, [onCancel]);

  useEffect(() => {
    const root = panelRef.current;
    root?.querySelector<HTMLElement>("[data-autofocus]")?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!busy) onCancelRef.current();
        return;
      }
      if (event.key !== "Tab" || !root) return;
      const list = focusable(root);
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [busy, sessionId, error]);

  async function confirmDelete() {
    setBusy("delete");
    setError(null);
    try {
      await api(`/tracks/${track.id}`, { method: "DELETE" });
      onDeleted();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.code === "unfinished_interview" &&
        err.sessionId
      ) {
        setSessionId(err.sessionId);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Could not delete this track.");
    } finally {
      setBusy(null);
    }
  }

  async function finish() {
    if (!sessionId) return;
    setBusy("finish");
    setError(null);
    try {
      await api(`/sessions/${sessionId}/complete`, { method: "POST" });
      onFinished(sessionId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not finish this interview.");
    } finally {
      setBusy(null);
    }
  }

  const conflict = sessionId !== null;

  return (
    <div
      data-testid="delete-track-backdrop"
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-track-title"
        className="start-modal-panel w-full max-w-md rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl"
      >
        <h2 id="delete-track-title" className="text-lg font-semibold text-slate-900">
          {conflict ? "You have an unfinished interview on this track" : "Delete this track?"}
        </h2>
        <p className="mt-1 text-sm font-medium text-slate-800">{track.subject}</p>
        {!conflict && (
          <>
            <p className="mt-2 text-sm text-slate-500">
              {plural(attempts, "attempt", "attempts")}, {plural(reports, "report", "reports")}
            </p>
            <p className="mt-2 text-sm text-slate-600">
              The track will be removed from your list. Your interview history and reports are kept.
            </p>
          </>
        )}
        {error && (
          <p role="alert" className="mt-3 rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            data-autofocus
            disabled={busy !== null}
            onClick={onCancel}
            className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            Cancel
          </button>
          {conflict ? (
            <>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => onResume(sessionId)}
                className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100 disabled:opacity-60"
              >
                Resume interview
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void finish()}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60"
              >
                {busy === "finish" && (
                  <svg viewBox="0 0 24 24" className="h-4 w-4 animate-spin" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                )}
                Finish and get feedback
              </button>
            </>
          ) : (
            <>
              {error && (
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void confirmDelete()}
                  className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Try again
                </button>
              )}
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void confirmDelete()}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
              >
                {busy === "delete" && (
                  <svg viewBox="0 0 24 24" className="h-4 w-4 animate-spin" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                  </svg>
                )}
                Delete track
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
