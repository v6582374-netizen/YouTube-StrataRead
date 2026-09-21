import { test, expect } from './fixtures';

test('YouTube follows the app language and keeps notifications outside the page', async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 850 });
  await page.addInitScript(() => localStorage.setItem('openworker.lang', 'en'));
  let discoveryError = '暂时无法刷新订阅，稍后自动重试。';
  let snapshots = 0;
  await page.route('**/v1/youtube/capability', async route => {
    const { capability } = route.request().postDataJSON();
    let result: unknown = {};
    if (capability === 'library.list') result = { assets: [] };
    if (capability === 'collection.preferences') result = { sources: [], excluded_channels: [] };
    if (capability === 'activity.list') result = { items: [], total: 0 };
    if (capability === 'activity.snapshot') {
      snapshots++;
      result = {
        queued: 0, acquiring: 0, generating: 0, ready: 0, failed: 0, unavailable: 0,
        drain_paused: false, model_ready: true, batch: { completed: 0, limit: 100 },
        discovery_error: discoveryError, runtime: { worker_alive: true, heartbeat_at: Date.now() / 1000 },
      };
    }
    if (capability === 'collection.refresh_updates') {
      await route.fulfill({ json: { ok: false, error: 'YouTube update feed could not be read' } });
      return;
    }
    await route.fulfill({ json: { ok: true, result } });
  });
  await page.goto('/');
  await page.getByTestId('nav-youtube').click();
  await page.getByRole('button', { name: 'Progress', exact: true }).click();
  const progress = page.getByRole('region', { name: 'Progress', exact: true });
  await expect(progress.getByRole('heading', { name: 'Waiting for subscription updates' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Progress', exact: true })).toHaveCSS('font-style', 'italic');
  expect(await page.locator('.yp-main').innerText()).not.toMatch(/[\u4e00-\u9fff]/);
  await page.screenshot({ path: '../../reports/ui-refinement/youtube-en.png' });
  await expect(page.locator('.notice-card')).toHaveText('Subscriptions could not refresh. Retrying later.');
  const before = await progress.boundingBox();
  await page.getByRole('button', { name: 'Check for updates', exact: true }).click();
  await expect(page.locator('.notice-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Dismiss notification' }).click();
  const previousSnapshots = snapshots;
  await expect.poll(() => snapshots).toBeGreaterThan(previousSnapshots);
  await expect(page.locator('.notice-card')).toHaveCount(0);
  expect(await progress.boundingBox()).toEqual(before);
  discoveryError = '';
  await page.getByTestId('account-row').click();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'General', exact: true }).click();
  await page.getByRole('radiogroup', { name: 'Language' }).getByRole('button', { name: '中文' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh');
  await page.getByTestId('nav-youtube').click();
  await page.getByRole('button', { name: '处理进度', exact: true }).click();
  await expect(page.getByRole('heading', { name: '等待新的订阅更新' })).toBeVisible();
  await expect(page.getByRole('button', { name: '立即检查更新' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Progress', exact: true })).toHaveCount(0);
  await expect(page.locator('.yp-main')).toHaveCSS('font-family', await page.locator('body').evaluate(element => getComputedStyle(element).fontFamily));
  await page.screenshot({ path: '../../reports/ui-refinement/youtube-zh.png' });
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.setViewportSize({ width: 800, height: 850 });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '../../reports/ui-refinement/youtube-zh-dark.png' });
});
