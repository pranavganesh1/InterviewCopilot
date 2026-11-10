import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

const READY = {
  disclaimer:
    "Based only on what your resume says. We cannot verify claims. This helps you prepare.",
  empty: false,
  summary: { clear: 1, add_detail: 1, be_ready: 1 },
  items: [
    {
      vault_item_id: "v1",
      category: "project",
      title: "Campus nav",
      claims: [
        {
          claim: "cut average route time by 18% using A/B tests",
          excerpt: "cut average route time by 18% using A/B tests",
          category: "metric",
          status: "be_ready",
          status_reason: "Interviewers often ask about this.",
          questions: ["How did you measure the 18% improvement?"],
          tips: ["Prepare the measurement window and method."],
          stronger_phrasing:
            "cut average route time by 18% measured by [your metric], if accurate.",
        },
        {
          claim: "Used FastAPI and Postgres",
          excerpt: "stack: FastAPI + Postgres",
          category: "technology",
          status: "clear",
          questions: [],
          tips: [],
          stronger_phrasing: "",
        },
        {
          claim: "Led the backend rewrite",
          excerpt: "Led the backend rewrite",
          category: "ownership",
          status: "add_detail",
          questions: ["What did you personally own on the rewrite?"],
          tips: ["Clarify team size and your decisions."],
          stronger_phrasing: "As [your role] on a [team size] effort, Led the backend rewrite, if accurate.",
        },
      ],
    },
  ],
  consistency_hints: [
    { message: "You may be asked how Kubernetes connects to your projects.", related_item_ids: ["s1"] },
  ],
  claim_seeds: [
    {
      vault_item_id: "v1",
      claim: "cut average route time by 18% using A/B tests",
      title: "Campus nav",
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({
      json: {
        dashboard: {
          completed_interviews: 0,
          average_score: null,
          total_questions_attempted: 0,
          strongest_skills: [],
          skills_needing_improvement: [],
          recommended_topics: [],
        },
        assessments: [],
      },
    }),
  );
  await page.route("**/api/v1/me/open-sessions", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tracks", (route) =>
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "topic",
          subject: "Systems",
          company: null,
          status: "active",
          created_at: "2026-11-01T00:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/v1/vault/items", (route) =>
    route.fulfill({
      json: [
        {
          id: "v1",
          category: "project",
          title: "Campus nav",
          details: { note: "cut average route time by 18%" },
        },
      ],
    }),
  );
  await page.route("**/api/v1/tracks/*/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );
  await page.route("**/api/v1/tracks/*/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );
  await page.route("**/api/v1/tracks/*/weaknesses", (route) =>
    route.fulfill({
      json: {
        track_id: "t1",
        has_data: false,
        weak: [],
        improving: [],
        mastered: [],
        top_weak: [],
        recommended_practice: [],
      },
    }),
  );
});

test("page renders summary, badges, expandable questions, and copy", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.route("**/api/v1/vault/readiness", (route) =>
    route.fulfill({ json: READY }),
  );
  await page.goto("/readiness");
  await expect(page.getByTestId("readiness-disclaimer")).toContainText(
    "We cannot verify claims",
  );
  await expect(page.getByTestId("readiness-summary")).toBeVisible();
  await expect(page.getByText("Be ready to explain")).toBeVisible();
  await expect(
    page.getByTestId("readiness-summary").getByText("Add detail"),
  ).toBeVisible();
  await expect(page.locator("span").filter({ hasText: "Add detail" })).toBeVisible();
  await expect(page.getByText("Clear").first()).toBeVisible();
  const expand = page.getByRole("button", { name: "Questions you may face" }).first();
  await expand.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("How did you measure the 18% improvement?")).toBeVisible();
  const copyBtn = page.getByRole("button", { name: "Copy" }).first();
  await expect(copyBtn).toBeVisible();
  await copyBtn.click();
  await expect(page.getByRole("button", { name: /Copied|Copy/ }).first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(overflow).toBeLessThanOrEqual(376);
});

test("Refresh and error Retry", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/vault/readiness", (route) => {
    calls += 1;
    if (calls === 1) {
      return route.fulfill({ status: 503, json: { detail: "busy" } });
    }
    return route.fulfill({ json: READY });
  });
  await page.goto("/readiness");
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByTestId("readiness-summary")).toBeVisible();
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect.poll(() => calls).toBeGreaterThanOrEqual(3);
});

test("Practice these claims opens start popup with resume on", async ({ page }) => {
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/vault/readiness", (route) =>
    route.fulfill({ json: READY }),
  );
  await page.route("**/api/v1/tracks/t1/sessions", async (route) => {
    posted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        session: { id: "s1", track_id: "t1", mode: "strict", status: "in_progress" },
        turn: { question: "About your latency claim?" },
      },
    });
  });
  await page.route("**/api/v1/sessions/s1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          duration_minutes: 60,
          created_at: "2026-11-10T00:00:00Z",
          max_turns: 15,
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Projects",
            question: "About your latency claim?",
            answer: null,
          },
        ],
      },
    }),
  );

  await page.goto("/readiness");
  await page.getByRole("button", { name: "Practice these claims" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Use my resume and projects")).toBeChecked();
  await dialog.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s1/);
  expect(posted && posted.use_resume).toBe(true);
  const seeds = posted && posted.claim_seeds;
  expect(Array.isArray(seeds)).toBe(true);
  expect((seeds as unknown[]).length).toBeGreaterThan(0);
});

test("empty state", async ({ page }) => {
  await page.route("**/api/v1/vault/readiness", (route) =>
    route.fulfill({
      json: {
        disclaimer: READY.disclaimer,
        empty: true,
        empty_hint: "Add a project or internship in onboarding or your vault to run a readiness check.",
        summary: { clear: 0, add_detail: 0, be_ready: 0 },
        items: [],
        consistency_hints: [],
        claim_seeds: [],
      },
    }),
  );
  await page.goto("/readiness");
  await expect(page.getByTestId("readiness-empty")).toBeVisible();
  await expect(page.getByRole("link", { name: /Add projects/i })).toBeVisible();
});
