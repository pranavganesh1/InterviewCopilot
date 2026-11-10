import { expect, test, type Page } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

async function mockShell(page: Page) {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  await page.route("**/api/v1/auth/logout", (route) =>
    route.fulfill({ json: { status: "ok" } }),
  );
  await page.route("**/api/v1/auth/refresh", (route) => route.fulfill({ status: 204 }));
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

test("track type cards change the fields and submit the existing payload", async ({
  page,
}) => {
  const bodies: unknown[] = [];
  await mockShell(page);
  await page.route("**/api/v1/tracks", async (route) => {
    if (route.request().method() === "POST") {
      bodies.push(route.request().postDataJSON());
      await route.fulfill({
        status: 201,
        json: {
          track: {
            id: `t-${bodies.length}`,
            track_type: "topic",
            subject: "Saved",
            company: null,
            status: "active",
            created_at: "2026-11-06T00:00:00Z",
          },
        },
      });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "New track" }).click();
  const topic = page.getByRole("radio", { name: /Practice a subject/ });
  const role = page.getByRole("radio", { name: /Prepare for a job role/ });
  const company = page.getByRole("radio", { name: /Paste a job description/ });
  await expect(topic).toHaveAttribute("aria-checked", "true");
  await expect(page.getByLabel("Subject")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create track" })).toBeDisabled();

  await page.getByRole("button", { name: "DBMS" }).click();
  await expect(page.getByLabel("Subject")).toHaveValue("DBMS");
  await page.getByRole("button", { name: "Create track" }).click();
  await expect(page.getByRole("heading", { name: "Create a new track" })).toBeHidden();

  await page.getByRole("button", { name: "New track" }).click();
  await role.click();
  await expect(role).toHaveAttribute("aria-checked", "true");
  await expect(topic).toHaveAttribute("aria-checked", "false");
  await expect(page.getByLabel("Role")).toBeVisible();
  await page.getByRole("button", { name: "Backend Intern" }).click();
  await page.getByRole("button", { name: "Create track" }).click();

  await page.getByRole("button", { name: "New track" }).click();
  await company.click();
  await expect(company).toHaveAttribute("aria-checked", "true");
  await expect(page.getByLabel("Company")).toBeVisible();
  await expect(page.getByLabel("Job description")).toBeVisible();
  await expect(page.getByText(/0\s*\/\s*20/)).toBeVisible();
  await page.getByLabel("Company").fill("Acme");
  await page.getByLabel("Role").fill("Backend Intern");
  await page.getByLabel("Job description").fill("Build APIs");
  await expect(page.getByText(/10\s*\/\s*20/)).toBeVisible();
  await page.getByRole("button", { name: "Create track" }).click();

  expect(bodies).toEqual([
    { track_type: "topic", subject: "DBMS", company: null, jd_text: null },
    { track_type: "role", subject: "Backend Intern", company: null, jd_text: null },
    {
      track_type: "company_jd",
      subject: "Backend Intern",
      company: "Acme",
      jd_text: "Build APIs",
    },
  ]);
});

test("arrow keys move between track types and Space or Enter selects", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await page.getByRole("button", { name: "New track" }).click();
  const topic = page.getByRole("radio", { name: /Practice a subject/ });
  const role = page.getByRole("radio", { name: /Prepare for a job role/ });
  const company = page.getByRole("radio", { name: /Paste a job description/ });
  await topic.focus();
  await page.keyboard.press("ArrowRight");
  await expect(role).toBeFocused();
  await expect(topic).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Space");
  await expect(role).toHaveAttribute("aria-checked", "true");
  await expect(page.getByLabel("Role")).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await expect(company).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(company).toHaveAttribute("aria-checked", "true");
  await expect(page.getByLabel("Job description")).toBeVisible();
});

test("a failed create stays in the form with the typed values", async ({ page }) => {
  await mockShell(page);
  await page.route("**/api/v1/tracks", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 500, json: { detail: "Could not create the track." } });
      return;
    }
    await route.fulfill({ json: [] });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "New track" }).click();
  await page.getByLabel("Subject").fill("Thermodynamics");
  await page.getByLabel("Subject").blur();
  await page.getByRole("button", { name: "Create track" }).click();
  await expect(page.getByRole("alert")).toHaveText("Could not create the track.");
  await expect(page.getByLabel("Subject")).toHaveValue("Thermodynamics");
  await expect(page.getByRole("heading", { name: "Create a new track" })).toBeVisible();
});

test("the new track form has no horizontal overflow at 375px", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await mockShell(page);
  await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await page.getByRole("button", { name: "New track" }).click();
  await page.getByRole("radio", { name: /Paste a job description/ }).click();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflow).toBe(false);
  const create = await page.getByRole("button", { name: "Create track" }).boundingBox();
  expect(create?.width ?? 0).toBeGreaterThan(300);
  expect(create?.height ?? 0).toBeGreaterThanOrEqual(44);
  await page.getByRole("button", { name: "Cancel" }).first().click();
  await expect(page.getByRole("heading", { name: "Create a new track" })).toBeHidden();
});
