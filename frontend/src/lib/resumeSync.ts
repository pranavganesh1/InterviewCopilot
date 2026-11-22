import type { ResumeSyncResult } from "./api";

export function syncSummary(data: ResumeSyncResult): string {
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
