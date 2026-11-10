import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import StartInterviewModal from "../components/StartInterviewModal";
import {
  api,
  type BriefContent,
  type Progression,
  type Track,
  type TrackWeaknesses,
} from "../lib/api";

const IMPORTANCE_STYLE: Record<string, string> = {
  core: "bg-accent-soft text-accent-strong",
  important: "bg-sky-100 text-sky-700",
  nice_to_have: "bg-stone-100 text-stone-600",
};

export default function TrackDetailPage() {
  const { trackId } = useParams();
  const [startOpen, setStartOpen] = useState(false);

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

  const weaknesses = useQuery({
    queryKey: ["weaknesses", trackId],
    queryFn: () => api<TrackWeaknesses>(`/tracks/${trackId}/weaknesses`),
    retry: false,
  });

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
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-stone-200 bg-white px-5 py-3 text-sm">
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

      <section className="rounded-lg border border-line bg-white p-5">
        <h2 className="text-sm font-semibold text-ink">Weak areas</h2>
        {weaknesses.isLoading ? (
          <p className="mt-2 text-sm text-ink-faint">Loading…</p>
        ) : weaknesses.isError ? (
          <p className="mt-2 text-sm text-ink-faint">Could not load weakness data.</p>
        ) : !weaknesses.data?.has_data || (weaknesses.data.top_weak?.length ?? 0) === 0 ? (
          <p className="mt-2 text-sm text-ink-faint">
            Complete interviews with answered questions to see weak areas.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {weaknesses.data.top_weak.map((row) => (
              <li
                key={row.concept}
                className="flex min-w-0 items-center justify-between gap-2 text-sm"
              >
                <span className="truncate font-medium text-ink" title={row.concept}>
                  {row.concept}
                </span>
                <span className="shrink-0 rounded-md bg-violet-50 px-2 py-0.5 text-[11px] font-semibold uppercase text-violet-700">
                  {row.status}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {content ? (
        <div className="space-y-5">
          <section className="rounded-lg border border-stone-200 bg-white p-5">
            <h2 className="text-sm font-semibold text-stone-500">
              Interview Brief · v{brief!.version}
            </h2>
            {content.clarification_message && (
              <p className="mt-2 rounded-md bg-amber-50 p-3 text-sm text-amber-950">
                {content.clarification_message}
              </p>
            )}
            <p className="mt-2 text-sm leading-relaxed">{content.summary}</p>
            {content.candidate_angle_notes && (
              <p className="mt-3 rounded-md bg-accent-soft p-3 text-sm text-ink">
                <span className="font-medium">Your angle: </span>
                {content.candidate_angle_notes}
              </p>
            )}
          </section>

          <div className="grid gap-5 md:grid-cols-2">
            <section className="rounded-lg border border-stone-200 bg-white p-5">
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
            <section className="rounded-lg border border-stone-200 bg-white p-5">
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
            <details className="rounded-lg border border-stone-200 bg-white p-5">
              <summary className="cursor-pointer text-sm font-semibold text-stone-700">
                Question bank ({content.question_bank.length} pre-validated questions)
              </summary>
              <div className="mt-3 space-y-3">
                {content.question_bank.map((q, i) => (
                  <div key={i} className="rounded-md border border-stone-100 p-3">
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
                      <span className="rounded-md bg-stone-100 px-1.5 py-0.5 font-medium text-stone-600">
                        {q.type}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm">{q.question}</p>
                  </div>
                ))}
              </div>
            </details>
          )}

          <section className="rounded-lg border border-stone-200 bg-white p-5">
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

      <button
        type="button"
        onClick={() => setStartOpen(true)}
        className="w-full rounded-lg bg-accent py-3 font-medium text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:w-auto sm:px-6"
      >
        Start interview
      </button>
      <StartInterviewModal
        track={startOpen ? { id: track.id, subject: track.subject } : null}
        onClose={() => setStartOpen(false)}
      />
    </div>
  );
}
