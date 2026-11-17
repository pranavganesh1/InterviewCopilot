import { expect, test, type Page } from "@playwright/test";

/**
 * Fix 5: wire orphan APIs — abort (covered in leaveInterview), goals/confirm,
 * review/refresh, POST /vault/items. All routes mocked; no shared DB writes.
 */

const EMPTY_ASSESSMENTS = {
  dashboard: {
    completed_interviews: 0,
    average_score: null,
    total_questions_attempted: 0,
    strongest_skills: [],
    skills_needing_improvement: [],
    recommended_topics: [],
  },
  assessments: [],
};

async function mockShell(
  page: Page,
  user: Record<string, unknown> = {
    id: "u1",
    email: "student@example.com",
    name: "Student",
    picture_url: null,
    onboarding_completed: false,
  },
) {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({ json: EMPTY_ASSESSMENTS }),
  );
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
}

test("Confirm goals posts /onboarding/goals/confirm and refreshes state", async ({
  page,
}) => {
  let confirmCalls = 0;
  const prefs = {
    interests: ["skill"],
    focus_skills: ["Python"],
    confirmed: false,
  };
  const baseState = {
    messages: [{ role: "assistant", content: "Ready when you are." }],
    vault_items: [{ id: "2", category: "skill", title: "Python", source: "manual" }],
    onboarding_complete: true,
    onboarding_finished: false,
    missing_categories: [],
    phase: "ready",
    show_goal_menu: true,
    followups_complete: true,
    goals_ready: true,
    goal_interest_options: [
      { id: "skill", label: "Skill Practice" },
      { id: "technical", label: "Technical" },
    ],
    suggested_skills: ["Python"],
    suggested_projects: [],
    preparation_preferences: prefs,
  };

  await mockShell(page);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        ...baseState,
        preparation_preferences: { ...prefs },
      },
    }),
  );
  await page.route("**/api/v1/onboarding/goals/confirm", async (route) => {
    expect(route.request().method()).toBe("POST");
    confirmCalls += 1;
    prefs.confirmed = true;
    await route.fulfill({
      json: {
        ...baseState,
        preparation_preferences: { ...prefs, confirmed: true },
        goals_ready: true,
      },
    });
  });

  await page.goto("/onboarding");
  const confirm = page.getByTestId("confirm-goals");
  await expect(confirm).toBeVisible();
  await confirm.click();
  await expect.poll(() => confirmCalls).toBe(1);
  await expect(page.getByTestId("confirm-goals")).toHaveCount(0);
});

test("Confirm goals failure keeps the button and shows an error", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        messages: [],
        vault_items: [],
        onboarding_complete: true,
        onboarding_finished: false,
        missing_categories: [],
        phase: "ready",
        show_goal_menu: true,
        followups_complete: true,
        goals_ready: true,
        goal_interest_options: [{ id: "skill", label: "Skill Practice" }],
        suggested_skills: ["Python"],
        preparation_preferences: {
          interests: ["skill"],
          focus_skills: ["Python"],
          confirmed: false,
        },
      },
    }),
  );
  await page.route("**/api/v1/onboarding/goals/confirm", (route) =>
    route.fulfill({ status: 500, json: { detail: "Confirm failed." } }),
  );

  await page.goto("/onboarding");
  await page.getByTestId("confirm-goals").click();
  await expect(page.getByTestId("confirm-goals-error")).toContainText("Confirm failed.");
  await expect(page.getByTestId("confirm-goals")).toBeEnabled();
});

test("preparation review refresh replaces payload and surfaces 429", async ({ page }) => {
  let refreshCalls = 0;
  const reviewV1 = {
    summary: "Plan v1",
    item_statuses: [],
    roadmap: [{ subject: "Arrays", track_type: "topic", reason: "foundation" }],
    next_action: { kind: "browse_tracks", label: "Browse tracks" },
  };
  const reviewV2 = {
    ...reviewV1,
    summary: "Plan v2 refreshed",
  };

  await mockShell(page, {
    id: "u1",
    email: "student@example.com",
    name: "Student",
    picture_url: null,
    onboarding_completed: true,
    profile_review: reviewV1,
  });
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        onboarding_completed: true,
        onboarding_finished: true,
        messages: [],
        vault_items: [],
      },
    }),
  );
  await page.route("**/api/v1/onboarding/review", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: reviewV1 });
    }
    return route.fulfill({ json: reviewV1 });
  });
  await page.route("**/api/v1/onboarding/review/refresh", async (route) => {
    expect(route.request().method()).toBe("POST");
    refreshCalls += 1;
    if (refreshCalls === 1) {
      await route.fulfill({
        status: 429,
        json: { detail: "Please wait a moment before refreshing again." },
      });
      return;
    }
    await route.fulfill({ json: reviewV2 });
  });

  await page.goto("/");
  await expect(page.getByText("Your personalized preparation plan")).toBeVisible();
  await expect(page.getByText("Plan v1")).toBeVisible();

  await page.getByTestId("preparation-review-refresh").click();
  await expect(page.getByTestId("preparation-review-refresh-error")).toContainText(
    "Please wait a moment before refreshing again.",
  );
  expect(refreshCalls).toBe(1);

  await page.getByTestId("preparation-review-refresh").click();
  await expect(page.getByText("Plan v2 refreshed")).toBeVisible();
  expect(refreshCalls).toBe(2);
});

test("manual vault add posts /vault/items and invalidates list", async ({ page }) => {
  let postCalls = 0;
  const items = [
    { id: "2", category: "skill", title: "Python", source: "resume", details: {} },
  ];

  await mockShell(page);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        messages: [{ role: "assistant", content: "Hi" }],
        vault_items: items,
        onboarding_complete: false,
        onboarding_finished: false,
        missing_categories: ["project"],
        phase: "profile",
        show_goal_menu: false,
        preparation_preferences: { interests: [], confirmed: false },
      },
    }),
  );
  await page.route("**/api/v1/vault/items", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: items });
      return;
    }
    if (route.request().method() === "POST") {
      postCalls += 1;
      const body = route.request().postDataJSON() as {
        category: string;
        title: string;
      };
      expect(body.category).toBe("skill");
      expect(body.title).toBe("TypeScript");
      const created = {
        id: "new-1",
        category: body.category,
        title: body.title,
        source: "manual",
        details: {},
      };
      items.push(created);
      await route.fulfill({
        json: { id: created.id, category: created.category, title: created.title },
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/onboarding");
  await expect(page.getByTestId("profile-panel")).toBeVisible();
  await page.getByTestId("vault-add-open").click();
  await page.getByTestId("vault-add-category").selectOption("skill");
  await page.getByTestId("vault-add-title").fill("TypeScript");
  await page.getByTestId("vault-add-submit").click();
  await expect.poll(() => postCalls).toBe(1);
  await page.getByTestId("profile-tab-skills").click();
  await expect(page.getByTestId("profile-tabpanel-skills")).toContainText("TypeScript");
});

test("manual vault add shows validation errors and does not double-submit", async ({
  page,
}) => {
  let postCalls = 0;
  await mockShell(page);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        messages: [],
        vault_items: [],
        onboarding_complete: false,
        onboarding_finished: false,
        missing_categories: ["skill"],
        phase: "profile",
        show_goal_menu: false,
      },
    }),
  );
  await page.route("**/api/v1/vault/items", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fulfill({ json: [] });
      return;
    }
    postCalls += 1;
    await new Promise((r) => setTimeout(r, 400));
    await route.fulfill({
      status: 422,
      json: { detail: "Unknown category: nope" },
    });
  });

  await page.goto("/onboarding");
  await page.getByTestId("vault-add-open").click();
  await page.getByTestId("vault-add-title").fill("Bad item");
  const submit = page.getByTestId("vault-add-submit");
  await submit.click();
  await submit.click({ force: true }).catch(() => undefined);
  await expect(page.getByTestId("vault-add-error")).toBeVisible();
  expect(postCalls).toBe(1);
});
