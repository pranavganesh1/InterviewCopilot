import type { ConversationStarter, VaultItem } from "../lib/api";

const STARTER_ICONS: Record<string, string> = {
  ai_interview: "AI",
  explore_projects: "PR",
  test_skills: "SK",
  career_goal: "CG",
};

type Props = {
  starters: ConversationStarter[];
  skills: string[];
  projects: string[];
  vaultItems: VaultItem[];
  activeMode?: string | null;
  pending?: boolean;
  onSelectStarter: (id: string) => void;
  onExploreSkill: (skill: string) => void;
  onExploreProject: (project: string) => void;
};

function groupSkills(skills: string[]): { label: string; items: string[] }[] {
  const languages = new Set([
    "python",
    "java",
    "javascript",
    "typescript",
    "c++",
    "c",
    "go",
    "rust",
    "sql",
    "r",
  ]);
  const frameworks = new Set([
    "react",
    "next.js",
    "node",
    "django",
    "flask",
    "spring",
    "pytorch",
    "pytorch geometric",
    "tensorflow",
    "fastapi",
  ]);
  const domains = new Set([
    "ai/ml",
    "machine learning",
    "deep learning",
    "quantum computing",
    "nlp",
    "computer vision",
  ]);

  const buckets: Record<string, string[]> = {
    Languages: [],
    Frameworks: [],
    Domains: [],
    Other: [],
  };

  for (const skill of skills) {
    const key = skill.trim().toLowerCase();
    if (languages.has(key) || key.includes("sql")) buckets.Languages.push(skill);
    else if (frameworks.has(key) || key.includes("pytorch") || key.includes("react"))
      buckets.Frameworks.push(skill);
    else if (domains.has(key) || key.includes("quantum") || key.includes("ml"))
      buckets.Domains.push(skill);
    else buckets.Other.push(skill);
  }

  return Object.entries(buckets)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}

export default function ConversationStarters({
  starters,
  skills,
  projects,
  vaultItems,
  activeMode,
  pending,
  onSelectStarter,
  onExploreSkill,
  onExploreProject,
}: Props) {
  const skillGroups = groupSkills(
    skills.length
      ? skills
      : vaultItems.filter((i) => i.category === "skill").map((i) => i.title),
  );
  const projectList =
    projects.length > 0
      ? projects
      : vaultItems.filter((i) => i.category === "project").map((i) => i.title);

  return (
    <div className="space-y-3" data-testid="conversation-starters">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          Where should we start?
        </p>
        <p className="mt-0.5 text-xs text-ink-faint">
          Pick a path — or type your own message anytime.
        </p>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {starters.map((starter) => {
          const active = activeMode === starter.id;
          return (
            <button
              key={starter.id}
              type="button"
              disabled={pending}
              data-testid={`starter-${starter.id}`}
              onClick={() => onSelectStarter(starter.id)}
              className={`group flex min-h-[4.75rem] items-start gap-3 rounded-2xl border px-3.5 py-3.5 text-left transition ${
                active
                  ? "border-accent bg-accent-soft shadow-sm"
                  : "border-line bg-surface hover:border-accent/45 hover:bg-accent-soft/50"
              } disabled:opacity-50`}
            >
              <span
                className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[10px] font-bold tracking-wide ${
                  active
                    ? "bg-accent text-white"
                    : "bg-accent-soft text-accent-strong group-hover:bg-accent/15"
                }`}
              >
                {STARTER_ICONS[starter.id] ?? "•"}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-ink">
                  {starter.label}
                </span>
                <span className="mt-0.5 block text-xs leading-snug text-ink-soft">
                  {starter.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {skillGroups.length > 0 && (
        <div className="rounded-2xl border border-line bg-accent-soft/30 p-3">
          <p className="text-xs font-semibold text-ink">Skills from your profile</p>
          <div className="mt-2 space-y-2">
            {skillGroups.map((group) => (
              <div key={group.label}>
                <p className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">
                  {group.label}
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {group.items.map((skill) => (
                    <button
                      key={skill}
                      type="button"
                      disabled={pending}
                      onClick={() => onExploreSkill(skill)}
                      className="rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition hover:border-accent hover:bg-accent-soft hover:text-accent-strong disabled:opacity-50"
                    >
                      {skill}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {projectList.length > 0 && (
        <div className="rounded-2xl border border-line bg-accent-soft/30 p-3">
          <p className="text-xs font-semibold text-ink">Projects to explore</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {projectList.map((project) => (
              <button
                key={project}
                type="button"
                disabled={pending}
                onClick={() => onExploreProject(project)}
                className="rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink transition hover:border-accent hover:bg-accent-soft hover:text-accent-strong disabled:opacity-50"
              >
                {project}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
