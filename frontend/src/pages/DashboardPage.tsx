import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import DeleteTrackDialog from "../components/DeleteTrackDialog";
import StartInterviewModal from "../components/StartInterviewModal";
import TrackOptionsMenu from "../components/TrackOptionsMenu";
import TrackTypePicker from "../components/TrackTypePicker";
import UserAvatar from "../components/UserAvatar";
import ProgressRing from "../components/ui/ProgressRing";
import SectionHeader from "../components/ui/SectionHeader";
import DashboardProgressChart from "../components/DashboardProgressChart";
import PreparationReviewPanel from "../components/PreparationReviewPanel";
import CompetencyOverview from "../components/CompetencyOverview";
import ProjectPrepPanel from "../components/ProjectPrepPanel";
import {
  ApiError,
  api,
  type AssessmentSummary,
  type AssessmentsDashboard,
  type CareerIntelligence,
  type NextAction,
  type OpenSessionRow,
  type ProfileReview,
  type RoadmapCompletion,
  type RoadmapStep,
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
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [search, setSearch] = useState("");
  const [topicFilter, setTopicFilter] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("newest");
  const [showDeleted, setShowDeleted] = useState(false);
  const [menuTrackId, setMenuTrackId] = useState<string | null>(null);
  const [startTrack, setStartTrack] = useState<Track | null>(null);
  const [startFocusWeak, setStartFocusWeak] = useState(false);
  const [startDefenseMode, setStartDefenseMode] = useState(false);
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
    refetchInterval: (query) => {
      const hasAuthoring = query.state.data?.some(
        (t) => t.brief_status === "authoring",
      );
      return hasAuthoring ? 2500 : false;
    },
  });

  const profileReview = useQuery({
    queryKey: ["profile-review"],
    enabled: Boolean(user?.onboarding_completed),
    queryFn: () => api<ProfileReview>("/onboarding/review"),
  });

  const saveReview = useMutation({
    mutationFn: (body: {
      summary?: string;
      item_statuses?: {
        item_id: string;
        status: "confirmed" | "needs_clarification" | "not_assessed";
        reason?: string;
      }[];
    }) =>
      api<ProfileReview>("/onboarding/review", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["profile-review"], data);
      void refresh();
    },
  });

  const startRecommended = useMutation({
    mutationFn: (payload?: {
      subject?: string;
      track_type?: string;
    }) =>
      api<{ track: Track; created: boolean; review: ProfileReview }>(
        "/onboarding/review/start-recommended",
        {
          method: "POST",
          body: JSON.stringify(payload ?? {}),
        },
      ),
    onSuccess: (data) => {
      qc.setQueryData(["profile-review"], data.review);
      void qc.invalidateQueries({ queryKey: ["tracks"] });
      void refresh();
      navigate(`/tracks/${data.track.id}`);
    },
  });

  const refreshReview = useMutation({
    mutationFn: () =>
      api<ProfileReview>("/onboarding/review/refresh", { method: "POST" }),
    onSuccess: (data) => {
      qc.setQueryData(["profile-review"], data);
      void refresh();
    },
  });

  function handleNextAction(action: NextAction) {
    const kind = action.kind || "recommend_track";
    if (kind === "resume_session" && action.track_id && action.session_id) {
      navigate(`/tracks/${action.track_id}/interview/${action.session_id}`);
      return;
    }
    if (kind === "clarify_profile") {
      navigate("/onboarding");
      return;
    }
    if (kind === "practise_weakness" && action.track_id) {
      navigate(`/tracks/${action.track_id}`);
      return;
    }
    if (
      (kind === "create_track" ||
        kind === "recommend_track" ||
        kind === "practise_weakness") &&
      action.subject
    ) {
      if (action.reuse_existing && action.track_id) {
        navigate(`/tracks/${action.track_id}`);
        return;
      }
      startRecommended.mutate({
        subject: action.subject,
        track_type: action.track_type || "topic",
      });
      return;
    }
    // No subject yet — open the new-track form instead of inventing one.
    setShowForm(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const assessments = useQuery({
    queryKey: ["me-assessments"],
    queryFn: () => api<AssessmentsDashboard>("/me/assessments"),
  });
  const career = useQuery({
    queryKey: ["career-intelligence"],
    enabled: Boolean(user?.onboarding_completed),
    queryFn: () => api<CareerIntelligence>("/me/career-intelligence"),
    retry: false,
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

  const reauthor = useMutation({
    mutationFn: (id: string) => api(`/tracks/${id}/reauthor-brief`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tracks"] });
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
  const review = profileReview.data ?? user?.profile_review;

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
  const comparableProgress = career.data?.progress?.available === true;
  const progressLabel = comparableProgress
    ? scoreDelta(visibleAssessments)
    : null;
  const progressUnavailableNote =
    career.data?.progress?.comparison_note ||
    career.data?.progress?.reason ||
    (visibleAssessments.length < 2
      ? "Need more comparable interviews before showing a trend"
      : null);
  const recent = visibleAssessments.slice(0, 5);
  const avgScore = dash?.average_score ?? null;
  const interviewsTaken = dash?.completed_interviews ?? 0;
  const openList = openSessions.data ?? [];
  const inProgressCount = openList.length;
  const readinessScore = career.data?.career_readiness?.evidence_index ?? null;
  const readinessLevel = career.data?.career_readiness?.level;
  const readinessSummary = career.data?.career_readiness?.summary;
  const targetRole =
    career.data?.career_readiness?.target_role ||
    user?.preparation_preferences?.target_role ||
    null;
  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const interviewsThisWeek = visibleAssessments.filter(
    (a) => new Date(a.created_at).getTime() >= weekAgo,
  ).length;
  const chartPoints = useMemo(() => {
    const trend = career.data?.progress?.session_score_trend;
    if (trend && trend.length > 0) {
      return trend.slice(-5).map((row, idx) => ({
        label: `Interview ${idx + 1}`,
        overall: row.overall_score ?? null,
        technical: null as number | null,
      }));
    }
    return [...visibleAssessments]
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
      .slice(-5)
      .map((a, idx) => ({
        label: `Interview ${idx + 1}`,
        overall: a.overall_score,
        technical: null as number | null,
      }));
  }, [career.data?.progress?.session_score_trend, visibleAssessments]);
  const strengthItems =
    career.data?.strengths?.length
      ? career.data.strengths.slice(0, 4).map((s) => s.concept)
      : (dash?.strongest_skills ?? []).slice(0, 4);
  const improveItems =
    career.data?.improvement_areas?.length
      ? career.data.improvement_areas.slice(0, 4).map((s) => s.concept)
      : (dash?.skills_needing_improvement ?? []).slice(0, 4);
  const roadmapSteps =
    (review?.roadmap?.length ?? 0) > 0
      ? review!.roadmap.slice(0, 4)
      : (career.data?.roadmap ?? []).slice(0, 4).map((step, i) => ({
          id: `career-${step.order ?? i}`,
          title: step.topic || `Step ${i + 1}`,
          why: step.reason || "",
          topics: [] as string[],
          practise: step.activity || "",
          track_type: "topic",
          subject: step.track_subject || step.topic || "",
          action_label: "Start practice",
          priority: step.priority,
          // Career roadmap has no completion flag — do not invent one.
          completion: undefined as RoadmapCompletion | undefined,
          evidence: step.supporting_evidence || step.evidence_basis || "",
        }));
  const primaryNext =
    review?.next_action ||
    (career.data?.next_actions?.[0]
      ? {
          title: career.data.next_actions[0].title,
          reason: career.data.next_actions[0].reason,
          action_label: career.data.next_actions[0].action_label,
          href: career.data.next_actions[0].href,
          kind: undefined,
        }
      : null);
  const readinessLevelLabel: Record<string, string> = {
    insufficient_evidence: "Building evidence",
    early: "Early signal",
    building: "Building",
    developing: "Developing",
    needs_focused_practice: "Needs focus",
    strong_evidence: "Strong preparation",
  };
  const openSessionsErrorMessage =
    openSessions.error instanceof ApiError
      ? openSessions.error.message
      : openSessions.error instanceof Error
        ? openSessions.error.message
        : "Could not load open interviews.";
  const assessmentsErrorMessage =
    assessments.error instanceof ApiError
      ? assessments.error.message
      : assessments.error instanceof Error
        ? assessments.error.message
        : "Could not load assessments.";

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

  const reviewBusy =
    saveReview.isPending || startRecommended.isPending || refreshReview.isPending;
  const refreshReviewError = (() => {
    if (!refreshReview.isError) return null;
    if (refreshReview.error instanceof ApiError) {
      if (refreshReview.error.status === 429) {
        return (
          refreshReview.error.message ||
          "Please wait a moment before refreshing again."
        );
      }
      if (refreshReview.error.status === 503) {
        return (
          refreshReview.error.message ||
          "The model is busy right now — retry in a minute."
        );
      }
      return refreshReview.error.message;
    }
    if (refreshReview.error instanceof Error) {
      return refreshReview.error.message;
    }
    return "Could not refresh your preparation plan.";
  })();

  return (
    <div className="space-y-6">
      {user?.onboarding_completed && (
        <PreparationReviewPanel
          review={review}
          userName={user.name}
          pending={reviewBusy}
          refreshPending={refreshReview.isPending}
          refreshError={refreshReviewError}
          onRefresh={() => {
            if (refreshReview.isPending) return;
            refreshReview.mutate();
          }}
          onSaveSummary={(summary) => saveReview.mutate({ summary })}
          onSetItemStatus={(itemId, status) =>
            saveReview.mutate({
              item_statuses: [
                {
                  item_id: itemId,
                  status,
                  reason: "Confirmed by you from the dashboard.",
                },
              ],
            })
          }
          onNextAction={handleNextAction}
          onStartRecommended={(step?: RoadmapStep) =>
            startRecommended.mutate(
              step
                ? { subject: step.subject, track_type: step.track_type }
                : undefined,
            )
          }
          onBrowseTracks={() => {
            setShowForm(true);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      )}

      {user?.onboarding_completed && (
        <section className="space-y-4" data-testid="career-intelligence">
          {career.isError && (
            <div
              role="alert"
              data-testid="career-intelligence-error"
              className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
            >
              <p className="font-semibold">Couldn’t load career readiness</p>
              <p className="mt-1">
                {career.error instanceof ApiError
                  ? career.error.message
                  : career.error instanceof Error
                    ? career.error.message
                    : "Could not load career readiness."}
              </p>
              <button
                type="button"
                onClick={() => void career.refetch()}
                className="mt-2 text-sm font-semibold underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <article className="rounded-2xl border border-line bg-white p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                Career Readiness
              </p>
              <div className="mt-3 flex items-center gap-3">
                <ProgressRing
                  value={career.isLoading ? null : readinessScore}
                  size="md"
                />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink" data-testid="career-readiness-summary">
                    {career.isLoading
                      ? "Loading…"
                      : readinessLevel
                        ? readinessLevelLabel[readinessLevel] || readinessLevel
                        : "No evidence yet"}
                  </p>
                  {progressLabel && progressLabel.startsWith("+") && (
                    <p className="mt-1 text-xs font-medium text-emerald-600">
                      ↑ {progressLabel} trend
                    </p>
                  )}
                </div>
              </div>
            </article>

            <article className="rounded-2xl border border-line bg-white p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                Interviews Completed
              </p>
              <p className="mt-3 text-3xl font-bold tabular-nums text-ink">
                {assessments.isLoading ? "…" : assessments.isError ? "—" : interviewsTaken}
              </p>
              <p className="mt-1 text-xs text-ink-soft">
                {assessments.isLoading || assessments.isError
                  ? "—"
                  : interviewsThisWeek > 0
                    ? `+${interviewsThisWeek} this week`
                    : "No new interviews this week"}
              </p>
            </article>

            <article className="rounded-2xl border border-line bg-white p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                Overall Performance
              </p>
              <p className="mt-3 text-3xl font-bold tabular-nums text-ink">
                {assessments.isLoading
                  ? "…"
                  : assessments.isError
                    ? "—"
                    : avgScore != null
                      ? `${avgScore}%`
                      : "—"}
              </p>
              <p
                className={`mt-1 text-xs font-medium ${
                  progressLabel?.startsWith("+")
                    ? "text-emerald-600"
                    : progressLabel?.startsWith("-")
                      ? "text-rose-600"
                      : "text-ink-soft"
                }`}
              >
                {assessments.isLoading || assessments.isError
                  ? "—"
                  : progressLabel
                    ? `${progressLabel} vs earlier interviews`
                    : progressUnavailableNote ||
                      "Need more comparable interviews for a trend"}
              </p>
            </article>

            <article className="rounded-2xl border border-line bg-white p-4 shadow-card">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                Target Role Readiness
              </p>
              <div className="mt-3 flex gap-3">
                <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
                  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                    <path d="M12 2a9 9 0 1 0 9 9 9 9 0 0 0-9-9Zm0 16a7 7 0 1 1 7-7 7 7 0 0 1-7 7Zm0-10a3 3 0 1 0 3 3 3 3 0 0 0-3-3Z" />
                  </svg>
                </span>
                <p className="text-sm leading-snug text-ink">
                  {targetRole
                    ? readinessSummary ||
                      `Preparation signals for ${targetRole} from your completed interviews.`
                    : readinessSummary ||
                      "Set a target role in onboarding to personalize readiness."}
                </p>
              </div>
            </article>
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <article className="rounded-2xl border border-line bg-white p-5 shadow-card xl:col-span-1">
              <h3 className="text-sm font-semibold text-ink">Strength & Weakness Analysis</h3>
              <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                    Your Strengths
                  </p>
                  {strengthItems.length === 0 ? (
                    <p className="mt-2 text-sm text-ink-faint">No strengths with enough evidence yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {strengthItems.map((item) => (
                        <li key={item} className="flex items-start gap-2 text-sm text-ink">
                          <span className="mt-0.5 text-emerald-600" aria-hidden="true">✓</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">
                    Areas to Improve
                  </p>
                  {improveItems.length === 0 ? (
                    <p className="mt-2 text-sm text-ink-faint">No demonstrated gaps yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-2">
                      {improveItems.map((item) => (
                        <li key={item} className="flex items-start gap-2 text-sm text-ink">
                          <span className="mt-0.5 text-orange-500" aria-hidden="true">!</span>
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
              {(readinessSummary || dash?.recommended_topics?.length) && (
                <div className="mt-4 rounded-xl bg-accent-soft/60 p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-strong">
                    Key Insight
                  </p>
                  <p className="mt-1 text-sm text-ink">
                    {readinessSummary ||
                      `Recommended focus: ${(dash?.recommended_topics ?? []).slice(0, 3).join(", ")}`}
                  </p>
                </div>
              )}
            </article>

            <article className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">Progress Overview</h3>
                <span className="text-[11px] text-ink-faint">Last {Math.max(chartPoints.length, 1)} interviews</span>
              </div>
              <div className="mt-3">
                <DashboardProgressChart
                  points={chartPoints}
                  emptyMessage={
                    assessments.isLoading
                      ? "Loading progress…"
                      : "Complete interviews to see progress."
                  }
                />
              </div>
            </article>

            <article className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <h3 className="text-sm font-semibold text-ink">Preparation Roadmap</h3>
              {roadmapSteps.length === 0 ? (
                <p className="mt-3 text-sm text-ink-faint">
                  Finish onboarding or interviews to unlock a roadmap.
                </p>
              ) : (
                <ol className="mt-3 space-y-3" data-testid="dashboard-roadmap">
                  {roadmapSteps.map((step, index) => {
                    const priority =
                      "priority" in step && typeof step.priority === "string"
                        ? step.priority
                        : index === 0
                          ? "high"
                          : "medium";
                    const completion =
                      "completion" in step && typeof step.completion === "string"
                        ? step.completion
                        : null;
                    const evidence =
                      "evidence" in step && typeof step.evidence === "string"
                        ? step.evidence
                        : step.practise;
                    return (
                      <li key={step.id} className="flex gap-3">
                        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-bold text-accent-strong">
                          {index + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-semibold text-ink">{step.title}</p>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                /high/i.test(priority)
                                  ? "bg-rose-50 text-rose-700"
                                  : "bg-amber-50 text-amber-800"
                              }`}
                            >
                              {/high/i.test(priority) ? "High Priority" : "Medium"}
                            </span>
                            {completion && (
                              <span
                                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                  completion === "completed"
                                    ? "bg-emerald-50 text-emerald-800"
                                    : completion === "in_progress"
                                      ? "bg-sky-50 text-sky-800"
                                      : "bg-stone-100 text-stone-600"
                                }`}
                              >
                                {completion === "completed"
                                  ? "Completed"
                                  : completion === "in_progress"
                                    ? "In progress"
                                    : "Not started"}
                              </span>
                            )}
                          </div>
                          {step.why && (
                            <p className="mt-0.5 text-xs text-ink-soft line-clamp-2">{step.why}</p>
                          )}
                          {step.subject && (
                            <p className="mt-0.5 text-[11px] text-ink-faint">
                              Track focus: {step.subject}
                            </p>
                          )}
                          {evidence && (
                            <p className="mt-0.5 text-[11px] text-ink-faint line-clamp-2">
                              {evidence}
                            </p>
                          )}
                          {"action_label" in step &&
                            step.subject &&
                            completion !== "completed" && (
                            <button
                              type="button"
                              disabled={reviewBusy}
                              onClick={() =>
                                startRecommended.mutate({
                                  subject: step.subject,
                                  track_type: step.track_type || "topic",
                                })
                              }
                              className="mt-1.5 text-xs font-semibold text-accent-strong hover:underline disabled:opacity-50"
                            >
                              {step.action_label || "Start"}
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
              <Link
                to="/readiness"
                className="mt-4 inline-flex text-xs font-semibold text-accent-strong hover:underline"
              >
                View Full Roadmap →
              </Link>
            </article>
          </div>

          {career.data && (
            <CompetencyOverview data={career.data} compact />
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <ProjectPrepPanel
              data={career.data?.project_intelligence}
              defense={career.data?.project_defense}
              canDefend={Boolean(focusTrackId)}
              onDefend={() => {
                const track = (tracks.data ?? []).find((t) => t.id === focusTrackId);
                if (!track) return;
                setStartFocusWeak(false);
                setStartDefenseMode(true);
                setStartTrack(track);
              }}
            />

            <article className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <h3 className="text-sm font-semibold text-ink">Continuous preparation</h3>
              <p className="mt-1 text-xs text-ink-soft">
                Interview → Assessment → Evidence → Career Intelligence → Practice → Reassessment
              </p>
              {primaryNext ? (
                <div
                  className="mt-4 rounded-xl border border-accent/20 bg-accent-soft/50 p-4"
                  data-testid="career-preparation-loop"
                >
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-strong">
                    Next useful action
                  </p>
                  <p className="mt-1 text-sm font-semibold text-ink">{primaryNext.title}</p>
                  {primaryNext.reason && (
                    <p className="mt-1 text-xs text-ink-soft">{primaryNext.reason}</p>
                  )}
                  <div className="mt-3 flex flex-wrap gap-2" data-testid="career-next-actions">
                    {review?.next_action ? (
                      <button
                        type="button"
                        disabled={reviewBusy}
                        onClick={() => handleNextAction(review.next_action!)}
                        className="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
                      >
                        {primaryNext.action_label || "Continue"}
                      </button>
                    ) : primaryNext.href ? (
                      <Link
                        to={primaryNext.href}
                        className="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong"
                      >
                        {primaryNext.action_label || "Continue"}
                      </Link>
                    ) : null}
                    <button
                      type="button"
                      data-testid="practice-weak-areas"
                      disabled={!focusTrackId}
                      onClick={() => {
                        if (!focusTrackId) return;
                        const track = (tracks.data ?? []).find((t) => t.id === focusTrackId);
                        if (!track) return;
                        setStartDefenseMode(false);
                        setStartFocusWeak(true);
                        setStartTrack(track);
                      }}
                      className="rounded-xl border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white disabled:opacity-50"
                    >
                      Practice weak areas
                    </button>
                    <Link
                      to="/readiness"
                      className="rounded-xl border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white"
                    >
                      Open full readiness
                    </Link>
                  </div>
                </div>
              ) : (
                <p className="mt-4 text-sm text-ink-faint">
                  Complete an interview to unlock your next preparation action.
                </p>
              )}
              {career.data?.disclaimer && (
                <p className="mt-3 text-[11px] text-ink-faint">{career.data.disclaimer}</p>
              )}
            </article>
          </div>
        </section>
      )}

      <div id="tracks" className="flex flex-wrap items-start justify-between gap-3 scroll-mt-24">
        <SectionHeader
          title="Preparation tracks"
          subtitle="Each track has its own interviews, feedback, and progression."
        />
        <button
          type="button"
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-white shadow-card hover:bg-accent-strong"
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

      {(user?.recommended_tracks?.length ?? 0) > 0 && (
        <div
          className="rounded-lg border border-accent/20 bg-accent-soft/40 p-4"
          data-testid="recommended-tracks"
        >
          <p className="text-sm font-semibold text-ink">Recommended for you</p>
          <p className="mt-0.5 text-xs text-ink-soft">
            Based on your onboarding preparation goals.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {user!.recommended_tracks!.map((seed) => (
              <button
                key={`${seed.track_type}-${seed.subject}`}
                type="button"
                onClick={() => {
                  setShowForm(true);
                  setForm({
                    track_type: seed.track_type,
                    subject: seed.subject,
                    company: "",
                    jd_text: "",
                  });
                }}
                className="rounded-md bg-white px-3 py-2 text-left text-xs font-medium text-ink ring-1 ring-stone-200 hover:ring-accent"
              >
                <span className="block text-[10px] uppercase tracking-wide text-ink-faint">
                  {TYPE_LABELS[seed.track_type] ?? seed.track_type}
                </span>
                {seed.subject}
              </button>
            ))}
          </div>
        </div>
      )}

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

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
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
                        {t.brief_status === "authoring" && (
                          <span className="inline-flex items-center gap-1 rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                            <span className="h-2 w-2 animate-spin rounded-full border-2 border-amber-500 border-t-transparent" />
                            Authoring brief…
                          </span>
                        )}
                        {t.brief_status === "failed" && (
                          <span className="rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                            Brief failed
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          if (!t.archived && t.brief_status !== "authoring") setStartTrack(t);
                        }}
                        className={`mt-1 block text-left text-lg font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                          t.brief_status === "authoring" ? "cursor-wait opacity-80" : "hover:text-accent-strong"
                        }`}
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
                      ) : t.brief_status === "authoring" ? (
                        <button
                          type="button"
                          disabled
                          className="inline-flex items-center gap-1.5 rounded-md bg-accent/60 px-3.5 py-2 text-sm font-semibold text-white cursor-wait opacity-85"
                        >
                          <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/60 border-t-white" />
                          Preparing Brief…
                        </button>
                      ) : t.brief_status === "failed" ? (
                        <button
                          type="button"
                          disabled={reauthor.isPending}
                          onClick={() => reauthor.mutate(t.id)}
                          className="inline-flex items-center gap-1.5 rounded-md bg-rose-600 px-3.5 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-60"
                        >
                          Retry Brief
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

          <div className="rounded-xl border border-line bg-white p-3 shadow-sm">
            <h2 className="text-[13px] font-semibold tracking-tight text-ink">
              Interview Progress
            </h2>
            <div className="mt-2.5 flex items-center gap-3">
              <ProgressRing value={avgScore} size="xs" />
              <div className="grid min-w-0 flex-1 grid-cols-2 gap-x-2 gap-y-1">
                {[
                  { label: "Assessments", value: interviewsTaken },
                  {
                    label: "In Progress",
                    value: openSessions.isLoading
                      ? "…"
                      : openSessions.isError
                        ? "—"
                        : inProgressCount,
                  },
                  {
                    label: activeTrackCount === 1 ? "Track" : "Tracks",
                    value: activeTrackCount,
                  },
                  {
                    label: "Weak Areas",
                    value: weaknesses.isLoading
                      ? "…"
                      : weaknesses.data?.top_weak?.length ?? 0,
                  },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    className="min-w-0 rounded-md bg-page/80 px-2 py-1"
                  >
                    <p className="text-[11px] font-semibold tabular-nums leading-none text-ink">
                      {stat.value}
                    </p>
                    <p className="mt-0.5 truncate text-[10px] leading-none text-ink-soft">
                      {stat.label}
                    </p>
                  </div>
                ))}
              </div>
            </div>
            {(weaknesses.data?.top_weak?.length ?? 0) > 0 && (
              <div className="mt-2 space-y-2 border-t border-line/70 pt-2">
                <ul className="space-y-0.5">
                  {weaknesses.data!.top_weak.slice(0, 3).map((row) => (
                    <li
                      key={row.concept}
                      className="flex min-w-0 items-center justify-between gap-2 text-[10px] text-ink-soft"
                    >
                      <span className="truncate" title={row.concept}>
                        {row.concept}
                      </span>
                      <span className="shrink-0 font-medium uppercase tracking-wide text-ink-faint">
                        {row.status}
                      </span>
                    </li>
                  ))}
                </ul>
                {focusTrackId && (
                  <button
                    type="button"
                    data-testid="practice-weak-areas"
                    onClick={() => {
                      const track = (tracks.data ?? []).find((t) => t.id === focusTrackId);
                      if (!track) return;
                      setStartDefenseMode(false);
                      setStartFocusWeak(true);
                      setStartTrack(track);
                    }}
                    className="w-full rounded-md border border-line bg-white px-2 py-1.5 text-[11px] font-medium text-ink hover:bg-page"
                  >
                    Practice weak areas
                  </button>
                )}
              </div>
            )}
            {focusTrackId && (
              <button
                type="button"
                data-testid="defend-projects-cta"
                onClick={() => {
                  const track = (tracks.data ?? []).find((t) => t.id === focusTrackId);
                  if (!track) return;
                  setStartFocusWeak(false);
                  setStartDefenseMode(true);
                  setStartTrack(track);
                }}
                className="mt-2 w-full rounded-md border border-line bg-white px-2 py-1.5 text-[11px] font-medium text-ink hover:bg-page"
              >
                Defend my projects
              </button>
            )}
            {finishError && (
              <p
                role="alert"
                className="mt-2 rounded-md bg-red-50 px-2 py-1 text-[11px] text-red-700"
              >
                {finishError}
              </p>
            )}
            {openSessions.isLoading ? (
              <p className="mt-2 text-[11px] text-ink-faint">Loading open interviews…</p>
            ) : openSessions.isError ? (
              <div
                role="alert"
                data-testid="dashboard-open-sessions-error"
                className="mt-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-[11px] text-red-800"
              >
                <p className="font-semibold text-red-900">Couldn’t load open interviews</p>
                <p className="mt-0.5 text-red-800/90">{openSessionsErrorMessage}</p>
                <button
                  type="button"
                  data-testid="dashboard-open-sessions-retry"
                  onClick={() => void openSessions.refetch()}
                  className="mt-1.5 inline-flex h-6 items-center rounded-md border border-red-200 bg-white px-2 text-[11px] font-semibold text-red-800 hover:bg-red-100"
                >
                  Retry
                </button>
              </div>
            ) : openList.length === 0 ? (
              <p
                className="mt-2 text-[11px] text-ink-faint"
                data-testid="dashboard-open-sessions-empty"
              >
                No unfinished interviews right now.
              </p>
            ) : (
              <ul className="mt-2 max-h-52 space-y-1.5 overflow-y-auto">
                {openList.map((row) => {
                  const finishing =
                    finishOpen.isPending &&
                    finishOpen.variables?.session_id === row.session_id;
                  const modeLabel =
                    row.mode?.toLowerCase() === "guided"
                      ? "Guided Mode"
                      : "Strict Mode";
                  return (
                    <li
                      key={row.session_id}
                      className="min-w-0 rounded-lg border border-line bg-white px-2.5 py-2"
                    >
                      <p className="truncate text-[13px] font-medium leading-tight text-ink">
                        {row.track_subject}
                      </p>
                      <p className="mt-0.5 text-[10px] leading-tight text-ink-soft">
                        Q{row.question_index}/{row.max_turns}
                        {" · "}
                        {row.answered_count} answered
                        {" · "}
                        {modeLabel}
                      </p>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        <Link
                          to={`/tracks/${row.track_id}/interview/${row.session_id}`}
                          className="inline-flex h-6 items-center rounded-md bg-accent px-2.5 text-[11px] font-semibold text-white hover:bg-accent-strong"
                        >
                          Resume
                        </Link>
                        <button
                          type="button"
                          disabled={finishOpen.isPending}
                          title="Finish and get feedback"
                          onClick={() => {
                            setFinishError(null);
                            finishOpen.mutate(row);
                          }}
                          className="inline-flex h-6 max-w-full items-center gap-1 rounded-md border border-line bg-white px-2 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink disabled:opacity-60"
                        >
                          {finishing && (
                            <svg
                              viewBox="0 0 24 24"
                              className="h-3 w-3 shrink-0 animate-spin"
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
                          <span className="truncate">Finish and get feedback</span>
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="rounded-lg border border-line bg-white p-5" data-testid="dashboard-interview-history">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-ink">
                Interview history
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
            ) : assessments.isError ? (
              <div
                role="alert"
                data-testid="dashboard-assessments-error"
                className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-3 text-xs text-red-800"
              >
                <p className="font-semibold text-red-900">Couldn’t load assessments</p>
                <p className="mt-1 text-red-800/90">{assessmentsErrorMessage}</p>
                <button
                  type="button"
                  data-testid="dashboard-assessments-retry"
                  onClick={() => void assessments.refetch()}
                  className="mt-2 inline-flex min-h-8 items-center rounded-md border border-red-200 bg-white px-2.5 text-xs font-semibold text-red-800 hover:bg-red-100"
                >
                  Retry
                </button>
              </div>
            ) : recent.length === 0 ? (
              <p
                className="mt-3 rounded-md bg-page px-3 py-4 text-center text-xs text-ink-faint"
                data-testid="dashboard-assessments-empty"
              >
                No completed assessments yet. Finish an interview to build evidence here.
              </p>
            ) : (
              <ul className="mt-3 space-y-3">
                {recent.map((a) => {
                  const topics = [
                    ...(a.strengths ?? []).slice(0, 2),
                    ...(a.improvement_areas ?? []).slice(0, 1),
                  ];
                  return (
                    <li key={a.report_id} className="flex gap-2.5">
                      <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="m5 13 4 4L19 7" />
                        </svg>
                      </span>
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/tracks/${a.track_id}/report/${a.session_id}`}
                          className="block truncate text-sm font-medium text-ink hover:text-accent-strong"
                        >
                          {a.track_subject}
                        </Link>
                        <p className="text-xs text-ink-soft">
                          {formatDate(a.created_at)} · {a.session_mode}
                          {a.overall_score != null ? ` · ${a.overall_score}%` : ""}
                          {a.coverage_status ? ` · ${a.coverage_status}` : ""}
                        </p>
                        {topics.length > 0 && (
                          <p className="mt-0.5 truncate text-[11px] text-ink-faint">
                            Topics: {topics.join(", ")}
                          </p>
                        )}
                        {a.summary_overview && (
                          <p className="mt-0.5 line-clamp-2 text-[11px] text-ink-soft">
                            {a.summary_overview}
                          </p>
                        )}
                        <Link
                          to={`/tracks/${a.track_id}/report/${a.session_id}`}
                          className="mt-1 inline-flex text-[11px] font-semibold text-accent-strong hover:underline"
                        >
                          View feedback report
                        </Link>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>
      </div>
      <StartInterviewModal
        track={startTrack ? { id: startTrack.id, subject: startTrack.subject } : null}
        initialFocusWeak={startFocusWeak}
        initialDefenseMode={startDefenseMode}
        onClose={() => {
          setStartTrack(null);
          setStartFocusWeak(false);
          setStartDefenseMode(false);
        }}
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
