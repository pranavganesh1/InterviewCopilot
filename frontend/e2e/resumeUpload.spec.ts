import { expect, test, type Page } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  onboarding_completed: false,
};

const STATE = {
  messages: [],
  vault_items: [],
  onboarding_complete: false,
  onboarding_finished: false,
  missing_categories: ["project", "skill", "education"],
};

async function mockShell(page: Page) {
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
  await page.route("**/api/v1/onboarding/state", (route) =>
    route.fulfill({ json: STATE }),
  );
}

test("resume error codes show friendly message and Try again", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await mockShell(page);
  await page.route("**/api/v1/vault/resume", (route) =>
    route.fulfill({
      status: 422,
      json: {
        detail: {
          message: "No text found in this PDF. Upload a text-based PDF.",
          code: "no_text",
        },
      },
    }),
  );

  await page.goto("/onboarding");
  const zone = page.getByTestId("resume-upload-dropzone");
  await expect(zone).toBeVisible();

  await page.setInputFiles('input[type="file"][accept="application/pdf"]', {
    name: "scan.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 fake"),
  });

  const err = page.getByTestId("resume-upload-error");
  await expect(err).toBeVisible();
  await expect(err.getByText(/No text found in this PDF/i)).toBeVisible();
  await expect(err.getByText(/not a scanned photo/i)).toBeVisible();
  await expect(err.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(page.getByText(/scan\.pdf/)).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});

test("resume success shows item count", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/vault/resume", (route) =>
    route.fulfill({
      json: {
        items_created: [
          { id: "1", category: "skill", title: "Python" },
          { id: "2", category: "project", title: "Campus nav" },
        ],
        s3_key: "u1/x.pdf",
      },
    }),
  );

  await page.goto("/onboarding");
  await page.setInputFiles('input[type="file"][accept="application/pdf"]', {
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 ok"),
  });
  await expect(page.getByTestId("resume-upload-success")).toContainText(
    "Added 2 vault items",
  );
});

test("storage 503 shows retry message", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/vault/resume", (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail: {
          message: "File storage is temporarily unavailable. Please retry in a minute.",
          code: "storage_unavailable",
        },
      },
    }),
  );

  await page.goto("/onboarding");
  await page.setInputFiles('input[type="file"][accept="application/pdf"]', {
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 ok"),
  });
  await expect(page.getByTestId("resume-upload-error")).toContainText(
    /storage is temporarily unavailable/i,
  );
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});
