import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { requestLeave } from "../lib/leaveGuard";
import UserAvatar from "./UserAvatar";

export default function AppHeader() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [menuPath, setMenuPath] = useState<string | null>(null);
  const open = menuPath === pathname;
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuPath(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuPath(null);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  return (
    <header className="sticky top-0 z-40 overflow-x-clip border-b border-line bg-surface">
      <div className="mx-auto flex w-full min-w-0 max-w-6xl items-center gap-2 px-3 py-3 sm:gap-6 sm:px-4">
        <Link
          to="/"
          onClick={(event) => {
            if (requestLeave({ kind: "href", href: "/", focus: event.currentTarget })) {
              event.preventDefault();
            }
          }}
          className="shrink-0 text-sm font-bold tracking-tight text-ink sm:text-base"
        >
          Interview<span className="text-accent">Copilot</span>
        </Link>

        <nav className="flex min-w-0 gap-0.5 text-sm sm:gap-1">
          <NavLink
            to="/"
            end
            onClick={(event) => {
              if (requestLeave({ kind: "href", href: "/", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className={({ isActive }) =>
              `rounded-full px-2.5 py-1.5 font-medium transition sm:px-3.5 ${
                isActive
                  ? "bg-accent-soft text-accent-strong"
                  : "text-ink-soft hover:bg-page"
              }`
            }
          >
            Tracks
          </NavLink>
          <NavLink
            to="/onboarding"
            onClick={(event) => {
              if (requestLeave({ kind: "href", href: "/onboarding", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className={({ isActive }) =>
              `rounded-full px-2.5 py-1.5 font-medium transition sm:px-3.5 ${
                isActive
                  ? "bg-accent-soft text-accent-strong"
                  : "text-ink-soft hover:bg-page"
              }`
            }
          >
            Onboarding
          </NavLink>
          {user.is_admin && (
            <NavLink
              to="/admin"
              onClick={(event) => {
                if (requestLeave({ kind: "href", href: "/admin", focus: event.currentTarget })) {
                  event.preventDefault();
                }
              }}
              className={({ isActive }) =>
                `rounded-full px-2.5 py-1.5 font-medium transition sm:px-3.5 ${
                  isActive ? "bg-accent-soft text-accent-strong" : "text-ink-soft hover:bg-page"
                }`
              }
            >
              Admin
            </NavLink>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <span className="hidden max-w-[14rem] truncate text-sm text-ink-soft md:inline">
            {user.email}
          </span>

          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-full text-ink-soft hover:bg-page"
            aria-label="Notifications"
            title="Notifications"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0v1a3 3 0 1 1-6 0v-1m6 0H9"
              />
            </svg>
          </button>

          <div className="relative" ref={menuRef}>
            <button
              type="button"
              data-testid="nav-profile"
              aria-expanded={open}
              aria-haspopup="menu"
              onClick={() => setMenuPath(open ? null : pathname)}
              className="flex items-center gap-1 rounded-full p-0.5 ring-2 ring-transparent transition hover:ring-line focus-visible:outline-none focus-visible:ring-accent"
            >
              <UserAvatar
                name={user.name}
                email={user.email}
                pictureUrl={user.picture_url}
              />
              <svg
                viewBox="0 0 20 20"
                className="hidden h-4 w-4 text-ink-faint sm:block"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.25a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08Z"
                  clipRule="evenodd"
                />
              </svg>
            </button>

            {open && (
              <div
                role="menu"
                className="absolute right-0 mt-2 w-56 overflow-hidden rounded-lg border border-line bg-surface py-1.5 shadow-card"
              >
                <Link
                  role="menuitem"
                  to="/profile"
                  onClick={(event) => {
                    if (requestLeave({ kind: "href", href: "/profile", focus: event.currentTarget })) {
                      event.preventDefault();
                      return;
                    }
                    setMenuPath(null);
                  }}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-page"
                >
                  <span className="grid h-7 w-7 place-items-center rounded-md bg-page text-ink-soft">
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                      <path d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-4 0-7 2-7 4v1h14v-1c0-2-3-4-7-4Z" />
                    </svg>
                  </span>
                  My Profile
                </Link>
                <Link
                  role="menuitem"
                  to="/profile#history"
                  onClick={(event) => {
                    if (requestLeave({ kind: "href", href: "/profile#history", focus: event.currentTarget })) {
                      event.preventDefault();
                      return;
                    }
                    setMenuPath(null);
                  }}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-page"
                >
                  <span className="grid h-7 w-7 place-items-center rounded-md bg-page text-ink-soft">
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                      <path d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z" />
                    </svg>
                  </span>
                  Assessment History
                </Link>
                <Link
                  role="menuitem"
                  to="/profile"
                  onClick={(event) => {
                    if (requestLeave({ kind: "href", href: "/profile", focus: event.currentTarget })) {
                      event.preventDefault();
                      return;
                    }
                    setMenuPath(null);
                  }}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-page"
                >
                  <span className="grid h-7 w-7 place-items-center rounded-md bg-page text-ink-soft">
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor">
                      <path d="M19.1 12.9a7.5 7.5 0 0 0 .1-1.8l2-1.6-2-3.4-2.4 1a7.6 7.6 0 0 0-1.6-.9L14.8 3h-4l-.4 2.7a7.6 7.6 0 0 0-1.6.9l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0-.1 1.8l-2 1.6 2 3.4 2.4-1c.5.4 1 .7 1.6.9L10.8 21h4l.4-2.7c.6-.2 1.1-.5 1.6-.9l2.4 1 2-3.4-2-1.6ZM12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5Z" />
                    </svg>
                  </span>
                  Settings
                </Link>
                <div className="my-1 border-t border-line" />
                <button
                  role="menuitem"
                  type="button"
                  onClick={async (event) => {
                    const run = async () => {
                      setMenuPath(null);
                      await signOut();
                      navigate("/");
                    };
                    if (requestLeave({ kind: "action", run, focus: event.currentTarget })) return;
                    await run();
                  }}
                  className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-sm text-rose-600 hover:bg-rose-50"
                >
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-rose-50 text-rose-600">
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" d="M15 12H3m0 0 3.5-3.5M3 12l3.5 3.5M12 4h5a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3h-5" />
                    </svg>
                  </span>
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
