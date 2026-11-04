import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import CodingWorkspace from "../components/CodingWorkspace";
import EvaluationFeedback from "../components/EvaluationFeedback";
import {
  api,
  type AssistanceResult,
  type SessionInfo,
  type Turn,
  type TurnEvaluation,
  type TurnResult,
} from "../lib/api";
import { classifyQuestion } from "../lib/questionKind";

const DEFAULT_MAX_TURNS = 15;

type SessionPayload = { session: SessionInfo; turns: Turn[] };

function mergeSubmitIntoCache(
  old: SessionPayload | undefined,
  vars: { answer: string; turnIndex: number },
  d: TurnResult,
): SessionPayload | undefined {
  if (!old) return old;
  const turns = old.turns.map((t) =>
    t.turn_index === vars.turnIndex
      ? { ...t, answer: vars.answer, evaluation: d.evaluation }
      : t,
  );
  if (d.turn && !turns.some((t) => t.turn_index === d.turn!.turn_index)) {
    turns.push({ ...d.turn, answer: d.turn.answer ?? null });
  }
  return {
    session: {
      ...old.session,
      status: d.completed ? "completed" : old.session.status,
    },
    turns,
  };
}

export default function InterviewPage() {
  const { trackId, sessionId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [answer, setAnswer] = useState("");
  const [completed, setCompleted] = useState(false);
  const [confirmExit, setConfirmExit] = useState(false);
  const [latestHint, setLatestHint] = useState<AssistanceResult["assistance"] | null>(
    null,
  );
  const [reportedMaxLevel, setReportedMaxLevel] = useState<number | null>(null);
  const [lastEvaluation, setLastEvaluation] = useState<{
    turnIndex: number;
    evaluation: TurnEvaluation;
  } | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api<SessionPayload>(`/sessions/${sessionId}`),
  });

  const submit = useMutation({
    mutationFn: (payload: { answer: string; turnIndex: number }) =>
      api<TurnResult>(`/sessions/${sessionId}/turns`, {
        method: "POST",
        body: JSON.stringify({ answer: payload.answer }),
      }),
    onSuccess: (d, vars) => {
      setLastEvaluation({
        turnIndex: vars.turnIndex,
        evaluation: d.evaluation,
      });
      if (d.completed) setCompleted(true);
      setLatestHint(null);
      setReportedMaxLevel(null);
      setAnswer("");
      qc.setQueryData<SessionPayload>(["session", sessionId], (old) =>
        mergeSubmitIntoCache(old, vars, d),
      );
      void session.refetch();
    },
  });

  const assist = useMutation({
    mutationFn: () =>
      api<AssistanceResult>(`/sessions/${sessionId}/assistance`, {
        method: "POST",
      }),
    onSuccess: (d) => {
      setLatestHint(d.assistance);
      setReportedMaxLevel(d.max_level || 3);
      session.refetch();
    },
  });

  const finishEarly = useMutation({
    mutationFn: () =>
      api<{ session: SessionInfo }>(`/sessions/${sessionId}/complete`, {
        method: "POST",
      }),
    onSuccess: () => {
      setCompleted(true);
      setConfirmExit(false);
      qc.setQueryData<SessionPayload>(["session", sessionId], (old) =>
        old
          ? {
              ...old,
              session: { ...old.session, status: "completed" },
            }
          : old,
      );
      navigate(`/tracks/${trackId}/report/${sessionId}`);
    },
  });

  const turns = session.data?.turns ?? [];
  const interviewDone =
    completed || session.data?.session.status === "completed";
  const isGuided = session.data?.session.mode === "guided";
  const openQuestion = [...turns].reverse().find((t) => t.answer === null);
  const awaitingAnswer = !interviewDone && !!openQuestion;
  const openAssistanceLevel = openQuestion?.assistance_level ?? 0;
  const openKind = openQuestion
    ? classifyQuestion(openQuestion.question_area, openQuestion.question)
    : "text";
  const assistMaxLevel =
    reportedMaxLevel ?? (openKind === "coding" ? 5 : 3);
  const canAssist =
    isGuided &&
    awaitingAnswer &&
    openAssistanceLevel < assistMaxLevel &&
    !submit.isPending;
  const answeredCount = turns.filter((t) => t.answer !== null).length;
  const currentIndex = openQuestion?.turn_index ?? answeredCount;
  const maxTurns = session.data?.session.max_turns ?? DEFAULT_MAX_TURNS;
  const showCodingWorkspace =
    awaitingAnswer && openKind === "coding";
  const statusLabel = interviewDone
    ? "Completed"
    : submit.isPending
      ? "Evaluating"
      : awaitingAnswer
        ? "Awaiting answer"
        : "In progress";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length, submit.isPending, lastEvaluation]);

  useEffect(() => {
    if (awaitingAnswer && !showCodingWorkspace) {
      composerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [openQuestion?.turn_index, awaitingAnswer, showCodingWorkspace]);

  const sendText = () => {
    const a = answer.trim();
    if (!a || submit.isPending || !awaitingAnswer || !openQuestion) return;
    submit.mutate({ answer: a, turnIndex: openQuestion.turn_index });
  };

  if (session.isLoading) {
    return (
      <div className="rounded-2xl border border-stone-200 bg-white px-5 py-10 text-center text-sm text-stone-500">
        Loading session…
      </div>
    );
  }

  return (
    <div
      className={`mx-auto space-y-4 ${showCodingWorkspace ? "max-w-6xl" : "max-w-3xl"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-indigo-600">
            {session.data?.session.mode} interview
          </p>
          <h1 className="text-xl font-semibold tracking-tight">Interview session</h1>
          <p className="mt-0.5 text-sm text-stone-500">
            {showCodingWorkspace
              ? "Write your own solution, then submit for evaluation."
              : "Answer one question at a time. Feedback appears after you submit."}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div
            className="min-w-[9.5rem] rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-2 text-right"
            aria-label={`Question progress ${currentIndex} of ${maxTurns}`}
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-indigo-500">
              Progress
            </p>
            <p className="text-lg font-semibold tabular-nums text-indigo-950">
              {interviewDone ? answeredCount : currentIndex || answeredCount}
              <span className="text-sm font-medium text-indigo-400">
                /{maxTurns}
              </span>
            </p>
            <p className="mt-0.5 text-[11px] font-medium text-indigo-700">
              Status: {statusLabel}
            </p>
          </div>
          {!interviewDone && (
            <button
              type="button"
              data-testid="finish-assessment-exit"
              onClick={() => setConfirmExit(true)}
              disabled={submit.isPending || finishEarly.isPending}
              className="rounded-xl border border-rose-200 bg-white px-3 py-2 text-sm font-semibold text-rose-700 shadow-sm hover:bg-rose-50 disabled:opacity-40"
            >
              Finish Assessment & Exit
            </button>
          )}
        </div>
      </div>

      {confirmExit && !interviewDone && (
        <div
          className="rounded-2xl border border-rose-200 bg-rose-50 p-4 shadow-sm sm:p-5"
          role="dialog"
          aria-labelledby="finish-exit-title"
          data-testid="finish-exit-confirm"
        >
          <p id="finish-exit-title" className="text-sm font-semibold text-rose-950">
            Finish Assessment & Exit
          </p>
          <p className="mt-2 text-sm leading-relaxed text-rose-900/90">
            Are you sure you want to finish this assessment and exit? Your
            submitted answers will be evaluated and your final feedback report
            will be generated.
          </p>
          {answeredCount === 0 && (
            <p className="mt-2 text-xs text-rose-800">
              You have not submitted any answers yet. The report will note that
              no questions were answered.
            </p>
          )}
          {finishEarly.isError && (
            <p className="mt-2 text-sm text-red-700">
              {finishEarly.error instanceof Error
                ? finishEarly.error.message
                : "Could not finish the assessment. Try again."}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              data-testid="confirm-finish-exit"
              disabled={submit.isPending || finishEarly.isPending}
              onClick={() => finishEarly.mutate()}
              className="rounded-xl bg-rose-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-rose-800 disabled:opacity-40"
            >
              {finishEarly.isPending
                ? "Finishing…"
                : submit.isPending
                  ? "Wait for evaluation…"
                  : "Yes, finish & exit"}
            </button>
            <button
              type="button"
              onClick={() => setConfirmExit(false)}
              disabled={finishEarly.isPending}
              className="rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
            >
              Keep answering
            </button>
          </div>
        </div>
      )}

      {/* Transcript — scrollable; composer stays outside so Submit is always reachable */}
      <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
        <div className="border-b border-stone-100 bg-stone-50/80 px-4 py-2.5 sm:px-5">
          <p className="text-xs font-medium text-stone-500">Transcript</p>
        </div>
        <div className="max-h-[min(50vh,28rem)] space-y-5 overflow-y-auto px-4 py-5 sm:px-5">
          {turns.map((t) => {
            const evaluation = t.evaluation ?? undefined;
            const isOpen = t.answer === null && !interviewDone;
            const kind = classifyQuestion(t.question_area, t.question);
            return (
              <div key={t.turn_index} className="space-y-2">
                <div
                  className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    isOpen
                      ? "border border-indigo-200 bg-indigo-50/60 ring-1 ring-indigo-100"
                      : "bg-stone-100 text-stone-800"
                  }`}
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-white px-2 py-0.5 text-[11px] font-semibold tabular-nums text-indigo-700 ring-1 ring-indigo-100">
                      Q{t.turn_index}/{maxTurns}
                    </span>
                    <span className="rounded-md bg-white/80 px-2 py-0.5 text-[11px] font-medium text-stone-500">
                      {t.question_area}
                    </span>
                    {kind === "coding" && (
                      <span className="rounded-md bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-violet-700">
                        Coding
                      </span>
                    )}
                    {isOpen && (
                      <span className="rounded-md bg-indigo-600 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
                        Current
                      </span>
                    )}
                  </div>
                  {t.question}
                </div>
                {t.answer !== null && (
                  <div className="ml-auto max-w-[92%] rounded-2xl bg-indigo-600 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-white">
                    {t.answer}
                  </div>
                )}
                {/* Strict mode: zero live feedback — everything lands in the
                    report (product rule, M9). Guided shows chips live. */}
                {isGuided && evaluation && (
                  <div className="ml-auto max-w-[92%]">
                    <EvaluationFeedback
                      evaluation={evaluation}
                      questionIndex={t.turn_index}
                      compact
                    />
                  </div>
                )}
              </div>
            );
          })}
          {submit.isPending && (
            <div className="rounded-2xl border border-dashed border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
              {isGuided
                ? "Evaluating your answer… please wait. Submit is disabled until this finishes."
                : "Recording your answer…"}
            </div>
          )}
          {submit.isError && (
            <p className="text-sm text-red-600">
              {submit.error instanceof Error
                ? submit.error.message
                : "Submission failed. Try again."}
            </p>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {showCodingWorkspace && openQuestion && (
        <CodingWorkspace
          key={openQuestion.turn_index}
          question={openQuestion.question}
          questionArea={openQuestion.question_area}
          turnIndex={openQuestion.turn_index}
          maxTurns={maxTurns}
          isGuided={isGuided}
          assistanceLevel={openAssistanceLevel}
          maxAssistanceLevel={assistMaxLevel}
          latestHelp={latestHint}
          assistError={
            assist.error instanceof Error ? assist.error.message : null
          }
          assistPending={assist.isPending}
          submitPending={submit.isPending}
          submitError={
            submit.error instanceof Error ? submit.error.message : null
          }
          leaveHref={`/tracks/${trackId}`}
          onAssist={() => assist.mutate()}
          onSubmit={(payload) =>
            submit.mutate({
              answer: payload,
              turnIndex: openQuestion.turn_index,
            })
          }
        />
      )}

      {!showCodingWorkspace && latestHint && (
        <div
          className="rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950"
          data-testid="assistance-panel"
        >
          <p className="text-xs font-medium uppercase tracking-wide text-sky-700">
            {latestHint.assistance_type} · level {latestHint.level}
          </p>
          <p className="mt-2 whitespace-pre-wrap leading-relaxed">
            {latestHint.content}
          </p>
        </div>
      )}

      {!showCodingWorkspace && assist.error instanceof Error && (
        <p className="text-sm text-red-600">{assist.error.message}</p>
      )}

      {interviewDone ? (
        <div
          className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm"
          data-testid="interview-complete"
        >
          <p className="text-base font-semibold text-indigo-950">
            Interview completed.
          </p>
          <p className="mt-1 text-sm text-indigo-900/80">
            You finished the question set ({answeredCount}/{maxTurns}). Feedback
            is pending — the report is generated asynchronously.
          </p>
          {isGuided && lastEvaluation && (
            <div className="mt-4">
              <EvaluationFeedback
                evaluation={lastEvaluation.evaluation}
                questionIndex={lastEvaluation.turnIndex}
              />
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={`/tracks/${trackId}/report/${sessionId}`}
              data-testid="finish-interview"
              className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-bold text-white hover:bg-indigo-700"
            >
              Finish Interview
            </Link>
            <Link
              to={`/tracks/${trackId}`}
              className="rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-medium text-stone-700 hover:bg-stone-50"
            >
              Back to track
            </Link>
          </div>
        </div>
      ) : awaitingAnswer && !showCodingWorkspace ? (
        <div
          ref={composerRef}
          data-testid="answer-composer"
          className="sticky bottom-3 z-10 rounded-2xl border border-indigo-200 bg-white p-4 shadow-lg ring-1 ring-indigo-100 sm:p-5"
        >
          <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-stone-500">
            Your answer · Q{openQuestion!.turn_index}/{maxTurns}
          </label>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={4}
            placeholder={
              isGuided
                ? "Type your answer… (optional hints available)"
                : "Type your answer… (no hints in strict mode!)"
            }
            className="w-full resize-y rounded-xl border border-stone-200 px-4 py-3 text-sm leading-relaxed outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
            disabled={submit.isPending}
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={sendText}
              disabled={submit.isPending || !answer.trim()}
              data-testid="submit-answer"
              className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
            >
              {submit.isPending ? "Evaluating…" : "Submit Answer"}
            </button>
            {isGuided && (
              <button
                type="button"
                onClick={() => assist.mutate()}
                disabled={!canAssist || assist.isPending || submit.isPending}
                className="rounded-xl border border-sky-300 bg-white px-4 py-2.5 text-sm font-medium text-sky-800 hover:bg-sky-50 disabled:opacity-40"
              >
                {assist.isPending
                  ? "Getting help…"
                  : openAssistanceLevel >= assistMaxLevel
                    ? "No more assistance for this question"
                    : openAssistanceLevel === 0
                      ? "Get a nudge"
                      : openAssistanceLevel === 1
                        ? "Get a clue"
                        : "Get an explanation"}
              </button>
            )}
            <Link
              to={`/tracks/${trackId}`}
              className="ml-auto text-sm text-stone-500 hover:text-indigo-600 hover:underline"
            >
              Leave session
            </Link>
          </div>
        </div>
      ) : !interviewDone && !showCodingWorkspace ? (
        <div className="rounded-2xl border border-dashed border-stone-200 bg-stone-50 px-4 py-6 text-center text-sm text-stone-500">
          Preparing the next question…
          <button
            type="button"
            className="mt-2 block w-full text-indigo-600 hover:underline"
            onClick={() => void session.refetch()}
          >
            Refresh
          </button>
        </div>
      ) : null}

      {awaitingAnswer && showCodingWorkspace && (
        <div className="flex justify-end">
          <Link
            to={`/tracks/${trackId}`}
            className="text-sm text-stone-500 hover:text-indigo-600 hover:underline"
          >
            Leave session
          </Link>
        </div>
      )}
    </div>
  );
}
