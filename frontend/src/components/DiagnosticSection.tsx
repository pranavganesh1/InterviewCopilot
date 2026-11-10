import type { ReportDiagnostics } from "../lib/api";

function AreaProgressChart({
  history,
}: {
  history: ReportDiagnostics["area_score_history"];
}) {
  if (!history.length) {
    return <p className="text-sm text-ink-faint">Not enough sessions for a chart yet.</p>;
  }
  const areas = [
    ...new Set(history.flatMap((row) => Object.keys(row.areas || {}))),
  ].slice(0, 5);
  const width = 320;
  const height = 120;
  const pad = 20;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-auto w-full max-w-md"
      role="img"
      aria-label="Progress over time by area"
    >
      <title>Progress over time by area</title>
      {areas.map((area, ai) => {
        const color = ["#6d28d9", "#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd"][ai] || "#6d28d9";
        const points = history.map((row, i) => {
          const score = row.areas[area] ?? 0;
          const x = pad + (history.length <= 1 ? innerW / 2 : (i / (history.length - 1)) * innerW);
          const y = pad + innerH - (score / 100) * innerH;
          return { x, y, score, i };
        });
        const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
        return (
          <g key={area}>
            <path d={path} fill="none" stroke={color} strokeWidth="2" />
            {points.map((p) => (
              <circle
                key={`${area}-${p.i}`}
                cx={p.x}
                cy={p.y}
                r="4"
                fill={color}
                tabIndex={0}
                role="img"
                aria-label={`${area}: ${p.score}% in session ${p.i + 1}`}
              >
                <title>{`${area}: ${p.score}%`}</title>
              </circle>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

export default function DiagnosticSection({
  diagnostics,
  onPracticeWeak,
}: {
  diagnostics?: ReportDiagnostics | null;
  onPracticeWeak?: () => void;
}) {
  if (!diagnostics) {
    return (
      <section className="rounded-lg border border-dashed border-line bg-white p-5">
        <h2 className="text-sm font-semibold text-ink">Your diagnostic</h2>
        <p className="mt-2 text-sm text-ink-faint">
          Diagnostics appear after enough answered questions across sessions.
        </p>
      </section>
    );
  }

  const weak = diagnostics.identified_weaknesses || [];
  const strengths = diagnostics.strengths || [];
  const practice = diagnostics.recommended_practice || [];

  return (
    <section className="space-y-4 rounded-lg border border-line bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Your diagnostic</h2>
          <p className="mt-1 text-xs text-ink-soft">
            Derived from your answered questions. Nothing here changes scoring rules.
          </p>
        </div>
        {onPracticeWeak && weak.length > 0 && (
          <button
            type="button"
            onClick={onPracticeWeak}
            className="rounded-md bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong"
          >
            Practice weak areas
          </button>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Identified weaknesses
        </h3>
        {weak.length === 0 ? (
          <p className="mt-2 text-sm text-ink-faint">No weak concepts yet.</p>
        ) : (
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {weak.map((row) => (
              <li
                key={row.concept}
                className="min-w-0 rounded-md border border-line bg-page/50 p-3"
              >
                <p className="truncate text-sm font-semibold text-ink" title={row.concept}>
                  {row.concept}
                </p>
                <p className="mt-1 text-[11px] font-medium uppercase text-violet-700">
                  {row.status}
                </p>
                {(row.missing_concepts?.length ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-ink-soft">
                    Practice this: {row.missing_concepts.slice(0, 2).join("; ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Strengths
        </h3>
        {strengths.length === 0 ? (
          <p className="mt-2 text-sm text-ink-faint">Keep practicing to surface strengths.</p>
        ) : (
          <ul className="mt-2 flex flex-wrap gap-2">
            {strengths.map((row) => (
              <li
                key={row.concept}
                className="max-w-full truncate rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800"
                title={row.concept}
              >
                {row.concept}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Progress over time
        </h3>
        <div className="mt-2">
          <AreaProgressChart history={diagnostics.area_score_history || []} />
        </div>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Recommended practice
        </h3>
        {practice.length === 0 ? (
          <p className="mt-2 text-sm text-ink-faint">No practice themes yet.</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {practice.map((row) => (
              <li key={row.concept} className="text-sm text-ink">
                <span className="font-semibold">{row.concept}</span>
                <span className="text-ink-soft">
                  {" — "}
                  {(row.study_topics || []).slice(0, 2).join("; ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
