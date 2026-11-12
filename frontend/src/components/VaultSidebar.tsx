import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type VaultItem } from "../lib/api";

const PROJECT_DETAIL_KEYS = [
  "purpose",
  "technologies",
  "architecture",
  "contribution",
  "outcome",
  "features",
] as const;

const PROJECT_FIELD_LABELS: Record<string, string> = {
  purpose: "Problem",
  architecture: "Methods",
  technologies: "Tools",
  tools: "Tools",
  dataset: "Dataset",
  data: "Dataset",
  outcome: "Outcome",
  contribution: "Contribution",
  features: "Features",
};

type ProfileTab = "skills" | "projects" | "education" | "resume";

function invalidateVaultQueries(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["onboarding-state"] });
  qc.invalidateQueries({ queryKey: ["vault-items"] });
  qc.invalidateQueries({ queryKey: ["profile-review"] });
}

function techList(item: VaultItem): string[] {
  const raw =
    item.details?.technologies ||
    item.details?.tools ||
    item.details?.stack ||
    "";
  return String(raw)
    .split(/[,|/]/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function summaryLine(item: VaultItem): string {
  const d = item.details || {};
  return String(d.purpose || d.outcome || d.contribution || d.features || "").trim();
}

function labelledProjectRows(item: VaultItem): { label: string; value: string }[] {
  const d = item.details || {};
  const rows: { label: string; value: string }[] = [];
  const order = [
    "purpose",
    "architecture",
    "technologies",
    "tools",
    "dataset",
    "data",
    "outcome",
    "contribution",
    "features",
  ];
  const seen = new Set<string>();
  for (const key of order) {
    const value = String(d[key] || "").trim();
    if (!value) continue;
    const label = PROJECT_FIELD_LABELS[key] || key;
    if (seen.has(label)) continue;
    seen.add(label);
    rows.push({ label, value });
  }
  return rows;
}

function CompletenessRing({ percent }: { percent: number }) {
  const r = 16;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(100, Math.max(0, percent)) / 100);
  return (
    <div
      className="relative h-11 w-11 shrink-0"
      data-testid="profile-completeness-ring"
      aria-hidden
    >
      <svg viewBox="0 0 40 40" className="h-full w-full -rotate-90">
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          className="stroke-line"
          strokeWidth="3.5"
        />
        <circle
          cx="20"
          cy="20"
          r={r}
          fill="none"
          className="stroke-accent profile-ring-progress"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[10px] font-semibold text-ink">
        {percent}%
      </span>
    </div>
  );
}

export function VaultSidebar({
  items,
  loading = false,
  errorMessage,
  onRetry,
  percentComplete,
  nextHint,
  finished,
  canStartPreparing,
  finishPending,
  finishError,
  onGoToTracks,
  onFinish,
  resumePanel,
}: {
  items: VaultItem[];
  loading?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
  percentComplete: number;
  nextHint: string;
  finished: boolean;
  canStartPreparing: boolean;
  finishPending?: boolean;
  finishError?: string | null;
  onGoToTracks: () => void;
  onFinish: () => void;
  resumePanel: ReactNode;
}) {
  const qc = useQueryClient();
  const [tab, setTab] = useState<ProfileTab>("resume");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/vault/items/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidateVaultQueries(qc),
  });

  const save = useMutation({
    mutationFn: (payload: {
      id: string;
      title: string;
      details?: Record<string, string>;
    }) =>
      api<VaultItem>(`/vault/items/${payload.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: payload.title,
          details: payload.details,
        }),
      }),
    onSuccess: () => {
      setEditingId(null);
      invalidateVaultQueries(qc);
    },
  });

  const skills = items.filter((i) => i.category === "skill");
  const projects = items.filter((i) => i.category === "project");
  const education = items.filter((i) => i.category === "education");
  const busy = remove.isPending || save.isPending;

  const tabs: { id: ProfileTab; label: string; count: number }[] = [
    { id: "skills", label: "Skills", count: skills.length },
    { id: "projects", label: "Projects", count: projects.length },
    { id: "education", label: "Education", count: education.length },
    { id: "resume", label: "Resume", count: 0 },
  ];

  return (
    <div
      className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-3xl border border-line/80 bg-surface/85 shadow-card backdrop-blur-md"
      data-testid="profile-panel"
    >
      <div className="flex shrink-0 items-center gap-3 border-b border-line/70 px-4 py-3">
        <CompletenessRing percent={percentComplete} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink" data-testid="profile-completeness-label">
            Profile {percentComplete}% complete
          </p>
          <p className="truncate text-xs text-ink-soft">{nextHint}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!finished && canStartPreparing && (
            <button
              type="button"
              data-testid="finish-onboarding"
              onClick={onFinish}
              disabled={finishPending}
              className="hidden min-h-11 rounded-xl bg-accent px-3 text-xs font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 sm:inline-flex sm:items-center"
            >
              {finishPending ? "Saving…" : "Start Preparing"}
            </button>
          )}
          {finished ? (
            <button
              type="button"
              data-testid="go-to-tracks"
              onClick={onGoToTracks}
              aria-label="Go to Tracks"
              title="Go to Tracks"
              className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-xl bg-accent px-3 text-xs font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:min-w-0 sm:px-3.5"
            >
              <svg viewBox="0 0 16 16" className="h-4 w-4 sm:hidden" aria-hidden>
                <path
                  d="M3 8h10M9 4l4 4-4 4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="hidden sm:inline">Go to Tracks</span>
            </button>
          ) : canStartPreparing ? (
            <button
              type="button"
              data-testid="finish-onboarding-mobile"
              onClick={onFinish}
              disabled={finishPending}
              className="inline-flex min-h-11 items-center rounded-xl bg-accent px-3 text-xs font-semibold text-white sm:hidden disabled:opacity-50"
            >
              {finishPending ? "…" : "Start"}
            </button>
          ) : null}
        </div>
      </div>
      {finishError && (
        <p className="px-4 pt-2 text-center text-xs text-red-600">{finishError}</p>
      )}

      <div
        role="tablist"
        aria-label="Profile sections"
        data-testid="profile-tabs"
        className="relative flex shrink-0 gap-1 border-b border-line/70 px-2 pt-2"
      >
        {tabs.map((t) => {
          const selected = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`profile-tab-${t.id}`}
              aria-selected={selected}
              aria-controls={`profile-panel-${t.id}`}
              data-testid={`profile-tab-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setTab(t.id)}
              onKeyDown={(e) => {
                const idx = tabs.findIndex((x) => x.id === tab);
                if (e.key === "ArrowRight") {
                  e.preventDefault();
                  setTab(tabs[(idx + 1) % tabs.length].id);
                } else if (e.key === "ArrowLeft") {
                  e.preventDefault();
                  setTab(tabs[(idx - 1 + tabs.length) % tabs.length].id);
                }
              }}
              className={`relative min-h-11 flex-1 rounded-t-lg px-1 text-[11px] font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:text-xs ${
                selected ? "text-accent-strong" : "text-ink-soft hover:text-ink"
              }`}
            >
              {t.label}
              {t.id !== "resume" && (
                <span className="ml-1 text-ink-faint">{t.count}</span>
              )}
              {selected && (
                <span className="profile-tab-indicator absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-accent" />
              )}
            </button>
          );
        })}
      </div>

      <div
        className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain px-4 py-3"
        data-testid="profile-panel-scroll"
      >
        {loading && (
          <div className="space-y-2" data-testid="profile-skeleton" aria-busy="true">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-12 animate-pulse rounded-xl bg-accent-soft/60" />
            ))}
          </div>
        )}

        {!loading && errorMessage && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700" role="alert">
            <p>{errorMessage}</p>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="mt-2 font-semibold text-accent-strong underline-offset-2 hover:underline"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {!loading && !errorMessage && tab === "skills" && (
          <div
            role="tabpanel"
            id="profile-panel-skills"
            aria-labelledby="profile-tab-skills"
            data-testid="profile-tabpanel-skills"
            className="profile-item-fade"
          >
            {skills.length === 0 ? (
              <EmptyState
                title="No skills yet"
                body="Chat with Aiko or upload a resume to add skills."
              />
            ) : (
              <ul className="flex flex-wrap gap-2">
                {skills.map((item) =>
                  editingId === item.id ? (
                    <li key={item.id} className="w-full">
                      <SkillEditForm
                        title={item.title}
                        busy={busy}
                        onCancel={() => setEditingId(null)}
                        onSave={(title) => save.mutate({ id: item.id, title })}
                      />
                    </li>
                  ) : (
                    <li key={item.id} className="group relative">
                      <button
                        type="button"
                        onClick={() => setEditingId(item.id)}
                        className="rounded-full border border-accent/15 bg-accent-soft/80 px-3 py-1.5 text-xs font-medium text-accent-strong transition hover:-translate-y-0.5 hover:shadow-card focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                        title="Edit skill"
                      >
                        {item.title}
                      </button>
                      <button
                        type="button"
                        aria-label={`Remove ${item.title}`}
                        disabled={busy}
                        onClick={() => remove.mutate(item.id)}
                        className="absolute -right-1 -top-1 grid h-5 w-5 place-items-center rounded-full bg-surface text-[10px] text-ink-soft opacity-0 shadow-card ring-1 ring-line transition group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40"
                      >
                        ×
                      </button>
                    </li>
                  ),
                )}
              </ul>
            )}
          </div>
        )}

        {!loading && !errorMessage && tab === "projects" && (
          <div
            role="tabpanel"
            id="profile-panel-projects"
            aria-labelledby="profile-tab-projects"
            data-testid="profile-tabpanel-projects"
            className="space-y-2 profile-item-fade"
          >
            {projects.length === 0 ? (
              <EmptyState
                title="No projects yet"
                body="Share a project in chat — Aiko will save it here."
              />
            ) : (
              projects.map((item) => {
                const techs = techList(item);
                const open = expandedId === item.id;
                const rows = labelledProjectRows(item);
                if (editingId === item.id) {
                  return (
                    <ProjectEditForm
                      key={item.id}
                      item={item}
                      busy={busy}
                      onCancel={() => setEditingId(null)}
                      onSave={(title, details) =>
                        save.mutate({ id: item.id, title, details })
                      }
                    />
                  );
                }
                return (
                  <article
                    key={item.id}
                    data-testid={`vault-project-card-${item.id}`}
                    className="rounded-2xl border border-line/80 bg-surface p-3 transition hover:-translate-y-0.5 hover:shadow-card"
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        aria-expanded={open}
                        onClick={() =>
                          setExpandedId((id) => (id === item.id ? null : item.id))
                        }
                      >
                        <p className="text-sm font-semibold text-ink">{item.title}</p>
                        {summaryLine(item) && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-ink-soft">
                            {summaryLine(item)}
                          </p>
                        )}
                        {techs.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {techs.slice(0, 4).map((t) => (
                              <span
                                key={t}
                                className="rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] font-medium text-accent-strong"
                              >
                                {t}
                              </span>
                            ))}
                            {techs.length > 4 && (
                              <span className="text-[10px] text-ink-faint">
                                +{techs.length - 4}
                              </span>
                            )}
                          </div>
                        )}
                      </button>
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          type="button"
                          aria-label={`Edit ${item.title}`}
                          title="Edit"
                          onClick={() => setEditingId(item.id)}
                          className="grid h-9 w-9 place-items-center rounded-lg text-ink-soft hover:bg-accent-soft hover:text-accent-strong focus-visible:outline-2 focus-visible:outline-accent"
                        >
                          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                            <path
                              d="M2.5 11.5 11 3l2 2-8.5 8.5H2.5v-2Z"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.4"
                              strokeLinejoin="round"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          aria-label={`Remove ${item.title}`}
                          title="Remove"
                          disabled={busy}
                          onClick={() => remove.mutate(item.id)}
                          className="grid h-9 w-9 place-items-center rounded-lg text-ink-soft hover:bg-red-50 hover:text-red-600 focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-40"
                        >
                          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                            <path
                              d="M3 4.5h10M6 4.5V3h4v1.5M5.5 4.5l.5 8h4l.5-8"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.4"
                              strokeLinecap="round"
                            />
                          </svg>
                        </button>
                        <button
                          type="button"
                          aria-label={open ? "Collapse project" : "Expand project"}
                          aria-expanded={open}
                          onClick={() =>
                            setExpandedId((id) => (id === item.id ? null : item.id))
                          }
                          className="grid h-9 w-9 place-items-center rounded-lg text-ink-soft hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent"
                        >
                          <svg
                            viewBox="0 0 16 16"
                            className={`h-3.5 w-3.5 transition ${open ? "rotate-180" : ""}`}
                            aria-hidden
                          >
                            <path
                              d="M4 6.5 8 10.5 12 6.5"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="1.6"
                              strokeLinecap="round"
                            />
                          </svg>
                        </button>
                      </div>
                    </div>
                    {open && rows.length > 0 && (
                      <dl className="mt-3 space-y-2 border-t border-line/70 pt-3">
                        {rows.map((row) => (
                          <div key={row.label}>
                            <dt className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">
                              {row.label}
                            </dt>
                            <dd className="mt-0.5 text-xs text-ink">{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </article>
                );
              })
            )}
          </div>
        )}

        {!loading && !errorMessage && tab === "education" && (
          <div
            role="tabpanel"
            id="profile-panel-education"
            aria-labelledby="profile-tab-education"
            data-testid="profile-tabpanel-education"
            className="space-y-2 profile-item-fade"
          >
            {education.length === 0 ? (
              <EmptyState
                title="No education yet"
                body="Optional — add a degree or program whenever you’re ready."
              />
            ) : (
              <ol className="relative space-y-3 border-l border-accent/25 pl-4">
                {education.map((item) => {
                  const d = item.details || {};
                  const institution = String(d.institution || d.school || "").trim();
                  const degree = String(d.degree || d.field || item.title).trim();
                  const dates = String(d.dates || d.year || d.period || "").trim();
                  return (
                    <li key={item.id} className="relative">
                      <span className="absolute -left-[1.3rem] top-1.5 h-2.5 w-2.5 rounded-full bg-accent ring-2 ring-surface" />
                      <div className="rounded-2xl border border-line/80 bg-surface p-3 transition hover:-translate-y-0.5 hover:shadow-card">
                        <p className="text-sm font-semibold text-ink">{degree}</p>
                        {institution && (
                          <p className="text-xs text-ink-soft">{institution}</p>
                        )}
                        {dates && (
                          <p className="mt-1 text-[11px] text-ink-faint">{dates}</p>
                        )}
                        <div className="mt-2 flex gap-2">
                          <button
                            type="button"
                            className="text-[11px] font-medium text-accent-strong hover:underline"
                            onClick={() => setEditingId(item.id)}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            aria-label={`Remove ${item.title}`}
                            disabled={busy}
                            className="text-[11px] text-ink-faint hover:text-red-600 disabled:opacity-40"
                            onClick={() => remove.mutate(item.id)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                      {editingId === item.id && (
                        <div className="mt-2">
                          <ProjectEditForm
                            item={item}
                            busy={busy}
                            onCancel={() => setEditingId(null)}
                            onSave={(title, details) =>
                              save.mutate({ id: item.id, title, details })
                            }
                          />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        )}

        {!loading && !errorMessage && tab === "resume" && (
          <div
            role="tabpanel"
            id="profile-panel-resume"
            aria-labelledby="profile-tab-resume"
            data-testid="profile-tabpanel-resume"
            className="profile-item-fade"
          >
            {resumePanel}
          </div>
        )}

        {save.error instanceof Error && (
          <p className="mt-2 text-xs text-rose-600">{save.error.message}</p>
        )}
      </div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-line bg-accent-soft/30 px-4 py-8 text-center">
      <svg viewBox="0 0 48 48" className="mb-3 h-12 w-12 text-accent/50" aria-hidden>
        <rect x="8" y="12" width="32" height="24" rx="4" fill="currentColor" opacity="0.15" />
        <path
          d="M16 24h16M16 28h10"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
      <p className="text-sm font-medium text-ink">{title}</p>
      <p className="mt-1 text-xs text-ink-soft">{body}</p>
    </div>
  );
}

function SkillEditForm({
  title,
  busy,
  onCancel,
  onSave,
}: {
  title: string;
  busy: boolean;
  onCancel: () => void;
  onSave: (title: string) => void;
}) {
  const [draft, setDraft] = useState(title);
  return (
    <form
      className="flex flex-wrap items-center gap-1.5 rounded-xl border border-accent/30 bg-surface p-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!draft.trim() || busy) return;
        onSave(draft.trim());
      }}
    >
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={255}
        className="min-w-0 flex-1 rounded-lg border border-line px-2 py-1.5 text-xs outline-none focus:border-accent"
        aria-label="Skill name"
      />
      <button
        type="submit"
        disabled={busy || !draft.trim()}
        className="text-[11px] font-semibold text-accent-strong disabled:opacity-40"
      >
        Save
      </button>
      <button type="button" onClick={onCancel} className="text-[11px] text-ink-soft">
        Cancel
      </button>
    </form>
  );
}

function ProjectEditForm({
  item,
  busy,
  onCancel,
  onSave,
}: {
  item: VaultItem;
  busy: boolean;
  onCancel: () => void;
  onSave: (title: string, details: Record<string, string>) => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [details, setDetails] = useState<Record<string, string>>({});

  useEffect(() => {
    const existing = item.details || {};
    const keys =
      item.category === "project"
        ? [...PROJECT_DETAIL_KEYS]
        : Object.keys(existing).length
          ? Object.keys(existing)
          : ["institution", "degree", "dates"];
    const next: Record<string, string> = {};
    for (const key of keys) {
      next[key] = String(existing[key] || "");
    }
    setTitle(item.title);
    setDetails(next);
  }, [item]);

  return (
    <form
      className="space-y-2 rounded-2xl border border-accent/30 bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim() || busy) return;
        const cleaned: Record<string, string> = {};
        for (const [key, value] of Object.entries(details)) {
          cleaned[key] = value.trim();
        }
        onSave(title.trim(), cleaned);
      }}
    >
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        maxLength={255}
        className="w-full rounded-lg border border-line px-2 py-1.5 text-sm outline-none focus:border-accent"
        aria-label="Item title"
      />
      {Object.keys(details).map((key) => (
        <label key={key} className="block text-[11px] text-ink-soft">
          <span className="font-medium">
            {PROJECT_FIELD_LABELS[key] || key}
          </span>
          <input
            value={details[key] ?? ""}
            onChange={(e) =>
              setDetails((prev) => ({ ...prev, [key]: e.target.value }))
            }
            className="mt-0.5 w-full rounded-lg border border-line px-2 py-1 text-xs text-ink outline-none focus:border-accent"
          />
        </label>
      ))}
      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={busy || !title.trim()}
          className="rounded-lg bg-accent px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-2.5 py-1 text-[11px] text-ink-soft"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default VaultSidebar;
