import { expect, test } from "@playwright/test";

// Smoke tests run against the built app with the backend API mocked via route
// interception — they verify frontend behavior, not backend integration.

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
});

test("dashboard lists tracks from the API", async ({ page }) => {
  await page.route("**/api/v1/tracks", (route) =>
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "role",
          subject: "Backend Engineer Intern",
          company: null,
          status: "active",
          created_at: "2026-11-03T00:00:00Z",
          brief_version: 1,
        },
      ],
    }),
  );
  await page.goto("/");
  await expect(page.getByText("Backend Engineer Intern")).toBeVisible();
  await expect(page.getByText("Brief v1")).toBeVisible();
});

test("interview page renders question and submits answer", async ({ page }) => {
  // Stateful mock mirroring the backend: turns live server-side, evaluations
  // are persisted onto the answered turn.
  const turns = [
    {
      turn_index: 1,
      question_area: "Hashmaps",
      question: "Explain hash collisions.",
      answer: null as string | null,
      evaluation: null as Record<string, unknown> | null,
    },
  ];
  await page.route("**/api/v1/sessions/s1", (route) =>
    route.fulfill({
      json: {
        session: { id: "s1", track_id: "t1", mode: "strict", status: "in_progress" },
        turns,
      },
    }),
  );
  await page.route("**/api/v1/sessions/s1/turns", async (route) => {
    turns[0].answer = "Buckets store multiple entries...";
    turns[0].evaluation = {
      coverage: "partial",
      strengths: ["Clear structure"],
      gaps: ["No examples"],
    };
    turns.push({
      turn_index: 2,
      question_area: "Hashmaps",
      question: "How would you resolve one?",
      answer: null,
      evaluation: null,
    });
    await route.fulfill({
      json: {
        completed: false,
        evaluation: {
          coverage: "partial",
          strengths: ["Clear structure"],
          gaps: ["No examples"],
        },
        turn: turns[1],
      },
    });
  });

  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByText("Explain hash collisions.")).toBeVisible();

  await page.fill("textarea", "Buckets store multiple entries...");
  await page.getByRole("button", { name: "Submit Answer" }).click();

  await expect(page.getByTestId("evaluation-feedback")).toBeVisible();
  await expect(page.getByText("partial")).toBeVisible();
  await expect(page.getByText("No examples")).toBeVisible();
  await expect(page.getByText("How would you resolve one?")).toHaveCount(0);

  await page.getByRole("button", { name: "Next question" }).click();
  await expect(page.getByText("How would you resolve one?")).toBeVisible();
});

test("report page shows competencies and recommendations", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({
      json: {
        id: "r1",
        session_id: "s1",
        created_at: "2026-11-03T00:00:00Z",
        content: {
          report_version: 1,
          session_mode: "strict",
          summary_overview: "Solid fundamentals overall.",
          coverage_status: "PARTIAL",
          question_assessments: [
            {
              turn_index: 1,
              coverage: "good",
              observation: "Explained collisions well",
              evidence_excerpt: "chaining resolves",
            },
          ],
          competency_assessments: [
            {
              competency_name: "DSA",
              assessment_status: "ASSESSED",
              level: "solid",
              observation: "Good grasp",
              confidence: "MEDIUM",
            },
          ],
          strengths: ["Clear explanations"],
          improvement_areas: ["Complexity analysis"],
          unassessed_topics: ["Graphs"],
          recommendations: ["Practice Big-O estimation daily"],
        },
      },
    }),
  );

  await page.goto("/tracks/t1/report/s1");
  await expect(page.getByText("Solid fundamentals overall.")).toBeVisible();
  await expect(page.getByText("solid").first()).toBeVisible();
  await expect(page.getByText("Practice Big-O estimation daily")).toBeVisible();
  await expect(page.getByText(/Not assessed in this session/)).toBeVisible();
});
