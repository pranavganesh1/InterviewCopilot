/** Shared feedback-report polling rules for InterviewPage / ReportPage. */

export const MAX_REPORT_POLLS = 24;
export const REPORT_POLL_MS = 5000;

export type ReportViewState =
  | "loading"
  | "pending"
  | "generating"
  | "ready"
  | "failed";

/**
 * Decide whether react-query should keep polling the report endpoint.
 * Only 404 (not ready yet) continues; other errors and success stop.
 */
export function nextReportPollInterval(args: {
  hasData: boolean;
  errorStatus?: number;
  pollsSoFar: number;
}): number | false {
  if (args.hasData) return false;
  if (args.errorStatus === 404 && args.pollsSoFar < MAX_REPORT_POLLS) {
    return REPORT_POLL_MS;
  }
  return false;
}

/**
 * Map query + poll progress into a single UI state.
 * pollsSoFar counts 404 responses already seen (before the next interval fires).
 */
export function deriveReportViewState(args: {
  hasData: boolean;
  isLoading: boolean;
  isFetching: boolean;
  errorStatus?: number;
  pollsSoFar: number;
}): ReportViewState {
  if (args.hasData) return "ready";
  if (args.errorStatus === 404) {
    if (args.pollsSoFar >= MAX_REPORT_POLLS) return "failed";
    if (args.pollsSoFar === 0 && !args.isFetching) return "pending";
    return "generating";
  }
  if (args.errorStatus != null) return "failed";
  if (args.isLoading || args.isFetching) return "loading";
  return "pending";
}
