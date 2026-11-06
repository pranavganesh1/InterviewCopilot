# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\tokenRefresh.spec.ts >> expired access token refreshes once and retries original request
- Location: frontend\e2e\tokenRefresh.spec.ts:52:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  9   |   test.beforeEach(() => {
  10  |     _resetAuthRefreshStateForTests();
  11  |   });
  12  |
  13  |   test("refresh is attempted only once per request path", () => {
  14  |     expect(shouldAttemptRefresh("/tracks", false)).toBe(true);
  15  |     expect(shouldAttemptRefresh("/tracks", true)).toBe(false);
  16  |     expect(shouldAttemptRefresh("/auth/refresh", false)).toBe(false);
  17  |     expect(shouldAttemptRefresh("/auth/logout", false)).toBe(false);
  18  |   });
  19  |
  20  |   test("concurrent refresh calls share one in-flight request", async () => {
  21  |     let calls = 0;
  22  |     const fetchImpl: typeof fetch = async () => {
  23  |       calls += 1;
  24  |       await new Promise((r) => setTimeout(r, 30));
  25  |       return new Response(null, { status: 204 });
  26  |     };
  27  |     const [a, b, c] = await Promise.all([
  28  |       refreshAccessToken(fetchImpl),
  29  |       refreshAccessToken(fetchImpl),
  30  |       refreshAccessToken(fetchImpl),
  31  |     ]);
  32  |     expect(a && b && c).toBe(true);
  33  |     expect(calls).toBe(1);
  34  |   });
  35  |
  36  |   test("failed refresh returns false", async () => {
  37  |     const fetchImpl: typeof fetch = async () =>
  38  |       new Response(JSON.stringify({ detail: "No refresh token" }), {
  39  |         status: 401,
  40  |       });
  41  |     expect(await refreshAccessToken(fetchImpl)).toBe(false);
  42  |   });
  43  | });
  44  |
  45  | const USER = {
  46  |   id: "u1",
  47  |   email: "student@example.com",
  48  |   name: "Student",
  49  |   picture_url: null,
  50  | };
  51  |
  52  | test("expired access token refreshes once and retries original request", async ({
  53  |   page,
  54  | }) => {
  55  |   let meCalls = 0;
  56  |   let trackCalls = 0;
  57  |   let refreshCalls = 0;
  58  |
  59  |   await page.route("**/api/v1/auth/refresh", async (route) => {
  60  |     refreshCalls += 1;
  61  |     await route.fulfill({ status: 204 });
  62  |   });
  63  |   await page.route("**/api/v1/me/assessments", (route) =>
  64  |     route.fulfill({
  65  |       json: {
  66  |         dashboard: {
  67  |           completed_interviews: 0,
  68  |           average_score: null,
  69  |           total_questions_attempted: 0,
  70  |           strongest_skills: [],
  71  |           skills_needing_improvement: [],
  72  |           recommended_topics: [],
  73  |         },
  74  |         assessments: [],
  75  |       },
  76  |     }),
  77  |   );
  78  |
  79  |   await page.route("**/api/v1/auth/me", async (route) => {
  80  |     meCalls += 1;
  81  |     // First auth/me after load succeeds so we reach the dashboard.
  82  |     await route.fulfill({ json: USER });
  83  |   });
  84  |   await page.route("**/api/v1/tracks", async (route) => {
  85  |     trackCalls += 1;
  86  |     if (trackCalls === 1) {
  87  |       await route.fulfill({
  88  |         status: 401,
  89  |         contentType: "application/json",
  90  |         body: JSON.stringify({ detail: "Not signed in" }),
  91  |       });
  92  |       return;
  93  |     }
  94  |     await route.fulfill({
  95  |       json: [
  96  |         {
  97  |           id: "t1",
  98  |           track_type: "role",
  99  |           subject: "After Refresh",
  100 |           company: null,
  101 |           status: "active",
  102 |           created_at: "2026-11-03T00:00:00Z",
  103 |           brief_version: 1,
  104 |         },
  105 |       ],
  106 |     });
  107 |   });
  108 |
> 109 |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  110 |   await expect(page.getByRole("button", { name: "After Refresh" })).toBeVisible();
  111 |   expect(refreshCalls).toBe(1);
  112 |   expect(trackCalls).toBe(2);
  113 |   expect(meCalls).toBeGreaterThanOrEqual(1);
  114 | });
  115 |
  116 | test("failed refresh clears session without infinite loop", async ({ page }) => {
  117 |   let refreshCalls = 0;
  118 |   let trackCalls = 0;
  119 |
  120 |   await page.route("**/api/v1/auth/me", (route) =>
  121 |     route.fulfill({ json: USER }),
  122 |   );
  123 |   await page.route("**/api/v1/me/assessments", (route) =>
  124 |     route.fulfill({
  125 |       json: {
  126 |         dashboard: {
  127 |           completed_interviews: 0,
  128 |           average_score: null,
  129 |           total_questions_attempted: 0,
  130 |           strongest_skills: [],
  131 |           skills_needing_improvement: [],
  132 |           recommended_topics: [],
  133 |         },
  134 |         assessments: [],
  135 |       },
  136 |     }),
  137 |   );
  138 |   await page.route("**/api/v1/auth/refresh", async (route) => {
  139 |     refreshCalls += 1;
  140 |     await route.fulfill({
  141 |       status: 401,
  142 |       contentType: "application/json",
  143 |       body: JSON.stringify({ detail: "Invalid refresh token" }),
  144 |     });
  145 |   });
  146 |   await page.route("**/api/v1/tracks", async (route) => {
  147 |     trackCalls += 1;
  148 |     await route.fulfill({
  149 |       status: 401,
  150 |       contentType: "application/json",
  151 |       body: JSON.stringify({ detail: "Not signed in" }),
  152 |     });
  153 |   });
  154 |
  155 |   await page.goto("/");
  156 |   // Auth failure should not hammer refresh.
  157 |   await page.waitForTimeout(500);
  158 |   expect(refreshCalls).toBe(1);
  159 |   expect(trackCalls).toBe(1);
  160 | });
  161 |
```
