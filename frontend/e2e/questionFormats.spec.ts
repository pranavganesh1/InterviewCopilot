import { expect, test } from "@playwright/test";
import { isCodeFriendly, resolveKind } from "../src/lib/questionKind";

const USER = { id: "u1", email: "s@example.com", name: "S", picture_url: null };

test("code-related kinds stay out of the coding workspace", () => {
  expect(resolveKind({ question_type: "mcq", question: "Pick one" })).toBe("text");
  expect(resolveKind({ question_type: "code_read", question: "What prints?" })).toBe("text");
  expect(resolveKind({ question_type: "coding", question: "Write a function" })).toBe("coding");
  expect(isCodeFriendly("code_read")).toBe(true);
  expect(isCodeFriendly("conceptual")).toBe(false);
});

async function mockSession(
  page: import("@playwright/test").Page,
  turn: Record<string, unknown>,
  mode = "strict",
) {
  await page.route("**/api/v1/auth/me", (r) => r.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (r) => r.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/v1/sessions/s1", (r) =>
    r.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode,
          status: "in_progress",
          max_turns: 15,
        },
        turns: [turn],
      },
    }),
  );
}

test("mcq selects with the keyboard and submits the index", async ({ page }) => {
  let submitted = "";
  await mockSession(page, {
    turn_index: 1,
    question_area: "Hashing",
    question: "What is the average lookup cost of a hash map?",
    question_type: "mcq",
    options: ["O(1) average", "O(n) average", "O(log n) average", "O(n log n) average"],
    answer: null,
    evaluation: null,
  });
  await page.route("**/api/v1/sessions/s1/turns", async (r) => {
    submitted = JSON.parse(r.request().postData() || "{}").answer;
    await r.fulfill({
      json: {
        completed: false,
        evaluation: { coverage: "excellent", strengths: ["Selected the correct option."], gaps: [] },
        turn: {
          turn_index: 2,
          question_area: "Next",
          question: "What is a collision?",
          question_type: "conceptual",
          answer: null,
          evaluation: null,
        },
      },
    });
  });
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/tracks/t1/interview/s1");
  await page.getByTestId("mcq-option-0").locator("input").focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByTestId("mcq-option-1").locator("input")).toBeChecked();
  await page.getByTestId("submit-answer").click();
  await expect.poll(() => submitted).toBe("1");
  await expect(page.getByText("Good start")).toHaveCount(0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  );
  expect(overflow).toBe(true);
});

test("code_read shows the snippet and a text answer", async ({ page }) => {
  await mockSession(page, {
    turn_index: 1,
    question_area: "Lists",
    question: "What does this slice print?",
    question_type: "code_read",
    code_snippet: "xs = [1, 2]\nprint(xs[:5])",
    answer: null,
    evaluation: null,
  });
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByTestId("code-snippet")).toContainText("print(xs[:5])");
  await expect(page.getByTestId("answer-composer").locator("textarea")).toBeVisible();
  await expect(page.getByTestId("ai-reviewed-badge")).toHaveCount(0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  );
  expect(overflow).toBe(true);
});

test("coding opens the workspace with the review label", async ({ page }) => {
  await mockSession(page, {
    turn_index: 1,
    question_area: "Lists",
    question: "Write a function that returns the first item.",
    question_type: "coding",
    answer: null,
    evaluation: null,
  });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByTestId("ai-reviewed-badge")).toBeVisible();
});

test("numeric and case questions fit a narrow screen", async ({ page }) => {
  await mockSession(
    page,
    {
      turn_index: 1,
      question_area: "Circuits",
      question: "What is the voltage drop?",
      question_type: "numeric",
      unit: "V",
      answer: null,
      evaluation: null,
    },
    "guided",
  );
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByTestId("numeric-answer")).toBeVisible();
  await expect(page.getByTestId("numeric-unit")).toHaveText("V");
  await page.getByTestId("numeric-answer").fill("5");
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  );
  expect(overflow).toBe(true);
});

test("a high-risk session shows the practice label and the case", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (r) => r.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (r) => r.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/v1/sessions/s1", (r) =>
    r.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          max_turns: 15,
          practice_label: "Exam-practice only, not professional advice",
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Pharmacy",
            question: "What is the main counselling point?",
            question_type: "case_study",
            scenario: "A generic adult collects a new medicine and asks about drowsiness.",
            answer: null,
            evaluation: null,
          },
        ],
      },
    }),
  );
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByTestId("practice-label")).toContainText("not professional advice");
  await expect(page.getByTestId("case-scenario")).toContainText("generic adult");
  await expect(page.getByText("Good start")).toHaveCount(0);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  );
  expect(overflow).toBe(true);
});

test("strict shows no evaluation before submit", async ({ page }) => {
  await mockSession(page, {
    turn_index: 1,
    question_area: "Lists",
    question: "What happens if you slice a list past its end?",
    question_type: "conceptual",
    answer: null,
    evaluation: null,
  });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByText("Good start")).toHaveCount(0);
  await expect(page.getByText("That's right")).toHaveCount(0);
  await expect(page.getByText("Not quite")).toHaveCount(0);
  await expect(page.getByTestId("answer-composer")).toBeVisible();
});
