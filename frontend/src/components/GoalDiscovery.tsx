import { useEffect, useMemo, useState } from "react";
import type { PreparationPreferences } from "../lib/api";

export type GoalOption = { id: string; label: string; subtitle?: string };

type FollowupStep =
  | "interests"
  | "technical_role"
  | "technical_areas"
  | "skills"
  | "projects"
  | "project_aspects"
  | "placement_target"
  | "placement_role"
  | "behavioral"
  | null;

type Props = {
  options: GoalOption[];
  preferences: PreparationPreferences | null | undefined;
  suggestedSkills: string[];
  suggestedProjects: string[];
  suggestedRoles?: string[];
  suggestedTechnicalAreas?: string[];
  projectOptions?: GoalOption[];
  projectAspectOptions?: GoalOption[];
  resumeHighlights?: {
    skills?: string[];
    projects?: string[];
    education?: string[];
    internships?: string[];
  };
  nextGoalFollowup?: FollowupStep | string | null;
  followupsComplete?: boolean;
  phase: string;
  showGoalMenu: boolean;
  goalsReady: boolean;
  pending?: boolean;
  onSaveInterests: (interests: string[]) => void;
  onSaveDetails: (patch: Partial<PreparationPreferences>) => void;
  onConfirmAndStart: () => void;
};

function ChipRow({
  items,
  activeValues,
  pending,
  onToggle,
  activeClass = "bg-accent text-white",
}: {
  items: { id: string; label: string; subtitle?: string }[];
  activeValues: string[];
  pending?: boolean;
  onToggle: (id: string) => void;
  activeClass?: string;
}) {
  if (!items.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((item) => {
        const active = activeValues.includes(item.id);
        return (
          <button
            key={item.id}
            type="button"
            disabled={pending}
            title={item.subtitle || item.label}
            onClick={() => onToggle(item.id)}
            className={`rounded-md px-2.5 py-1 text-left text-xs transition ${
              active ? activeClass : "bg-white text-ink ring-1 ring-stone-200 hover:ring-accent"
            }`}
          >
            <span className="font-medium">{item.label}</span>
            {item.subtitle ? (
              <span
                className={`mt-0.5 block text-[10px] ${
                  active ? "text-white/80" : "text-ink-faint"
                }`}
              >
                {item.subtitle}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

const STEP_ORDER: Exclude<FollowupStep, "interests" | null>[] = [
  "technical_role",
  "technical_areas",
  "skills",
  "projects",
  "project_aspects",
  "placement_target",
  "placement_role",
  "behavioral",
];

function isStepApplicable(
  step: Exclude<FollowupStep, "interests" | null>,
  prefs: PreparationPreferences | null | undefined,
): boolean {
  const interests = prefs?.interests ?? [];
  switch (step) {
    case "technical_role":
      return interests.includes("technical") && !prefs?.target_role;
    case "technical_areas":
      return interests.includes("technical") && !(prefs?.technical_areas?.length ?? 0);
    case "skills":
      return interests.includes("skill") && !(prefs?.focus_skills?.length ?? 0);
    case "projects":
      return interests.includes("project") && !(prefs?.focus_projects?.length ?? 0);
    case "project_aspects":
      return (
        interests.includes("project") &&
        (prefs?.focus_projects?.length ?? 0) > 0 &&
        !(prefs?.project_aspects?.length ?? 0)
      );
    case "placement_target":
      return interests.includes("placement") && !prefs?.placement_target;
    case "placement_role":
      return interests.includes("placement") && !prefs?.target_role;
    case "behavioral":
      return (
        interests.includes("behavioral") &&
        !(prefs?.experience_level || prefs?.behavioral_goals)
      );
    default:
      return false;
  }
}

function deriveNextStep(
  prefs: PreparationPreferences | null | undefined,
  skipped: Set<string>,
): FollowupStep {
  if (!(prefs?.interests?.length ?? 0)) return "interests";
  for (const step of STEP_ORDER) {
    if (skipped.has(step)) continue;
    if (isStepApplicable(step, prefs)) return step;
  }
  return null;
}

export default function GoalDiscovery({
  options,
  preferences,
  suggestedSkills,
  suggestedProjects,
  suggestedRoles = [],
  suggestedTechnicalAreas = [],
  projectOptions = [],
  projectAspectOptions = [],
  resumeHighlights,
  followupsComplete,
  phase,
  showGoalMenu,
  goalsReady,
  pending,
  onSaveInterests,
  onSaveDetails,
  onConfirmAndStart,
}: Props) {
  const selected = preferences?.interests ?? [];
  const [draft, setDraft] = useState<string[]>(selected);
  const [customRole, setCustomRole] = useState(preferences?.target_role ?? "");
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [editingFocus, setEditingFocus] = useState(false);

  useEffect(() => {
    setCustomRole(preferences?.target_role ?? "");
  }, [preferences?.target_role]);

  useEffect(() => {
    setDraft(selected);
  }, [selected.join("|")]);

  const step = useMemo(
    () => deriveNextStep(preferences, skipped),
    [
      preferences?.interests?.join("|"),
      preferences?.target_role,
      preferences?.technical_areas?.join("|"),
      preferences?.focus_skills?.join("|"),
      preferences?.focus_projects?.join("|"),
      preferences?.project_aspects?.join("|"),
      preferences?.placement_target,
      preferences?.experience_level,
      preferences?.behavioral_goals,
      skipped,
    ],
  );

  const detailsDone =
    !editingFocus &&
    selected.length > 0 &&
    (followupsComplete === true || goalsReady || step === null);

  const focusSkills = preferences?.focus_skills ?? [];
  const focusProjects = preferences?.focus_projects ?? [];
  const technicalAreas = preferences?.technical_areas ?? [];
  const projectAspects = preferences?.project_aspects ?? [];

  const skillItems = (
    suggestedSkills.length ? suggestedSkills : (resumeHighlights?.skills ?? [])
  ).map((s) => ({ id: s, label: s }));
  const areaItems = (
    suggestedTechnicalAreas.length
      ? suggestedTechnicalAreas
      : [...suggestedSkills, ...suggestedProjects]
  ).map((s) => ({ id: s, label: s }));
  const projectItems: GoalOption[] =
    projectOptions.length > 0
      ? projectOptions.map((p) => ({
          id: p.id || p.label,
          label: p.label,
          subtitle: p.subtitle,
        }))
      : suggestedProjects.map((p) => ({ id: p, label: p }));
  const roleItems = [
    ...suggestedRoles.map((r) => ({ id: r, label: r })),
    ...(!suggestedRoles.includes("I'm still exploring")
      ? [{ id: "I'm still exploring", label: "I'm not sure yet" }]
      : []),
  ];
  const aspectItems =
    projectAspectOptions.length > 0
      ? projectAspectOptions
      : [
          { id: "architecture", label: "Project architecture" },
          { id: "implementation", label: "Technical implementation" },
          { id: "challenges", label: "Challenges and solutions" },
          { id: "technologies", label: "Technologies used" },
          { id: "research", label: "Research contributions" },
          { id: "deep_dive", label: "Complete project deep dive" },
        ];

  const highlightSkills =
    resumeHighlights?.skills?.slice(0, 4) ?? suggestedSkills.slice(0, 4);
  const highlightProjects =
    resumeHighlights?.projects?.slice(0, 3) ?? suggestedProjects.slice(0, 3);

  const summaryBits: string[] = [];
  if (selected.length) {
    summaryBits.push(
      selected.map((id) => options.find((o) => o.id === id)?.label ?? id).join(", "),
    );
  }
  if (preferences?.target_role) summaryBits.push(`Role: ${preferences.target_role}`);
  if (technicalAreas.length) summaryBits.push(`Areas: ${technicalAreas.join(", ")}`);
  if (focusSkills.length) summaryBits.push(`Skills: ${focusSkills.join(", ")}`);
  if (focusProjects.length) summaryBits.push(`Projects: ${focusProjects.join(", ")}`);
  if (projectAspects.length) {
    const labels = projectAspects.map(
      (a) => aspectItems.find((o) => o.id === a)?.label ?? a,
    );
    summaryBits.push(`Project focus: ${labels.join(", ")}`);
  }
  if (preferences?.placement_target) {
    summaryBits.push(`Placement: ${preferences.placement_target}`);
  }
  if (preferences?.behavioral_goals) {
    summaryBits.push(`HR focus: ${preferences.behavioral_goals}`);
  }

  if (phase === "profile" && !showGoalMenu) return null;

  function toggleInterest(id: string) {
    setDraft((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleList(
    key: "focus_skills" | "focus_projects" | "technical_areas" | "project_aspects",
    value: string,
  ) {
    const cur = preferences?.[key] ?? [];
    const next = cur.includes(value)
      ? cur.filter((x) => x !== value)
      : [...cur, value];
    onSaveDetails({ [key]: next });
  }

  function selectRole(role: string) {
    setCustomRole(role);
    if (role !== (preferences?.target_role ?? "")) {
      onSaveDetails({ target_role: role });
    }
  }

  const showInterestPicker =
    editingFocus ||
    showGoalMenu ||
    (phase === "goals" && !selected.length) ||
    step === "interests";

  return (
    <div
      className="space-y-3 rounded-lg border border-accent/25 bg-accent-soft/40 p-4"
      data-testid="goal-discovery"
    >
      {showInterestPicker && (
        <>
          <p className="text-sm font-semibold text-ink">
            What would you like to prepare for?
          </p>
          {(highlightSkills.length > 0 || highlightProjects.length > 0) && (
            <p className="text-xs text-ink-soft">
              Based on your resume
              {highlightSkills.length ? ` (${highlightSkills.join(", ")})` : ""}
              {highlightProjects.length
                ? `${highlightSkills.length ? " and" : ""} projects like ${highlightProjects
                    .map((p) => `“${p}”`)
                    .join(", ")}`
                : ""}
              .
            </p>
          )}
          <p className="text-xs text-ink-soft">Select one or more focuses.</p>
          <div className="flex flex-wrap gap-2">
            {options.map((opt) => {
              const active = draft.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  disabled={pending}
                  data-testid={`goal-interest-${opt.id}`}
                  onClick={() => toggleInterest(opt.id)}
                  className={`rounded-xl px-3 py-2.5 text-left text-xs font-medium shadow-sm transition ${
                    active
                      ? "bg-accent text-white shadow-md"
                      : "bg-white text-ink ring-1 ring-stone-200 hover:bg-accent-soft/50 hover:ring-accent"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            disabled={pending || draft.length === 0}
            onClick={() => {
              setSkipped(new Set());
              setEditingFocus(false);
              onSaveInterests(draft);
            }}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
          >
            Continue
          </button>
        </>
      )}

      {!showInterestPicker && !detailsDone && step && (
        <div className="space-y-3">
          {step === "technical_role" && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-ink">
                Based on your background, which role are you targeting?
              </p>
              <ChipRow
                items={roleItems}
                activeValues={preferences?.target_role ? [preferences.target_role] : []}
                pending={pending}
                onToggle={selectRole}
              />
              <label className="block text-xs text-ink-soft">
                Or type a custom role
                <input
                  data-testid="goal-target-role"
                  value={customRole}
                  disabled={pending}
                  onChange={(e) => setCustomRole(e.target.value)}
                  onBlur={() => {
                    const v = customRole.trim();
                    if (v !== (preferences?.target_role ?? "")) {
                      onSaveDetails({ target_role: v || null });
                    }
                  }}
                  placeholder="e.g. Backend Intern"
                  className="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm text-ink"
                />
              </label>
            </div>
          )}

          {step === "technical_areas" && (
            <div>
              <p className="text-sm font-medium text-ink">
                {highlightSkills.length
                  ? `I noticed ${highlightSkills.slice(0, 3).join(", ")} in your profile. Which areas would you like to practice?`
                  : "Which technical areas would you like to practice?"}
              </p>
              <ChipRow
                items={areaItems}
                activeValues={technicalAreas}
                pending={pending}
                onToggle={(id) => toggleList("technical_areas", id)}
                activeClass="bg-indigo-600 text-white"
              />
            </div>
          )}

          {step === "skills" && (
            <div>
              <p className="text-sm font-medium text-ink">
                {skillItems.length
                  ? `Your resume mentions ${skillItems
                      .slice(0, 3)
                      .map((s) => s.label)
                      .join(", ")}. Which skill would you like to test first?`
                  : "Which skill would you like to practice?"}
              </p>
              <ChipRow
                items={skillItems}
                activeValues={focusSkills}
                pending={pending}
                onToggle={(id) => toggleList("focus_skills", id)}
                activeClass="bg-emerald-600 text-white"
              />
            </div>
          )}

          {step === "projects" && (
            <div>
              <p className="text-sm font-medium text-ink">
                I found these projects in your resume. Which one would you like to
                prepare for interviews?
              </p>
              <ChipRow
                items={projectItems}
                activeValues={focusProjects}
                pending={pending}
                onToggle={(id) => toggleList("focus_projects", id)}
                activeClass="bg-sky-700 text-white"
              />
            </div>
          )}

          {step === "project_aspects" && (
            <div>
              <p className="text-sm font-medium text-ink">
                {focusProjects[0]
                  ? (() => {
                      const card = projectItems.find((p) => p.id === focusProjects[0]);
                      const tech = card?.subtitle;
                      return tech
                        ? `I noticed your “${focusProjects[0]}” project uses ${tech}. What would you like to practice?`
                        : `What should we practice for “${focusProjects[0]}”?`;
                    })()
                  : "What should we practice for your selected projects?"}
              </p>
              <ChipRow
                items={aspectItems}
                activeValues={projectAspects}
                pending={pending}
                onToggle={(id) => toggleList("project_aspects", id)}
                activeClass="bg-sky-800 text-white"
              />
            </div>
          )}

          {step === "placement_target" && (
            <div>
              <p className="text-sm font-medium text-ink">
                Are you preparing for internship, full-time, or both?
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {(["internship", "full-time", "both"] as const).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    disabled={pending}
                    onClick={() => onSaveDetails({ placement_target: opt })}
                    className={`rounded-md px-2.5 py-1 text-xs capitalize ${
                      preferences?.placement_target === opt
                        ? "bg-accent text-white"
                        : "bg-white text-ink ring-1 ring-stone-200"
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === "placement_role" && (
            <div className="space-y-2">
              <p className="text-sm font-medium text-ink">
                Based on your background, which roles are you targeting?
              </p>
              <ChipRow
                items={roleItems}
                activeValues={preferences?.target_role ? [preferences.target_role] : []}
                pending={pending}
                onToggle={selectRole}
              />
              <label className="block text-xs text-ink-soft">
                Custom role
                <input
                  value={customRole}
                  disabled={pending}
                  onChange={(e) => setCustomRole(e.target.value)}
                  onBlur={() => {
                    const v = customRole.trim();
                    if (v !== (preferences?.target_role ?? "")) {
                      onSaveDetails({ target_role: v || null });
                    }
                  }}
                  placeholder="Type a role"
                  className="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm text-ink"
                />
              </label>
            </div>
          )}

          {step === "behavioral" && (
            <label className="block text-sm font-medium text-ink">
              Experience / HR goal
              <input
                defaultValue={preferences?.behavioral_goals ?? ""}
                disabled={pending}
                onBlur={(e) => {
                  const v = e.target.value.trim();
                  if (v !== (preferences?.behavioral_goals ?? "")) {
                    onSaveDetails({
                      behavioral_goals: v || null,
                      experience_level: preferences?.experience_level ?? "student",
                    });
                  }
                }}
                placeholder="e.g. first internship interviews"
                className="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm font-normal text-ink"
              />
            </label>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                setSkipped((prev) => {
                  const next = new Set(prev);
                  if (step) next.add(step);
                  return next;
                })
              }
              className="text-xs font-medium text-ink-soft hover:text-ink"
            >
              Skip for now
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => {
                setDraft(selected);
                setEditingFocus(true);
              }}
              className="text-xs font-medium text-ink-soft hover:text-ink"
            >
              Change focus
            </button>
          </div>
        </div>
      )}

      {detailsDone && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50/80 px-3 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
            Your preparation plan
          </p>
          <ul className="mt-1.5 space-y-0.5 text-sm text-emerald-950">
            {summaryBits.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          <button
            type="button"
            data-testid="start-preparing"
            disabled={pending}
            onClick={onConfirmAndStart}
            className="mt-3 w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
          >
            Start Preparing
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={() => {
              setDraft(selected);
              setEditingFocus(true);
              setSkipped(new Set());
            }}
            className="mt-2 w-full text-xs font-medium text-emerald-800 hover:underline"
          >
            Adjust focus
          </button>
        </div>
      )}
    </div>
  );
}
