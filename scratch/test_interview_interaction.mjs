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

  const networkErrors = [];
  const consoleLogs = [];
  page.on("console", (m) => consoleLogs.push({ type: m.type(), text: m.text() }));
  page.on("response", (r) => {
    if (r.status() >= 400) {
      console.log(`[HTTP ${r.status()}] ${r.url()}`);
      networkErrors.push({ url: r.url(), status: r.status() });
    }
  });

  const trackId = "0d91e79d-d9a5-4aa1-bc60-4d82bb9fe9e7";
  const sessionId = "9a161de0-55be-4138-8cdf-b9ac5f105ed3";

  console.log(`Navigating to interview page: /tracks/${trackId}/interview/${sessionId}`);
  await page.goto(`http://localhost:8080/tracks/${trackId}/interview/${sessionId}`, {
    waitUntil: "networkidle",
  });

  await page.screenshot({ path: path.join(ARTIFACT_DIR, "07_interview_page.png"), fullPage: true });

  const bodyText = await page.innerText("body");
  console.log("Interview page text preview:", bodyText.slice(0, 300));

  // Check if answer input is present (textarea or Monaco)
  const textarea = page.locator("textarea");
  const hasTextarea = (await textarea.count()) > 0;
  console.log("Has textarea?", hasTextarea);

  // Check if Monaco or code editor is present
  const monaco = page.locator(".monaco-editor");
  const hasMonaco = (await monaco.count()) > 0;
  console.log("Has Monaco?", hasMonaco);

  // Check buttons
  const buttons = await page.getByRole("button").allInnerTexts();
  console.log("Visible buttons on interview page:", buttons);

  // Check Track detail page specifically
  console.log(`Navigating to track detail: /tracks/${trackId}`);
  await page.goto(`http://localhost:8080/tracks/${trackId}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "08_track_detail_sql.png"), fullPage: true });
  console.log("Track detail headings:", await page.getByRole("heading").allInnerTexts());
  console.log("Track detail buttons:", await page.getByRole("button").allInnerTexts());

  await browser.close();
  console.log("Interview & Track detail test finished. Network errors:", networkErrors.length);
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
