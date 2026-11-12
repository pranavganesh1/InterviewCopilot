import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  onboarding_completed: false,
};

const BASE_STATE = {
  messages: [
    {
      role: "assistant",
      content:
        "Hey! 👋 I've reviewed your resume. You've got some really interesting experience — especially your “QCGNN” project! 🚀",
    },
  ],
  vault_items: [
    { id: "1", category: "project", title: "QCGNN", source: "resume" },
    { id: "2", category: "skill", title: "Python", source: "resume" },
    { id: "3", category: "education", title: "B.Tech CSE", source: "resume" },
  ],
  onboarding_complete: true,
  onboarding_finished: false,
  missing_categories: [],
  phase: "goals",
  show_goal_menu: true,
  has_resume_welcome: true,
  goal_interest_options: [
    { id: "technical", label: "💻 Technical Interviews" },
    { id: "skill", label: "🧠 Skill Practice" },
    { id: "project", label: "🚀 Project Deep Dive" },
    { id: "placement", label: "🎯 Internship & Placements" },
    { id: "behavioral", label: "💬 HR & Behavioral" },
  ],
  suggested_skills: ["Python", "SQL"],
  suggested_projects: ["QCGNN"],
  suggested_roles: ["ML Engineer"],
  suggested_technical_areas: ["Python", "SQL"],
  project_options: [{ id: "QCGNN", label: "QCGNN", subtitle: "PyTorch" }],
  project_aspect_options: [
    { id: "architecture", label: "Project architecture" },
  ],
  preparation_preferences: {
    interests: [],
    confirmed: false,
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
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

test("chat panel keeps a fixed scroll region and friendly coach chrome", async ({
  page,
}) => {
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );

  await page.goto("/onboarding");

  const panel = page.getByTestId("onboarding-chat-panel");
  await expect(panel).toBeVisible();
  await expect(page.getByText("Aiko · Interview Coach")).toBeVisible();

  const messages = page.getByTestId("onboarding-messages");
  await expect(messages).toBeVisible();
  await expect(messages).toContainText("QCGNN");
  const overflowY = await messages.evaluate(
    (el) => getComputedStyle(el).overflowY,
  );
  expect(["auto", "scroll", "overlay"]).toContain(overflowY);

  await expect(page.getByTestId("goal-interest-technical")).toContainText(
    "Technical",
  );
  await expect(page.getByTestId("onboarding-chat-input")).toBeVisible();
});

test("chat failure shows friendly retry and preserves typed message", async ({
  page,
}) => {
  let chatCalls = 0;
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    chatCalls += 1;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "The interview coach is temporarily busy. Please retry in about a minute.",
      }),
    });
  });

  await page.goto("/onboarding");
  const input = page.getByTestId("onboarding-chat-input");
  await input.fill("I want to practice Python");
  await page.getByTestId("onboarding-chat-send").click();

  await expect(page.getByTestId("onboarding-chat-error")).toContainText(
    "thoughts got interrupted",
  );
  await expect(page.getByTestId("onboarding-chat-retry")).toBeVisible();
  await expect(input).toHaveValue("I want to practice Python");
  expect(chatCalls).toBe(1);

  await page.getByTestId("onboarding-chat-retry").click();
  await expect
    .poll(() => chatCalls)
    .toBe(2);
  await expect(input).toHaveValue("I want to practice Python");
});
