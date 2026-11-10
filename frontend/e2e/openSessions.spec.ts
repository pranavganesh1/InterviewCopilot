import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
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
          completed_interviews: 1,
          average_score: 80,
          total_questions_attempted: 1,
          strongest_skills: [],
          skills_needing_improvement: [],
          recommended_topics: [],
        },
        assessments: [],
      },
    }),
  );
  await page.route("**/api/v1/tracks**", (route) =>
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "topic",
          subject: "Graphs",
          company: null,
          status: "active",
          created_at: "2026-11-01T00:00:00Z",
          brief_version: 1,
        },
      ],
    }),
  );
});

test("Interview Progress shows open sessions with Resume and Finish", async ({ page }) => {
  let completed = false;
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({
      json: completed
        ? []
        : [
            {
              session_id: "sess-open",
              track_id: "t1",
              track_subject: "Graphs",
              mode: "strict",
              status: "in_progress",
              question_index: 2,
              max_turns: 15,
              answered_count: 1,
              created_at: "2026-11-08T10:00:00Z",
              duration_minutes: 60,
            },
          ],
    }),
  );
  await page.route("**/api/v1/sessions/sess-open/complete", async (route) => {
    completed = true;
    await route.fulfill({
      json: { session: { id: "sess-open", status: "completed" } },
    });
  });
  await page.route("**/api/v1/sessions/sess-open/report", (route) =>
    route.fulfill({
      json: {
        id: "r1",
        session_id: "sess-open",
        content: { summary_overview: "Done.", coverage_status: "PARTIAL" },
      },
    }),
  );
  await page.route("**/api/v1/tracks/t1/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );

  await page.goto("/");
  const progress = page.getByRole("heading", { name: "Interview Progress" }).locator("..");
  await expect(progress).toContainText("1");
  await expect(progress.getByText("In Progress")).toBeVisible();
  await expect(page.getByText("Q2/15")).toBeVisible();
  await expect(page.getByRole("link", { name: "Resume" })).toHaveAttribute(
    "href",
    "/tracks/t1/interview/sess-open",
  );
  await page.getByRole("button", { name: "Finish and get feedback" }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/report\/sess-open/);
});

test("empty open sessions show a quiet message and zero count", async ({ page }) => {
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto("/");
  const progress = page.getByRole("heading", { name: "Interview Progress" }).locator("..");
  await expect(progress).toContainText("0");
  await expect(page.getByText("No unfinished interviews right now.")).toBeVisible();
});

test("open session list does not overflow at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({
      json: [
        {
          session_id: "sess-open",
          track_id: "t1",
          track_subject: "Very Long Track Subject Name For Mobile",
          mode: "strict",
          status: "in_progress",
          question_index: 3,
          max_turns: 15,
          answered_count: 2,
          created_at: "2026-11-08T10:00:00Z",
          duration_minutes: 60,
        },
      ],
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Finish and get feedback" })).toBeVisible();
  const fits = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
  expect(fits).toBe(true);
});
