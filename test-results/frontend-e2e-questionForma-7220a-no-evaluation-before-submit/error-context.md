# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\questionFormats.spec.ts >> strict shows no evaluation before submit
- Location: frontend\e2e\questionFormats.spec.ts:177:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/tracks/t1/interview/s1", waiting until "load"

```

# Test source

```ts
  86  |     answer: null,
  87  |     evaluation: null,
  88  |   });
  89  |   await page.setViewportSize({ width: 375, height: 800 });
  90  |   await page.goto("/tracks/t1/interview/s1");
  91  |   await expect(page.getByTestId("code-snippet")).toContainText("print(xs[:5])");
  92  |   await expect(page.getByTestId("answer-composer").locator("textarea")).toBeVisible();
  93  |   await expect(page.getByTestId("ai-reviewed-badge")).toHaveCount(0);
  94  |   const overflow = await page.evaluate(
  95  |     () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  96  |   );
  97  |   expect(overflow).toBe(true);
  98  | });
  99  |
  100 | test("coding opens the workspace with the review label", async ({ page }) => {
  101 |   await mockSession(page, {
  102 |     turn_index: 1,
  103 |     question_area: "Lists",
  104 |     question: "Write a function that returns the first item.",
  105 |     question_type: "coding",
  106 |     answer: null,
  107 |     evaluation: null,
  108 |   });
  109 |   await page.goto("/tracks/t1/interview/s1");
  110 |   await expect(page.getByTestId("ai-reviewed-badge")).toBeVisible();
  111 | });
  112 |
  113 | test("numeric and case questions fit a narrow screen", async ({ page }) => {
  114 |   await mockSession(
  115 |     page,
  116 |     {
  117 |       turn_index: 1,
  118 |       question_area: "Circuits",
  119 |       question: "What is the voltage drop?",
  120 |       question_type: "numeric",
  121 |       unit: "V",
  122 |       answer: null,
  123 |       evaluation: null,
  124 |     },
  125 |     "guided",
  126 |   );
  127 |   await page.setViewportSize({ width: 375, height: 800 });
  128 |   await page.goto("/tracks/t1/interview/s1");
  129 |   await expect(page.getByTestId("numeric-answer")).toBeVisible();
  130 |   await expect(page.getByTestId("numeric-unit")).toHaveText("V");
  131 |   await page.getByTestId("numeric-answer").fill("5");
  132 |   const overflow = await page.evaluate(
  133 |     () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  134 |   );
  135 |   expect(overflow).toBe(true);
  136 | });
  137 |
  138 | test("a high-risk session shows the practice label and the case", async ({ page }) => {
  139 |   await page.route("**/api/v1/auth/me", (r) => r.fulfill({ json: USER }));
  140 |   await page.route("**/api/v1/auth/logout", (r) => r.fulfill({ json: { status: "ok" } }));
  141 |   await page.route("**/api/v1/sessions/s1", (r) =>
  142 |     r.fulfill({
  143 |       json: {
  144 |         session: {
  145 |           id: "s1",
  146 |           track_id: "t1",
  147 |           mode: "strict",
  148 |           status: "in_progress",
  149 |           max_turns: 15,
  150 |           practice_label: "Exam-practice only, not professional advice",
  151 |         },
  152 |         turns: [
  153 |           {
  154 |             turn_index: 1,
  155 |             question_area: "Pharmacy",
  156 |             question: "What is the main counselling point?",
  157 |             question_type: "case_study",
  158 |             scenario: "A generic adult collects a new medicine and asks about drowsiness.",
  159 |             answer: null,
  160 |             evaluation: null,
  161 |           },
  162 |         ],
  163 |       },
  164 |     }),
  165 |   );
  166 |   await page.setViewportSize({ width: 375, height: 800 });
  167 |   await page.goto("/tracks/t1/interview/s1");
  168 |   await expect(page.getByTestId("practice-label")).toContainText("not professional advice");
  169 |   await expect(page.getByTestId("case-scenario")).toContainText("generic adult");
  170 |   await expect(page.getByText("Good start")).toHaveCount(0);
  171 |   const overflow = await page.evaluate(
  172 |     () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
  173 |   );
  174 |   expect(overflow).toBe(true);
  175 | });
  176 |
  177 | test("strict shows no evaluation before submit", async ({ page }) => {
  178 |   await mockSession(page, {
  179 |     turn_index: 1,
  180 |     question_area: "Lists",
  181 |     question: "What happens if you slice a list past its end?",
  182 |     question_type: "conceptual",
  183 |     answer: null,
  184 |     evaluation: null,
  185 |   });
> 186 |   await page.goto("/tracks/t1/interview/s1");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  187 |   await expect(page.getByText("Good start")).toHaveCount(0);
  188 |   await expect(page.getByText("That's right")).toHaveCount(0);
  189 |   await expect(page.getByText("Not quite")).toHaveCount(0);
  190 |   await expect(page.getByTestId("answer-composer")).toBeVisible();
  191 | });
  192 |
```
