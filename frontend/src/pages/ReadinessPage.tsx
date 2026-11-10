import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ReadinessClaim,
  type ReadinessResult,
  type Track,
} from "../lib/api";
import StartInterviewModal from "../components/StartInterviewModal";

const STATUS_LABEL: Record<ReadinessClaim["status"], string> = {
  clear: "Clear",
  add_detail: "Add detail",
  be_ready: "Be ready to explain",
};

const STATUS_CLASS: Record<ReadinessClaim["status"], string> = {
  clear: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  add_detail: "bg-amber-50 text-amber-900 ring-amber-200",
  be_ready: "bg-accent-soft text-accent-strong ring-accent/30",
};

function ClaimRow({ claim }: { claim: ReadinessClaim }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const expandable = claim.status !== "clear";

  async function copyPhrasing() {
    if (!claim.stronger_phrasing) return;
    try {
      await navigator.clipboard.writeText(claim.stronger_phrasing);
    } catch {
      /* Clipboard may be unavailable in some browsers; still acknowledge the action. */
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="rounded-md border border-line bg-white p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium text-ink">{claim.claim}</p>
        <span
          className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ${STATUS_CLASS[claim.status]}`}
        >
          {STATUS_LABEL[claim.status]}
        </span>
      </div>
      <blockquote className="mt-2 border-l-2 border-accent/40 pl-3 text-xs italic text-ink-soft">
        “{claim.excerpt}”
      </blockquote>
      {claim.status_reason && (
        <p className="mt-2 text-xs text-ink-soft">{claim.status_reason}</p>
      )}
      {expandable && (
        <div className="mt-3">
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="text-xs font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            {open ? "Hide preparation tips" : "Questions you may face"}
          </button>
          {open && (
            <div className="mt-2 space-y-3 rounded-md bg-page p-3">
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                  Questions you may face
                </h4>
                <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-ink">
                  {claim.questions.map((q) => (
                    <li key={q}>{q}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                  How to strengthen
                </h4>
                <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-ink">
                  {claim.tips.map((tip) => (
                    <li key={tip}>{tip}</li>
                  ))}
                </ul>
              </div>
              {claim.stronger_phrasing && (
                <div className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-line bg-white p-2.5">
                  <p className="min-w-0 flex-1 text-sm text-ink">
                    <span className="font-semibold">Stronger phrasing (if accurate): </span>
                    {claim.stronger_phrasing}
                  </p>
                  <button
                    type="button"
                    onClick={copyPhrasing}
                    className="shrink-0 rounded-md border border-line px-2 py-1 text-xs font-semibold text-ink hover:bg-page focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  >
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReadinessPage() {
  const [practiceOpen, setPracticeOpen] = useState(false);
  const [expandedEdit, setExpandedEdit] = useState<string | null>(null);

  const readiness = useMutation({
    mutationFn: (refresh: boolean) =>
      api<ReadinessResult>("/vault/readiness", {
        method: "POST",
        body: JSON.stringify({ refresh }),
      }),
  });

  const tracks = useQuery({
    queryKey: ["tracks"],
    queryFn: () => api<Track[]>("/tracks"),
  });

  useEffect(() => {
    readiness.mutate(false);
    // Intentionally once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const data = readiness.data;
  const practiceTrack = useMemo(() => {
    const list = tracks.data ?? [];
    const active = list.find((t) => !t.archived) ?? list[0];
    return active ? { id: active.id, subject: active.subject } : null;
  }, [tracks.data]);

  const summary = data?.summary ?? { clear: 0, add_detail: 0, be_ready: 0 };

  return (
    <div className="space-y-5" data-testid="readiness-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-accent">
            Preparation
          </p>
          <h1 className="text-xl font-semibold tracking-tight">Resume readiness</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-soft">
            See which resume claims interviewers often ask about — and how to explain them clearly.
          </p>
        </div>
        <button
          type="button"
          disabled={readiness.isPending}
          onClick={() => readiness.mutate(true)}
          className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink hover:bg-page disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          Refresh
        </button>
      </div>

      <p
        className="rounded-md border border-accent/20 bg-accent-soft/60 px-3 py-2 text-xs text-accent-strong"
        data-testid="readiness-disclaimer"
      >
        {data?.disclaimer ||
          "Based only on what your resume says. We cannot verify claims. This helps you prepare."}
      </p>

      {readiness.isPending && !data && (
        <div className="space-y-3" aria-busy="true" aria-label="Loading readiness">
          <div className="h-16 animate-pulse rounded-lg bg-page" />
          <div className="h-28 animate-pulse rounded-lg bg-page" />
          <div className="h-28 animate-pulse rounded-lg bg-page" />
        </div>
      )}

      {readiness.isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
          <p>
            {readiness.error instanceof ApiError
              ? readiness.error.message
              : "Could not run the readiness check."}
          </p>
          <button
            type="button"
            className="mt-2 font-semibold underline-offset-2 hover:underline"
            onClick={() => readiness.mutate(false)}
          >
            Retry
          </button>
        </div>
      )}

      {data?.empty && (
        <div
          className="rounded-lg border border-dashed border-line bg-surface p-6 text-center"
          data-testid="readiness-empty"
        >
          <h2 className="text-sm font-semibold text-ink">No projects yet</h2>
          <p className="mt-1 text-sm text-ink-soft">{data.empty_hint}</p>
          <Link
            to="/onboarding"
            className="mt-3 inline-flex rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-strong"
          >
            Add projects in onboarding
          </Link>
        </div>
      )}

      {data && !data.empty && (
        <>
          <div
            className="grid grid-cols-3 gap-2 sm:gap-3"
            data-testid="readiness-summary"
          >
            {(
              [
                ["clear", "Clear", summary.clear],
                ["add_detail", "Add detail", summary.add_detail],
                ["be_ready", "Be ready", summary.be_ready],
              ] as const
            ).map(([key, label, count]) => (
              <div
                key={key}
                className="rounded-lg border border-line bg-surface p-3 text-center shadow-card"
              >
                <p className="text-[11px] font-medium uppercase tracking-wide text-ink-soft">
                  {label}
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-ink">{count}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={!practiceTrack || (data.claim_seeds?.length ?? 0) === 0}
              onClick={() => setPracticeOpen(true)}
              className="rounded-md bg-accent px-3 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Practice these claims
            </button>
            <Link
              to="/onboarding"
              className="rounded-md border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink hover:bg-page"
            >
              Edit profile
            </Link>
          </div>

          {(data.consistency_hints?.length ?? 0) > 0 && (
            <section className="rounded-lg border border-line bg-surface p-4">
              <h2 className="text-sm font-semibold text-ink">Connections to prepare</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-soft">
                {data.consistency_hints.map((hint) => (
                  <li key={hint.message}>{hint.message}</li>
                ))}
              </ul>
            </section>
          )}

          <div className="space-y-4">
            {data.items.map((item) => (
              <section
                key={item.vault_item_id}
                className="rounded-lg border border-line bg-surface p-4 shadow-card"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                      {item.category}
                    </p>
                    <h2 className="truncate text-base font-semibold text-ink" title={item.title}>
                      {item.title}
                    </h2>
                  </div>
                  <Link
                    to="/onboarding"
                    onClick={() => setExpandedEdit(item.vault_item_id)}
                    className="text-xs font-semibold text-accent-strong underline-offset-2 hover:underline"
                  >
                    Edit in vault
                  </Link>
                </div>
                <div className="mt-3 space-y-2">
                  {item.claims.length === 0 ? (
                    <p className="text-sm text-ink-faint">No probe-worthy claims spotted here.</p>
                  ) : (
                    item.claims.map((claim) => (
                      <ClaimRow key={`${item.vault_item_id}-${claim.excerpt}`} claim={claim} />
                    ))
                  )}
                </div>
                {expandedEdit === item.vault_item_id && (
                  <p className="sr-only">Opening vault editor for {item.title}</p>
                )}
              </section>
            ))}
          </div>
        </>
      )}

      <StartInterviewModal
        track={practiceOpen ? practiceTrack : null}
        onClose={() => setPracticeOpen(false)}
        initialUseResume
        claimSeeds={data?.claim_seeds ?? []}
      />
    </div>
  );
}
