// One-off script (Phase 10 verification) - drives the real running app
// with Playwright and saves screenshots for the completion report. Not
// part of the application; not committed to the repo build output.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const OUT_DIR = 'C:/GenAI/TalentFlowAI/frontend/screenshots';
mkdirSync(OUT_DIR, { recursive: true });

const BASE = 'http://localhost:5173';

const pages = [
  { path: '/', name: 'dashboard' },
  { path: '/requisitions', name: 'requisitions-list' },
  { path: '/screening', name: 'screening-list' },
  { path: '/interviews', name: 'interviews' },
  { path: '/offers', name: 'offers' },
];

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 834, height: 1112 },
];

const browser = await chromium.launch();

for (const viewport of viewports) {
  const context = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
  const page = await context.newPage();
  for (const p of pages) {
    await page.goto(`${BASE}${p.path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${OUT_DIR}/${p.name}-${viewport.name}.png`, fullPage: viewport.name === 'desktop' ? false : true });
    console.log(`captured ${p.name}-${viewport.name}`);
  }
  await context.close();
}

// Drill into one requisition detail and one screening detail for evidence
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
await page.goto(`${BASE}/requisitions`, { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
const firstRow = page.locator('table tbody tr').first();
if (await firstRow.count() > 0) {
  await firstRow.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT_DIR}/requisition-detail-desktop.png` });
  console.log('captured requisition-detail-desktop');
}

await page.goto(`${BASE}/screening`, { waitUntil: 'networkidle' });
await page.waitForTimeout(400);
const firstScreeningRow = page.locator('table tbody tr').first();
if (await firstScreeningRow.count() > 0) {
  await firstScreeningRow.click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT_DIR}/screening-detail-desktop.png` });
  console.log('captured screening-detail-desktop');
}
await context.close();

await browser.close();
console.log('done');
