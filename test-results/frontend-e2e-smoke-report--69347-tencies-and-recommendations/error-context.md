# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\smoke.spec.ts >> report page shows competencies and recommendations
- Location: frontend\e2e\smoke.spec.ts:178:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/tracks/t1/report/s1", waiting until "load"

```

# Test source

```ts
  116 | test("interview page renders question and submits answer", async ({ page }) => {
  117 |   // Stateful mock mirroring the backend: turns live server-side, evaluations
  118 |   // are persisted onto the answered turn.
  119 |   const turns = [
  120 |     {
  121 |       turn_index: 1,
  122 |       question_area: "Hashmaps",
  123 |       question: "Explain hash collisions.",
  124 |       answer: null as string | null,
  125 |       evaluation: null as Record<string, unknown> | null,
  126 |     },
  127 |   ];
  128 |   await page.route("**/api/v1/sessions/s1", (route) =>
  129 |     route.fulfill({
  130 |       json: {
  131 |         session: { id: "s1", track_id: "t1", mode: "strict", status: "in_progress" },
  132 |         turns,
  133 |       },
  134 |     }),
  135 |   );
  136 |   await page.route("**/api/v1/sessions/s1/turns", async (route) => {
  137 |     turns[0].answer = "Buckets store multiple entries...";
  138 |     turns[0].evaluation = {
  139 |       coverage: "partial",
  140 |       strengths: ["Clear structure"],
  141 |       gaps: ["No examples"],
  142 |     };
  143 |     turns.push({
  144 |       turn_index: 2,
  145 |       question_area: "Hashmaps",
  146 |       question: "How would you resolve one?",
  147 |       answer: null,
  148 |       evaluation: null,
  149 |     });
  150 |     await route.fulfill({
  151 |       json: {
  152 |         completed: false,
  153 |         evaluation: {
  154 |           coverage: "partial",
  155 |           strengths: ["Clear structure"],
  156 |           gaps: ["No examples"],
  157 |         },
  158 |         turn: turns[1],
  159 |       },
  160 |     });
  161 |   });
  162 |
  163 |   await page.goto("/tracks/t1/interview/s1");
  164 |   await expect(page.getByText("Explain hash collisions.")).toBeVisible();
  165 |
  166 |   await page.fill("textarea", "Buckets store multiple entries...");
  167 |   await page.getByRole("button", { name: "Submit Answer" }).click();
  168 |
  169 |   await expect(page.getByTestId("evaluation-feedback")).toBeVisible();
  170 |   await expect(page.getByText("partial")).toBeVisible();
  171 |   await expect(page.getByText("No examples")).toBeVisible();
  172 |   await expect(page.getByText("How would you resolve one?")).toHaveCount(0);
  173 |
  174 |   await page.getByRole("button", { name: "Next question" }).click();
  175 |   await expect(page.getByText("How would you resolve one?")).toBeVisible();
  176 | });
  177 |
  178 | test("report page shows competencies and recommendations", async ({ page }) => {
  179 |   await page.route("**/api/v1/sessions/s1/report", (route) =>
  180 |     route.fulfill({
  181 |       json: {
  182 |         id: "r1",
  183 |         session_id: "s1",
  184 |         created_at: "2026-11-03T00:00:00Z",
  185 |         content: {
  186 |           report_version: 1,
  187 |           session_mode: "strict",
  188 |           summary_overview: "Solid fundamentals overall.",
  189 |           coverage_status: "PARTIAL",
  190 |           question_assessments: [
  191 |             {
  192 |               turn_index: 1,
  193 |               coverage: "good",
  194 |               observation: "Explained collisions well",
  195 |               evidence_excerpt: "chaining resolves",
  196 |             },
  197 |           ],
  198 |           competency_assessments: [
  199 |             {
  200 |               competency_name: "DSA",
  201 |               assessment_status: "ASSESSED",
  202 |               level: "solid",
  203 |               observation: "Good grasp",
  204 |               confidence: "MEDIUM",
  205 |             },
  206 |           ],
  207 |           strengths: ["Clear explanations"],
  208 |           improvement_areas: ["Complexity analysis"],
  209 |           unassessed_topics: ["Graphs"],
  210 |           recommendations: ["Practice Big-O estimation daily"],
  211 |         },
  212 |       },
  213 |     }),
  214 |   );
  215 |
> 216 |   await page.goto("/tracks/t1/report/s1");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  217 |   await expect(page.getByText("Solid fundamentals overall.")).toBeVisible();
  218 |   await expect(page.getByText("solid").first()).toBeVisible();
  219 |   await expect(page.getByText("Practice Big-O estimation daily")).toBeVisible();
  220 |   await expect(page.getByText(/Not assessed in this session/)).toBeVisible();
  221 | });
  222 |
```
