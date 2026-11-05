import { expect, test } from "@playwright/test";

const USER = { id: "u1", email: "s@example.com", name: "S", picture_url: null };

async function mockInterview(page: import("@playwright/test").Page) {
  const turns = [
    {
      turn_index: 1,
      question_area: "Array Basics",
      question: "What is an array and how is it stored contiguously?",
      answer: null as string | null,
      evaluation: null as Record<string, unknown> | null,
    },
  ];
  await page.route("**/api/v1/auth/me", (r) => r.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (r) =>
    r.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/sessions/s1", (r) =>
    r.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "in_progress",
          max_turns: 15,
        },
        turns,
      },
    }),
  );
  await page.route("**/api/v1/sessions/s1/turns", async (r) => {
    turns[0].answer = "Contiguous memory.";
    turns[0].evaluation = { coverage: "good", strengths: ["ok"], gaps: [] };
    turns.push({
      turn_index: 2,
      question_area: "Two Pointers",
      question: "Explain two pointers.",
      answer: null,
      evaluation: null,
    });
    await r.fulfill({
      json: {
        completed: false,
        evaluation: turns[0].evaluation,
        turn: turns[1],
      },
    });
  });
  await page.route("**/api/v1/sessions/s1/complete", (r) =>
    r.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: "completed",
          max_turns: 15,
        },
      },
    }),
  );
}

for (const width of [375, 768, 1440] as const) {
  test(`viewport ${width}px: one question, next, finish`, async ({ page }) => {
    await page.setViewportSize({ width, height: 800 });
    await mockInterview(page);
    await page.goto("/tracks/t1/interview/s1");
    await expect(page.getByText("What is an array")).toBeVisible();
    await expect(page.getByText("Explain two pointers")).toHaveCount(0);
    // No page-level horizontal scroll (inner stepper may overflow with overflow-x-auto).
    const noPageHScroll = await page.evaluate(() => {
      const root = document.documentElement;
      const before = root.scrollLeft;
      root.scrollLeft = 200;
      const moved = root.scrollLeft !== before;
      root.scrollLeft = before;
      const session = document.querySelector("[data-testid='interview-session']");
      const fits =
        !session ||
        session.getBoundingClientRect().right <= window.innerWidth + 1;
      return !moved && fits;
    });
    expect(noPageHScroll).toBeTruthy();
    await page.fill("textarea", "Contiguous memory.");
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("evaluation-feedback")).toBeVisible();
    await expect(page.getByTestId("next-question")).toBeVisible();
    await page.getByTestId("next-question").click();
    await expect(page.getByText("Explain two pointers.")).toBeVisible();
    await page.getByTestId("finish-assessment-exit").click();
    await expect(page.getByTestId("finish-exit-confirm")).toBeVisible();
  });
}
