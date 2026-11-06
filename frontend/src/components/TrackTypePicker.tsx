import { useRef } from "react";

const TYPES = [
  {
    value: "topic",
    title: "Topic",
    hint: "Practice a subject, e.g. DSA, DBMS, Thermodynamics",
    icon: (
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" />
      </svg>
    ),
  },
  {
    value: "role",
    title: "Role",
    hint: "Prepare for a job role, e.g. Backend Intern",
    icon: (
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="3" />
        <path strokeLinecap="round" d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    value: "company_jd",
    title: "Company + JD",
    hint: "Paste a job description and company",
    icon: (
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 21h18M6 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M9 8h.01M9 12h.01M9 16h.01M15 8h.01M15 12h.01M15 16h.01" />
      </svg>
    ),
  },
] as const;

export type TrackTypeValue = (typeof TYPES)[number]["value"];

type Props = {
  value: string;
  onChange: (value: TrackTypeValue) => void;
};

export default function TrackTypePicker({ value, onChange }: Props) {
  const buttons = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (from: number, direction: number) => {
    const next = (from + direction + TYPES.length) % TYPES.length;
    buttons.current[next]?.focus();
  };

  return (
    <div role="radiogroup" aria-label="Track type" className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {TYPES.map((type, index) => {
        const selected = value === type.value;
        return (
          <button
            key={type.value}
            ref={(node) => {
              buttons.current[index] = node;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected || (index === 0 && !TYPES.some((item) => item.value === value)) ? 0 : -1}
            onClick={() => onChange(type.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                event.preventDefault();
                move(index, 1);
              } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                event.preventDefault();
                move(index, -1);
              } else if (event.key === " " || event.key === "Enter") {
                event.preventDefault();
                onChange(type.value);
              }
            }}
            className={`relative flex min-h-11 min-w-0 flex-col items-start gap-2 rounded-lg border p-4 text-left transition hover:border-accent/40 hover:bg-accent-soft/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              selected
                ? "border-accent bg-accent-soft"
                : "border-line bg-white"
            }`}
          >
            <span className="flex w-full items-center gap-2 text-accent-strong">
              {type.icon}
              <span className="min-w-0 flex-1 text-sm font-semibold text-ink">{type.title}</span>
              {selected && (
                <svg viewBox="0 0 20 20" className="h-5 w-5 shrink-0 text-accent" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M16.7 5.3a1 1 0 0 1 0 1.4l-7.2 7.2a1 1 0 0 1-1.4 0L3.3 9.1a1 1 0 1 1 1.4-1.4l4.1 4.1 6.5-6.5a1 1 0 0 1 1.4 0Z" clipRule="evenodd" />
                </svg>
              )}
            </span>
            <span className="text-sm leading-snug text-ink-soft">{type.hint}</span>
          </button>
        );
      })}
    </div>
  );
}
