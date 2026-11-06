import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type AdminOverview } from "../lib/api";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-stone-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-stone-900">{value}</p>
    </div>
  );
}

export default function AdminOverviewPage() {
  const data = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => api<AdminOverview>("/admin/overview"),
  });

  if (data.isLoading) return <p className="text-stone-500">Loading analytics…</p>;
  if (data.error instanceof Error)
    return <p className="text-red-600">{data.error.message}</p>;

  const d = data.data!;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Admin · Overview</h1>
        <p className="text-sm text-stone-500">
          Platform totals and estimated LLM cost (list-price basis).
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Users" value={d.users} />
        <Stat label="Tracks" value={d.tracks} />
        <Stat label="Interviews" value={`${d.interviews_completed}/${d.interviews_total}`} />
        <Stat label="Interview minutes" value={d.interview_minutes} />
        <Stat label="LLM calls" value={d.llm_calls} />
        <Stat label="Tokens in" value={d.tokens_in.toLocaleString()} />
        <Stat label="Tokens out" value={d.tokens_out.toLocaleString()} />
        <Stat label="Est. cost" value={`$${d.estimated_cost_usd.toFixed(4)}`} />
      </div>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">By day (last 30)</h2>
        {d.by_day.length === 0 ? (
          <p className="mt-2 text-sm text-stone-400">No LLM calls recorded yet.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-stone-400">
                <th className="py-1">Day</th>
                <th>Calls</th>
                <th>Tokens</th>
                <th>Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {d.by_day.map((r) => (
                <tr key={r.day} className="border-t border-stone-100">
                  <td className="py-1.5">{r.day}</td>
                  <td>{r.calls}</td>
                  <td>{r.tokens.toLocaleString()}</td>
                  <td>${r.estimated_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-stone-500">By model</h2>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-stone-400">
              <th className="py-1">Model</th>
              <th>Calls</th>
              <th>Tokens</th>
              <th>Est. cost</th>
            </tr>
          </thead>
          <tbody>
            {d.by_model.map((r) => (
              <tr key={r.model} className="border-t border-stone-100">
                <td className="py-1.5">{r.model}</td>
                <td>{r.calls}</td>
                <td>{r.tokens.toLocaleString()}</td>
                <td>${r.estimated_cost_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <Link to="/admin/users" className="inline-block text-sm text-accent hover:underline">
        Users →
      </Link>
    </div>
  );
}
