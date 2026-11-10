import { expect, test, type Page } from "@playwright/test";

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

const REPORT = {
  id: "r1",
  session_id: "s1",
  created_at: "2026-11-04T00:00:00Z",
  overall_score: 70,
  questions_attempted: 1,
  content: {
    report_version: 1,
    session_mode: "strict",
    summary_overview: "Scored the answered questions.",
    coverage_status: "PARTIAL",
    question_assessments: [],
    competency_assessments: [],
    strengths: [],
    improvement_areas: [],
    unassessed_topics: [],
    recommendations: [],
  },
};

function sessionBody(status: string, duration?: number) {
  return {
    session: {
      id: "s1",
      track_id: "t1",
      mode: "strict",
      status,
      max_turns: 15,
      ...(duration ? { duration_minutes: duration, created_at: "2026-11-06T08:00:00Z" } : {}),
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
}

async function mockShell(page: Page) {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 204 }));
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
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({
      json: {
        onboarding_completed: false,
        messages: [],
        profile: {},
      },
    }),
  );
}

async function openInterview(page: Page, duration?: number, status = "in_progress") {
  await page.route("**/api/v1/sessions/s1", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({ json: sessionBody(status, duration) });
  });
  await page.goto("/");
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
}

async function unloadBlocked(page: Page) {
  return page.evaluate(() => {
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    return event.defaultPrevented;
  });
}

test.beforeEach(async ({ page }) => {
  await mockShell(page);
});

test("header links and profile menu open the leave warning and can stay or leave", async ({
  page,
}) => {
  await openInterview(page);
  const draft = page.locator("textarea");
  await draft.fill("unsaved chaining note");

  await page.getByRole("link", { name: "Tracks", exact: true }).click();
  const modal = page.getByTestId("leave-interview-modal");
  await expect(modal).toBeVisible();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s1/);
  await page.getByRole("button", { name: "Stay in interview" }).click();
  await expect(modal).toBeHidden();
  await expect(draft).toHaveValue("unsaved chaining note");

  await page.getByRole("link", { name: "Onboarding" }).click();
  await expect(modal).toBeVisible();
  await expect(page).toHaveURL(/\/interview\/s1/);
  await page.getByRole("button", { name: "Leave and resume later" }).click();
  await expect(page).toHaveURL(/\/onboarding$/);

  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  await page.getByTestId("nav-profile").click();
  await page.getByRole("menuitem", { name: "My Profile" }).click();
  await expect(modal).toBeVisible();
  await expect(page).toHaveURL(/\/interview\/s1/);
  await page.getByRole("button", { name: "Stay in interview" }).click();
  await expect(modal).toBeHidden();

  await page.getByRole("button", { name: "Leave session" }).click();
  await expect(modal).toBeVisible();
  await page.getByRole("button", { name: "Leave and resume later" }).click();
  await expect(page).toHaveURL(/\/tracks\/t1$/);
});

test("browser Back is blocked on an active interview and not on a finished session or report", async ({
  page,
}) => {
  await openInterview(page);
  await page.goBack();
  await expect(page.getByTestId("leave-interview-modal")).toBeVisible();
  await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s1/);
  await page.getByRole("button", { name: "Leave and resume later" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("leave-interview-modal")).toBeHidden();

  await page.route("**/api/v1/sessions/s1", (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    return route.fulfill({ json: sessionBody("completed") });
  });
  await page.goto("/tracks/t1/interview/s1");
  await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("leave-interview-modal")).toHaveCount(0);

  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({ status: 404, json: { detail: "pending" } }),
  );
  await page.goto("/tracks/t1/report/s1");
  await page.goBack();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("leave-interview-modal")).toHaveCount(0);
});

test("timed interviews mention the running timer and untimed ones do not", async ({ page }) => {
  await openInterview(page, 45);
  await page.getByRole("link", { name: "Tracks", exact: true }).click();
  await expect(page.getByText("The timer keeps running while you are away.")).toBeVisible();
  await page.getByRole("button", { name: "Stay in interview" }).click();

  const untimed = sessionBody("in_progress");
  untimed.session.id = "s-plain";
  await page.route("**/api/v1/sessions/s-plain", (route) => route.fulfill({ json: untimed }));
  await page.goto("/");
  await page.goto("/tracks/t1/interview/s-plain");
  await expect(page.getByRole("heading", { name: "Interview session" })).toBeVisible();
  await page.getByRole("link", { name: "Tracks", exact: true }).click();
  await expect(page.getByTestId("leave-interview-modal")).toBeVisible();
  await expect(page.getByText("The timer keeps running while you are away.")).toHaveCount(0);
});

test("Finish and get feedback confirms, completes once, and opens the report", async ({
  page,
}) => {
  let finishes = 0;
  await page.route("**/api/v1/sessions/s1/complete", async (route) => {
    finishes += 1;
    await route.fulfill({
      json: {
        session: { id: "s1", track_id: "t1", mode: "strict", status: "completed", max_turns: 15 },
      },
    });
  });
  await page.route("**/api/v1/sessions/s1/report", (route) => route.fulfill({ json: REPORT }));
  await openInterview(page);
  await page.getByRole("button", { name: "Leave session" }).click();
  await page.getByRole("button", { name: "Finish and get feedback" }).click();
  await expect(
    page.getByText("Your answered questions will be scored. Unanswered ones will not count against you."),
  ).toBeVisible();
  expect(finishes).toBe(0);
  await page.getByRole("button", { name: "Finish and get feedback" }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/report\/s1/);
  expect(finishes).toBe(1);
});

test("a failed finish stays in the modal and can be retried", async ({ page }) => {
  let finishes = 0;
  await page.route("**/api/v1/sessions/s1/complete", async (route) => {
    finishes += 1;
    if (finishes === 1) {
      await route.fulfill({ status: 500, json: { detail: "Scoring is unavailable." } });
      return;
    }
    await route.fulfill({
      json: {
        session: { id: "s1", track_id: "t1", mode: "strict", status: "completed", max_turns: 15 },
      },
    });
  });
  await page.route("**/api/v1/sessions/s1/report", (route) => route.fulfill({ json: REPORT }));
  await openInterview(page);
  await page.getByRole("link", { name: "Tracks", exact: true }).click();
  await page.getByRole("button", { name: "Finish and get feedback" }).click();
  await page.getByRole("button", { name: "Finish and get feedback" }).click();
  await expect(page.getByText("Scoring is unavailable.")).toBeVisible();
  await expect(page).toHaveURL(/\/interview\/s1/);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page).toHaveURL(/\/tracks\/t1\/report\/s1/);
  expect(finishes).toBe(2);
});

test("beforeunload is registered only while a draft exists", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1/turns", (route) =>
    route.fulfill({
      json: {
        completed: false,
        evaluation: { coverage: "partial", strengths: [], gaps: [] },
      },
    }),
  );
  await openInterview(page);
  expect(await unloadBlocked(page)).toBe(false);
  await page.locator("textarea").fill("draft answer");
  await expect.poll(() => unloadBlocked(page)).toBe(true);
  await page.getByTestId("submit-answer").click();
  await expect.poll(() => unloadBlocked(page)).toBe(false);
});

test("Escape, backdrop, and a 375px layout keep the candidate in the interview", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 700 });
  await openInterview(page);
  await page.locator("textarea").fill("keep me");

  await page.getByRole("link", { name: "Onboarding" }).click();
  await expect(page.getByTestId("leave-interview-modal")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("leave-interview-modal")).toBeHidden();
  await expect(page).toHaveURL(/\/interview\/s1/);
  await expect(page.locator("textarea")).toHaveValue("keep me");

  await page.getByRole("link", { name: "Onboarding" }).click();
  await page.getByTestId("leave-backdrop").click({ position: { x: 8, y: 8 } });
  await expect(page.getByTestId("leave-interview-modal")).toBeHidden();
  await expect(page).toHaveURL(/\/interview\/s1/);

  await page.getByRole("button", { name: "Leave session" }).click();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
  const stay = page.getByRole("button", { name: "Stay in interview" });
  const box = await stay.boundingBox();
  expect(box?.width ?? 0).toBeGreaterThan(300);
});
