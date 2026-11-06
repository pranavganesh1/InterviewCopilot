# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend\e2e\codingWorkspace.spec.ts >> language tabs switch without leaving workspace
- Location: frontend\e2e\codingWorkspace.spec.ts:125:1

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/tracks/t1/interview/code2", waiting until "load"

```

# Test source

```ts
  48  |   );
  49  | });
  50  |
  51  | test("coding question shows workspace; text question keeps textarea", async ({
  52  |   page,
  53  | }) => {
  54  |   const codingTurns = [
  55  |     {
  56  |       turn_index: 1,
  57  |       question_area: "Arrays",
  58  |       question:
  59  |         "Write a function that finds two numbers in an array that sum to a target.\nConstraints:\n- 2 <= n <= 10^4\nExample 1:\nInput: [2,7,11], 9\nOutput: [0,1]",
  60  |       answer: null as string | null,
  61  |       evaluation: null,
  62  |       assistance_level: 0,
  63  |     },
  64  |   ];
  65  |
  66  |   await page.route("**/api/v1/sessions/code1", (route) =>
  67  |     route.fulfill({
  68  |       json: {
  69  |         session: {
  70  |           id: "code1",
  71  |           track_id: "t1",
  72  |           mode: "guided",
  73  |           status: "in_progress",
  74  |         },
  75  |         turns: codingTurns,
  76  |       },
  77  |     }),
  78  |   );
  79  |
  80  |   await page.goto("/tracks/t1/interview/code1");
  81  |   const workspace = page.getByTestId("coding-workspace");
  82  |   await expect(workspace).toBeVisible();
  83  |   await expect(workspace.getByRole("button", { name: "Python" })).toBeVisible();
  84  |   await expect(workspace.getByRole("button", { name: "Java" })).toBeVisible();
  85  |   await expect(workspace.getByRole("button", { name: "C" })).toBeVisible();
  86  |   const runBtn = workspace.getByTestId("run-disabled");
  87  |   await expect(runBtn).toBeVisible();
  88  |   await expect(runBtn).toBeDisabled();
  89  |   await expect(workspace.getByRole("button", { name: "Submit Answer" })).toBeVisible();
  90  |   await expect(workspace.getByTestId("ai-reviewed-badge")).toHaveText(
  91  |     /AI-reviewed, not executed/i,
  92  |   );
  93  |   await expect(page.getByRole("heading", { name: "Need Help?" })).toBeVisible();
  94  |
  95  |   // Text / conceptual path still uses the classic answer box.
  96  |   await page.route("**/api/v1/sessions/text1", (route) =>
  97  |     route.fulfill({
  98  |       json: {
  99  |         session: {
  100 |           id: "text1",
  101 |           track_id: "t1",
  102 |           mode: "strict",
  103 |           status: "in_progress",
  104 |         },
  105 |         turns: [
  106 |           {
  107 |             turn_index: 1,
  108 |             question_area: "Behavioral",
  109 |             question: "Tell me about a time you led a difficult project.",
  110 |             answer: null,
  111 |             evaluation: null,
  112 |           },
  113 |         ],
  114 |       },
  115 |     }),
  116 |   );
  117 |   await page.goto("/tracks/t1/interview/text1");
  118 |   await expect(page.getByTestId("coding-workspace")).toHaveCount(0);
  119 |   await expect(page.getByRole("button", { name: "Submit Answer" })).toBeVisible();
  120 |   await expect(
  121 |     page.getByPlaceholder(/no hints in strict mode/i),
  122 |   ).toBeVisible();
  123 | });
  124 |
  125 | test("language tabs switch without leaving workspace", async ({ page }) => {
  126 |   await page.route("**/api/v1/sessions/code2", (route) =>
  127 |     route.fulfill({
  128 |       json: {
  129 |         session: {
  130 |           id: "code2",
  131 |           track_id: "t1",
  132 |           mode: "strict",
  133 |           status: "in_progress",
  134 |         },
  135 |         turns: [
  136 |           {
  137 |             turn_index: 1,
  138 |             question_area: "Algorithms",
  139 |             question: "Implement merge sort and discuss its time complexity.",
  140 |             answer: null,
  141 |             evaluation: null,
  142 |             assistance_level: 0,
  143 |           },
  144 |         ],
  145 |       },
  146 |     }),
  147 |   );
> 148 |   await page.goto("/tracks/t1/interview/code2");
      |              ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  149 |   const workspace = page.getByTestId("coding-workspace");
  150 |   await workspace.getByRole("button", { name: "Java" }).click();
  151 |   await expect(workspace.getByRole("button", { name: "Java" })).toHaveClass(
  152 |     /bg-indigo-600/,
  153 |   );
  154 |   await workspace.getByRole("button", { name: "C" }).click();
  155 |   await expect(workspace.getByRole("button", { name: "C" })).toHaveClass(
  156 |     /bg-indigo-600/,
  157 |   );
  158 |   await expect(
  159 |     page.getByText(/Strict mode: no solutions before you submit/i),
  160 |   ).toBeVisible();
  161 | });
  162 |
```
