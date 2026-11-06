# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\smoke.spec.ts >> dashboard lists tracks from the API
- Location: frontend\e2e\smoke.spec.ts:37:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   |
  3   | // Smoke tests run against the built app with the backend API mocked via route
  4   | // interception — they verify frontend behavior, not backend integration.
  5   |
  6   | const USER = {
  7   |   id: "u1",
  8   |   email: "student@example.com",
  9   |   name: "Student",
  10  |   picture_url: null,
  11  | };
  12  |
  13  | test.beforeEach(async ({ page }) => {
  14  |   await page.route("**/api/v1/auth/me", (route) =>
  15  |     route.fulfill({ json: USER }),
  16  |   );
  17  |   await page.route("**/api/v1/me/assessments", (route) =>
  18  |     route.fulfill({
  19  |       json: {
  20  |         dashboard: {
  21  |           completed_interviews: 0,
  22  |           average_score: null,
  23  |           total_questions_attempted: 0,
  24  |           strongest_skills: [],
  25  |           skills_needing_improvement: [],
  26  |           recommended_topics: [],
  27  |         },
  28  |         assessments: [],
  29  |       },
  30  |     }),
  31  |   );
  32  |   await page.route("**/api/v1/auth/logout", (route) =>
  33  |     route.fulfill({ json: { status: "ok" } }),
  34  |   );
  35  | });
  36  |
  37  | test("dashboard lists tracks from the API", async ({ page }) => {
  38  |   await page.route("**/api/v1/tracks", (route) =>
  39  |     route.fulfill({
  40  |       json: [
  41  |         {
  42  |           id: "t1",
  43  |           track_type: "role",
  44  |           subject: "Backend Engineer Intern",
  45  |           company: null,
  46  |           status: "active",
  47  |           created_at: "2026-11-03T00:00:00Z",
  48  |           brief_version: 1,
  49  |         },
  50  |       ],
  51  |     }),
  52  |   );
> 53  |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  54  |   await expect(
  55  |     page.getByRole("button", { name: "Backend Engineer Intern" }),
  56  |   ).toBeVisible();
  57  |   await expect(page.getByText(/Interview prep focused on the/i)).toBeVisible();
  58  | });
  59  |
  60  | test("track detail shows the question bank (M9)", async ({ page }) => {
  61  |   await page.route("**/api/v1/tracks/t1", (route) =>
  62  |     route.fulfill({
  63  |       json: {
  64  |         track: {
  65  |           id: "t1",
  66  |           track_type: "topic",
  67  |           subject: "Data Structures & Algorithms",
  68  |           company: null,
  69  |           status: "active",
  70  |           created_at: "2026-11-03T00:00:00Z",
  71  |         },
  72  |         brief: {
  73  |           version: 1,
  74  |           content: {
  75  |             summary: "DSA basics",
  76  |             competencies: [],
  77  |             question_areas: [],
  78  |             preparation_plan: [],
  79  |             candidate_angle_notes: "",
  80  |             question_bank: [
  81  |               {
  82  |                 area: "Hashmaps",
  83  |                 question: "Walk through how a Python dict resolves collisions.",
  84  |                 difficulty: "intermediate",
  85  |                 type: "conceptual",
  86  |                 expected_answer_sketch: "open addressing",
  87  |               },
  88  |               {
  89  |                 area: "Big-O",
  90  |                 question: "When is O(n log n) better than O(n)?",
  91  |                 difficulty: "advanced",
  92  |                 type: "conceptual",
  93  |                 expected_answer_sketch: "constants and cache behavior",
  94  |               },
  95  |             ],
  96  |           },
  97  |         },
  98  |       },
  99  |     }),
  100 |   );
  101 |   await page.route("**/api/v1/tracks/t1/progression", (route) =>
  102 |     route.fulfill({
  103 |       json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
  104 |     }),
  105 |   );
  106 |
  107 |   await page.goto("/tracks/t1");
  108 |   const bank = page.getByText(/Question bank \(2 pre-validated questions\)/);
  109 |   await bank.click();
  110 |   await expect(
  111 |     page.getByText("Walk through how a Python dict resolves collisions."),
  112 |   ).toBeVisible();
  113 |   await expect(page.getByText("advanced")).toBeVisible();
  114 | });
  115 |
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
```
