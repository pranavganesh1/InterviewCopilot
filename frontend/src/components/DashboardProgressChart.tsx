type Point = {
  label: string;
  overall: number | null;
  technical?: number | null;
};

/** SVG progress chart — uses only provided scores; no invented values. */
export default function DashboardProgressChart({
  points,
  emptyMessage = "Complete interviews to see progress.",
}: {
  points: Point[];
  emptyMessage?: string;
}) {
  const usable = points.filter((p) => p.overall != null);
  if (usable.length === 0) {
    return (
      <div className="grid h-48 place-items-center rounded-xl bg-page/80 text-center text-sm text-ink-faint">
        {emptyMessage}
      </div>
    );
  }

  const w = 320;
  const h = 180;
  const pad = { t: 16, r: 12, b: 28, l: 36 };
  const innerW = w - pad.l - pad.r;
  const innerH = h - pad.t - pad.b;
  const n = Math.max(usable.length - 1, 1);

  const xAt = (i: number) => pad.l + (i / n) * innerW;
  const yAt = (v: number) => pad.t + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;

  const overallPath = usable
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.overall!).toFixed(1)}`)
    .join(" ");

  const techPts = usable.filter((p) => p.technical != null);
  const techPath =
    techPts.length >= 2
      ? usable
          .map((p, i) =>
            p.technical == null
              ? null
              : `${i === 0 || usable[i - 1]?.technical == null ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.technical).toFixed(1)}`,
          )
          .filter(Boolean)
          .join(" ")
      : "";

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-48 w-full min-w-[260px]" role="img" aria-label="Interview score progress">
        {[0, 25, 50, 75, 100].map((tick) => {
          const y = yAt(tick);
          return (
            <g key={tick}>
              <line
                x1={pad.l}
                x2={w - pad.r}
                y1={y}
                y2={y}
                stroke="var(--color-line)"
                strokeWidth="1"
              />
              <text
                x={pad.l - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-ink-faint"
                fontSize="9"
              >
                {tick}%
              </text>
            </g>
          );
        })}
        <path d={overallPath} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {techPath && (
          <path
            d={techPath}
            fill="none"
            stroke="#38bdf8"
            strokeWidth="2"
            strokeDasharray="4 3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {usable.map((p, i) => (
          <g key={`${p.label}-${i}`}>
            <circle cx={xAt(i)} cy={yAt(p.overall!)} r="3.5" fill="var(--color-accent)" />
            <text
              x={xAt(i)}
              y={h - 8}
              textAnchor="middle"
              className="fill-ink-soft"
              fontSize="9"
            >
              {p.label}
            </text>
          </g>
        ))}
      </svg>
      <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-ink-soft">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 rounded bg-accent" /> Overall
        </span>
        {techPath && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-sky-400" /> Technical
          </span>
        )}
      </div>
    </div>
  );
}
