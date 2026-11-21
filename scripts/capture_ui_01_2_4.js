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
  console.log('Starting Playwright capture for UI Refinement 01.2.4 (Arrival Uncertainty Propagation & Connection Feasibility)...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR STACK:', err.stack || err.message));

  // Query: Depart 2026-11-15 from Udayapura to Delhi, refNow=2026-11-14T08:34:50+05:30
  const targetUrl = 'http://127.0.0.1:5173/results?origin=Udayapura&destination=Delhi&date=2026-11-15&arrivalBefore=20:00&carbonWeight=0.5&durationWeight=0.2&costWeight=0.15&comfortWeight=0.15&refNow=2026-11-14T08:34:50%2B05:30';
  console.log(`Navigating to Target Scenario: ${targetUrl}`);
  await page.goto(targetUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // 1. Select the train journey (Karnataka Express) card
  const trainCardButton = page.locator('button:has-text("100% Electrified Net-Zero")').first();
  if (await trainCardButton.count() > 0) {
    await trainCardButton.click();
    await page.waitForTimeout(1500);
  }

  // Scroll to show the journey card timing, leg 2 timetable, transfer buffer passenger readiness, and leg 3 frequency-based metro
  await page.evaluate(() => window.scrollBy(0, 360));
  await page.waitForTimeout(1500);

  console.log('Capturing Screenshot 1: Propagated Downstream Arrival Window & Connection Semantics...');
  const path1 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_4_propagated_arrival_window.png');
  await page.screenshot({ path: path1, fullPage: false });
  await copyToArtifact(path1, 'ui_refinement_01_2_4_propagated_arrival_window.png');
  console.log(`Saved: ${path1}`);

  // 2. Scroll to show feasibility advisory, operational regulation, and AI trade-off analysis
  await page.evaluate(() => window.scrollBy(0, 450));
  await page.waitForTimeout(1000);

  console.log('Capturing Screenshot 2: Connection Feasibility Semantics & Operational Notice...');
  const path2 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_4_connection_feasibility.png');
  await page.screenshot({ path: path2, fullPage: false });
  await copyToArtifact(path2, 'ui_refinement_01_2_4_connection_feasibility.png');
  console.log(`Saved: ${path2}`);

  // 3. Scroll back up to the interactive Leaflet Map below the header
  await page.evaluate(() => window.scrollTo(0, 80));
  await page.waitForTimeout(1000);

  try {
    const destMarker = page.locator('.custom-leaflet-marker').last();
    if (await destMarker.count() > 0) {
      await destMarker.click({ force: true });
      await page.waitForTimeout(1000);
    }
  } catch (e) {
    console.log('Could not click destination marker directly:', e.message);
  }

  console.log('Capturing Screenshot 3: Interactive Journey Map Destination Arrival Uncertainty Window...');
  const path3 = path.join(SCREENSHOT_DIR, 'ui_refinement_01_2_4_map_uncertainty_tooltip.png');
  await page.screenshot({ path: path3, fullPage: false });
  await copyToArtifact(path3, 'ui_refinement_01_2_4_map_uncertainty_tooltip.png');
  console.log(`Saved: ${path3}`);

  console.log('All UI Refinement 01.2.4 screenshots captured successfully!');
  await browser.close();
}

run().catch((err) => {
  console.error('Fatal error during capture:', err);
  process.exit(1);
});
