import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { api, type BriefContent, type Progression, type Track } from "../lib/api";

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

  const start = useMutation({
    mutationFn: (id: string) =>
      api<{ session: { id: string } }>(`/tracks/${id}/sessions`, {
        method: "POST",
        body: JSON.stringify({ mode: "strict" }),
      }),
    onSuccess: (d, id) => navigate(`/tracks/${id}/interview/${d.session.id}`),
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
      <button
        onClick={() => start.mutate(trackId!)}
        disabled={start.isPending}
        className="w-full rounded-2xl bg-indigo-600 py-3 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {start.isPending
          ? "Interviewer is preparing your first question…"
          : "Start strict interview"}
      </button>
    </div>
  );
}
