import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type VaultItem } from "../lib/api";

const SECTION_ORDER = [
  "education",
  "skill",
  "project",
  "internship",
  "achievement",
  "other",
] as const;

const SECTION_LABELS: Record<string, string> = {
  education: "Education",
  skill: "Skills",
  project: "Projects",
  internship: "Internships",
  achievement: "Achievements",
  other: "Other",
};

const SKILL_GROUP_ORDER = [
  "Programming Languages",
  "AI/ML",
  "Backend / Architecture",
  "Frontend",
  "Databases",
  "Cloud & DevOps",
  "Core Concepts",
  "Skills",
];

const CATEGORY_STYLES: Record<string, string> = {
  project: "bg-sky-100 text-sky-700",
  internship: "bg-sky-100 text-sky-700",
  skill: "bg-emerald-100 text-emerald-700",
  achievement: "bg-amber-100 text-amber-700",
  education: "bg-stone-100 text-stone-600",
  other: "bg-stone-100 text-stone-600",
};

function skillGroup(item: VaultItem): string {
  const d = item.details || {};
  return (
    d.skill_group ||
    d.category ||
    d.area ||
    d.group ||
    "Skills"
  );
}

function detailLines(item: VaultItem): string[] {
  const d = item.details || {};
  const prefer = [
    "purpose",
    "technologies",
    "architecture",
    "contribution",
    "outcome",
    "features",
    "role",
    "stack",
    "level",
  ];
  const lines: string[] = [];
  for (const key of prefer) {
    const value = d[key];
    if (value) lines.push(`${key}: ${value}`);
  }
  for (const [key, value] of Object.entries(d)) {
    if (prefer.includes(key) || ["skill_group", "category", "area", "group"].includes(key)) {
      continue;
    }
    if (value) lines.push(`${key}: ${value}`);
  }
  return lines.slice(0, 5);
}

export function VaultSidebar({ items }: { items: VaultItem[] }) {
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/vault/items/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onboarding-state"] });
      qc.invalidateQueries({ queryKey: ["vault-items"] });
    },
  });

  const byCategory = SECTION_ORDER.map((category) => ({
    category,
    items: items.filter((i) => i.category === category),
  })).filter((g) => g.items.length > 0);

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-stone-800">Your vault</h2>
        <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600">
          {items.length} items
        </span>
      </div>
      <p className="mt-1 text-xs text-stone-500">
        Extracted profile information — edit in chat or remove items below.
      </p>

      <div className="mt-3 max-h-[28rem] space-y-4 overflow-y-auto pr-0.5">
        {items.length === 0 && (
          <p className="rounded-md bg-stone-50 px-3 py-4 text-center text-xs text-stone-400">
            Empty so far — chat or upload a resume.
          </p>
        )}

        {byCategory.map(({ category, items: group }) => (
          <section key={category} data-testid={`vault-section-${category}`}>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-stone-500">
              {SECTION_LABELS[category] ?? category}
            </h3>

            {category === "skill" ? (
              <SkillGroups
                items={group}
                onRemove={(id) => remove.mutate(id)}
                removing={remove.isPending}
              />
            ) : (
              <ul className="space-y-2">
                {group.map((item) => (
                  <VaultCard
                    key={item.id}
                    item={item}
                    onRemove={() => remove.mutate(item.id)}
                    removing={remove.isPending}
                  />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

function SkillGroups({
  items,
  onRemove,
  removing,
}: {
  items: VaultItem[];
  onRemove: (id: string) => void;
  removing: boolean;
}) {
  const groups = new Map<string, VaultItem[]>();
  for (const item of items) {
    const key = skillGroup(item);
    const list = groups.get(key) ?? [];
    list.push(item);
    groups.set(key, list);
  }
  const ordered = [
    ...SKILL_GROUP_ORDER.filter((g) => groups.has(g)),
    ...[...groups.keys()].filter((g) => !SKILL_GROUP_ORDER.includes(g)),
  ];

  return (
    <div className="space-y-3">
      {ordered.map((label) => (
        <div key={label}>
          <p className="mb-1.5 text-[11px] font-medium text-emerald-800">{label}</p>
          <ul className="flex flex-wrap gap-1.5">
            {(groups.get(label) ?? []).map((item) => (
              <li
                key={item.id}
                className="inline-flex max-w-full items-center gap-1 rounded-md border border-emerald-100 bg-emerald-50 px-2 py-1 text-xs text-emerald-900"
              >
                <span className="truncate">{item.title}</span>
                <button
                  type="button"
                  aria-label={`Remove ${item.title}`}
                  disabled={removing}
                  onClick={() => onRemove(item.id)}
                  className="text-emerald-700/70 hover:text-emerald-950 disabled:opacity-40"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function VaultCard({
  item,
  onRemove,
  removing,
}: {
  item: VaultItem;
  onRemove: () => void;
  removing: boolean;
}) {
  const lines = detailLines(item);
  return (
    <li className="rounded-md border border-stone-100 bg-stone-50/80 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <span
          className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
            CATEGORY_STYLES[item.category] ?? CATEGORY_STYLES.other
          }`}
        >
          {item.category}
        </span>
        <button
          type="button"
          aria-label={`Remove ${item.title}`}
          disabled={removing}
          onClick={onRemove}
          className="text-xs text-stone-400 hover:text-rose-600 disabled:opacity-40"
        >
          Remove
        </button>
      </div>
      <p className="mt-1.5 text-sm font-medium leading-snug text-stone-800">
        {item.title}
      </p>
      {lines.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-[11px] leading-snug text-stone-500">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {item.source && (
        <p className="mt-1 text-[10px] uppercase tracking-wide text-stone-400">
          {item.source.replace(/_/g, " ")}
        </p>
      )}
    </li>
  );
}
