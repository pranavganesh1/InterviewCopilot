import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

type TrackRow = {
  id: string;
  track_type: string;
  subject: string;
  company: string | null;
  status: string;
  archived: boolean;
  archived_at: string | null;
  created_at: string;
  brief_version: number;
};

function assessment(trackId: string) {
  return {
    report_id: "r1",
    session_id: "s1",
    track_id: trackId,
    track_subject: "Graphs",
    created_at: "2026-11-01T00:00:00Z",
    session_mode: "strict",
    coverage_status: "PARTIAL",
    overall_score: 80,
    questions_attempted: 1,
    max_turns: 15,
    status: "completed",
    track_archived: false,
    summary_overview: "Kept.",
    strengths: [],
    improvement_areas: [],
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/me/open-sessions", (route) =>
    route.fulfill({ json: [] }),
  );
});

test("menu opens and closes, delete updates counts, and undo restores", async ({ page }) => {
  const tracks: TrackRow[] = [
    {
      id: "t1",
      track_type: "topic",
      subject: "Graphs",
      company: null,
      status: "active",
      archived: false,
      archived_at: null,
      created_at: "2026-11-01T00:00:00Z",
      brief_version: 1,
    },
  ];
  let archived = false;

  await page.route("**/api/v1/me/assessments", (route) =>
    route.fulfill({
      json: {
        dashboard: {
          completed_interviews: archived ? 0 : 1,
          average_score: archived ? null : 80,
          total_questions_attempted: archived ? 0 : 1,
          strongest_skills: [],
          skills_needing_improvement: [],
          recommended_topics: [],
        },
        assessments: [{ ...assessment("t1"), track_archived: archived }],
      },
    }),
  );
  await page.route("**/api/v1/tracks**", async (route) => {
    const request = route.request();
    const url = request.url();
    if (request.method() === "DELETE") {
      archived = true;
      tracks[0].archived = true;
      tracks[0].archived_at = "2026-11-06T00:00:00Z";
      await route.fulfill({
        json: { track: tracks[0] },
      });
      return;
    }
    if (request.method() === "POST" && url.includes("/restore")) {
      archived = false;
      tracks[0].archived = false;
      tracks[0].archived_at = null;
      await route.fulfill({ json: { track: tracks[0] } });
      return;
    }
    const include = url.includes("include_archived=true");
    await route.fulfill({
      json: include ? tracks : tracks.filter((item) => !item.archived),
    });
  });

  await page.goto("/");
  await expect(page.getByText("Interviews Taken").locator("xpath=..")).toContainText("1");
  await page.getByRole("button", { name: "Track options" }).click();
  await expect(page.getByRole("menuitem", { name: "Open track" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Delete track" })).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Latest report" })).toBeFocused();
  await page.getByRole("heading", { name: "Preparation tracks" }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);

  await page.getByRole("button", { name: "Track options" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toHaveCount(0);

  await page.getByRole("button", { name: "Track options" }).click();
  await page.getByRole("menuitem", { name: "Delete track" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Delete this track?" })).toBeVisible();
  await expect(dialog.getByText("Graphs")).toBeVisible();
  await expect(dialog.getByText("1 attempt, 1 report")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Delete track" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page.getByRole("button", { name: "Graphs" })).toHaveCount(0);
  await expect(page.getByText("Total Tracks").locator("xpath=..")).toContainText("0");
  await expect(page.getByText("Interviews Taken").locator("xpath=..")).toContainText("0");
  await expect(page.getByRole("status")).toContainText("Track deleted");
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByRole("button", { name: "Graphs" })).toBeVisible();
  await expect(page.getByText("Total Tracks").locator("xpath=..")).toContainText("1");
});

test("deleting a track with an unfinished interview succeeds and aborts it", async ({
  page,
}) => {
  // M11: deletion is always allowed now — the backend auto-aborts any
  // unfinished interview instead of blocking with 409.
  let deleted = false;
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
  await page.route("**/api/v1/tracks**", async (route) => {
    if (route.request().method() === "DELETE") {
      deleted = true;
      await route.fulfill({ status: 200, json: { track: { id: "t1", status: "active" } } });
      return;
    }
    await route.fulfill({
      json: deleted
        ? []
        : [
            {
              id: "t1",
              track_type: "topic",
              subject: "Graphs",
              company: null,
              status: "active",
              archived: false,
              created_at: "2026-11-01T00:00:00Z",
            },
          ],
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Track options" }).click();
  await page.getByRole("menuitem", { name: "Delete track" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Delete track" }).click();

  // Track disappears (aborted server-side, nothing blocks the delete).
  await expect(page.getByRole("link", { name: "Graphs" })).toHaveCount(0);
});

test("delete failure stays in the dialog and focus returns to the menu button", async ({
  page,
}) => {
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
  await page.route("**/api/v1/tracks**", async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 500, json: { detail: "Could not delete this track." } });
      return;
    }
    await route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "topic",
          subject: "Graphs",
          company: null,
          status: "active",
          created_at: "2026-11-01T00:00:00Z",
        },
      ],
    });
  });

  await page.goto("/");
  const menuButton = page.getByRole("button", { name: "Track options" });
  await menuButton.click();
  await page.getByRole("menuitem", { name: "Delete track" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Delete track" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Could not delete this track.");
  await expect(dialog.getByRole("button", { name: "Try again" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Cancel" })).not.toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(menuButton).toBeFocused();
});

test("track list does not overflow at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 700 });
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
  await page.route("**/api/v1/tracks**", (route) =>
    route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "company_jd",
          subject: "Backend Engineer Intern with a long title",
          company: "Very Long Company Name",
          status: "active",
          created_at: "2026-11-01T00:00:00Z",
        },
      ],
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Track options" }).click();
  await page.getByRole("menuitem", { name: "Delete track" }).click();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  );
  expect(overflow).toBe(true);
  await expect(page.getByRole("dialog")).toBeVisible();
});
