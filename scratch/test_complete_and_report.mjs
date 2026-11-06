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

  const finishExitBtn = page.getByRole("button", { name: "Finish Assessment & Exit" });
  console.log("Finish Assessment & Exit visible?", await finishExitBtn.isVisible());

  if (await finishExitBtn.isVisible()) {
    console.log("Clicking Finish Assessment & Exit...");
    await finishExitBtn.click();
    await page.waitForTimeout(500);

    await page.screenshot({ path: path.join(ARTIFACT_DIR, "21_finish_confirmation_modal.png") });

    // The modal asks to confirm finish
    const confirmBtn = page.getByRole("dialog").getByRole("button", { name: /Finish and get feedback|Finish/i }).last();
    console.log("Confirm finish button visible?", await confirmBtn.isVisible());
    console.log("Clicking confirm finish...");
    await confirmBtn.click();

    // Wait for redirect to /report/:sessionId
    console.log("Waiting for navigation to report page...");
    await page.waitForURL((u) => u.pathname.includes(`/report/${sessionId}`), { timeout: 30000 });
    console.log("Landed on report page:", page.url());

    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(ARTIFACT_DIR, "22_report_page_initial.png"), fullPage: true });

    // Report is generated asynchronously by backend-worker via NATS. Let's poll/wait up to 30s
    console.log("Checking if report is ready or pending...");
    for (let i = 0; i < 15; i++) {
      const text = await page.innerText("body");
      if (text.includes("Generating feedback") || text.includes("Feedback pending") || text.includes("pending")) {
        console.log(`[Poll ${i}] Feedback still pending, waiting...`);
        await page.waitForTimeout(2000);
      } else {
        console.log(`[Poll ${i}] Report seems rendered!`);
        break;
      }
    }

    await page.screenshot({ path: path.join(ARTIFACT_DIR, "23_report_page_final.png"), fullPage: true });
    console.log("Report page text preview:\n", (await page.innerText("body")).slice(0, 500));
  }

  await browser.close();
}

run().catch((e) => {
  console.error("Test error:", e);
  process.exit(1);
});
