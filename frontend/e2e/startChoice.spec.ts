import { expect, test, type Page } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

const STARTED = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();

const OPEN = {
  id: "s-open",
  mode: "strict",
  status: "in_progress",
  question_index: 2,
  max_turns: 15,
  answered_count: 1,
  created_at: STARTED,
  duration_minutes: 180,
};

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
  await page.route("**/api/v1/tracks/t1/progression", (route) =>
    route.fulfill({
      json: { track_id: "t1", strict_completed: 0, guided_state: "LOCKED" },
    }),
  );
}

test("an unfinished session opens in the modal and resume keeps that question", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: OPEN } }),
  );
  await page.route("**/api/v1/sessions/s-open", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s-open",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          duration_minutes: 180,
          created_at: STARTED,
        },
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

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  await expect(page).toHaveURL("/");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Backend Engineer Intern" })).toBeVisible();
  await expect(dialog.getByText("Unfinished interview")).toBeVisible();
  await expect(dialog.getByText("Question 2 of 15")).toBeVisible();
  await expect(dialog.getByText("Started 2 hours ago")).toBeVisible();
  await expect(dialog.getByText(/left/)).toBeVisible();
  await expect(dialog.getByText("Strict", { exact: true })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);

  await dialog.getByRole("button", { name: "Resume interview" }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-open/);
  await expect(page.getByText("Same question after resume")).toBeVisible();
});

test("finish asks for confirmation, then calls the finish endpoint", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: OPEN } }),
  );
  let finished = false;
  await page.route("**/api/v1/sessions/s-open/complete", (route) => {
    finished = true;
    return route.fulfill({ json: { session: { id: "s-open", status: "completed" } } });
  });
  await page.route("**/api/v1/sessions/s-open/report", (route) =>
    route.fulfill({ status: 404, json: { detail: "not ready" } }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Backend Engineer Intern" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Finish and get feedback" }).click();
  await expect(
    dialog.getByText(
      "Your answered questions will be scored. Unanswered ones will not count against you.",
    ),
  ).toBeVisible();
  expect(finished).toBe(false);
  await dialog.getByRole("button", { name: "Score my answers" }).click();
  await expect.poll(() => finished).toBe(true);
});

test("start a new interview shows mode and duration, then starts", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: OPEN } }),
  );
  const calls: string[] = [];
  await page.route("**/api/v1/sessions/s-open/complete", (route) => {
    calls.push("complete");
    return route.fulfill({ json: { session: { id: "s-open", status: "completed" } } });
  });
  await page.route("**/api/v1/tracks/t1/sessions", (route) => {
    calls.push("start");
    return route.fulfill({
      json: { session: { id: "s-new" }, turn: { question: "Fresh question" } },
    });
  });
  await page.route("**/api/v1/sessions/s-new", (route) =>
    route.fulfill({
      json: {
        session: { id: "s-new", track_id: "t1", mode: "strict", status: "in_progress" },
        turns: [
          {
            turn_index: 1,
            question_area: "General",
            question: "Fresh question",
            answer: null,
            evaluation: null,
          },
        ],
      },
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Start a new interview" }).click();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByRole("button", { name: /Strict/ })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Guided/ })).toBeDisabled();
  await expect(dialog.getByText("Interview duration")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "1 hr" })).toBeVisible();
  await dialog.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-new/);
  expect(calls).toEqual(["complete", "start"]);
});

test("a track with no unfinished session opens on the start options", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1", (route) =>
    route.fulfill({
      json: {
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
      },
    }),
  );
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );

  await page.goto("/tracks/t1");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Start interview" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "Resume interview" })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: /Strict/ })).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Guided/ })).toBeDisabled();
  await expect(dialog.getByText("Interview duration")).toBeVisible();
});

test("escape and the close button return focus to the track", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );

  await page.goto("/");
  const trigger = page.getByRole("button", { name: "Start Interview", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: /Strict/ })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  const wrapped = await page.evaluate(() =>
    Boolean(document.querySelector("[role=dialog]")?.contains(document.activeElement)),
  );
  expect(wrapped).toBe(true);

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await trigger.click();
  await page.getByRole("button", { name: "Close" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("a backdrop click does nothing while the session is being created", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );
  let release: (() => void) | undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/tracks/t1/sessions", async (route) => {
    await gate;
    await route.fulfill({
      json: { session: { id: "s-slow" }, turn: { question: "Later" } },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const startBtn = page.getByRole("button", { name: "Start interview", exact: true });
  await startBtn.click();
  await expect(startBtn).toBeDisabled();
  await page.mouse.click(8, 8);
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page).toHaveURL("/");
  release?.();
});

test("a failed start stays in the modal with a way to retry", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks/t1/open-session", (route) =>
    route.fulfill({ json: { session: null } }),
  );
  await page.route("**/api/v1/tracks/t1/sessions", (route) =>
    route.fulfill({ status: 503, json: { detail: "rate limited" } }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  await page.getByRole("button", { name: "Start interview", exact: true }).click();
  await expect(page.getByText("The interview model is busy right now.")).toBeVisible();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page).toHaveURL("/");
});
