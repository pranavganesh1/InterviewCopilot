import {
  notifyAuthFailure,
  refreshAccessToken,
  shouldAttemptRefresh,
} from "./authRefresh";
import { API_BASE } from "./apiBase";

export { API_BASE };

export class ApiError extends Error {
  status: number;
  code?: string;
  sessionId?: string;
  constructor(
    status: number,
    message: string,
    extra?: { code?: string; sessionId?: string },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = extra?.code;
    this.sessionId = extra?.sessionId;
  }
}

type ApiOptions = RequestInit & { _retried?: boolean };

export async function api<T>(
  path: string,
  options: ApiOptions = {},
): Promise<T> {
  const { _retried = false, ...fetchOptions } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers:
      fetchOptions.body && !(fetchOptions.body instanceof FormData)
        ? { "Content-Type": "application/json", ...fetchOptions.headers }
        : fetchOptions.headers,
    ...fetchOptions,
  });

  if (res.status === 401 && shouldAttemptRefresh(path, _retried)) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return api<T>(path, { ...options, _retried: true });
    }
    notifyAuthFailure();
    throw new ApiError(401, "Not signed in");
  }

  if (res.status === 401) {
    notifyAuthFailure();
    throw new ApiError(401, "Not signed in");
  }

  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    if (detail && typeof detail === "object") {
      const record = detail as {
        message?: string;
        code?: string;
        session_id?: string;
        correlation_id?: string;
      };
      const message =
        record.message ||
        (typeof (detail as { detail?: string }).detail === "string"
          ? (detail as { detail: string }).detail
          : res.statusText);
      throw new ApiError(res.status, message, {
        code: record.code,
        sessionId: record.session_id || record.correlation_id,
      });
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : res.statusText);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null as T;
  }
  return res.json() as Promise<T>;
}

// ---------- types ----------

export type ProfileItemStatus =
  | "confirmed"
  | "needs_clarification"
  | "not_assessed";

export interface ProfileReviewItem {
  item_id: string;
  category: string;
  title: string;
  status: ProfileItemStatus;
  reason: string;
  user_set?: boolean;
}

export type RoadmapCompletion = "not_started" | "in_progress" | "completed";

export type NextActionKind =
  | "resume_session"
  | "clarify_profile"
  | "create_track"
  | "practise_weakness"
  | "recommend_track";

export interface RoadmapStep {
  id: string;
  title: string;
  why: string;
  topics: string[];
  practise: string;
  track_type: string;
  subject: string;
  action_label: string;
  stage?: number;
  completion?: RoadmapCompletion;
}

export interface NextAction {
  kind?: NextActionKind;
  title: string;
  reason?: string;
  track_type?: string;
  subject?: string;
  step_id?: string;
  action_label?: string;
  reuse_existing?: boolean;
  session_id?: string;
  track_id?: string;
  item_id?: string;
  href?: string | null;
}

export interface ProfileReview {
  summary: string;
  summary_user_edit?: string | null;
  item_statuses: ProfileReviewItem[];
  needs_clarification?: ProfileReviewItem[];
  not_assessed?: ProfileReviewItem[];
  confirmed?: ProfileReviewItem[];
  roadmap: RoadmapStep[];
  next_action?: NextAction | null;
  selected_next_track_id?: string | null;
  preparation_summary?: string;
  goal_labels?: string[];
  vault_fingerprint?: string;
  generated_at?: string | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
  picture_url: string | null;
  professional_title?: string;
  introduction?: string;
  skills?: string[];
  education?: string;
  onboarding_completed?: boolean;
  onboarding_completed_at?: string | null;
  is_admin?: boolean;
  preparation_preferences?: PreparationPreferences;
  recommended_tracks?: { track_type: string; subject: string }[];
  profile_review?: ProfileReview;
}

export interface ProfileUpdate {
  name?: string;
  professional_title?: string;
  introduction?: string;
  education?: string;
  picture_url?: string | null;
  skills?: string[];
}

export interface AssessmentSummary {
  report_id: string;
  session_id: string;
  track_id: string;
  track_subject: string;
  created_at: string;
  session_mode: string;
  coverage_status: string;
  overall_score: number | null;
  questions_attempted: number;
  max_turns: number;
  status: string;
  track_archived?: boolean;
  summary_overview: string;
  strengths: string[];
  improvement_areas: string[];
}

export interface AssessmentsDashboard {
  dashboard: {
    completed_interviews: number;
    average_score: number | null;
    total_questions_attempted: number;
    strongest_skills: string[];
    skills_needing_improvement: string[];
    recommended_topics: string[];
  };
  assessments: AssessmentSummary[];
}

export interface VaultItem {
  id: string;
  category: string;
  title: string;
  details?: Record<string, string>;
  source?: string;
}

export interface ReadinessClaim {
  claim: string;
  excerpt: string;
  category: string;
  status: "clear" | "add_detail" | "be_ready";
  status_reason?: string;
  questions: string[];
  tips: string[];
  stronger_phrasing?: string;
}

export interface ReadinessItem {
  vault_item_id: string;
  category: string;
  title: string;
  claims: ReadinessClaim[];
}

export interface ReadinessResult {
  disclaimer: string;
  empty: boolean;
  empty_hint?: string;
  content_hash?: string;
  cached?: boolean;
  summary: { clear: number; add_detail: number; be_ready: number };
  items: ReadinessItem[];
  consistency_hints: { message: string; related_item_ids: string[] }[];
  claim_seeds: {
    vault_item_id: string;
    claim: string;
    excerpt?: string;
    title?: string;
  }[];
}

export interface TrackWeaknesses {
  track_id: string;
  has_data: boolean;
  weak: { concept: string; status: string; last_coverage?: string | null }[];
  improving: { concept: string; status: string; last_coverage?: string | null }[];
  mastered: { concept: string; status: string; last_coverage?: string | null }[];
  top_weak: { concept: string; status: string; last_coverage?: string | null }[];
  recommended_practice: {
    concept: string;
    status: string;
    study_topics: string[];
    practice_themes: string[];
  }[];
}

export interface ReportDiagnostics {
  identified_weaknesses: {
    concept: string;
    status: string;
    evidence: { session_id?: string; turn_index?: number; coverage?: string }[];
    missing_concepts: string[];
  }[];
  strengths: { concept: string; last_coverage?: string | null; trend?: string[] }[];
  area_score_history: { session_id: string; areas: Record<string, number> }[];
  recommended_practice: {
    concept: string;
    status: string;
    study_topics: string[];
    practice_themes: string[];
  }[];
}

export interface PreparationPreferences {
  interests: string[];
  target_role?: string | null;
  technical_areas?: string[];
  focus_skills?: string[];
  focus_projects?: string[];
  placement_target?: string | null;
  experience_level?: string | null;
  behavioral_goals?: string | null;
  confirmed?: boolean;
}

export interface ConversationStarter {
  id: string;
  label: string;
  description: string;
}

export interface OnboardingState {
  messages: { role: string; content: string; created_at?: string }[];
  vault_items: VaultItem[];
  onboarding_complete?: boolean;
  onboarding_finished?: boolean;
  onboarding_completed_at?: string | null;
  missing_categories?: string[];
  phase?: "profile" | "goals" | "ready";
  show_goal_menu?: boolean;
  preparation_preferences?: PreparationPreferences;
  goal_interest_options?: { id: string; label: string }[];
  suggested_skills?: string[];
  suggested_projects?: string[];
  recommended_tracks?: { track_type: string; subject: string }[];
  preparation_summary?: string;
  goals_ready?: boolean;
  conversation_mode?: string | null;
  show_starters?: boolean;
  conversation_starters?: ConversationStarter[];
  has_resume_welcome?: boolean;
  profile_review?: ProfileReview;
}

export interface ChatResult {
  reply: string;
  items_created: { id: string; category: string; title: string }[];
  items_updated?: { id: string; category: string; title: string }[];
  onboarding_complete: boolean;
  phase?: "profile" | "goals" | "ready";
  show_goal_menu?: boolean;
  preparation_preferences?: PreparationPreferences;
  conversation_mode?: string | null;
  show_starters?: boolean;
}

export interface Track {
  id: string;
  track_type: string;
  subject: string;
  company: string | null;
  status: string;
  brief_status?: "authoring" | "ready" | "failed";
  archived?: boolean;
  archived_at?: string | null;
  created_at: string;
  brief_version?: number;
}

export interface BankQuestion {
  area: string;
  question: string;
  difficulty: "foundational" | "intermediate" | "advanced";
  type: "coding" | "conceptual" | "behavioral";
  expected_answer_sketch: string;
}

export interface BriefContent {
  summary: string;
  question_bank: BankQuestion[];
  preparation_plan: string[];
  competencies: { name: string; description: string; importance: string }[];
  question_areas: { topic: string; guidance: string }[];
  candidate_angle_notes: string;
  clarification_message?: string;
}

export interface OpenSession {
  id: string;
  mode: string;
  status: string;
  question_index: number;
  max_turns: number;
  answered_count: number;
  created_at?: string | null;
  duration_minutes?: number | null;
}

export interface OpenSessionRow {
  session_id: string;
  track_id: string;
  track_subject: string;
  mode: string;
  status: string;
  question_index: number;
  max_turns: number;
  answered_count: number;
  created_at?: string | null;
  duration_minutes?: number | null;
}

export interface Progression {
  track_id: string;
  strict_completed: number;
  guided_state: string;
}

export interface SessionInfo {
  id: string;
  track_id: string;
  mode: string;
  status: string;
  max_turns?: number;
  duration_minutes: number;
  created_at: string;
  practice_label?: string;
  persona_id?: string;
  persona_name?: string;
}

export interface TurnEvaluation {
  coverage: "none" | "partial" | "good" | "excellent";
  strengths: string[];
  gaps: string[];
  expected_answer_explanation?: string;
  corrected_code?: string;
  time_complexity?: string;
  space_complexity?: string;
}

export interface Turn {
  turn_index: number;
  question_area: string;
  question: string;
  question_type?:
    | "coding"
    | "conceptual"
    | "behavioral"
    | "mcq"
    | "code_read"
    | "case_study"
    | "numeric"
    | null;
  options?: string[];
  code_snippet?: string;
  scenario?: string;
  unit?: string;
  objective?: string;
  origin?: string;
  probe_label?: string;
  project_name?: string;
  correct_index?: number;
  explanation?: string;
  answer: string | null;
  assisted?: boolean;
  assistance_level?: number;
  assistance_events?: {
    assistance_event_id: string;
    level: number;
    assistance_type: string;
    content: string;
    created_at: string;
  }[];
  evaluation?: TurnEvaluation | null;
}

export interface AssistanceResult {
  session_id: string;
  turn_index: number;
  assistance: {
    assistance_event_id: string;
    level: number;
    assistance_type: string;
    content: string;
  };
  assistance_level: number;
  max_level: number;
}

export interface TurnResult {
  completed: boolean;
  evaluation: TurnEvaluation;
  turn?: Turn;
}

export interface QuestionAssessment {
  turn_index: number;
  coverage: string;
  observation: string;
  evidence_excerpt: string;
  question?: string;
  answer?: string;
  strengths?: string[];
  gaps?: string[];
  expected_answer_explanation?: string;
  corrected_code?: string;
  time_complexity?: string;
  space_complexity?: string;
  score?: number | null;
  /** false when coding answer was reviewed statically (never run). */
  executed?: boolean | null;
  review_label?: string;
  chosen_option?: string;
  correct_option?: string;
  explanation?: string;
  code_snippet?: string;
  scenario?: string;
  expected_value?: number;
  unit?: string;
}

export interface ReportContent {
  report_version: number;
  session_mode: string;
  summary_overview: string;
  coverage_status: string;
  practice_label?: string;
  persona_id?: string;
  persona_name?: string;
  question_assessments: QuestionAssessment[];
  competency_assessments: {
    competency_name: string;
    assessment_status: string;
    level: string | null;
    observation: string;
    confidence: string;
  }[];
  strengths: string[];
  improvement_areas: string[];
  unassessed_topics: string[];
  recommendations: string[];
  /** Present when any coding answer was assessed without execution. */
  coding_review_note?: string;
  diagnostics?: ReportDiagnostics;
}

export interface Report {
  id: string;
  session_id: string;
  content: ReportContent;
  overall_score?: number | null;
  performance_level?: string;
  questions_attempted?: number;
  max_turns?: number;
  created_at: string;
}

// ---------- admin (M11) ----------

export interface AdminOverview {
  users: number;
  tracks: number;
  interviews_total: number;
  interviews_completed: number;
  interview_minutes: number;
  llm_calls: number;
  tokens_in: number;
  tokens_out: number;
  estimated_cost_usd: number;
  by_day: { day: string; calls: number; tokens: number; estimated_cost_usd: number }[];
  by_model: { model: string; calls: number; tokens: number; estimated_cost_usd: number }[];
}

export interface AdminUserRow {
  id: string;
  email: string;
  name: string;
  tracks: number;
  interviews_completed: number;
  interview_minutes: number;
  tokens: number;
  estimated_cost_usd: number;
  avg_performance: number | null;
}

export interface AdminUserDetail {
  user: { id: string; email: string; name: string };
  llm: { calls: number; tokens: number; estimated_cost_usd: number };
  tracks: { id: string; subject: string; track_type: string; archived?: boolean }[];
  sessions: {
    id: string;
    mode: string;
    status: string;
    minutes: number;
    started: string;
    coverage_status: string | null;
  }[];
  reports: { session_id: string; coverage_status: string; summary_overview: string }[];
}
