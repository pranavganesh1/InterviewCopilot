# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\feedbackStatus.spec.ts >> report page shows failed state for non-404 errors
- Location: frontend\e2e\feedbackStatus.spec.ts:189:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/tracks/t1/report/s1", waiting until "load"

```

# Test source

```ts
  98  |       question: "Explain the handshake.",
  99  |       answer: null as string | null,
  100 |       evaluation: null as Record<string, unknown> | null,
  101 |     },
  102 |   ];
  103 |   await page.route("**/api/v1/sessions/s1", (route) =>
  104 |     route.fulfill({
  105 |       json: {
  106 |         session: {
  107 |           id: "s1",
  108 |           track_id: "t1",
  109 |           mode: "strict",
  110 |           status: turns[0].answer ? "completed" : "in_progress",
  111 |         },
  112 |         turns,
  113 |       },
  114 |     }),
  115 |   );
  116 |   await page.route("**/api/v1/sessions/s1/turns", async (route) => {
  117 |     turns[0].answer = "SYN SYN-ACK ACK";
  118 |     turns[0].evaluation = {
  119 |       coverage: "good",
  120 |       strengths: ["Clear"],
  121 |       gaps: [],
  122 |     };
  123 |     await route.fulfill({
  124 |       json: {
  125 |         completed: true,
  126 |         evaluation: turns[0].evaluation,
  127 |       },
  128 |     });
  129 |   });
  130 |
  131 |   await page.goto("/tracks/t1/interview/s1");
  132 |   await page.fill("textarea", "SYN SYN-ACK ACK");
  133 |   await page.getByRole("button", { name: "Submit Answer" }).click();
  134 |
  135 |   await expect(page.getByTestId("evaluation-feedback")).toBeVisible();
  136 |   await expect(page.getByText("Interview completed.")).toBeVisible();
  137 |   await expect(page.getByText(/Feedback is pending/)).toBeVisible();
  138 |   await expect(page.getByText(/report is ready/i)).toHaveCount(0);
  139 |   await expect(page.getByTestId("finish-interview")).toBeVisible();
  140 |   await expect(page.getByRole("button", { name: "View report" })).toBeVisible();
  141 | });
  142 |
  143 | test("report page shows pending then ready after 404 clears", async ({ page }) => {
  144 |   let calls = 0;
  145 |   await page.route("**/api/v1/sessions/s1/report", async (route) => {
  146 |     calls += 1;
  147 |     if (calls === 1) {
  148 |       await route.fulfill({
  149 |         status: 404,
  150 |         contentType: "application/json",
  151 |         body: JSON.stringify({ detail: "Report not ready" }),
  152 |       });
  153 |       return;
  154 |     }
  155 |     await route.fulfill({
  156 |       json: {
  157 |         id: "r1",
  158 |         session_id: "s1",
  159 |         created_at: "2026-11-03T00:00:00Z",
  160 |         content: {
  161 |           report_version: 1,
  162 |           session_mode: "strict",
  163 |           summary_overview: "Ready now.",
  164 |           coverage_status: "PARTIAL",
  165 |           question_assessments: [],
  166 |           competency_assessments: [],
  167 |           strengths: ["Clear"],
  168 |           improvement_areas: [],
  169 |           unassessed_topics: [],
  170 |           recommendations: ["Keep practicing"],
  171 |         },
  172 |       },
  173 |     });
  174 |   });
  175 |
  176 |   await page.goto("/tracks/t1/report/s1");
  177 |   await expect(page.getByTestId("report-status")).toHaveAttribute(
  178 |     "data-state",
  179 |     /pending|generating|loading/,
  180 |   );
  181 |   await expect(page.getByTestId("report-status")).toHaveAttribute(
  182 |     "data-state",
  183 |     "ready",
  184 |     { timeout: 15000 },
  185 |   );
  186 |   await expect(page.getByText("Ready now.")).toBeVisible();
  187 | });
  188 |
  189 | test("report page shows failed state for non-404 errors", async ({ page }) => {
  190 |   await page.route("**/api/v1/sessions/s1/report", (route) =>
  191 |     route.fulfill({
  192 |       status: 500,
  193 |       contentType: "application/json",
  194 |       body: JSON.stringify({ detail: "worker crashed" }),
  195 |     }),
  196 |   );
  197 |
> 198 |   await page.goto("/tracks/t1/report/s1");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  199 |   await expect(page.getByTestId("report-status")).toHaveAttribute(
  200 |     "data-state",
  201 |     "failed",
  202 |   );
  203 |   await expect(page.getByText("Feedback generation failed")).toBeVisible();
  204 |   await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  205 | });
  206 |
```
