import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import UserAvatar from "../components/UserAvatar";
import {
  api,
  type AssessmentSummary,
  type AssessmentsDashboard,
  type Track,
} from "../lib/api";

const TYPE_LABELS: Record<string, string> = {
  topic: "Topic",
  role: "Role",
  company_jd: "Company + JD",
};

const DEFAULT_MAX_QUESTIONS = 15;

type SortKey = "newest" | "oldest" | "highest_score";

function trackDescription(t: Track) {
  if (t.company) return `${t.company} · preparation track`;
  if (t.track_type === "topic") {
    return `${t.subject} fundamentals and problem solving.`;
  }
  if (t.track_type === "role") {
    return `Interview prep focused on the ${t.subject} role.`;
  }
  return "Preparation track with interviews, feedback, and progression.";
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function scoreDelta(assessments: AssessmentSummary[]): string | null {
  const scored = assessments
    .filter((a) => a.overall_score != null)
    .slice()
    .sort(
      (a, b) =>
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
    );
  if (scored.length < 2) return null;
  const mid = Math.floor(scored.length / 2);
  const older = scored.slice(0, mid);
  const newer = scored.slice(mid);
  const avg = (xs: AssessmentSummary[]) =>
    xs.reduce((s, a) => s + (a.overall_score ?? 0), 0) / xs.length;
  const delta = Math.round(avg(newer) - avg(older));
  if (delta === 0) return "0%";
  return `${delta > 0 ? "+" : ""}${delta}%`;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");
  const [topicFilter, setTopicFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("newest");
  const [menuTrackId, setMenuTrackId] = useState<string | null>(null);
  const [form, setForm] = useState({
    track_type: "topic",
    subject: "",
    company: "",
    jd_text: "",
  });

  const tracks = useQuery({
    queryKey: ["tracks"],
    queryFn: () => api<Track[]>("/tracks"),
  });

  const assessments = useQuery({
    queryKey: ["me-assessments"],
    queryFn: () => api<AssessmentsDashboard>("/me/assessments"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<{ track: Track }>("/tracks", {
        method: "POST",
        body: JSON.stringify({
          track_type: form.track_type,
          subject: form.subject,
          company: form.company || null,
          jd_text: form.track_type === "company_jd" ? form.jd_text : null,
        }),
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({ track_type: "topic", subject: "", company: "", jd_text: "" });
      qc.invalidateQueries({ queryKey: ["tracks"] });
    },
  });

  const trackList = tracks.data ?? [];
  const assessmentList = assessments.data?.assessments ?? [];
  const dash = assessments.data?.dashboard;

  const topicOptions = useMemo(() => {
    const list = tracks.data ?? [];
    return [...new Set(list.map((t) => t.subject))].sort();
  }, [tracks.data]);

  const byTrack = useMemo(() => {
    const map = new Map<
      string,
      { attempts: number; best: number | null; latest: AssessmentSummary | null }
    >();
    for (const a of assessments.data?.assessments ?? []) {
      const cur = map.get(a.track_id) ?? {
        attempts: 0,
        best: null as number | null,
        latest: null as AssessmentSummary | null,
      };
      cur.attempts += 1;
      if (a.overall_score != null) {
        cur.best =
          cur.best == null ? a.overall_score : Math.max(cur.best, a.overall_score);
      }
      if (
        !cur.latest ||
        new Date(a.created_at) > new Date(cur.latest.created_at)
      ) {
        cur.latest = a;
      }
      map.set(a.track_id, cur);
    }
    return map;
  }, [assessments.data]);

  const filteredTracks = useMemo(() => {
    let list = [...(tracks.data ?? [])];
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (t) =>
          t.subject.toLowerCase().includes(q) ||
          (t.company ?? "").toLowerCase().includes(q) ||
          t.track_type.toLowerCase().includes(q),
      );
    }
    if (topicFilter !== "all") {
      list = list.filter((t) => t.subject === topicFilter);
    }
    list.sort((a, b) => {
      if (sortKey === "oldest") {
        return (
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        );
      }
      if (sortKey === "highest_score") {
        const sa = byTrack.get(a.id)?.best ?? -1;
        const sb = byTrack.get(b.id)?.best ?? -1;
        return sb - sa;
      }
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
    return list;
  }, [tracks.data, search, topicFilter, sortKey, byTrack]);

  const progressLabel = scoreDelta(assessmentList);
  const recent = assessmentList.slice(0, 5);
  const avgScore = dash?.average_score ?? null;
  const interviewsTaken = dash?.completed_interviews ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            Preparation tracks
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Each track has its own interviews, feedback, and progression.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-indigo-200 hover:bg-indigo-700"
        >
          {showForm ? (
            "Cancel"
          ) : (
            <>
              <span className="text-base leading-none">+</span> New track
            </>
          )}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="space-y-3 rounded-2xl border border-indigo-100 bg-white p-5 shadow-sm"
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">
              <span className="text-slate-500">Type</span>
              <select
                value={form.track_type}
                onChange={(e) => setForm({ ...form, track_type: e.target.value })}
                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2"
              >
                <option value="topic">Topic (e.g. DSA)</option>
                <option value="role">Role (e.g. Backend Intern)</option>
                <option value="company_jd">Company + JD</option>
              </select>
            </label>
            <label className="text-sm sm:col-span-2">
              <span className="text-slate-500">Subject / role</span>
              <input
                required
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="Data Structures & Algorithms"
                className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2"
              />
            </label>
          </div>
          {form.track_type === "company_jd" && (
            <>
              <label className="block text-sm">
                <span className="text-slate-500">Company</span>
                <input
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Acme Corp"
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2"
                />
              </label>
              <label className="block text-sm">
                <span className="text-slate-500">Job description</span>
                <textarea
                  required
                  value={form.jd_text}
                  onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
                  rows={4}
                  placeholder="Paste the JD here — the architect derives requirements only from this text."
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2"
                />
              </label>
            </>
          )}
          {create.error instanceof Error && (
            <p className="text-sm text-red-600">{create.error.message}</p>
          )}
          <button
            disabled={create.isPending}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {create.isPending
              ? "Interview Architect is designing your brief and question bank… (1–2 minutes on the free tier)"
              : "Create track"}
          </button>
        </form>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Tracks"
          value={String(trackList.length)}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M4 19h4V9H4v10Zm6 0h4V5h-4v14Zm6 0h4v-7h-4v7Z" />
            </svg>
          }
          tone="indigo"
        />
        <StatCard
          label="Interviews Taken"
          value={assessments.isLoading ? "…" : String(interviewsTaken)}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M8 5v14l11-7L8 5Z" />
            </svg>
          }
          tone="sky"
        />
        <StatCard
          label="Avg. Score"
          value={
            assessments.isLoading
              ? "…"
              : avgScore != null
                ? `${avgScore}%`
                : "—"
          }
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M12 2 9.5 8.5 2 9.3l5.5 4.7L5.8 21 12 17.3 18.2 21l-1.7-7 5.5-4.7-7.5-.8L12 2Z" />
            </svg>
          }
          tone="amber"
        />
        <StatCard
          label="Progress"
          value={
            assessments.isLoading ? "…" : (progressLabel ?? "—")
          }
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l5-5 4 4 7-8" />
            </svg>
          }
          tone="emerald"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative min-w-0 flex-1">
              <span className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-slate-400">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="7" />
                  <path strokeLinecap="round" d="m20 20-3-3" />
                </svg>
              </span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tracks (e.g., arrays, dp, system design…)"
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pr-3 pl-10 text-sm outline-none ring-indigo-100 focus:border-indigo-300 focus:ring-2"
              />
            </label>
            <select
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
              aria-label="Filter by topic"
            >
              <option value="all">All Topics</option>
              {topicOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700"
              aria-label="Sort tracks"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="highest_score">Highest Score</option>
            </select>
          </div>

          {tracks.isLoading && (
            <p className="text-sm text-slate-400">Loading tracks…</p>
          )}
          {tracks.error instanceof Error && (
            <p className="text-sm text-red-600">{tracks.error.message}</p>
          )}
          {!tracks.isLoading && filteredTracks.length === 0 && (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/70 px-5 py-10 text-center">
              <p className="text-sm font-medium text-slate-700">
                {trackList.length === 0
                  ? "No tracks yet — create your first one."
                  : "No tracks match your search."}
              </p>
            </div>
          )}

          <div className="space-y-3">
            {filteredTracks.map((t) => {
              const stats = byTrack.get(t.id);
              const attempts = stats?.attempts ?? 0;
              const best = stats?.best;
              const latest = stats?.latest;
              return (
                <article
                  key={t.id}
                  className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm shadow-slate-200/40 sm:p-5"
                >
                  <div className="flex flex-wrap items-start gap-4">
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-indigo-100 text-indigo-600">
                      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor">
                        <path d="M4 6h16v2H4V6Zm2 5h16v2H6v-2Zm-2 5h16v2H4v-2Z" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700">
                          {TYPE_LABELS[t.track_type] ?? t.track_type}
                        </span>
                        {t.status !== "active" && (
                          <span className="text-[11px] text-slate-400">{t.status}</span>
                        )}
                      </div>
                      <Link
                        to={`/tracks/${t.id}`}
                        className="mt-1 block text-lg font-semibold text-slate-900 hover:text-indigo-700"
                      >
                        {t.subject}
                      </Link>
                      <p className="mt-0.5 text-sm text-slate-500">
                        {trackDescription(t)}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        <span>{DEFAULT_MAX_QUESTIONS} Questions</span>
                        <span>
                          {attempts} Attempt{attempts === 1 ? "" : "s"}
                        </span>
                        <span>
                          Best: {best != null ? `${best}%` : "—"}
                        </span>
                      </div>
                    </div>
                    <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto sm:justify-end">
                      {latest ? (
                        <Link
                          to={`/tracks/${t.id}/report/${latest.session_id}`}
                          className="rounded-xl border border-indigo-100 bg-indigo-50 px-3.5 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100"
                        >
                          View Report
                        </Link>
                      ) : (
                        <span
                          className="rounded-xl border border-slate-100 bg-slate-50 px-3.5 py-2 text-sm font-medium text-slate-400"
                          title="Complete an interview to unlock a report"
                        >
                          View Report
                        </span>
                      )}
                      <Link
                        to={`/tracks/${t.id}`}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
                      >
                        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
                          <path d="M8 5v14l11-7L8 5Z" />
                        </svg>
                        Start Interview
                      </Link>
                      <div className="relative">
                        <button
                          type="button"
                          aria-label="Track options"
                          onClick={() =>
                            setMenuTrackId((id) => (id === t.id ? null : t.id))
                          }
                          className="grid h-9 w-9 place-items-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        >
                          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
                            <circle cx="12" cy="5" r="1.5" />
                            <circle cx="12" cy="12" r="1.5" />
                            <circle cx="12" cy="19" r="1.5" />
                          </svg>
                        </button>
                        {menuTrackId === t.id && (
                          <div className="absolute right-0 z-10 mt-1 w-40 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                            <Link
                              to={`/tracks/${t.id}`}
                              onClick={() => setMenuTrackId(null)}
                              className="block px-3 py-2 text-sm text-slate-700 hover:bg-indigo-50"
                            >
                              Open track
                            </Link>
                            {latest && (
                              <Link
                                to={`/tracks/${t.id}/report/${latest.session_id}`}
                                onClick={() => setMenuTrackId(null)}
                                className="block px-3 py-2 text-sm text-slate-700 hover:bg-indigo-50"
                              >
                                Latest report
                              </Link>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 text-center shadow-sm">
            <div className="mx-auto w-fit">
              <UserAvatar
                name={user?.name}
                email={user?.email}
                pictureUrl={user?.picture_url}
                size="lg"
              />
            </div>
            <p className="mt-3 text-base font-semibold text-slate-900">
              {user?.name || "Your profile"}
            </p>
            <p className="mt-0.5 truncate text-sm text-slate-500">
              {user?.professional_title || "Add a professional title"}
            </p>
            <Link
              to="/profile"
              className="mt-4 inline-flex rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-100"
            >
              Edit Profile
            </Link>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-slate-800">
              Interview Progress
            </h2>
            <div className="mt-4 flex items-center gap-4">
              <ProgressRing value={avgScore} />
              <ul className="space-y-1.5 text-sm text-slate-600">
                <li>
                  <span className="font-semibold text-slate-900">
                    {interviewsTaken}
                  </span>{" "}
                  Assessments
                </li>
                <li>
                  <span className="font-semibold text-slate-900">—</span> In
                  Progress
                </li>
                <li>
                  <span className="font-semibold text-slate-900">
                    {trackList.length}
                  </span>{" "}
                  Track{trackList.length === 1 ? "" : "s"}
                </li>
              </ul>
            </div>
            <p className="mt-3 text-[11px] text-slate-400">
              In-progress sessions are not listed on this endpoint yet.
            </p>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-slate-800">
                Recent Activity
              </h2>
              <Link
                to="/profile#history"
                className="text-xs font-semibold text-indigo-600 hover:underline"
              >
                View All
              </Link>
            </div>
            {assessments.isLoading ? (
              <p className="mt-3 text-sm text-slate-400">Loading…</p>
            ) : recent.length === 0 ? (
              <p className="mt-3 rounded-xl bg-slate-50 px-3 py-4 text-center text-xs text-slate-400">
                No completed assessments yet.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {recent.map((a) => (
                  <li key={a.report_id} className="flex gap-2.5">
                    <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m5 13 4 4L19 7" />
                      </svg>
                    </span>
                    <div className="min-w-0">
                      <Link
                        to={`/tracks/${a.track_id}/report/${a.session_id}`}
                        className="block truncate text-sm font-medium text-slate-800 hover:text-indigo-700"
                      >
                        {a.track_subject} Interview
                      </Link>
                      <p className="text-xs text-slate-500">
                        Completed
                        {a.overall_score != null
                          ? ` · Score: ${a.overall_score}%`
                          : ""}{" "}
                        · {formatDate(a.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon: ReactNode;
  tone: "indigo" | "sky" | "amber" | "emerald";
}) {
  const tones = {
    indigo: "bg-indigo-50 text-indigo-600",
    sky: "bg-sky-50 text-sky-600",
    amber: "bg-amber-50 text-amber-600",
    emerald: "bg-emerald-50 text-emerald-600",
  };
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm shadow-slate-200/40">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900">
            {value}
          </p>
        </div>
        <span className={`grid h-10 w-10 place-items-center rounded-xl ${tones[tone]}`}>
          {icon}
        </span>
      </div>
    </div>
  );
}

function ProgressRing({ value }: { value: number | null }) {
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const r = 34;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <div className="relative h-20 w-20 shrink-0">
      <svg viewBox="0 0 80 80" className="h-20 w-20 -rotate-90">
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke="#eef2ff"
          strokeWidth="8"
        />
        <circle
          cx="40"
          cy="40"
          r={r}
          fill="none"
          stroke="#6366f1"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={value == null ? c : offset}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-sm font-bold text-slate-900">
        {value != null ? `${value}%` : "—"}
      </span>
    </div>
  );
}
