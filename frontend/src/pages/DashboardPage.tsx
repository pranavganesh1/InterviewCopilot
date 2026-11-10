import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import DeleteTrackDialog from "../components/DeleteTrackDialog";
import StartInterviewModal from "../components/StartInterviewModal";
import TrackOptionsMenu from "../components/TrackOptionsMenu";
import TrackTypePicker from "../components/TrackTypePicker";
import UserAvatar from "../components/UserAvatar";
import StatCard from "../components/ui/StatCard";
import ProgressRing from "../components/ui/ProgressRing";
import SectionHeader from "../components/ui/SectionHeader";
import {
  ApiError,
  api,
  type AssessmentSummary,
  type AssessmentsDashboard,
  type OpenSessionRow,
  type Track,
  type TrackWeaknesses,
} from "../lib/api";

const TYPE_LABELS: Record<string, string> = {
  topic: "Topic",
  role: "Role",
  company_jd: "Company + JD",
};

const DEFAULT_MAX_QUESTIONS = 15;
const SUBJECT_MAX = 255;
const COMPANY_MAX = 255;
const JD_MAX = 20000;

const TOPIC_CHIPS = [
  "Data Structures & Algorithms",
  "DBMS",
  "Operating Systems",
  "Computer Networks",
  "Python",
  "Java",
  "SQL",
  "Electronics",
  "Pharmacology",
  "World History",
];

const ROLE_CHIPS = [
  "Backend Intern",
  "Frontend Developer",
  "Data Analyst",
  "DevOps Engineer",
  "Software Engineer",
  "QA Engineer",
];

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

type PendingDelete = {
  track: Track;
  attempts: number;
  reports: number;
  returnFocus: HTMLElement | null;
};

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");
  const [topicFilter, setTopicFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("newest");
  const [showDeleted, setShowDeleted] = useState(false);
  const [menuTrackId, setMenuTrackId] = useState<string | null>(null);
  const [startTrack, setStartTrack] = useState<Track | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [leavingId, setLeavingId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ id: string; subject: string } | null>(null);
  const [finishError, setFinishError] = useState<string | null>(null);
  const [form, setForm] = useState({
    track_type: "topic",
    subject: "",
    company: "",
    jd_text: "",
  });
  const [touched, setTouched] = useState({ subject: false, company: false, jd: false });

  const tracks = useQuery({
    queryKey: ["tracks", showDeleted],
    queryFn: () =>
      api<Track[]>(showDeleted ? "/tracks?include_archived=true" : "/tracks"),
  });

  const assessments = useQuery({
    queryKey: ["me-assessments"],
    queryFn: () => api<AssessmentsDashboard>("/me/assessments"),
  });

  const openSessions = useQuery({
    queryKey: ["me-open-sessions"],
    queryFn: () => api<OpenSessionRow[]>("/me/open-sessions"),
  });

  const focusTrackId = (tracks.data ?? []).find((t) => !t.archived)?.id;
  const weaknesses = useQuery({
    queryKey: ["weaknesses", focusTrackId],
    enabled: Boolean(focusTrackId),
    retry: false,
    queryFn: () => api<TrackWeaknesses>(`/tracks/${focusTrackId}/weaknesses`),
  });

  const finishOpen = useMutation({
    mutationFn: async (row: OpenSessionRow) => {
      await api(`/sessions/${row.session_id}/complete`, { method: "POST" });
      return row;
    },
    onSuccess: (row) => {
      setFinishError(null);
      void qc.invalidateQueries({ queryKey: ["me-open-sessions"] });
      void qc.invalidateQueries({ queryKey: ["me-assessments"] });
      navigate(`/tracks/${row.track_id}/report/${row.session_id}`);
    },
    onError: (err) => {
      setFinishError(
        err instanceof ApiError ? err.message : "Could not finish this interview.",
      );
    },
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
      setTouched({ subject: false, company: false, jd: false });
      qc.invalidateQueries({ queryKey: ["tracks"] });
    },
  });

  const restore = useMutation({
    mutationFn: (id: string) => api(`/tracks/${id}/restore`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tracks"] });
      qc.invalidateQueries({ queryKey: ["me-assessments"] });
      qc.invalidateQueries({ queryKey: ["me-open-sessions"] });
    },
  });

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 6000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const subjectError =
    form.subject.length > SUBJECT_MAX
      ? `Use ${SUBJECT_MAX} characters or fewer.`
      : touched.subject && !form.subject.trim()
        ? form.track_type === "role" || form.track_type === "company_jd"
          ? "Enter a role."
          : "Enter a subject."
        : "";
  const companyError =
    form.company.length > COMPANY_MAX ? `Use ${COMPANY_MAX} characters or fewer.` : "";
  const jdError =
    form.jd_text.length > JD_MAX
      ? "Job description must be 20,000 characters or fewer."
      : touched.jd && form.track_type === "company_jd" && !form.jd_text.trim()
        ? "Paste a job description."
        : "";
  const formReady =
    form.subject.trim().length > 0 &&
    form.subject.length <= SUBJECT_MAX &&
    form.company.length <= COMPANY_MAX &&
    (form.track_type !== "company_jd" ||
      (form.jd_text.trim().length > 0 && form.jd_text.length <= JD_MAX));

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

  const visibleAssessments = assessmentList.filter((item) => !item.track_archived);
  const activeTrackCount = trackList.filter((item) => !item.archived).length;
  const progressLabel = scoreDelta(visibleAssessments);
  const recent = visibleAssessments.slice(0, 5);
  const avgScore = dash?.average_score ?? null;
  const interviewsTaken = dash?.completed_interviews ?? 0;
  const openList = openSessions.data ?? [];
  const inProgressCount = openList.length;

  function closeDeleteDialog() {
    const focus = pendingDelete?.returnFocus;
    setPendingDelete(null);
    focus?.focus();
  }

  function onTrackDeleted(track: Track) {
    setPendingDelete(null);
    setLeavingId(track.id);
    const wait = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 160;
    window.setTimeout(() => {
      setLeavingId(null);
      qc.setQueryData<Track[]>(["tracks", showDeleted], (current) =>
        (current ?? []).filter((item) => item.id !== track.id),
      );
      void qc.invalidateQueries({ queryKey: ["tracks"] });
      void qc.invalidateQueries({ queryKey: ["me-assessments"] });
      void qc.invalidateQueries({ queryKey: ["me-open-sessions"] });
      setToast({ id: track.id, subject: track.subject });
    }, wait);
  }

  async function undoDelete() {
    if (!toast) return;
    const target = toast;
    setToast(null);
    await restore.mutateAsync(target.id);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader
          title="Preparation tracks"
          subtitle="Each track has its own interviews, feedback, and progression."
        />
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-card hover:bg-accent-strong"
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
            setTouched({ subject: true, company: true, jd: true });
            if (!formReady || create.isPending) return;
            create.mutate();
          }}
          className="min-w-0 space-y-5 rounded-lg border border-line bg-white p-5 shadow-card sm:p-6"
        >
          <div>
            <h2 className="text-lg font-semibold text-ink">Create a new track</h2>
            <p className="mt-1 text-sm text-ink-soft">
              Choose a type, then name what you want to practice. Suggestions only fill the box.
            </p>
          </div>
          <TrackTypePicker
            value={form.track_type}
            onChange={(track_type) => setForm({ ...form, track_type })}
          />
          <div key={form.track_type} className="track-fields space-y-4">
            {form.track_type === "company_jd" && (
              <label className="block text-sm">
                <span className="font-medium text-ink-soft">Company</span>
                <input
                  value={form.company}
                  maxLength={COMPANY_MAX}
                  onBlur={() => setTouched((current) => ({ ...current, company: true }))}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Acme Corp"
                  aria-invalid={companyError ? true : undefined}
                  className="mt-1.5 min-h-11 w-full rounded-md border border-line px-3 py-2.5 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 focus-visible:outline-none"
                />
                {companyError && <p className="mt-1 text-sm text-red-600">{companyError}</p>}
              </label>
            )}
            <div>
              <label className="block text-sm" htmlFor="track-subject">
                <span className="font-medium text-ink-soft">
                  {form.track_type === "topic" ? "Subject" : "Role"}
                </span>
                <input
                  id="track-subject"
                  value={form.subject}
                  maxLength={SUBJECT_MAX}
                  onBlur={() => setTouched((current) => ({ ...current, subject: true }))}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder={
                    form.track_type === "topic"
                      ? "Data Structures & Algorithms"
                      : "Backend Intern"
                  }
                  aria-invalid={subjectError ? true : undefined}
                  aria-describedby={subjectError ? "track-subject-error" : undefined}
                  className="mt-1.5 min-h-11 w-full rounded-md border border-line px-3 py-2.5 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 focus-visible:outline-none"
                />
              </label>
              {subjectError && (
                <p id="track-subject-error" className="mt-1 text-sm text-red-600">
                  {subjectError}
                </p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {(form.track_type === "role" ? ROLE_CHIPS : form.track_type === "topic" ? TOPIC_CHIPS : []).map(
                  (chip) => (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => setForm({ ...form, subject: chip })}
                      className="min-h-11 rounded-full border border-line bg-accent-soft px-3 text-sm font-medium text-accent-strong hover:border-accent/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      {chip}
                    </button>
                  ),
                )}
              </div>
            </div>
            {form.track_type === "company_jd" && (
              <label className="block text-sm">
                <span className="font-medium text-ink-soft">Job description</span>
                <textarea
                  required
                  value={form.jd_text}
                  maxLength={JD_MAX}
                  rows={6}
                  onBlur={() => setTouched((current) => ({ ...current, jd: true }))}
                  onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
                  placeholder="Paste the job description here."
                  aria-invalid={jdError ? true : undefined}
                  aria-describedby={jdError ? "track-jd-error" : "track-jd-count"}
                  className="mt-1.5 w-full rounded-md border border-line px-3 py-2.5 outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 focus-visible:outline-none"
                />
                <span id="track-jd-count" className="mt-1 block text-right text-xs text-ink-soft">
                  {form.jd_text.length.toLocaleString()} / {JD_MAX.toLocaleString()}
                </span>
                {jdError && (
                  <p id="track-jd-error" className="mt-1 text-sm text-red-600">
                    {jdError}
                  </p>
                )}
              </label>
            )}
          </div>
          {create.error instanceof Error && (
            <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {create.error.message}
            </p>
          )}
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="min-h-11 w-full rounded-md border border-line bg-white px-4 text-sm font-semibold text-ink-soft hover:bg-page focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent sm:w-auto"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!formReady || create.isPending}
              className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50 sm:w-auto"
            >
              {create.isPending && (
                <svg viewBox="0 0 24 24" className="h-4 w-4 motion-reduce:animate-none animate-spin" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
                  <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
              )}
              Create track
            </button>
          </div>
        </form>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Tracks"
          value={String(activeTrackCount)}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M4 19h4V9H4v10Zm6 0h4V5h-4v14Zm6 0h4v-7h-4v7Z" />
            </svg>
          }
        />
        <StatCard
          label="Interviews Taken"
          value={assessments.isLoading ? "…" : String(interviewsTaken)}
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M8 5v14l11-7L8 5Z" />
            </svg>
          }
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
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="relative min-w-0 flex-1">
              <span className="pointer-events-none absolute inset-y-0 left-3 grid place-items-center text-ink-faint">
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="7" />
                  <path strokeLinecap="round" d="m20 20-3-3" />
                </svg>
              </span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tracks (e.g., arrays, dp, system design…)"
                className="w-full rounded-md border border-line bg-white py-2.5 pr-3 pl-10 text-sm outline-none ring-accent/20 focus:border-accent/40 focus:ring-2"
              />
            </label>
            <button
              type="button"
              aria-pressed={showDeleted}
              onClick={() => setShowDeleted((value) => !value)}
              className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                showDeleted
                  ? "border-accent/40 bg-accent-soft text-accent-strong"
                  : "border-line bg-white text-ink-soft"
              }`}
            >
              Show deleted
            </button>
            <select
              value={topicFilter}
              onChange={(e) => setTopicFilter(e.target.value)}
              className="rounded-md border border-line bg-white px-3 py-2.5 text-sm text-ink-soft"
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
              className="rounded-md border border-line bg-white px-3 py-2.5 text-sm text-ink-soft"
              aria-label="Sort tracks"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="highest_score">Highest Score</option>
            </select>
          </div>

          {tracks.isLoading && (
            <p className="text-sm text-ink-faint">Loading tracks…</p>
          )}
          {tracks.error instanceof Error && (
            <p className="text-sm text-red-600">{tracks.error.message}</p>
          )}
          {!tracks.isLoading && filteredTracks.length === 0 && (
            <div className="rounded-lg border border-dashed border-line bg-surface/70 px-5 py-10 text-center">
              <p className="text-sm font-medium text-ink-soft">
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
                  className={`rounded-lg border border-line bg-white p-4 shadow-card sm:p-5 ${
                    menuTrackId === t.id ? "relative z-20" : "relative"
                  } ${t.archived ? "opacity-60" : ""} ${leavingId === t.id ? "track-card-leave" : ""}`}
                >
                  <div className="flex flex-wrap items-start gap-4">
                    <div className="grid h-12 w-12 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                      <svg viewBox="0 0 24 24" className="h-6 w-6" fill="currentColor">
                        <path d="M4 6h16v2H4V6Zm2 5h16v2H6v-2Zm-2 5h16v2H4v-2Z" />
                      </svg>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-md bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-strong">
                          {TYPE_LABELS[t.track_type] ?? t.track_type}
                        </span>
                        {t.status !== "active" && (
                          <span className="text-[11px] text-ink-faint">{t.status}</span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (!t.archived) setStartTrack(t);
                        }}
                        className="mt-1 block text-left text-lg font-semibold text-ink hover:text-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                      >
                        {t.subject}
                      </button>
                      <p className="mt-0.5 text-sm text-ink-soft">
                        {trackDescription(t)}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-soft">
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
                          className="rounded-md border border-line bg-accent-soft px-3.5 py-2 text-sm font-semibold text-accent-strong hover:bg-accent-soft"
                        >
                          View Report
                        </Link>
                      ) : (
                        <span
                          className="rounded-md border border-line bg-page px-3.5 py-2 text-sm font-medium text-ink-faint"
                          title="Complete an interview to unlock a report"
                        >
                          View Report
                        </span>
                      )}
                      {t.archived ? (
                        <button
                          type="button"
                          disabled={restore.isPending}
                          onClick={() => restore.mutate(t.id)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-3.5 py-2 text-sm font-semibold text-accent-strong hover:bg-accent-soft disabled:opacity-60"
                        >
                          Restore
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setStartTrack(t)}
                          className="inline-flex items-center gap-1.5 rounded-md bg-accent px-3.5 py-2 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                        >
                          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
                            <path d="M8 5v14l11-7L8 5Z" />
                          </svg>
                          Start Interview
                        </button>
                      )}
                      <TrackOptionsMenu
                        trackId={t.id}
                        open={menuTrackId === t.id}
                        latestReportTo={
                          latest ? `/tracks/${t.id}/report/${latest.session_id}` : null
                        }
                        showDelete={!t.archived}
                        onToggle={() =>
                          setMenuTrackId((id) => (id === t.id ? null : t.id))
                        }
                        onClose={() => setMenuTrackId(null)}
                        onDelete={(button) =>
                          setPendingDelete({
                            track: t,
                            attempts,
                            reports: attempts,
                            returnFocus: button,
                          })
                        }
                      />
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-lg border border-line bg-white p-5 text-center">
            <div className="mx-auto w-fit">
              <UserAvatar
                name={user?.name}
                email={user?.email}
                pictureUrl={user?.picture_url}
                size="lg"
              />
            </div>
            <p className="mt-3 text-base font-semibold text-ink">
              {user?.name || "Your profile"}
            </p>
            <p className="mt-0.5 truncate text-sm text-ink-soft">
              {user?.professional_title || "Add a professional title"}
            </p>
            <Link
              to="/profile"
              className="mt-4 inline-flex rounded-md border border-line bg-accent-soft px-4 py-2 text-sm font-semibold text-accent-strong hover:bg-accent-soft"
            >
              Edit Profile
            </Link>
          </div>

          <div className="rounded-lg border border-line bg-white p-5">
            <h2 className="text-sm font-semibold text-ink">
              Interview Progress
            </h2>
            <div className="mt-4 flex items-center gap-4">
              <ProgressRing value={avgScore} />
              <ul className="space-y-1.5 text-sm text-ink-soft">
                <li>
                  <span className="font-semibold text-ink">
                    {interviewsTaken}
                  </span>{" "}
                  Assessments
                </li>
                <li>
                  <span className="font-semibold text-ink">
                    {openSessions.isLoading ? "…" : inProgressCount}
                  </span>{" "}
                  In Progress
                </li>
                <li>
                  <span className="font-semibold text-ink">
                    {activeTrackCount}
                  </span>{" "}
                  Track{activeTrackCount === 1 ? "" : "s"}
                </li>
                <li>
                  <span className="font-semibold text-ink">
                    {weaknesses.isLoading
                      ? "…"
                      : weaknesses.data?.top_weak?.length ?? 0}
                  </span>{" "}
                  Weak areas
                </li>
              </ul>
            </div>
            {(weaknesses.data?.top_weak?.length ?? 0) > 0 && (
              <ul className="mt-3 space-y-1.5">
                {weaknesses.data!.top_weak.map((row) => (
                  <li
                    key={row.concept}
                    className="flex min-w-0 items-center justify-between gap-2 text-xs text-ink-soft"
                  >
                    <span className="truncate" title={row.concept}>
                      {row.concept}
                    </span>
                    <span className="shrink-0 font-semibold uppercase text-violet-700">
                      {row.status}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {finishError && (
              <p role="alert" className="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
                {finishError}
              </p>
            )}
            {openSessions.isLoading ? (
              <p className="mt-3 text-xs text-ink-faint">Loading open interviews…</p>
            ) : openList.length === 0 ? (
              <p className="mt-3 text-[11px] text-ink-faint">
                No unfinished interviews right now.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {openList.map((row) => {
                  const finishing =
                    finishOpen.isPending &&
                    finishOpen.variables?.session_id === row.session_id;
                  return (
                    <li
                      key={row.session_id}
                      className="min-w-0 rounded-md border border-line bg-page/60 p-3"
                    >
                      <p className="truncate text-sm font-medium text-ink">
                        {row.track_subject}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-soft">
                        Q{row.question_index}/{row.max_turns}
                        {" · "}
                        {row.answered_count} answered
                        {" · "}
                        {row.mode}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Link
                          to={`/tracks/${row.track_id}/interview/${row.session_id}`}
                          className="inline-flex rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong"
                        >
                          Resume
                        </Link>
                        <button
                          type="button"
                          disabled={finishOpen.isPending}
                          onClick={() => {
                            setFinishError(null);
                            finishOpen.mutate(row);
                          }}
                          className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink hover:bg-page disabled:opacity-60"
                        >
                          {finishing && (
                            <svg
                              viewBox="0 0 24 24"
                              className="h-3.5 w-3.5 animate-spin"
                              fill="none"
                              aria-hidden="true"
                            >
                              <circle
                                cx="12"
                                cy="12"
                                r="9"
                                stroke="currentColor"
                                strokeWidth="3"
                                opacity="0.25"
                              />
                              <path
                                d="M21 12a9 9 0 0 0-9-9"
                                stroke="currentColor"
                                strokeWidth="3"
                                strokeLinecap="round"
                              />
                            </svg>
                          )}
                          Finish and get feedback
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-line bg-white p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-ink">
                Recent Activity
              </h2>
              <Link
                to="/profile#history"
                className="text-xs font-semibold text-accent hover:underline"
              >
                View All
              </Link>
            </div>
            {assessments.isLoading ? (
              <p className="mt-3 text-sm text-ink-faint">Loading…</p>
            ) : recent.length === 0 ? (
              <p className="mt-3 rounded-md bg-page px-3 py-4 text-center text-xs text-ink-faint">
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
                        className="block truncate text-sm font-medium text-ink hover:text-accent-strong"
                      >
                        {a.track_subject} Interview
                      </Link>
                      <p className="text-xs text-ink-soft">
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
      <StartInterviewModal
        track={startTrack ? { id: startTrack.id, subject: startTrack.subject } : null}
        onClose={() => setStartTrack(null)}
      />
      {pendingDelete && (
        <DeleteTrackDialog
          track={pendingDelete.track}
          attempts={pendingDelete.attempts}
          reports={pendingDelete.reports}
          onCancel={closeDeleteDialog}
          onDeleted={() => onTrackDeleted(pendingDelete.track)}
        />
      )}
      {toast && (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 z-40 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-3 rounded-full bg-slate-900 px-4 py-2 text-sm text-white shadow-lg"
        >
          Track deleted
          <button
            type="button"
            onClick={() => void undoDelete()}
            className="font-semibold text-ink-faint hover:text-white"
          >
            Undo
          </button>
        </div>
      )}
    </div>
  );
}
