import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  api,
  type ResumeSyncResult,
  type VaultDuplicatePair,
} from "../lib/api";

type Props = {
  onRequestUpload?: () => void;
};

function syncSummary(data: ResumeSyncResult): string {
  const c = data.counts;
  if (!c) {
    const created = data.items_created?.length ?? 0;
    return created
      ? `Added ${created} vault item${created === 1 ? "" : "s"}.`
      : "No new vault items.";
  }
  const parts = [
    `${c.created} created`,
    `${c.skipped} skipped`,
    `${c.enrichment_candidates} enrichment`,
    `${c.uncertain_matches} need review`,
  ];
  if (c.failed) parts.push(`${c.failed} failed`);
  return parts.join(" · ");
}

export default function ResumeVaultManager({ onRequestUpload }: Props) {
  const qc = useQueryClient();
  const [panel, setPanel] = useState<"idle" | "duplicates" | "reset">("idle");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const duplicates = useQuery({
    queryKey: ["vault-duplicates"],
    enabled: panel === "duplicates",
    queryFn: () =>
      api<{ pairs: VaultDuplicatePair[]; count: number; note?: string }>(
        "/vault/duplicates",
      ),
  });

  const resetPreview = useQuery({
    queryKey: ["vault-resume-reset-preview"],
    enabled: panel === "reset",
    queryFn: () =>
      api<{
        count: number;
        items: { id: string; category: string; title: string; source: string }[];
        scope: string;
        confirm_phrase: string;
      }>("/vault/resume-data/reset-preview"),
  });

  const reprocess = useMutation({
    mutationFn: () => api<ResumeSyncResult>("/vault/resume/reprocess", { method: "POST" }),
    onSuccess: (data) => {
      setError(null);
      setMessage(`Reprocess complete: ${syncSummary(data)}`);
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      qc.invalidateQueries({ queryKey: ["vault-items"] });
      qc.invalidateQueries({ queryKey: ["profile-review"] });
      qc.invalidateQueries({ queryKey: ["vault-duplicates"] });
      qc.invalidateQueries({ queryKey: ["career-intelligence"] });
    },
    onError: (err) => {
      setMessage(null);
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not reprocess resume.",
      );
    },
  });

  const confirmProfile = useMutation({
    mutationFn: () =>
      api("/onboarding/profile/confirm", {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      }),
    onSuccess: (data) => {
      setError(null);
      setMessage("Thanks — profile confirmed. Tell Chanakya what role you're aiming for next.");
      qc.setQueryData(["onboarding-state"], data);
      void qc.invalidateQueries({ queryKey: ["onboarding-state"] });
    },
    onError: (err) => {
      setMessage(null);
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Could not confirm profile.",
      );
    },
  });

  const resolve = useMutation({
    mutationFn: (body: { keep_id: string; discard_id: string }) =>
      api("/vault/duplicates/resolve", {
        method: "POST",
        body: JSON.stringify({ ...body, merge_details: true }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vault-duplicates"] });
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      qc.invalidateQueries({ queryKey: ["vault-items"] });
      qc.invalidateQueries({ queryKey: ["profile-review"] });
    },
  });

  const reset = useMutation({
    mutationFn: () =>
      api<{ status?: string; removed_count?: number }>("/vault/resume-data/reset", {
        method: "POST",
        body: JSON.stringify({
          confirm: true,
          confirm_phrase: "RESET RESUME DATA",
        }),
      }),
    onSuccess: (data) => {
      setPanel("idle");
      setConfirmPhrase("");
      setMessage(
        `Removed ${data.removed_count ?? 0} resume-derived vault item${
          (data.removed_count ?? 0) === 1 ? "" : "s"
        }. Manual and chat items were kept.`,
      );
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      qc.invalidateQueries({ queryKey: ["vault-items"] });
      qc.invalidateQueries({ queryKey: ["profile-review"] });
      qc.invalidateQueries({ queryKey: ["vault-duplicates"] });
      qc.invalidateQueries({ queryKey: ["vault-resume-reset-preview"] });
      qc.invalidateQueries({ queryKey: ["career-intelligence"] });
    },
    onError: (err) => {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Reset failed.",
      );
    },
  });

  const pairs = duplicates.data?.pairs ?? [];
  const previewItems = resetPreview.data?.items ?? [];
  const canConfirmReset = useMemo(
    () => confirmPhrase.trim().toUpperCase() === "RESET RESUME DATA",
    [confirmPhrase],
  );

  return (
    <section
      className="space-y-3 rounded-2xl border border-line bg-white p-4"
      data-testid="resume-vault-manager"
    >
      <div>
        <h3 className="text-sm font-semibold text-ink">Resume & profile management</h3>
        <p className="mt-1 text-xs text-ink-soft">
          Uploads sync against your Profile Vault. Duplicates are skipped; uncertain matches
          wait for your review.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="resume-confirm-profile"
          disabled={confirmProfile.isPending}
          onClick={() => confirmProfile.mutate()}
          className="rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          {confirmProfile.isPending ? "Confirming…" : "Confirm Profile"}
        </button>
        <button
          type="button"
          data-testid="resume-reprocess"
          disabled={reprocess.isPending}
          onClick={() => reprocess.mutate()}
          className="rounded-xl border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white disabled:opacity-50"
        >
          {reprocess.isPending ? "Reprocessing…" : "Reprocess Resume"}
        </button>
        <button
          type="button"
          data-testid="resume-review-duplicates"
          onClick={() => {
            setPanel("duplicates");
            setError(null);
          }}
          className="rounded-xl border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white"
        >
          Review Duplicates
        </button>
        <button
          type="button"
          data-testid="resume-reset-open"
          onClick={() => {
            setPanel("reset");
            setConfirmPhrase("");
            setError(null);
          }}
          className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-800 hover:bg-rose-100"
        >
          Reset Resume Data
        </button>
        {onRequestUpload && (
          <button
            type="button"
            onClick={onRequestUpload}
            className="rounded-xl border border-line bg-page px-3 py-2 text-xs font-semibold text-ink hover:bg-white"
          >
            Upload new PDF
          </button>
        )}
      </div>

      {message && (
        <p className="text-xs text-emerald-700" data-testid="resume-manager-message">
          {message}
        </p>
      )}
      {error && (
        <p className="text-xs text-rose-700" role="alert" data-testid="resume-manager-error">
          {error}
        </p>
      )}

      {panel === "duplicates" && (
        <div
          className="space-y-3 rounded-xl border border-line bg-page/50 p-3"
          data-testid="resume-duplicates-panel"
        >
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
              Suspected duplicates
            </h4>
            <button
              type="button"
              className="text-xs font-semibold text-accent-strong hover:underline"
              onClick={() => setPanel("idle")}
            >
              Close
            </button>
          </div>
          {duplicates.isLoading && (
            <p className="text-xs text-ink-faint">Loading…</p>
          )}
          {duplicates.isError && (
            <p className="text-xs text-rose-700">Could not load duplicates.</p>
          )}
          {!duplicates.isLoading && pairs.length === 0 && (
            <p className="text-xs text-ink-faint">No suspected duplicates right now.</p>
          )}
          {pairs.map((pair) => {
            const keep = pair.suggested_keep === "a" ? pair.a : pair.b;
            const drop = pair.suggested_keep === "a" ? pair.b : pair.a;
            return (
              <article
                key={`${pair.a.id}-${pair.b.id}`}
                className="rounded-xl border border-line bg-white p-3"
                data-testid="resume-duplicate-pair"
              >
                <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                  {pair.category} · {pair.match}
                </p>
                <p className="mt-1 text-xs text-ink-soft">{pair.reason}</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg bg-page p-2">
                    <p className="text-xs font-semibold text-ink">{pair.a.title}</p>
                    <p className="text-[11px] text-ink-faint">
                      source: {pair.a.source || "—"} · details: {pair.a.detail_count ?? 0}
                    </p>
                  </div>
                  <div className="rounded-lg bg-page p-2">
                    <p className="text-xs font-semibold text-ink">{pair.b.title}</p>
                    <p className="text-[11px] text-ink-faint">
                      source: {pair.b.source || "—"} · details: {pair.b.detail_count ?? 0}
                    </p>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({ keep_id: keep.id, discard_id: drop.id })
                    }
                    className="rounded-lg bg-accent px-2.5 py-1.5 text-[11px] font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
                  >
                    Keep fuller record & merge
                  </button>
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({ keep_id: pair.a.id, discard_id: pair.b.id })
                    }
                    className="rounded-lg border border-line px-2.5 py-1.5 text-[11px] font-semibold text-ink hover:bg-page disabled:opacity-50"
                  >
                    Keep left, remove right
                  </button>
                  <button
                    type="button"
                    disabled={resolve.isPending}
                    onClick={() =>
                      resolve.mutate({ keep_id: pair.b.id, discard_id: pair.a.id })
                    }
                    className="rounded-lg border border-line px-2.5 py-1.5 text-[11px] font-semibold text-ink hover:bg-page disabled:opacity-50"
                  >
                    Keep right, remove left
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {panel === "reset" && (
        <div
          className="space-y-3 rounded-xl border border-rose-200 bg-rose-50/60 p-3"
          data-testid="resume-reset-panel"
          role="dialog"
          aria-labelledby="resume-reset-title"
        >
          <div className="flex items-center justify-between gap-2">
            <h4 id="resume-reset-title" className="text-sm font-semibold text-rose-900">
              Reset resume-derived data
            </h4>
            <button
              type="button"
              className="text-xs font-semibold text-rose-800 hover:underline"
              onClick={() => setPanel("idle")}
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-rose-900/90">
            {resetPreview.data?.scope ||
              "Only source=resume Profile Vault rows for your account will be removed."}
          </p>
          {resetPreview.isLoading && (
            <p className="text-xs text-ink-faint">Loading preview…</p>
          )}
          <ul className="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-rose-200 bg-white p-2 text-xs text-ink">
            {previewItems.length === 0 ? (
              <li className="text-ink-faint">No resume-derived items to remove.</li>
            ) : (
              previewItems.map((item) => (
                <li key={item.id}>
                  <span className="font-medium">{item.category}</span>: {item.title}
                </li>
              ))
            )}
          </ul>
          <label className="block text-xs text-rose-900">
            Type <span className="font-semibold">RESET RESUME DATA</span> to confirm
            <input
              value={confirmPhrase}
              onChange={(e) => setConfirmPhrase(e.target.value)}
              className="mt-1 w-full rounded-lg border border-rose-200 px-2 py-1.5 text-sm text-ink"
              data-testid="resume-reset-confirm-input"
              autoComplete="off"
            />
          </label>
          <button
            type="button"
            data-testid="resume-reset-confirm"
            disabled={!canConfirmReset || reset.isPending || previewItems.length === 0}
            onClick={() => reset.mutate()}
            className="rounded-xl bg-rose-700 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-800 disabled:opacity-50"
          >
            {reset.isPending ? "Removing…" : `Remove ${previewItems.length} resume items`}
          </button>
        </div>
      )}
    </section>
  );
}

export { syncSummary };
