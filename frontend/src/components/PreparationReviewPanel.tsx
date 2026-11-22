import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { NextAction, ProfileReview, RoadmapStep } from "../lib/api";

const STATUS_STYLES: Record<string, string> = {
  confirmed: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  needs_clarification: "bg-amber-50 text-amber-900 ring-amber-200",
  not_assessed: "bg-stone-100 text-stone-700 ring-stone-200",
};

const STATUS_LABELS: Record<string, string> = {
  confirmed: "Confirmed",
  needs_clarification: "Needs clarification",
  not_assessed: "Not assessed",
};

const COMPLETION_STYLES: Record<string, string> = {
  completed: "bg-emerald-50 text-emerald-800",
  in_progress: "bg-sky-50 text-sky-800",
  not_started: "bg-stone-100 text-stone-600",
};

const COMPLETION_LABELS: Record<string, string> = {
  completed: "Completed",
  in_progress: "In progress",
  not_started: "Not started",
};

type Props = {
  review: ProfileReview | null | undefined;
  userName?: string | null;
  pending?: boolean;
  refreshPending?: boolean;
  refreshError?: string | null;
  onRefresh?: () => void;
  onSaveSummary: (summary: string) => void;
  onSetItemStatus: (
    itemId: string,
    status: "confirmed" | "needs_clarification" | "not_assessed",
  ) => void;
  onNextAction: (action: NextAction) => void;
  onStartRecommended: (step?: RoadmapStep) => void;
  onBrowseTracks: () => void;
};

export default function PreparationReviewPanel({
  review,
  userName,
  pending,
  refreshPending,
  refreshError,
  onRefresh,
  onSaveSummary,
  onSetItemStatus,
  onNextAction,
  onStartRecommended,
  onBrowseTracks,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(review?.summary ?? "");

  useEffect(() => {
    if (!editing) setDraft(review?.summary ?? "");
  }, [review?.summary, editing]);

  if (!review?.summary && !(review?.roadmap?.length)) {
    return null;
  }

  const next = review.next_action;
  const clarify = review.needs_clarification ?? [];
  const notAssessed = review.not_assessed ?? [];
  const confirmedCount = review.confirmed?.length ?? 0;
  const totalItems = review.item_statuses?.length ?? 0;

  const targetLabel =
    review.goal_labels?.find((g) => /role|engineer|intern|analyst|developer/i.test(g)) ||
    review.goal_labels?.[0] ||
    null;

  return (
    <section className="space-y-4" data-testid="preparation-review">
      <div className="overflow-hidden rounded-2xl border border-accent/20 bg-gradient-to-r from-accent-soft via-[#ece9fe] to-white p-5 shadow-card sm:p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-accent">
              Welcome back{userName ? `, ${userName.split(" ")[0]}` : ""}
            </p>
            <h2 className="mt-1 text-xl font-bold tracking-tight text-ink sm:text-2xl">
              Your Personalized Preparation Plan
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-ink-soft">
              Based on your vault and goals — not guessed proficiency scores.
            </p>
            {refreshError && (
              <p
                role="alert"
                data-testid="preparation-review-refresh-error"
                className="mt-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800"
              >
                {refreshError}
              </p>
            )}
            {totalItems > 0 && (
              <p className="mt-2 text-xs text-ink-faint" data-testid="profile-completeness">
                Profile signals: {confirmedCount} confirmed
                {clarify.length > 0 ? ` · ${clarify.length} need clarification` : ""}
                {notAssessed.length > 0
                  ? ` · ${notAssessed.length} not yet interview-assessed`
                  : ""}
              </p>
            )}
          </div>
          <div className="flex w-full flex-col gap-2 sm:max-w-xs lg:w-72">
            <div className="rounded-xl border border-white/80 bg-white/90 p-3 shadow-sm backdrop-blur">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                Target Role
              </p>
              <p className="mt-1 text-sm font-semibold text-ink">
                {targetLabel || "Set a target role in onboarding"}
              </p>
              <Link
                to="/onboarding"
                className="mt-2 inline-flex text-xs font-semibold text-accent-strong hover:underline"
              >
                Update Goal
              </Link>
            </div>
            {onRefresh && (
              <button
                type="button"
                data-testid="preparation-review-refresh"
                disabled={pending || refreshPending}
                onClick={onRefresh}
                className="rounded-xl border border-accent/30 bg-white px-3 py-2 text-xs font-semibold text-accent-strong hover:bg-accent-soft disabled:opacity-50"
              >
                {refreshPending ? "Refreshing…" : "Refresh plan"}
              </button>
            )}
          </div>
        </div>

        {next && (
          <div
            className="mt-4 rounded-xl border border-accent/25 bg-white/95 p-4 shadow-sm"
            data-testid="next-action"
            data-kind={next.kind || "recommend_track"}
          >
            <p className="text-sm font-semibold text-ink">{next.title}</p>
            {next.reason && (
              <p className="mt-1 text-xs text-ink-soft">{next.reason}</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={pending}
                onClick={() => onNextAction(next)}
                className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
              >
                {next.action_label || "Continue"}
              </button>
              <button
                type="button"
                onClick={onBrowseTracks}
                className="rounded-xl bg-white px-4 py-2 text-sm font-medium text-ink-soft ring-1 ring-line hover:bg-page"
              >
                Browse other tracks
              </button>
              <Link
                to="/onboarding"
                className="rounded-xl px-4 py-2 text-sm font-medium text-accent-strong hover:underline"
              >
                Edit profile vault
              </Link>
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-stone-800">Profile summary</h3>
            {!editing ? (
              <button
                type="button"
                className="text-xs font-medium text-accent-strong hover:underline"
                onClick={() => setEditing(true)}
              >
                Correct summary
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  type="button"
                  className="text-xs font-medium text-stone-500"
                  onClick={() => {
                    setEditing(false);
                    setDraft(review.summary ?? "");
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={pending || !draft.trim()}
                  className="text-xs font-semibold text-accent-strong disabled:opacity-40"
                  onClick={() => {
                    onSaveSummary(draft.trim());
                    setEditing(false);
                  }}
                >
                  Save
                </button>
              </div>
            )}
          </div>
          {editing ? (
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={10}
              className="mt-3 w-full rounded-md border border-stone-200 px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
            />
          ) : (
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-stone-700">
              {review.summary}
            </p>
          )}
          {(review.goal_labels?.length ?? 0) > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {review.goal_labels!.map((label) => (
                <span
                  key={label}
                  className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent-strong"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-stone-800">
            Profile validation
          </h3>
          <p className="mt-0.5 text-xs text-stone-500">
            Confirmed facts vs items that still need detail or interview assessment.
          </p>
          <div className="mt-3 space-y-2 max-h-72 overflow-y-auto">
            {(review.item_statuses ?? []).map((item) => (
              <div
                key={item.item_id}
                className="rounded-lg border border-stone-100 px-3 py-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-stone-800">{item.title}</p>
                    <p className="text-[11px] uppercase tracking-wide text-stone-400">
                      {item.category}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${
                      STATUS_STYLES[item.status] ?? STATUS_STYLES.not_assessed
                    }`}
                  >
                    {STATUS_LABELS[item.status] ?? item.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-stone-500">{item.reason}</p>
                <div className="mt-1.5 flex flex-wrap gap-3">
                  {item.status !== "confirmed" && (
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => onSetItemStatus(item.item_id, "confirmed")}
                      className="text-[11px] font-medium text-accent-strong hover:underline disabled:opacity-40"
                    >
                      Mark as confirmed
                    </button>
                  )}
                  {item.status === "needs_clarification" && (
                    <Link
                      to="/onboarding"
                      className="text-[11px] font-medium text-stone-600 hover:underline"
                    >
                      Fix in vault
                    </Link>
                  )}
                </div>
              </div>
            ))}
            {(review.item_statuses?.length ?? 0) === 0 && (
              <p className="text-sm text-stone-500">No vault items yet.</p>
            )}
          </div>
        </div>
      </div>

      {(review.roadmap?.length ?? 0) > 0 && (
        <div className="rounded-xl border border-stone-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-stone-800">
            Preparation roadmap
          </h3>
          <p className="mt-0.5 text-xs text-stone-500">
            Recommended from your selected goals and profile — start any step.
          </p>
          <ol className="mt-4 grid gap-3 md:grid-cols-2">
            {review.roadmap!.map((step, index) => (
              <li
                key={step.id}
                className="rounded-lg border border-stone-100 bg-stone-50/60 p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-stone-400">
                    Stage {step.stage ?? index + 1}
                  </p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      COMPLETION_STYLES[step.completion ?? "not_started"]
                    }`}
                  >
                    {COMPLETION_LABELS[step.completion ?? "not_started"]}
                  </span>
                </div>
                <p className="mt-0.5 text-sm font-semibold text-stone-800">
                  {step.title}
                </p>
                <p className="mt-1 text-xs text-stone-600">{step.why}</p>
                {step.topics?.length > 0 && (
                  <p className="mt-2 text-xs text-stone-500">
                    <span className="font-medium text-stone-700">Topics: </span>
                    {step.topics.join(", ")}
                  </p>
                )}
                <p className="mt-1 text-xs text-stone-500">
                  <span className="font-medium text-stone-700">You&apos;ll practise: </span>
                  {step.practise}
                </p>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => onStartRecommended(step)}
                  className="mt-3 rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-accent-strong ring-1 ring-accent/30 hover:bg-accent-soft disabled:opacity-40"
                >
                  {step.action_label}
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
