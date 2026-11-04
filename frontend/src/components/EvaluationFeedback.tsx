import { COVERAGE_STYLE } from "../lib/ui";
import type { TurnResult } from "../lib/api";

type Evaluation = TurnResult["evaluation"];

type Props = {
  evaluation: Evaluation;
  questionIndex?: number;
  compact?: boolean;
};

export default function EvaluationFeedback({
  evaluation,
  questionIndex,
  compact = false,
}: Props) {
  const hasExplanation = !!evaluation.expected_answer_explanation?.trim();
  const hasCode = !!evaluation.corrected_code?.trim();
  const hasComplexity =
    !!evaluation.time_complexity?.trim() || !!evaluation.space_complexity?.trim();

  return (
    <div
      className={`rounded-2xl border border-indigo-100 bg-white shadow-sm ${
        compact ? "p-3" : "p-4 sm:p-5"
      }`}
      data-testid="evaluation-feedback"
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-stone-900">
          {questionIndex != null ? `Q${questionIndex} evaluation` : "Evaluation"}
        </p>
        <span
          className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${
            COVERAGE_STYLE[evaluation.coverage] ?? "bg-stone-100"
          }`}
        >
          {evaluation.coverage}
        </span>
      </div>

      {evaluation.strengths.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
            Strengths
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-stone-800">
            {evaluation.strengths.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {evaluation.gaps.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-700">
            Mistakes / missing concepts
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-stone-800">
            {evaluation.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {hasExplanation && (
        <div className="mt-3 rounded-xl bg-indigo-50/80 px-3 py-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-700">
            Expected answer
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-indigo-950">
            {evaluation.expected_answer_explanation}
          </p>
        </div>
      )}

      {hasComplexity && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {evaluation.time_complexity?.trim() && (
            <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 font-medium text-stone-700">
              Time: {evaluation.time_complexity}
            </span>
          )}
          {evaluation.space_complexity?.trim() && (
            <span className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1 font-medium text-stone-700">
              Space: {evaluation.space_complexity}
            </span>
          )}
        </div>
      )}

      {hasCode && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
            Corrected code
          </p>
          <pre className="mt-1 max-h-64 overflow-auto rounded-xl border border-violet-100 bg-stone-950 px-3 py-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-violet-100">
            {evaluation.corrected_code}
          </pre>
        </div>
      )}
    </div>
  );
}
