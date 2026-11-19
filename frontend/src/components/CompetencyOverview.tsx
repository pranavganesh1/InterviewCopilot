import type { CareerIntelligence, CareerConceptEvidence } from "../lib/api";

type Props = {
  data: CareerIntelligence;
  compact?: boolean;
};

function evidenceHint(row: CareerConceptEvidence): string | null {
  const parts: string[] = [];
  if (row.last_coverage) parts.push(`Last: ${row.last_coverage}`);
  if (row.times_asked != null) parts.push(`${row.times_asked}× assessed`);
  if (row.evidence_label) parts.push(row.evidence_label);
  return parts.length ? parts.join(" · ") : null;
}

function ChipList({
  items,
  tone,
  empty,
  testId,
}: {
  items: { label: string; hint?: string | null }[];
  tone: "strong" | "improve" | "partial" | "neutral" | "claim";
  empty: string;
  testId: string;
}) {
  const toneClass: Record<typeof tone, string> = {
    strong: "bg-emerald-50 text-emerald-900 ring-emerald-200",
    improve: "bg-rose-50 text-rose-900 ring-rose-200",
    partial: "bg-amber-50 text-amber-900 ring-amber-200",
    neutral: "bg-page text-ink-soft ring-line",
    claim: "bg-sky-50 text-sky-900 ring-sky-200",
  };
  return (
    <div data-testid={testId}>
      {items.length === 0 ? (
        <p className="mt-2 text-sm text-ink-faint">{empty}</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {items.map((item) => (
            <li key={item.label}>
              <span
                className={`inline-flex max-w-full flex-wrap items-baseline gap-x-2 rounded-md px-2 py-1 text-xs font-medium ring-1 ${toneClass[tone]}`}
              >
                <span className="truncate">{item.label}</span>
                {item.hint && (
                  <span className="font-normal opacity-80">{item.hint}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Competency categories from Career Intelligence only.
 * Not-assessed and claims are never shown as weaknesses.
 */
export default function CompetencyOverview({ data, compact = false }: Props) {
  const gaps = data.knowledge_gaps;
  const limit = compact ? 4 : 6;

  const strengths = (data.strengths ?? []).slice(0, limit).map((row) => ({
    label: row.concept,
    hint: evidenceHint(row),
  }));
  const improve = (data.improvement_areas ?? []).slice(0, limit).map((row) => ({
    label: row.concept,
    hint: evidenceHint(row),
  }));
  const partial = (data.developing ?? gaps?.needs_improvement ?? [])
    .slice(0, limit)
    .map((row) => ({
      label: "concept" in row ? String(row.concept || "") : String(row),
      hint:
        typeof row === "object" && row && "last_coverage" in row
          ? evidenceHint(row as CareerConceptEvidence)
          : "Partially demonstrated",
    }))
    .filter((r) => r.label);

  const notAssessed = (
    gaps?.not_assessed?.length
      ? gaps.not_assessed
      : data.not_yet_assessed ?? []
  )
    .slice(0, limit)
    .map((topic) => ({ label: topic, hint: "Not assessed yet" }));

  const claims = (
    gaps?.claimed_skills_without_interview?.length
      ? gaps.claimed_skills_without_interview
      : gaps?.unverified_claims ?? []
  )
    .slice(0, limit)
    .map((topic) => ({
      label: topic,
      hint: "Claim — not yet demonstrated",
    }));

  return (
    <section
      className="space-y-4 rounded-2xl border border-line bg-white p-5 shadow-card"
      data-testid="competency-overview"
      aria-labelledby="competency-overview-heading"
    >
      <div>
        <h2
          id="competency-overview-heading"
          className="text-sm font-semibold text-ink"
        >
          Competency intelligence
        </h2>
        <p className="mt-1 text-xs text-ink-soft">
          Interview evidence only. Resume claims are separate — missing evidence
          is not a weakness.
        </p>
      </div>

      <div className={`grid gap-4 ${compact ? "sm:grid-cols-2" : "sm:grid-cols-2 xl:grid-cols-3"}`}>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
            Demonstrated strengths
          </h3>
          <ChipList
            items={strengths}
            tone="strong"
            empty="None with enough interview evidence yet."
            testId="competency-strengths"
          />
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-rose-700">
            Areas requiring improvement
          </h3>
          <ChipList
            items={improve}
            tone="improve"
            empty="No demonstrated weaknesses yet."
            testId="competency-improve"
          />
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">
            Partially demonstrated
          </h3>
          <ChipList
            items={partial}
            tone="partial"
            empty="No partial competencies recorded yet."
            testId="competency-partial"
          />
        </div>
        <div>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            Not yet assessed
          </h3>
          <ChipList
            items={notAssessed}
            tone="neutral"
            empty="No pending planned topics."
            testId="competency-not-assessed"
          />
        </div>
        <div className={compact ? "sm:col-span-2" : "sm:col-span-2 xl:col-span-1"}>
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-sky-800">
            Claims not yet demonstrated
          </h3>
          <ChipList
            items={claims}
            tone="claim"
            empty="No unverified vault claims waiting for interview evidence."
            testId="competency-claims"
          />
        </div>
      </div>

      {gaps?.policy?.note && (
        <p className="text-[11px] text-ink-faint" data-testid="competency-policy">
          {gaps.policy.note}
        </p>
      )}

      {!compact && (data.competency_evidence?.length ?? 0) > 0 && (
        <div data-testid="competency-evidence-list">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            Supporting evidence
          </h3>
          <ul className="mt-2 space-y-2">
            {data.competency_evidence!.slice(0, 5).map((row) => (
              <li
                key={`${row.competency}-${row.track_id || ""}`}
                className="rounded-md border border-line bg-page/50 px-3 py-2 text-xs text-ink"
              >
                <span className="font-semibold">{row.competency}</span>
                {row.assessment && (
                  <span className="text-ink-soft"> · {row.assessment}</span>
                )}
                {row.track_subject && (
                  <span className="text-ink-soft"> · {row.track_subject}</span>
                )}
                {row.last_coverage && (
                  <span className="text-ink-faint"> · {row.last_coverage}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
