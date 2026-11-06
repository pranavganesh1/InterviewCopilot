# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\interviewViewport.spec.ts >> viewport 375px: one question, next, finish
- Location: frontend\e2e\interviewViewport.spec.ts:67:3

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/tracks/t1/interview/s1", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  |
  3  | const USER = { id: "u1", email: "s@example.com", name: "S", picture_url: null };
  4  |
  5  | async function mockInterview(page: import("@playwright/test").Page) {
  6  |   const turns = [
  7  |     {
  8  |       turn_index: 1,
  9  |       question_area: "Array Basics",
  10 |       question: "What is an array and how is it stored contiguously?",
  11 |       answer: null as string | null,
  12 |       evaluation: null as Record<string, unknown> | null,
  13 |     },
  14 |   ];
  15 |   await page.route("**/api/v1/auth/me", (r) => r.fulfill({ json: USER }));
  16 |   await page.route("**/api/v1/auth/logout", (r) =>
  17 |     r.fulfill({ json: { status: "ok" } }),
  18 |   );
  19 |   await page.route("**/api/v1/sessions/s1", (r) =>
  20 |     r.fulfill({
  21 |       json: {
  22 |         session: {
  23 |           id: "s1",
  24 |           track_id: "t1",
  25 |           mode: "strict",
  26 |           status: "in_progress",
  27 |           max_turns: 15,
  28 |         },
  29 |         turns,
  30 |       },
  31 |     }),
  32 |   );
  33 |   await page.route("**/api/v1/sessions/s1/turns", async (r) => {
  34 |     turns[0].answer = "Contiguous memory.";
  35 |     turns[0].evaluation = { coverage: "good", strengths: ["ok"], gaps: [] };
  36 |     turns.push({
  37 |       turn_index: 2,
  38 |       question_area: "Two Pointers",
  39 |       question: "Explain two pointers.",
  40 |       answer: null,
  41 |       evaluation: null,
  42 |     });
  43 |     await r.fulfill({
  44 |       json: {
  45 |         completed: false,
  46 |         evaluation: turns[0].evaluation,
  47 |         turn: turns[1],
  48 |       },
  49 |     });
  50 |   });
  51 |   await page.route("**/api/v1/sessions/s1/complete", (r) =>
  52 |     r.fulfill({
  53 |       json: {
  54 |         session: {
  55 |           id: "s1",
  56 |           track_id: "t1",
  57 |           mode: "strict",
  58 |           status: "completed",
  59 |           max_turns: 15,
  60 |         },
  61 |       },
  62 |     }),
  63 |   );
  64 | }
  65 |
  66 | for (const width of [375, 768, 1440] as const) {
  67 |   test(`viewport ${width}px: one question, next, finish`, async ({ page }) => {
  68 |     await page.setViewportSize({ width, height: 800 });
  69 |     await mockInterview(page);
> 70 |     await page.goto("/tracks/t1/interview/s1");
     |                ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  71 |     await expect(page.getByText("What is an array")).toBeVisible();
  72 |     await expect(page.getByText("Explain two pointers")).toHaveCount(0);
  73 |     // No page-level horizontal scroll (inner stepper may overflow with overflow-x-auto).
  74 |     const noPageHScroll = await page.evaluate(() => {
  75 |       const root = document.documentElement;
  76 |       const before = root.scrollLeft;
  77 |       root.scrollLeft = 200;
  78 |       const moved = root.scrollLeft !== before;
  79 |       root.scrollLeft = before;
  80 |       const session = document.querySelector("[data-testid='interview-session']");
  81 |       const fits =
  82 |         !session ||
  83 |         session.getBoundingClientRect().right <= window.innerWidth + 1;
  84 |       return !moved && fits;
  85 |     });
  86 |     expect(noPageHScroll).toBeTruthy();
  87 |     await page.fill("textarea", "Contiguous memory.");
  88 |     await page.getByTestId("submit-answer").click();
  89 |     await expect(page.getByTestId("evaluation-feedback")).toBeVisible();
  90 |     await expect(page.getByTestId("next-question")).toBeVisible();
  91 |     await page.getByTestId("next-question").click();
  92 |     await expect(page.getByText("Explain two pointers.")).toBeVisible();
  93 |     await page.getByTestId("finish-assessment-exit").click();
  94 |     await expect(page.getByTestId("finish-exit-confirm")).toBeVisible();
  95 |   });
  96 | }
  97 |
```
