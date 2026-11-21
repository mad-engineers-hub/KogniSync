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
  console.log('Starting Playwright screenshot capture for UI Refinement 01.2...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();

  const targetUrl = 'http://127.0.0.1:5173/results?origin=Udayapura&destination=Delhi&date=2026-11-15&arrivalBefore=20:00&carbonWeight=0.5&durationWeight=0.2&costWeight=0.15&comfortWeight=0.15';
  console.log(`Navigating to ${targetUrl}...`);
  await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });

  // Wait for results to render
  await page.waitForTimeout(3000);

  // Look for Greenest route button if not already selected
  const greenestBtn = page.locator('button:has-text("100% Electrified Net-Zero")').first();
  if (await greenestBtn.count() > 0) {
    console.log('Selecting 100% Electrified Net-Zero Transit Corridor (Greenest)...');
    await greenestBtn.click();
    await page.waitForTimeout(1500);
  }

  // 1. Full Udayapura-to-Delhi map (ui_refinement_01_2_national_corridor.png)
  console.log('Capturing Screenshot 1: National Corridor Map...');
  const mapContainer = page.locator('.rounded-2xl.border.border-slate-200.bg-white').first();
  if (await mapContainer.count() > 0) {
    await mapContainer.scrollIntoViewIfNeeded();
    await page.waitForTimeout(1500);
    const fitBtn = page.locator('button[title="Fit Whole Route"]').first();
    if (await fitBtn.count() > 0) {
      await fitBtn.click();
      await page.waitForTimeout(2000);
    }
    const path1 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_national_corridor.png');
    await mapContainer.screenshot({ path: path1 });
    await copyToArtifact(path1, 'ui_refinement_01_2_national_corridor.png');
    console.log(`Saved: ${path1}`);
  }

  // 2. Udayapura-to-KSR feeder leg (ui_refinement_01_2_feeder_leg.png)
  console.log('Capturing Screenshot 2: Udayapura-to-KSR Feeder Leg...');
  const originBtn = page.locator('button[title="Focus Origin"]').first();
  if (await originBtn.count() > 0) {
    await originBtn.click();
    await page.waitForTimeout(1500);
  }
  // Click on segment 1 in the segment bar if present
  const seg1Bar = page.locator('text=Bangalore Rapid EV Shuttle').first();
  if (await seg1Bar.count() > 0) {
    await seg1Bar.click();
    await page.waitForTimeout(1000);
  }
  const path2 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_feeder_leg.png');
  await mapContainer.screenshot({ path: path2 });
  await copyToArtifact(path2, 'ui_refinement_01_2_feeder_leg.png');
  console.log(`Saved: ${path2}`);

  // 3. Intercity railway corridor (ui_refinement_01_2_railway_corridor.png)
  console.log('Capturing Screenshot 3: Intercity Railway Corridor...');
  const fitBtn2 = page.locator('button[title="Fit Whole Route"]').first();
  if (await fitBtn2.count() > 0) {
    await fitBtn2.click();
    await page.waitForTimeout(1000);
  }
  const leg2Btn = page.locator('text=Karnataka Express').first();
  if (await leg2Btn.count() > 0) {
    await leg2Btn.click();
    await page.waitForTimeout(1500);
  }
  const path3 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_railway_corridor.png');
  await mapContainer.screenshot({ path: path3 });
  await copyToArtifact(path3, 'ui_refinement_01_2_railway_corridor.png');
  console.log(`Saved: ${path3}`);

  // 4. Correct Delhi destination leg (ui_refinement_01_2_delhi_destination.png)
  console.log('Capturing Screenshot 4: Delhi Destination Leg...');
  const destBtn = page.locator('button[title="Focus Destination"]').first();
  if (await destBtn.count() > 0) {
    await destBtn.click();
    await page.waitForTimeout(1500);
  }
  const leg3Btn = page.locator('text=Delhi Metro (Yellow Line)').first();
  if (await leg3Btn.count() > 0) {
    await leg3Btn.click();
    await page.waitForTimeout(1500);
  }
  const path4 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_delhi_destination.png');
  await mapContainer.screenshot({ path: path4 });
  await copyToArtifact(path4, 'ui_refinement_01_2_delhi_destination.png');
  console.log(`Saved: ${path4}`);

  // 5. Segment details and total summary (ui_refinement_01_2_summary_reconciliation.png)
  console.log('Capturing Screenshot 5: Segment Details & Total Reconciliation...');
  // Scroll down to the journey cards and summary section
  await page.evaluate(() => window.scrollBy(0, 450));
  await page.waitForTimeout(1500);
  const path5 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_summary_reconciliation.png');
  await page.screenshot({ path: path5, fullPage: false });
  await copyToArtifact(path5, 'ui_refinement_01_2_summary_reconciliation.png');
  console.log(`Saved: ${path5}`);

  console.log('All 5 screenshots captured successfully!');
  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});

