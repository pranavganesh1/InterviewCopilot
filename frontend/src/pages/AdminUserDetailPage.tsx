import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type AdminUserDetail } from "../lib/api";

export default function AdminUserDetailPage() {
  const { userId } = useParams();

  const data = useQuery({
    queryKey: ["admin-user", userId],
    queryFn: () => api<AdminUserDetail>(`/admin/users/${userId}`),
  });

  if (data.isLoading) return <p className="text-stone-500">Loading…</p>;
  if (data.error instanceof Error)
    return <p className="text-red-600">{data.error.message}</p>;

  const d = data.data!;
  return (
    <div className="space-y-6">
      <div>
        <Link to="/admin/users" className="text-sm text-indigo-600 hover:underline">
          ← All users
        </Link>
        <h1 className="mt-1 text-xl font-semibold">{d.user.name || d.user.email}</h1>
        <p className="text-sm text-stone-500">{d.user.email}</p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <p className="text-[11px] uppercase tracking-wide text-stone-400">LLM calls</p>
          <p className="mt-1 text-lg font-semibold">{d.llm.calls}</p>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <p className="text-[11px] uppercase tracking-wide text-stone-400">Tokens</p>
          <p className="mt-1 text-lg font-semibold tabular-nums">
            {d.llm.tokens.toLocaleString()}
          </p>
        </div>
        <div className="rounded-2xl border border-stone-200 bg-white p-4">
          <p className="text-[11px] uppercase tracking-wide text-stone-400">Est. cost</p>
          <p className="mt-1 text-lg font-semibold">
            ${d.llm.estimated_cost_usd.toFixed(4)}
          </p>
        </div>
      </div>

      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">Tracks</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {d.tracks.length === 0 && <p className="text-sm text-stone-400">None</p>}
          {d.tracks.map((t) => (
            <span
              key={t.id}
              className="rounded-lg bg-stone-100 px-2.5 py-1 text-sm text-stone-700"
            >
              {t.subject}
              <span className="ml-1.5 text-xs text-stone-400">{t.track_type}</span>
              {t.archived && (
                <span className="ml-1.5 text-xs font-semibold text-amber-700">Archived</span>
              )}
            </span>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">Interview sessions</h2>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-stone-400">
              <th className="py-1">Started</th>
              <th>Mode</th>
              <th>Status</th>
              <th>Minutes</th>
              <th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {d.sessions.length === 0 && (
              <tr>
                <td colSpan={5} className="py-2 text-stone-400">
                  No sessions yet.
                </td>
              </tr>
            )}
            {d.sessions.map((s) => (
              <tr key={s.id} className="border-t border-stone-100">
                <td className="py-1.5">{s.started.slice(0, 16).replace("T", " ")}</td>
                <td>{s.mode}</td>
                <td>{s.status}</td>
                <td>{s.minutes}</td>
                <td>{s.coverage_status ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-2xl border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">Report summaries</h2>
        <div className="mt-3 space-y-2">
          {d.reports.length === 0 && (
            <p className="text-sm text-stone-400">No reports yet.</p>
          )}
          {d.reports.map((r) => (
            <div key={r.session_id} className="rounded-xl border border-stone-100 p-3">
              <p className="text-xs font-medium uppercase text-stone-400">
                {r.coverage_status}
              </p>
              <p className="mt-1 text-sm">{r.summary_overview}…</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
