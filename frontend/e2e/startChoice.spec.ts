import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

const TRACK = {
  track: {
    id: "t1",
    track_type: "topic",
    subject: "Data Structures & Algorithms",
    company: null,
    status: "active",
    created_at: "2026-11-03T00:00:00Z",
  },
  brief: {
    version: 1,
    content: {
      summary: "DSA basics",
      competencies: [],
      question_areas: [],
      preparation_plan: [],
      candidate_angle_notes: "",
      question_bank: [],
    },
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
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
  await page.route("**/api/v1/tracks/t1", (route) => route.fulfill({ json: TRACK }));
  await page.route("**/api/v1/tracks/t1/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );
});

test("an unfinished session offers resume, finish, and a new interview", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s-open",
          mode: "strict",
          status: "in_progress",
          question_index: 2,
          max_turns: 15,
          answered_count: 1,
        },
      },
    }),
  );
  await page.route("**/api/v1/sessions/s-open", (route) =>
    route.fulfill({
      json: {
        session: { id: "s-open", track_id: "t1", mode: "strict", status: "in_progress" },
        turns: [
          {
            turn_index: 2,
            question_area: "Hashmaps",
            question: "Same question after resume",
            answer: null,
            evaluation: null,
          },
        ],
      },
    }),
  );

  await page.goto("/tracks/t1");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Unfinished interview: Q2/15 (strict)")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Resume" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Finish and get feedback" })).toBeVisible();
  await dialog.getByRole("button", { name: "Start a new interview" }).click();
  await expect(dialog.getByText("Interview duration")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Start strict interview" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Guided locked" })).toBeVisible();

  await dialog.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByText("Same question after resume")).toBeVisible();
});

test("a track with no open session shows the start options", async ({ page }) => {
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );
  await page.goto("/tracks/t1");
  await expect(page.getByRole("button", { name: "Resume" })).toHaveCount(0);
  await expect(page.getByText("Interview duration")).toBeVisible();
  await expect(page.getByRole("button", { name: "Start strict interview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Guided locked" })).toBeVisible();
});
