import { useEffect, useRef } from "react";

type Props = {
  timed: boolean;
  confirming: boolean;
  busy: boolean;
  error: string | null;
  onStay: () => void;
  onLeave: () => void;
  onFinish: () => void;
  onRetry: () => void;
};

function focusable(root: HTMLElement) {
  return [
    ...root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ].filter((el) => !el.hasAttribute("disabled"));
}

export default function LeaveInterviewModal({
  timed,
  confirming,
  busy,
  error,
  onStay,
  onLeave,
  onFinish,
  onRetry,
}: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const onStayRef = useRef(onStay);
  useEffect(() => {
    onStayRef.current = onStay;
  }, [onStay]);

  useEffect(() => {
    const root = panelRef.current;
    const preferred = root?.querySelector<HTMLElement>("[data-autofocus]");
    preferred?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (!busy) onStayRef.current();
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
  }, [busy]);

  return (
    <div
      data-testid="leave-backdrop"
      className="fixed inset-0 z-50 flex items-end justify-center bg-stone-900/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => {
        event.stopPropagation();
        if (event.target === event.currentTarget && !busy) onStay();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="leave-interview-title"
        aria-describedby={
          confirming ? "leave-interview-desc leave-interview-confirm" : "leave-interview-desc"
        }
        data-testid="leave-interview-modal"
        className="start-modal-panel max-h-[92dvh] w-full max-w-[480px] overflow-x-hidden overflow-y-auto rounded-t-2xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:rounded-lg"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-amber-50 text-amber-700">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.3 4.6 2.7 18a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 4.6a2 2 0 0 0-3.4 0Z" />
            </svg>
          </span>
          <h2 id="leave-interview-title" className="pt-1.5 text-lg font-semibold text-ink">
            Leave this interview?
          </h2>
        </div>
        <div id="leave-interview-desc" className="mt-4 space-y-2 text-sm leading-relaxed text-ink-soft">
          <p>Your submitted answers are saved. Anything you have typed but not submitted on this question will be lost.</p>
          {timed && <p>The timer keeps running while you are away.</p>}
        </div>
        {confirming && (
          <p id="leave-interview-confirm" className="mt-3 text-sm text-ink-soft">
            Your answered questions will be scored. Unanswered ones will not count against you.
          </p>
        )}
        {error && (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {error}{" "}
            <button
              type="button"
              onClick={onRetry}
              disabled={busy}
              className="font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
            >
              Try again
            </button>
          </p>
        )}
        <div className="mt-5 flex flex-col gap-2">
          <button
            type="button"
            data-autofocus
            onClick={onStay}
            disabled={busy}
            className="w-full rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          >
            Stay in interview
          </button>
          <button
            type="button"
            onClick={onLeave}
            disabled={busy}
            className="w-full rounded-md border border-line bg-white py-3 text-sm font-semibold text-accent-strong hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          >
            Leave and resume later
          </button>
          <button
            type="button"
            onClick={onFinish}
            disabled={busy}
            className="w-full py-2 text-sm font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
          >
            Finish and get feedback
          </button>
        </div>
      </div>
    </div>
  );
}
