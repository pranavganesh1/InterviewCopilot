# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\onboardingFinish.spec.ts >> Finish Onboarding posts complete then lands on Tracks
- Location: frontend\e2e\onboardingFinish.spec.ts:51:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/onboarding", waiting until "load"

```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   |
  3   | const USER = {
  4   |   id: "u1",
  5   |   email: "student@example.com",
  6   |   name: "Student",
  7   |   picture_url: null,
  8   |   onboarding_completed: false,
  9   | };
  10  |
  11  | const READY_STATE = {
  12  |   messages: [
  13  |     { role: "user", content: "I built a line follower." },
  14  |     { role: "assistant", content: "Nice — what stack did you use?" },
  15  |   ],
  16  |   vault_items: [
  17  |     { id: "1", category: "project", title: "Line follower", source: "onboarding_chat" },
  18  |     { id: "2", category: "skill", title: "Python", source: "onboarding_chat" },
  19  |     { id: "3", category: "education", title: "B.Tech CSE", source: "onboarding_chat" },
  20  |   ],
  21  |   onboarding_complete: true,
  22  |   onboarding_finished: false,
  23  |   missing_categories: [],
  24  | };
  25  |
  26  | test.beforeEach(async ({ page }) => {
  27  |   await page.route("**/api/v1/auth/me", (route) =>
  28  |     route.fulfill({ json: USER }),
  29  |   );
  30  |   await page.route("**/api/v1/auth/logout", (route) =>
  31  |     route.fulfill({ json: { status: "ok" } }),
  32  |   );
  33  |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  34  |   await page.route("**/api/v1/me/assessments", (route) =>
  35  |     route.fulfill({
  36  |       json: {
  37  |         dashboard: {
  38  |           completed_interviews: 0,
  39  |           average_score: null,
  40  |           total_questions_attempted: 0,
  41  |           strongest_skills: [],
  42  |           skills_needing_improvement: [],
  43  |           recommended_topics: [],
  44  |         },
  45  |         assessments: [],
  46  |       },
  47  |     }),
  48  |   );
  49  | });
  50  |
  51  | test("Finish Onboarding posts complete then lands on Tracks", async ({
  52  |   page,
  53  | }) => {
  54  |   let completeCalls = 0;
  55  |   await page.route("**/api/v1/onboarding/state", (route) =>
  56  |     route.fulfill({ json: READY_STATE }),
  57  |   );
  58  |   await page.route("**/api/v1/onboarding/complete", async (route) => {
  59  |     completeCalls += 1;
  60  |     USER.onboarding_completed = true;
  61  |     await route.fulfill({
  62  |       json: {
  63  |         ...READY_STATE,
  64  |         onboarding_finished: true,
  65  |         onboarding_completed_at: "2026-11-04T10:00:00+00:00",
  66  |       },
  67  |     });
  68  |   });
  69  |
> 70  |   await page.goto("/onboarding");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  71  |   await expect(page.getByTestId("finish-onboarding")).toBeVisible();
  72  |   await expect(page.getByTestId("finish-onboarding-aside")).toHaveCount(0);
  73  |
  74  |   await page.getByTestId("finish-onboarding").click();
  75  |   await expect(page).toHaveURL("/");
  76  |   expect(completeCalls).toBe(1);
  77  |   await expect(page.getByRole("heading", { name: "Tracks" })).toBeVisible();
  78  | });
  79  |
  80  | test("completed onboarding shows Go to Tracks, not Finish", async ({
  81  |   page,
  82  | }) => {
  83  |   USER.onboarding_completed = true;
  84  |   await page.route("**/api/v1/onboarding/state", (route) =>
  85  |     route.fulfill({
  86  |       json: {
  87  |         ...READY_STATE,
  88  |         onboarding_finished: true,
  89  |         onboarding_completed_at: "2026-11-04T10:00:00+00:00",
  90  |       },
  91  |     }),
  92  |   );
  93  |
  94  |   await page.goto("/onboarding");
  95  |   await expect(page.getByTestId("onboarding-finished-banner")).toBeVisible();
  96  |   await expect(page.getByTestId("finish-onboarding")).toHaveCount(0);
  97  |   await expect(page.getByTestId("go-to-tracks")).toBeVisible();
  98  |   await page.getByRole("link", { name: "Onboarding" }).click();
  99  |   await expect(page).toHaveURL("/onboarding");
  100 | });
  101 |
```
