import type { ReactNode } from "react";
import Card from "./Card";

export default function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string;
  icon: ReactNode;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-ink-soft">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-ink">{value}</p>
        </div>
        <span
          aria-hidden="true"
          className="grid h-10 w-10 place-items-center rounded-lg bg-page text-ink-soft"
        >
          {icon}
        </span>
      </div>
    </Card>
  );
}
