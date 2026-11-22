import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  onboarding_completed: true,
  preparation_preferences: { interests: ["backend"], target_role: "Backend Intern" },
};

const CAREER = {
  disclaimer: "Based on interview evidence — not a hiring prediction.",
  career_readiness: {
    level: "early",
    summary: "Early signal from one completed interview.",
    target_role: "Backend Intern",
    evidence_index: 28,
    evidence_method: "demonstrated concept coverage",
  },
  strengths: [{ concept: "REST APIs", last_coverage: "good", times_asked: 1 }],
  improvement_areas: [{ concept: "SQL", last_coverage: "none", times_asked: 1 }],
  developing: [{ concept: "Auth", last_coverage: "partial", times_asked: 1 }],
  not_yet_assessed: ["Caching"],
  progress: {
    available: false,
    reason: "Need at least two completed interviews for comparison.",
    comparison_note: "Scores are not compared until interviews are comparable.",
  },
  recommendations: [
    {
      topic: "SQL",
      why: "Weak coverage",
      evidence: "none",
      practice: "Write JOIN queries",
      track_subject: "Backend",
    },
  ],
  roadmap: [
    {
      order: 1,
      topic: "SQL",
      reason: "Gap",
      activity: "Practice joins",
      priority: "high",
      track_subject: "Backend",
    },
  ],
  next_actions: [
    {
      kind: "start_interview",
      title: "Practise SQL",
      reason: "Recent gap",
      action_label: "Start practice",
      href: "/",
    },
  ],
  knowledge_gaps: {
    demonstrated_weaknesses: [{ concept: "SQL" }],
    needs_improvement: [{ concept: "Auth" }],
    not_assessed: ["Caching"],
    claimed_skills_without_interview: ["Docker"],
    policy: {
      note: "Not-assessed and unverified claims are not weaknesses.",
    },
  },
  project_intelligence: {
    projects: [
      {
        name: "Music Database Management System",
        technologies: ["SQL", "Postgres"],
        contribution: "Schema design",
        needs_clarification: ["Clarify testing approach"],
        discussion_ready: false,
        evidence_kind: "claim",
      },
    ],
    note: "Project details are candidate claims until defended.",
  },
  project_defense: null,
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/me/career-intelligence", (route) =>
    route.fulfill({ json: CAREER }),
  );
  await page.route("**/api/v1/onboarding/review", (route) =>
    route.fulfill({
      json: {
        summary: "Focus on SQL and project clarification.",
        item_statuses: [],
        roadmap: [
          {
            id: "r1",
            title: "SQL joins",
            why: "Weak interview coverage",
            topics: ["SQL"],
            practise: "Write INNER and LEFT joins",
            track_type: "topic",
            subject: "SQL",
            action_label: "Start SQL practice",
            completion: "not_started",
          },
        ],
        next_action: {
          kind: "recommend_track",
          title: "Start SQL practice",
          reason: "Evidence shows a join gap",
          action_label: "Start practice",
          subject: "SQL",
          track_type: "topic",
        },
      },
    }),
  );
  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({
      json: {
        dashboard: {
          completed_interviews: 1,
          average_score: 62,
          total_questions_attempted: 8,
          strongest_skills: ["REST APIs"],
          skills_needing_improvement: ["SQL"],
          recommended_topics: ["SQL"],
        },
        assessments: [
          {
            report_id: "rep1",
            session_id: "s1",
            track_id: "t1",
            track_subject: "Backend",
            created_at: "2026-11-10T12:00:00Z",
            session_mode: "strict",
            coverage_status: "partial",
            overall_score: 62,
            questions_attempted: 8,
            max_turns: 12,
            status: "completed",
            summary_overview: "Solid APIs; SQL needs work.",
            strengths: ["REST APIs"],
            improvement_areas: ["SQL"],
          },
        ],
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
          subject: "Backend",
          company: null,
          status: "active",
          created_at: "2026-11-01T00:00:00Z",
        },
      ],
    }),
  );
});

test("dashboard shows competency categories, roadmap, projects, and history", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("competency-overview")).toBeVisible();
  await expect(page.getByTestId("competency-claims")).toContainText("Docker");
  await expect(page.getByTestId("competency-not-assessed")).toContainText("Caching");
  await expect(page.getByTestId("dashboard-roadmap")).toContainText("SQL joins");
  await expect(page.getByTestId("dashboard-roadmap")).toContainText("Not started");
  await expect(page.getByTestId("project-prep-panel")).toContainText(
    "Music Database Management System",
  );
  await expect(page.getByTestId("career-preparation-loop")).toContainText(
    "Start SQL practice",
  );
  await expect(page.getByTestId("dashboard-interview-history")).toContainText("Backend");
  await expect(page.getByTestId("dashboard-interview-history")).toContainText("strict");
  await expect(
    page.getByTestId("dashboard-interview-history").getByRole("link", {
      name: /View feedback report/i,
    }),
  ).toHaveAttribute("href", "/tracks/t1/report/s1");
});

test("dashboard empty history and career error states", async ({ page }) => {
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
  await page.route("**/api/v1/me/career-intelligence", (route) =>
    route.fulfill({ status: 503, json: { detail: "busy" } }),
  );
  await page.goto("/");
  await expect(page.getByTestId("dashboard-assessments-empty")).toBeVisible();
  await expect(page.getByTestId("career-intelligence-error")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" }).first()).toBeVisible();
});

test("dashboard is usable on mobile width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/");
  await expect(page.getByTestId("competency-overview")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(overflow).toBeLessThanOrEqual(376);
});
