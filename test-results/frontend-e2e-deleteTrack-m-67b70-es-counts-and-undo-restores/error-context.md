# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\deleteTrack.spec.ts >> menu opens and closes, delete updates counts, and undo restores
- Location: frontend\e2e\deleteTrack.spec.ts:49:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/", waiting until "load"

```

# Test source

```ts
  5   |   email: "student@example.com",
  6   |   name: "Student",
  7   |   picture_url: null,
  8   | };
  9   |
  10  | type TrackRow = {
  11  |   id: string;
  12  |   track_type: string;
  13  |   subject: string;
  14  |   company: string | null;
  15  |   status: string;
  16  |   archived: boolean;
  17  |   archived_at: string | null;
  18  |   created_at: string;
  19  |   brief_version: number;
  20  | };
  21  |
  22  | function assessment(trackId: string) {
  23  |   return {
  24  |     report_id: "r1",
  25  |     session_id: "s1",
  26  |     track_id: trackId,
  27  |     track_subject: "Graphs",
  28  |     created_at: "2026-11-01T00:00:00Z",
  29  |     session_mode: "strict",
  30  |     coverage_status: "PARTIAL",
  31  |     overall_score: 80,
  32  |     questions_attempted: 1,
  33  |     max_turns: 15,
  34  |     status: "completed",
  35  |     track_archived: false,
  36  |     summary_overview: "Kept.",
  37  |     strengths: [],
  38  |     improvement_areas: [],
  39  |   };
  40  | }
  41  |
  42  | test.beforeEach(async ({ page }) => {
  43  |   await page.route("**/api/v1/auth/me", (route) => route.fulfill({ json: USER }));
  44  |   await page.route("**/api/v1/auth/logout", (route) =>
  45  |     route.fulfill({ json: { status: "ok" } }),
  46  |   );
  47  | });
  48  |
  49  | test("menu opens and closes, delete updates counts, and undo restores", async ({ page }) => {
  50  |   const tracks: TrackRow[] = [
  51  |     {
  52  |       id: "t1",
  53  |       track_type: "topic",
  54  |       subject: "Graphs",
  55  |       company: null,
  56  |       status: "active",
  57  |       archived: false,
  58  |       archived_at: null,
  59  |       created_at: "2026-11-01T00:00:00Z",
  60  |       brief_version: 1,
  61  |     },
  62  |   ];
  63  |   let archived = false;
  64  |
  65  |   await page.route("**/api/v1/me/assessments", (route) =>
  66  |     route.fulfill({
  67  |       json: {
  68  |         dashboard: {
  69  |           completed_interviews: archived ? 0 : 1,
  70  |           average_score: archived ? null : 80,
  71  |           total_questions_attempted: archived ? 0 : 1,
  72  |           strongest_skills: [],
  73  |           skills_needing_improvement: [],
  74  |           recommended_topics: [],
  75  |         },
  76  |         assessments: [{ ...assessment("t1"), track_archived: archived }],
  77  |       },
  78  |     }),
  79  |   );
  80  |   await page.route("**/api/v1/tracks**", async (route) => {
  81  |     const request = route.request();
  82  |     const url = request.url();
  83  |     if (request.method() === "DELETE") {
  84  |       archived = true;
  85  |       tracks[0].archived = true;
  86  |       tracks[0].archived_at = "2026-11-06T00:00:00Z";
  87  |       await route.fulfill({
  88  |         json: { track: tracks[0] },
  89  |       });
  90  |       return;
  91  |     }
  92  |     if (request.method() === "POST" && url.includes("/restore")) {
  93  |       archived = false;
  94  |       tracks[0].archived = false;
  95  |       tracks[0].archived_at = null;
  96  |       await route.fulfill({ json: { track: tracks[0] } });
  97  |       return;
  98  |     }
  99  |     const include = url.includes("include_archived=true");
  100 |     await route.fulfill({
  101 |       json: include ? tracks : tracks.filter((item) => !item.archived),
  102 |     });
  103 |   });
  104 |
> 105 |   await page.goto("/");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  106 |   await expect(page.getByText("Interviews Taken").locator("xpath=..")).toContainText("1");
  107 |   await page.getByRole("button", { name: "Track options" }).click();
  108 |   await expect(page.getByRole("menuitem", { name: "Open track" })).toBeVisible();
  109 |   await expect(page.getByRole("menuitem", { name: "Delete track" })).toBeVisible();
  110 |   await page.keyboard.press("ArrowDown");
  111 |   await expect(page.getByRole("menuitem", { name: "Latest report" })).toBeFocused();
  112 |   await page.getByRole("heading", { name: "Preparation tracks" }).click();
  113 |   await expect(page.getByRole("menu")).toHaveCount(0);
  114 |
  115 |   await page.getByRole("button", { name: "Track options" }).click();
  116 |   await page.keyboard.press("Escape");
  117 |   await expect(page.getByRole("menu")).toHaveCount(0);
  118 |
  119 |   await page.getByRole("button", { name: "Track options" }).click();
  120 |   await page.getByRole("menuitem", { name: "Delete track" }).click();
  121 |   const dialog = page.getByRole("dialog");
  122 |   await expect(dialog.getByRole("heading", { name: "Delete this track?" })).toBeVisible();
  123 |   await expect(dialog.getByText("Graphs")).toBeVisible();
  124 |   await expect(dialog.getByText("1 attempt, 1 report")).toBeVisible();
  125 |   await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  126 |   await page.keyboard.press("Shift+Tab");
  127 |   await expect(dialog.getByRole("button", { name: "Delete track" })).toBeFocused();
  128 |   await page.keyboard.press("Enter");
  129 |
  130 |   await expect(page.getByRole("button", { name: "Graphs" })).toHaveCount(0);
  131 |   await expect(page.getByText("Total Tracks").locator("xpath=..")).toContainText("0");
  132 |   await expect(page.getByText("Interviews Taken").locator("xpath=..")).toContainText("0");
  133 |   await expect(page.getByRole("status")).toContainText("Track deleted");
  134 |   await page.getByRole("button", { name: "Undo" }).click();
  135 |   await expect(page.getByRole("button", { name: "Graphs" })).toBeVisible();
  136 |   await expect(page.getByText("Total Tracks").locator("xpath=..")).toContainText("1");
  137 | });
  138 |
  139 | test("open-session conflict offers resume and finish", async ({ page }) => {
  140 |   await page.route("**/api/v1/me/assessments", (route) =>
  141 |     route.fulfill({
  142 |       json: {
  143 |         dashboard: {
  144 |           completed_interviews: 0,
  145 |           average_score: null,
  146 |           total_questions_attempted: 0,
  147 |           strongest_skills: [],
  148 |           skills_needing_improvement: [],
  149 |           recommended_topics: [],
  150 |         },
  151 |         assessments: [],
  152 |       },
  153 |     }),
  154 |   );
  155 |   await page.route("**/api/v1/tracks**", async (route) => {
  156 |     if (route.request().method() === "DELETE") {
  157 |       await route.fulfill({
  158 |         status: 409,
  159 |         json: {
  160 |           detail: {
  161 |             code: "unfinished_interview",
  162 |             message: "Finish or close your unfinished interview first",
  163 |             session_id: "sess-open",
  164 |           },
  165 |         },
  166 |       });
  167 |       return;
  168 |     }
  169 |     await route.fulfill({
  170 |       json: [
  171 |         {
  172 |           id: "t1",
  173 |           track_type: "topic",
  174 |           subject: "Graphs",
  175 |           company: null,
  176 |           status: "active",
  177 |           archived: false,
  178 |           created_at: "2026-11-01T00:00:00Z",
  179 |         },
  180 |       ],
  181 |     });
  182 |   });
  183 |   await page.route("**/api/v1/sessions/sess-open/complete", (route) =>
  184 |     route.fulfill({ json: { session: { id: "sess-open", status: "completed" } } }),
  185 |   );
  186 |   await page.route("**/api/v1/sessions/sess-open**", (route) =>
  187 |     route.fulfill({ json: { session: { id: "sess-open", status: "in_progress" } } }),
  188 |   );
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
```
