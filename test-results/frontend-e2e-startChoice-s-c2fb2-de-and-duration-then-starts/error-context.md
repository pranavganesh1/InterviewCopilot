# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\startChoice.spec.ts >> start a new interview shows mode and duration, then starts
- Location: frontend\e2e\startChoice.spec.ts:142:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  75  |           track_id: "t1",
  76  |           mode: "strict",
  77  |           status: "in_progress",
  78  |           duration_minutes: 180,
  79  |           created_at: STARTED,
  80  |         },
  81  |         turns: [
  82  |           {
  83  |             turn_index: 2,
  84  |             question_area: "Hashmaps",
  85  |             question: "Same question after resume",
  86  |             answer: null,
  87  |             evaluation: null,
  88  |           },
  89  |         ],
  90  |       },
  91  |     }),
  92  |   );
  93  |
  94  |   await page.goto("/");
  95  |   await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  96  |   await expect(page).toHaveURL("/");
  97  |   const dialog = page.getByRole("dialog");
  98  |   await expect(dialog.getByRole("heading", { name: "Backend Engineer Intern" })).toBeVisible();
  99  |   await expect(dialog.getByText("Unfinished interview")).toBeVisible();
  100 |   await expect(dialog.getByText("Question 2 of 15")).toBeVisible();
  101 |   await expect(dialog.getByText("Started 2 hours ago")).toBeVisible();
  102 |   await expect(dialog.getByText(/left/)).toBeVisible();
  103 |   await expect(dialog.getByText("Strict")).toBeVisible();
  104 |   const overflow = await page.evaluate(
  105 |     () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  106 |   );
  107 |   expect(overflow).toBeLessThanOrEqual(1);
  108 |
  109 |   await dialog.getByRole("button", { name: "Resume interview" }).click();
  110 |   await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-open/);
  111 |   await expect(page.getByText("Same question after resume")).toBeVisible();
  112 | });
  113 |
  114 | test("finish asks for confirmation, then calls the finish endpoint", async ({ page }) => {
  115 |   await mockShell(page);
  116 |   await page.route("**/api/v1/tracks/t1/open-session", (route) =>
  117 |     route.fulfill({ json: { session: OPEN } }),
  118 |   );
  119 |   let finished = false;
  120 |   await page.route("**/api/v1/sessions/s-open/complete", (route) => {
  121 |     finished = true;
  122 |     return route.fulfill({ json: { session: { id: "s-open", status: "completed" } } });
  123 |   });
  124 |   await page.route("**/api/v1/sessions/s-open/report", (route) =>
  125 |     route.fulfill({ status: 404, json: { detail: "not ready" } }),
  126 |   );
  127 |
  128 |   await page.goto("/");
  129 |   await page.getByRole("button", { name: "Backend Engineer Intern" }).click();
  130 |   const dialog = page.getByRole("dialog");
  131 |   await dialog.getByRole("button", { name: "Finish and get feedback" }).click();
  132 |   await expect(
  133 |     dialog.getByText(
  134 |       "Your answered questions will be scored. Unanswered ones will not count against you.",
  135 |     ),
  136 |   ).toBeVisible();
  137 |   expect(finished).toBe(false);
  138 |   await dialog.getByRole("button", { name: "Score my answers" }).click();
  139 |   await expect.poll(() => finished).toBe(true);
  140 | });
  141 |
  142 | test("start a new interview shows mode and duration, then starts", async ({ page }) => {
  143 |   await mockShell(page);
  144 |   await page.route("**/api/v1/tracks/t1/open-session", (route) =>
  145 |     route.fulfill({ json: { session: OPEN } }),
  146 |   );
  147 |   const calls: string[] = [];
  148 |   await page.route("**/api/v1/sessions/s-open/complete", (route) => {
  149 |     calls.push("complete");
  150 |     return route.fulfill({ json: { session: { id: "s-open", status: "completed" } } });
  151 |   });
  152 |   await page.route("**/api/v1/tracks/t1/sessions", (route) => {
  153 |     calls.push("start");
  154 |     return route.fulfill({
  155 |       json: { session: { id: "s-new" }, turn: { question: "Fresh question" } },
  156 |     });
  157 |   });
  158 |   await page.route("**/api/v1/sessions/s-new", (route) =>
  159 |     route.fulfill({
  160 |       json: {
  161 |         session: { id: "s-new", track_id: "t1", mode: "strict", status: "in_progress" },
  162 |         turns: [
  163 |           {
  164 |             turn_index: 1,
  165 |             question_area: "General",
  166 |             question: "Fresh question",
  167 |             answer: null,
  168 |             evaluation: null,
  169 |           },
  170 |         ],
  171 |       },
  172 |     }),
  173 |   );
  174 |
> 175 |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  176 |   await page.getByRole("button", { name: "Start Interview", exact: true }).click();
  177 |   const dialog = page.getByRole("dialog");
  178 |   await dialog.getByRole("button", { name: "Start a new interview" }).click();
  179 |   await dialog.getByRole("button", { name: "Continue" }).click();
  180 |   await expect(dialog.getByRole("button", { name: /Strict/ })).toBeVisible();
  181 |   await expect(dialog.getByRole("button", { name: /Guided/ })).toBeDisabled();
  182 |   await expect(dialog.getByText("Interview duration")).toBeVisible();
  183 |   await expect(dialog.getByRole("button", { name: "1 hr" })).toBeVisible();
  184 |   await dialog.getByRole("button", { name: "Start interview", exact: true }).click();
  185 |   await expect(page).toHaveURL(/\/tracks\/t1\/interview\/s-new/);
  186 |   expect(calls).toEqual(["complete", "start"]);
  187 | });
  188 |
  189 | test("a track with no unfinished session opens on the start options", async ({ page }) => {
  190 |   await mockShell(page);
  191 |   await page.route("**/api/v1/tracks/t1", (route) =>
  192 |     route.fulfill({
  193 |       json: {
  194 |         track: {
  195 |           id: "t1",
  196 |           track_type: "topic",
  197 |           subject: "Data Structures & Algorithms",
  198 |           company: null,
  199 |           status: "active",
  200 |           created_at: "2026-11-03T00:00:00Z",
  201 |         },
  202 |         brief: {
  203 |           version: 1,
  204 |           content: {
  205 |             summary: "DSA basics",
  206 |             competencies: [],
  207 |             question_areas: [],
  208 |             preparation_plan: [],
  209 |             candidate_angle_notes: "",
  210 |             question_bank: [],
  211 |           },
  212 |         },
  213 |       },
  214 |     }),
  215 |   );
  216 |   await page.route("**/api/v1/tracks/t1/open-session", (route) =>
  217 |     route.fulfill({ json: { session: null } }),
  218 |   );
  219 |
  220 |   await page.goto("/tracks/t1");
  221 |   await expect(page.getByRole("dialog")).toHaveCount(0);
  222 |   await page.getByRole("button", { name: "Start interview" }).click();
  223 |   const dialog = page.getByRole("dialog");
  224 |   await expect(dialog.getByRole("button", { name: "Resume interview" })).toHaveCount(0);
  225 |   await expect(dialog.getByRole("button", { name: /Strict/ })).toBeVisible();
  226 |   await expect(dialog.getByRole("button", { name: /Guided/ })).toBeDisabled();
  227 |   await expect(dialog.getByText("Interview duration")).toBeVisible();
  228 | });
  229 |
  230 | test("escape and the close button return focus to the track", async ({ page }) => {
  231 |   await mockShell(page);
  232 |   await page.route("**/api/v1/tracks/t1/open-session", (route) =>
  233 |     route.fulfill({ json: { session: null } }),
  234 |   );
  235 |
  236 |   await page.goto("/");
  237 |   const trigger = page.getByRole("button", { name: "Start Interview", exact: true });
  238 |   await trigger.click();
  239 |   const dialog = page.getByRole("dialog");
  240 |   await expect(dialog.getByRole("button", { name: /Strict/ })).toBeFocused();
  241 |   await page.keyboard.press("Shift+Tab");
  242 |   await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  243 |   await page.keyboard.press("Shift+Tab");
  244 |   const wrapped = await page.evaluate(() =>
  245 |     Boolean(document.querySelector("[role=dialog]")?.contains(document.activeElement)),
  246 |   );
  247 |   expect(wrapped).toBe(true);
  248 |
  249 |   await page.keyboard.press("Escape");
  250 |   await expect(dialog).toHaveCount(0);
  251 |   await expect(trigger).toBeFocused();
  252 |
  253 |   await trigger.click();
  254 |   await page.getByRole("button", { name: "Close" }).click();
  255 |   await expect(page.getByRole("dialog")).toHaveCount(0);
  256 |   await expect(trigger).toBeFocused();
  257 | });
  258 |
  259 | test("a backdrop click does nothing while the session is being created", async ({ page }) => {
  260 |   await mockShell(page);
  261 |   await page.route("**/api/v1/tracks/t1/open-session", (route) =>
  262 |     route.fulfill({ json: { session: null } }),
  263 |   );
  264 |   let release: (() => void) | undefined;
  265 |   const gate = new Promise<void>((resolve) => {
  266 |     release = resolve;
  267 |   });
  268 |   await page.route("**/api/v1/tracks/t1/sessions", async (route) => {
  269 |     await gate;
  270 |     await route.fulfill({
  271 |       json: { session: { id: "s-slow" }, turn: { question: "Later" } },
  272 |     });
  273 |   });
  274 |
  275 |   await page.goto("/");
```
