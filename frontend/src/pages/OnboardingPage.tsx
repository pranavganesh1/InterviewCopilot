import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ChatResult,
  type OnboardingState,
  type VaultItem,
} from "../lib/api";
import { useAuth } from "../context/AuthContext";

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

const CATEGORY_STYLES: Record<string, string> = {
  project: "bg-sky-100 text-sky-700",
  internship: "bg-sky-100 text-sky-700",
  skill: "bg-emerald-100 text-emerald-700",
  achievement: "bg-amber-100 text-amber-700",
  education: "bg-stone-100 text-stone-600",
  other: "bg-stone-100 text-stone-600",
};

const REQUIRED_LABELS: Record<string, string> = {
  project: "a project",
  skill: "skills",
  education: "education",
};

export default function OnboardingPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [input, setInput] = useState("");
  const [coachMarkedComplete, setCoachMarkedComplete] = useState(false);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const resumeInputRef = useRef<HTMLInputElement>(null);
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
    onSuccess: (data) => {
      if (data.onboarding_complete) setCoachMarkedComplete(true);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<{ items_created: { title: string }[]; items_skipped?: number }>(
        "/vault/resume",
        { method: "POST", body: form },
      );
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-state"] }),
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

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.data?.messages.length, chat.isPending]);

  const send = () => {
    const message = input.trim();
    if (!message || chat.isPending) return;
    setInput("");
    chat.mutate(message);
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
  const vaultComplete =
    state.data?.onboarding_complete === true || missing.length === 0;
  const canFinish =
    !finished && (coachMarkedComplete || vaultComplete) && !finish.isPending;

  const messages = [
    ...(state.data?.messages ?? []),
    ...(chat.isPending
      ? [
          {
            role: "pending",
            content: finished
              ? "Updating your profile…"
              : "Your onboarding coach is thinking…",
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-accent">
          Profile setup
        </p>
        <h1 className="text-xl font-semibold tracking-tight">Onboarding</h1>
        <p className="mt-0.5 text-sm text-stone-500">
          {finished
            ? "Your profile is saved. Edit anything below — Tracks stays your home."
            : "Share projects, internships, skills, and education so interviews stay grounded in your story."}
        </p>
      </div>

      {finished && (
        <div
          data-testid="onboarding-finished-banner"
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
        >
          Onboarding completed
          {state.data?.onboarding_completed_at
            ? ` · ${new Date(state.data.onboarding_completed_at).toLocaleDateString()}`
            : ""}
          . You can keep refining your vault anytime.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <section className="flex min-h-[28rem] flex-col overflow-hidden rounded-lg border border-stone-200 bg-white md:min-h-[calc(100vh-11rem)]">
          <div className="flex items-center justify-between gap-3 border-b border-stone-100 bg-page px-4 py-3 sm:px-5">
            <div>
              <h2 className="text-sm font-semibold text-stone-800">
                Conversation
              </h2>
              <p className="text-xs text-stone-500">
                {finished
                  ? "Add or correct details — we won’t restart intake questions"
                  : "Chat with your coach · vault updates as you share"}
              </p>
            </div>
            <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-stone-500 ring-1 ring-stone-200">
              {messages.filter((m) => m.role !== "pending").length} messages
            </span>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4 sm:px-5">
            {messages.length === 0 && (
              <div className="rounded-md border border-dashed border-stone-200 bg-stone-50 px-4 py-8 text-center">
                <p className="text-sm font-medium text-stone-700">
                  {finished
                    ? "Tell us what you’d like to update"
                    : "Start with a project you’ve built"}
                </p>
                <p className="mt-1 text-xs text-stone-500">
                  {finished
                    ? "New skills, projects, or education details go straight into your vault."
                    : "Include stack, your role, and one concrete outcome."}
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`max-w-[min(100%,36rem)] rounded-lg px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
                  m.role === "user"
                    ? "ml-auto bg-accent-soft text-ink"
                    : m.role === "pending"
                      ? "bg-stone-100 italic text-stone-400"
                      : "bg-stone-100 text-stone-800"
                }`}
              >
                {m.content}
              </div>
            ))}
            {chat.error instanceof Error && (
              <p className="text-sm text-red-600">{chat.error.message}</p>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-stone-100 bg-stone-50/60 p-3 sm:p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
                placeholder={
                  finished
                    ? "Add or correct a project, skill, or education detail…"
                    : "Describe a project, internship, or skill…"
                }
                className="min-w-0 flex-1 rounded-md border border-stone-200 bg-white px-4 py-2.5 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
                disabled={chat.isPending}
              />
              <button
                onClick={send}
                disabled={chat.isPending || !input.trim()}
                className="rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-white hover:bg-accent-strong disabled:opacity-40 sm:self-auto"
              >
                Send
              </button>
            </div>
          </div>
        </section>

        <aside className="flex flex-col gap-4">
          <div className="rounded-lg border border-stone-200 bg-white p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-stone-800">Your vault</h2>
              <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600">
                {vaultItems.length} items
              </span>
            </div>
            <p className="mt-1 text-xs text-stone-500">
              What your copilot already knows about you.
            </p>
            <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-0.5">
              {vaultItems.length === 0 && (
                <p className="rounded-md bg-stone-50 px-3 py-4 text-center text-xs text-stone-400">
                  Empty so far — chat or upload a resume.
                </p>
              )}
              {vaultItems.map((item: VaultItem) => (
                <div
                  key={item.id}
                  className="rounded-md border border-stone-100 bg-stone-50/80 px-3 py-2.5"
                >
                  <span
                    className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                      CATEGORY_STYLES[item.category] ?? CATEGORY_STYLES.other
                    }`}
                  >
                    {item.category}
                  </span>
                  <p className="mt-1.5 text-sm font-medium leading-snug text-stone-800">
                    {item.title}
                  </p>
                </div>
              ))}
            </div>
          </div>

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
              Optional — PDF up to 10 MB.
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
          ) : canFinish ? (
            <div className="space-y-2">
              <button
                type="button"
                data-testid="finish-onboarding"
                onClick={() => finish.mutate()}
                disabled={finish.isPending}
                className="w-full rounded-lg bg-accent px-4 py-3.5 text-center text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
              >
                {finish.isPending ? "Saving…" : "Finish Onboarding"}
              </button>
              {finish.error instanceof Error && (
                <p className="text-center text-xs text-red-600">
                  {finish.error.message}
                </p>
              )}
            </div>
          ) : (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-center text-xs text-amber-900">
              Still needed:{" "}
              {missing.map((c) => REQUIRED_LABELS[c] ?? c).join(", ") ||
                "keep chatting with your coach"}
              .
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
