import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type OpenSession, type Progression } from "../lib/api";

const PRESETS = [30, 45, 60, 90, 120, 180];

type Mode = "strict" | "guided";
type Phase = "loading" | "resume" | "confirm-finish" | "confirm-new" | "setup";

export type StartTrack = { id: string; subject: string };

function friendly(err: unknown): string {
  if (err instanceof ApiError && err.status === 503) {
    return "The interview model is busy right now. Wait a moment and try again.";
  }
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong. Please try again.";
}

function startedLabel(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 1) return "Started just now";
  if (minutes < 60) {
    return `Started ${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `Started ${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `Started ${days} day${days === 1 ? "" : "s"} ago`;
}

function remainingLabel(
  iso: string | null | undefined,
  duration: number | null | undefined,
): string | null {
  if (!iso || duration == null) return null;
  const elapsed = (Date.now() - new Date(iso).getTime()) / 60000;
  if (Number.isNaN(elapsed)) return null;
  const left = Math.max(0, Math.round(duration - elapsed));
  if (left < 60) return `${left} min left`;
  const hours = Math.floor(left / 60);
  const mins = left % 60;
  return mins ? `${hours} hr ${mins} min left` : `${hours} hr left`;
}

function durationLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = minutes / 60;
  return `${hours} hr${hours > 1 ? "s" : ""}`;
}

function focusable(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => !el.hasAttribute("disabled"));
}

export default function StartInterviewModal({
  track,
  onClose,
}: {
  track: StartTrack | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const seenTrack = useRef<string | null>(null);
  const onCloseRef = useRef(onClose);
  const [choice, setChoice] = useState<{ trackId: string; phase: Phase } | null>(null);
  const [mode, setMode] = useState<Mode>("strict");
  const [duration, setDuration] = useState(60);
  const [custom, setCustom] = useState("");
  const [useCustom, setUseCustom] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<"start" | "finish" | null>(null);
  const [finishing, setFinishing] = useState(false);

  const openSession = useQuery({
    queryKey: ["open-session", track?.id],
    enabled: Boolean(track),
    retry: false,
    queryFn: () =>
      api<{ session: OpenSession | null }>(`/tracks/${track!.id}/open-session`),
  });
  const progression = useQuery({
    queryKey: ["progression", track?.id],
    enabled: Boolean(track),
    retry: false,
    queryFn: () => api<Progression>(`/tracks/${track!.id}/progression`),
  });

  const unfinished = openSession.data?.session ?? null;
  const guidedUnlocked = progression.data?.guided_state === "UNLOCKED";
  const phase: Phase =
    choice && track && choice.trackId === track.id
      ? choice.phase
      : !track || openSession.isLoading
        ? "loading"
        : unfinished
          ? "resume"
          : "setup";
  const customValue = parseInt(custom, 10);
  const customValid = !Number.isNaN(customValue) && customValue >= 15 && customValue <= 240;
  const startMinutes = useCustom ? (customValid ? customValue : null) : duration;

  const start = useMutation({
    mutationFn: async () => {
      if (!track || startMinutes == null) throw new Error("Choose a duration first.");
      if (unfinished) {
        await api(`/sessions/${unfinished.id}/complete`, { method: "POST" });
      }
      return api<{ session: { id: string } }>(`/tracks/${track.id}/sessions`, {
        method: "POST",
        body: JSON.stringify({ mode, duration_minutes: startMinutes }),
      });
    },
    onSuccess: (data) => {
      if (!track) return;
      navigate(`/tracks/${track.id}/interview/${data.session.id}`);
    },
    onError: (err) => {
      setRetry("start");
      setError(friendly(err));
    },
  });

  const requestBusy = finishing || start.isPending;

  useEffect(() => {
    onCloseRef.current = onClose;
    if (!track) {
      seenTrack.current = null;
      return;
    }
    const root = panelRef.current;
    if (!root) return;
    if (seenTrack.current !== track.id) {
      seenTrack.current = track.id;
      returnTo.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    const items = focusable(root);
    const preferred = root.querySelector<HTMLElement>("[data-autofocus]");
    (preferred && !preferred.hasAttribute("disabled") ? preferred : items[0])?.focus();

    function dismiss() {
      onCloseRef.current();
      returnTo.current?.focus();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        dismiss();
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
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [track, phase, requestBusy, onClose]);

  if (!track) return null;

  function choose(next: Phase) {
    setError(null);
    setChoice({ trackId: track!.id, phase: next });
  }

  function close() {
    onClose();
    returnTo.current?.focus();
  }

  async function finish() {
    if (!unfinished) return;
    setFinishing(true);
    setError(null);
    try {
      await api(`/sessions/${unfinished.id}/complete`, { method: "POST" });
      navigate(`/tracks/${track!.id}/report/${unfinished.id}`);
    } catch (err) {
      setRetry("finish");
      setError(friendly(err));
    } finally {
      setFinishing(false);
    }
  }

  function tryAgain() {
    if (retry === "finish") void finish();
    else start.mutate();
  }

  const started = startedLabel(unfinished?.created_at);
  const remaining = remainingLabel(unfinished?.created_at, unfinished?.duration_minutes);
  const progress =
    unfinished && unfinished.max_turns > 0
      ? Math.min(100, Math.round((unfinished.question_index / unfinished.max_turns) * 100))
      : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-stone-900/40 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !requestBusy) close();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="start-interview-title"
        className="start-modal-panel max-h-[92dvh] w-full max-w-[480px] overflow-x-hidden overflow-y-auto rounded-t-2xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl sm:rounded-lg"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2
              id="start-interview-title"
              className="break-words text-lg font-semibold text-ink"
            >
              {track.subject}
            </h2>
            {phase === "resume" && unfinished && (
              <span className="mt-2 inline-flex rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent-strong">
                {unfinished.mode === "guided" ? "Guided" : "Strict"}
              </span>
            )}
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={close}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-md text-ink-soft hover:bg-accent-soft hover:text-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>

        {phase === "loading" && (
          <p className="mt-5 text-sm text-ink-soft">Checking this track…</p>
        )}

        {phase === "resume" && unfinished && (
          <div className="mt-5 space-y-4">
            <div className="rounded-lg border border-line bg-accent-soft/60 p-4">
              <p className="text-sm font-semibold text-ink">Unfinished interview</p>
              <p className="mt-1 text-sm text-ink-soft">
                Question {unfinished.question_index} of {unfinished.max_turns}
              </p>
              <div
                className="mt-3 h-1.5 overflow-hidden rounded-full bg-accent-soft"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={unfinished.max_turns}
                aria-valuenow={unfinished.question_index}
                aria-label="Interview progress"
              >
                <div className="h-full rounded-full bg-accent" style={{ width: `${progress}%` }} />
              </div>
              <p className="mt-3 text-xs text-ink-soft">
                {[started, remaining].filter(Boolean).join(" · ")}
              </p>
            </div>
            <button
              type="button"
              data-autofocus
              onClick={() => navigate(`/tracks/${track.id}/interview/${unfinished.id}`)}
              className="w-full rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Resume interview
            </button>
            <button
              type="button"
              onClick={() => choose("confirm-finish")}
              className="w-full rounded-md border border-line bg-white py-3 text-sm font-semibold text-accent-strong hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Finish and get feedback
            </button>
            <button
              type="button"
              onClick={() => choose("confirm-new")}
              className="w-full py-1 text-sm font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Start a new interview
            </button>
          </div>
        )}

        {phase === "confirm-finish" && (
          <div className="mt-5 space-y-4">
            <p className="text-sm leading-relaxed text-ink-soft">
              Your answered questions will be scored. Unanswered ones will not count against you.
            </p>
            <button
              type="button"
              data-autofocus
              disabled={requestBusy}
              onClick={() => void finish()}
              className="w-full rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Score my answers
            </button>
            <button
              type="button"
              onClick={() => choose("resume")}
              className="w-full text-sm font-semibold text-accent-strong underline-offset-2 hover:underline"
            >
              Back
            </button>
          </div>
        )}

        {phase === "confirm-new" && (
          <div className="mt-5 space-y-4">
            <p className="text-sm leading-relaxed text-ink-soft">
              Starting a new interview finishes this one first. Answered questions will be scored.
              Nothing is deleted.
            </p>
            <button
              type="button"
              data-autofocus
              onClick={() => choose("setup")}
              className="w-full rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Continue
            </button>
            <button
              type="button"
              onClick={() => choose("resume")}
              className="w-full text-sm font-semibold text-accent-strong underline-offset-2 hover:underline"
            >
              Back
            </button>
          </div>
        )}

        {phase === "setup" && (
          <div className="mt-5 space-y-5">
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                data-autofocus
                aria-pressed={mode === "strict"}
                onClick={() => setMode("strict")}
                className={`rounded-lg border p-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  mode === "strict"
                    ? "border-accent bg-accent-soft"
                    : "border-line bg-white hover:bg-page"
                }`}
              >
                <span className="block text-sm font-semibold text-ink">Strict</span>
                <span className="mt-1 block text-xs text-ink-soft">No hints, scored at the end</span>
              </button>
              <button
                type="button"
                aria-pressed={mode === "guided"}
                disabled={!guidedUnlocked}
                onClick={() => setMode("guided")}
                className={`rounded-lg border p-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60 ${
                  mode === "guided"
                    ? "border-accent bg-accent-soft"
                    : "border-line bg-white"
                }`}
              >
                <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  {!guidedUnlocked && (
                    <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true">
                      <path d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5Zm-3 8V7a3 3 0 1 1 6 0v3H9Z" />
                    </svg>
                  )}
                  Guided
                </span>
                <span className="mt-1 block text-xs text-ink-soft">
                  {guidedUnlocked
                    ? "Hints and coaching"
                    : "Guided unlocks after 3 strict interviews."}
                </span>
              </button>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                Interview duration
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {PRESETS.map((minutes) => (
                  <button
                    key={minutes}
                    type="button"
                    onClick={() => {
                      setUseCustom(false);
                      setCustom("");
                      setDuration(minutes);
                    }}
                    className={`rounded-md border px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                      !useCustom && duration === minutes
                        ? "border-accent bg-accent-soft text-accent-strong"
                        : "border-line text-ink-soft hover:bg-page"
                    }`}
                  >
                    {durationLabel(minutes)}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setUseCustom(true)}
                  className={`rounded-md border px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                    useCustom
                      ? "border-accent bg-accent-soft text-accent-strong"
                      : "border-line text-ink-soft hover:bg-page"
                  }`}
                >
                  Custom
                </button>
              </div>
              {useCustom && (
                <input
                  type="number"
                  min={15}
                  max={240}
                  inputMode="numeric"
                  aria-label="Custom duration in minutes"
                  placeholder="15–240"
                  value={custom}
                  onChange={(event) => setCustom(event.target.value)}
                  className="mt-2 w-28 rounded-md border border-line px-3 py-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                />
              )}
            </div>
            <button
              type="button"
              disabled={requestBusy || startMinutes == null}
              onClick={() => {
                setError(null);
                start.mutate();
              }}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {start.isPending && (
                <span className="h-4 w-4 motion-safe:animate-spin rounded-full border-2 border-white/40 border-t-white" />
              )}
              Start interview
            </button>
          </div>
        )}

        {error && (
          <div className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
            <p>{error}</p>
            <button
              type="button"
              onClick={tryAgain}
              className="mt-2 font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Try again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
