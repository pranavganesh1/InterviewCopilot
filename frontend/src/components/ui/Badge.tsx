import type { HTMLAttributes } from "react";

export type BadgeTone = "neutral" | "success" | "warn" | "danger" | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-stone-100 text-stone-700",
  success: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  danger: "bg-red-100 text-red-800",
  info: "bg-accent-soft text-accent-strong",
};

export default function Badge({
  tone = "neutral",
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
      {...props}
    >
      {children}
    </span>
  );
}
