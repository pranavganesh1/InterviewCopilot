export const API_BASE = "/api/v1";

/**
 * Backend origin for top-level OAuth navigation only.
 * Must match GOOGLE_REDIRECT_URI's host (localhost:8000) so authlib's session
 * cookie is stored on the same host Google returns to — not the Vite proxy host
 * (127.0.0.1:5173 vs localhost:8000 otherwise causes MismatchingStateError).
 */
export const AUTH_ORIGIN = (
  import.meta.env.VITE_AUTH_ORIGIN as string | undefined
)?.replace(/\/$/, "") || "http://localhost:8000";
