import { useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { requestLeave } from "../lib/leaveGuard";
import UserAvatar from "./UserAvatar";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${
    isActive
      ? "bg-gradient-to-r from-accent to-accent-strong text-white shadow-sm"
      : "text-ink-soft hover:bg-accent-soft/70 hover:text-ink"
  }`;

function NavIcon({
  children,
  active,
}: {
  children: ReactNode;
  active?: boolean;
}) {
  return (
    <span
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
        active ? "bg-white/15 text-white" : "bg-accent-soft text-accent"
      }`}
      aria-hidden="true"
    >
      {children}
    </span>
  );
}

export default function DashboardSidebar() {
  const { user, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (!user) return null;

  const subtitle =
    user.professional_title?.trim() ||
    user.education?.trim() ||
    user.email;

  const nav = (
    <>
      <div className="flex items-center gap-2.5 px-1">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-strong text-white shadow-sm">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
            <path d="M12 2a7 7 0 0 0-7 7v1.2A4.2 4.2 0 0 0 3 14.2V16a3 3 0 0 0 3 3h1.1A3.9 3.9 0 0 0 12 22a3.9 3.9 0 0 0 4.9-3H18a3 3 0 0 0 3-3v-1.8a4.2 4.2 0 0 0-2-3.8V9a7 7 0 0 0-7-7Zm-3.2 9.5a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4Zm6.4 0a1.2 1.2 0 1 1 0-2.4 1.2 1.2 0 0 1 0 2.4Z" />
          </svg>
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-bold tracking-tight text-ink">
            Interview<span className="text-accent">Copilot</span>
          </p>
          <p className="truncate text-[11px] text-ink-faint">Practice with AI</p>
        </div>
      </div>

      <nav className="mt-6 flex flex-1 flex-col gap-1" aria-label="Main">
        <NavLink
          to="/"
          end
          className={linkClass}
          onClick={(event) => {
            setMobileOpen(false);
            if (requestLeave({ kind: "href", href: "/", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
        >
          {({ isActive }) => (
            <>
              <NavIcon active={isActive}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                  <path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6V11h-6v9Zm0-16v5h6V4h-6Z" />
                </svg>
              </NavIcon>
              Dashboard
            </>
          )}
        </NavLink>
        <a
          href="/#tracks"
          className={linkClass({ isActive: false })}
          onClick={(event) => {
            setMobileOpen(false);
            if (requestLeave({ kind: "href", href: "/#tracks", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
        >
          <NavIcon>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
              <path d="M8 5v14l11-7L8 5Z" />
            </svg>
          </NavIcon>
          Start Interview
        </a>
        <NavLink
          to="/onboarding"
          className={linkClass}
          onClick={(event) => {
            setMobileOpen(false);
            if (requestLeave({ kind: "href", href: "/onboarding", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
        >
          {({ isActive }) => (
            <>
              <NavIcon active={isActive}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                  <path d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 3h7v4h-7v-4Z" />
                </svg>
              </NavIcon>
              Profile Vault
            </>
          )}
        </NavLink>
        <NavLink
          to="/profile#history"
          className={linkClass}
          onClick={(event) => {
            setMobileOpen(false);
            if (
              requestLeave({
                kind: "href",
                href: "/profile#history",
                focus: event.currentTarget,
              })
            ) {
              event.preventDefault();
            }
          }}
        >
          {({ isActive }) => (
            <>
              <NavIcon active={isActive}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                  <path d="M12 8v5l3 2 .8-1.2-2.3-1.5V8H12Zm0-6a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8Z" />
                </svg>
              </NavIcon>
              Interview History
            </>
          )}
        </NavLink>
        <NavLink
          to="/readiness"
          className={linkClass}
          onClick={(event) => {
            setMobileOpen(false);
            if (requestLeave({ kind: "href", href: "/readiness", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
        >
          {({ isActive }) => (
            <>
              <NavIcon active={isActive}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                  <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Zm0 2.2 6 2.2v4.7c0 3.9-2.5 7.4-6 8.9-3.5-1.5-6-5-6-8.9V6.4l6-2.2Z" />
                </svg>
              </NavIcon>
              <span className="flex min-w-0 flex-1 items-center justify-between gap-2">
                Career Readiness
                <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent-strong">
                  New
                </span>
              </span>
            </>
          )}
        </NavLink>
        <NavLink
          to="/profile"
          className={linkClass}
          onClick={(event) => {
            setMobileOpen(false);
            if (requestLeave({ kind: "href", href: "/profile", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
        >
          {({ isActive }) => (
            <>
              <NavIcon active={isActive}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                  <path d="M19.1 12.9a7.5 7.5 0 0 0 .1-1.8l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-1.6-.9L14.8 3h-4l-.4 2.7a7.6 7.6 0 0 0-1.6.9l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0-.1 1.8l-2 1.6 2 3.4 2.4-1c.5.4 1 .7 1.6.9L10.8 21h4l.4-2.7c.6-.2 1.1-.5 1.6-.9l2.4 1 2-3.4-2-1.6ZM12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5Z" />
                </svg>
              </NavIcon>
              Settings
            </>
          )}
        </NavLink>
        <a
          href="mailto:support@interviewcopilot.local"
          className={linkClass({ isActive: false })}
          onClick={() => setMobileOpen(false)}
        >
          <NavIcon>
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
              <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Zm1 15h-2v-2h2v2Zm0-4h-2V7h2v6Z" />
            </svg>
          </NavIcon>
          Help & Support
        </a>
      </nav>

      <div className="mt-4 space-y-3">
        <div className="rounded-2xl bg-gradient-to-br from-accent-soft via-white to-accent-soft/40 p-3 ring-1 ring-accent/15">
          <div className="flex items-start gap-2">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-white">
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden="true">
                <path d="M13 3 4 14h7l-1 7 10-12h-7l0-6Z" />
              </svg>
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold text-ink">Your Interview Journey</p>
              <p className="mt-0.5 text-[11px] text-ink-soft">Powered by AI</p>
            </div>
          </div>
          <Link
            to="/#tracks"
            onClick={(event) => {
              setMobileOpen(false);
              if (requestLeave({ kind: "href", href: "/#tracks", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className="mt-3 inline-flex w-full items-center justify-center rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong"
          >
            Start Interview →
          </Link>
        </div>

        <div className="flex items-center gap-2.5 rounded-xl border border-line bg-white p-2.5">
          <UserAvatar
            name={user.name}
            email={user.email}
            pictureUrl={user.picture_url}
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-ink">
              {user.name || "Your profile"}
            </p>
            <p className="truncate text-[11px] text-ink-soft">{subtitle}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={async (event) => {
            const run = async () => {
              setMobileOpen(false);
              await signOut();
            };
            if (requestLeave({ kind: "action", run, focus: event.currentTarget })) return;
            await run();
          }}
          className="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50"
        >
          Logout
        </button>
      </div>
    </>
  );

  return (
    <>
      <button
        type="button"
        className="fixed bottom-4 left-4 z-50 grid h-11 w-11 place-items-center rounded-full bg-accent text-white shadow-lg lg:hidden"
        aria-label={mobileOpen ? "Close menu" : "Open menu"}
        onClick={() => setMobileOpen((v) => !v)}
      >
        {mobileOpen ? (
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        )}
      </button>

      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-ink/30 lg:hidden"
          aria-label="Close menu overlay"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[17.5rem] flex-col border-r border-line bg-surface px-3 py-4 transition-transform lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {nav}
      </aside>
    </>
  );
}
