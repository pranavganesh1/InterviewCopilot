import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, type ConversationSummary, type OnboardingState } from "../lib/api";

type Props = {
  conversations?: ConversationSummary[];
  activeId?: string | null;
  disabled?: boolean;
};

function formatActivity(iso?: string | null): string {
  if (!iso) return "No activity";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "No activity";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function ConversationHistory({
  conversations = [],
  activeId,
  disabled,
}: Props) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);

  const sorted = useMemo(
    () =>
      [...conversations].sort((a, b) =>
        String(b.updated_at || "").localeCompare(String(a.updated_at || "")),
      ),
    [conversations],
  );

  const create = useMutation({
    mutationFn: () =>
      api<OnboardingState>("/onboarding/conversations", { method: "POST" }),
    onSuccess: (data) => {
      setError(null);
      setOpen(false);
      qc.setQueryData(["onboarding-state"], data);
      void qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not start a new chat.",
      );
    },
  });

  const activate = useMutation({
    mutationFn: (conversationId: string) =>
      api<OnboardingState>("/onboarding/conversations/activate", {
        method: "POST",
        body: JSON.stringify({ conversation_id: conversationId }),
      }),
    onSuccess: (data) => {
      setError(null);
      setOpen(false);
      qc.setQueryData(["onboarding-state"], data);
      void qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not open that conversation.",
      );
    },
  });

  const remove = useMutation({
    mutationFn: (conversationId: string) =>
      api<OnboardingState & { status?: string; conversation_deleted?: { deleted_id: string } }>(
        `/onboarding/conversations/${encodeURIComponent(conversationId)}`,
        { method: "DELETE" },
      ),
    onSuccess: (data) => {
      setError(null);
      setPendingDelete(null);
      qc.setQueryData(["onboarding-state"], data);
      void qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not delete that conversation.",
      );
    },
  });

  const busy =
    disabled || create.isPending || activate.isPending || remove.isPending;

  return (
    <div className="relative" data-testid="conversation-history">
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          data-testid="conversation-history-toggle"
          disabled={busy}
          onClick={() => setOpen((v) => !v)}
          className="rounded-lg border border-line bg-page px-2.5 py-1.5 text-[11px] font-semibold text-ink hover:bg-white disabled:opacity-50"
        >
          History
        </button>
        <button
          type="button"
          data-testid="conversation-new-chat"
          disabled={busy}
          onClick={() => create.mutate()}
          className="rounded-lg bg-accent px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          {create.isPending ? "Starting…" : "New Chat"}
        </button>
      </div>

      {open && (
        <div
          className="absolute right-0 z-30 mt-2 w-80 rounded-2xl border border-line bg-white p-2 shadow-card"
          data-testid="conversation-history-panel"
          role="dialog"
          aria-label="Conversation history"
        >
          <div className="mb-1.5 flex items-center justify-between px-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
              Conversations
            </p>
            <button
              type="button"
              className="text-[11px] font-semibold text-ink-soft hover:underline"
              onClick={() => {
                setOpen(false);
                setPendingDelete(null);
              }}
            >
              Close
            </button>
          </div>
          {error && (
            <p className="mb-2 rounded-lg bg-red-50 px-2 py-1.5 text-[11px] text-red-700">
              {error}
            </p>
          )}
          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {sorted.length === 0 ? (
              <li className="px-2 py-3 text-center text-[11px] text-ink-faint">
                No conversations yet
              </li>
            ) : (
              sorted.map((c) => {
                const isActive = Boolean(c.active) || c.id === activeId;
                return (
                  <li key={c.id} className="flex items-stretch gap-1">
                    <button
                      type="button"
                      disabled={busy || isActive}
                      data-testid={`conversation-row-${c.id}`}
                      data-active={isActive ? "true" : "false"}
                      onClick={() => {
                        if (!isActive) activate.mutate(c.id);
                      }}
                      className={`min-w-0 flex-1 flex flex-col rounded-xl px-2.5 py-2 text-left transition ${
                        isActive
                          ? "bg-accent-soft ring-1 ring-accent/30"
                          : "hover:bg-page"
                      } disabled:cursor-default`}
                    >
                      <span className="truncate text-xs font-semibold text-ink">
                        {c.title || "Conversation"}
                        {isActive ? " · current" : ""}
                      </span>
                      <span className="mt-0.5 text-[10px] text-ink-faint">
                        {formatActivity(c.updated_at)}
                        {typeof c.message_count === "number"
                          ? ` · ${c.message_count} msg`
                          : ""}
                      </span>
                    </button>
                    <button
                      type="button"
                      data-testid={`conversation-delete-${c.id}`}
                      disabled={busy}
                      title="Delete conversation"
                      aria-label={`Delete ${c.title || "conversation"}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setError(null);
                        setPendingDelete(c);
                      }}
                      className="shrink-0 self-center rounded-lg px-2 py-1.5 text-[11px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
                    >
                      Delete
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}

      {pendingDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
          data-testid="conversation-delete-dialog"
          role="presentation"
          onClick={() => {
            if (!remove.isPending) setPendingDelete(null);
          }}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="conversation-delete-title"
            className="w-full max-w-sm rounded-2xl border border-line bg-white p-4 shadow-card"
            onClick={(e) => e.stopPropagation()}
          >
            <h3
              id="conversation-delete-title"
              className="text-sm font-semibold text-ink"
            >
              Delete this conversation?
            </h3>
            <p className="mt-2 text-xs leading-relaxed text-ink-soft">
              “{pendingDelete.title || "Conversation"}” and its messages will be
              permanently removed from your account. Profile Vault, resumes,
              interviews and other chats are not affected.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                disabled={remove.isPending}
                className="rounded-xl border border-line px-3 py-2 text-xs font-semibold text-ink hover:bg-page disabled:opacity-50"
                onClick={() => setPendingDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                data-testid="conversation-delete-confirm"
                disabled={remove.isPending}
                className="rounded-xl bg-rose-700 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-800 disabled:opacity-50"
                onClick={() => remove.mutate(pendingDelete.id)}
              >
                {remove.isPending ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
