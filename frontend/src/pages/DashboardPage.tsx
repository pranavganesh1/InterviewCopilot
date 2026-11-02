import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Track } from "../lib/api";

const TYPE_LABELS: Record<string, string> = {
  topic: "Topic",
  role: "Role",
  company_jd: "Company + JD",
};

export default function DashboardPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    track_type: "topic",
    subject: "",
    company: "",
    jd_text: "",
  });

  const tracks = useQuery({
    queryKey: ["tracks"],
    queryFn: () => api<Track[]>("/tracks"),
  });

  const create = useMutation({
    mutationFn: () =>
      api<{ track: Track }>("/tracks", {
        method: "POST",
        body: JSON.stringify({
          track_type: form.track_type,
          subject: form.subject,
          company: form.company || null,
          jd_text: form.track_type === "company_jd" ? form.jd_text : null,
        }),
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({ track_type: "topic", subject: "", company: "", jd_text: "" });
      qc.invalidateQueries({ queryKey: ["tracks"] });
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Preparation tracks</h1>
          <p className="text-sm text-stone-500">
            Each track has its own interviews, feedback, and progression.
          </p>
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          {showForm ? "Cancel" : "New track"}
        </button>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
          className="mt-4 space-y-3 rounded-2xl border border-stone-200 bg-white p-5"
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm">
              <span className="text-stone-500">Type</span>
              <select
                value={form.track_type}
                onChange={(e) => setForm({ ...form, track_type: e.target.value })}
                className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2"
              >
                <option value="topic">Topic (e.g. DSA)</option>
                <option value="role">Role (e.g. Backend Intern)</option>
                <option value="company_jd">Company + JD</option>
              </select>
            </label>
            <label className="text-sm sm:col-span-2">
              <span className="text-stone-500">Subject / role</span>
              <input
                required
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="Data Structures & Algorithms"
                className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2"
              />
            </label>
          </div>
          {form.track_type === "company_jd" && (
            <>
              <label className="block text-sm">
                <span className="text-stone-500">Company</span>
                <input
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Acme Corp"
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2"
                />
              </label>
              <label className="block text-sm">
                <span className="text-stone-500">Job description</span>
                <textarea
                  required
                  value={form.jd_text}
                  onChange={(e) => setForm({ ...form, jd_text: e.target.value })}
                  rows={4}
                  placeholder="Paste the JD here — the architect derives requirements only from this text."
                  className="mt-1 w-full rounded-xl border border-stone-200 px-3 py-2"
                />
              </label>
            </>
          )}
          {create.error instanceof Error && (
            <p className="text-sm text-red-600">{create.error.message}</p>
          )}
          <button
            disabled={create.isPending}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {create.isPending
              ? "Interview Architect is designing your brief… (~30 s)"
              : "Create track"}
          </button>
        </form>
      )}

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {tracks.data?.length === 0 && (
          <p className="text-sm text-stone-400">
            No tracks yet — create your first one.
          </p>
        )}
        {tracks.data?.map((t) => (
          <Link
            key={t.id}
            to={`/tracks/${t.id}`}
            className="rounded-2xl border border-stone-200 bg-white p-5 transition hover:border-indigo-300"
          >
            <span className="rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] font-medium text-stone-600">
              {TYPE_LABELS[t.track_type] ?? t.track_type}
            </span>
            <h2 className="mt-2 font-medium">{t.subject}</h2>
            {t.company && <p className="text-sm text-stone-500">{t.company}</p>}
            <p className="mt-2 text-xs text-stone-400">
              Brief v{t.brief_version ?? 0}
              {t.status !== "active" ? ` · ${t.status}` : ""}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
