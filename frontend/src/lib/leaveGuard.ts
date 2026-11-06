export type LeaveIntent =
  | { kind: "href"; href: string; focus: HTMLElement | null }
  | { kind: "history"; focus: null }
  | { kind: "action"; run: () => void | Promise<void>; focus: HTMLElement | null };

export type LeaveGuard = {
  active: boolean;
  dirty: boolean;
  timed: boolean;
};

const IDLE: LeaveGuard = { active: false, dirty: false, timed: false };

let snapshot: LeaveGuard = IDLE;
let finishImpl: () => Promise<void> = async () => {};
const listeners = new Set<() => void>();
let opener: ((intent: LeaveIntent) => void) | null = null;

function emit() {
  listeners.forEach((listener) => listener());
}

export function getLeaveGuard(): LeaveGuard {
  return snapshot;
}

export function subscribeLeaveGuard(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setLeaveGuard(
  next: (LeaveGuard & { finish: () => Promise<void> }) | null,
) {
  finishImpl = next?.finish ?? (async () => {});
  const upcoming: LeaveGuard = next
    ? { active: next.active, dirty: next.dirty, timed: next.timed }
    : IDLE;
  if (
    snapshot.active === upcoming.active &&
    snapshot.dirty === upcoming.dirty &&
    snapshot.timed === upcoming.timed
  ) {
    return;
  }
  snapshot = upcoming.active ? upcoming : IDLE;
  emit();
}

export function finishLeaveGuard() {
  return finishImpl();
}

export function bindLeaveOpener(open: ((intent: LeaveIntent) => void) | null) {
  opener = open;
}

export function requestLeave(intent: LeaveIntent): boolean {
  if (!snapshot.active || !opener) return false;
  opener(intent);
  return true;
}
