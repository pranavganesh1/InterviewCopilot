export default function ProgressRing({
  value,
  size = "md",
}: {
  value: number | null;
  size?: "xs" | "sm" | "md";
}) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const dim = size === "xs" ? 44 : size === "sm" ? 56 : 80;
  const r = size === "xs" ? 17 : size === "sm" ? 22 : 34;
  const stroke = size === "xs" ? 4.5 : size === "sm" ? 6 : 8;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  const half = dim / 2;
  return (
    <div
      className="relative shrink-0"
      style={{ width: dim, height: dim }}
      aria-label={value != null ? `Average score ${value}%` : "No score yet"}
    >
      <svg
        viewBox={`0 0 ${dim} ${dim}`}
        className="-rotate-90"
        style={{ width: dim, height: dim }}
        aria-hidden="true"
      >
        <circle
          cx={half}
          cy={half}
          r={r}
          fill="none"
          stroke="var(--color-line, #e7e5e4)"
          strokeWidth={stroke}
        />
        <circle
          cx={half}
          cy={half}
          r={r}
          fill="none"
          stroke="var(--color-accent, #1d4ed8)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={value == null ? c : offset}
        />
      </svg>
      <span
        className={`absolute inset-0 grid place-items-center font-semibold tabular-nums text-ink ${
          size === "xs" ? "text-[10px]" : size === "sm" ? "text-xs" : "text-sm"
        }`}
      >
        {value != null ? `${value}%` : "—"}
      </span>
    </div>
  );
}
