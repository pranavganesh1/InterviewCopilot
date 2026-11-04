import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import {
  api,
  type AssessmentsDashboard,
  type ProfileUpdate,
  type User,
} from "../lib/api";

function initials(name: string, email: string) {
  const base = (name || email || "?").trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

export default function ProfilePage() {
  const { user, refresh } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ProfileUpdate>({});

  const assessments = useQuery({
    queryKey: ["me-assessments"],
    queryFn: () => api<AssessmentsDashboard>("/me/assessments"),
  });

  const save = useMutation({
    mutationFn: (body: ProfileUpdate) =>
      api<User>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: async () => {
      await refresh();
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["me-assessments"] });
    },
  });

  if (!user) return null;

  const startEdit = () => {
    setForm({
      name: user.name || "",
      professional_title: user.professional_title || "",
      introduction: user.introduction || "",
      education: user.education || "",
      picture_url: user.picture_url || "",
      skills: user.skills ?? [],
    });
    setEditing(true);
  };

  const dash = assessments.data?.dashboard;
  const history = assessments.data?.assessments ?? [];
  const skillsText = (form.skills ?? []).join(", ");

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <section className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
        <div className="bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-8 sm:px-8">
          <div className="flex flex-wrap items-center gap-4">
            {user.picture_url ? (
              <img
                src={user.picture_url}
                alt=""
                className="h-20 w-20 rounded-full border-2 border-white/80 object-cover shadow"
              />
            ) : (
              <div className="grid h-20 w-20 place-items-center rounded-full border-2 border-white/80 bg-white/20 text-xl font-semibold text-white">
                {initials(user.name, user.email)}
              </div>
            )}
            <div className="min-w-0 text-white">
              <h1 className="truncate text-2xl font-semibold tracking-tight">
                {user.name || "Your profile"}
              </h1>
              <p className="mt-0.5 text-sm text-indigo-100">
                {user.professional_title || "Add a professional title"}
              </p>
              <p className="mt-1 text-xs text-indigo-200">{user.email}</p>
            </div>
            {!editing && (
              <button
                type="button"
                onClick={startEdit}
                className="ml-auto rounded-xl bg-white px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50"
              >
                Edit profile
              </button>
            )}
          </div>
        </div>

        <div className="space-y-4 px-5 py-5 sm:px-8">
          {editing ? (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                const skills = skillsText
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean);
                save.mutate({
                  name: form.name?.trim() || "",
                  professional_title: form.professional_title?.trim() || "",
                  introduction: form.introduction?.trim() || "",
                  education: form.education?.trim() || "",
                  picture_url: form.picture_url?.trim() || null,
                  skills,
                });
              }}
            >
              <label className="block text-xs font-medium text-stone-500">
                Full name
                <input
                  value={form.name ?? ""}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label className="block text-xs font-medium text-stone-500">
                Professional title
                <input
                  value={form.professional_title ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, professional_title: e.target.value })
                  }
                  placeholder="e.g. Backend Developer"
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label className="block text-xs font-medium text-stone-500">
                Short introduction
                <textarea
                  value={form.introduction ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, introduction: e.target.value })
                  }
                  rows={3}
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label className="block text-xs font-medium text-stone-500">
                Skills (comma-separated)
                <input
                  value={skillsText}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      skills: e.target.value.split(",").map((s) => s.trim()),
                    })
                  }
                  placeholder="Python, SQL, System Design"
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label className="block text-xs font-medium text-stone-500">
                Education
                <textarea
                  value={form.education ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, education: e.target.value })
                  }
                  rows={2}
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              <label className="block text-xs font-medium text-stone-500">
                Profile photo URL (optional)
                <input
                  value={form.picture_url ?? ""}
                  onChange={(e) =>
                    setForm({ ...form, picture_url: e.target.value })
                  }
                  placeholder="https://…"
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
                />
              </label>
              {save.isError && (
                <p className="text-sm text-red-600">
                  {save.error instanceof Error
                    ? save.error.message
                    : "Could not save profile."}
                </p>
              )}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="submit"
                  disabled={save.isPending}
                  className="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  {save.isPending ? "Saving…" : "Save profile"}
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className="rounded-xl border border-stone-200 px-4 py-2.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
                >
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <>
              {user.introduction ? (
                <p className="text-sm leading-relaxed text-stone-700">
                  {user.introduction}
                </p>
              ) : (
                <p className="text-sm text-stone-400">
                  No introduction yet — edit your profile to add one.
                </p>
              )}
              <div>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Skills
                </h2>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(user.skills ?? []).length === 0 && (
                    <span className="text-sm text-stone-400">No skills listed</span>
                  )}
                  {(user.skills ?? []).map((s) => (
                    <span
                      key={s}
                      className="rounded-md bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-800"
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <h2 className="text-xs font-semibold uppercase tracking-wide text-stone-500">
                  Education
                </h2>
                <p className="mt-1 whitespace-pre-wrap text-sm text-stone-700">
                  {user.education || "Not set"}
                </p>
              </div>
            </>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-stone-800">
          Interview performance
        </h2>
        {assessments.isLoading ? (
          <p className="text-sm text-stone-500">Loading assessments…</p>
        ) : assessments.isError ? (
          <p className="text-sm text-red-600">
            Could not load assessment history.
          </p>
        ) : !dash || dash.completed_interviews === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-5 py-8 text-center">
            <p className="text-sm font-medium text-stone-700">
              No completed assessments yet
            </p>
            <p className="mt-1 text-xs text-stone-500">
              Finish an interview to see scores, strengths, and history here.
            </p>
            <Link
              to="/"
              className="mt-3 inline-block text-sm font-medium text-indigo-600 hover:underline"
            >
              Go to tracks →
            </Link>
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
                  Completed interviews
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-indigo-950">
                  {dash.completed_interviews}
                </p>
              </div>
              <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
                  Average score
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-indigo-950">
                  {dash.average_score != null ? `${dash.average_score}%` : "—"}
                </p>
              </div>
              <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                <p className="text-[11px] font-medium uppercase tracking-wide text-stone-500">
                  Questions attempted
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-indigo-950">
                  {dash.total_questions_attempted}
                </p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-stone-800">
                  Technical strengths
                </h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone-700">
                  {dash.strongest_skills.length === 0 && (
                    <li className="list-none pl-0 text-stone-400">
                      Not enough data yet
                    </li>
                  )}
                  {dash.strongest_skills.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-stone-800">
                  Areas to improve
                </h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-stone-700">
                  {dash.skills_needing_improvement.length === 0 && (
                    <li className="list-none pl-0 text-stone-400">
                      Not enough data yet
                    </li>
                  )}
                  {dash.skills_needing_improvement.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>

            {dash.recommended_topics.length > 0 && (
              <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
                <h3 className="text-sm font-semibold text-indigo-950">
                  Recommended next learning topics
                </h3>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {dash.recommended_topics.map((t) => (
                    <span
                      key={t}
                      className="rounded-md bg-white px-2 py-1 text-xs font-medium text-indigo-800 ring-1 ring-indigo-100"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div id="history">
              <h3 className="mb-2 text-sm font-semibold text-stone-800">
                Assessment history
              </h3>
              <div className="space-y-2">
                {history.map((a) => (
                  <div
                    key={a.report_id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-3 shadow-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-stone-900">
                        {a.track_subject}
                      </p>
                      <p className="mt-0.5 text-xs text-stone-500">
                        {new Date(a.created_at).toLocaleString()} ·{" "}
                        {a.session_mode} · {a.questions_attempted}/{a.max_turns}{" "}
                        questions · {a.coverage_status}
                        {a.overall_score != null
                          ? ` · ${a.overall_score}%`
                          : ""}
                      </p>
                    </div>
                    <Link
                      to={`/tracks/${a.track_id}/report/${a.session_id}`}
                      className="shrink-0 rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-700"
                    >
                      View Full Feedback
                    </Link>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
