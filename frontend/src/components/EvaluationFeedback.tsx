import { AI_REVIEWED_NOT_EXECUTED } from "../lib/codingReview";
import Badge from "./ui/Badge";
import { COVERAGE_TONE } from "../lib/status";
import type { TurnResult } from "../lib/api";

type Evaluation = TurnResult["evaluation"];

type Props = {
  evaluation: Evaluation;
  questionIndex?: number;
  compact?: boolean;
  /** When true (coding question), show the static-review badge. */
  coding?: boolean;
};

export default function EvaluationFeedback({
  evaluation,
  questionIndex,
  compact = false,
  coding = false,
}: Props) {
  const hasExplanation = !!evaluation.expected_answer_explanation?.trim();
  const hasCode = !!evaluation.corrected_code?.trim();
  const hasComplexity =
    !!evaluation.time_complexity?.trim() || !!evaluation.space_complexity?.trim();
  const showAiReviewed = coding || hasCode || hasComplexity;

  return (
    <div
      className={`rounded-lg border border-line bg-surface shadow-card ${
        compact ? "p-3" : "p-4 sm:p-5"
      }`}
      data-testid="evaluation-feedback"
    >
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold text-stone-900">
          {questionIndex != null ? `Q${questionIndex} evaluation` : "Evaluation"}
        </p>
        <Badge tone={COVERAGE_TONE[evaluation.coverage] ?? "neutral"}>
          {evaluation.coverage}
        </Badge>
        {showAiReviewed && (
          <span
            className="rounded-md bg-stone-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-700"
            data-testid="ai-reviewed-badge"
          >
            {AI_REVIEWED_NOT_EXECUTED}
          </span>
        )}
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
            To improve
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-stone-800">
            {evaluation.gaps.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </div>
      )}

      {hasExplanation && (
        <div className="mt-3 rounded-md border border-line bg-page px-3 py-2.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            Expected answer
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-ink">
            {evaluation.expected_answer_explanation}
          </p>
        </div>
      )}

      {hasComplexity && (
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {evaluation.time_complexity?.trim() && (
            <span className="rounded-md border border-line bg-page px-2.5 py-1 font-medium text-ink-soft">
              Time: {evaluation.time_complexity}
            </span>
          )}
          {evaluation.space_complexity?.trim() && (
            <span className="rounded-md border border-line bg-page px-2.5 py-1 font-medium text-ink-soft">
              Space: {evaluation.space_complexity}
            </span>
          )}
        </div>
      )}

      {hasCode && (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-600">
            Corrected code
          </p>
          <pre className="mt-1 max-h-64 overflow-auto rounded-md border border-line bg-stone-950 px-3 py-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-stone-200">
            {evaluation.corrected_code}
          </pre>
        </div>
      )}
    </div>
  );
}
