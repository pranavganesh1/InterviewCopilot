type Props = {
  name?: string | null;
  email?: string | null;
  pictureUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
};

function initials(name?: string | null, email?: string | null) {
  const base = (name || email || "?").trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

const SIZE = {
  sm: "h-9 w-9 text-xs",
  md: "h-11 w-11 text-sm",
  lg: "h-16 w-16 text-xl",
};

/** Initials-first avatar; optional photo with graceful onError fallback. */
export default function UserAvatar({
  name,
  email,
  pictureUrl,
  size = "sm",
  className = "",
}: Props) {
  const label = initials(name, email);
  const dim = SIZE[size];

  if (pictureUrl) {
    return (
      <span className={`relative inline-grid shrink-0 ${dim} ${className}`}>
        <span
          className={`absolute inset-0 grid place-items-center rounded-full bg-accent font-semibold text-white ${dim}`}
          aria-hidden
        >
          {label}
        </span>
        <img
          src={pictureUrl}
          alt=""
          className={`relative z-[1] rounded-full object-cover ${dim}`}
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
      </span>
    );
  }

  return (
    <span
      className={`inline-grid shrink-0 place-items-center rounded-full bg-accent font-semibold text-white ${dim} ${className}`}
      aria-hidden
    >
      {label}
    </span>
  );
}
