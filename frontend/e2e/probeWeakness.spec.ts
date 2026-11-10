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
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({
      json: {
        dashboard: {
          completed_interviews: 1,
          average_score: 70,
          total_questions_attempted: 2,
          strongest_skills: [],
          skills_needing_improvement: ["recursion"],
          recommended_topics: [],
        },
        assessments: [],
      },
    }),
  );
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/tracks**", (route) => {
    if (route.request().url().includes("/weaknesses")) {
      return route.fulfill({
        json: {
          track_id: "t1",
          has_data: true,
          weak: [{ concept: "recursion", status: "weak", last_coverage: "partial" }],
          improving: [],
          mastered: [],
          top_weak: [{ concept: "recursion", status: "weak", last_coverage: "partial" }],
          recommended_practice: [
            {
              concept: "recursion",
              status: "weak",
              study_topics: ["base cases"],
              practice_themes: ["trace a recursive call"],
            },
          ],
        },
      });
    }
    if (route.request().url().includes("/progression")) {
      return route.fulfill({
        json: { track_id: "t1", strict_completed: 1, guided_state: "LOCKED" },
      });
    }
    if (route.request().url().includes("/open-session")) {
      return route.fulfill({ json: { session: null } });
    }
    return route.fulfill({ json: [TRACK] });
  });
  await page.route("**/api/v1/vault/items", (route) =>
    route.fulfill({
      json: [
        {
          id: "v1",
          category: "project",
          title: "Campus app",
          details: { stack: "FastAPI" },
        },
      ],
    }),
  );
});

test("start popup toggles enable and disable correctly", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview" }).click();
  await expect(page.getByText("Use my resume and projects")).toBeVisible();
  await expect(page.getByLabel("Use my resume and projects")).toBeChecked();
  await expect(page.getByLabel("Focus on weak areas")).not.toBeDisabled();
  await page.getByLabel("Focus on weak areas").check();
  await expect(page.getByLabel("Focus on weak areas")).toBeChecked();
});

test("interview shows probe chip", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          max_turns: 15,
          duration_minutes: 60,
          created_at: "2026-11-10T10:00:00Z",
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Hashmaps",
            question: "You mentioned using a hash map. What is the lookup cost?",
            question_type: "conceptual",
            origin: "answer_probe",
            probe_label: "Follow-up on your answer",
            answer: null,
          },
        ],
      },
    }),
  );
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByText("Follow-up on your answer")).toBeVisible();
});

test("report diagnostics render and Practice weak areas opens popup", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({
      json: {
        id: "r1",
        session_id: "s1",
        created_at: "2026-11-10T11:00:00Z",
        overall_score: 70,
        content: {
          report_version: 1,
          session_mode: "strict",
          summary_overview: "Solid start.",
          coverage_status: "PARTIAL",
          question_assessments: [],
          competency_assessments: [],
          strengths: ["Clear structure"],
          improvement_areas: ["Recursion"],
          unassessed_topics: [],
          recommendations: ["Practice base cases"],
          diagnostics: {
            identified_weaknesses: [
              {
                concept: "recursion",
                status: "weak",
                evidence: [{ turn_index: 2, coverage: "partial" }],
                missing_concepts: ["base cases"],
              },
            ],
            strengths: [{ concept: "hashmaps", last_coverage: "good", trend: ["good"] }],
            area_score_history: [
              { session_id: "s0", areas: { recursion: 40, hashmaps: 75 } },
              { session_id: "s1", areas: { recursion: 55, hashmaps: 80 } },
            ],
            recommended_practice: [
              {
                concept: "recursion",
                status: "weak",
                study_topics: ["base cases"],
                practice_themes: ["trace calls"],
              },
            ],
          },
        },
      },
    }),
  );
  await page.goto("/tracks/t1/report/s1");
  await expect(page.getByRole("heading", { name: "Your diagnostic" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Progress over time" })).toBeVisible();
  const chart = page.getByRole("img", { name: "Progress over time by area" });
  await expect(chart).toBeVisible();
  await chart.locator("circle").first().focus();
  await page.getByRole("button", { name: "Practice weak areas" }).click();
  await expect(page.getByLabel("Focus on weak areas")).toBeChecked();
});

test("track page weak areas card and 375px layout", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await page.route("**/api/v1/tracks/t1", (route) =>
    route.fulfill({
      json: {
        track: TRACK,
        brief: {
          version: 1,
          content: {
            summary: "Graphs basics",
            competencies: [],
            question_areas: [],
            preparation_plan: [],
            candidate_angle_notes: "",
            question_bank: [],
          },
        },
      },
    }),
  );
  await page.goto("/tracks/t1");
  await expect(page.getByRole("heading", { name: "Weak areas" })).toBeVisible();
  await expect(page.getByText("recursion")).toBeVisible();
  const fits = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
  expect(fits).toBe(true);
});

test("dashboard progress shows weak area count", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Weak areas")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Interview Progress" })).toBeVisible();
});
