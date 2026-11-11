import { useEffect, useState } from "react";
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

const PROJECT_DETAIL_KEYS = [
  "purpose",
  "technologies",
  "architecture",
  "contribution",
  "outcome",
  "features",
] as const;

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

function invalidateVaultQueries(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ["onboarding-state"] });
  qc.invalidateQueries({ queryKey: ["vault-items"] });
  qc.invalidateQueries({ queryKey: ["profile-review"] });
}

export function VaultSidebar({ items }: { items: VaultItem[] }) {
  const qc = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);

  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/vault/items/${id}`, { method: "DELETE" }),
    onSuccess: () => invalidateVaultQueries(qc),
  });

  const save = useMutation({
    mutationFn: (payload: {
      id: string;
      title: string;
      details?: Record<string, string>;
    }) =>
      api<VaultItem>(`/vault/items/${payload.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: payload.title,
          details: payload.details,
        }),
      }),
    onSuccess: () => {
      setEditingId(null);
      invalidateVaultQueries(qc);
    },
  });

  const byCategory = SECTION_ORDER.map((category) => ({
    category,
    items: items.filter((i) => i.category === category),
  })).filter((g) => g.items.length > 0);

  const busy = remove.isPending || save.isPending;

  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-stone-800">Your vault</h2>
        <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600">
          {items.length} items
        </span>
      </div>
      <p className="mt-1 text-xs text-stone-500">
        Correct titles and details here — changes save through your profile vault.
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
                editingId={editingId}
                onEdit={setEditingId}
                onCancel={() => setEditingId(null)}
                onSave={(id, title) => save.mutate({ id, title })}
                onRemove={(id) => remove.mutate(id)}
                busy={busy}
              />
            ) : (
              <ul className="space-y-2">
                {group.map((item) => (
                  <VaultCard
                    key={item.id}
                    item={item}
                    editing={editingId === item.id}
                    onEdit={() => setEditingId(item.id)}
                    onCancel={() => setEditingId(null)}
                    onSave={(title, details) =>
                      save.mutate({ id: item.id, title, details })
                    }
                    onRemove={() => remove.mutate(item.id)}
                    busy={busy}
                  />
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
      {save.error instanceof Error && (
        <p className="mt-2 text-xs text-rose-600">{save.error.message}</p>
      )}
    </div>
  );
}

function SkillGroups({
  items,
  editingId,
  onEdit,
  onCancel,
  onSave,
  onRemove,
  busy,
}: {
  items: VaultItem[];
  editingId: string | null;
  onEdit: (id: string) => void;
  onCancel: () => void;
  onSave: (id: string, title: string) => void;
  onRemove: (id: string) => void;
  busy: boolean;
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
            {(groups.get(label) ?? []).map((item) =>
              editingId === item.id ? (
                <li key={item.id} className="w-full">
                  <SkillEditForm
                    title={item.title}
                    busy={busy}
                    onCancel={onCancel}
                    onSave={(title) => onSave(item.id, title)}
                  />
                </li>
              ) : (
                <li
                  key={item.id}
                  className="inline-flex max-w-full items-center gap-1 rounded-md border border-emerald-100 bg-emerald-50 px-2 py-1 text-xs text-emerald-900"
                >
                  <button
                    type="button"
                    onClick={() => onEdit(item.id)}
                    className="truncate hover:underline"
                    title="Edit skill name"
                  >
                    {item.title}
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${item.title}`}
                    disabled={busy}
                    onClick={() => onRemove(item.id)}
                    className="text-emerald-700/70 hover:text-emerald-950 disabled:opacity-40"
                  >
                    ×
                  </button>
                </li>
              ),
            )}
          </ul>
        </div>
      ))}
    </div>
  );
}

function SkillEditForm({
  title,
  busy,
  onCancel,
  onSave,
}: {
  title: string;
  busy: boolean;
  onCancel: () => void;
  onSave: (title: string) => void;
}) {
  const [draft, setDraft] = useState(title);
  return (
    <form
      className="flex flex-wrap items-center gap-1.5 rounded-md border border-emerald-200 bg-white p-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!draft.trim() || busy) return;
        onSave(draft.trim());
      }}
    >
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        maxLength={255}
        className="min-w-0 flex-1 rounded border border-stone-200 px-2 py-1 text-xs outline-none focus:border-accent"
        aria-label="Skill name"
      />
      <button
        type="submit"
        disabled={busy || !draft.trim()}
        className="text-[11px] font-semibold text-accent-strong disabled:opacity-40"
      >
        Save
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="text-[11px] text-stone-500"
      >
        Cancel
      </button>
    </form>
  );
}

function VaultCard({
  item,
  editing,
  onEdit,
  onCancel,
  onSave,
  onRemove,
  busy,
}: {
  item: VaultItem;
  editing: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (title: string, details: Record<string, string>) => void;
  onRemove: () => void;
  busy: boolean;
}) {
  const lines = detailLines(item);
  const [title, setTitle] = useState(item.title);
  const [details, setDetails] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!editing) return;
    const existing = item.details || {};
    const keys =
      item.category === "project"
        ? [...PROJECT_DETAIL_KEYS]
        : Object.keys(existing);
    const next: Record<string, string> = {};
    for (const key of keys) {
      next[key] = String(existing[key] || "");
    }
    setTitle(item.title);
    setDetails(next);
  }, [editing, item]);

  if (editing) {
    return (
      <li className="rounded-md border border-accent/30 bg-white px-3 py-2.5">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim() || busy) return;
            const cleaned: Record<string, string> = {};
            for (const [key, value] of Object.entries(details)) {
              cleaned[key] = value.trim();
            }
            onSave(title.trim(), cleaned);
          }}
        >
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
            className="w-full rounded border border-stone-200 px-2 py-1.5 text-sm outline-none focus:border-accent"
            aria-label="Item title"
          />
          {Object.keys(details).map((key) => (
            <label key={key} className="block text-[11px] text-stone-500">
              <span className="font-medium capitalize">{key}</span>
              <input
                value={details[key] ?? ""}
                onChange={(e) =>
                  setDetails((prev) => ({ ...prev, [key]: e.target.value }))
                }
                className="mt-0.5 w-full rounded border border-stone-200 px-2 py-1 text-xs text-stone-800 outline-none focus:border-accent"
              />
            </label>
          ))}
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={busy || !title.trim()}
              className="rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
            >
              Save
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="rounded-md px-2.5 py-1 text-[11px] text-stone-500"
            >
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

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
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onEdit}
            className="text-xs font-medium text-accent-strong hover:underline"
          >
            Edit
          </button>
          <button
            type="button"
            aria-label={`Remove ${item.title}`}
            disabled={busy}
            onClick={onRemove}
            className="text-xs text-stone-400 hover:text-rose-600 disabled:opacity-40"
          >
            Remove
          </button>
        </div>
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

export default VaultSidebar;
