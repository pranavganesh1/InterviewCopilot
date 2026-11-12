import { useEffect, useId, useRef } from "react";

const EMOJIS = [
  "😀",
  "😊",
  "🙂",
  "😉",
  "🤩",
  "😎",
  "🤔",
  "😅",
  "🙌",
  "👍",
  "👏",
  "🔥",
  "✨",
  "💡",
  "🎯",
  "🚀",
  "💪",
  "📚",
  "✅",
  "❤️",
  "🎉",
  "🙏",
  "💬",
  "🌟",
] as const;

type Props = {
  open: boolean;
  onClose: () => void;
  onPick: (emoji: string) => void;
};

export default function EmojiPicker({ open, onClose, onPick }: Props) {
  const labelId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    const onDoc = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    panelRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelId}
      data-testid="emoji-picker"
      className="absolute bottom-full left-0 z-20 mb-2 w-[13.5rem] rounded-xl border border-line bg-white p-2 shadow-lg"
    >
      <p id={labelId} className="sr-only">
        Choose an emoji
      </p>
      <div className="grid grid-cols-6 gap-0.5" role="listbox" aria-label="Emojis">
        {EMOJIS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            role="option"
            aria-label={`Insert ${emoji}`}
            className="rounded-md p-1.5 text-base leading-none hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
            onClick={() => {
              onPick(emoji);
              onClose();
            }}
          >
            {emoji}
          </button>
        ))}
      </div>
    </div>
  );
}
