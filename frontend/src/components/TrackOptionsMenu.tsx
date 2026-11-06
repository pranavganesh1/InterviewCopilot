import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";

type Props = {
  trackId: string;
  open: boolean;
  latestReportTo: string | null;
  showDelete: boolean;
  onToggle: () => void;
  onClose: () => void;
  onDelete: (button: HTMLButtonElement) => void;
};

export default function TrackOptionsMenu({
  trackId,
  open,
  latestReportTo,
  showDelete,
  onToggle,
  onClose,
  onDelete,
}: Props) {
  const menuId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [dropUp, setDropUp] = useState(false);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const first = menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]');
    first?.focus();

    function onPointer(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) onCloseRef.current();
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        buttonRef.current?.focus();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const items = [
        ...(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []),
      ];
      if (items.length === 0) return;
      event.preventDefault();
      const current = items.indexOf(document.activeElement as HTMLElement);
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const start = current < 0 ? (delta === 1 ? -1 : 0) : current;
      items[(start + delta + items.length) % items.length].focus();
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function toggle() {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) setDropUp(rect.bottom > window.innerHeight - 180);
    onToggle();
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Track options"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={toggle}
        className="grid h-9 w-9 place-items-center rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-700"
      >
        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
          <circle cx="12" cy="5" r="1.5" />
          <circle cx="12" cy="12" r="1.5" />
          <circle cx="12" cy="19" r="1.5" />
        </svg>
      </button>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          data-placement={dropUp ? "up" : "down"}
          className={`absolute right-0 z-30 w-44 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg ${
            dropUp ? "bottom-full mb-1" : "top-full mt-1"
          }`}
        >
          <Link
            role="menuitem"
            to={`/tracks/${trackId}`}
            onClick={onClose}
            className="block px-3 py-2 text-sm text-slate-700 hover:bg-indigo-50 focus:bg-indigo-50 focus:outline-none"
          >
            Open track
          </Link>
          {latestReportTo && (
            <Link
              role="menuitem"
              to={latestReportTo}
              onClick={onClose}
              className="block px-3 py-2 text-sm text-slate-700 hover:bg-indigo-50 focus:bg-indigo-50 focus:outline-none"
            >
              Latest report
            </Link>
          )}
          {showDelete && <div role="separator" className="my-1 border-t border-slate-100" />}
          {showDelete && (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                const button = buttonRef.current;
                onClose();
                if (button) onDelete(button);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50 focus:bg-red-50 focus:outline-none"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M9 7V5h6v2m-7 0 1 12h6l1-12" />
              </svg>
              Delete track
            </button>
          )}
        </div>
      )}
    </div>
  );
}
