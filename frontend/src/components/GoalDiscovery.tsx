import { useState } from "react";
import type { PreparationPreferences } from "../lib/api";

export type GoalOption = { id: string; label: string };

type Props = {
  options: GoalOption[];
  preferences: PreparationPreferences | null | undefined;
  suggestedSkills: string[];
  suggestedProjects: string[];
  phase: string;
  showGoalMenu: boolean;
  goalsReady: boolean;
  pending?: boolean;
  onSaveInterests: (interests: string[]) => void;
  onSaveDetails: (patch: Partial<PreparationPreferences>) => void;
  onConfirmAndStart: () => void;
};

export default function GoalDiscovery({
  options,
  preferences,
  suggestedSkills,
  suggestedProjects,
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
  const interests = selected.length ? selected : draft;

  const needsSkills = interests.includes("skill");
  const needsProjects = interests.includes("project");
  const needsTechnical = interests.includes("technical");
  const needsPlacement = interests.includes("placement");
  const needsBehavioral = interests.includes("behavioral");

  const focusSkills = preferences?.focus_skills ?? [];
  const focusProjects = preferences?.focus_projects ?? [];

  const summaryBits: string[] = [];
  if (selected.length) {
    summaryBits.push(
      selected
        .map((id) => options.find((o) => o.id === id)?.label ?? id)
        .join(", "),
    );
  }
  if (preferences?.target_role) summaryBits.push(`Role: ${preferences.target_role}`);
  if (focusSkills.length) summaryBits.push(`Skills: ${focusSkills.join(", ")}`);
  if (focusProjects.length) summaryBits.push(`Projects: ${focusProjects.join(", ")}`);
  if (preferences?.placement_target) {
    summaryBits.push(`Placement: ${preferences.placement_target}`);
  }

  if (phase === "profile" && !showGoalMenu) return null;

  function toggleInterest(id: string) {
    setDraft((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function toggleList(key: "focus_skills" | "focus_projects", value: string) {
    const cur = preferences?.[key] ?? [];
    const next = cur.includes(value)
      ? cur.filter((x) => x !== value)
      : [...cur, value];
    onSaveDetails({ [key]: next });
  }

  return (
    <div
      className="space-y-3 rounded-lg border border-accent/25 bg-accent-soft/40 p-4"
      data-testid="goal-discovery"
    >
      {(showGoalMenu || (phase === "goals" && !selected.length)) && (
        <>
          <p className="text-sm font-semibold text-ink">
            What would you like to prepare for?
          </p>
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
                  className={`rounded-md px-3 py-2 text-left text-xs font-medium transition ${
                    active
                      ? "bg-accent text-white"
                      : "bg-white text-ink ring-1 ring-stone-200 hover:ring-accent"
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
            onClick={() => onSaveInterests(draft)}
            className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
          >
            Continue
          </button>
        </>
      )}

      {phase === "goals" && selected.length > 0 && !goalsReady && (
        <div className="space-y-3">
          {needsTechnical && (
            <label className="block text-xs text-ink-soft">
              Target role
              <input
                data-testid="goal-target-role"
                defaultValue={preferences?.target_role ?? ""}
                disabled={pending}
                onBlur={(e) => {
                  const v = e.target.value.trim();
                  if (v !== (preferences?.target_role ?? "")) {
                    onSaveDetails({ target_role: v || null });
                  }
                }}
                placeholder="e.g. Backend Intern"
                className="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm text-ink"
              />
            </label>
          )}

          {needsSkills && suggestedSkills.length > 0 && (
            <div>
              <p className="text-xs font-medium text-ink-soft">Skills from your profile</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {suggestedSkills.map((skill) => {
                  const active = focusSkills.includes(skill);
                  return (
                    <button
                      key={skill}
                      type="button"
                      disabled={pending}
                      onClick={() => toggleList("focus_skills", skill)}
                      className={`rounded-md px-2.5 py-1 text-xs ${
                        active
                          ? "bg-emerald-600 text-white"
                          : "bg-white text-ink ring-1 ring-stone-200"
                      }`}
                    >
                      {skill}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {needsProjects && suggestedProjects.length > 0 && (
            <div>
              <p className="text-xs font-medium text-ink-soft">Projects from your vault</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {suggestedProjects.map((project) => {
                  const active = focusProjects.includes(project);
                  return (
                    <button
                      key={project}
                      type="button"
                      disabled={pending}
                      onClick={() => toggleList("focus_projects", project)}
                      className={`rounded-md px-2.5 py-1 text-xs ${
                        active
                          ? "bg-sky-700 text-white"
                          : "bg-white text-ink ring-1 ring-stone-200"
                      }`}
                    >
                      {project}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {needsPlacement && (
            <div className="flex flex-wrap gap-1.5">
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
          )}

          {needsBehavioral && (
            <label className="block text-xs text-ink-soft">
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
                className="mt-1 w-full rounded-md border border-stone-200 bg-white px-3 py-2 text-sm text-ink"
              />
            </label>
          )}
        </div>
      )}

      {(goalsReady || (phase === "ready" && selected.length > 0) || selected.length > 0) && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50/80 px-3 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
            Your preparation plan
          </p>
          <ul className="mt-1.5 space-y-0.5 text-sm text-emerald-950">
            {summaryBits.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
          {selected.length > 0 && (
            <button
              type="button"
              data-testid="start-preparing"
              disabled={pending}
              onClick={onConfirmAndStart}
              className="mt-3 w-full rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-40"
            >
              Start Preparing
            </button>
          )}
        </div>
      )}
    </div>
  );
}
