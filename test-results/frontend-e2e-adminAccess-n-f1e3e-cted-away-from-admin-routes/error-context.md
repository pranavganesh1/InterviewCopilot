# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\adminAccess.spec.ts >> non-admin is redirected away from admin routes
- Location: frontend\e2e\adminAccess.spec.ts:11:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/admin", waiting until "load"

```

# Test source

```ts
  1  | import { expect, test } from "@playwright/test";
  2  |
  3  | const USER = {
  4  |   id: "u1",
  5  |   email: "student@example.com",
  6  |   name: "Student",
  7  |   picture_url: null,
  8  |   is_admin: false,
  9  | };
  10 |
  11 | test("non-admin is redirected away from admin routes", async ({ page }) => {
  12 |   await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  13 |   await page.route("**/api/v1/me/assessments", (route) =>
  14 |     route.fulfill({
  15 |       json: {
  16 |         dashboard: {
  17 |           completed_interviews: 0,
  18 |           average_score: null,
  19 |           total_questions_attempted: 0,
  20 |           strongest_skills: [],
  21 |           skills_needing_improvement: [],
  22 |           recommended_topics: [],
  23 |         },
  24 |         assessments: [],
  25 |       },
  26 |     }),
  27 |   );
  28 |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  29 |
> 30 |   await page.goto("/admin");
     |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  31 |   await expect(page).toHaveURL("/");
  32 |   await expect(page.getByRole("heading", { name: "Admin · Overview" })).toHaveCount(0);
  33 |
  34 |   await page.goto("/admin/users");
  35 |   await expect(page).toHaveURL("/");
  36 | });
  37 |
```
