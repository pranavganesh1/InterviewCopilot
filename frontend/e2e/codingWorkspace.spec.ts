import { expect, test } from "@playwright/test";
import { classifyQuestion } from "../src/lib/questionKind";
import { formatCodeAnswer } from "../src/lib/codeTemplates";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

test.describe("question classification", () => {
  test("coding vs conceptual heuristics", () => {
    expect(
      classifyQuestion(
        "Arrays",
        "Write a function that returns two numbers that sum to target.",
      ),
    ).toBe("coding");
    expect(
      classifyQuestion("DSA", "Implement binary search on a sorted array."),
    ).toBe("coding");
    expect(
      classifyQuestion("Hashmaps", "Explain hash collisions."),
    ).toBe("text");
    expect(
      classifyQuestion(
        "Behavioral",
        "Tell me about a time you resolved a conflict on your team.",
      ),
    ).toBe("text");
    expect(
      classifyQuestion("System Design", "Describe CAP theorem trade-offs."),
    ).toBe("text");
  });

  test("formatCodeAnswer wraps language fence", () => {
    const out = formatCodeAnswer("python", "def solve():\n    return 1\n");
    expect(out).toContain("Language: Python");
    expect(out).toContain("```python");
    expect(out).toContain("def solve()");
  });
});

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
});

test("coding question shows workspace; text question keeps textarea", async ({
  page,
}) => {
  const codingTurns = [
    {
      turn_index: 1,
      question_area: "Arrays",
      question:
        "Write a function that finds two numbers in an array that sum to a target.\nConstraints:\n- 2 <= n <= 10^4\nExample 1:\nInput: [2,7,11], 9\nOutput: [0,1]",
      answer: null as string | null,
      evaluation: null,
      assistance_level: 0,
    },
  ];

  await page.route("**/api/v1/sessions/code1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "code1",
          track_id: "t1",
          mode: "guided",
          status: "in_progress",
        },
        turns: codingTurns,
      },
    }),
  );

  await page.goto("/tracks/t1/interview/code1");
  const workspace = page.getByTestId("coding-workspace");
  await expect(workspace).toBeVisible();
  await expect(workspace.getByRole("button", { name: "Python" })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "Java" })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "C" })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "Run" })).toBeVisible();
  await expect(workspace.getByRole("button", { name: "Submit Answer" })).toBeVisible();
  await expect(page.getByText(/execution unavailable/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Need Help?" })).toBeVisible();

  await workspace.getByRole("button", { name: "Run" }).click();
  await expect(page.getByText(/No secure code-execution sandbox/i)).toBeVisible();

  // Text / conceptual path still uses the classic answer box.
  await page.route("**/api/v1/sessions/text1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "text1",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Behavioral",
            question: "Tell me about a time you led a difficult project.",
            answer: null,
            evaluation: null,
          },
        ],
      },
    }),
  );
  await page.goto("/tracks/t1/interview/text1");
  await expect(page.getByTestId("coding-workspace")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Submit Answer" })).toBeVisible();
  await expect(
    page.getByPlaceholder(/no hints in strict mode/i),
  ).toBeVisible();
});

test("language tabs switch without leaving workspace", async ({ page }) => {
  await page.route("**/api/v1/sessions/code2", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "code2",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Algorithms",
            question: "Implement merge sort and discuss its time complexity.",
            answer: null,
            evaluation: null,
            assistance_level: 0,
          },
        ],
      },
    }),
  );
  await page.goto("/tracks/t1/interview/code2");
  const workspace = page.getByTestId("coding-workspace");
  await workspace.getByRole("button", { name: "Java" }).click();
  await expect(workspace.getByRole("button", { name: "Java" })).toHaveClass(
    /bg-indigo-600/,
  );
  await workspace.getByRole("button", { name: "C" }).click();
  await expect(workspace.getByRole("button", { name: "C" })).toHaveClass(
    /bg-indigo-600/,
  );
  await expect(
    page.getByText(/Strict mode: no solutions before you submit/i),
  ).toBeVisible();
});
