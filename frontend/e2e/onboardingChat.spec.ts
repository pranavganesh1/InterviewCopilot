import { expect, test, type Page } from "@playwright/test";

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
    {
      id: "1",
      category: "project",
      title: "QCGNN",
      source: "resume",
      details: {
        purpose: "Quantum graph neural network research",
        technologies: "PyTorch, Python, CUDA",
        outcome: "Improved accuracy on benchmark graphs",
      },
    },
    { id: "2", category: "skill", title: "Python", source: "resume" },
    {
      id: "3",
      category: "education",
      title: "B.Tech CSE",
      source: "resume",
      details: { institution: "Demo University", dates: "2021–2025" },
    },
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
  await expect(page.getByRole("heading", { name: "Chanakya" })).toBeVisible();
  await expect(page.getByText("Interview Coach")).toBeVisible();
  await expect(page.getByTestId("resume-upload-bar")).toBeVisible();
  await expect(page.getByTestId("resume-upload-dropzone")).toBeVisible();
  await expect(page.getByTestId("onboarding-status-chip")).toContainText(
    "In progress",
  );

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
        detail: {
          message: "Something is wrong on our side.",
          cause: "unknown",
          retry_after_seconds: 15,
        },
      }),
    });
  });

  await page.goto("/onboarding");
  const input = page.getByTestId("onboarding-chat-input");
  await input.fill("I want to practice Python");
  await page.getByTestId("onboarding-chat-send").click();

  await expect(page.getByTestId("onboarding-chat-error")).toContainText(
    "Something is wrong on our side",
  );
  await expect(page.getByTestId("onboarding-chat-retry")).toBeVisible();
  await expect(page.getByTestId("message-not-delivered")).toBeVisible();
  await expect(page.getByTestId("toast-error")).toHaveCount(0);
  await expect(input).toHaveValue("I want to practice Python");
  expect(chatCalls).toBe(1);

  await page.getByTestId("onboarding-chat-retry").click();
  await expect.poll(() => chatCalls).toBe(2);
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

  await page.getByTestId("onboarding-chat-input").fill("My next answer");
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
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });

  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await gate;
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

  await page.getByTestId("onboarding-chat-input").fill("ping");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("typing-indicator")).toBeVisible();
  await list.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });
  release();
  await expect(list).toContainText("fresh reply from up high");
  await list.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });

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

test("typing indicator shows while pending then disappears; vault chip appears", async ({
  page,
}) => {
  let state = { ...BASE_STATE };
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });

  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await gate;
    const body = route.request().postDataJSON() as { message: string };
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Saved Excel to your vault." },
      ],
      vault_items: [
        ...state.vault_items,
        { id: "9", category: "skill", title: "Excel", source: "chat" },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Saved Excel to your vault.",
        items_created: [{ id: "9", category: "skill", title: "Excel" }],
        items_updated: [],
        onboarding_complete: true,
        phase: "goals",
      },
    });
  });

  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("I know Excel");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("typing-indicator")).toBeVisible();
  release();
  await expect(page.getByTestId("typing-indicator")).toHaveCount(0);
  await expect(page.getByTestId("vault-add-chips")).toContainText(
    "Added to your profile: Excel",
  );
});

test("Enter sends, Shift+Enter newlines, send disabled when empty/loading, textarea caps at 5 lines", async ({
  page,
}) => {
  let state = { ...BASE_STATE };
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });

  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await gate;
    const body = route.request().postDataJSON() as { message: string };
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Got your note." },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Got your note.",
        items_created: [],
        onboarding_complete: true,
        phase: "goals",
      },
    });
  });

  await page.goto("/onboarding");
  const input = page.getByTestId("onboarding-chat-input");
  const send = page.getByTestId("onboarding-chat-send");
  await expect(send).toBeDisabled();

  await input.press("Shift+Enter");
  await input.type("line two");
  await expect(input).toHaveValue(/\nline two/);

  await input.fill("one\ntwo\nthree\nfour\nfive\nsix");
  const height = await input.evaluate((el) => (el as HTMLTextAreaElement).offsetHeight);
  const line = await input.evaluate((el) => {
    const lh = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    return lh * 5 + 24;
  });
  expect(height).toBeLessThanOrEqual(line + 4);

  await input.fill("Send with enter");
  await expect(send).toBeEnabled();
  await input.press("Enter");
  await expect(page.getByTestId("typing-indicator")).toBeVisible();
  await expect(send).toBeDisabled();
  release();
  await expect(page.getByTestId("onboarding-messages")).toContainText(
    "Got your note",
  );
});

test("emoji picker inserts at cursor and closes on Escape", async ({ page }) => {
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );
  await page.goto("/onboarding");
  const input = page.getByTestId("onboarding-chat-input");
  await input.fill("Hi ");
  await page.getByTestId("emoji-picker-button").click();
  await expect(page.getByTestId("emoji-picker")).toBeVisible();
  await page.getByRole("option", { name: "Insert 🚀" }).click();
  await expect(input).toHaveValue("Hi 🚀");
  await expect(page.getByTestId("emoji-picker")).toHaveCount(0);

  await page.getByTestId("emoji-picker-button").click();
  await expect(page.getByTestId("emoji-picker")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("emoji-picker")).toHaveCount(0);
});

test("reduced motion skips bubble animation; history loads at bottom; no horizontal overflow at 375", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 375, height: 720 });

  const state = longHistoryState(24);
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );

  await page.goto("/onboarding");
  const list = page.getByTestId("onboarding-messages");
  await expect(list).toBeVisible();

  await expect
    .poll(async () =>
      list.evaluate(
        (el) => el.scrollHeight - el.scrollTop - el.clientHeight < 140,
      ),
    )
    .toBe(true);

  const animated = await list.evaluate(
    (el) =>
      el.querySelectorAll(
        ".coach-bubble-enter-assistant, .coach-bubble-enter-user",
      ).length,
  );
  expect(animated).toBe(0);

  const overflowX = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth > doc.clientWidth + 1;
  });
  expect(overflowX).toBe(false);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);

  await expect(page.getByTestId("mobile-pane-switcher")).toBeVisible();
  await page.getByTestId("mobile-pane-profile").click();
  await expect(page.getByTestId("profile-panel")).toBeVisible();
  await expect(page.getByTestId("onboarding-chat-panel")).toBeHidden();
  await page.getByTestId("mobile-pane-chat").click();
  await expect(page.getByTestId("onboarding-chat-input")).toBeVisible();
});

async function countScrollableContainers(page: Page) {
  return page.evaluate(() => {
    const nodes = Array.from(document.querySelectorAll("body *"));
    return nodes.filter((el) => {
      const style = getComputedStyle(el);
      const oy = style.overflowY;
      if (oy !== "auto" && oy !== "scroll" && oy !== "overlay") return false;
      return (el as HTMLElement).scrollHeight > (el as HTMLElement).clientHeight + 1;
    }).length;
  });
}

test("workspace is single-screen with profile tabs, ring, and no page scroll", async ({
  page,
}) => {
  const rich = {
    ...BASE_STATE,
    onboarding_finished: true,
    onboarding_completed_at: "2026-11-01T10:00:00Z",
    show_goal_menu: false,
    phase: "ready",
  };
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: rich }),
  );

  for (const size of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
  ] as const) {
    await page.setViewportSize(size);
    await page.goto("/onboarding");

    await expect
      .poll(async () =>
        page.evaluate(
          () => document.documentElement.scrollHeight <= window.innerHeight + 1,
        ),
      )
      .toBe(true);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);

    expect(await countScrollableContainers(page)).toBeLessThanOrEqual(2);

    await expect(page.getByText("Profile setup")).toHaveCount(0);
    await expect(page.getByText("Your profile vault")).toHaveCount(0);
    await expect(page.getByTestId("onboarding-progress")).toHaveCount(0);
    await expect(page.getByTestId("onboarding-finished-banner")).toHaveCount(0);
    await expect(page.getByTestId("onboarding-status-chip")).toContainText(
      "Onboarding complete",
    );
    await expect(page.getByTestId("profile-completeness-ring")).toBeVisible();
    await expect(page.getByTestId("profile-tabs")).toBeVisible();

    await page.getByTestId("profile-tab-skills").click();
    await expect(page.getByTestId("profile-tabpanel-skills")).toContainText(
      "Python",
    );
    await expect(page.getByTestId("profile-tabpanel-projects")).toHaveCount(0);

    await page.getByTestId("profile-tab-projects").click();
    await expect(page.getByTestId("profile-tabpanel-projects")).toBeVisible();
    await page.getByTestId("vault-project-card-1").getByLabel("Expand project").click();
    await expect(page.getByTestId("vault-project-card-1")).toContainText("Problem");
    await expect(page.getByTestId("vault-project-card-1")).toContainText(
      "Quantum graph neural network research",
    );
    await expect(page.getByTestId("vault-project-card-1")).not.toContainText(
      "outcome:",
    );

    await expect(page.getByTestId("resume-upload-bar")).toBeVisible();
    await expect(page.getByTestId("resume-upload-dropzone")).toBeVisible();
    await page.getByTestId("profile-tab-resume").click();
    await expect(page.getByTestId("readiness-onboarding-card")).toBeVisible();
    await expect(page.getByTestId("go-to-tracks")).toBeVisible();
  }
});

test("resume drop zone shows error and success; Go to Tracks navigates", async ({
  page,
}) => {
  const rich = {
    ...BASE_STATE,
    onboarding_finished: true,
    onboarding_completed_at: "2026-11-01T10:00:00Z",
    show_goal_menu: false,
  };
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: rich }),
  );
  let resumeCalls = 0;
  await page.route("**/api/v1/vault/resume", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    resumeCalls += 1;
    const body = route.request().postData() || "";
    if (resumeCalls === 1 || body.includes("empty.pdf")) {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Empty PDF rejected",
          code: "empty_file",
        }),
      });
      return;
    }
    await route.fulfill({
      json: {
        items_created: [{ title: "SQL" }],
        items_skipped: 0,
        welcome_seeded: false,
      },
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/onboarding");
  await expect(page.getByTestId("resume-upload-dropzone")).toBeVisible();

  await page.setInputFiles('input[type="file"][accept="application/pdf"]', {
    name: "empty.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF"),
  });
  await expect(page.getByTestId("resume-upload-error")).toContainText(
    "Empty PDF rejected",
  );

  await page.setInputFiles('input[type="file"][accept="application/pdf"]', {
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 " + "x".repeat(80)),
  });
  await expect(page.getByTestId("resume-upload-success")).toContainText(
    "Added 1 vault item",
  );

  await page.getByTestId("go-to-tracks").click();
  await expect(page).toHaveURL("/");
});

test("slow reply shows still thinking then timeout Not delivered", async ({
  page,
}) => {
  await page.clock.install();
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await gate;
    await route.fulfill({
      status: 503,
      body: JSON.stringify({ detail: "busy" }),
      contentType: "application/json",
    });
  });

  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("hello slow");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("typing-indicator")).toBeVisible();
  await page.clock.fastForward(8000);
  await expect(page.getByTestId("still-thinking")).toBeVisible();
  // Client timeout is 55s; release before abort so a real 503 is observed.
  await page.clock.fastForward(20000);
  release();
  await expect(page.getByTestId("message-not-delivered")).toBeVisible();
  await expect(page.getByTestId("onboarding-chat-error")).toBeVisible();
  await expect(page.getByTestId("toast-error")).toHaveCount(0);
});

test("empty reply shows fallback bubble", async ({ page }) => {
  let state = { ...BASE_STATE };
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
        { role: "assistant", content: "" },
      ],
    };
    await route.fulfill({
      json: {
        reply: "",
        items_created: [],
        onboarding_complete: true,
        phase: "goals",
      },
    });
  });
  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("ping");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("onboarding-messages")).toContainText(
    "I didn't catch that",
  );
});

test("idle nudge appears, fills input without sending, respects visibility", async ({
  page,
}) => {
  await page.clock.install();
  let chatCalls = 0;
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: { ...BASE_STATE, show_goal_menu: false, phase: "profile" },
    }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    chatCalls += 1;
    await route.fulfill({
      json: { reply: "ok", items_created: [], onboarding_complete: true },
    });
  });

  await page.goto("/onboarding");
  await expect(page.getByTestId("onboarding-chat-input")).toBeVisible();
  await expect(page.getByTestId("onboarding-messages")).toContainText("QCGNN");
  await page.clock.fastForward(45000);
  await expect(page.getByTestId("idle-nudge")).toBeVisible();
  await page.getByTestId("idle-nudge-chip").first().click();
  await expect(page.getByTestId("onboarding-chat-input")).not.toHaveValue("");
  expect(chatCalls).toBe(0);

  await page.getByTestId("onboarding-chat-input").fill("typing clears nudge");
  await expect(page.getByTestId("idle-nudge")).toHaveCount(0);

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await page.clock.fastForward(200000);
  await expect(page.getByTestId("idle-nudge")).toHaveCount(0);
});

test("offline and online show connection toasts", async ({ page }) => {
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: BASE_STATE }),
  );
  await page.goto("/onboarding");
  await expect(page.getByTestId("onboarding-chat-input")).toBeVisible();
  await page.evaluate(() => window.dispatchEvent(new Event("offline")));
  await expect(page.getByTestId("toast-error")).toContainText("Connection lost");
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.getByTestId("toast-success")).toContainText(
    "Connection restored",
  );
});

test("trailing unanswered user message shows inline recovery, not toast", async ({
  page,
}) => {
  let chatCalls = 0;
  let state = {
    ...BASE_STATE,
    show_goal_menu: false,
    phase: "profile" as const,
    messages: [
      ...BASE_STATE.messages,
      { role: "user", content: "give both" },
      { role: "user", content: "lets us start" },
    ],
  };
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    chatCalls += 1;
    const body = route.request().postDataJSON() as { message: string };
    const reply = "Kept both. Which project should we explore next?";
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: reply },
      ],
    };
    await route.fulfill({
      json: {
        reply,
        items_created: [],
        onboarding_complete: true,
      },
    });
  });
  await page.goto("/onboarding");
  await expect(page.getByTestId("toast-error")).toHaveCount(0);
  await expect(page.getByTestId("message-not-delivered")).toBeVisible();
  await expect(page.getByTestId("onboarding-chat-error")).toContainText(
    "Last reply didn't arrive",
  );
  await page.getByTestId("onboarding-chat-retry").click();
  await expect.poll(() => chatCalls).toBe(1);
  await expect(page.getByTestId("onboarding-messages")).toContainText(
    "Kept both",
  );
});

test("busy 503 shows countdown, disables Retry, auto-retries once", async ({
  page,
}) => {
  await page.clock.install();
  let chatCalls = 0;
  let state = {
    ...BASE_STATE,
    show_goal_menu: false,
    phase: "profile" as const,
    messages: [...BASE_STATE.messages],
  };
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    chatCalls += 1;
    const body = route.request().postDataJSON() as {
      message: string;
      message_id?: string;
    };
    if (chatCalls === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            message: "The interview coach is temporarily busy.",
            cause: "rate_limited",
            retry_after_seconds: 3,
          },
        }),
      });
      return;
    }
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Back online — what next?" },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Back online — what next?",
        items_created: [],
        onboarding_complete: true,
      },
    });
  });

  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("Tell me about Python");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("onboarding-chat-error")).toContainText(
    "Temporary request limit",
  );
  await expect(page.getByTestId("retry-countdown")).toBeVisible();
  await expect(page.getByTestId("onboarding-chat-retry")).toBeDisabled();
  await page.clock.fastForward(3000);
  await expect.poll(() => chatCalls).toBe(2);
  await expect(page.getByTestId("onboarding-messages")).toContainText(
    "Back online",
  );
  const userBubbles = page.locator(
    '[data-testid="onboarding-messages"] >> text=Tell me about Python',
  );
  await expect(userBubbles).toHaveCount(1);
});

test("blocks double send of identical text while pending", async ({ page }) => {
  let chatCalls = 0;
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: { ...BASE_STATE, show_goal_menu: false } }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    chatCalls += 1;
    await gate;
    await route.fulfill({
      json: {
        reply: "Only once",
        items_created: [],
        onboarding_complete: true,
      },
    });
  });
  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("I'd like to practise Python");
  await page.getByTestId("onboarding-chat-send").click();
  await page.getByTestId("onboarding-chat-send").click({ force: true });
  await page.getByTestId("onboarding-chat-input").press("Enter");
  expect(chatCalls).toBe(1);
  release();
  await expect(page.getByTestId("typing-indicator")).toHaveCount(0);
});

test("practise reply shows Let's start interview popup", async ({ page }) => {
  let state = {
    ...BASE_STATE,
    show_goal_menu: false,
    phase: "profile" as const,
  };
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
        {
          role: "assistant",
          content: "Great — we can run a focused interview on Python.",
        },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Great — we can run a focused interview on Python.",
        items_created: [],
        onboarding_complete: true,
        offer_start_interview: {
          subject: "Python",
          track_type: "topic",
          reason: "practise",
        },
      },
    });
  });
  await page.goto("/onboarding");
  await page.getByTestId("onboarding-chat-input").fill("I'd like to practise Python");
  await page.getByTestId("onboarding-chat-send").click();
  await expect(page.getByTestId("start-interview-offer")).toBeVisible();
  await expect(page.getByTestId("start-interview-offer")).toContainText(
    "Let's start your interview",
  );
});

test("hidden tab title updates when reply arrives", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((r) => {
    release = r;
  });
  let state = { ...BASE_STATE };
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: state }),
  );
  await page.route("**/api/v1/onboarding/chat", async (route) => {
    await gate;
    const body = route.request().postDataJSON() as { message: string };
    state = {
      ...state,
      messages: [
        ...state.messages,
        { role: "user", content: body.message },
        { role: "assistant", content: "Back with a reply" },
      ],
    };
    await route.fulfill({
      json: {
        reply: "Back with a reply",
        items_created: [],
        onboarding_complete: true,
      },
    });
  });

  await page.goto("/onboarding");
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
  });
  await page.getByTestId("onboarding-chat-input").fill("hi");
  await page.getByTestId("onboarding-chat-send").click();
  release();
  await expect
    .poll(async () => page.evaluate(() => document.title))
    .toContain("New reply from Chanakya");
});
