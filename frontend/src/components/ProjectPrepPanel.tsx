import { Link } from "react-router-dom";
import type { ProjectIntelligence } from "../lib/api";

type Props = {
  data?: ProjectIntelligence | null;
  defense?: {
    projects_assessed?: string[];
    demonstrated?: string[];
    knowledge_gaps?: string[];
    ownership_unclear?: string[];
    has_data?: boolean;
  } | null;
  onDefend?: () => void;
  canDefend?: boolean;
};

function techList(value: string[] | string | null | undefined): string {
  if (Array.isArray(value)) return value.filter(Boolean).slice(0, 6).join(", ");
  if (typeof value === "string") return value;
  return "";
}

/**
 * Vault projects/internships for prep — claims only until defended.
 * Never auto-selects a primary project.
 */
export default function ProjectPrepPanel({
  data,
  defense,
  onDefend,
  canDefend,
}: Props) {
  const projects = data?.projects ?? [];
  const internships = data?.internships ?? [];
  const empty = projects.length === 0 && internships.length === 0;

  return (
    <section
      className="space-y-3 rounded-2xl border border-line bg-white p-5 shadow-card"
      data-testid="project-prep-panel"
      aria-labelledby="project-prep-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="project-prep-heading" className="text-sm font-semibold text-ink">
            Project & internship preparation
          </h2>
          <p className="mt-1 text-xs text-ink-soft">
            From your vault. Details are claims until you defend them in an interview.
          </p>
        </div>
        <Link
          to="/onboarding"
          className="text-xs font-semibold text-accent-strong hover:underline"
        >
          Edit vault
        </Link>
      </div>

      {empty ? (
        <p
          className="rounded-md border border-dashed border-line bg-page px-3 py-4 text-center text-sm text-ink-faint"
          data-testid="project-prep-empty"
        >
          Add projects or internships in your profile vault to prepare for defense
          questions.
        </p>
      ) : (
        <ul className="space-y-3">
          {projects.map((project, idx) => {
            const name = project.name || "Untitled project";
            const tech = techList(project.technologies);
            const clarify = project.needs_clarification ?? [];
            return (
              <li
                key={`${name}-${idx}`}
                className="rounded-xl border border-line bg-page/40 p-3"
                data-testid="project-prep-item"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-ink">{name}</p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      project.discussion_ready
                        ? "bg-emerald-50 text-emerald-800"
                        : "bg-amber-50 text-amber-900"
                    }`}
                  >
                    {project.discussion_ready
                      ? "Discussion ready"
                      : "Needs clarification"}
                  </span>
                  <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-800">
                    Claim
                  </span>
                </div>
                {tech && (
                  <p className="mt-1 text-xs text-ink-soft">Tech: {tech}</p>
                )}
                {project.contribution && (
                  <p className="mt-1 text-xs text-ink">
                    Contribution: {project.contribution}
                  </p>
                )}
                {project.architecture && (
                  <p className="mt-1 text-xs text-ink-soft line-clamp-2">
                    Architecture: {project.architecture}
                  </p>
                )}
                {project.outcomes && (
                  <p className="mt-1 text-xs text-ink-soft line-clamp-2">
                    Outcomes: {project.outcomes}
                  </p>
                )}
                {clarify.length > 0 && (
                  <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-amber-900">
                    {clarify.slice(0, 3).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
          {internships.map((item, idx) => (
            <li
              key={item.title || `internship-${idx}`}
              className="rounded-xl border border-line bg-page/40 p-3"
              data-testid="internship-prep-item"
            >
              <p className="text-sm font-semibold text-ink">
                {item.title || "Internship"}
              </p>
              <span className="mt-1 inline-block rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-semibold text-sky-800">
                Internship claim
              </span>
            </li>
          ))}
        </ul>
      )}

      {defense?.has_data && (
        <div
          className="rounded-xl border border-line bg-page/60 p-3"
          data-testid="project-defense-signals"
        >
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
            Interview defense signals
          </p>
          <p className="mt-1 text-xs text-ink">
            Assessed:{" "}
            {(defense.projects_assessed ?? []).slice(0, 4).join(", ") || "—"}
          </p>
          {(defense.knowledge_gaps?.length ?? 0) > 0 && (
            <p className="mt-1 text-xs text-amber-800">
              Gaps: {defense.knowledge_gaps!.slice(0, 3).join("; ")}
            </p>
          )}
          {(defense.ownership_unclear?.length ?? 0) > 0 && (
            <p className="mt-1 text-xs text-ink-soft">
              Ownership to clarify:{" "}
              {defense.ownership_unclear!.slice(0, 2).join("; ")}
            </p>
          )}
        </div>
      )}

      {data?.note && (
        <p className="text-[11px] text-ink-faint">{data.note}</p>
      )}

      {onDefend && (
        <button
          type="button"
          data-testid="defend-projects-cta"
          disabled={!canDefend}
          onClick={onDefend}
          className="inline-flex rounded-xl bg-accent px-3 py-2 text-xs font-semibold text-white hover:bg-accent-strong disabled:opacity-50"
        >
          Practice project defense
        </button>
      )}
    </section>
  );
}
