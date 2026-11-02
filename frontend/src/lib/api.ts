export const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers:
      options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json", ...options.headers }
        : options.headers,
    ...options,
  });
  if (res.status === 401) {
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
  return res.json() as Promise<T>;
}

// ---------- types ----------

export interface User {
  id: string;
  email: string;
  name: string;
  picture_url: string | null;
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
}

export interface Turn {
  turn_index: number;
  question_area: string;
  question: string;
  answer: string | null;
}

export interface TurnResult {
  completed: boolean;
  evaluation: {
    coverage: "none" | "partial" | "good" | "excellent";
    strengths: string[];
    gaps: string[];
  };
  turn?: Turn;
}

export interface ReportContent {
  report_version: number;
  session_mode: string;
  summary_overview: string;
  coverage_status: string;
  question_assessments: {
    turn_index: number;
    coverage: string;
    observation: string;
    evidence_excerpt: string;
  }[];
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
  created_at: string;
}
