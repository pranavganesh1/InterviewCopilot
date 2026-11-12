import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import EmojiPicker from "../components/EmojiPicker";
import GoalDiscovery from "../components/GoalDiscovery";
import { VaultSidebar } from "../components/VaultSidebar";

const NEAR_BOTTOM_PX = 120;
const TEXTAREA_MAX_LINES = 5;
const CHAT_TIMEOUT_MS = 30_000;
const STILL_THINKING_MS = 8_000;
const IDLE_NUDGE_MS = 45_000;
const IDLE_NUDGE_SECOND_MS = 120_000;
const EMPTY_REPLY_FALLBACK =
  "I didn't catch that. Could you say it a different way?";
const DEFAULT_DOC_TITLE = "InterviewCopilot";

type ToastKind = "info" | "success" | "error";
type ToastItem = {
  id: string;
  kind: ToastKind;
  title: string;
  detail?: string;
  actionLabel?: string;
  onAction?: () => void;
  ms: number;
};

function isNearBottom(el: HTMLElement, threshold = NEAR_BOTTOM_PX): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

function messageKey(role: string, content: string, index: number): string {
  return `${role}:${index}:${content.slice(0, 48)}`;
}

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

function TypingIndicator() {
  return (
    <span
      className="inline-flex items-center gap-1 px-0.5"
      data-testid="typing-indicator"
      aria-label="Coach is typing"
    >
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

function profileCompleteness(items: { category: string; source?: string }[], hasResumeWelcome: boolean) {
  const hasSkills = items.some((i) => i.category === "skill");
  const hasProjects = items.some((i) => i.category === "project");
  const hasEducation = items.some((i) => i.category === "education");
  const hasResume =
    hasResumeWelcome || items.some((i) => (i.source || "").includes("resume"));
  const score =
    (hasSkills ? 25 : 0) +
    (hasProjects ? 25 : 0) +
    (hasEducation ? 25 : 0) +
    (hasResume ? 25 : 0);
  let nextHint = "Your profile looks complete — keep refining anytime.";
  if (!hasProjects) nextHint = "Add a project to reach 100%";
  else if (!hasSkills) nextHint = "Add a skill to reach 100%";
  else if (!hasEducation) nextHint = "Add education to reach 100%";
  else if (!hasResume) nextHint = "Upload a resume to reach 100%";
  return { percent: score, nextHint };
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const stickToBottomRef = useRef(true);
  const forceScrollRef = useRef(false);
  const initialScrollDoneRef = useRef(false);
  const prevMsgCountRef = useRef(0);
  const [historyAnchor, setHistoryAnchor] = useState<number | null>(null);
  const [showNewPill, setShowNewPill] = useState(false);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [keyboardInset, setKeyboardInset] = useState(0);
  const [mobilePane, setMobilePane] = useState<"chat" | "profile">("chat");
  const [vaultChips, setVaultChips] = useState<
    { id: string; title: string }[]
  >([]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [stillThinking, setStillThinking] = useState(false);
  const [pendingUser, setPendingUser] = useState<{
    content: string;
    status: "sending" | "failed";
  } | null>(null);
  const [emptyFallback, setEmptyFallback] = useState<string | null>(null);
  const [nudge, setNudge] = useState<{
    text: string;
    chips: string[];
  } | null>(null);
  const [nudgeCount, setNudgeCount] = useState(0);
  const [activityEpoch, setActivityEpoch] = useState(0);
  const lastActivityRef = useRef(Date.now());
  const baseTitleRef = useRef(
    typeof document !== "undefined" ? document.title || DEFAULT_DOC_TITLE : DEFAULT_DOC_TITLE,
  );
  const toastTimers = useRef<Map<string, number>>(new Map());

  const bumpActivity = () => {
    lastActivityRef.current = Date.now();
    setActivityEpoch((n) => n + 1);
  };

  const pushToast = (
    kind: ToastKind,
    title: string,
    detail?: string,
    action?: { label: string; onAction: () => void },
  ) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const ms = kind === "error" ? 8000 : 5000;
    setToasts((prev) =>
      [
        ...prev,
        {
          id,
          kind,
          title,
          detail,
          actionLabel: action?.label,
          onAction: action?.onAction,
          ms,
        },
      ].slice(-3),
    );
    const timer = window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
      toastTimers.current.delete(id);
    }, ms);
    toastTimers.current.set(id, timer);
  };

  const dismissToast = (id: string) => {
    const t = toastTimers.current.get(id);
    if (t) window.clearTimeout(t);
    toastTimers.current.delete(id);
    setToasts((prev) => prev.filter((x) => x.id !== id));
  };

  const state = useQuery({
    queryKey: ["onboarding-state"],
    queryFn: () => api<OnboardingState>("/onboarding/state"),
  });

  const chat = useMutation({
    mutationFn: (message: string) =>
      api<ChatResult>("/onboarding/chat", {
        method: "POST",
        body: JSON.stringify({ message }),
        signal: AbortSignal.timeout(CHAT_TIMEOUT_MS),
      }),
    onSuccess: (data) => {
      setFailedMessage(null);
      setPendingUser(null);
      setStillThinking(false);
      setInput("");
      setEmptyFallback(
        (data.reply || "").trim() ? null : EMPTY_REPLY_FALLBACK,
      );
      const added = [
        ...(data.items_created ?? []),
        ...(data.items_updated ?? []),
      ]
        .filter((item) => item?.title)
        .map((item) => ({ id: item.id, title: item.title }));
      if (added.length) {
        setVaultChips(added.slice(0, 4));
        pushToast(
          "success",
          `Saved to your profile: ${added[0].title}`,
        );
      }
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        document.title = "(1) New reply from Aiko";
      }
      setNudge(null);
      bumpActivity();
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    onError: (err, message) => {
      setFailedMessage(message);
      setPendingUser({ content: message, status: "failed" });
      setStillThinking(false);
      const detail =
        err instanceof Error ? err.message : "Please try again.";
      pushToast("error", "Message failed", detail, {
        label: "Retry",
        onAction: () => {
          setPendingUser({ content: message, status: "sending" });
          setFailedMessage(null);
          chat.mutate(message);
        },
      });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
  });

  const starter = useMutation({
    mutationFn: (starterId: string) =>
      api<ChatResult>("/onboarding/starter", {
        method: "POST",
        body: JSON.stringify({ starter_id: starterId }),
        signal: AbortSignal.timeout(CHAT_TIMEOUT_MS),
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
    onSuccess: (data) => {
      setShowStartersOverride(true);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      const n = data.items_created?.length ?? 0;
      pushToast(
        "success",
        n ? `Resume uploaded · ${n} item${n === 1 ? "" : "s"}` : "Resume uploaded",
      );
    },
    onError: (err) => {
      pushToast(
        "error",
        "Resume upload failed",
        err instanceof Error ? err.message : undefined,
      );
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
      pushToast("success", "Onboarding finished");
      await refresh();
      navigate("/", { replace: true });
    },
  });

  useEffect(() => {
    if (!chat.isPending) {
      setStillThinking(false);
      return;
    }
    const t = window.setTimeout(() => setStillThinking(true), STILL_THINKING_MS);
    return () => window.clearTimeout(t);
  }, [chat.isPending]);

  useEffect(() => {
    const onOnline = () => pushToast("success", "Connection restored");
    const onOffline = () =>
      pushToast("error", "Connection lost", "Messages may not send until you're back online.");
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === "visible") {
        document.title = baseTitleRef.current;
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const suggestedProjectsRef = useRef<string[]>([]);
  const suggestedSkillsRef = useRef<string[]>([]);
  useEffect(() => {
    suggestedProjectsRef.current = state.data?.suggested_projects ?? [];
    suggestedSkillsRef.current = state.data?.suggested_skills ?? [];
  }, [state.data?.suggested_projects, state.data?.suggested_skills]);

  useEffect(() => {
    if (nudgeCount >= 2 || nudge) return;
    if (chat.isPending || starter.isPending) return;

    const wait = nudgeCount === 0 ? IDLE_NUDGE_MS : IDLE_NUDGE_SECOND_MS;
    let cancelled = false;

    const showNudge = () => {
      if (cancelled) return;
      if (document.visibilityState === "hidden") return;
      if (chat.isPending || starter.isPending) return;
      const projects = suggestedProjectsRef.current;
      const skills = suggestedSkillsRef.current;
      const chips: string[] = [];
      if (projects[0]) chips.push(`Tell me about my ${projects[0]} project`);
      if (skills[0]) chips.push(`I'd like to practise ${skills[0]}`);
      if (chips.length < 2) chips.push("Add a project");
      if (chips.length < 2) chips.push("Add a skill");
      setNudge({
        text: "Still here — want a gentle prompt?",
        chips: chips.slice(0, 2),
      });
      setNudgeCount((c) => c + 1);
    };

    const id = window.setTimeout(showNudge, wait);
    const onVis = () => {
      if (document.visibilityState !== "visible" || cancelled) return;
      if (Date.now() - lastActivityRef.current >= wait) showNudge();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [activityEpoch, chat.isPending, starter.isPending, nudge, nudgeCount]);

  const busy =
    chat.isPending || starter.isPending || saveGoals.isPending || finish.isPending;
  const goalsBusy = busy;

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const sync = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      setKeyboardInset(inset > 40 ? inset : 0);
    };
    sync();
    vv.addEventListener("resize", sync);
    vv.addEventListener("scroll", sync);
    return () => {
      vv.removeEventListener("resize", sync);
      vv.removeEventListener("scroll", sync);
    };
  }, []);

  useEffect(() => {
    if (!vaultChips.length) return;
    const t = window.setTimeout(() => setVaultChips([]), 4200);
    return () => window.clearTimeout(t);
  }, [vaultChips]);

  useLayoutEffect(() => {
    if (historyAnchor !== null || state.isLoading || !state.data) return;
    setHistoryAnchor(state.data.messages?.length ?? 0);
  }, [historyAnchor, state.isLoading, state.data]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const line = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    const max = line * TEXTAREA_MAX_LINES + 20;
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [input]);

  const scrollMessagesToBottom = (behavior: ScrollBehavior) => {
    const panel = messagesRef.current;
    if (!panel) return;
    panel.scrollTo({ top: panel.scrollHeight, behavior });
    stickToBottomRef.current = true;
    setShowNewPill(false);
  };

  useEffect(() => {
    const panel = messagesRef.current;
    if (!panel) return;
    const count =
      (state.data?.messages?.length ?? 0) +
      (chat.isPending || starter.isPending || saveGoals.isPending ? 1 : 0);

    if (!initialScrollDoneRef.current) {
      if (state.isLoading) return;
      panel.scrollTop = panel.scrollHeight;
      initialScrollDoneRef.current = true;
      stickToBottomRef.current = true;
      prevMsgCountRef.current = count;
      return;
    }

    if (count === prevMsgCountRef.current && !forceScrollRef.current) return;
    const grew = count > prevMsgCountRef.current;
    prevMsgCountRef.current = count;

    const force = forceScrollRef.current;
    if (force || stickToBottomRef.current) {
      forceScrollRef.current = false;
      // Instant jump after send so a later user scroll-up is not fought by smooth scroll.
      requestAnimationFrame(() =>
        scrollMessagesToBottom(force ? "auto" : "smooth"),
      );
      return;
    }

    if (grew) setShowNewPill(true);
  }, [
    state.data?.messages?.length,
    state.isLoading,
    chat.isPending,
    starter.isPending,
    saveGoals.isPending,
    chat.isError,
    vaultChips.length,
  ]);

  const send = (override?: string) => {
    const message = (override ?? input).trim();
    if (!message || busy) return;
    chat.reset();
    setFailedMessage(null);
    setEmptyFallback(null);
    setNudge(null);
    bumpActivity();
    forceScrollRef.current = true;
    stickToBottomRef.current = true;
    setShowNewPill(false);
    setPendingUser({ content: message, status: "sending" });
    // Keep the message visible until success so failures can retry without retyping.
    setInput(message);
    chat.mutate(message);
  };

  const insertEmoji = (emoji: string) => {
    const el = textareaRef.current;
    if (!el) {
      setInput((prev) => prev + emoji);
      return;
    }
    const start = el.selectionStart ?? input.length;
    const end = el.selectionEnd ?? input.length;
    const next = input.slice(0, start) + emoji + input.slice(end);
    setInput(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + emoji.length;
      el.setSelectionRange(pos, pos);
    });
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

  const baseMessages = state.data?.messages ?? [];
  const serverHasPendingUser =
    pendingUser &&
    baseMessages.some(
      (m) => m.role === "user" && m.content === pendingUser.content,
    );
  const messages = [
    ...baseMessages,
    ...(pendingUser && !serverHasPendingUser
      ? [{ role: "user", content: pendingUser.content, _local: true }]
      : []),
    ...(emptyFallback && !chat.isPending
      ? [{ role: "assistant", content: emptyFallback, _fallback: true }]
      : []),
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

  const { percent: profilePercent, nextHint } = profileCompleteness(
    vaultItems,
    state.data?.has_resume_welcome === true,
  );
  const showQuickChips =
    (messages.length === 0 || startersVisible || suggestedReplies.length > 0) &&
    !busy;
  const hasResumeSignal =
    state.data?.has_resume_welcome === true ||
    vaultItems.some((i) => (i.source || "").includes("resume")) ||
    Boolean(upload.data);

  const resumeDropzone = (
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
      className={`flex min-w-0 cursor-pointer flex-col justify-center rounded-2xl border border-dashed px-4 py-3 text-center transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
        upload.isPending
          ? "cursor-not-allowed border-line bg-page opacity-80"
          : dragOver
            ? "border-accent bg-accent-soft"
            : "border-line bg-page/60 hover:border-accent hover:bg-accent-soft/40"
      }`}
    >
      {upload.isPending ? (
        <span className="inline-flex items-center justify-center gap-2 text-sm font-medium text-ink">
          <span
            className="h-4 w-4 motion-safe:animate-spin rounded-full border-2 border-accent/30 border-t-accent"
            aria-hidden="true"
          />
          Extracting your experience…
        </span>
      ) : (
        <span className="text-sm font-medium text-ink">Upload resume PDF</span>
      )}
      <span className="mt-0.5 text-[11px] text-ink-soft">
        Drag and drop or click — PDF up to 10 MB
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
  );

  const resumeStatus = (
    <>
      {resumeFile && (
        <p className="truncate text-xs text-ink-soft" title={resumeFile.name}>
          {resumeFile.name} · {formatBytes(resumeFile.size)}
        </p>
      )}
      {upload.data && (
        <p className="text-xs text-emerald-700" data-testid="resume-upload-success">
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
          className="rounded-xl bg-red-50 p-3 text-xs text-red-700"
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
    </>
  );

  const resumePanel = (
    <div className="space-y-3">
      <p className="text-xs text-ink-soft">
        {hasResumeSignal
          ? "Replace or refresh your resume anytime from the upload bar above."
          : "Use the upload bar above to add a PDF — Aiko builds your profile from it."}
      </p>
      <Link
        to="/readiness"
        className="block rounded-2xl border border-accent/25 bg-accent-soft/50 p-3 transition hover:-translate-y-0.5 hover:bg-accent-soft hover:shadow-card"
        data-testid="readiness-onboarding-card"
      >
        <h2 className="text-sm font-semibold text-accent-strong">
          Check how ready your resume is for interviews
        </h2>
        <p className="mt-1 text-xs text-ink-soft">
          See which claims interviewers often ask about — without judging honesty.
        </p>
      </Link>
    </div>
  );

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col overflow-hidden"
      data-testid="onboarding-page"
      style={keyboardInset ? { paddingBottom: keyboardInset } : undefined}
    >
      <div
        className="pointer-events-none absolute -left-16 top-8 h-56 w-56 rounded-full bg-accent/15 blur-3xl"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -right-10 bottom-10 h-64 w-64 rounded-full bg-accent-soft blur-3xl"
        aria-hidden
      />

      <div
        className="relative z-10 mb-2 shrink-0 space-y-1.5"
        data-testid="resume-upload-bar"
      >
        {resumeDropzone}
        {resumeStatus}
      </div>

      <div
        role="tablist"
        aria-label="Onboarding views"
        data-testid="mobile-pane-switcher"
        className="relative z-10 mb-2 flex shrink-0 gap-1 rounded-2xl border border-line/80 bg-surface/80 p-1 backdrop-blur-md lg:hidden"
      >
        <button
          type="button"
          role="tab"
          aria-selected={mobilePane === "chat"}
          data-testid="mobile-pane-chat"
          onClick={() => setMobilePane("chat")}
          className={`min-h-11 flex-1 rounded-xl text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
            mobilePane === "chat"
              ? "bg-accent text-white shadow-card"
              : "text-ink-soft"
          }`}
        >
          Chat
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobilePane === "profile"}
          data-testid="mobile-pane-profile"
          onClick={() => setMobilePane("profile")}
          className={`relative min-h-11 flex-1 rounded-xl text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
            mobilePane === "profile"
              ? "bg-accent text-white shadow-card"
              : "text-ink-soft"
          }`}
        >
          Profile
          <span
            className={`ml-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-semibold ${
              mobilePane === "profile"
                ? "bg-white/20 text-white"
                : "bg-accent-soft text-accent-strong"
            }`}
          >
            {profilePercent}%
          </span>
        </button>
      </div>

      <div className="relative z-10 grid min-h-0 flex-1 gap-4 overflow-hidden lg:grid-cols-[minmax(0,1.62fr)_minmax(0,1fr)]">
        <section
          data-testid="onboarding-chat-panel"
          aria-label="Coach chat"
          className={`flex min-h-0 min-w-0 flex-col overflow-hidden rounded-3xl border border-line/80 bg-surface/85 shadow-card backdrop-blur-md ${
            mobilePane === "chat" ? "flex" : "hidden lg:flex"
          }`}
        >
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line/70 px-4 py-3 sm:px-5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="relative">
                <CoachAvatar mood={coachMood} />
                <span
                  className={`absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full ring-2 ring-surface ${
                    busy ? "bg-amber-400 coach-status-pulse" : "bg-emerald-500"
                  }`}
                  aria-hidden
                />
              </div>
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-ink">Aiko</h2>
                <p className="truncate text-xs text-ink-soft">Interview Coach</p>
              </div>
            </div>
            <span
              data-testid="onboarding-status-chip"
              title={
                finished && state.data?.onboarding_completed_at
                  ? `Completed ${new Date(state.data.onboarding_completed_at).toLocaleString()}`
                  : undefined
              }
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 ${
                finished
                  ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
                  : "bg-accent-soft text-accent-strong ring-accent/20"
              }`}
            >
              {finished ? (
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                  <path
                    d="M3.5 8.2 6.8 11.3 12.5 4.8"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              ) : null}
              {finished ? "Onboarding complete" : "In progress"}
            </span>
          </div>

          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
            <div
              ref={messagesRef}
              role="log"
              aria-live="polite"
              aria-relevant="additions"
              data-testid="onboarding-messages"
              onScroll={() => {
                const panel = messagesRef.current;
                if (!panel) return;
                const near = isNearBottom(panel);
                stickToBottomRef.current = near;
                if (near) setShowNewPill(false);
              }}
              className="min-h-0 flex-1 space-y-3 overflow-x-hidden overflow-y-auto overscroll-contain px-4 py-4 sm:px-5"
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
              {messages.map((m, i) => {
                const key = messageKey(m.role, m.content, i);
                const isNew =
                  m.role !== "pending" &&
                  historyAnchor !== null &&
                  i >= historyAnchor;
                const enterClass =
                  isNew && m.role === "user"
                    ? "coach-bubble-enter-user"
                    : isNew
                      ? "coach-bubble-enter-assistant"
                      : "";
                const prevRole = i > 0 ? messages[i - 1]?.role : null;
                const showAvatar =
                  m.role !== "user" &&
                  (i === 0 || prevRole === "user" || prevRole === undefined);
                return (
                  <div
                    key={key}
                    className={`flex max-w-[85%] gap-2 sm:max-w-[min(85%,36rem)] ${
                      m.role === "user" ? "ml-auto flex-row-reverse" : "mr-auto"
                    } ${enterClass}`}
                  >
                    {m.role !== "user" && (
                      <div className="w-8 shrink-0">
                        {showAvatar ? (
                          <CoachAvatar
                            size="sm"
                            mood={m.role === "pending" ? "thinking" : "idle"}
                          />
                        ) : null}
                      </div>
                    )}
                    <div className="min-w-0">
                      <div
                        className={`min-w-0 break-words rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm [overflow-wrap:anywhere] ${
                          m.role === "user"
                            ? "rounded-br-md bg-accent text-white"
                            : m.role === "pending"
                              ? "rounded-bl-md border border-line bg-accent-soft/50 text-ink-soft"
                              : "rounded-bl-md border border-line bg-page/80 text-ink"
                        }`}
                      >
                        {m.role === "pending" ? (
                          <div>
                            <TypingIndicator />
                            {stillThinking && chat.isPending && (
                              <p
                                className="mt-1.5 text-[11px] text-ink-soft"
                                data-testid="still-thinking"
                              >
                                Still thinking… this can take a moment
                              </p>
                            )}
                          </div>
                        ) : (
                          m.content
                        )}
                      </div>
                      {m.role === "user" &&
                        pendingUser?.status === "failed" &&
                        pendingUser.content === m.content && (
                          <p
                            className="mt-1 text-right text-[11px] font-medium text-amber-700"
                            data-testid="message-not-delivered"
                          >
                            Not delivered
                          </p>
                        )}
                    </div>
                  </div>
                );
              })}

              {vaultChips.length > 0 && (
                <div
                  className="flex flex-wrap gap-2 pl-10"
                  data-testid="vault-add-chips"
                  aria-live="polite"
                >
                  {vaultChips.map((chip) => (
                    <span
                      key={chip.id}
                      className="coach-vault-chip inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-800"
                    >
                      <svg
                        viewBox="0 0 16 16"
                        className="h-3.5 w-3.5 shrink-0"
                        aria-hidden
                      >
                        <circle cx="8" cy="8" r="7" fill="#10b981" opacity="0.2" />
                        <path
                          d="M4.5 8.2 7 10.6 11.5 5.5"
                          fill="none"
                          stroke="#059669"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      Added to your profile: {chip.title}
                    </span>
                  ))}
                </div>
              )}

              {(phase === "goals" || phase === "ready" || showGoalMenu) &&
                !finished && (
                  <div className="rounded-2xl border border-line/80 bg-surface/90 p-3">
                    <GoalDiscovery
                      options={state.data?.goal_interest_options ?? []}
                      preferences={prefs}
                      suggestedSkills={state.data?.suggested_skills ?? []}
                      suggestedProjects={state.data?.suggested_projects ?? []}
                      suggestedRoles={state.data?.suggested_roles ?? []}
                      suggestedTechnicalAreas={
                        state.data?.suggested_technical_areas ?? []
                      }
                      projectOptions={state.data?.project_options ?? []}
                      projectAspectOptions={
                        state.data?.project_aspect_options ?? []
                      }
                      resumeHighlights={state.data?.resume_highlights}
                      nextGoalFollowup={state.data?.next_goal_followup}
                      followupsComplete={state.data?.followups_complete}
                      phase={phase}
                      showGoalMenu={
                        Boolean(state.data?.show_goal_menu) ||
                        !prefs?.interests?.length
                      }
                      goalsReady={goalsReady}
                      pending={goalsBusy}
                      onSaveInterests={(interests) =>
                        saveGoals.mutate({ interests })
                      }
                      onSaveDetails={(patch) => saveGoals.mutate(patch)}
                      onConfirmAndStart={() => finish.mutate()}
                    />
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
                    className="mt-2 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
                  >
                    Try Again
                  </button>
                </div>
              )}
            </div>

            {showNewPill && (
              <button
                type="button"
                data-testid="new-message-pill"
                aria-label="Jump to new message"
                onClick={() => scrollMessagesToBottom("smooth")}
                className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 inline-flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-semibold text-white shadow-md hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                New message
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                  <path
                    d="M4 6.5 8 10.5 12 6.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            )}
          </div>

          <div
            data-testid="onboarding-chat-composer"
            className="shrink-0 border-t border-line/70 bg-surface/90 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:p-4"
          >
            {nudge && !busy && (
              <div
                data-testid="idle-nudge"
                className="mb-2 rounded-2xl border border-accent/20 bg-accent-soft/60 px-3 py-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs text-ink">{nudge.text}</p>
                  <button
                    type="button"
                    aria-label="Dismiss suggestion"
                    className="text-ink-faint hover:text-ink"
                    onClick={() => setNudge(null)}
                  >
                    ×
                  </button>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {nudge.chips.map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      data-testid="idle-nudge-chip"
                      className="min-h-9 rounded-full border border-accent/25 bg-surface px-2.5 text-[11px] font-medium text-accent-strong focus-visible:outline-2 focus-visible:outline-accent"
                      onClick={() => {
                        setInput(chip);
                        setNudge(null);
                        bumpActivity();
                        requestAnimationFrame(() => textareaRef.current?.focus());
                      }}
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {showQuickChips && (
              <div className="mb-2 space-y-2">
                {startersVisible && (
                  <ConversationStarters
                    starters={starters}
                    skills={state.data?.suggested_skills ?? []}
                    projects={state.data?.suggested_projects ?? []}
                    vaultItems={vaultItems}
                    activeMode={state.data?.conversation_mode}
                    pending={busy}
                    onSelectStarter={(id) => {
                      setLastStarterId(id);
                      forceScrollRef.current = true;
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
                {suggestedReplies.length > 0 && !finished && (
                  <div
                    className="flex flex-wrap gap-2"
                    data-testid="suggested-replies"
                  >
                    {suggestedReplies.map((reply) => (
                      <button
                        key={reply}
                        type="button"
                        disabled={busy}
                        onClick={() => send(reply)}
                        className="min-h-9 rounded-full border border-accent/25 bg-accent-soft/70 px-3 py-1.5 text-xs font-medium text-accent-strong transition hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
                      >
                        {reply}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="mb-2 flex flex-wrap gap-2">
              {!finished && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  onClick={() => setShowStartersOverride(true)}
                >
                  Change topic
                </button>
              )}
              {!finished && phase !== "profile" && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  onClick={() =>
                    send(
                      "Let's go back to reviewing my vault profile for a moment.",
                    )
                  }
                >
                  Return to profile review
                </button>
              )}
              {!finished && (
                <button
                  type="button"
                  className="rounded-md px-2 py-1 text-[11px] font-medium text-ink-soft hover:bg-page hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                  onClick={() =>
                    send("I'd like to skip this question and move on.")
                  }
                >
                  Skip this question
                </button>
              )}
            </div>
            <div className="flex items-end gap-2">
              <div className="relative shrink-0">
                <button
                  type="button"
                  data-testid="emoji-picker-button"
                  aria-label="Insert emoji"
                  aria-expanded={emojiOpen}
                  disabled={busy}
                  onClick={() => setEmojiOpen((v) => !v)}
                  className="min-h-11 min-w-11 rounded-xl border border-line bg-page/40 text-base leading-none hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
                >
                  😊
                </button>
                <EmojiPicker
                  open={emojiOpen}
                  onClose={() => setEmojiOpen(false)}
                  onPick={insertEmoji}
                />
              </div>
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value.slice(0, 4000));
                  if (nudge) setNudge(null);
                  bumpActivity();
                }}
                onKeyDown={(e) => {
                  bumpActivity();
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
                className="max-h-[7.5rem] min-h-11 min-w-0 flex-1 resize-none overflow-y-auto rounded-xl border border-line bg-page/40 px-4 py-2.5 text-sm leading-5 outline-none transition focus:border-accent focus:bg-surface focus:ring-2 focus:ring-accent/20 disabled:opacity-60"
                disabled={busy}
                data-testid="onboarding-chat-input"
                aria-label="Message your coach"
              />
              <button
                type="button"
                onClick={() => send()}
                disabled={busy || !input.trim()}
                data-testid="onboarding-chat-send"
                aria-label={busy ? "Sending" : "Send message"}
                className="inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-xl bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40 sm:min-w-[4.5rem]"
              >
                {busy ? (
                  <span
                    className="h-4 w-4 motion-safe:animate-spin rounded-full border-2 border-white/30 border-t-white"
                    aria-hidden
                  />
                ) : (
                  "Send"
                )}
              </button>
            </div>
          </div>
        </section>

        <aside
          className={`min-h-0 min-w-0 ${
            mobilePane === "profile" ? "flex" : "hidden lg:flex"
          }`}
          aria-label="Profile vault"
        >
          <VaultSidebar
            items={vaultItems}
            loading={state.isLoading}
            errorMessage={
              state.error instanceof Error ? state.error.message : null
            }
            onRetry={() => state.refetch()}
            percentComplete={profilePercent}
            nextHint={nextHint}
            finished={finished}
            canStartPreparing={canStartPreparing}
            finishPending={finish.isPending}
            finishError={
              finish.error instanceof Error ? finish.error.message : null
            }
            onGoToTracks={() => navigate("/", { replace: true })}
            onFinish={() => finish.mutate()}
            resumePanel={resumePanel}
          />
        </aside>
      </div>

      <div
        className="pointer-events-none fixed inset-x-3 top-[max(0.75rem,env(safe-area-inset-top))] z-50 flex flex-col items-stretch gap-2 sm:inset-x-auto sm:right-4 sm:left-auto sm:w-80 lg:top-16"
        data-testid="toast-stack"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            aria-live={t.kind === "error" ? "assertive" : "polite"}
            data-testid={`toast-${t.kind}`}
            className="coach-toast pointer-events-auto flex items-start gap-2 rounded-2xl border border-line/80 bg-surface/90 px-3 py-2.5 text-sm shadow-card backdrop-blur-md"
            onMouseEnter={() => {
              const timer = toastTimers.current.get(t.id);
              if (timer) window.clearTimeout(timer);
            }}
            onMouseLeave={() => {
              const timer = window.setTimeout(() => dismissToast(t.id), t.ms);
              toastTimers.current.set(t.id, timer);
            }}
          >
            <span className="mt-0.5 text-base" aria-hidden>
              {t.kind === "success" ? "✓" : t.kind === "error" ? "!" : "i"}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-medium text-ink">{t.title}</p>
              {t.detail && (
                <p className="mt-0.5 text-xs text-ink-soft">{t.detail}</p>
              )}
              {t.actionLabel && t.onAction && (
                <button
                  type="button"
                  className="mt-1 text-xs font-semibold text-accent-strong underline-offset-2 hover:underline"
                  onClick={() => {
                    t.onAction?.();
                    dismissToast(t.id);
                  }}
                >
                  {t.actionLabel}
                </button>
              )}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              className="text-ink-faint hover:text-ink"
              onClick={() => dismissToast(t.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
