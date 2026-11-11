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
        <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">
          Where should we start?
        </p>
        <p className="mt-0.5 text-xs text-stone-500">
          Pick a path — or type your own message anytime.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {starters.map((starter) => {
          const active = activeMode === starter.id;
          return (
            <button
              key={starter.id}
              type="button"
              disabled={pending}
              data-testid={`starter-${starter.id}`}
              onClick={() => onSelectStarter(starter.id)}
              className={`group flex items-start gap-3 rounded-xl border px-3.5 py-3 text-left transition ${
                active
                  ? "border-accent bg-accent-soft shadow-sm"
                  : "border-stone-200 bg-white hover:border-accent/50 hover:bg-accent-soft/40"
              } disabled:opacity-50`}
            >
              <span
                className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold tracking-wide ${
                  active
                    ? "bg-accent text-white"
                    : "bg-stone-100 text-stone-600 group-hover:bg-accent/15 group-hover:text-accent-strong"
                }`}
              >
                {STARTER_ICONS[starter.id] ?? "•"}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-stone-800">
                  {starter.label}
                </span>
                <span className="mt-0.5 block text-xs leading-snug text-stone-500">
                  {starter.description}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {skillGroups.length > 0 && (
        <div className="rounded-xl border border-stone-200 bg-stone-50/80 p-3">
          <p className="text-xs font-semibold text-stone-700">Skills from your profile</p>
          <div className="mt-2 space-y-2">
            {skillGroups.map((group) => (
              <div key={group.label}>
                <p className="text-[10px] font-medium uppercase tracking-wide text-stone-400">
                  {group.label}
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {group.items.map((skill) => (
                    <button
                      key={skill}
                      type="button"
                      disabled={pending}
                      onClick={() => onExploreSkill(skill)}
                      className="rounded-md border border-stone-200 bg-white px-2.5 py-1 text-xs font-medium text-stone-700 transition hover:border-accent hover:bg-accent-soft hover:text-accent-strong disabled:opacity-50"
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
        <div className="rounded-xl border border-stone-200 bg-stone-50/80 p-3">
          <p className="text-xs font-semibold text-stone-700">Projects to explore</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {projectList.map((project) => (
              <button
                key={project}
                type="button"
                disabled={pending}
                onClick={() => onExploreProject(project)}
                className="rounded-md border border-stone-200 bg-white px-2.5 py-1 text-xs font-medium text-stone-700 transition hover:border-accent hover:bg-accent-soft hover:text-accent-strong disabled:opacity-50"
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
