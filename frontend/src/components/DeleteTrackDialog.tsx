import { useEffect, useRef, useState } from "react";
import { ApiError, api, type Track } from "../lib/api";

type Props = {
  track: Track;
  attempts: number;
  reports: number;
  onCancel: () => void;
  onDeleted: () => void;
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
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onCancelRef = useRef(onCancel);
  const [busy, setBusy] = useState<"delete" | "finish" | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, [busy, error]);

  async function confirmDelete() {
    setBusy("delete");
    setError(null);
    try {
      await api(`/tracks/${track.id}`, { method: "DELETE" });
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not delete this track.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      data-testid="delete-track-backdrop"
      className="fixed inset-0 z-50 flex items-end justify-center bg-stone-900/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-track-title"
        className="start-modal-panel w-full max-w-md rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-lg"
      >
        <h2 id="delete-track-title" className="text-lg font-semibold text-ink">
          Delete this track?
        </h2>
        <p className="mt-1 text-sm font-medium text-ink">{track.subject}</p>
        <p className="mt-2 text-sm text-ink-soft">
          {plural(attempts, "attempt", "attempts")}, {plural(reports, "report", "reports")}
        </p>
        <p className="mt-2 text-sm text-ink-soft">
          The track will be removed from your list. Any unfinished interview is closed.
          Your interview history and reports are kept.
        </p>
        {error && (
          <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button
            type="button"
            data-autofocus
            disabled={busy !== null}
            onClick={onCancel}
            className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink-soft hover:bg-page disabled:opacity-60"
          >
            Cancel
          </button>
          {error && (
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void confirmDelete()}
              className="rounded-md border border-line px-4 py-2 text-sm font-semibold text-ink-soft hover:bg-page"
            >
              Try again
            </button>
          )}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void confirmDelete()}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-60"
          >
            {busy === "delete" && (
              <svg viewBox="0 0 24 24" className="h-4 w-4 animate-spin" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
              </svg>
            )}
            Delete track
          </button>
        </div>
      </div>
    </div>
  );
}
