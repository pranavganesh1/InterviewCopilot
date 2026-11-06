# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\finishExit.spec.ts >> profile nav opens dashboard empty state
- Location: frontend\e2e\finishExit.spec.ts:130:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  50  |       json: {
  51  |         session: {
  52  |           id: "s1",
  53  |           track_id: "t1",
  54  |           mode: "strict",
  55  |           status: completed ? "completed" : "in_progress",
  56  |           max_turns: 15,
  57  |         },
  58  |         turns,
  59  |       },
  60  |     }),
  61  |   );
  62  |   await page.route("**/api/v1/sessions/s1/complete", async (route) => {
  63  |     completed = true;
  64  |     await route.fulfill({
  65  |       json: {
  66  |         session: {
  67  |           id: "s1",
  68  |           track_id: "t1",
  69  |           mode: "strict",
  70  |           status: "completed",
  71  |           max_turns: 15,
  72  |         },
  73  |       },
  74  |     });
  75  |   });
  76  |   await page.route("**/api/v1/sessions/s1/report", (route) =>
  77  |     route.fulfill({
  78  |       json: {
  79  |         id: "r1",
  80  |         session_id: "s1",
  81  |         created_at: "2026-11-04T00:00:00Z",
  82  |         overall_score: 75,
  83  |         questions_attempted: 1,
  84  |         content: {
  85  |           report_version: 1,
  86  |           session_mode: "strict",
  87  |           summary_overview: "Early exit after one solid answer.",
  88  |           coverage_status: "PARTIAL",
  89  |           question_assessments: [
  90  |             {
  91  |               turn_index: 1,
  92  |               coverage: "good",
  93  |               observation: "Explained chaining",
  94  |               evidence_excerpt: "list",
  95  |             },
  96  |           ],
  97  |           competency_assessments: [],
  98  |           strengths: ["Clear structure"],
  99  |           improvement_areas: ["Cover more topics"],
  100 |           unassessed_topics: ["Trees"],
  101 |           recommendations: ["Continue with open addressing"],
  102 |         },
  103 |       },
  104 |     }),
  105 |   );
  106 |
  107 |   await page.goto("/tracks/t1/interview/s1");
  108 |   await expect(
  109 |     page.getByRole("button", { name: "Finish Assessment & Exit" }),
  110 |   ).toBeVisible();
  111 |   await expect(page.getByRole("button", { name: "Submit Answer" })).toBeVisible();
  112 |
  113 |   await page.getByTestId("finish-assessment-exit").click();
  114 |   await expect(page.getByTestId("finish-exit-confirm")).toBeVisible();
  115 |   await expect(
  116 |     page.getByText(/submitted answers will be evaluated/i),
  117 |   ).toBeVisible();
  118 |
  119 |   await page.getByTestId("confirm-finish-exit").click();
  120 |   await expect(page).toHaveURL(/\/tracks\/t1\/report\/s1/);
  121 |   await expect(page.getByTestId("report-status")).toHaveAttribute(
  122 |     "data-state",
  123 |     "ready",
  124 |   );
  125 |   await expect(page.getByText("Overall score")).toBeVisible();
  126 |   await expect(page.getByText("75%")).toBeVisible();
  127 |   await expect(page.getByText("Early exit after one solid answer.")).toBeVisible();
  128 | });
  129 |
  130 | test("profile nav opens dashboard empty state", async ({ page }) => {
  131 |   await page.route("**/api/v1/me/assessments", (route) =>
  132 |     route.fulfill({
  133 |       json: {
  134 |         dashboard: {
  135 |           completed_interviews: 0,
  136 |           average_score: null,
  137 |           total_questions_attempted: 0,
  138 |           strongest_skills: [],
  139 |           skills_needing_improvement: [],
  140 |           recommended_topics: [],
  141 |         },
  142 |         assessments: [],
  143 |       },
  144 |     }),
  145 |   );
  146 |   await page.route("**/api/v1/auth/refresh", (route) =>
  147 |     route.fulfill({ status: 204 }),
  148 |   );
  149 |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
> 150 |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  151 |   await page.getByTestId("nav-profile").click();
  152 |   await page.getByRole("menuitem", { name: "My Profile" }).click();
  153 |   await expect(page).toHaveURL(/\/profile/);
  154 |   await expect(page.getByText("No completed assessments yet")).toBeVisible();
  155 | });
  156 |
```
