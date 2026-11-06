# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\newTrack.spec.ts >> track type cards change the fields and submit the existing payload
- Location: frontend\e2e\newTrack.spec.ts:33:1

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
  8   | };
  9   |
  10  | async function mockShell(page: Page) {
  11  |   await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  12  |   await page.route("**/api/v1/auth/logout", (route) =>
  13  |     route.fulfill({ json: { status: "ok" } }),
  14  |   );
  15  |   await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 204 }));
  16  |   await page.route("**/api/v1/me/assessments", (route) =>
  17  |     route.fulfill({
  18  |       json: {
  19  |         dashboard: {
  20  |           completed_interviews: 0,
  21  |           average_score: null,
  22  |           total_questions_attempted: 0,
  23  |           strongest_skills: [],
  24  |           skills_needing_improvement: [],
  25  |           recommended_topics: [],
  26  |         },
  27  |         assessments: [],
  28  |       },
  29  |     }),
  30  |   );
  31  | }
  32  |
  33  | test("track type cards change the fields and submit the existing payload", async ({
  34  |   page,
  35  | }) => {
  36  |   const bodies: unknown[] = [];
  37  |   await mockShell(page);
  38  |   await page.route("**/api/v1/tracks", async (route) => {
  39  |     if (route.request().method() === "POST") {
  40  |       bodies.push(route.request().postDataJSON());
  41  |       await route.fulfill({
  42  |         status: 201,
  43  |         json: {
  44  |           track: {
  45  |             id: `t-${bodies.length}`,
  46  |             track_type: "topic",
  47  |             subject: "Saved",
  48  |             company: null,
  49  |             status: "active",
  50  |             created_at: "2026-11-06T00:00:00Z",
  51  |           },
  52  |         },
  53  |       });
  54  |       return;
  55  |     }
  56  |     await route.fulfill({ json: [] });
  57  |   });
  58  |
> 59  |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  60  |   await page.getByRole("button", { name: "New track" }).click();
  61  |   const topic = page.getByRole("radio", { name: /Practice a subject/ });
  62  |   const role = page.getByRole("radio", { name: /Prepare for a job role/ });
  63  |   const company = page.getByRole("radio", { name: /Paste a job description/ });
  64  |   await expect(topic).toHaveAttribute("aria-checked", "true");
  65  |   await expect(page.getByLabel("Subject")).toBeVisible();
  66  |   await expect(page.getByRole("button", { name: "Create track" })).toBeDisabled();
  67  |
  68  |   await page.getByRole("button", { name: "DBMS" }).click();
  69  |   await expect(page.getByLabel("Subject")).toHaveValue("DBMS");
  70  |   await page.getByRole("button", { name: "Create track" }).click();
  71  |   await expect(page.getByRole("heading", { name: "Create a new track" })).toBeHidden();
  72  |
  73  |   await page.getByRole("button", { name: "New track" }).click();
  74  |   await role.click();
  75  |   await expect(role).toHaveAttribute("aria-checked", "true");
  76  |   await expect(topic).toHaveAttribute("aria-checked", "false");
  77  |   await expect(page.getByLabel("Role")).toBeVisible();
  78  |   await page.getByRole("button", { name: "Backend Intern" }).click();
  79  |   await page.getByRole("button", { name: "Create track" }).click();
  80  |
  81  |   await page.getByRole("button", { name: "New track" }).click();
  82  |   await company.click();
  83  |   await expect(company).toHaveAttribute("aria-checked", "true");
  84  |   await expect(page.getByLabel("Company")).toBeVisible();
  85  |   await expect(page.getByLabel("Job description")).toBeVisible();
  86  |   await expect(page.getByText(/0\s*\/\s*20/)).toBeVisible();
  87  |   await page.getByLabel("Company").fill("Acme");
  88  |   await page.getByLabel("Role").fill("Backend Intern");
  89  |   await page.getByLabel("Job description").fill("Build APIs");
  90  |   await expect(page.getByText(/10\s*\/\s*20/)).toBeVisible();
  91  |   await page.getByRole("button", { name: "Create track" }).click();
  92  |
  93  |   expect(bodies).toEqual([
  94  |     { track_type: "topic", subject: "DBMS", company: null, jd_text: null },
  95  |     { track_type: "role", subject: "Backend Intern", company: null, jd_text: null },
  96  |     {
  97  |       track_type: "company_jd",
  98  |       subject: "Backend Intern",
  99  |       company: "Acme",
  100 |       jd_text: "Build APIs",
  101 |     },
  102 |   ]);
  103 | });
  104 |
  105 | test("arrow keys move between track types and Space or Enter selects", async ({ page }) => {
  106 |   await mockShell(page);
  107 |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  108 |   await page.goto("/");
  109 |   await page.getByRole("button", { name: "New track" }).click();
  110 |   const topic = page.getByRole("radio", { name: /Practice a subject/ });
  111 |   const role = page.getByRole("radio", { name: /Prepare for a job role/ });
  112 |   const company = page.getByRole("radio", { name: /Paste a job description/ });
  113 |   await topic.focus();
  114 |   await page.keyboard.press("ArrowRight");
  115 |   await expect(role).toBeFocused();
  116 |   await expect(topic).toHaveAttribute("aria-checked", "true");
  117 |   await page.keyboard.press("Space");
  118 |   await expect(role).toHaveAttribute("aria-checked", "true");
  119 |   await expect(page.getByLabel("Role")).toBeVisible();
  120 |   await page.keyboard.press("ArrowDown");
  121 |   await expect(company).toBeFocused();
  122 |   await page.keyboard.press("Enter");
  123 |   await expect(company).toHaveAttribute("aria-checked", "true");
  124 |   await expect(page.getByLabel("Job description")).toBeVisible();
  125 | });
  126 |
  127 | test("a failed create stays in the form with the typed values", async ({ page }) => {
  128 |   await mockShell(page);
  129 |   await page.route("**/api/v1/tracks", async (route) => {
  130 |     if (route.request().method() === "POST") {
  131 |       await route.fulfill({ status: 500, json: { detail: "Could not create the track." } });
  132 |       return;
  133 |     }
  134 |     await route.fulfill({ json: [] });
  135 |   });
  136 |   await page.goto("/");
  137 |   await page.getByRole("button", { name: "New track" }).click();
  138 |   await page.getByLabel("Subject").fill("Thermodynamics");
  139 |   await page.getByLabel("Subject").blur();
  140 |   await page.getByRole("button", { name: "Create track" }).click();
  141 |   await expect(page.getByRole("alert")).toHaveText("Could not create the track.");
  142 |   await expect(page.getByLabel("Subject")).toHaveValue("Thermodynamics");
  143 |   await expect(page.getByRole("heading", { name: "Create a new track" })).toBeVisible();
  144 | });
  145 |
  146 | test("the new track form has no horizontal overflow at 375px", async ({ page }) => {
  147 |   await page.setViewportSize({ width: 375, height: 800 });
  148 |   await mockShell(page);
  149 |   await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  150 |   await page.goto("/");
  151 |   await page.getByRole("button", { name: "New track" }).click();
  152 |   await page.getByRole("radio", { name: /Paste a job description/ }).click();
  153 |   const overflow = await page.evaluate(
  154 |     () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  155 |   );
  156 |   expect(overflow).toBe(false);
  157 |   const create = await page.getByRole("button", { name: "Create track" }).boundingBox();
  158 |   expect(create?.width ?? 0).toBeGreaterThan(300);
  159 |   expect(create?.height ?? 0).toBeGreaterThanOrEqual(44);
```
