import pkg from "../frontend/node_modules/@playwright/test/index.js";
const { chromium } = pkg;
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/prana/.gemini/antigravity/brain/8553bf43-3f92-4027-af43-b3620fb4d7de/scratch";
const token = process.argv[2];
const trackId = "1eca1524-8030-4d40-9253-03de9c424304";

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

  console.log(`Navigating to Track Detail: http://localhost:8080/tracks/${trackId}`);
  await page.goto(`http://localhost:8080/tracks/${trackId}`, { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "15_new_track_detail.png"), fullPage: true });

  const startInterviewBtn = page.getByRole("button", { name: "Start interview" });
  console.log("Start interview button visible?", await startInterviewBtn.isVisible());
  await startInterviewBtn.click();
  await page.waitForTimeout(500);

  await page.screenshot({ path: path.join(ARTIFACT_DIR, "16_start_modal.png") });

  const modalStartBtn = page.getByRole("dialog").getByRole("button", { name: "Start interview" });
  console.log("Modal start button visible?", await modalStartBtn.isVisible());
  console.log("Clicking Start interview inside modal (triggers session + first turn LLM)...");
  await modalStartBtn.click();

  console.log("Waiting for /api/v1/tracks/.../sessions response...");
  const sessRes = await page.waitForResponse(
    (r) => r.url().includes("/sessions") && r.request().method() === "POST",
    { timeout: 90000 }
  );
  console.log("Start session status:", sessRes.status());
  const sessData = await sessRes.json();
  console.log("Start session body:", JSON.stringify(sessData).slice(0, 300));

  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "17_live_interview_turn1.png"), fullPage: true });

  console.log("Interview URL:", page.url());
  const text = await page.innerText("body");
  console.log("Page text sample:\n", text.slice(0, 400));

  await browser.close();
}

run().catch((e) => {
  console.error("Test error:", e);
  process.exit(1);
});
