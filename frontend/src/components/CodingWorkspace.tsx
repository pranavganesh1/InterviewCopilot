import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import Editor from "@monaco-editor/react";
import {
  LANGUAGE_TABS,
  STARTER_CODE,
  formatCodeAnswer,
  type CodeLanguage,
} from "../lib/codeTemplates";
import { parseProblemSections } from "../lib/questionKind";
import type { AssistanceResult } from "../lib/api";

const CODING_HELP_LABELS: Record<number, string> = {
  0: "Get a hint",
  1: "Get the approach",
  2: "Get pseudocode",
  3: "Get starter code",
  4: "Get complete solution",
};

type Props = {
  question: string;
  questionArea: string;
  turnIndex: number;
  maxTurns: number;
  isGuided: boolean;
  assistanceLevel: number;
  maxAssistanceLevel: number;
  latestHelp: AssistanceResult["assistance"] | null;
  assistError: string | null;
  assistPending: boolean;
  submitPending: boolean;
  submitError: string | null;
  leaveHref: string;
  onAssist: () => void;
  onSubmit: (answer: string) => void;
};

export default function CodingWorkspace({
  question,
  questionArea,
  turnIndex,
  maxTurns,
  isGuided,
  assistanceLevel,
  maxAssistanceLevel,
  latestHelp,
  assistError,
  assistPending,
  submitPending,
  submitError,
  leaveHref,
  onAssist,
  onSubmit,
}: Props) {
  const [language, setLanguage] = useState<CodeLanguage>("python");
  const [codeByLang, setCodeByLang] = useState<Record<CodeLanguage, string>>(
    () => ({ ...STARTER_CODE }),
  );
  const [terminal, setTerminal] = useState(
    "Code execution is not available in this environment.\nRun is disabled until a secure sandbox is connected.\nYou can still edit code and Submit Answer for interview evaluation.",
  );

  const sections = useMemo(() => parseProblemSections(question), [question]);
  const code = codeByLang[language];
  const monacoLang =
    LANGUAGE_TABS.find((t) => t.id === language)?.monaco ?? "python";
  const canAssist =
    isGuided &&
    assistanceLevel < maxAssistanceLevel &&
    !submitPending &&
    !assistPending;

  const resetCode = () => {
    setCodeByLang((prev) => ({ ...prev, [language]: STARTER_CODE[language] }));
    setTerminal(`Reset ${language} starter template.`);
  };

  const runCode = () => {
    setTerminal(
      [
        "$ run",
        "Status: unavailable",
        "Reason: No secure code-execution sandbox is configured for InterviewCopilot.",
        "Nothing was executed. Output below is not a fake result — execution was blocked.",
      ].join("\n"),
    );
  };

  const submit = () => {
    const trimmed = code.trim();
    if (!trimmed || submitPending) return;
    onSubmit(formatCodeAnswer(language, code));
  };

  return (
    <div className="space-y-4" data-testid="coding-workspace">
      <section className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm sm:p-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold tabular-nums text-indigo-700 ring-1 ring-indigo-100">
            Q{turnIndex}/{maxTurns}
          </span>
          <span className="rounded-md bg-stone-100 px-2 py-0.5 text-[11px] font-medium text-stone-600">
            {questionArea}
          </span>
          <span className="rounded-md bg-violet-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-violet-700">
            Coding
          </span>
        </div>
        <h2 className="text-base font-semibold text-stone-900">Problem</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-stone-800">
          {sections.statement}
        </p>
        {sections.constraints && (
          <div className="mt-3 rounded-xl border border-amber-100 bg-amber-50/70 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-800">
              Constraints
            </p>
            <p className="mt-1 whitespace-pre-wrap text-xs text-amber-950">
              {sections.constraints}
            </p>
          </div>
        )}
        {sections.examples && (
          <div className="mt-3 rounded-xl border border-stone-100 bg-stone-50 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">
              Examples
            </p>
            <p className="mt-1 whitespace-pre-wrap font-mono text-xs text-stone-700">
              {sections.examples}
            </p>
          </div>
        )}
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.9fr)]">
        <section className="flex min-h-[28rem] flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
          <div className="flex flex-wrap items-center gap-1 border-b border-stone-100 bg-stone-50 px-2 py-2">
            {LANGUAGE_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setLanguage(tab.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  language === tab.id
                    ? "bg-indigo-600 text-white"
                    : "text-stone-600 hover:bg-white"
                }`}
              >
                {tab.label}
              </button>
            ))}
            <div className="ml-auto flex flex-wrap gap-2 px-1">
              <button
                type="button"
                onClick={runCode}
                disabled={submitPending}
                className="rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-50 disabled:opacity-40"
              >
                Run
              </button>
              <button
                type="button"
                onClick={resetCode}
                disabled={submitPending}
                className="rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 hover:bg-stone-50 disabled:opacity-40"
              >
                Reset
              </button>
            </div>
          </div>
          <div className="min-h-[22rem] flex-1 overflow-hidden">
            <Editor
              height="360px"
              defaultLanguage={monacoLang}
              language={monacoLang}
              value={code}
              onChange={(v: string | undefined) =>
                setCodeByLang((prev) => ({
                  ...prev,
                  [language]: v ?? "",
                }))
              }
              theme="vs"
              options={{
                fontSize: 13,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                automaticLayout: true,
                lineNumbers: "on",
                tabSize: 4,
                wordWrap: "on",
                padding: { top: 8 },
                readOnly: submitPending,
              }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-stone-100 bg-white px-3 py-3">
            <button
              type="button"
              onClick={submit}
              disabled={submitPending || !code.trim()}
              className="rounded-xl bg-indigo-600 px-6 py-3 text-sm font-bold text-white shadow-sm hover:bg-indigo-700 disabled:opacity-40"
            >
              {submitPending ? "Evaluating…" : "Submit Answer"}
            </button>
            {submitPending && (
              <span className="text-xs text-indigo-700">
                Waiting for AI evaluation…
              </span>
            )}
            {submitError && (
              <span className="text-xs text-red-600">{submitError}</span>
            )}
            <Link
              to={leaveHref}
              className="ml-auto text-sm text-stone-500 hover:text-indigo-600 hover:underline"
            >
              Leave session
            </Link>
          </div>
        </section>

        <div className="flex min-h-[28rem] flex-col gap-4">
          <section className="flex min-h-[12rem] flex-1 flex-col overflow-hidden rounded-2xl border border-stone-800 bg-stone-950 shadow-sm">
            <div className="flex items-center justify-between border-b border-stone-800 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                Output
              </p>
              <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-medium text-amber-300">
                execution unavailable
              </span>
            </div>
            <pre className="flex-1 overflow-auto px-3 py-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-emerald-300">
              {terminal}
            </pre>
          </section>

          <section
            className="rounded-2xl border border-indigo-100 bg-indigo-50/60 p-4 shadow-sm"
            data-testid="assistance-panel"
          >
            <h3 className="text-sm font-semibold text-indigo-950">Need Help?</h3>
            <p className="mt-1 text-xs leading-relaxed text-indigo-900/80">
              Progressive coaching for this problem. Full solutions are only
              revealed at the last step when you ask.
            </p>

            {!isGuided ? (
              <p className="mt-3 rounded-xl border border-stone-200 bg-white px-3 py-2 text-xs text-stone-600">
                Strict mode: no solutions before you submit. After Submit Answer,
                evaluation may include corrected code and complexity.
              </p>
            ) : (
              <>
                <ol className="mt-3 space-y-1 text-[11px] text-indigo-900/70">
                  <li>1 · Hint</li>
                  <li>2 · Approach</li>
                  <li>3 · Pseudocode</li>
                  <li>4 · Starter code</li>
                  <li>5 · Complete solution</li>
                </ol>
                <button
                  type="button"
                  onClick={onAssist}
                  disabled={!canAssist || assistPending}
                  className="mt-3 w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-40"
                >
                  {assistPending
                    ? "Getting help…"
                    : assistanceLevel >= maxAssistanceLevel
                      ? "All help levels used for this question"
                      : CODING_HELP_LABELS[assistanceLevel] ?? "Need Help?"}
                </button>
                <p className="mt-2 text-center text-[11px] text-indigo-700">
                  Level {assistanceLevel}/{maxAssistanceLevel}
                </p>
              </>
            )}

            {assistError && (
              <p className="mt-2 text-xs text-red-600">{assistError}</p>
            )}

            {latestHelp && (
              <div className="mt-3 max-h-56 overflow-auto rounded-xl border border-indigo-100 bg-white p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                  {latestHelp.assistance_type} · level {latestHelp.level}
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-stone-800">
                  {latestHelp.content}
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
