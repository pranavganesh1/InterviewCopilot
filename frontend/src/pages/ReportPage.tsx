import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api, type Report } from "../lib/api";
import { AI_REVIEWED_NOT_EXECUTED } from "../lib/codingReview";
import {
  deriveReportViewState,
  nextReportPollInterval,
} from "../lib/feedbackStatus";
import { COVERAGE_STYLE, LEVEL_STYLE } from "../lib/ui";

function StatusShell({
  state,
  title,
  detail,
  tone,
  children,
}: {
  state: string;
  title: string;
  detail: string;
  tone: "neutral" | "progress" | "danger";
  children?: ReactNode;
}) {
  const toneClass =
    tone === "danger"
      ? "border-rose-200 from-rose-50 to-white"
      : tone === "progress"
        ? "border-indigo-200 from-indigo-50 to-white"
        : "border-stone-200 from-stone-50 to-white";

  return (
    <div
      className={`mx-auto max-w-lg rounded-2xl border bg-gradient-to-br p-8 text-center shadow-sm ${toneClass}`}
      data-testid="report-status"
      data-state={state}
    >
      {tone === "progress" && (
        <div
          className="mx-auto mb-4 h-1.5 w-24 overflow-hidden rounded-full bg-indigo-100"
          aria-hidden
        >
          <div className="h-full w-1/2 animate-pulse rounded-full bg-indigo-500" />
        </div>
      )}
      <p className="text-base font-semibold text-stone-900">{title}</p>
      <p className="mt-2 text-sm leading-relaxed text-stone-600">{detail}</p>
      {children}
    </div>
  );
}

export default function ReportPage() {
  const { trackId, sessionId } = useParams();
  const [pollsSoFar, setPollsSoFar] = useState(0);

  const report = useQuery({
    queryKey: ["report", sessionId],
    queryFn: async () => {
      try {
        return await api<Report>(`/sessions/${sessionId}/report`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setPollsSoFar((n) => n + 1);
        }
        throw err;
      }
    },
    refetchInterval: (q) => {
      const err = q.state.error;
      const status = err instanceof ApiError ? err.status : undefined;
      return nextReportPollInterval({
        hasData: !!q.state.data,
        errorStatus: status,
        pollsSoFar,
      });
    },
    retry: false,
  });

  const errorStatus =
    report.error instanceof ApiError ? report.error.status : undefined;
  const view = deriveReportViewState({
    hasData: !!report.data,
    isLoading: report.isLoading,
    isFetching: report.isFetching,
    errorStatus,
    pollsSoFar,
  });

  if (view === "loading" || view === "pending" || view === "generating") {
    const title =
      view === "generating"
        ? "Generating feedback…"
        : view === "pending"
          ? "Feedback pending"
          : "Loading report…";
    const detail =
      view === "generating"
        ? "Your interview is complete. We are building the evidence-based report now."
        : view === "pending"
          ? "Your interview is complete. Feedback has not been generated yet."
          : "Checking whether your report is ready…";
    return (
      <StatusShell state={view} title={title} detail={detail} tone="progress">
        <Link
          to={`/tracks/${trackId}`}
          className="mt-5 inline-block text-sm font-medium text-indigo-600 hover:underline"
        >
          ← Back to track
        </Link>
      </StatusShell>
    );
  }

  if (view === "failed") {
    const message =
      report.error instanceof Error
        ? report.error.message
        : "Feedback generation failed or timed out.";
    return (
      <StatusShell
        state="failed"
        title="Feedback generation failed"
        detail={message}
        tone="danger"
      >
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={() => {
              setPollsSoFar(0);
              report.refetch();
            }}
            className="rounded-xl bg-rose-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-800"
          >
            Retry
          </button>
          <Link
            to={`/tracks/${trackId}`}
            className="text-sm font-medium text-indigo-600 hover:underline"
          >
            ← Back to track
          </Link>
        </div>
      </StatusShell>
    );
  }

  const data = report.data!;
  const c = data.content;
  const maxTurns = data.max_turns ?? 15;
  const attempted =
    data.questions_attempted ?? c.question_assessments?.length ?? 0;
  const score = data.overall_score;
  const level = data.performance_level ?? "Not assessed";

  return (
    <div className="space-y-5" data-testid="report-status" data-state="ready">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-indigo-600">
            Feedback ready
          </p>
          <h1 className="text-xl font-semibold tracking-tight">Feedback report</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/profile"
            className="rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-800 hover:bg-indigo-100"
          >
            Profile dashboard
          </Link>
          <Link
            to={`/tracks/${trackId}`}
            className="rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50"
          >
            ← Back to track
          </Link>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4 text-center shadow-sm">
          <p className="text-[11px] font-medium uppercase tracking-wide text-indigo-600">
            Overall score
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-indigo-950">
            {score != null ? `${score}%` : "—"}
          </p>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4 text-center shadow-sm">
          <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
            Questions answered
          </p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-stone-900">
            {attempted}
            <span className="text-sm font-medium text-stone-400">/{maxTurns}</span>
          </p>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4 text-center shadow-sm">
          <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
            Performance level
          </p>
          <p className="mt-1 text-lg font-semibold text-stone-900">{level}</p>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4 text-center shadow-sm">
          <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
            Coverage
          </p>
          <p className="mt-1 text-lg font-semibold text-stone-900">
            {c.coverage_status}
          </p>
        </div>
      </div>

      <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-stone-600">AI assessment summary</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`rounded-md px-2 py-0.5 font-medium ${
              COVERAGE_STYLE[c.coverage_status.toLowerCase()] ?? "bg-stone-100"
            }`}
          >
            {c.coverage_status}
          </span>
          <span className="text-stone-400">{c.session_mode} interview</span>
          {(c.coding_review_note ||
            c.question_assessments.some((q) => q.executed === false)) && (
            <span
              className="rounded-md bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-800"
              data-testid="ai-reviewed-badge"
            >
              {c.coding_review_note || AI_REVIEWED_NOT_EXECUTED}
            </span>
          )}
        </div>
        <p className="mt-3 text-sm leading-relaxed text-stone-800">
          {c.summary_overview}
        </p>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-stone-600">
          Topic-wise competencies
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {c.competency_assessments.map((comp) => (
            <div
              key={comp.competency_name}
              className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-stone-900">
                  {comp.competency_name}
                </span>
                {comp.level ? (
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${
                      LEVEL_STYLE[comp.level] ?? "bg-stone-100"
                    }`}
                  >
                    {comp.level}
                  </span>
                ) : (
                  <span className="shrink-0 rounded-md bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500">
                    {comp.assessment_status.toLowerCase().replaceAll("_", " ")}
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

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-stone-600">
            Technical strengths
          </h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-stone-800">
            {c.strengths.length === 0 && (
              <li className="list-none pl-0 text-stone-400">None recorded</li>
            )}
            {c.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
        <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-stone-600">
            Areas for improvement
          </h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm text-stone-800">
            {c.improvement_areas.length === 0 && (
              <li className="list-none pl-0 text-stone-400">None recorded</li>
            )}
            {c.improvement_areas.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-2xl border border-indigo-200 bg-indigo-50 p-5">
        <h2 className="text-sm font-semibold text-indigo-900">
          Personalized improvement plan
        </h2>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-indigo-950">
          {c.recommendations.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
        <h2 className="text-sm font-semibold text-stone-600">
          Question-by-question evidence
        </h2>
        <p className="mt-1 text-xs text-stone-500">
          Only submitted answers are scored. Unanswered questions are not counted
          as incorrect.
        </p>
        <div className="mt-3 space-y-3">
          {c.question_assessments.map((qa) => (
            <details
              key={qa.turn_index}
              className="rounded-xl border border-stone-100 bg-stone-50/60 p-4 open:bg-white open:shadow-sm"
              data-testid={`report-qa-${qa.turn_index}`}
            >
              <summary className="cursor-pointer text-sm text-stone-800">
                <span
                  className={`mr-2 rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                    COVERAGE_STYLE[qa.coverage] ?? "bg-stone-100"
                  }`}
                >
                  {qa.coverage}
                  {qa.score != null ? ` · ${qa.score}%` : ""}
                </span>
                {(qa.executed === false || qa.review_label) && (
                  <span className="mr-2 rounded-md bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-800">
                    {qa.review_label || AI_REVIEWED_NOT_EXECUTED}
                  </span>
                )}
                <span className="font-semibold">Q{qa.turn_index}</span>
                {qa.question ? (
                  <span className="text-stone-600"> — {qa.question}</span>
                ) : (
                  <span className="text-stone-600"> — {qa.observation}</span>
                )}
              </summary>

              <div className="mt-3 space-y-3 text-sm">
                {qa.question && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">
                      Question
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-stone-800">
                      {qa.question}
                    </p>
                  </div>
                )}
                {qa.code_snippet && (
                  <pre className="overflow-x-auto rounded-xl bg-stone-900 p-3 font-mono text-xs text-stone-100">
                    {qa.code_snippet}
                  </pre>
                )}
                {qa.chosen_option && (
                  <p className="text-stone-800" data-testid="mcq-chosen">
                    Chosen: {qa.chosen_option}
                    {qa.correct_option ? ` · Correct: ${qa.correct_option}` : ""}
                  </p>
                )}
                {qa.answer && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">
                      Your answer
                    </p>
                    <p className="mt-1 whitespace-pre-wrap rounded-xl bg-indigo-50 px-3 py-2 text-indigo-950">
                      {qa.chosen_option || qa.answer}
                    </p>
                  </div>
                )}
                {(qa.strengths?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
                      Strengths
                    </p>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-stone-800">
                      {qa.strengths!.map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {(qa.gaps?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
                      Mistakes / missing concepts
                    </p>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-stone-800">
                      {qa.gaps!.map((g) => (
                        <li key={g}>{g}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {qa.expected_answer_explanation?.trim() && (
                  <div className="rounded-xl bg-indigo-50/80 px-3 py-2.5">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">
                      Expected answer / explanation
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-indigo-950">
                      {qa.expected_answer_explanation}
                    </p>
                  </div>
                )}
                {(qa.time_complexity?.trim() || qa.space_complexity?.trim()) && (
                  <div className="flex flex-wrap gap-2 text-xs">
                    {qa.time_complexity?.trim() && (
                      <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 font-medium text-stone-700">
                        Time: {qa.time_complexity}
                      </span>
                    )}
                    {qa.space_complexity?.trim() && (
                      <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 font-medium text-stone-700">
                        Space: {qa.space_complexity}
                      </span>
                    )}
                  </div>
                )}
                {qa.corrected_code?.trim() && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
                      Corrected code
                    </p>
                    <pre className="mt-1 max-h-56 overflow-auto rounded-xl border border-violet-100 bg-stone-950 px-3 py-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-violet-100">
                      {qa.corrected_code}
                    </pre>
                  </div>
                )}
                {!qa.answer && qa.evidence_excerpt && (
                  <p className="rounded-lg bg-white p-2 text-xs italic text-stone-600 ring-1 ring-stone-100">
                    “{qa.evidence_excerpt}”
                  </p>
                )}
              </div>
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
