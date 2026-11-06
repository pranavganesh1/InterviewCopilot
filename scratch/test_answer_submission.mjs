import pkg from "../frontend/node_modules/@playwright/test/index.js";
const { chromium } = pkg;
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/prana/.gemini/antigravity/brain/8553bf43-3f92-4027-af43-b3620fb4d7de/scratch";
const token = process.argv[2];
const trackId = "1eca1524-8030-4d40-9253-03de9c424304";
const sessionId = "9f4e0a09-eec8-4ad2-a981-c1206be2e29b";

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

  const url = `http://localhost:8080/tracks/${trackId}/interview/${sessionId}`;
  console.log(`Navigating to live interview: ${url}`);
  await page.goto(url, { waitUntil: "networkidle" });

  await page.screenshot({ path: path.join(ARTIFACT_DIR, "18_live_question.png"), fullPage: true });

  const questionText = await page.getByTestId("question-text").innerText().catch(() => null);
  console.log("Question text:", questionText);

  // Check if answer composer is visible
  const textarea = page.locator("textarea");
  console.log("Textarea visible?", await textarea.isVisible());

  if (await textarea.isVisible()) {
    const candidateAnswer = "volatile-lru evicts keys with an expire set using the least recently used algorithm, while allkeys-lru evicts any key regardless of whether an expiration is set.";
    console.log("Typing answer into textarea...");
    await textarea.fill(candidateAnswer);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, "19_answer_typed.png"), fullPage: true });

    const submitBtn = page.getByRole("button", { name: "Submit answer" });
    console.log("Submit button visible?", await submitBtn.isVisible());
    console.log("Clicking Submit answer...");
    await submitBtn.click();

    console.log("Waiting for /turns response...");
    const turnRes = await page.waitForResponse(
      (r) => r.url().includes("/turns") && r.request().method() === "POST",
      { timeout: 90000 }
    );
    console.log("Turn submit status:", turnRes.status());
    const turnData = await turnRes.json();
    console.log("Turn response:", JSON.stringify(turnData).slice(0, 300));

    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, "20_feedback_or_next.png"), fullPage: true });
  }

  await browser.close();
}

run().catch((e) => {
  console.error("Test error:", e);
  process.exit(1);
});
