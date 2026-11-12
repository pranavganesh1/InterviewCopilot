import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ChatResult,
  type OnboardingState,
  type PreparationPreferences,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";
import ConversationStarters from "../components/ConversationStarters";
import GoalDiscovery from "../components/GoalDiscovery";
import { VaultSidebar } from "../components/VaultSidebar";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const RESUME_HINTS: Record<string, string[]> = {
  pdf_unreadable: [
    "Export again from Word/Google Docs as PDF",
    "Remove any password protection",
  ],
  pdf_encrypted: [
    "Export again from Word/Google Docs as PDF",
    "Remove any password protection",
  ],
  no_text: [
    "Use a text-based PDF (not a scanned photo)",
    "Or type projects into the chat instead",
  ],
  empty_file: ["Choose a non-empty PDF file"],
  file_too_large: ["Keep the PDF under 10 MB"],
  unsupported_media_type: ["Only PDF files are accepted"],
};

const REQUIRED_LABELS: Record<string, string> = {
  project: "a project",
  skill: "skills",
  education: "education",
};

const DEFAULT_STARTERS = [
  {
    id: "ai_interview",
    label: "Start AI Interview",
    description: "A friendly warm-up using your resume — one question at a time.",
  },
  {
    id: "explore_projects",
    label: "Explore My Projects",
    description: "Deep-dive a project from your vault with smart follow-ups.",
  },
  {
    id: "test_skills",
    label: "Test My Skills",
    description: "Pick skills from your profile and practise them conversationally.",
  },
  {
    id: "career_goal",
    label: "Set My Career Goal",
    description: "Choose roles, placement focus, and interview preparation goals.",
  },
];

function CoachAvatar({
  mood = "idle",
  size = "md",
}: {
  mood?: "idle" | "thinking" | "happy";
  size?: "sm" | "md" | "lg";
}) {
  const dim = size === "sm" ? "h-8 w-8" : size === "lg" ? "h-14 w-14" : "h-10 w-10";
  const eyeY = mood === "thinking" ? 11 : 10;
  const mouth =
    mood === "thinking"
      ? "M10 16.5c1.2.6 2.8.6 4 0"
      : mood === "happy"
        ? "M9.5 15.5c1.4 1.6 3.6 1.6 5 0"
        : "M10 16c1.3.8 2.7.8 4 0";
  return (
    <div
      className={`${dim} shrink-0 overflow-hidden rounded-full bg-gradient-to-b from-sky-100 to-accent-soft shadow-sm ring-2 ring-white ${
        mood === "thinking" ? "coach-avatar-thinking" : ""
      }`}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="h-full w-full">
        <circle cx="12" cy="12" r="11" fill="#dbeafe" />
        <circle cx="12" cy="12" r="9.2" fill="#eff6ff" />
        <circle cx="9" cy={eyeY} r="1.15" fill="#1e3a8a" />
        <circle cx="15" cy={eyeY} r="1.15" fill="#1e3a8a" />
        <circle cx="9.35" cy={eyeY - 0.35} r="0.35" fill="#fff" />
        <circle cx="15.35" cy={eyeY - 0.35} r="0.35" fill="#fff" />
        <path d={mouth} fill="none" stroke="#1d4ed8" strokeWidth="1.2" strokeLinecap="round" />
        {mood === "happy" && (
          <>
            <circle cx="7.2" cy="13.2" r="1.1" fill="#93c5fd" opacity="0.55" />
            <circle cx="16.8" cy="13.2" r="1.1" fill="#93c5fd" opacity="0.55" />
          </>
        )}
      </svg>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 px-0.5" aria-label="Coach is typing">
      <span className="coach-typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
      <span className="coach-typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
      <span className="coach-typing-dot h-1.5 w-1.5 rounded-full bg-accent" />
    </span>
  );
}

function friendlyCoachError(raw: string | undefined): string {
  const text = (raw || "").toLowerCase();
  if (text.includes("busy") || text.includes("rate") || text.includes("503") || text.includes("temporarily")) {
    return "Oops! My thoughts got interrupted 😅 Let's try that again.";
  }
  return "Oops! My thoughts got interrupted 😅 Let's try that again.";
}

function ProgressSteps({
  phase,
  hasVault,
  hasWelcome,
  finished,
}: {
  phase: string;
  hasVault: boolean;
  hasWelcome: boolean;
  finished: boolean;
}) {
  const steps = [
    { id: "resume", label: "Resume", done: hasVault || hasWelcome || finished },
    {
      id: "explore",
      label: "Explore",
      done: finished || phase === "goals" || phase === "ready",
    },
    { id: "goals", label: "Goals", done: finished || phase === "ready" },
    { id: "ready", label: "Ready", done: finished },
  ];
  return (
    <ol
      className="flex flex-wrap items-center gap-2"
      data-testid="onboarding-progress"
      aria-label="Onboarding progress"
    >
      {steps.map((step, index) => (
        <li key={step.id} className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
              step.done
                ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200"
                : "bg-white text-stone-500 ring-1 ring-stone-200"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                step.done ? "bg-emerald-500" : "bg-stone-300"
              }`}
            />
            {step.label}
          </span>
          {index < steps.length - 1 && (
            <span className="hidden text-stone-300 sm:inline" aria-hidden>
              →
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function OnboardingPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [input, setInput] = useState("");
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  const [lastStarterId, setLastStarterId] = useState<string | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [showStartersOverride, setShowStartersOverride] = useState(true);
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const state = useQuery({
    queryKey: ["onboarding-state"],
    queryFn: () => api<OnboardingState>("/onboarding/state"),
  });

  const chat = useMutation({
    mutationFn: (message: string) =>
      api<ChatResult>("/onboarding/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    onSuccess: () => {
      setFailedMessage(null);
      setInput("");
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
    onError: (_err, message) => {
      setFailedMessage(message);
    },
  });

  const starter = useMutation({
    mutationFn: (starterId: string) =>
      api<ChatResult>("/onboarding/starter", {
        method: "POST",
        body: JSON.stringify({ starter_id: starterId }),
      }),
    onSuccess: () => {
      setShowStartersOverride(true);
      setFailedMessage(null);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
  });

  const saveGoals = useMutation({
    mutationFn: (body: Partial<PreparationPreferences> & { interests?: string[] }) =>
      api<ChatResult>("/onboarding/goals", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setFailedMessage(null);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<{
        items_created: { title: string }[];
        items_skipped?: number;
        welcome_seeded?: boolean;
      }>("/vault/resume", { method: "POST", body: form });
    },
    onSuccess: () => {
      setShowStartersOverride(true);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
  });

  function pickResume(file: File | undefined | null) {
    if (!file || upload.isPending) return;
    setResumeFile(file);
    upload.mutate(file);
  }

  const uploadError =
    upload.error instanceof ApiError
      ? upload.error
      : upload.error instanceof Error
        ? new ApiError(500, upload.error.message)
        : null;
  const uploadHints = uploadError?.code
    ? RESUME_HINTS[uploadError.code]
    : undefined;

  const finish = useMutation({
    mutationFn: () =>
      api<OnboardingState>("/onboarding/complete", { method: "POST" }),
    onSuccess: async (data) => {
      qc.setQueryData(["onboarding-state"], data);
      await refresh();
      navigate("/", { replace: true });
    },
  });

  const busy =
    chat.isPending || starter.isPending || saveGoals.isPending || finish.isPending;
  const goalsBusy = busy;

  useEffect(() => {
    const panel = messagesRef.current;
    if (!panel) return;
    panel.scrollTo({ top: panel.scrollHeight, behavior: "smooth" });
  }, [
    state.data?.messages.length,
    chat.isPending,
    starter.isPending,
    saveGoals.isPending,
    chat.isError,
  ]);

  const send = (override?: string) => {
    const message = (override ?? input).trim();
    if (!message || busy) return;
    chat.reset();
    setFailedMessage(null);
    // Keep the message visible until success so failures can retry without retyping.
    setInput(message);
    chat.mutate(message);
  };

  const retryCoach = () => {
    if (busy) return;
    if (chat.error) {
      const message = (failedMessage ?? input).trim();
      if (!message) return;
      send(message);
      return;
    }
    if (starter.error && lastStarterId) {
      starter.reset();
      starter.mutate(lastStarterId);
      return;
    }
    starter.reset();
    saveGoals.reset();
  };

  const vaultItems = state.data?.vault_items ?? [];
  const missing =
    state.data?.missing_categories ??
    (() => {
      const cats = new Set(vaultItems.map((v) => v.category));
      return (["project", "skill", "education"] as const).filter(
        (c) => !cats.has(c),
      );
    })();
  const finished = state.data?.onboarding_finished === true;
  const phase = state.data?.phase ?? (missing.length === 0 ? "goals" : "profile");
  const prefs = state.data?.preparation_preferences;
  const goalsReady = state.data?.goals_ready === true || Boolean(prefs?.confirmed);
  const showGoalMenu = state.data?.show_goal_menu === true || phase === "goals";
  const canStartPreparing =
    !finished &&
    missing.length === 0 &&
    (prefs?.interests?.length ?? 0) > 0 &&
    !finish.isPending;

  const starters = state.data?.conversation_starters?.length
    ? state.data.conversation_starters
    : DEFAULT_STARTERS;
  const canShowStarters =
    !finished &&
    (state.data?.show_starters === true ||
      state.data?.has_resume_welcome === true ||
      (vaultItems.length > 0 && (state.data?.messages?.length ?? 0) > 0));
  const startersVisible = canShowStarters && showStartersOverride;

  const suggestedReplies = useMemo(() => {
    const mode = state.data?.conversation_mode;
    if (mode === "test_skills" && (state.data?.suggested_skills?.length ?? 0) > 0) {
      return (state.data?.suggested_skills ?? []).slice(0, 4).map((s) => `Let's practise ${s}`);
    }
    if (mode === "explore_projects" && (state.data?.suggested_projects?.length ?? 0) > 0) {
      return (state.data?.suggested_projects ?? [])
        .slice(0, 3)
        .map((p) => `Tell me more about ${p}`);
    }
    if (mode === "ai_interview") {
      return ["I'm ready — ask me about my background", "Start with my strongest project"];
    }
    if (mode === "career_goal") {
      const roles = (state.data?.suggested_roles ?? []).slice(0, 2);
      if (roles.length) {
        return [
          ...roles.map((r) => `I'm targeting ${r}`),
          "Help me prepare for technical rounds",
        ];
      }
      const skills = (state.data?.suggested_skills ?? []).slice(0, 2);
      if (skills.length) {
        return [
          `I want to practice ${skills.join(" and ")}`,
          "Help me prepare for technical rounds",
        ];
      }
      return ["I want a software engineering internship", "Help me prepare for technical rounds"];
    }
    return [];
  }, [
    state.data?.conversation_mode,
    state.data?.suggested_skills,
    state.data?.suggested_projects,
    state.data?.suggested_roles,
  ]);

  const messages = [
    ...(state.data?.messages ?? []),
    ...(chat.isPending || starter.isPending || saveGoals.isPending
      ? [
          {
            role: "pending",
            content: finished
              ? "Updating your profile…"
              : starter.isPending
                ? "Opening that conversation…"
                : "Your onboarding coach is thinking…",
          },
        ]
      : []),
  ];

  const coachMood = busy ? "thinking" : finished ? "happy" : "idle";
  const coachError =
    chat.error instanceof Error
      ? chat.error
      : starter.error instanceof Error
        ? starter.error
        : saveGoals.error instanceof Error
          ? saveGoals.error
          : null;

  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden"
      data-testid="onboarding-page"
    >
      <div className="flex shrink-0 flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-accent">
            Profile setup
          </p>
          <h1 className="text-xl font-semibold tracking-tight">
            {finished ? "Your profile vault" : "Meet your interview coach"}
          </h1>
          <p className="mt-0.5 text-sm text-stone-500">
            {finished
              ? "Your profile is saved. Edit anything below — Tracks stays your home."
              : "Upload a resume or chat — your coach builds your vault with you."}
          </p>
        </div>
        <ProgressSteps
          phase={phase}
          hasVault={vaultItems.length > 0}
          hasWelcome={state.data?.has_resume_welcome === true}
          finished={finished}
        />
      </div>

      {finished && (
        <div
          data-testid="onboarding-finished-banner"
          className="shrink-0 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
        >
          Onboarding completed
          {state.data?.onboarding_completed_at
            ? ` · ${new Date(state.data.onboarding_completed_at).toLocaleDateString()}`
            : ""}
          . You can keep refining your vault anytime.
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[minmax(0,1fr)_280px]">
        <section
          data-testid="onboarding-chat-panel"
          className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-sm"
        >
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line bg-accent-soft/40 px-4 py-3 sm:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <CoachAvatar mood={coachMood} />
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-ink">
                  Aiko · Interview Coach
                </h2>
                <p className="truncate text-xs text-ink-soft">
                  {busy
                    ? "Thinking…"
                    : finished
                      ? "Happy to refine your vault anytime"
                      : state.data?.has_resume_welcome
                        ? "Resume reviewed · let's personalize your prep"
                        : "Friendly coach · vault updates as you share"}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {canShowStarters && (
                <button
                  type="button"
                  className="hidden rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-ink-soft ring-1 ring-line hover:bg-page sm:inline"
                  onClick={() => setShowStartersOverride((v) => !v)}
                >
                  {showStartersOverride ? "Hide starters" : "Show starters"}
                </button>
              )}
              <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-ink-faint ring-1 ring-line">
                {messages.filter((m) => m.role !== "pending").length}
              </span>
            </div>
          </div>

          <div
            ref={messagesRef}
            data-testid="onboarding-messages"
            className="min-h-0 flex-1 space-y-3 overflow-x-hidden overflow-y-auto px-4 py-4 sm:px-5"
          >
            {messages.length === 0 && (
              <div className="rounded-2xl border border-dashed border-line bg-accent-soft/30 px-4 py-8 text-center">
                <div className="mx-auto mb-3 flex justify-center">
                  <CoachAvatar mood="happy" size="lg" />
                </div>
                <p className="text-sm font-medium text-ink">
                  {finished
                    ? "What would you like to update?"
                    : vaultItems.length > 0
                      ? "Ready when you are ✨"
                      : "Hi! Upload a resume or say hello 👋"}
                </p>
                <p className="mx-auto mt-1 max-w-sm text-xs text-ink-soft">
                  {finished
                    ? "New skills, projects, or education details go straight into your vault."
                    : vaultItems.length > 0
                      ? "We'll chat about your experience one question at a time."
                      : "Drop a PDF on the right, or tell me about a project you've built."}
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex max-w-[min(100%,36rem)] gap-2 ${
                  m.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                }`}
              >
                {m.role !== "user" && (
                  <CoachAvatar
                    size="sm"
                    mood={m.role === "pending" ? "thinking" : "idle"}
                  />
                )}
                <div
                  className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
                    m.role === "user"
                      ? "rounded-br-md bg-accent text-white"
                      : m.role === "pending"
                        ? "rounded-bl-md border border-line bg-accent-soft/50 text-ink-soft"
                        : "rounded-bl-md border border-line bg-white text-ink"
                  }`}
                >
                  {m.role === "pending" ? <TypingDots /> : m.content}
                </div>
              </div>
            ))}

            {startersVisible && !busy && (
              <ConversationStarters
                starters={starters}
                skills={state.data?.suggested_skills ?? []}
                projects={state.data?.suggested_projects ?? []}
                vaultItems={vaultItems}
                activeMode={state.data?.conversation_mode}
                pending={busy}
                onSelectStarter={(id) => {
                  setLastStarterId(id);
                  starter.mutate(id);
                }}
                onExploreSkill={(skill) =>
                  send(
                    `I'd like to explore my skill in ${skill}. Ask me one question about how I've used it.`,
                  )
                }
                onExploreProject={(project) =>
                  send(
                    `Let's explore my project “${project}”. Ask follow-ups based only on what's in my vault.`,
                  )
                }
              />
            )}

            {suggestedReplies.length > 0 && !busy && !finished && (
              <div className="flex flex-wrap gap-2 pl-10" data-testid="suggested-replies">
                {suggestedReplies.map((reply) => (
                  <button
                    key={reply}
                    type="button"
                    disabled={busy}
                    onClick={() => send(reply)}
                    className="rounded-full border border-accent/25 bg-accent-soft/70 px-3 py-1.5 text-xs font-medium text-accent-strong transition hover:bg-accent-soft disabled:opacity-50"
                  >
                    {reply}
                  </button>
                ))}
              </div>
            )}

            {coachError && (
              <div
                data-testid="onboarding-chat-error"
                role="alert"
                className="ml-10 max-w-md rounded-2xl border border-amber-200 bg-amber-50 px-3.5 py-3 text-sm text-amber-950"
              >
                <p>{friendlyCoachError(coachError.message)}</p>
                <button
                  type="button"
                  data-testid="onboarding-chat-retry"
                  disabled={busy}
                  onClick={retryCoach}
                  className="mt-2 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
                >
                  Try Again
                </button>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {(phase === "goals" || phase === "ready" || showGoalMenu) && !finished && (
            <div className="max-h-[40%] shrink-0 overflow-y-auto border-t border-line p-3 sm:p-4">
              <GoalDiscovery
                options={state.data?.goal_interest_options ?? []}
                preferences={prefs}
                suggestedSkills={state.data?.suggested_skills ?? []}
                suggestedProjects={state.data?.suggested_projects ?? []}
                suggestedRoles={state.data?.suggested_roles ?? []}
                suggestedTechnicalAreas={state.data?.suggested_technical_areas ?? []}
                projectOptions={state.data?.project_options ?? []}
                projectAspectOptions={state.data?.project_aspect_options ?? []}
                resumeHighlights={state.data?.resume_highlights}
                nextGoalFollowup={state.data?.next_goal_followup}
                followupsComplete={state.data?.followups_complete}
                phase={phase}
                showGoalMenu={Boolean(state.data?.show_goal_menu) || !prefs?.interests?.length}
                goalsReady={goalsReady}
                pending={goalsBusy}
                onSaveInterests={(interests) => saveGoals.mutate({ interests })}
                onSaveDetails={(patch) => saveGoals.mutate(patch)}
                onConfirmAndStart={() => finish.mutate()}
              />
            </div>
          )}

          <div className="shrink-0 border-t border-line bg-white p-3 sm:p-4">
            <div className="mb-2 flex flex-wrap gap-2">
              {!finished && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink"
                  onClick={() => setShowStartersOverride(true)}
                >
                  Change topic
                </button>
              )}
              {!finished && phase !== "profile" && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink"
                  onClick={() =>
                    send("Let's go back to reviewing my vault profile for a moment.")
                  }
                >
                  Return to profile review
                </button>
              )}
              {!finished && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink"
                  onClick={() => send("I'd like to skip this question and move on.")}
                >
                  Skip this question
                </button>
              )}
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder={
                  finished
                    ? "Add or correct a project, skill, or education detail…"
                    : state.data?.has_resume_welcome
                      ? "Type your reply…"
                      : "Tell me about a project, internship, or skill…"
                }
                className="min-w-0 flex-1 rounded-xl border border-line bg-page/40 px-4 py-2.5 text-sm outline-none transition focus:border-accent focus:bg-white focus:ring-2 focus:ring-accent/20"
                disabled={busy}
                data-testid="onboarding-chat-input"
              />
              <button
                type="button"
                onClick={() => send()}
                disabled={busy || !input.trim()}
                data-testid="onboarding-chat-send"
                className="rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-40 sm:self-auto"
              >
                Send
              </button>
            </div>
          </div>
        </section>

        <aside className="flex min-h-0 flex-col gap-4 overflow-y-auto lg:max-h-full">
          <VaultSidebar items={vaultItems} />

          <Link
            to="/readiness"
            className="block rounded-lg border border-accent/30 bg-accent-soft/50 p-4 hover:bg-accent-soft"
            data-testid="readiness-onboarding-card"
          >
            <h2 className="text-sm font-semibold text-accent-strong">
              Check how ready your resume is for interviews
            </h2>
            <p className="mt-1 text-xs text-ink-soft">
              See which claims interviewers often ask about — without judging honesty.
            </p>
          </Link>

          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-stone-800">Resume</h2>
            <p className="mt-1 text-xs text-stone-500">
              Optional — PDF up to 10 MB. Successful upload starts the AI conversation.
            </p>
            <div
              role="button"
              tabIndex={upload.isPending ? -1 : 0}
              aria-disabled={upload.isPending}
              aria-label="Upload resume PDF"
              data-testid="resume-upload-dropzone"
              onKeyDown={(event) => {
                if (upload.isPending) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  resumeInputRef.current?.click();
                }
              }}
              onClick={() => {
                if (!upload.isPending) resumeInputRef.current?.click();
              }}
              onDragEnter={(event) => {
                event.preventDefault();
                if (!upload.isPending) setDragOver(true);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                if (!upload.isPending) setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragOver(false);
                pickResume(event.dataTransfer.files?.[0]);
              }}
              className={`mt-3 flex min-w-0 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed px-4 py-5 text-center transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                upload.isPending
                  ? "cursor-not-allowed border-line bg-stone-50 opacity-80"
                  : dragOver
                    ? "border-accent bg-accent-soft"
                    : "border-line bg-page hover:border-accent hover:bg-surface"
              }`}
            >
              {upload.isPending ? (
                <span className="inline-flex items-center gap-2 text-sm font-medium text-ink">
                  <span
                    className="h-4 w-4 motion-safe:animate-spin rounded-full border-2 border-accent/30 border-t-accent"
                    aria-hidden="true"
                  />
                  Extracting your experience…
                </span>
              ) : (
                <span className="text-sm font-medium text-ink">Upload resume PDF</span>
              )}
              <span className="mt-1 text-[11px] text-stone-500">
                Drag and drop or click — speeds up vault setup
              </span>
              <input
                ref={resumeInputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                disabled={upload.isPending}
                onChange={(e) => {
                  pickResume(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </div>
            {resumeFile && (
              <p className="mt-2 truncate text-xs text-ink-soft" title={resumeFile.name}>
                {resumeFile.name} · {formatBytes(resumeFile.size)}
              </p>
            )}
            {upload.data && (
              <p className="mt-2 text-xs text-emerald-700" data-testid="resume-upload-success">
                {upload.data.items_created.length === 0
                  ? "No new vault items — those titles were already saved."
                  : `Added ${upload.data.items_created.length} vault item${
                      upload.data.items_created.length === 1 ? "" : "s"
                    } from your resume.`}
                {upload.data.welcome_seeded
                  ? " Your coach started the conversation."
                  : ""}
              </p>
            )}
            {uploadError && (
              <div
                className="mt-2 rounded-md bg-red-50 p-3 text-xs text-red-700"
                data-testid="resume-upload-error"
                role="alert"
              >
                <p>{uploadError.message}</p>
                {uploadHints && uploadHints.length > 0 && (
                  <ul className="mt-2 list-disc space-y-0.5 pl-4 text-red-600/90">
                    {uploadHints.map((hint) => (
                      <li key={hint}>{hint}</li>
                    ))}
                  </ul>
                )}
                <button
                  type="button"
                  className="mt-2 font-semibold text-accent-strong underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  onClick={() => {
                    upload.reset();
                    if (resumeFile) upload.mutate(resumeFile);
                    else resumeInputRef.current?.click();
                  }}
                >
                  Try again
                </button>
              </div>
            )}
          </div>

          {finished ? (
            <button
              type="button"
              data-testid="go-to-tracks"
              onClick={() => navigate("/", { replace: true })}
              className="rounded-lg bg-accent px-4 py-3.5 text-center text-sm font-semibold text-white hover:bg-accent-strong"
            >
              Go to Tracks
            </button>
          ) : canStartPreparing ? (
            <div className="space-y-2">
              <button
                type="button"
                data-testid="finish-onboarding"
                onClick={() => finish.mutate()}
                disabled={finish.isPending}
                className="w-full rounded-lg bg-accent px-4 py-3.5 text-center text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
              >
                {finish.isPending ? "Saving…" : "Start Preparing"}
              </button>
              {finish.error instanceof Error && (
                <p className="text-center text-xs text-red-600">
                  {finish.error.message}
                </p>
              )}
            </div>
          ) : missing.length > 0 ? (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs text-amber-900">
              Still needed:{" "}
              {missing.map((c) => REQUIRED_LABELS[c] ?? c).join(", ")}.
            </p>
          ) : (
            <p className="rounded-lg border border-accent/30 bg-accent-soft/50 px-4 py-3 text-center text-xs text-ink">
              Pick your interview preparation goals above to continue.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
