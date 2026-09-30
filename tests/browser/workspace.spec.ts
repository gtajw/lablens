import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdir, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

test('complete experiment, findings, residuals, export, reload, and deletion', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Analyze measurements' })).toBeEnabled();
  await expect(page.getByRole('heading', { name: 'Acceleration & time', exact: true })).toBeVisible();
  await mkdir('docs/submission/screenshots', { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'docs/submission/screenshots/01-workspace.png', fullPage: true });
  await page.getByRole('button', { name: 'Analyze measurements' }).click();
  await expect(page.getByRole('heading', { name: 'What the coefficients mean' })).toBeVisible();
  await expect(page.getByText('0.021 m/s⁴', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'The slope unit needs another look' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Zero intercept is an assumption' })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'docs/submission/screenshots/02-analysis.png', fullPage: true });
  await page.getByRole('button', { name: 'Residuals', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Residuals', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Read the guide', exact: true }).click();
  await expect(page.getByText('Deterministic guide · AI unavailable')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export result' }).click();
  const file = await download;
  await file.saveAs('docs/submission/example-export.json');
  const exported = await readFile('docs/submission/example-export.json', 'utf8');
  const exact = exported.match(/^\{"content":([\s\S]+),"sha256":"([0-9a-f]{64})"\}$/);
  expect(exact).not.toBeNull();
  expect(createHash('sha256').update(exact![1]).digest('hex')).toBe(exact![2]);
  expect(file.suggestedFilename()).toMatch(/^lablens-.*\.json$/);
  await page.reload();
  await expect(page.getByRole('button', { name: /Acceleration & time.*data version/ })).toBeEnabled();
  await page.getByRole('button', { name: /Acceleration & time.*data version/ }).click();
  await expect(page.locator('.notice-message').filter({ hasText: 'Experiment opened.' })).toBeVisible();
  await page.getByRole('button', { name: /History/ }).click();
  await page.getByRole('button', { name: /Linear · Square x/ }).click();
  await expect(page.locator('.notice-message').filter({ hasText: 'Viewing the original saved result.' })).toBeVisible();
  await page.getByLabel('Row 1 x', { exact: true }).fill('0.9');
  await expect(page.getByText('Settings have changed.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: /History/ }).click();
  await page.getByRole('button', { name: 'Delete experiment', exact: true }).click();
  await page.getByRole('button', { name: 'Delete permanently', exact: true }).click();
  await expect(page.locator('.notice-message').filter({ hasText: 'Experiment and all of its measurements' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('invalid transform rejects without fitted coefficients', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Analyze measurements' })).toBeEnabled();
  await page.getByLabel('Explore a sample').selectOption('reciprocal');
  await page.getByRole('button', { name: 'Analyze measurements' }).click();
  await expect(page.getByRole('heading', { name: 'Let’s check the setup first' })).toBeVisible();
  await expect(page.getByText('Check row 1.', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What the coefficients mean' })).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'docs/submission/screenshots/03-domain-check.png', fullPage: true });
});

test('CSV import, malformed input, and ordinary school lab fit', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Analyze measurements' })).toBeEnabled();
  await page.getByLabel('Explore a sample').selectOption('spring');
  await page.getByLabel('Choose CSV file').setInputFiles({ name: 'spring.csv', mimeType: 'text/csv', buffer: Buffer.from('Extension,Force\n1,0.51\n2,0.97\n3,1.52\n4,1.98\n5,2.53\n6,2.99\n') });
  await page.getByRole('button', { name: 'Import measurements', exact: true }).click();
  await expect(page.locator('.notice-message').filter({ hasText: 'CSV imported as an immutable data version.' })).toBeVisible();
  await page.getByRole('button', { name: 'Analyze measurements' }).click();
  await expect(page.getByRole('heading', { name: 'What the coefficients mean' })).toBeVisible();
  await page.getByLabel('Row 1 x', { exact: true }).fill('=1+1');
  await page.getByRole('button', { name: 'Analyze measurements' }).click();
  await expect(page.locator('.error-message')).toContainText('Row 1: enter a finite number');
});

test('keyboard access, desktop accessibility scan, and 200 percent layout', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Analyze measurements' })).toBeEnabled();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to workspace' })).toBeFocused();
  await page.keyboard.press('Enter');
  await page.getByRole('button', { name: 'Quick guide' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
  expect(scan.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await page.addStyleTag({ content: 'html { font-size: 200%; }' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('mobile analysis and no horizontal page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Analyze measurements' })).toBeEnabled();
  await page.getByRole('button', { name: 'Analyze measurements' }).click();
  await expect(page.getByRole('heading', { name: 'What the coefficients mean' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
  expect(scan.violations.map(v => ({ id: v.id, nodes: v.nodes.map(n => n.target) }))).toEqual([]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'docs/submission/screenshots/04-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 320, height: 700 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('gateway rejects cross-origin writes and does not expose internal headers', async ({ request }) => {
  const session = await request.get('/api/v1/session');
  expect(session.ok()).toBeTruthy();
  expect(session.headers()['x-new-session']).toBeUndefined();
  expect(session.headers()['set-cookie']).toContain('HttpOnly');
  expect(session.headers()['set-cookie']).toContain('SameSite=strict');
  const response = await request.post('/api/v1/projects', { data: { title: 'blocked' }, headers: { Origin: 'https://unrelated.example' } });
  expect(response.status()).toBe(403);
  expect((await response.json()).error.code).toBe('ORIGIN_INVALID');
});
