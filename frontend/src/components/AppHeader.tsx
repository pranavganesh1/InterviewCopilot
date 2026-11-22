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

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `relative px-3 py-2 text-sm font-semibold transition sm:px-4 ${
      isActive
        ? "text-accent-strong after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:rounded-full after:bg-accent"
        : "text-ink-soft hover:text-ink"
    }`;

  return (
    <header className="sticky top-0 z-30 overflow-x-clip border-b border-line bg-surface/95 backdrop-blur">
      <div className="flex w-full min-w-0 items-center gap-2 px-3 py-2.5 sm:gap-4 sm:px-5">
        <nav className="flex min-w-0 items-center gap-0.5 text-sm sm:gap-1" aria-label="Primary">
          <NavLink
            to="/"
            end
            onClick={(event) => {
              if (requestLeave({ kind: "href", href: "/", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className={tabClass}
          >
            InterviewCopilot
          </NavLink>
          <a
            href="/#tracks"
            onClick={(event) => {
              if (requestLeave({ kind: "href", href: "/#tracks", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className={tabClass({ isActive: false })}
          >
            Tracks
          </a>
          <NavLink
            to="/onboarding"
            onClick={(event) => {
              if (requestLeave({ kind: "href", href: "/onboarding", focus: event.currentTarget })) {
                event.preventDefault();
              }
            }}
            className={tabClass}
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
              className={tabClass}
            >
              Admin
            </NavLink>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
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
                className="absolute right-0 mt-2 w-56 overflow-hidden rounded-xl border border-line bg-surface py-1.5 shadow-card"
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
                  My Profile
                </Link>
                <Link
                  role="menuitem"
                  to="/readiness"
                  onClick={(event) => {
                    if (requestLeave({ kind: "href", href: "/readiness", focus: event.currentTarget })) {
                      event.preventDefault();
                      return;
                    }
                    setMenuPath(null);
                  }}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-page"
                  data-testid="nav-readiness"
                >
                  Resume readiness
                </Link>
                <Link
                  role="menuitem"
                  to="/profile#history"
                  onClick={(event) => {
                    if (
                      requestLeave({
                        kind: "href",
                        href: "/profile#history",
                        focus: event.currentTarget,
                      })
                    ) {
                      event.preventDefault();
                      return;
                    }
                    setMenuPath(null);
                  }}
                  className="flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-ink hover:bg-page"
                >
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
