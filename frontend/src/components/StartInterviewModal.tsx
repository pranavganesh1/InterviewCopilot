import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  api,
  type OpenSession,
  type Progression,
  type TrackWeaknesses,
  type VaultItem,
} from "../lib/api";
import {
  PERSONA_OPTIONS,
  readStoredPersonaId,
  storePersonaId,
  type PersonaId,
} from "../lib/personas";

const PRESETS = [30, 45, 60, 90, 120, 180];

type Mode = "strict" | "guided";
type Phase =
  | "loading"
  | "resume"
  | "confirm-finish"
  | "confirm-new"
  | "confirm-close-empty"
  | "setup";

export type StartTrack = { id: string; subject: string };

type OpenSessionPayload = {
  session: OpenSession | null;
  sessions?: OpenSession[];
};

function sessionSummary(row: OpenSession): string {
  const q = `Q${row.question_index}/${row.max_turns}`;
  const answered = `${row.answered_count} answered`;
  const mode = row.mode === "guided" ? "guided" : "strict";
  return `${q} · ${answered} · ${mode}`;
}

function friendly(err: unknown): string {
  if (err instanceof ApiError) {
    const cause = (err.causeCode || "").toLowerCase();
    const wait =
      typeof err.retryAfterSeconds === "number" && err.retryAfterSeconds > 0
        ? Math.min(90, Math.ceil(err.retryAfterSeconds))
        : undefined;
    if (cause === "rate_limited") {
      return wait
        ? `Temporary request limit reached. Retry in about ${wait}s.`
        : "Temporary request limit reached. Wait a moment and try again.";
    }
    if (cause === "overloaded") {
      return "Temporary service overload. Wait a moment and try again.";
    }
    if (cause === "schema_rejected") {
      return "Interview preparation got an invalid AI response. Keep your settings and try again.";
    }
    if (cause === "timeout") {
      return "Starting the interview took too long. Keep your settings and try again.";
    }
    if (cause === "auth_failed") {
      return "AI provider authentication failed. Check server configuration.";
    }
    if (cause === "network") {
      return "Could not reach the AI provider. Check your connection and retry.";
    }
    if (err.status === 503) {
      if (/rate|quota|busy|overload/i.test(err.message || "")) {
        return "The interview model is busy right now. Wait a moment and try again.";
      }
      return (
        err.message ||
        "Could not start the interview. Keep your settings and try again."
      );
    }
    if (err.message) return err.message;
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
  initialFocusWeak = false,
  initialUseResume = false,
  claimSeeds = [],
}: {
  track: StartTrack | null;
  onClose: () => void;
  initialFocusWeak?: boolean;
  initialUseResume?: boolean;
  claimSeeds?: { vault_item_id?: string; claim: string; excerpt?: string; title?: string }[];
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
  const [useResume, setUseResume] = useState(false);
  const [focusWeak, setFocusWeak] = useState(initialFocusWeak);
  const [personaId, setPersonaId] = useState<PersonaId>(() => readStoredPersonaId());
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<"start" | "finish" | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [finishId, setFinishId] = useState<string | null>(null);
  const [olderOpen, setOlderOpen] = useState(false);
  const [starting, setStarting] = useState(false);
  const startLock = useRef(false);

  const openSession = useQuery({
    queryKey: ["open-session", track?.id],
    enabled: Boolean(track),
    retry: false,
    queryFn: () => api<OpenSessionPayload>(`/tracks/${track!.id}/open-session`),
  });
  const progression = useQuery({
    queryKey: ["progression", track?.id],
    enabled: Boolean(track),
    retry: false,
    queryFn: () => api<Progression>(`/tracks/${track!.id}/progression`),
  });
  const vault = useQuery({
    queryKey: ["vault-items"],
    enabled: Boolean(track),
    retry: false,
    queryFn: () => api<VaultItem[]>("/vault/items"),
  });
  const weaknesses = useQuery({
    queryKey: ["weaknesses", track?.id],
    enabled: Boolean(track),
    retry: false,
    queryFn: () => api<TrackWeaknesses>(`/tracks/${track!.id}/weaknesses`),
  });

  const openSessions =
    openSession.data?.sessions ??
    (openSession.data?.session ? [openSession.data.session] : []);
  const unfinished = openSessions[0] ?? openSession.data?.session ?? null;
  const olderSessions = openSessions.slice(1);
  const emptyCount = openSessions.filter((row) => row.answered_count === 0).length;
  const guidedUnlocked = progression.data?.guided_state === "UNLOCKED";
  const vaultReady = (vault.data ?? []).some((item) =>
    ["project", "skill", "internship"].includes((item.category || "").toLowerCase()),
  );
  const weakReady = Boolean(weaknesses.data?.has_data && (weaknesses.data.weak?.length ?? 0) > 0);

  useEffect(() => {
    if (!track) return;
    if (vault.isSuccess) {
      setUseResume(initialUseResume || vaultReady || claimSeeds.length > 0);
    }
  }, [track, vault.isSuccess, vaultReady, initialUseResume, claimSeeds.length]);

  useEffect(() => {
    if (initialFocusWeak && weakReady) setFocusWeak(true);
  }, [initialFocusWeak, weakReady]);

  useEffect(() => {
    if (initialUseResume || claimSeeds.length > 0) setUseResume(true);
  }, [initialUseResume, claimSeeds.length]);

  useEffect(() => {
    setOlderOpen(false);
    setFinishId(null);
    startLock.current = false;
    setStarting(false);
  }, [track?.id]);

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
      storePersonaId(personaId);
      return api<{ session: { id: string } }>(`/tracks/${track.id}/sessions`, {
        method: "POST",
        body: JSON.stringify({
          mode,
          duration_minutes: startMinutes,
          use_resume: useResume,
          focus_weak: focusWeak,
          persona_id: personaId,
          claim_seeds: useResume ? claimSeeds.slice(0, 24) : [],
        }),
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
    onSettled: () => {
      startLock.current = false;
      setStarting(false);
    },
  });

  const closeEmpty = useMutation({
    mutationFn: async () => {
      if (!track) throw new Error("No track selected.");
      return api<{ closed_count: number; session_ids: string[] }>(
        `/tracks/${track.id}/close-empty-sessions`,
        { method: "POST" },
      );
    },
    onSuccess: async () => {
      setChoice(null);
      setOlderOpen(false);
      await openSession.refetch();
    },
    onError: (err) => {
      setError(friendly(err));
    },
  });

  const requestBusy = finishing || start.isPending || starting || closeEmpty.isPending;

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
      setFocusWeak(initialFocusWeak);
      setPersonaId(readStoredPersonaId());
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
  }, [track, phase, requestBusy, onClose, initialFocusWeak]);

  if (!track) return null;

  function choose(next: Phase) {
    setError(null);
    setChoice({ trackId: track!.id, phase: next });
  }

  function close() {
    onClose();
    returnTo.current?.focus();
  }

  async function finish(sessionId?: string) {
    const id = sessionId ?? finishId ?? unfinished?.id;
    if (!id) return;
    setFinishing(true);
    setError(null);
    try {
      await api(`/sessions/${id}/complete`, { method: "POST" });
      navigate(`/tracks/${track!.id}/report/${id}`);
    } catch (err) {
      setRetry("finish");
      setError(friendly(err));
    } finally {
      setFinishing(false);
    }
  }

  function tryAgain() {
    if (retry === "finish") void finish();
    else {
      if (startLock.current) return;
      startLock.current = true;
      setStarting(true);
      start.mutate();
    }
  }

  function requestStart() {
    if (requestBusy || startMinutes == null || startLock.current) return;
    startLock.current = true;
    setStarting(true);
    setError(null);
    start.mutate();
  }

  const started = startedLabel(unfinished?.created_at);
  const remaining = remainingLabel(unfinished?.created_at, unfinished?.duration_minutes);
  const progress =
    unfinished && unfinished.max_turns > 0
      ? Math.min(100, Math.round((unfinished.question_index / unfinished.max_turns) * 100))
      : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center overflow-x-hidden bg-stone-900/40 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !requestBusy) close();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="start-interview-title"
        className="start-modal-panel flex max-h-[85vh] w-full max-w-[480px] flex-col overflow-x-hidden rounded-t-2xl bg-white shadow-xl sm:rounded-lg"
      >
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-line/70 px-5 pb-3 pt-5">
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

        <div className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-5 py-4 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        {phase === "loading" && (
          <div className="space-y-3" aria-busy="true" aria-label="Checking this track">
            <div className="h-4 w-2/3 animate-pulse rounded bg-stone-100" />
            <div className="h-24 animate-pulse rounded-lg bg-stone-100" />
            <div className="h-10 animate-pulse rounded-md bg-stone-100" />
            <div className="h-10 animate-pulse rounded-md bg-stone-100" />
          </div>
        )}

        {phase === "resume" && unfinished && (
          <div className="space-y-4">
            <div className="rounded-lg border border-line bg-accent-soft/60 p-4">
              <p className="text-sm font-semibold text-ink">Unfinished interview</p>
              <p className="mt-1 text-sm text-ink-soft">
                Question {unfinished.question_index} of {unfinished.max_turns}
              </p>
              <p className="mt-1 text-xs text-ink-soft">{sessionSummary(unfinished)}</p>
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
              onClick={() => {
                setFinishId(unfinished.id);
                choose("confirm-finish");
              }}
              className="w-full rounded-md border border-line bg-white py-3 text-sm font-semibold text-accent-strong hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Finish and get feedback
            </button>

            {olderSessions.length > 0 && (
              <div className="rounded-lg border border-line">
                <button
                  type="button"
                  aria-expanded={olderOpen}
                  onClick={() => setOlderOpen((v) => !v)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-semibold text-accent-strong hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                >
                  <span>
                    {olderSessions.length} older unfinished interview
                    {olderSessions.length === 1 ? "" : "s"}
                  </span>
                  <span aria-hidden="true">{olderOpen ? "▾" : "▸"}</span>
                </button>
                {olderOpen && (
                  <ul className="max-h-40 space-y-2 overflow-y-auto border-t border-line p-2">
                    {olderSessions.map((row) => (
                      <li
                        key={row.id}
                        className="rounded-md border border-line/80 bg-page/50 p-2.5"
                      >
                        <p className="text-xs text-ink-soft">{sessionSummary(row)}</p>
                        <p className="mt-0.5 text-[11px] text-ink-faint">
                          {startedLabel(row.created_at) ?? "Started earlier"}
                        </p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              navigate(`/tracks/${track.id}/interview/${row.id}`)
                            }
                            className="rounded-md bg-accent px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong"
                          >
                            Resume
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setFinishId(row.id);
                              choose("confirm-finish");
                            }}
                            className="rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-semibold text-accent-strong hover:bg-accent-soft"
                          >
                            Finish and get feedback
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {emptyCount > 1 && (
              <button
                type="button"
                onClick={() => choose("confirm-close-empty")}
                className="w-full rounded-md border border-amber-200 bg-amber-50 py-2.5 text-sm font-semibold text-amber-900 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Close empty interviews
              </button>
            )}

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
          <div className="space-y-4">
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

        {phase === "confirm-close-empty" && (
          <div className="space-y-4">
            <p className="text-sm leading-relaxed text-ink-soft">
              Close interviews with no answers on this track? Nothing is deleted — they are
              only marked closed so they stop cluttering this list.
            </p>
            <button
              type="button"
              data-autofocus
              disabled={requestBusy}
              onClick={() => closeEmpty.mutate()}
              className="w-full rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {closeEmpty.isPending ? "Closing…" : "Close empty interviews"}
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
          <div className="space-y-4">
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

        {phase === "setup" && openSessions.length === 0 && !openSession.isLoading && (
          <p className="mb-4 text-sm text-ink-soft">No unfinished interview on this track.</p>
        )}

        {phase === "setup" && (
          <div className="space-y-5">
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
              <p
                id="persona-label"
                className="text-xs font-semibold uppercase tracking-wide text-ink-soft"
              >
                Choose your interviewer
              </p>
              <div
                role="radiogroup"
                aria-labelledby="persona-label"
                className="mt-2 flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] sm:grid sm:grid-cols-2 sm:overflow-visible [&::-webkit-scrollbar]:hidden"
              >
                {PERSONA_OPTIONS.map((persona, index) => {
                  const selected = personaId === persona.id;
                  return (
                    <button
                      key={persona.id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      data-persona-id={persona.id}
                      disabled={requestBusy}
                      tabIndex={selected ? 0 : -1}
                      onClick={() => setPersonaId(persona.id)}
                      onKeyDown={(event) => {
                        const move =
                          event.key === "ArrowRight" || event.key === "ArrowDown"
                            ? 1
                            : event.key === "ArrowLeft" || event.key === "ArrowUp"
                              ? -1
                              : 0;
                        if (event.key === " " || event.key === "Enter") {
                          event.preventDefault();
                          setPersonaId(persona.id);
                          return;
                        }
                        if (!move) return;
                        event.preventDefault();
                        const next =
                          PERSONA_OPTIONS[
                            (index + move + PERSONA_OPTIONS.length) % PERSONA_OPTIONS.length
                          ];
                        setPersonaId(next.id);
                        requestAnimationFrame(() => {
                          panelRef.current
                            ?.querySelector<HTMLElement>(`[data-persona-id="${next.id}"]`)
                            ?.focus();
                        });
                      }}
                      className={`min-w-[12.5rem] shrink-0 snap-start rounded-lg border p-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-60 sm:min-w-0 ${
                        selected
                          ? "border-accent bg-accent-soft"
                          : "border-line bg-white hover:bg-page"
                      }`}
                    >
                      <span className="flex items-start gap-2.5">
                        <span
                          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
                          style={{ backgroundColor: persona.accent }}
                          aria-hidden="true"
                        >
                          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                            <circle cx="12" cy="8" r="3.2" />
                            <path d="M5 19c0-3.4 3-5.5 7-5.5s7 2.1 7 5.5" />
                          </svg>
                          <span className="sr-only">{persona.initials}</span>
                        </span>
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-ink">
                            {persona.name}
                          </span>
                          <span className="mt-0.5 block text-xs text-ink-soft">
                            {persona.description}
                          </span>
                          <span className="mt-1.5 flex flex-wrap gap-1">
                            {persona.tags.map((tag) => (
                              <span
                                key={tag}
                                className="rounded bg-white/80 px-1.5 py-0.5 text-[10px] font-medium text-accent-strong ring-1 ring-accent/20"
                              >
                                {tag}
                              </span>
                            ))}
                          </span>
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="space-y-3 rounded-lg border border-line bg-page/60 p-3">
              <label className="flex items-start gap-2.5 text-sm text-ink">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={useResume}
                  disabled={!vaultReady || requestBusy}
                  onChange={(e) => setUseResume(e.target.checked)}
                />
                <span>
                  <span className="font-semibold">Use my resume and projects</span>
                  <span className="mt-0.5 block text-xs text-ink-soft">
                    {vaultReady
                      ? "Ask Socratic questions about your vault projects and skills."
                      : "Add a project or skill in onboarding to enable this."}
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2.5 text-sm text-ink">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={focusWeak}
                  disabled={!weakReady || requestBusy}
                  onChange={(e) => setFocusWeak(e.target.checked)}
                />
                <span>
                  <span className="font-semibold">Focus on weak areas</span>
                  <span className="mt-0.5 block text-xs text-ink-soft">
                    {weakReady
                      ? "About 30% of questions re-test concepts you struggled with."
                      : "Complete an interview first to unlock weakness focus."}
                  </span>
                </span>
              </label>
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
              onClick={requestStart}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-accent py-3 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              {(start.isPending || starting) && (
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
    </div>
  );
}
