import { Link } from "react-router-dom";
import type { CareerIntelligence } from "../lib/api";
import CompetencyOverview from "./CompetencyOverview";
import ProjectPrepPanel from "./ProjectPrepPanel";

const LEVEL_LABEL: Record<string, string> = {
  insufficient_evidence: "Insufficient evidence",
  early: "Early signal",
  building: "Building evidence",
  developing: "Developing",
  needs_focused_practice: "Needs focused practice",
  strong_evidence: "Strong evidence",
};

const LEVEL_CLASS: Record<string, string> = {
  insufficient_evidence: "bg-stone-100 text-stone-700",
  early: "bg-sky-50 text-sky-800",
  building: "bg-amber-50 text-amber-900",
  developing: "bg-amber-50 text-amber-900",
  needs_focused_practice: "bg-rose-50 text-rose-900",
  strong_evidence: "bg-emerald-50 text-emerald-900",
};

type Props = {
  data?: CareerIntelligence | null;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  compact?: boolean;
  onPracticeWeak?: () => void;
  onDefendProjects?: () => void;
  canDefend?: boolean;
};

export default function CareerIntelligencePanel({
  data,
  loading,
  error,
  onRetry,
  compact = false,
  onPracticeWeak,
  onDefendProjects,
  canDefend = true,
}: Props) {
  if (loading && !data) {
    return (
      <section
        className="space-y-3 rounded-lg border border-line bg-white p-5"
        aria-busy="true"
        data-testid="career-intelligence-loading"
      >
        <div className="h-5 w-40 animate-pulse rounded bg-page" />
        <div className="h-16 animate-pulse rounded bg-page" />
        <div className="h-24 animate-pulse rounded bg-page" />
      </section>
    );
  }

  if (error) {
    return (
      <section
        className="rounded-lg border border-rose-200 bg-rose-50 p-5 text-sm text-rose-900"
        data-testid="career-intelligence-error"
        role="alert"
      >
        <p className="font-semibold">Couldn’t load career readiness</p>
        <p className="mt-1">{error}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-2 text-sm font-semibold underline-offset-2 hover:underline"
          >
            Retry
          </button>
        )}
      </section>
    );
  }

  if (!data) return null;

  const readiness = data.career_readiness;
  const level = readiness?.level || "insufficient_evidence";
  const progress = data.progress;
  const showFull = !compact;
  const primaryAction = data.next_actions?.[0];

  return (
    <div className="space-y-4" data-testid="career-intelligence">
      <section className="space-y-4 rounded-lg border border-line bg-white p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-ink">Career readiness</h2>
            <p className="mt-1 text-xs text-ink-soft">
              From completed interview evidence — not a hiring prediction.
            </p>
          </div>
          <span
            className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${LEVEL_CLASS[level] || LEVEL_CLASS.insufficient_evidence}`}
          >
            {LEVEL_LABEL[level] || level}
          </span>
        </div>

        <p className="text-sm text-ink" data-testid="career-readiness-summary">
          {readiness?.summary}
        </p>
        {readiness?.target_role && (
          <p className="text-xs text-ink-soft">Target role: {readiness.target_role}</p>
        )}
        {readiness?.evidence_index != null && readiness.evidence_method && (
          <p className="text-xs text-ink-soft" data-testid="career-evidence-index">
            Evidence strength: {readiness.evidence_index}/100 — {readiness.evidence_method}
          </p>
        )}

        {primaryAction && (
          <div
            className="rounded-xl border border-accent/20 bg-accent-soft/50 p-3"
            data-testid="career-preparation-loop"
          >
            <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-strong">
              Recommended next step
            </p>
            <p className="mt-1 text-sm font-semibold text-ink">{primaryAction.title}</p>
            {primaryAction.reason && (
              <p className="mt-0.5 text-xs text-ink-soft">{primaryAction.reason}</p>
            )}
            <p className="mt-2 text-[11px] text-ink-faint">
              Interview → Assessment → Evidence → Recommendation → Practice → Reassessment
            </p>
          </div>
        )}

        {(data.next_actions?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-2" data-testid="career-next-actions">
            {data.next_actions!.map((action) => {
              if (action.kind === "practice_weak" && onPracticeWeak) {
                return (
                  <button
                    key={action.title}
                    type="button"
                    onClick={onPracticeWeak}
                    className="rounded-md bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong"
                  >
                    {action.action_label || action.title}
                  </button>
                );
              }
              if (action.kind === "defend_projects" && onDefendProjects) {
                return (
                  <button
                    key={action.title}
                    type="button"
                    onClick={onDefendProjects}
                    className="rounded-md border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white"
                  >
                    {action.action_label || action.title}
                  </button>
                );
              }
              return (
                <Link
                  key={action.title}
                  to={action.href || "/readiness"}
                  className="rounded-md border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white"
                >
                  {action.action_label || action.title}
                </Link>
              );
            })}
          </div>
        )}

        {showFull && (
          <>
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                Progress across interviews
              </h3>
              {!progress?.available ? (
                <p className="mt-2 text-sm text-ink-faint">
                  {progress?.comparison_note || progress?.reason ||
                    "Need comparable interviews before showing a trend."}
                </p>
              ) : (
                <div className="mt-2 grid gap-2 text-sm text-ink sm:grid-cols-2">
                  <p>
                    <span className="font-medium text-emerald-800">Improving: </span>
                    {(progress.improving?.length ?? 0) > 0
                      ? progress.improving!.slice(0, 4).join(", ")
                      : "—"}
                  </p>
                  <p>
                    <span className="font-medium text-rose-800">Persistent gaps: </span>
                    {(progress.persistent_weaknesses?.length ?? 0) > 0
                      ? progress.persistent_weaknesses!.slice(0, 4).join(", ")
                      : "—"}
                  </p>
                </div>
              )}
            </div>

            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                Recommendations
              </h3>
              {(data.recommendations?.length ?? 0) === 0 ? (
                <p className="mt-2 text-sm text-ink-faint">
                  Complete interviews to unlock personalized recommendations.
                </p>
              ) : (
                <ul className="mt-2 space-y-2" data-testid="career-recommendations">
                  {data.recommendations!.slice(0, 5).map((rec) => (
                    <li key={rec.topic} className="rounded-md border border-line bg-page/60 p-3">
                      <p className="text-sm font-semibold text-ink">{rec.topic}</p>
                      <p className="mt-1 text-xs text-ink-soft">{rec.why}</p>
                      <p className="mt-1 text-xs text-ink">Practice: {rec.practice}</p>
                      {rec.track_subject && (
                        <p className="mt-1 text-[11px] text-ink-soft">
                          Track: {rec.track_subject}
                        </p>
                      )}
                      <p className="mt-1 text-[11px] text-ink-faint">
                        Evidence: {rec.evidence_basis || rec.evidence}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                Preparation roadmap
              </h3>
              {(data.roadmap?.length ?? 0) === 0 ? (
                <p className="mt-2 text-sm text-ink-faint">No roadmap steps yet.</p>
              ) : (
                <ol className="mt-2 list-decimal space-y-2 pl-5 text-sm text-ink">
                  {data.roadmap!.slice(0, 6).map((step) => (
                    <li key={`${step.order}-${step.topic}`}>
                      <span className="font-semibold">{step.topic}</span>
                      <span className="text-ink-soft"> — {step.reason}</span>
                      <p className="text-xs text-ink-soft">{step.activity}</p>
                      {(step.track_subject || step.supporting_evidence) && (
                        <p className="text-[11px] text-ink-faint">
                          {[step.track_subject, step.supporting_evidence || step.evidence_basis]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </>
        )}

        {compact && (
          <Link
            to="/readiness"
            className="inline-flex text-xs font-semibold text-accent-strong underline-offset-2 hover:underline"
          >
            Open full career readiness →
          </Link>
        )}

        <p className="text-[11px] text-ink-faint">{data.disclaimer}</p>
      </section>

      {showFull && <CompetencyOverview data={data} />}

      {showFull && (
        <ProjectPrepPanel
          data={data.project_intelligence}
          defense={data.project_defense}
          onDefend={onDefendProjects}
          canDefend={canDefend}
        />
      )}
    </div>
  );
}
