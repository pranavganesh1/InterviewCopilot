# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\deleteTrack.spec.ts >> track list does not overflow at 375px
- Location: frontend\e2e\deleteTrack.spec.ts:258:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  189 |   await page.route("**/api/v1/sessions/sess-open/report", (route) =>
  190 |     route.fulfill({ json: { id: "r1", content: {} } }),
  191 |   );
  192 |
  193 |   await page.goto("/");
  194 |   await page.getByRole("button", { name: "Track options" }).click();
  195 |   await page.getByRole("menuitem", { name: "Delete track" }).click();
  196 |   await page.getByRole("dialog").getByRole("button", { name: "Delete track" }).click();
  197 |   const dialog = page.getByRole("dialog");
  198 |   await expect(
  199 |     dialog.getByRole("heading", { name: "You have an unfinished interview on this track" }),
  200 |   ).toBeVisible();
  201 |   await expect(dialog.getByRole("button", { name: "Resume interview" })).toBeVisible();
  202 |   await expect(dialog.getByRole("button", { name: "Finish and get feedback" })).toBeVisible();
  203 |   await expect(page.getByRole("button", { name: "Graphs" })).toBeVisible();
  204 | });
  205 |
  206 | test("delete failure stays in the dialog and focus returns to the menu button", async ({
  207 |   page,
  208 | }) => {
  209 |   await page.route("**/api/v1/me/assessments", (route) =>
  210 |     route.fulfill({
  211 |       json: {
  212 |         dashboard: {
  213 |           completed_interviews: 0,
  214 |           average_score: null,
  215 |           total_questions_attempted: 0,
  216 |           strongest_skills: [],
  217 |           skills_needing_improvement: [],
  218 |           recommended_topics: [],
  219 |         },
  220 |         assessments: [],
  221 |       },
  222 |     }),
  223 |   );
  224 |   await page.route("**/api/v1/tracks**", async (route) => {
  225 |     if (route.request().method() === "DELETE") {
  226 |       await route.fulfill({ status: 500, json: { detail: "Could not delete this track." } });
  227 |       return;
  228 |     }
  229 |     await route.fulfill({
  230 |       json: [
  231 |         {
  232 |           id: "t1",
  233 |           track_type: "topic",
  234 |           subject: "Graphs",
  235 |           company: null,
  236 |           status: "active",
  237 |           created_at: "2026-11-01T00:00:00Z",
  238 |         },
  239 |       ],
  240 |     });
  241 |   });
  242 |
  243 |   await page.goto("/");
  244 |   const menuButton = page.getByRole("button", { name: "Track options" });
  245 |   await menuButton.click();
  246 |   await page.getByRole("menuitem", { name: "Delete track" }).click();
  247 |   const dialog = page.getByRole("dialog");
  248 |   await dialog.getByRole("button", { name: "Delete track" }).click();
  249 |   await expect(dialog.getByRole("alert")).toContainText("Could not delete this track.");
  250 |   await expect(dialog.getByRole("button", { name: "Try again" })).toBeVisible();
  251 |   await page.keyboard.press("Tab");
  252 |   await expect(dialog.getByRole("button", { name: "Cancel" })).not.toBeFocused();
  253 |   await page.keyboard.press("Escape");
  254 |   await expect(dialog).toHaveCount(0);
  255 |   await expect(menuButton).toBeFocused();
  256 | });
  257 |
  258 | test("track list does not overflow at 375px", async ({ page }) => {
  259 |   await page.setViewportSize({ width: 375, height: 700 });
  260 |   await page.route("**/api/v1/me/assessments", (route) =>
  261 |     route.fulfill({
  262 |       json: {
  263 |         dashboard: {
  264 |           completed_interviews: 0,
  265 |           average_score: null,
  266 |           total_questions_attempted: 0,
  267 |           strongest_skills: [],
  268 |           skills_needing_improvement: [],
  269 |           recommended_topics: [],
  270 |         },
  271 |         assessments: [],
  272 |       },
  273 |     }),
  274 |   );
  275 |   await page.route("**/api/v1/tracks**", (route) =>
  276 |     route.fulfill({
  277 |       json: [
  278 |         {
  279 |           id: "t1",
  280 |           track_type: "company_jd",
  281 |           subject: "Backend Engineer Intern with a long title",
  282 |           company: "Very Long Company Name",
  283 |           status: "active",
  284 |           created_at: "2026-11-01T00:00:00Z",
  285 |         },
  286 |       ],
  287 |     }),
  288 |   );
> 289 |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  290 |   await page.getByRole("button", { name: "Track options" }).click();
  291 |   await page.getByRole("menuitem", { name: "Delete track" }).click();
  292 |   const overflow = await page.evaluate(
  293 |     () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
  294 |   );
  295 |   expect(overflow).toBe(true);
  296 |   await expect(page.getByRole("dialog")).toBeVisible();
  297 | });
  298 |
```
