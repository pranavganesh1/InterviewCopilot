import { API_BASE } from "./apiBase";

/** Shared in-flight refresh so concurrent 401s share one POST /auth/refresh. */
let refreshInFlight: Promise<boolean> | null = null;
let authFailureHandler: (() => void) | null = null;

export function setAuthFailureHandler(handler: (() => void) | null): void {
  authFailureHandler = handler;
}

export function notifyAuthFailure(): void {
  authFailureHandler?.();
}

/** Reset module state between tests. */
export function _resetAuthRefreshStateForTests(): void {
  refreshInFlight = null;
  authFailureHandler = null;
}

export function shouldAttemptRefresh(path: string, alreadyRetried: boolean): boolean {
  if (alreadyRetried) return false;
  if (path === "/auth/refresh" || path === "/auth/logout") return false;
  return true;
}

/**
 * POST /auth/refresh once. Concurrent callers await the same promise.
 * Cookie-based — never reads or stores JWT values in JS storage.
 */
export async function refreshAccessToken(
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    try {
      const res = await fetchImpl(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}
