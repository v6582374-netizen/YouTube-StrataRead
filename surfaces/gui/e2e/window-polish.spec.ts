import { test, expect } from './fixtures';

test('English processing stages stay on one line without overlapping their status', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('openworker.lang', 'en'));
  await page.route('**/v1/youtube/capability', async route => {
    const { capability } = route.request().postDataJSON();
    let result: unknown = {};
    if (capability === 'library.list') result = { assets: [], total: 0 };
    if (capability === 'collection.preferences') result = { sources: [{ channel_id: 'one', title: 'Example' }], excluded_channels: [] };
    if (capability === 'activity.list') result = { items: [], total: 0 };
    if (capability === 'activity.snapshot') result = {
      queued: 1, generating: 1, acquiring: 0, ready: 0, failed: 0, unavailable: 0,
      drain_paused: false, model_ready: true, batch: { completed: 0, limit: 100 },
      runtime: { worker_alive: true, heartbeat_at: Date.now() / 1000 },
      current: [{ video_id: 'one', title: 'Example video', channel_title: 'Example', preparation_state: 'generating', preparation_stage: 'initial', observed_stages: ['checking', 'acquiring', 'initial'] }],
    };
    await route.fulfill({ json: { ok: true, result } });
  });
  await page.goto('/');
  await page.getByTestId('nav-youtube').click();
  await page.getByRole('button', { name: 'Progress', exact: true }).click();
  for (const width of [1360, 1100, 980, 800]) {
    await page.setViewportSize({ width, height: 850 });
    const rows = page.locator('.discovery-beacon-stage');
    await expect(rows).toHaveCount(6);
    for (const row of await rows.all()) {
      expect(await row.locator('strong').evaluate(element => {
        const range = document.createRange();
        range.selectNodeContents(element);
        const rects = [...range.getClientRects()];
        return rects.length === 1 && rects[0].right <= element.nextElementSibling!.getBoundingClientRect().left;
      }), `stage label at ${width}px`).toBe(true);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
