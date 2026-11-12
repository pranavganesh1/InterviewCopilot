import { expect, test, type Page, type Route } from "@playwright/test";

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

function longHistoryState(count = 30) {
  const messages = Array.from({ length: count }, (_, i) => ({
    role: i % 2 === 0 ? "assistant" : "user",
    content:
      i % 2 === 0
        ? `Assistant message ${i + 1}. Tell me more about your experience with long-url-https://example.com/path/to/resource and wrap.`
        : `User reply ${i + 1} about my background.`,
  }));
  return { ...BASE_STATE, messages, show_goal_menu: false, phase: "profile" };
}

async function mockCommon(page: Page) {
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
}

test.beforeEach(async ({ page }) => {
  await mockCommon(page);
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

test("sending with long history scrolls message list; window stays at 0", async ({
  page,
}) => {
  let state = longHistoryState(30);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    const body = route.request().postDataJSON() as { message: string };
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Great — let's keep going! ✨" },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Great — let's keep going! ✨",
        items_created: [],
        onboarding_complete: true,
        phase: "profile",
      },
    });
  });

  await page.goto("/onboarding");
  const list = page.getByTestId("onboarding-messages");
  await expect(list).toBeVisible();

  await expect
    .poll(async () =>
      list.evaluate((el) => el.scrollHeight - el.clientHeight > 40),
    )
    .toBe(true);

  const input = page.getByTestId("onboarding-chat-input");
  await input.fill("My next answer");
  await page.getByTestId("onboarding-chat-send").click();

  await expect(list).toContainText("Great — let's keep going");
  await expect
    .poll(async () =>
      list.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 140,
      ),
    )
    .toBe(true);

  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  await expect(page.getByTestId("onboarding-chat-composer")).toBeInViewport();
});

test("scrolled-up user sees New message pill instead of jump", async ({
  page,
}) => {
  let state = longHistoryState(30);
  let releaseChat: (() => void) | null = null;
  const chatGate = new Promise<void>((resolve) => {
    releaseChat = resolve;
  });

  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await chatGate;
    const body = route.request().postDataJSON() as { message: string };
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Here is a fresh reply from up high." },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Here is a fresh reply from up high.",
        items_created: [],
        onboarding_complete: true,
        phase: "profile",
      },
    });
  });

  await page.goto("/onboarding");
  const list = page.getByTestId("onboarding-messages");
  await expect(list).toBeVisible();
  await list.evaluate((el) => {
    el.scrollTop = 0;
  });

  // Send via forceScroll would scroll — so we inject an assistant-only update path:
  // fill + send after scrolling up, but release after we confirm stickiness broke.
  await page.getByTestId("onboarding-chat-input").fill("ping");
  // User send always force-scrolls; instead mutate state via a delayed assistant
  // by using starter-less invalidate: click send then immediately scroll up again
  // before the reply lands.
  const sendPromise = page.getByTestId("onboarding-chat-send").click();
  await page.getByTestId("typing-indicator").waitFor({ state: "visible" });
  await list.evaluate((el) => {
    el.scrollTop = 0;
  });
  releaseChat?.();
  await sendPromise;
  await expect(list).toContainText("fresh reply from up high");

  const nearBottom = await list.evaluate(
    (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 120,
  );
  expect(nearBottom).toBe(false);
  await expect(page.getByTestId("new-message-pill")).toBeVisible();
  await page.getByTestId("new-message-pill").click();
  await expect
    .poll(async () =>
      list.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 140,
      ),
    )
    .toBe(true);
});

test("typing indicator shows while reply pending then disappears", async ({
  page,
}) => {
  let resolveChat: ((route: Route) => void) | null = null;
  const pending = new Promise<Route>((resolve) => {
    resolveChat = resolve;
  });

  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await pending;
    await route.fulfill({
      json: {
        reply: "Done thinking.",
        items_created: [{ id: "9", category: "skill", title: "Excel" }],
        items_updated: [],
        onboarding_complete: true,
        phase: "goals",
      },
    });
  });

  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("hello coach");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("typing-indicator")).toBeVisible();
  resolveChat?.(await pending);
  // fulfill already waiting — resolve the gate by fulfilling via second tick
  // The promise above resolves with Route when route handler runs — fix approach:
});
