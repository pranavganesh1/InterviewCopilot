import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type SessionInfo, type Turn, type TurnResult } from "../lib/api";

const COVERAGE_STYLE: Record<string, string> = {
  excellent: "bg-emerald-100 text-emerald-700",
  good: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  none: "bg-red-100 text-red-700",
};

export default function InterviewPage() {
  const { trackId, sessionId } = useParams();
  const [answer, setAnswer] = useState("");
  const [completed, setCompleted] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () =>
      api<{ session: SessionInfo; turns: Turn[] }>(`/sessions/${sessionId}`),
  });

  const submit = useMutation({
    mutationFn: (answer: string) =>
      api<TurnResult>(`/sessions/${sessionId}/turns`, {
        method: "POST",
        body: JSON.stringify({ answer }),
      }),
    onSuccess: (d) => {
      if (d.completed) setCompleted(true);
      session.refetch();
    },
  });

  const turns = session.data?.turns ?? [];
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, submit.isPending]);

  const send = () => {
    const a = answer.trim();
    if (!a || submit.isPending || completed) return;
    setAnswer("");
    submit.mutate(a);
  };

  if (session.isLoading) return <p className="text-stone-500">Loading session…</p>;

  const openQuestion = [...turns].reverse().find((t) => t.answer === null);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-stone-400">
            {session.data?.session.mode} interview
          </p>
          <h1 className="text-lg font-semibold">Interview session</h1>
        </div>
        {completed && (
          <Link
            to={`/tracks/${trackId}/report/${sessionId}`}
            className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            View feedback report →
          </Link>
        )}
      </div>

      <div className="space-y-4 rounded-2xl border border-stone-200 bg-white p-5">
        {turns.map((t) => {
          const evaluation = t.evaluation ?? undefined;
          return (
            <div key={t.turn_index} className="space-y-2">
              <div className="max-w-[90%] rounded-2xl bg-stone-100 px-4 py-2.5 text-sm">
                <span className="mr-2 rounded-md bg-white px-1.5 py-0.5 text-[10px] font-medium text-stone-500">
                  {t.question_area}
                </span>
                {t.question}
              </div>
              {t.answer !== null && (
                <div className="ml-auto max-w-[90%] rounded-2xl bg-indigo-600 px-4 py-2.5 text-sm whitespace-pre-wrap text-white">
                  {t.answer}
                </div>
              )}
              {evaluation && (
                <div className="ml-auto flex max-w-[90%] flex-wrap items-center gap-2 text-xs">
                  <span
                    className={`rounded-md px-2 py-0.5 font-medium ${
                      COVERAGE_STYLE[evaluation.coverage] ?? "bg-stone-100"
                    }`}
                  >
                    {evaluation.coverage}
                  </span>
                  {evaluation.strengths.slice(0, 2).map((s) => (
                    <span key={s} className="text-emerald-700">
                      + {s}
                    </span>
                  ))}
                  {evaluation.gaps.slice(0, 2).map((g) => (
                    <span key={g} className="text-amber-700">
                      − {g}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {submit.isPending && (
          <div className="rounded-2xl bg-stone-100 px-4 py-2.5 text-sm italic text-stone-400">
            Interviewer is evaluating your answer…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {completed || session.data?.session.status === "completed" ? (
        <p className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          Interview complete. Your feedback report is ready.
        </p>
      ) : (
        <div className="mt-4 flex gap-2">
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={3}
            placeholder="Type your answer… (no hints in strict mode!)"
            className="flex-1 rounded-2xl border border-stone-200 px-4 py-3 text-sm outline-none focus:border-indigo-400"
            disabled={submit.isPending || !openQuestion}
          />
          <button
            onClick={send}
            disabled={submit.isPending || !answer.trim() || !openQuestion}
            className="self-end rounded-2xl bg-indigo-600 px-5 py-3 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
          >
            Answer
          </button>
        </div>
      )}
    </div>
  );
}
