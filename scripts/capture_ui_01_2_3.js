const fs = require('fs');
const path = require('path');

// Portable Playwright resolution
let chromium;
try {
  chromium = require('playwright').chromium;
} catch {
  try {
    chromium = require('@playwright/test').chromium;
  } catch {
    console.error('Playwright module not found. Please ensure playwright is installed.');
    process.exit(1);
  }
}

const ARTIFACT_DIR = process.env.ARTIFACT_DIR || path.resolve(__dirname, '../artifacts');
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR || path.resolve(__dirname, '../docs/demo/screenshots');

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function copyToArtifact(filePath, filename) {
  if (!process.env.ARTIFACT_DIR && !fs.existsSync(ARTIFACT_DIR)) {
    return;
  }
  try {
    if (!fs.existsSync(ARTIFACT_DIR)) {
      fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
    }
    const dest = path.join(ARTIFACT_DIR, filename);
    fs.copyFileSync(filePath, dest);
    console.log(`Copied ${filename} to artifact directory: ${dest}`);
  } catch (err) {
    console.error(`Error copying to artifact dir:`, err.message);
  }
}

async function run() {
  console.log('Starting Playwright capture for UI Refinement 01.2.3 (Operational Timetable & Actionable Validation)...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR STACK:', err.stack || err.message));

  // 1. Capture Infeasible Scenario with Past Departure Elimination & Regulation Banner
  // Query: Depart 2026-11-15, arrival deadline 20:00, refNow=2026-11-14T08:34:50+05:30
  const infeasibleUrl = 'http://127.0.0.1:5173/results?origin=Udayapura&destination=Delhi&date=2026-11-15&arrivalBefore=20:00&carbonWeight=0.5&durationWeight=0.2&costWeight=0.15&comfortWeight=0.15&refNow=2026-11-14T08:34:50%2B05:30';
  console.log(`Navigating to Infeasible Scenario: ${infeasibleUrl}`);
  await page.goto(infeasibleUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Select the train journey (Karnataka Express) card
  const trainCardButton = page.locator('button:has-text("100% Electrified Net-Zero")').first();
  if (await trainCardButton.count() > 0) {
    await trainCardButton.click();
    await page.waitForTimeout(1500);
  }

  // Scroll to journey details where the operational notice banner and schedule state are located
  await page.evaluate(() => window.scrollBy(0, 380));
  await page.waitForTimeout(1500);

  console.log('Capturing Screenshot 1: Operational Regulation Banner & Schedule State...');
  const path1 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_3_operational_regulation.png');
  await page.screenshot({ path: path1, fullPage: false });
  await copyToArtifact(path1, 'ui_refinement_01_2_3_operational_regulation.png');
  console.log(`Saved: ${path1}`);

  // Scroll to reveal the full feasibility advisory notes (past departure elimination + actionable flight promotion)
  await page.evaluate(() => window.scrollTo(0, 950));
  await page.waitForTimeout(1000);

  console.log('Capturing Screenshot 2: Infeasible Deadline Advisory & Past Departure Elimination...');
  const path2 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_3_past_departure_elimination.png');
  await page.screenshot({ path: path2, fullPage: false });
  await copyToArtifact(path2, 'ui_refinement_01_2_3_past_departure_elimination.png');
  console.log(`Saved: ${path2}`);

  // Scroll to view the actionable flight option details
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(800);

  const flightBtn = page.locator('button:has-text("SyncAir Multi-Modal Link")').first();
  if (await flightBtn.count() > 0) {
    await flightBtn.click();
    await page.waitForTimeout(1500);
  }

  // Scroll down to the selected flight card
  const flightCard = page.locator('.rounded-2xl:has-text("SyncAir Multi-Modal Link")').first();
  if (await flightCard.count() > 0) {
    await flightCard.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);
  } else {
    await page.evaluate(() => window.scrollTo(0, 550));
    await page.waitForTimeout(1000);
  }

  console.log('Capturing Screenshot 3: Actionable Future Alternative (Fastest Flight Option)...');
  const path3 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_3_actionable_alternatives.png');
  await page.screenshot({ path: path3, fullPage: false });
  await copyToArtifact(path3, 'ui_refinement_01_2_3_actionable_alternatives.png');
  console.log(`Saved: ${path3}`);

  console.log('All UI Refinement 01.2.3 screenshots captured successfully!');
  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});
