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

const scenarios = [
  {
    name: 'Hubli -> Coimbatore Desktop',
    url: 'http://localhost:5176/plan?origin=Hubli&destination=Coimbatore&date=2026-11-21&passengers=1',
    viewport: { width: 1440, height: 950 },
    filename: 'm4_0_5_hubli_coimbatore_desktop.png',
    scroll: 150,
  },
  {
    name: 'Hubli -> Coimbatore Mobile',
    url: 'http://localhost:5176/plan?origin=Hubli&destination=Coimbatore&date=2026-11-21&passengers=1',
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    filename: 'm4_0_5_hubli_coimbatore_mobile.png',
    scroll: 200,
  },
  {
    name: 'Tumkur -> Goa Desktop',
    url: 'http://localhost:5176/plan?origin=Tumkur&destination=Goa&date=2026-11-21&passengers=1',
    viewport: { width: 1440, height: 950 },
    filename: 'm4_0_5_tumkur_goa.png',
    scroll: 150,
  },
  {
    name: 'Bengaluru -> Goa Desktop',
    url: 'http://localhost:5176/plan?origin=Bangalore&destination=Goa&date=2026-11-21&passengers=1',
    viewport: { width: 1440, height: 950 },
    filename: 'm4_0_5_bengaluru_goa.png',
    scroll: 150,
  },
  {
    name: 'Short Local Journey Desktop (Udayapalya -> Bangalore)',
    url: 'http://localhost:5176/plan?origin=Udayapalya&destination=Bangalore&date=2026-11-21&passengers=1',
    viewport: { width: 1440, height: 950 },
    filename: 'm4_0_5_short_local.png',
    scroll: 150,
  },
];

async function main() {
  console.log('Launching browser to capture all 5 verification scenarios...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });

  for (const sc of scenarios) {
    console.log(`\n=== Capturing Scenario: ${sc.name} ===`);
    const context = await browser.newContext({
      viewport: sc.viewport,
      deviceScaleFactor: sc.deviceScaleFactor || 1.5,
      isMobile: sc.isMobile || false,
      hasTouch: sc.hasTouch || false,
    });

    const page = await context.newPage();
    console.log(`Navigating to: ${sc.url}`);
    await page.goto(sc.url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    try {
      await page.waitForSelector('.custom-leaflet-marker', { timeout: 20000 });
      await page.waitForTimeout(2000);

      if (sc.scroll) {
        await page.evaluate((s) => window.scrollBy(0, s), sc.scroll);
        await page.waitForTimeout(1000);
      }

      // Check telemetry
      const telemetry = await page.evaluate(() => {
        const vp = document.querySelector('[data-testid="journey-map-viewport"]');
        const box = vp ? vp.getBoundingClientRect() : null;
        const markers = (window.__KOGNISYNC_RENDERED_MARKERS__ || []).map((m) => ({
          id: m.markerId,
          category: m.category,
          city: m.city,
          lat: m.lat,
          lng: m.lng,
          label: m.label,
        }));
        return {
          viewportHeight: box ? box.height : null,
          viewportWidth: box ? box.width : null,
          markers,
        };
      });

      console.log(`Viewport: ${telemetry.viewportWidth}x${telemetry.viewportHeight}px`);
      console.log(`Markers detected (${telemetry.markers.length}):`, JSON.stringify(telemetry.markers, null, 2));

      const outPath = path.join(SCREENSHOT_DIR, sc.filename);
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`Saved screenshot: ${outPath}`);
      await copyToArtifact(outPath, sc.filename);
    } catch (err) {
      console.error(`Failed to capture scenario ${sc.name}:`, err.message);
    } finally {
      await context.close();
    }
  }

  await browser.close();
  console.log('\nAll scenario captures finished.');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
