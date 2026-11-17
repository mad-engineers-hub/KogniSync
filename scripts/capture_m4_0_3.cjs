const fs = require('fs');
const path = require('path');
const { chromium } = require('C:/Users/deeks/node_modules/playwright');

const ARTIFACT_DIR = 'C:/Users/deeks/.gemini/antigravity/brain/9b5a137c-314e-48a7-90a3-3db3f30932a6';
const SCREENSHOT_DIR = path.resolve(__dirname, '../docs/screenshots');

if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function copyToArtifact(filePath, filename) {
  try {
    const dest = path.join(ARTIFACT_DIR, filename);
    fs.copyFileSync(filePath, dest);
    console.log(`Copied ${filename} to artifact directory: ${dest}`);
  } catch (err) {
    console.error(`Error copying to artifact dir:`, err.message);
  }
}

async function run() {
  console.log('Starting Playwright capture for M4.0.3 (Dynamic Origin/Destination Synchronization)...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 1.5,
  });
  const page = await context.newPage();

  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', err => console.log('PAGE ERROR STACK:', err.stack || err.message));

  // =========================================================================
  // SCENARIO 1: Tumkur -> Chennai
  // =========================================================================
  const tumkurUrl = 'http://localhost:5175/plan?origin=Tumkur&destination=Chennai&date=2026-11-16&passengers=1';
  console.log(`\nNavigating to Scenario 1: ${tumkurUrl}`);
  await page.goto(tumkurUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
  
  // Wait for journey results and Leaflet markers to render
  console.log('Waiting for journey map to load...');
  await page.waitForSelector('.custom-leaflet-marker', { timeout: 20000 });
  await page.waitForTimeout(1500);

  // Scroll to show map and active journey
  await page.evaluate(() => window.scrollBy(0, 240));
  await page.waitForTimeout(1000);

  // Click on the green origin marker to display popup
  console.log('Clicking green origin marker at Tumkur...');
  const originMarker = page.locator('.custom-leaflet-marker').first();
  if (await originMarker.count() > 0) {
    await originMarker.click();
    await page.waitForTimeout(1000);
  }

  const shot1Path = path.join(SCREENSHOT_DIR, 'm4_0_3_tumkur_chennai_journey_map.png');
  await page.screenshot({ path: shot1Path, fullPage: false });
  console.log(`Saved Tumkur -> Chennai screenshot: ${shot1Path}`);
  await copyToArtifact(shot1Path, 'm4_0_3_tumkur_chennai_journey_map.png');

  // =========================================================================
  // SCENARIO 2: Bangalore -> Chennai
  // =========================================================================
  const blrUrl = 'http://localhost:5175/plan?origin=Bangalore&destination=Chennai&date=2026-11-16&passengers=1';
  console.log(`\nNavigating to Scenario 2: ${blrUrl}`);
  await page.goto(blrUrl, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // Scroll to show map and active journey
  await page.evaluate(() => window.scrollBy(0, 240));
  await page.waitForTimeout(1000);

  // Click on the green origin marker to display popup
  console.log('Clicking green origin marker at Bangalore...');
  const blrOriginMarker = page.locator('.custom-leaflet-marker').first();
  if (await blrOriginMarker.count() > 0) {
    await blrOriginMarker.click();
    await page.waitForTimeout(1000);
  }

  const shot2Path = path.join(SCREENSHOT_DIR, 'm4_0_3_bangalore_chennai_journey_map.png');
  await page.screenshot({ path: shot2Path, fullPage: false });
  console.log(`Saved Bangalore -> Chennai screenshot: ${shot2Path}`);
  await copyToArtifact(shot2Path, 'm4_0_3_bangalore_chennai_journey_map.png');

  await browser.close();
  console.log('\nAll M4.0.3 visual verification screenshots captured successfully!');
}

run().catch(err => {
  console.error('Capture script failed:', err);
  process.exit(1);
});
