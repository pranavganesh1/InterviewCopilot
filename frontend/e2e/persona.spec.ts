import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

const TRACK = {
  id: "t1",
  track_type: "topic",
  subject: "Graphs",
  company: null,
  status: "active",
  created_at: "2026-11-01T00:00:00Z",
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem("ic_persona_id"));
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
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/vault/items", (route) => route.fulfill({ json: [] }));
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
  await page.route("**/api/v1/tracks", (route) =>
    route.fulfill({ json: [TRACK] }),
  );
  await page.route("**/api/v1/tracks/t1/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );
});

test("persona cards render, Balanced is preselected, keyboard moves", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Choose your interviewer")).toBeVisible();
  const balanced = dialog.getByRole("radio", { name: /Balanced/ });
  await expect(balanced).toBeChecked();
  await balanced.focus();
  await page.keyboard.press("ArrowRight");
  await expect(dialog.getByRole("radio", { name: /Strict Architect/ })).toBeChecked();
  await page.keyboard.press("ArrowLeft");
  await expect(balanced).toBeChecked();
  const box = await dialog.boundingBox();
  expect(box).toBeTruthy();
  expect((await page.locator("body").evaluate((el) => el.scrollWidth)) <= 375 + 1).toBe(
    true,
  );
});

test("chosen persona id is sent on start and badge shows", async ({ page }) => {
  let posted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/tracks/t1/sessions", async (route) => {
    posted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        session: {
          id: "s-persona",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          persona_id: "architect",
          persona_name: "The Strict Architect",
          duration_minutes: 60,
          created_at: "2026-11-10T00:00:00Z",
        },
        turn: {
          turn_index: 1,
          question_area: "Graphs",
          question: "What is a trade-off of adjacency lists?",
        },
      },
    });
  });
  await page.route("**/api/v1/sessions/s-persona", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s-persona",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          persona_id: "architect",
          persona_name: "The Strict Architect",
          duration_minutes: 60,
          created_at: "2026-11-10T00:00:00Z",
          max_turns: 15,
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Graphs",
            question: "What is a trade-off of adjacency lists?",
            answer: null,
            evaluation: null,
          },
        ],
      },
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  await page.getByRole("radio", { name: /Strict Architect/ }).click();
  await page.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-persona/);
  expect(posted?.persona_id).toBe("architect");
  await expect(page.getByTestId("persona-badge")).toHaveText(
    "Interviewer: The Strict Architect",
  );
});

test("report shows Interviewed by persona name", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({
      json: {
        id: "r1",
        session_id: "s1",
        overall_score: 70,
        performance_level: "Solid",
        questions_attempted: 2,
        max_turns: 15,
        created_at: "2026-11-10T00:00:00Z",
        content: {
          report_version: 1,
          session_mode: "strict",
          summary_overview: "Solid fundamentals.",
          coverage_status: "Partial",
          persona_id: "academic",
          persona_name: "The Academic Deep-Diver",
          question_assessments: [],
          competency_assessments: [],
          strengths: [],
          improvement_areas: [],
          unassessed_topics: [],
          recommendations: [],
        },
      },
    }),
  );
  await page.goto("/tracks/t1/report/s1");
  await expect(page.getByTestId("persona-header")).toHaveText(
    "Interviewed by The Academic Deep-Diver",
  );
});
