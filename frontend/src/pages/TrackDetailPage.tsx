import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, type BriefContent, type Progression, type Track } from "../lib/api";

type OpenSession = {
  id: string;
  mode: string;
  status: string;
  question_index: number;
  max_turns: number;
  answered_count: number;
};

const IMPORTANCE_STYLE: Record<string, string> = {
  core: "bg-indigo-100 text-indigo-700",
  important: "bg-sky-100 text-sky-700",
  nice_to_have: "bg-stone-100 text-stone-600",
};

export default function TrackDetailPage() {
  const { trackId } = useParams();
  const navigate = useNavigate();

  const data = useQuery({
    queryKey: ["track", trackId],
    queryFn: () =>
      api<{ track: Track; brief: { version: number; content: BriefContent } | null }>(
        `/tracks/${trackId}`,
      ),
  });

  const progression = useQuery({
    queryKey: ["progression", trackId],
    queryFn: () => api<Progression>(`/tracks/${trackId}/progression`),
  });

  const [duration, setDuration] = useState(60);
  const [customDuration, setCustomDuration] = useState("");
  const [hiddenSessionId, setHiddenSessionId] = useState<string | null>(null);
  const [showNewOptions, setShowNewOptions] = useState(false);
  const [choiceError, setChoiceError] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);

  const openSession = useQuery({
    queryKey: ["open-session", trackId],
    enabled: Boolean(trackId),
    retry: false,
    queryFn: () =>
      api<{ session: OpenSession | null }>(`/tracks/${trackId}/open-session`),
  });
  const unfinished = openSession.data?.session ?? null;
  const choiceOpen = Boolean(unfinished) && hiddenSessionId !== unfinished?.id;

  useEffect(() => {
    if (!choiceOpen) return;
    const root = dialogRef.current;
    if (!root) return;
    const focusable = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute("disabled"));
    focusable()[0]?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setHiddenSessionId(unfinished?.id ?? null);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
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
  }, [choiceOpen, showNewOptions, unfinished?.id]);

  const start = useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: "strict" | "guided" }) =>
      api<{ session: { id: string } }>(`/tracks/${id}/sessions`, {
        method: "POST",
        body: JSON.stringify({ mode, duration_minutes: duration }),
      }),
    onSuccess: (d, vars) =>
      navigate(`/tracks/${vars.id}/interview/${d.session.id}`),
  });

  const guidedUnlocked = progression.data?.guided_state === "UNLOCKED";

  function begin(mode: "strict" | "guided") {
    if (unfinished) {
      setShowNewOptions(false);
      setHiddenSessionId(null);
      return;
    }
    start.mutate({ id: trackId!, mode });
  }

  async function finishUnfinished() {
    if (!unfinished || !trackId) return;
    try {
      await api(`/sessions/${unfinished.id}/complete`, { method: "POST" });
      navigate(`/tracks/${trackId}/report/${unfinished.id}`);
    } catch (err) {
      setChoiceError(err instanceof Error ? err.message : "Could not finish");
    }
  }

  async function startFresh(mode: "strict" | "guided") {
    if (!trackId) return;
    try {
      if (unfinished) {
        await api(`/sessions/${unfinished.id}/complete`, { method: "POST" });
      }
      start.mutate({ id: trackId, mode });
    } catch (err) {
      setChoiceError(err instanceof Error ? err.message : "Could not start");
    }
  }

  if (data.isLoading) return <p className="text-stone-500">Loading…</p>;
  if (data.error instanceof Error)
    return <p className="text-red-600">{data.error.message}</p>;

  const { track, brief } = data.data!;
  const content = brief?.content;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-wide text-stone-400">
          {track.track_type.replace("_", " + ")}
        </p>
        <h1 className="text-xl font-semibold">{track.subject}</h1>
        {track.company && <p className="text-stone-500">{track.company}</p>}
      </div>

      {progression.data && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-stone-200 bg-white px-5 py-3 text-sm">
          <span className="text-stone-500">Progression:</span>
          <span>
            {progression.data.strict_completed} strict
            {progression.data.strict_completed === 1 ? "" : "s"} completed
          </span>
          {progression.data.guided_state === "UNLOCKED" ? (
            <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
              Guided mode unlocked 🎉
            </span>
          ) : (
            <span className="rounded-md bg-stone-100 px-2 py-0.5 text-xs text-stone-500">
              Guided locked (3 strict attempts needed)
            </span>
          )}
        </div>
      )}

      {content ? (
        <div className="space-y-5">
          <section className="rounded-2xl border border-stone-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-stone-500">
              Interview Brief · v{brief!.version}
            </h2>
            {content.clarification_message && (
              <p className="mt-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-950">
                {content.clarification_message}
              </p>
            )}
            <p className="mt-2 text-sm leading-relaxed">{content.summary}</p>
            {content.candidate_angle_notes && (
              <p className="mt-3 rounded-xl bg-indigo-50 p-3 text-sm text-indigo-900">
                <span className="font-medium">Your angle: </span>
                {content.candidate_angle_notes}
              </p>
            )}
          </section>

          <div className="grid gap-5 md:grid-cols-2">
            <section className="rounded-2xl border border-stone-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-stone-500">Competencies</h2>
              <div className="mt-3 space-y-2">
                {content.competencies.map((c) => (
                  <div key={c.name} className="text-sm">
                    <span
                      className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                        IMPORTANCE_STYLE[c.importance] ?? IMPORTANCE_STYLE.nice_to_have
                      }`}
                    >
                      {c.importance.replace("_", " ")}
                    </span>{" "}
                    {c.name}
                    <p className="ml-0.5 text-xs text-stone-500">{c.description}</p>
                  </div>
                ))}
              </div>
            </section>
            <section className="rounded-2xl border border-stone-200 bg-white p-5">
              <h2 className="text-sm font-semibold text-stone-500">Question areas</h2>
              <ul className="mt-3 space-y-2 text-sm">
                {content.question_areas.map((qa) => (
                  <li key={qa.topic}>
                    <span className="font-medium">{qa.topic}</span>
                    <span className="text-stone-500"> — {qa.guidance}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {content.question_bank?.length > 0 && (
            <details className="rounded-2xl border border-stone-200 bg-white p-5">
              <summary className="cursor-pointer text-sm font-semibold text-stone-700">
                Question bank ({content.question_bank.length} pre-validated questions)
              </summary>
              <div className="mt-3 space-y-3">
                {content.question_bank.map((q, i) => (
                  <div key={i} className="rounded-xl border border-stone-100 p-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="rounded-md bg-stone-100 px-1.5 py-0.5 font-medium text-stone-600">
                        {q.area}
                      </span>
                      <span
                        className={`rounded-md px-1.5 py-0.5 font-medium ${
                          q.difficulty === "advanced"
                            ? "bg-rose-100 text-rose-700"
                            : q.difficulty === "foundational"
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {q.difficulty}
                      </span>
                      <span className="rounded-md bg-violet-100 px-1.5 py-0.5 font-medium text-violet-700">
                        {q.type}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm">{q.question}</p>
                  </div>
                ))}
              </div>
            </details>
          )}

          <section className="rounded-2xl border border-stone-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-stone-500">Preparation plan</h2>
            <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm">
              {content.preparation_plan.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ol>
          </section>
        </div>
      ) : (
        <p className="text-sm text-stone-400">No Interview Brief yet.</p>
      )}

      {start.error instanceof Error && (
        <p className="text-sm text-red-600">{start.error.message}</p>
      )}
      <div className="rounded-2xl border border-stone-200 bg-white p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
          Interview duration
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {[30, 45, 60, 90, 120, 180].map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setDuration(m);
                setCustomDuration("");
              }}
              className={`rounded-xl border px-3 py-2 text-sm font-medium ${
                duration === m
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                  : "border-stone-200 text-stone-600 hover:bg-stone-50"
              }`}
            >
              {m >= 60 ? `${m / 60} hr${m > 60 ? "s" : ""}` : `${m} min`}
            </button>
          ))}
          <input
            type="number"
            min={15}
            max={240}
            placeholder="Custom"
            value={customDuration}
            onChange={(e) => {
              setCustomDuration(e.target.value);
              const v = parseInt(e.target.value, 10);
              if (!Number.isNaN(v) && v >= 15 && v <= 240) setDuration(v);
            }}
            className={`w-24 rounded-xl border px-3 py-2 text-sm ${
              duration === parseInt(customDuration, 10) && customDuration !== ""
                ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                : "border-stone-200 text-stone-600"
            }`}
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <button
          onClick={() => begin("strict")}
          disabled={start.isPending}
          className="rounded-2xl bg-indigo-600 py-3 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {start.isPending
            ? "Preparing…"
            : "Start strict interview"}
        </button>
        <button
          onClick={() => begin("guided")}
          disabled={start.isPending || !guidedUnlocked}
          title={
            guidedUnlocked
              ? "Start a guided interview with optional assistance"
              : "Guided mode unlocks after progression policy criteria are met"
          }
          className="rounded-2xl border border-stone-300 bg-white py-3 font-medium text-stone-800 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {guidedUnlocked ? "Start guided interview" : "Guided locked"}
        </button>
      </div>
      {unfinished && !choiceOpen && (
        <button
          type="button"
          onClick={() => setHiddenSessionId(null)}
          className="text-sm font-medium text-indigo-700 underline"
        >
          Unfinished interview: Q{unfinished.question_index}/{unfinished.max_turns} (
          {unfinished.mode})
        </button>
      )}
      {choiceOpen && unfinished && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-stone-900/40 p-4 sm:items-center">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="start-choice-title"
            className="w-full max-w-md rounded-2xl border border-indigo-100 bg-white p-5 shadow-xl"
          >
            <h2 id="start-choice-title" className="text-base font-semibold text-stone-900">
              Unfinished interview: Q{unfinished.question_index}/{unfinished.max_turns} (
              {unfinished.mode})
            </h2>
            {choiceError && <p className="mt-2 text-sm text-red-600">{choiceError}</p>}
            <div className="mt-4 flex flex-col gap-2">
              <button
                type="button"
                onClick={() =>
                  navigate(`/tracks/${trackId}/interview/${unfinished.id}`)
                }
                className="rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Resume
              </button>
              <button
                type="button"
                onClick={() => void finishUnfinished()}
                className="rounded-xl border border-indigo-200 bg-white px-3 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-50"
              >
                Finish and get feedback
              </button>
              <button
                type="button"
                onClick={() => setShowNewOptions(true)}
                className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-800 hover:bg-stone-50"
              >
                Start a new interview
              </button>
            </div>
            {showNewOptions && (
              <div className="mt-4 space-y-3 border-t border-indigo-100 pt-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Interview duration
                </p>
                <div className="flex flex-wrap gap-2">
                  {[30, 45, 60, 90, 120, 180].map((m) => (
                    <button
                      key={`new-${m}`}
                      type="button"
                      onClick={() => {
                        setDuration(m);
                        setCustomDuration("");
                      }}
                      className={`rounded-xl border px-3 py-2 text-sm font-medium ${
                        duration === m
                          ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-stone-200 text-stone-600"
                      }`}
                    >
                      {m >= 60 ? `${m / 60} hr${m > 60 ? "s" : ""}` : `${m} min`}
                    </button>
                  ))}
                </div>
                <div className="grid gap-2">
                  <button
                    type="button"
                    onClick={() => void startFresh("strict")}
                    disabled={start.isPending}
                    className="rounded-xl bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                  >
                    Start strict interview
                  </button>
                  <button
                    type="button"
                    onClick={() => void startFresh("guided")}
                    disabled={start.isPending || !guidedUnlocked}
                    className="rounded-xl border border-stone-300 py-2 text-sm font-medium text-stone-800 disabled:opacity-40"
                  >
                    {guidedUnlocked ? "Start guided interview" : "Guided locked"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
