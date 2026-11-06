import pkg from "../frontend/node_modules/@playwright/test/index.js";
const { chromium } = pkg;
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/prana/.gemini/antigravity/brain/8553bf43-3f92-4027-af43-b3620fb4d7de/scratch";
const token = process.argv[2];

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });

  await context.addCookies([
    {
      name: "ic_access",
      value: token,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  const page = await context.newPage();

  page.on("console", (m) => console.log(`[Browser Console ${m.type()}] ${m.text()}`));
  page.on("response", (r) => {
    if (r.status() >= 400) {
      console.log(`[HTTP ${r.status()}] ${r.url()}`);
    }
  });

  console.log("Navigating to http://localhost:8080/ ...");
  await page.goto("http://localhost:8080/", { waitUntil: "networkidle" });

  const newTrackBtn = page.getByRole("button", { name: /\+ New track/i });
  console.log("New track button exists?", await newTrackBtn.isVisible());

  await newTrackBtn.click();
  await page.waitForTimeout(500);

  const subjectInput = page.locator("#track-subject");
  console.log("Subject input visible?", await subjectInput.isVisible());
  await subjectInput.fill("Redis and Caching Patterns");

  const createTrackBtn = page.getByRole("button", { name: /^Create track$/i });
  console.log("Create track button visible?", await createTrackBtn.isVisible());
  console.log("Clicking Create track (triggers LLM generation)...");
  await createTrackBtn.click();

  // Wait for track creation
  console.log("Waiting for track creation response...");
  const res = await page.waitForResponse(
    (r) => r.url().includes("/api/v1/tracks") && r.request().method() === "POST",
    { timeout: 90000 }
  );
  console.log("Track creation response status:", res.status());
  const json = await res.json();
  console.log("Track creation response body:", JSON.stringify(json).slice(0, 300));

  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "11_track_created.png"), fullPage: true });

  await browser.close();
}

run().catch((e) => {
  console.error("Test error:", e);
  process.exit(1);
});
