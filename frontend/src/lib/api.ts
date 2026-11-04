import {
  notifyAuthFailure,
  refreshAccessToken,
  shouldAttemptRefresh,
} from "./authRefresh";
import { API_BASE } from "./apiBase";

export { API_BASE };

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
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
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return null as T;
  }
  return res.json() as Promise<T>;
}

// ---------- types ----------

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

export interface OnboardingState {
  messages: { role: string; content: string; created_at?: string }[];
  vault_items: { id: string; category: string; title: string; source: string }[];
  onboarding_complete?: boolean;
  onboarding_finished?: boolean;
  onboarding_completed_at?: string | null;
  missing_categories?: string[];
}

export interface ChatResult {
  reply: string;
  items_created: { id: string; category: string; title: string }[];
  onboarding_complete: boolean;
}

export interface Track {
  id: string;
  track_type: string;
  subject: string;
  company: string | null;
  status: string;
  created_at: string;
  brief_version?: number;
}

export interface BriefContent {
  summary: string;
  preparation_plan: string[];
  competencies: { name: string; description: string; importance: string }[];
  question_areas: { topic: string; guidance: string }[];
  candidate_angle_notes: string;
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
}

export interface ReportContent {
  report_version: number;
  session_mode: string;
  summary_overview: string;
  coverage_status: string;
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
