import pkg from "../frontend/node_modules/@playwright/test/index.js";
const { chromium } = pkg;
import fs from "fs";
import path from "path";

const ARTIFACT_DIR = "C:/Users/prana/.gemini/antigravity/brain/8553bf43-3f92-4027-af43-b3620fb4d7de/scratch";
if (!fs.existsSync(ARTIFACT_DIR)) {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
}

// Generate valid access token via Python script beforehand or passed as arg
const token = process.argv[2];
if (!token) {
  console.error("Missing token arg");
  process.exit(1);
}

async function run() {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });

  // Set cookie for auth
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

  const consoleLogs = [];
  const networkErrors = [];

  page.on("console", (msg) => {
    consoleLogs.push({ type: msg.type(), text: msg.text() });
    if (msg.type() === "error") {
      console.log(`[Browser Console Error] ${msg.text()}`);
    }
  });

  page.on("pageerror", (err) => {
    console.log(`[Browser Page Error] ${err.message}`);
    consoleLogs.push({ type: "pageerror", text: err.message });
  });

  page.on("response", (res) => {
    if (res.status() >= 400) {
      console.log(`[HTTP ${res.status()}] ${res.url()}`);
      networkErrors.push({ url: res.url(), status: res.status() });
    }
  });

  console.log("Navigating to http://localhost:8080/ ...");
  await page.goto("http://localhost:8080/", { waitUntil: "networkidle" });

  await page.screenshot({ path: path.join(ARTIFACT_DIR, "01_dashboard.png"), fullPage: true });
  console.log("Dashboard loaded. Title:", await page.title());

  // Check if track cards are rendered
  const trackButtons = await page.getByRole("button", { name: "Open track" }).all();
  console.log(`Found ${trackButtons.length} "Open track" options/cards`);

  const headings = await page.getByRole("heading").allInnerTexts();
  console.log("Headings on Dashboard:", headings);

  // Navigate to Track Detail for first track
  // Check track links
  const sqlTrack = page.getByRole("link", { name: /SQL/i }).first();
  if (await sqlTrack.count() > 0) {
    console.log("Clicking SQL track link...");
    await sqlTrack.click();
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: path.join(ARTIFACT_DIR, "02_track_detail.png"), fullPage: true });
    console.log("Track detail URL:", page.url());
  } else {
    // Try first track card link
    const firstTrackLink = page.locator("a[href*='/tracks/']").first();
    if (await firstTrackLink.count() > 0) {
      console.log("Clicking first track link:", await firstTrackLink.getAttribute("href"));
      await firstTrackLink.click();
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: path.join(ARTIFACT_DIR, "02_track_detail.png"), fullPage: true });
    }
  }

  // Check if admin page is accessible
  console.log("Testing Admin page access /admin ...");
  await page.goto("http://localhost:8080/admin", { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "03_admin.png"), fullPage: true });
  console.log("Admin URL:", page.url());
  const adminHeadings = await page.getByRole("heading").allInnerTexts();
  console.log("Admin headings:", adminHeadings);

  // Test Profile page
  console.log("Testing Profile page /profile ...");
  await page.goto("http://localhost:8080/profile", { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "04_profile.png"), fullPage: true });
  console.log("Profile URL:", page.url());

  // Test Onboarding page
  console.log("Testing Onboarding page /onboarding ...");
  await page.goto("http://localhost:8080/onboarding", { waitUntil: "networkidle" });
  await page.screenshot({ path: path.join(ARTIFACT_DIR, "05_onboarding.png"), fullPage: true });
  console.log("Onboarding URL:", page.url());

  // Go back to Dashboard and test the Track Options modal / Delete dialog
  console.log("Testing Delete Track dialog on Dashboard...");
  await page.goto("http://localhost:8080/", { waitUntil: "networkidle" });
  const trackMenuButtons = page.getByRole("button", { name: "Track options" });
  const menuCount = await trackMenuButtons.count();
  console.log(`Found ${menuCount} Track options buttons`);

  if (menuCount > 0) {
    await trackMenuButtons.first().click();
    await page.waitForTimeout(300);
    const deleteBtn = page.getByRole("menuitem", { name: "Delete track" });
    if (await deleteBtn.isVisible()) {
      console.log("Delete menu item is visible, clicking it...");
      await deleteBtn.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(ARTIFACT_DIR, "06_delete_dialog.png") });
      const dialog = page.getByRole("dialog");
      console.log("Dialog visible?", await dialog.isVisible());
      console.log("Dialog text:", await dialog.innerText());
      // Click Cancel so we don't accidentally delete anything without user permission
      await dialog.getByRole("button", { name: "Cancel" }).click();
      console.log("Clicked Cancel on delete dialog.");
    }
  }

  await browser.close();
  console.log("Audit complete. Console logs count:", consoleLogs.length, "Network errors count:", networkErrors.length);
  fs.writeFileSync(
    path.join(ARTIFACT_DIR, "audit_summary.json"),
    JSON.stringify({ consoleLogs, networkErrors }, null, 2)
  );
}

run().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
