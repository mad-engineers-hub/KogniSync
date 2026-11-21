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
  console.log('Starting Playwright capture for UI Refinement 01.2.2 (Timetable Feasibility)...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();

  // 1. Infeasible Scenario (Depart Nov 15, arrival deadline Nov 15 20:00)
  const infeasibleUrl = 'http://127.0.0.1:5173/results?origin=Udayapura&destination=Delhi&date=2026-11-15&arrivalBefore=20:00&carbonWeight=0.5&durationWeight=0.2&costWeight=0.15&comfortWeight=0.15';
  console.log(`Navigating to Infeasible Scenario: ${infeasibleUrl}`);
  await page.goto(infeasibleUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Capture Infeasible Result Cards / Map
  console.log('Capturing Screenshot 1: Infeasible Deadline Scenario...');
  const path1 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_2_infeasible_deadline.png');
  await page.screenshot({ path: path1, fullPage: false });
  await copyToArtifact(path1, 'ui_refinement_01_2_2_infeasible_deadline.png');
  console.log(`Saved: ${path1}`);

  // Select Greenest (Karnataka Express) to show its detailed breakdown and infeasibility warning
  const greenestBtn = page.locator('button:has-text("100% Electrified Net-Zero")').first();
  if (await greenestBtn.count() > 0) {
    await greenestBtn.click();
    await page.waitForTimeout(1500);
  }

  // Scroll to journey details
  await page.evaluate(() => window.scrollBy(0, 400));
  await page.waitForTimeout(1500);
  console.log('Capturing Screenshot 2: Karnataka Express Timetable & Infeasibility Breakdown...');
  const path2 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_2_karnataka_timetable.png');
  await page.screenshot({ path: path2, fullPage: false });
  await copyToArtifact(path2, 'ui_refinement_01_2_2_karnataka_timetable.png');
  console.log(`Saved: ${path2}`);

  // 2. Feasible Scenario (Depart Nov 13, arrival deadline Nov 15 20:00)
  const feasibleUrl = 'http://127.0.0.1:5173/results?origin=Udayapura&destination=Delhi&date=2026-11-13&arrivalBefore=2026-11-15T20:00&carbonWeight=0.5&durationWeight=0.2&costWeight=0.15&comfortWeight=0.15';
  console.log(`Navigating to Feasible Scenario: ${feasibleUrl}`);
  await page.goto(feasibleUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  const greenestBtnFeasible = page.locator('button:has-text("100% Electrified Net-Zero")').first();
  if (await greenestBtnFeasible.count() > 0) {
    await greenestBtnFeasible.click();
    await page.waitForTimeout(1500);
  }

  console.log('Capturing Screenshot 3: Feasible Train Schedule Scenario...');
  const path3 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_2_feasible_scenario.png');
  await page.screenshot({ path: path3, fullPage: false });
  await copyToArtifact(path3, 'ui_refinement_01_2_2_feasible_scenario.png');
  console.log(`Saved: ${path3}`);

  console.log('All UI Refinement 01.2.2 screenshots captured successfully!');
  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});

