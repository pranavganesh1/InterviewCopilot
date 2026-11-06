# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\leaveInterview.spec.ts >> header links and profile menu open the leave warning and can stay or leave
- Location: frontend\e2e\leaveInterview.spec.ts:109:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  1   | import { expect, test, type Page } from "@playwright/test";
  2   |
  3   | const USER = {
  4   |   id: "u1",
  5   |   email: "student@example.com",
  6   |   name: "Student",
  7   |   picture_url: null,
  8   |   professional_title: "",
  9   |   introduction: "",
  10  |   skills: [],
  11  |   education: "",
  12  | };
  13  |
  14  | const REPORT = {
  15  |   id: "r1",
  16  |   session_id: "s1",
  17  |   created_at: "2026-11-04T00:00:00Z",
  18  |   overall_score: 70,
  19  |   questions_attempted: 1,
  20  |   content: {
  21  |     report_version: 1,
  22  |     session_mode: "strict",
  23  |     summary_overview: "Scored the answered questions.",
  24  |     coverage_status: "PARTIAL",
  25  |     question_assessments: [],
  26  |     competency_assessments: [],
  27  |     strengths: [],
  28  |     improvement_areas: [],
  29  |     unassessed_topics: [],
  30  |     recommendations: [],
  31  |   },
  32  | };
  33  |
  34  | function sessionBody(status: string, duration?: number) {
  35  |   return {
  36  |     session: {
  37  |       id: "s1",
  38  |       track_id: "t1",
  39  |       mode: "strict",
  40  |       status,
  41  |       max_turns: 15,
  42  |       ...(duration ? { duration_minutes: duration, created_at: "2026-11-06T08:00:00Z" } : {}),
  43  |     },
  44  |     turns: [
  45  |       {
  46  |         turn_index: 1,
  47  |         question_area: "Hashmaps",
  48  |         question: "Explain hash collisions.",
  49  |         answer: null,
  50  |         evaluation: null,
  51  |       },
  52  |     ],
  53  |   };
  54  | }
  55  |
  56  | async function mockShell(page: Page) {
  57  |   await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  58  |   await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ json: { status: "ok" } }));
  59  |   await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 204 }));
  60  |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  61  |   await page.route("**/api/v1/me/assessments", (route) =>
  62  |     route.fulfill({
  63  |       json: {
  64  |         dashboard: {
  65  |           completed_interviews: 0,
  66  |           average_score: null,
  67  |           total_questions_attempted: 0,
  68  |           strongest_skills: [],
  69  |           skills_needing_improvement: [],
  70  |           recommended_topics: [],
  71  |         },
  72  |         assessments: [],
  73  |       },
  74  |     }),
  75  |   );
  76  |   await page.route("**/api/v1/onboarding/state", (route) =>
  77  |     route.fulfill({
  78  |       json: {
  79  |         onboarding_completed: false,
  80  |         messages: [],
  81  |         profile: {},
  82  |       },
  83  |     }),
  84  |   );
  85  | }
  86  |
  87  | async function openInterview(page: Page, duration?: number, status = "in_progress") {
  88  |   await page.route("**/api/v1/sessions/s1", (route) => {
  89  |     if (route.request().method() !== "GET") return route.fallback();
  90  |     return route.fulfill({ json: sessionBody(status, duration) });
  91  |   });
> 92  |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  93  |   await page.goto("/tracks/t1/interview/s1");
  94  |   await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  95  | }
  96  |
  97  | async function unloadBlocked(page: Page) {
  98  |   return page.evaluate(() => {
  99  |     const event = new Event("beforeunload", { cancelable: true });
  100 |     window.dispatchEvent(event);
  101 |     return event.defaultPrevented;
  102 |   });
  103 | }
  104 |
  105 | test.beforeEach(async ({ page }) => {
  106 |   await mockShell(page);
  107 | });
  108 |
  109 | test("header links and profile menu open the leave warning and can stay or leave", async ({
  110 |   page,
  111 | }) => {
  112 |   await openInterview(page);
  113 |   const draft = page.locator("textarea");
  114 |   await draft.fill("unsaved chaining note");
  115 |
  116 |   await page.getByRole("link", { name: "Tracks", exact: true }).click();
  117 |   const modal = page.getByTestId("leave-interview-modal");
  118 |   await expect(modal).toBeVisible();
  119 |   await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s1/);
  120 |   await page.getByRole("button", { name: "Stay in interview" }).click();
  121 |   await expect(modal).toBeHidden();
  122 |   await expect(draft).toHaveValue("unsaved chaining note");
  123 |
  124 |   await page.getByRole("link", { name: "Onboarding" }).click();
  125 |   await expect(modal).toBeVisible();
  126 |   await expect(page).toHaveURL(/\/interview\/s1/);
  127 |   await page.getByRole("button", { name: "Leave and resume later" }).click();
  128 |   await expect(page).toHaveURL(/\/onboarding$/);
  129 |
  130 |   await page.goto("/tracks/t1/interview/s1");
  131 |   await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  132 |   await page.getByTestId("nav-profile").click();
  133 |   await page.getByRole("menuitem", { name: "My Profile" }).click();
  134 |   await expect(modal).toBeVisible();
  135 |   await expect(page).toHaveURL(/\/interview\/s1/);
  136 |   await page.getByRole("button", { name: "Stay in interview" }).click();
  137 |   await expect(modal).toBeHidden();
  138 |
  139 |   await page.getByRole("button", { name: "Leave session" }).click();
  140 |   await expect(modal).toBeVisible();
  141 |   await page.getByRole("button", { name: "Leave and resume later" }).click();
  142 |   await expect(page).toHaveURL(/\/tracks\/t1$/);
  143 | });
  144 |
  145 | test("browser Back is blocked on an active interview and not on a finished session or report", async ({
  146 |   page,
  147 | }) => {
  148 |   await openInterview(page);
  149 |   await page.goBack();
  150 |   await expect(page.getByTestId("leave-interview-modal")).toBeVisible();
  151 |   await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s1/);
  152 |   await page.getByRole("button", { name: "Leave and resume later" }).click();
  153 |   await expect(page).toHaveURL(/\/$/);
  154 |   await expect(page.getByTestId("leave-interview-modal")).toBeHidden();
  155 |
  156 |   await page.route("**/api/v1/sessions/s1", (route) => {
  157 |     if (route.request().method() !== "GET") return route.fallback();
  158 |     return route.fulfill({ json: sessionBody("completed") });
  159 |   });
  160 |   await page.goto("/tracks/t1/interview/s1");
  161 |   await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  162 |   await page.goBack();
  163 |   await expect(page).toHaveURL(/\/$/);
  164 |   await expect(page.getByTestId("leave-interview-modal")).toHaveCount(0);
  165 |
  166 |   await page.route("**/api/v1/sessions/s1/report", (route) =>
  167 |     route.fulfill({ status: 404, json: { detail: "pending" } }),
  168 |   );
  169 |   await page.goto("/tracks/t1/report/s1");
  170 |   await page.goBack();
  171 |   await expect(page).toHaveURL(/\/$/);
  172 |   await expect(page.getByTestId("leave-interview-modal")).toHaveCount(0);
  173 | });
  174 |
  175 | test("timed interviews mention the running timer and untimed ones do not", async ({ page }) => {
  176 |   await openInterview(page, 45);
  177 |   await page.getByRole("link", { name: "Tracks", exact: true }).click();
  178 |   await expect(page.getByText("The timer keeps running while you are away.")).toBeVisible();
  179 |   await page.getByRole("button", { name: "Stay in interview" }).click();
  180 |
  181 |   const untimed = sessionBody("in_progress");
  182 |   untimed.session.id = "s-plain";
  183 |   await page.route("**/api/v1/sessions/s-plain", (route) => route.fulfill({ json: untimed }));
  184 |   await page.goto("/");
  185 |   await page.goto("/tracks/t1/interview/s-plain");
  186 |   await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  187 |   await page.getByRole("link", { name: "Tracks", exact: true }).click();
  188 |   await expect(page.getByTestId("leave-interview-modal")).toBeVisible();
  189 |   await expect(page.getByText("The timer keeps running while you are away.")).toHaveCount(0);
  190 | });
  191 |
  192 | test("Finish and get feedback confirms, completes once, and opens the report", async ({
```
