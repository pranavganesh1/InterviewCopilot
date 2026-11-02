import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  type ChatResult,
  type OnboardingState,
  type VaultItem,
} from "../lib/api";

const CATEGORY_STYLES: Record<string, string> = {
  project: "bg-indigo-100 text-indigo-700",
  internship: "bg-sky-100 text-sky-700",
  skill: "bg-emerald-100 text-emerald-700",
  achievement: "bg-amber-100 text-amber-700",
  education: "bg-violet-100 text-violet-700",
  other: "bg-stone-100 text-stone-600",
};

export default function OnboardingPage() {
  const qc = useQueryClient();
  const [input, setInput] = useState("");
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-state"] }),
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<{ items_created: { title: string }[] }>("/vault/resume", {
        method: "POST",
        body: form,
      });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["onboarding-state"] }),
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

  const messages = [
    ...(state.data?.messages ?? []),
    ...(chat.isPending
      ? [
          {
            role: "pending",
            content: "Your onboarding coach is thinking…",
          },
        ]
      : []),
  ];

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_300px]">
      <section className="flex h-[calc(100vh-9rem)] flex-col rounded-2xl border border-stone-200 bg-white">
        <div className="border-b border-stone-100 px-5 py-3">
          <h1 className="font-semibold">Onboarding</h1>
          <p className="text-xs text-stone-500">
            Tell your story — projects, internships, skills, achievements.
          </p>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {messages.length === 0 && (
            <p className="text-sm text-stone-400">
              Start by describing a project you've built.
            </p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap ${
                m.role === "user"
                  ? "ml-auto bg-indigo-600 text-white"
                  : m.role === "pending"
                    ? "bg-stone-100 italic text-stone-400"
                    : "bg-stone-100"
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
        <div className="border-t border-stone-100 p-3">
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              placeholder="Describe a project, an internship, a skill…"
              className="flex-1 rounded-xl border border-stone-200 px-4 py-2.5 text-sm outline-none focus:border-indigo-400"
              disabled={chat.isPending}
            />
            <button
              onClick={send}
              disabled={chat.isPending || !input.trim()}
              className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      </section>

      <aside className="space-y-4">
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <h2 className="text-sm font-semibold">Your vault</h2>
          <p className="mt-1 text-xs text-stone-500">
            What your copilot knows about you.
          </p>
          <div className="mt-3 space-y-2">
            {state.data?.vault_items.length === 0 && (
              <p className="text-xs text-stone-400">Empty so far.</p>
            )}
            {state.data?.vault_items.map((item: VaultItem) => (
              <div key={item.id} className="rounded-xl border border-stone-100 p-2.5">
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
                    CATEGORY_STYLES[item.category] ?? CATEGORY_STYLES.other
                  }`}
                >
                  {item.category}
                </span>
                <p className="mt-1 text-sm">{item.title}</p>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <h2 className="text-sm font-semibold">Resume</h2>
          <p className="mt-1 text-xs text-stone-500">PDF up to 10 MB.</p>
          <label className="mt-3 block cursor-pointer rounded-xl border border-dashed border-stone-300 px-4 py-4 text-center text-sm text-stone-500 hover:border-indigo-400 hover:text-indigo-600">
            {upload.isPending
              ? "Extracting your experience…"
              : "Upload resume PDF"}
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              disabled={upload.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
              }}
            />
          </label>
          {upload.data && (
            <p className="mt-2 text-xs text-emerald-600">
              Added {upload.data.items_created.length} vault items from your resume.
            </p>
          )}
          {upload.error instanceof Error && (
            <p className="mt-2 text-xs text-red-600">{upload.error.message}</p>
          )}
        </div>
      </aside>
    </div>
  );
}
