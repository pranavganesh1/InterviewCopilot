import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import LeaveInterviewModal from "./LeaveInterviewModal";
import {
  abortLeaveGuard,
  bindLeaveOpener,
  finishLeaveGuard,
  getLeaveGuard,
  subscribeLeaveGuard,
  type LeaveIntent,
} from "../lib/leaveGuard";

export default function LeaveGuardProvider({ children }: { children: ReactNode }) {
  const guard = useSyncExternalStore(subscribeLeaveGuard, getLeaveGuard, getLeaveGuard);
  const navigate = useNavigate();
  const [pending, setPending] = useState<LeaveIntent | null>(null);
  const [confirmingFinish, setConfirmingFinish] = useState(false);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKind, setRetryKind] = useState<"finish" | "discard" | null>(null);
  const bypass = useRef(false);
  const here = useRef(window.location.href);

  useEffect(() => {
    bindLeaveOpener((intent) => {
      setConfirmingFinish(false);
      setConfirmingDiscard(false);
      setError(null);
      setRetryKind(null);
      setPending(intent);
    });
    return () => bindLeaveOpener(null);
  }, []);

  useEffect(() => {
    if (!guard.active) return;
    here.current = window.location.href;
    const marked = { ...(window.history.state ?? {}), leaveGuard: true };
    window.history.pushState(marked, "", here.current);

    const onPop = () => {
      if (bypass.current) {
        bypass.current = false;
        return;
      }
      window.history.pushState(
        { ...(window.history.state ?? {}), leaveGuard: true },
        "",
        here.current,
      );
      setConfirmingFinish(false);
      setConfirmingDiscard(false);
      setError(null);
      setRetryKind(null);
      setPending({ kind: "history", focus: null });
    };

    window.addEventListener("popstate", onPop, true);
    return () => window.removeEventListener("popstate", onPop, true);
  }, [guard.active]);

  useEffect(() => {
    if (!guard.active || !guard.dirty) return;
    const onBefore = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBefore);
    return () => window.removeEventListener("beforeunload", onBefore);
  }, [guard.active, guard.dirty]);

  function stay() {
    if (busy) return;
    const focus = pending?.focus ?? null;
    setPending(null);
    setConfirmingFinish(false);
    setConfirmingDiscard(false);
    setError(null);
    setRetryKind(null);
    if (focus?.isConnected) focus.focus();
  }

  function proceed() {
    if (!pending || busy) return;
    const intent = pending;
    setPending(null);
    setConfirmingFinish(false);
    setConfirmingDiscard(false);
    setRetryKind(null);
    if (intent.kind === "history") {
      bypass.current = true;
      window.history.go(-2);
      return;
    }
    if (intent.kind === "href") {
      const replace = Boolean(window.history.state?.leaveGuard);
      navigate(intent.href, { replace });
      return;
    }
    void intent.run();
  }

  async function runFinish() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setRetryKind("finish");
    try {
      await finishLeaveGuard();
      setPending(null);
      setConfirmingFinish(false);
      setConfirmingDiscard(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish the interview.");
    } finally {
      setBusy(false);
    }
  }

  async function runDiscard() {
    if (busy) return;
    setBusy(true);
    setError(null);
    setRetryKind("discard");
    try {
      await abortLeaveGuard();
      const intent = pending;
      setPending(null);
      setConfirmingFinish(false);
      setConfirmingDiscard(false);
      setRetryKind(null);
      if (!intent) return;
      if (intent.kind === "history") {
        bypass.current = true;
        window.history.go(-2);
        return;
      }
      if (intent.kind === "href") {
        const replace = Boolean(window.history.state?.leaveGuard);
        navigate(intent.href, { replace });
        return;
      }
      void intent.run();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not discard the interview. It was not aborted.",
      );
    } finally {
      setBusy(false);
    }
  }

  function askFinish() {
    if (busy) return;
    setConfirmingDiscard(false);
    if (!confirmingFinish) {
      setConfirmingFinish(true);
      return;
    }
    void runFinish();
  }

  function askDiscard() {
    if (busy) return;
    setConfirmingFinish(false);
    if (!confirmingDiscard) {
      setConfirmingDiscard(true);
      return;
    }
    void runDiscard();
  }

  return (
    <>
      {children}
      {pending && (
        <LeaveInterviewModal
          timed={guard.timed}
          confirmingFinish={confirmingFinish}
          confirmingDiscard={confirmingDiscard}
          busy={busy}
          error={error}
          onStay={stay}
          onLeave={proceed}
          onFinish={askFinish}
          onDiscard={askDiscard}
          onRetry={() => {
            if (retryKind === "discard") void runDiscard();
            else void runFinish();
          }}
        />
      )}
    </>
  );
}
