import { expect, test } from "@playwright/test";

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
  is_admin: false,
};

test("non-admin is redirected away from admin routes", async ({ page }) => {
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
  await page.route("**/api/v1/tracks", (route) => route.fulfill({ json: [] }));

  await page.goto("/admin");
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { name: "Admin · Overview" })).toHaveCount(0);

  await page.goto("/admin/users");
  await expect(page).toHaveURL("/");
});
