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
import { requestLeave, setLeaveGuard } from "../lib/leaveGuard";
import { isCodeFriendly, resolveKind } from "../lib/questionKind";

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
  const [codeDirty, setCodeDirty] = useState(false);
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
  /** Which turn is on screen; null = follow the live open question. */
  const [viewTurnIndex, setViewTurnIndex] = useState<number | null>(null);

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api<SessionPayload>(`/sessions/${sessionId}`),
  });

  // Ticking clock for the timed-interview display (M9.2).
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 30000);
    return () => clearInterval(t);
  }, []);

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
      // Stay on this question so feedback + Next are visible (one screen at a time).
      setViewTurnIndex(vars.turnIndex);
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
  const guardActive = !!session.data && !interviewDone;
  const finishRef = useRef(finishEarly.mutateAsync);

  useEffect(() => {
    finishRef.current = finishEarly.mutateAsync;
    if (!guardActive) {
      setLeaveGuard(null);
      return;
    }
    setLeaveGuard({
      active: true,
      dirty: answer.trim().length > 0 || codeDirty,
      timed: (session.data?.session.duration_minutes ?? 0) > 0,
      finish: () => finishRef.current().then(() => undefined),
    });
  }, [guardActive, answer, codeDirty, session.data?.session.duration_minutes, finishEarly.mutateAsync]);

  useEffect(() => () => setLeaveGuard(null), []);

  const leaveSession = (source: HTMLElement) => {
    const href = `/tracks/${trackId}`;
    if (!requestLeave({ kind: "href", href, focus: source })) navigate(href);
  };
  const isGuided = session.data?.session.mode === "guided";
  const openQuestion = [...turns].reverse().find((t) => t.answer === null);
  const maxTurns = session.data?.session.max_turns ?? DEFAULT_MAX_TURNS;
  const answeredCount = turns.filter((t) => t.answer !== null).length;

  const focusIndex =
    viewTurnIndex ??
    openQuestion?.turn_index ??
    turns[turns.length - 1]?.turn_index ??
    1;
  const focusTurn =
    turns.find((t) => t.turn_index === focusIndex) ?? openQuestion ?? null;

  const awaitingAnswer =
    !interviewDone && !!focusTurn && focusTurn.answer === null;
  const openAssistanceLevel = focusTurn?.assistance_level ?? 0;
  const focusKind = focusTurn ? resolveKind(focusTurn) : "text";
  const assistMaxLevel =
    reportedMaxLevel ?? (focusKind === "coding" ? 5 : 3);
  const canAssist =
    isGuided &&
    awaitingAnswer &&
    openAssistanceLevel < assistMaxLevel &&
    !submit.isPending;
  const showCodingWorkspace = awaitingAnswer && focusKind === "coding";

  const focusEvaluation =
    focusTurn?.evaluation ??
    (lastEvaluation && lastEvaluation.turnIndex === focusTurn?.turn_index
      ? lastEvaluation.evaluation
      : undefined);
  const showFeedback = !!focusTurn && focusTurn.answer !== null && !!focusEvaluation;

  const progressNum = interviewDone
    ? answeredCount
    : (openQuestion?.turn_index ?? (answeredCount || focusIndex));
  const statusLabel = interviewDone
    ? "Completed"
    : submit.isPending
      ? "Evaluating"
      : awaitingAnswer
        ? "Awaiting answer"
        : showFeedback
          ? "Feedback ready"
          : "In progress";

  const canGoNext =
    !!focusTurn &&
    focusTurn.answer !== null &&
    !submit.isPending &&
    (interviewDone || !!openQuestion);

  const sendText = () => {
    const a = answer.trim();
    if (!a || submit.isPending || !awaitingAnswer || !focusTurn) return;
    submit.mutate({ answer: a, turnIndex: focusTurn.turn_index });
  };

  const goNext = () => {
    if (interviewDone) {
      navigate(`/tracks/${trackId}/report/${sessionId}`);
      return;
    }
    if (openQuestion) {
      setViewTurnIndex(openQuestion.turn_index);
      setAnswer("");
      setLatestHint(null);
    }
  };

  if (session.isLoading) {
    return (
      <div className="grid flex-1 place-items-center px-4 text-sm text-stone-500">
        Loading session…
      </div>
    );
  }

  return (
    <div
      className="mx-auto flex min-h-0 w-full min-w-0 max-w-[1100px] flex-1 flex-col overflow-x-hidden px-3 py-3 sm:px-6 sm:py-4"
      data-testid="interview-session"
    >
      {/* Top bar: title + progress + exit */}
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-indigo-600">
            {session.data?.session.mode} interview
          </p>
          <h1 className="text-lg font-semibold tracking-tight sm:text-xl">
            Interview session
          </h1>
          {session.data?.session.practice_label && (
            <p
              className="mt-1 max-w-full text-xs font-medium text-amber-800"
              data-testid="practice-label"
            >
              {session.data.session.practice_label}
            </p>
          )}
          <p className="mt-0.5 hidden text-sm text-stone-500 sm:block">
            {showCodingWorkspace
              ? "Write your own solution, then submit for evaluation."
              : isGuided
                ? "Answer one question at a time — live feedback is on."
                : "Answer one question at a time. Your full evaluation arrives in the final report."}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <div
            className="rounded-xl border border-indigo-100 bg-indigo-50 px-3 py-1.5 text-right sm:min-w-[9rem] sm:py-2"
            aria-label={`Question progress ${progressNum} of ${maxTurns}`}
          >
            <p className="text-[10px] font-medium uppercase tracking-wide text-indigo-500">
              Progress
            </p>
            <p className="text-base font-semibold tabular-nums text-indigo-950 sm:text-lg">
              {progressNum}
              <span className="text-sm font-medium text-indigo-400">
                /{maxTurns}
              </span>
            </p>
            <p className="text-[11px] font-medium text-indigo-700">
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
              <span className="sm:hidden">Finish & Exit</span>
              <span className="hidden sm:inline">Finish Assessment & Exit</span>
            </button>
          )}
        </div>
      </div>

      {/* Question stepper */}
      <nav
        className="mt-3 -mx-1 flex min-w-0 w-full shrink-0 gap-1 overflow-x-auto overscroll-x-contain px-1 pb-1"
        aria-label="Question stepper"
      >
        {Array.from({ length: maxTurns }, (_, i) => {
          const n = i + 1;
          const turn = turns.find((t) => t.turn_index === n);
          const answered = !!turn && turn.answer !== null;
          const isCurrent = n === focusIndex;
          const reachable = answered || turn?.answer === null;
          return (
            <button
              key={n}
              type="button"
              disabled={!reachable}
              onClick={() => reachable && setViewTurnIndex(n)}
              aria-current={isCurrent ? "step" : undefined}
              className={`h-7 w-7 shrink-0 rounded-lg text-[11px] font-semibold tabular-nums transition sm:h-8 sm:w-8 sm:text-xs ${
                isCurrent
                  ? "bg-indigo-600 text-white"
                  : answered
                    ? "bg-indigo-100 text-indigo-800 hover:bg-indigo-200"
                    : "bg-stone-100 text-stone-400"
              } disabled:cursor-default disabled:opacity-50`}
            >
              {n}
            </button>
          );
        })}
      </nav>

      {confirmExit && !interviewDone && (
        <div
          className="mt-3 shrink-0 rounded-2xl border border-rose-200 bg-rose-50 p-4 shadow-sm sm:p-5"
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

      {/* Main content fills remaining height */}
      <div className="mt-3 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {showCodingWorkspace && focusTurn ? (
          <CodingWorkspace
            key={focusTurn.turn_index}
            question={focusTurn.question}
            questionArea={focusTurn.question_area}
            turnIndex={focusTurn.turn_index}
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
            onLeave={leaveSession}
            onDraftChange={setCodeDirty}
            onAssist={() => assist.mutate()}
            onSubmit={(payload) =>
              submit.mutate({
                answer: payload,
                turnIndex: focusTurn.turn_index,
              })
            }
          />
        ) : focusTurn ? (
          <>
            <section className="shrink-0 rounded-2xl border border-indigo-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-indigo-700 ring-1 ring-indigo-100">
                  Q{focusTurn.turn_index}/{maxTurns}
                </span>
                <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600">
                  {focusTurn.question_area}
                </span>
                {focusKind === "coding" && (
                  <span className="rounded-md bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-violet-700">
                    Coding
                  </span>
                )}
                {awaitingAnswer && (
                  <span className="rounded-md bg-indigo-600 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-white">
                    Current
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-stone-900 sm:text-[15px]">
                {focusTurn.question}
              </p>
            </section>

            {focusTurn.answer !== null && (
              <section className="shrink-0 rounded-2xl bg-indigo-600 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-white sm:px-5">
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-indigo-200">
                  Your answer
                </p>
                {focusTurn.answer}
              </section>
            )}

            {submit.isPending && (
              <div className="rounded-2xl border border-dashed border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800">
                Evaluating your answer… please wait.
              </div>
            )}

            {showFeedback && focusEvaluation && (
              <EvaluationFeedback
                evaluation={focusEvaluation}
                questionIndex={focusTurn.turn_index}
                coding={focusKind === "coding"}
              />
            )}
            {isGuided && showFeedback && focusTurn.explanation && (
              <p className="rounded-xl bg-indigo-50 px-3 py-2 text-sm text-indigo-950" data-testid="mcq-explanation">
                {focusTurn.explanation}
              </p>
            )}

            {interviewDone && showFeedback && (
              <div
                className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-white p-4 shadow-sm"
                data-testid="interview-complete"
              >
                <p className="text-base font-semibold text-indigo-950">
                  Interview completed.
                </p>
                <p className="mt-1 text-sm text-indigo-900/80">
                  You finished the question set ({answeredCount}/{maxTurns}).
                  Feedback is pending — the report is generated asynchronously.
                </p>
              </div>
            )}

            {!showCodingWorkspace && latestHint && awaitingAnswer && (
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

            {awaitingAnswer && focusTurn.question_type === "mcq" && (
              <McqOptions
                options={focusTurn.options ?? []}
                selected={answer}
                onSelect={setAnswer}
                disabled={submit.isPending}
              />
            )}

            {awaitingAnswer && focusTurn.question_type === "numeric" && (
              <label className="flex min-w-0 items-center gap-2 rounded-2xl border border-indigo-200 bg-white p-3">
                <input
                  data-testid="numeric-answer"
                  inputMode="decimal"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  disabled={submit.isPending}
                  className="min-w-0 flex-1 rounded-xl border border-stone-200 px-4 py-3 text-sm outline-none focus:border-indigo-400"
                />
                {focusTurn.unit && (
                  <span data-testid="numeric-unit" className="shrink-0 text-sm text-stone-500">
                    {focusTurn.unit}
                  </span>
                )}
              </label>
            )}

            {awaitingAnswer &&
              focusTurn.question_type !== "mcq" &&
              focusTurn.question_type !== "numeric" && (
              <div
                data-testid="answer-composer"
                className="flex min-h-[40vh] flex-1 flex-col rounded-2xl border border-indigo-200 bg-white p-3 shadow-sm sm:min-h-0 sm:p-4"
              >
                {focusTurn.scenario && (
                  <p
                    data-testid="case-scenario"
                    className="mb-3 whitespace-pre-wrap rounded-xl bg-amber-50 p-3 text-sm leading-relaxed text-amber-950"
                  >
                    {focusTurn.scenario}
                  </p>
                )}
                {focusTurn.code_snippet && (
                  <pre
                    data-testid="code-snippet"
                    className="mb-3 max-w-full overflow-x-auto rounded-xl bg-stone-900 p-3 font-mono text-xs leading-relaxed text-stone-100"
                  >
                    {focusTurn.code_snippet}
                  </pre>
                )}
                <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-stone-500">
                  Your answer · Q{focusTurn.turn_index}/{maxTurns}
                </label>
                {isCodeFriendly(focusTurn.question_type) && (
                  <label className="mb-2 flex items-center gap-2 text-xs text-stone-500">
                    Language
                    <select
                      data-testid="answer-language"
                      className="rounded-lg border border-stone-200 bg-white px-2 py-1"
                      defaultValue="python"
                    >
                      <option value="python">Python</option>
                      <option value="java">Java</option>
                      <option value="c">C</option>
                    </select>
                  </label>
                )}
                <textarea
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  onKeyDown={(e) => {
                    if (!isCodeFriendly(focusTurn.question_type)) return;
                    if (e.key === "Tab") {
                      e.preventDefault();
                      const el = e.currentTarget;
                      const start = el.selectionStart ?? answer.length;
                      const next = `${answer.slice(0, start)}  ${answer.slice(el.selectionEnd ?? start)}`;
                      setAnswer(next);
                    }
                  }}
                  placeholder={
                    isGuided
                      ? "Type your answer… (optional hints available)"
                      : "Type your answer… (no hints in strict mode!)"
                  }
                  className={`min-h-[40vh] w-full flex-1 resize-none rounded-xl border border-stone-200 px-4 py-3 text-sm leading-relaxed outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 sm:min-h-[12rem] ${
                    isCodeFriendly(focusTurn.question_type) ? "font-mono" : ""
                  }`}
                  disabled={submit.isPending}
                />
              </div>
            )}

            {submit.isError && (
              <p className="text-sm text-red-600">
                {submit.error instanceof Error
                  ? submit.error.message
                  : "Submission failed. Try again."}
              </p>
            )}
            {!showCodingWorkspace && assist.error instanceof Error && (
              <p className="text-sm text-red-600">{assist.error.message}</p>
            )}
          </>
        ) : (
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
        )}
      </div>

      {/* Sticky action bar */}
      {!showCodingWorkspace && (
        <div className="mt-3 flex shrink-0 flex-col gap-2 border-t border-stone-200/80 bg-[#f6f4fb] pt-3 sm:flex-row sm:flex-wrap sm:items-center">
          {awaitingAnswer && (
            <>
              <button
                type="button"
                onClick={sendText}
                disabled={submit.isPending || !answer.trim()}
                data-testid="submit-answer"
                className="w-full rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40 sm:w-auto"
              >
                {submit.isPending ? "Evaluating…" : "Submit Answer"}
              </button>
              {isGuided && (
                <button
                  type="button"
                  onClick={() => assist.mutate()}
                  disabled={!canAssist || assist.isPending || submit.isPending}
                  className="w-full rounded-xl border border-sky-300 bg-white px-4 py-2.5 text-sm font-medium text-sky-800 hover:bg-sky-50 disabled:opacity-40 sm:w-auto"
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
            </>
          )}

          {canGoNext && (
            <button
              type="button"
              data-testid={interviewDone ? "finish-interview" : "next-question"}
              onClick={goNext}
              className="w-full rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 sm:w-auto"
            >
              {interviewDone ? "View report" : "Next question"}
            </button>
          )}

          {interviewDone && !canGoNext && (
            <Link
              to={`/tracks/${trackId}/report/${sessionId}`}
              data-testid="finish-interview"
              className="inline-flex w-full justify-center rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white hover:bg-indigo-700 sm:w-auto"
            >
              View report
            </Link>
          )}

          <button
            type="button"
            onClick={(event) => leaveSession(event.currentTarget)}
            className="text-center text-sm text-stone-500 hover:text-indigo-600 hover:underline sm:ml-auto"
          >
            Leave session
          </button>
        </div>
      )}
    </div>
  );
}

function McqOptions({
  options,
  selected,
  onSelect,
  disabled,
}: {
  options: string[];
  selected: string;
  onSelect: (value: string) => void;
  disabled: boolean;
}) {
  const move = (delta: number, from: number) => {
    const current = selected === "" ? from : Number(selected);
    const next = (current + delta + options.length) % options.length;
    onSelect(String(next));
  };
  return (
    <div
      role="radiogroup"
      aria-label="Answer options"
      data-testid="mcq-options"
      tabIndex={0}
      className="grid gap-2 outline-none"
      onKeyDown={(e) => {
        if (disabled || options.length === 0) return;
        const raw = (e.target as HTMLInputElement).value;
        const from = raw === undefined || raw === "" ? -1 : Number(raw);
        if (e.key === "ArrowDown" || e.key === "ArrowRight") {
          e.preventDefault();
          move(1, Number.isNaN(from) ? -1 : from);
        } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
          e.preventDefault();
          move(-1, Number.isNaN(from) ? 0 : from);
        }
      }}
    >
      {options.map((option, index) => {
        const value = String(index);
        const checked = selected === value;
        return (
          <label
            key={option}
            data-testid={`mcq-option-${index}`}
            className={`flex cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${
              checked ? "border-indigo-400 bg-indigo-50" : "border-stone-200 bg-white"
            }`}
          >
            <input
              type="radio"
              name="mcq"
              value={value}
              checked={checked}
              disabled={disabled}
              onChange={() => onSelect(value)}
              className="mt-1"
            />
            <span>{option}</span>
          </label>
        );
      })}
    </div>
  );
}
