/** Classify interview questions using existing turn metadata (area + text). */

export type QuestionKind = "coding" | "text";

const CODING_AREA =
  /\b(dsa|algorithm|algorithms|coding|programming|code|leetcode|data.?struct|arrays?|strings?|linked.?list|tree|graph|dp|dynamic.?programming|recursion|sorting|searching|complexity|big.?o|hashmap|hash.?table|heap|stack|queue|binary.?search|two.?pointer|bit.?manip|system.?design.?code|implementation)\b/i;

const CODING_QUESTION =
  /\b(write (a |the )?(function|method|program|code|class)|implement|code (this|a|the)|pseudocode|time complexity|space complexity|return the|given an? array|given a string|leetcode|compile|runtime|input:|output:|constraints?:|example\s*\d|def\s+\w+\(|public\s+static|int\s+main)\b/i;

const TEXT_OVERRIDE =
  /\b(tell me about|describe (a time|yourself|your)|why (do you|should)|behavioral|soft skill|leadership|conflict|weakness|strength|motivate|culture|teamwork|internship experience|career goal)\b/i;

const CONCEPTUAL_QUESTION =
  /^(explain|describe|what is|what are|compare|discuss|how would you (approach|design|think)|walk me through(?! (writing|implementing|coding)))\b/i;

/**
 * Prefer text when unsure. Only treat as coding when the question clearly
 * asks for implementation — not every DSA topic discussion.
 */
export function classifyQuestion(area: string, question: string): QuestionKind {
  const a = area ?? "";
  const q = (question ?? "").trim();
  if (TEXT_OVERRIDE.test(a) || TEXT_OVERRIDE.test(q)) return "text";
  if (CONCEPTUAL_QUESTION.test(q) && !CODING_QUESTION.test(q)) return "text";
  if (CODING_QUESTION.test(q)) return "coding";
  if (CODING_AREA.test(a) && /\b(write|implement|code|function|program)\b/i.test(q)) {
    return "coding";
  }
  return "text";
}

/**
 * Authoritative resolution (M9): the backend persists question_type from the
 * interviewer/bank. The keyword heuristic is only a fallback for legacy
 * turns created before question_type existed.
 */
export function resolveKind(turn: {
  question_type?: string | null;
  question_area?: string | null;
  question: string;
}): QuestionKind {
  if (turn.question_type === "coding") return "coding";
  if (
    turn.question_type === "conceptual" ||
    turn.question_type === "behavioral" ||
    turn.question_type === "mcq" ||
    turn.question_type === "code_read" ||
    turn.question_type === "case_study" ||
    turn.question_type === "numeric"
  ) {
    return "text";
  }
  return classifyQuestion(turn.question_area ?? "", turn.question);
}

/** Monospace answer box for questions whose answer is code or about code. */
export function isCodeFriendly(questionType?: string | null): boolean {
  return questionType === "code_read" || questionType === "coding";
}

export function parseProblemSections(question: string): {
  statement: string;
  constraints: string | null;
  examples: string | null;
} {
  const text = question.trim();
  const constraintsMatch = text.match(
    /(?:^|\n)\s*constraints?\s*[:\-–]?\s*([\s\S]*?)(?=\n\s*examples?\s*[:\-–]|\n\s*example\s*\d|$)/i,
  );
  const examplesMatch = text.match(
    /(?:^|\n)\s*examples?\s*[:\-–]?\s*([\s\S]*)$/i,
  );
  let statement = text;
  if (constraintsMatch || examplesMatch) {
    const cut =
      constraintsMatch?.index ?? examplesMatch?.index ?? text.length;
    statement = text.slice(0, cut).trim();
  }
  return {
    statement: statement || text,
    constraints: constraintsMatch?.[1]?.trim() || null,
    examples: examplesMatch?.[1]?.trim() || null,
  };
}
