import { expect, test } from "@playwright/test";
import { resolveKind } from "../src/lib/questionKind";

/**
 * Fix 7: coding workspace detection must respect domain_profile.uses_code.
 * Pure unit checks via Playwright's TS runner (no shared backend / DB).
 */

test("domain profile uses_code=false blocks coding heuristics", () => {
  const kind = resolveKind(
    {
      question: "Implement a hash map collision strategy in code",
      question_area: "Arrays",
    },
    { uses_code: false, allowed_types: ["conceptual", "mcq"] },
  );
  expect(kind).toBe("text");
});

test("explicit coding type still opens workspace when uses_code is true", () => {
  expect(
    resolveKind(
      {
        question_type: "coding",
        question: "Write a function to reverse a linked list",
        question_area: "Linked Lists",
      },
      { uses_code: true, allowed_types: ["coding", "conceptual"] },
    ),
  ).toBe("coding");
});

test("explicit coding type is suppressed when domain forbids code", () => {
  expect(
    resolveKind(
      {
        question_type: "coding",
        question: "Write a function about enzymes",
        question_area: "Enzymes",
      },
      { uses_code: false, allowed_types: ["conceptual", "mcq"] },
    ),
  ).toBe("text");
});

test("legacy turns without type still use heuristics for CS tracks", () => {
  expect(
    resolveKind(
      {
        question: "Write a function that returns the max subarray sum",
        question_area: "Arrays",
      },
      { uses_code: true },
    ),
  ).toBe("coding");
});
