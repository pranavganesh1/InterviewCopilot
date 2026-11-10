import { expect, test, type Page } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

function openRow(id: string, answered: number, minutesAgo: number) {
  const created = new Date(Date.now() - minutesAgo * 60_000).toISOString();
  return {
    id,
    mode: "strict",
    status: "in_progress",
    question_index: answered + 1,
    max_turns: 15,
    answered_count: answered,
    created_at: created,
    duration_minutes: 60,
  };
}

async function mockShell(page: Page) {
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
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "topic",
          subject: "array",
          company: null,
          status: "active",
          created_at: "2026-11-03T00:00:00Z",
          brief_version: 1,
        },
      ],
    }),
  );
  await page.route("**/api/v1/tracks/t1/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );
}

test("five unfinished sessions show one main card plus four older", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockShell(page);
  const sessions = [
    openRow("s1", 0, 5),
    openRow("s2", 0, 20),
    openRow("s3", 0, 40),
    openRow("s4", 1, 60),
    openRow("s5", 0, 90),
  ];
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: sessions[0], sessions } }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Unfinished interview", { exact: true })).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: /4 older unfinished interviews/ }),
  ).toBeVisible();
  await expect(dialog.getByText(/Q1\/15 · 0 answered · strict/).first()).toBeVisible();

  await dialog.getByRole("button", { name: /4 older unfinished interviews/ }).click();
  await expect(dialog.getByRole("button", { name: "Resume" }).first()).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box).toBeTruthy();
  expect((box?.height ?? 0) <= 812 * 0.9).toBeTruthy();

  await dialog.getByRole("button", { name: "Close empty interviews" }).click();
  await expect(
    dialog.getByText(/Close interviews with no answers on this track/i),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: /^Close empty interviews$/ }),
  ).toBeVisible();

  const overflow = await page.evaluate(() => {
    const el = document.querySelector('[role="dialog"]');
    if (!(el instanceof HTMLElement)) return true;
    return el.scrollWidth > el.clientWidth + 1;
  });
  expect(overflow).toBe(false);
});

test("double clicking Start sends one request", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null, sessions: [] } }),
  );

  let starts = 0;
  await page.route("**/api/v1/tracks/t1/sessions", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    starts += 1;
    await new Promise((r) => setTimeout(r, 400));
    await route.fulfill({
      status: 201,
      json: {
        session: {
          id: "s-new",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          max_turns: 15,
          duration_minutes: 60,
          created_at: new Date().toISOString(),
        },
        turn: {
          turn_index: 1,
          question_area: "Arrays",
          question: "What is an array?",
        },
      },
    });
  });
  await page.route("**/api/v1/sessions/s-new", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s-new",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          duration_minutes: 60,
          created_at: new Date().toISOString(),
        },
        turns: [
          {
            turn_index: 1,
            question_area: "Arrays",
            question: "What is an array?",
            answer: null,
          },
        ],
      },
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  const startBtn = dialog.getByRole("button", { name: /Start interview/i });
  await expect(startBtn).toBeEnabled();
  await Promise.all([startBtn.click(), startBtn.click()]);
  await expect.poll(() => starts, { timeout: 10_000 }).toBe(1);
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-new/);
});
