import type { HTMLAttributes } from "react";

export default function Card({
  className = "",
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-lg border border-line bg-surface shadow-card ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
