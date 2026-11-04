import { expect, test } from "@playwright/test";
import {
  _resetAuthRefreshStateForTests,
  refreshAccessToken,
  shouldAttemptRefresh,
} from "../src/lib/authRefresh";

test.describe("authRefresh helpers", () => {
  test.beforeEach(() => {
    _resetAuthRefreshStateForTests();
  });

  test("refresh is attempted only once per request path", () => {
    expect(shouldAttemptRefresh("/tracks", false)).toBe(true);
    expect(shouldAttemptRefresh("/tracks", true)).toBe(false);
    expect(shouldAttemptRefresh("/auth/refresh", false)).toBe(false);
    expect(shouldAttemptRefresh("/auth/logout", false)).toBe(false);
  });

  test("concurrent refresh calls share one in-flight request", async () => {
    let calls = 0;
    const fetchImpl: typeof fetch = async () => {
      calls += 1;
      await new Promise((r) => setTimeout(r, 30));
      return new Response(null, { status: 204 });
    };
    const [a, b, c] = await Promise.all([
      refreshAccessToken(fetchImpl),
      refreshAccessToken(fetchImpl),
      refreshAccessToken(fetchImpl),
    ]);
    expect(a && b && c).toBe(true);
    expect(calls).toBe(1);
  });

  test("failed refresh returns false", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ detail: "No refresh token" }), {
        status: 401,
      });
    expect(await refreshAccessToken(fetchImpl)).toBe(false);
  });
});

const USER = {
  id: "u1",
  email: "student@example.com",
  name: "Student",
  picture_url: null,
};

test("expired access token refreshes once and retries original request", async ({
  page,
}) => {
  let meCalls = 0;
  let trackCalls = 0;
  let refreshCalls = 0;

  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshCalls += 1;
    await route.fulfill({ status: 204 });
  });
  await page.route("**/api/v1/auth/me", async (route) => {
    meCalls += 1;
    // First auth/me after load succeeds so we reach the dashboard.
    await route.fulfill({ json: USER });
  });
  await page.route("**/api/v1/tracks", async (route) => {
    trackCalls += 1;
    if (trackCalls === 1) {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Not signed in" }),
      });
      return;
    }
    await route.fulfill({
      json: [
        {
          id: "t1",
          track_type: "role",
          subject: "After Refresh",
          company: null,
          status: "active",
          created_at: "2026-11-03T00:00:00Z",
          brief_version: 1,
        },
      ],
    });
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: "After Refresh" })).toBeVisible();
  expect(refreshCalls).toBe(1);
  expect(trackCalls).toBe(2);
  expect(meCalls).toBeGreaterThanOrEqual(1);
});

test("failed refresh clears session without infinite loop", async ({ page }) => {
  let refreshCalls = 0;
  let trackCalls = 0;

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({ json: USER }),
  );
  await page.route("**/api/v1/auth/refresh", async (route) => {
    refreshCalls += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Invalid refresh token" }),
    });
  });
  await page.route("**/api/v1/tracks", async (route) => {
    trackCalls += 1;
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not signed in" }),
    });
  });

  await page.goto("/");
  // Auth failure should not hammer refresh.
  await page.waitForTimeout(500);
  expect(refreshCalls).toBe(1);
  expect(trackCalls).toBe(1);
});
