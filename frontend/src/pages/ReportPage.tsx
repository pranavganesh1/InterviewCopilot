import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Report } from "../lib/api";

const LEVEL_STYLE: Record<string, string> = {
  strong: "bg-emerald-100 text-emerald-700",
  solid: "bg-emerald-100 text-emerald-700",
  developing: "bg-amber-100 text-amber-700",
  weak: "bg-red-100 text-red-700",
};

const COVERAGE_STYLE: Record<string, string> = {
  excellent: "bg-emerald-100 text-emerald-700",
  good: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  none: "bg-red-100 text-red-700",
};

export default function ReportPage() {
  const { trackId, sessionId } = useParams();

  const report = useQuery({
    queryKey: ["report", sessionId],
    queryFn: () => api<Report>(`/sessions/${sessionId}/report`),
    refetchInterval: (q) => (q.state.error ? 5000 : false),
    retry: 2,
  });

  if (report.isLoading) return <p className="text-stone-500">Loading report…</p>;
  if (report.error instanceof Error)
    return (
      <div className="rounded-2xl border border-stone-200 bg-white p-6 text-center">
        <p className="text-sm text-stone-500">{report.error.message}</p>
        <Link
          to={`/tracks/${trackId}`}
          className="mt-3 inline-block text-sm text-indigo-600 hover:underline"
        >
          ← Back to track
        </Link>
      </div>
    );

  const c = report.data!.content;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Feedback report</h1>
        <Link
          to={`/tracks/${trackId}`}
          className="text-sm text-indigo-600 hover:underline"
        >
          ← Back to track
        </Link>
      </div>

      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`rounded-md px-2 py-0.5 font-medium ${
              COVERAGE_STYLE[c.coverage_status.toLowerCase()] ?? "bg-stone-100"
            }`}
          >
            {c.coverage_status}
          </span>
          <span className="text-stone-400">{c.session_mode} interview</span>
        </div>
        <p className="mt-3 text-sm leading-relaxed">{c.summary_overview}</p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-stone-500">Competencies</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {c.competency_assessments.map((comp) => (
            <div
              key={comp.competency_name}
              className="rounded-2xl border border-stone-200 bg-white p-4"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{comp.competency_name}</span>
                {comp.level ? (
                  <span
                    className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      LEVEL_STYLE[comp.level] ?? "bg-stone-100"
                    }`}
                  >
                    {comp.level}
                  </span>
                ) : (
                  <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500">
                    {comp.assessment_status.toLowerCase().replace("_", " ")}
                  </span>
                )}
              </div>
              {comp.observation && (
                <p className="mt-2 text-xs leading-relaxed text-stone-500">
                  {comp.observation}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        <section className="rounded-2xl border border-stone-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-stone-500">Strengths</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {c.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
        <section className="rounded-2xl border border-stone-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-stone-500">Improve these</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {c.improvement_areas.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-2xl border border-indigo-200 bg-indigo-50 p-5">
        <h2 className="text-sm font-semibold text-indigo-900">
          Your improvement plan
        </h2>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-indigo-900">
          {c.recommendations.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">
          Question-by-question evidence
        </h2>
        <div className="mt-3 space-y-3">
          {c.question_assessments.map((qa) => (
            <details key={qa.turn_index} className="rounded-xl border border-stone-100 p-3">
              <summary className="cursor-pointer text-sm">
                <span
                  className={`mr-2 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                    COVERAGE_STYLE[qa.coverage] ?? "bg-stone-100"
                  }`}
                >
                  {qa.coverage}
                </span>
                Q{qa.turn_index}: {qa.observation}
              </summary>
              {qa.evidence_excerpt && (
                <p className="mt-2 rounded-lg bg-stone-50 p-2 text-xs italic text-stone-600">
                  “{qa.evidence_excerpt}”
                </p>
              )}
            </details>
          ))}
        </div>
      </section>

      {c.unassessed_topics.length > 0 && (
        <p className="text-xs text-stone-400">
          Not assessed in this session (never probed):{" "}
          {c.unassessed_topics.join(", ")}
        </p>
      )}
    </div>
  );
}
