import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type AdminUserRow } from "../lib/api";

export default function AdminUsersPage() {
  const users = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api<AdminUserRow[]>("/admin/users"),
  });

  if (users.isLoading) return <p className="text-stone-500">Loading users…</p>;
  if (users.error instanceof Error)
    return <p className="text-red-600">{users.error.message}</p>;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Admin · Users</h1>
        <p className="text-sm text-stone-500">
          Per-user activity, LLM cost attribution and performance.
        </p>
      </div>

      {users.data!.length === 0 ? (
        <p className="text-sm text-stone-400">No users yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-stone-200 text-left text-xs text-stone-400">
                <th className="px-4 py-2.5">User</th>
                <th>Tracks</th>
                <th>Interviews</th>
                <th>Minutes</th>
                <th>Tokens</th>
                <th>Est. cost</th>
                <th>Avg performance</th>
              </tr>
            </thead>
            <tbody>
              {users.data!.map((u) => (
                <tr key={u.id} className="border-b border-stone-100">
                  <td className="px-4 py-2.5">
                    <Link
                      to={`/admin/users/${u.id}`}
                      className="font-medium text-accent hover:underline"
                    >
                      {u.name || u.email}
                    </Link>
                    <p className="text-xs text-stone-400">{u.email}</p>
                  </td>
                  <td>{u.tracks}</td>
                  <td>{u.interviews_completed}</td>
                  <td>{u.interview_minutes}</td>
                  <td>{u.tokens.toLocaleString()}</td>
                  <td>${u.estimated_cost_usd.toFixed(4)}</td>
                  <td>
                    {u.avg_performance === null ? (
                      <span className="text-stone-400">—</span>
                    ) : (
                      `${u.avg_performance}/100`
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
