import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  onboarding_completed: false,
};

const READY_STATE = {
  messages: [
    { role: "user", content: "I built a line follower." },
    { role: "assistant", content: "Nice — what stack did you use?" },
  ],
  vault_items: [
    { id: "1", category: "project", title: "Line follower", source: "onboarding_chat" },
    { id: "2", category: "skill", title: "Python", source: "onboarding_chat" },
    { id: "3", category: "education", title: "B.Tech CSE", source: "onboarding_chat" },
  ],
  onboarding_complete: true,
  onboarding_finished: false,
  missing_categories: [],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
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
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
});

test("Finish Onboarding posts complete then lands on Tracks", async ({
  page,
}) => {
  let completeCalls = 0;
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: READY_STATE }),
  );
  await page.route("**/api/v1/onboarding/complete", async (route) => {
    completeCalls += 1;
    USER.onboarding_completed = true;
    await route.fulfill({
      json: {
        ...READY_STATE,
        onboarding_finished: true,
        onboarding_completed_at: "2026-11-04T10:00:00+00:00",
      },
    });
  });

  await page.goto("/onboarding");
  await expect(page.getByTestId("finish-onboarding")).toBeVisible();
  await expect(page.getByTestId("finish-onboarding-aside")).toHaveCount(0);

  await page.getByTestId("finish-onboarding").click();
  await expect(page).toHaveURL("/");
  expect(completeCalls).toBe(1);
  await expect(page.getByRole("heading", { name: "Tracks" })).toBeVisible();
});

test("completed onboarding shows Go to Tracks, not Finish", async ({
  page,
}) => {
  USER.onboarding_completed = true;
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        ...READY_STATE,
        onboarding_finished: true,
        onboarding_completed_at: "2026-11-04T10:00:00+00:00",
      },
    }),
  );

  await page.goto("/onboarding");
  await expect(page.getByTestId("onboarding-finished-banner")).toBeVisible();
  await expect(page.getByTestId("finish-onboarding")).toHaveCount(0);
  await expect(page.getByTestId("go-to-tracks")).toBeVisible();
  await page.getByRole("link", { name: "Onboarding" }).click();
  await expect(page).toHaveURL("/onboarding");
});
