import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  professional_title: "",
  introduction: "",
  skills: [],
  education: "",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
});

test("Finish Assessment & Exit confirms, completes, and opens report", async ({
  page,
}) => {
  const turns = [
    {
      turn_index: 1,
      question_area: "Hashmaps",
      question: "Explain hash collisions.",
      answer: "Chaining stores collisions in a list.",
      evaluation: {
        coverage: "good",
        strengths: ["Clear"],
        gaps: [],
      },
    },
    {
      turn_index: 2,
      question_area: "Hashmaps",
      question: "How would you resolve one?",
      answer: null,
      evaluation: null,
    },
  ];
  let completed = false;

  await page.route("**/api/v1/sessions/s1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: completed ? "completed" : "in_progress",
          max_turns: 15,
        },
        turns,
      },
    }),
  );
  await page.route("**/api/v1/sessions/s1/complete", async (route) => {
    completed = true;
    await route.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "completed",
          max_turns: 15,
        },
      },
    });
  });
  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({
      json: {
        id: "r1",
        session_id: "s1",
        created_at: "2026-11-04T00:00:00Z",
        overall_score: 75,
        questions_attempted: 1,
        content: {
          report_version: 1,
          session_mode: "strict",
          summary_overview: "Early exit after one solid answer.",
          coverage_status: "PARTIAL",
          question_assessments: [
            {
              turn_index: 1,
              coverage: "good",
              observation: "Explained chaining",
              evidence_excerpt: "list",
            },
          ],
          competency_assessments: [],
          strengths: ["Clear structure"],
          improvement_areas: ["Cover more topics"],
          unassessed_topics: ["Trees"],
          recommendations: ["Continue with open addressing"],
        },
      },
    }),
  );

  await page.goto("/tracks/t1/interview/s1");
  await expect(
    page.getByRole("button", { name: "Finish Assessment & Exit" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit Answer" })).toBeVisible();

  await page.getByTestId("finish-assessment-exit").click();
  await expect(page.getByTestId("finish-exit-confirm")).toBeVisible();
  await expect(
    page.getByText(/submitted answers will be evaluated/i),
  ).toBeVisible();

  await page.getByTestId("confirm-finish-exit").click();
  await expect(page).toHaveURL(/\/tracks\/t1\/report\/s1/);
  await expect(page.getByTestId("report-status")).toHaveAttribute(
    "data-state",
    "ready",
  );
  await expect(page.getByText("Overall score")).toBeVisible();
  await expect(page.getByText("75%")).toBeVisible();
  await expect(page.getByText("Early exit after one solid answer.")).toBeVisible();
});

test("profile nav opens dashboard empty state", async ({ page }) => {
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
  await page.goto("/");
  await page.getByTestId("nav-profile").click();
  await page.getByRole("menuitem", { name: "My Profile" }).click();
  await expect(page).toHaveURL(/\/profile/);
  await expect(page.getByText("No completed assessments yet")).toBeVisible();
});
