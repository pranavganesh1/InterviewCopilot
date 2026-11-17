import { expect, test } from "@playwright/test";

/**
 * Fix 4: mocked API failures must show recoverable error UI — never empty
 * success states or an active interview dock.
 */

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

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

const SESSION_OK = {
  session: {
    id: "s1",
    track_id: "t1",
    mode: "strict",
    status: "in_progress",
    max_turns: 15,
  },
  turns: [
    {
      turn_index: 1,
      question_area: "Hashmaps",
      question: "Explain hash collisions.",
      answer: null,
      evaluation: null,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
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
  await page.route("**/api/v1/onboarding/review", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        json: {
          summary: "",
          item_statuses: [],
          roadmap: [],
          next_action: null,
        },
      });
    }
    return route.fulfill({ json: {} });
  });
  await page.route("**/api/v1/tracks", (route) =>
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "topic",
          subject: "Backend Basics",
          company: null,
          status: "active",
          created_at: "2026-11-03T00:00:00Z",
          brief_version: 1,
        },
      ],
    }),
  );
});

test("InterviewPage: session 500 shows error UI without answer dock; Retry recovers", async ({
  page,
}) => {
  let sessionCalls = 0;
  await page.route("**/api/v1/sessions/s1", (route) => {
    sessionCalls += 1;
    // Initial load (+ react-query retry) fail; after Retry button, succeed.
    if (sessionCalls <= 2) {
      return route.fulfill({
        status: 500,
        json: { detail: "Session store unavailable" },
      });
    }
    return route.fulfill({ json: SESSION_OK });
  });

  await page.goto("/tracks/t1/interview/s1");

  await expect(page.getByTestId("interview-session-error")).toBeVisible();
  await expect(page.getByRole("alert")).toContainText(/Session store unavailable|Couldn’t load/i);
  await expect(page.getByTestId("interview-action-dock")).toHaveCount(0);
  await expect(page.getByTestId("submit-answer")).toHaveCount(0);
  await expect(page.getByTestId("interview-session")).toHaveCount(0);

  await page.getByTestId("interview-session-retry").click();
  await expect(page.getByTestId("interview-session")).toBeVisible();
  await expect(page.getByText("Explain hash collisions.")).toBeVisible();
  await expect(page.getByTestId("interview-action-dock")).toBeVisible();
});

test("Dashboard: open-sessions failure shows error; assessments empty success stays empty", async ({
  page,
}) => {
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({
      status: 500,
      json: { detail: "Open sessions unavailable" },
    }),
  );
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({ json: EMPTY_ASSESSMENTS }),
  );

  await page.goto("/");

  await expect(page.getByTestId("dashboard-open-sessions-error")).toBeVisible();
  await expect(page.getByTestId("dashboard-open-sessions-error")).toContainText(
    /Open sessions unavailable|Couldn’t load open interviews/i,
  );
  await expect(page.getByTestId("dashboard-open-sessions-empty")).toHaveCount(0);
  await expect(page.getByTestId("dashboard-assessments-empty")).toBeVisible();
  await expect(page.getByTestId("dashboard-assessments-error")).toHaveCount(0);
});

test("Dashboard: assessments failure shows error; open-sessions success can stay empty", async ({
  page,
}) => {
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({
      status: 500,
      json: { detail: "Assessments unavailable" },
    }),
  );

  await page.goto("/");

  await expect(page.getByTestId("dashboard-assessments-error")).toBeVisible();
  await expect(page.getByTestId("dashboard-assessments-error")).toContainText(
    /Assessments unavailable|Couldn’t load assessments/i,
  );
  await expect(page.getByTestId("dashboard-assessments-empty")).toHaveCount(0);
  await expect(page.getByTestId("dashboard-open-sessions-empty")).toBeVisible();
  await expect(page.getByTestId("dashboard-open-sessions-error")).toHaveCount(0);
});

test("Dashboard: open-sessions Retry refetches without full reload", async ({ page }) => {
  let openCalls = 0;
  await page.route("**/api/v1/me/open-sessions", (route) => {
    openCalls += 1;
    if (openCalls <= 2) {
      return route.fulfill({
        status: 500,
        json: { detail: "Temporary open-sessions fault" },
      });
    }
    return route.fulfill({
      json: [
        {
          session_id: "sess-open",
          track_id: "t1",
          track_subject: "Backend Basics",
          mode: "strict",
          status: "in_progress",
          question_index: 2,
          max_turns: 15,
          answered_count: 1,
          created_at: "2026-11-08T10:00:00Z",
          duration_minutes: 60,
        },
      ],
    });
  });
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({ json: EMPTY_ASSESSMENTS }),
  );

  await page.goto("/");
  await expect(page.getByTestId("dashboard-open-sessions-error")).toBeVisible();

  await page.getByTestId("dashboard-open-sessions-retry").click();
  await expect(page.getByRole("link", { name: "Resume" })).toBeVisible();
  await expect(page.getByTestId("dashboard-open-sessions-error")).toHaveCount(0);
});
