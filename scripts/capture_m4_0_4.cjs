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
  console.log('Starting Playwright capture for M4.0.4.1 (Adversarial Review Remediation & Fallback Sync)...');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
    deviceScaleFactor: 1.5,
  });

  // =========================================================================
  // SCENARIO 1: Pure Client Fallback Simulation — Tumkur -> Goa
  // =========================================================================
  {
    console.log('\n--- Capturing Scenario 1: Pure Client Fallback Simulation (Tumkur -> Goa) ---');
    const page = await context.newPage();

    // Isolate pure client fallback: fail both journey search AND backend map enrichment
    await page.route('**/api/v1/journeys/search', (route) => {
      console.log('Intercepted /api/v1/journeys/search -> aborting (pure client fallback)');
      route.abort();
    });
    await page.route('**/api/v1/maps/enrich', (route) => {
      console.log('Intercepted /api/v1/maps/enrich -> aborting (pure client fallback)');
      route.abort();
    });
    await page.route('**/api/v1/maps/health', (route) => {
      console.log('Intercepted /api/v1/maps/health -> aborting (pure client fallback)');
      route.abort();
    });

    const url = 'http://127.0.0.1:5175/plan?origin=Tumkur&destination=Goa&date=2026-11-21&passengers=1&budgetMax=3000';
    console.log(`Navigating to: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    // Wait for journey results and Leaflet markers
    console.log('Waiting for journey map to render...');
    await page.waitForSelector('.custom-leaflet-marker', { timeout: 20000 });
    await page.waitForTimeout(2000);

    // Scroll to reveal the map and toolbar clearly
    await page.evaluate(() => window.scrollBy(0, 240));
    await page.waitForTimeout(1000);

    // Click on the green Origin marker at Tumkur to show coordinates popup
    console.log('Clicking Origin marker at Tumkur...');
    const originMarker = page.locator('.custom-leaflet-marker').first();
    if (await originMarker.count() > 0) {
      await originMarker.click();
      await page.waitForTimeout(1000);
    }

    const shot1Path = path.join(SCREENSHOT_DIR, 'm4_0_4_client_fallback_tumkur_goa.png');
    await page.screenshot({ path: shot1Path, fullPage: false });
    console.log(`Saved screenshot 1: ${shot1Path}`);
    await copyToArtifact(shot1Path, 'm4_0_4_client_fallback_tumkur_goa.png');
    await page.close();
  }

  // =========================================================================
  // SCENARIO 2: Backend Orchestrated (Valhalla OSM Live) — Tumkur -> Goa
  // =========================================================================
  {
    console.log('\n--- Capturing Scenario 2: Backend Orchestrated Valhalla (Tumkur -> Goa) ---');
    const page = await context.newPage();

    // Do NOT intercept: let live backend on port 8000 orchestrate and enrich
    const url = 'http://127.0.0.1:5175/plan?origin=Tumkur&destination=Goa&date=2026-11-21&passengers=1&budgetMax=3000';
    console.log(`Navigating to: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    console.log('Waiting for backend journey map to render...');
    await page.waitForSelector('.custom-leaflet-marker', { timeout: 30000 });
    await page.waitForTimeout(2500);

    // Scroll to reveal map
    await page.evaluate(() => window.scrollBy(0, 240));
    await page.waitForTimeout(1000);

    // Click on the green Origin marker at Tumkur
    console.log('Clicking Origin marker at Tumkur...');
    const originMarker = page.locator('.custom-leaflet-marker').first();
    if (await originMarker.count() > 0) {
      await originMarker.click();
      await page.waitForTimeout(1000);
    }

    const shot2Path = path.join(SCREENSHOT_DIR, 'm4_0_4_backend_tumkur_goa.png');
    await page.screenshot({ path: shot2Path, fullPage: false });
    console.log(`Saved screenshot 2: ${shot2Path}`);
    await copyToArtifact(shot2Path, 'm4_0_4_backend_tumkur_goa.png');
    await page.close();
  }

  // =========================================================================
  // SCENARIO 3: Client Fallback Simulation — Bengaluru -> Goa Baseline
  // =========================================================================
  {
    console.log('\n--- Capturing Scenario 3: Client Fallback Simulation (Bengaluru -> Goa) ---');
    const page = await context.newPage();

    // Pure client fallback
    await page.route('**/api/v1/journeys/search', (route) => route.abort());
    await page.route('**/api/v1/maps/enrich', (route) => route.abort());
    await page.route('**/api/v1/maps/health', (route) => route.abort());

    const url = 'http://127.0.0.1:5175/plan?origin=Bengaluru&destination=Goa&date=2026-11-21&passengers=1&budgetMax=3000';
    console.log(`Navigating to: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    console.log('Waiting for journey map to render...');
    await page.waitForSelector('.custom-leaflet-marker', { timeout: 20000 });
    await page.waitForTimeout(2000);

    // Scroll to reveal map
    await page.evaluate(() => window.scrollBy(0, 240));
    await page.waitForTimeout(1000);

    // Click on the green Origin marker at Bengaluru
    console.log('Clicking Origin marker at Bengaluru...');
    const originMarker = page.locator('.custom-leaflet-marker').first();
    if (await originMarker.count() > 0) {
      await originMarker.click();
      await page.waitForTimeout(1000);
    }

    const shot3Path = path.join(SCREENSHOT_DIR, 'm4_0_4_client_fallback_bangalore_goa.png');
    await page.screenshot({ path: shot3Path, fullPage: false });
    console.log(`Saved screenshot 3: ${shot3Path}`);
    await copyToArtifact(shot3Path, 'm4_0_4_client_fallback_bangalore_goa.png');
    await page.close();
  }

  // =========================================================================
  // SCENARIO 4: Invalid Geometry Mode — Spatial Geometry Unavailable (No Null Island)
  // =========================================================================
  {
    console.log('\n--- Capturing Scenario 4: Spatial Geometry Unavailable Overlay (No Null Island) ---');
    const page = await context.newPage();

    // Mock search response with missing spatial coordinates
    await page.route('**/api/v1/journeys/search', async (route) => {
      const mockJourneyWithoutCoords = {
        journeys: [
          {
            id: 'jny-no-coords',
            title: 'Abstract Corridor Connection',
            origin: {
              id: 'loc-orig-unloc',
              name: 'Remote Research Outpost',
              city: 'Deep Reserve',
              type: 'address',
              coordinates: { lat: NaN, lng: NaN },
            },
            destination: {
              id: 'loc-dest-unloc',
              name: 'Continental Logistics Hub',
              city: 'Inland Depot',
              type: 'address',
              coordinates: { lat: NaN, lng: NaN },
            },
            departureTime: '2026-11-21T08:00:00Z',
            arrivalTime: '2026-11-21T14:00:00Z',
            totalDurationMinutes: 360,
            totalPrice: 450,
            currency: 'INR',
            totalTransfers: 0,
            modes: ['train'],
            segments: [
              {
                segmentId: 'seg-no-coords-1',
                mode: 'train',
                provider: 'Regional Express',
                origin: {
                  id: 'loc-orig-unloc',
                  name: 'Remote Research Outpost',
                  city: 'Deep Reserve',
                  type: 'address',
                  coordinates: { lat: NaN, lng: NaN },
                },
                destination: {
                  id: 'loc-dest-unloc',
                  name: 'Continental Logistics Hub',
                  city: 'Inland Depot',
                  type: 'address',
                  coordinates: { lat: NaN, lng: NaN },
                },
                departureTime: '2026-11-21T08:00:00Z',
                arrivalTime: '2026-11-21T14:00:00Z',
                durationMinutes: 360,
                distanceKm: 250,
                price: 450,
                currency: 'INR',
                availability: { status: 'available', remainingUnits: 10, isRealInventory: false },
              },
            ],
            carbonKg: 15,
            comfortScore: 7,
            recommendationCategory: 'best_value',
            aiExplanation: { summary: 'Abstract corridor without valid spatial coordinates', tradeOffs: [], rankReason: 'Test Abstract Corridor', score: 80 },
          },
        ],
        total: 1,
        source: 'backend_orchestrator',
      };

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockJourneyWithoutCoords),
      });
    });

    await page.route('**/api/v1/maps/enrich', (route) => route.abort());
    await page.route('**/api/v1/maps/health', (route) => route.abort());

    const url = 'http://127.0.0.1:5175/plan?origin=DeepReserve&destination=InlandDepot&date=2026-11-21&passengers=1';
    console.log(`Navigating to: ${url}`);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

    console.log('Waiting for spatial-geometry-unavailable overlay...');
    await page.waitForSelector('[data-testid="spatial-geometry-unavailable"]', { timeout: 20000 });
    await page.waitForTimeout(2000);

    // Scroll to reveal the map container
    await page.evaluate(() => window.scrollBy(0, 240));
    await page.waitForTimeout(1000);

    const shot4Path = path.join(SCREENSHOT_DIR, 'm4_0_4_invalid_geometry_no_null_island.png');
    await page.screenshot({ path: shot4Path, fullPage: false });
    console.log(`Saved screenshot 4: ${shot4Path}`);
    await copyToArtifact(shot4Path, 'm4_0_4_invalid_geometry_no_null_island.png');
    await page.close();
  }

  await browser.close();
  console.log('\nAll 4 required M4.0.4.1 screenshots captured and copied to artifact directory!');
}

run().catch((err) => {
  console.error('Playwright capture script failed:', err);
  process.exit(1);
});
