import { expect, test } from "@playwright/test";
import {
  MAX_REPORT_POLLS,
  deriveReportViewState,
  nextReportPollInterval,
} from "../src/lib/feedbackStatus";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

test.describe("feedbackStatus helpers", () => {
  test("pending / generating / ready / failed mapping", () => {
    expect(
      deriveReportViewState({
        hasData: false,
        isLoading: false,
        isFetching: false,
        errorStatus: 404,
        pollsSoFar: 0,
      }),
    ).toBe("pending");

    expect(
      deriveReportViewState({
        hasData: false,
        isLoading: false,
        isFetching: true,
        errorStatus: 404,
        pollsSoFar: 1,
      }),
    ).toBe("generating");

    expect(
      deriveReportViewState({
        hasData: true,
        isLoading: false,
        isFetching: false,
        pollsSoFar: 3,
      }),
    ).toBe("ready");

    expect(
      deriveReportViewState({
        hasData: false,
        isLoading: false,
        isFetching: false,
        errorStatus: 404,
        pollsSoFar: MAX_REPORT_POLLS,
      }),
    ).toBe("failed");

    expect(
      deriveReportViewState({
        hasData: false,
        isLoading: false,
        isFetching: false,
        errorStatus: 500,
        pollsSoFar: 0,
      }),
    ).toBe("failed");
  });

  test("polling continues only for 404 and stops after success or exhaustion", () => {
    expect(
      nextReportPollInterval({ hasData: false, errorStatus: 404, pollsSoFar: 0 }),
    ).toBe(5000);
    expect(
      nextReportPollInterval({
        hasData: false,
        errorStatus: 404,
        pollsSoFar: MAX_REPORT_POLLS,
      }),
    ).toBe(false);
    expect(
      nextReportPollInterval({ hasData: true, errorStatus: 404, pollsSoFar: 1 }),
    ).toBe(false);
    expect(
      nextReportPollInterval({ hasData: false, errorStatus: 500, pollsSoFar: 0 }),
    ).toBe(false);
  });
});

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
});

test("interview completion does not claim feedback is ready", async ({ page }) => {
  const turns = [
    {
      turn_index: 1,
      question_area: "TCP",
      question: "Explain the handshake.",
      answer: null as string | null,
      evaluation: null as Record<string, unknown> | null,
    },
  ];
  await page.route("**/api/v1/sessions/s1", (route) =>
    route.fulfill({
      json: {
        session: {
          id: "s1",
          track_id: "t1",
          mode: "strict",
          status: turns[0].answer ? "completed" : "in_progress",
        },
        turns,
      },
    }),
  );
  await page.route("**/api/v1/sessions/s1/turns", async (route) => {
    turns[0].answer = "SYN SYN-ACK ACK";
    turns[0].evaluation = {
      coverage: "good",
      strengths: ["Clear"],
      gaps: [],
    };
    await route.fulfill({
      json: {
        completed: true,
        evaluation: turns[0].evaluation,
      },
    });
  });

  await page.goto("/tracks/t1/interview/s1");
  await page.fill("textarea", "SYN SYN-ACK ACK");
  await page.getByRole("button", { name: "Submit Answer" }).click();

  await expect(page.getByText("Interview completed.")).toBeVisible();
  await expect(page.getByText(/Feedback is pending/)).toBeVisible();
  await expect(page.getByText(/report is ready/i)).toHaveCount(0);
  await expect(page.getByTestId("finish-interview")).toBeVisible();
});

test("report page shows pending then ready after 404 clears", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/sessions/s1/report", async (route) => {
    calls += 1;
    if (calls === 1) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Report not ready" }),
      });
      return;
    }
    await route.fulfill({
      json: {
        id: "r1",
        session_id: "s1",
        created_at: "2026-11-03T00:00:00Z",
        content: {
          report_version: 1,
          session_mode: "strict",
          summary_overview: "Ready now.",
          coverage_status: "PARTIAL",
          question_assessments: [],
          competency_assessments: [],
          strengths: ["Clear"],
          improvement_areas: [],
          unassessed_topics: [],
          recommendations: ["Keep practicing"],
        },
      },
    });
  });

  await page.goto("/tracks/t1/report/s1");
  await expect(page.getByTestId("report-status")).toHaveAttribute(
    "data-state",
    /pending|generating|loading/,
  );
  await expect(page.getByTestId("report-status")).toHaveAttribute(
    "data-state",
    "ready",
    { timeout: 15000 },
  );
  await expect(page.getByText("Ready now.")).toBeVisible();
});

test("report page shows failed state for non-404 errors", async ({ page }) => {
  await page.route("**/api/v1/sessions/s1/report", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "worker crashed" }),
    }),
  );

  await page.goto("/tracks/t1/report/s1");
  await expect(page.getByTestId("report-status")).toHaveAttribute(
    "data-state",
    "failed",
  );
  await expect(page.getByText("Feedback generation failed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
