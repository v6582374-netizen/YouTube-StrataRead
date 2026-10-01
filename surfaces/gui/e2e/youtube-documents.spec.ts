import { test, expect } from './fixtures';

for (const width of [1440, 800]) {
  test(`document list and inspector at ${width}px`, async ({page}, testInfo) => {
    await page.setViewportSize({width, height: 1000});
    await page.addInitScript(() => {
      localStorage.setItem('openworker.lang', 'en');
      localStorage.setItem('openwork-theme', 'light');
    });
    let assets = [
      ['The architecture of everyday life', 'The School of Life'],
      ['Designing for a quieter world', 'Design Notes'],
      ['Paul Graham: How to do great work', 'Y Combinator'],
      ['The beauty of everyday things', 'Objects & Ideas'],
      ['Why cities need places to pause', 'The Urbanist'],
      ['A conversation about craft and time', 'Design Notes'],
      ['Learning to see: light, space and materials', 'Architecture Today'],
      ['The art of paying attention', 'The School of Life'],
    ].map(([title, channel_title], index) => ({
      video_id: `doc-${index}`, channel_id: `channel-${index}`, channel_title, title,
      url: 'https://www.youtube.com/watch?v=example', published_at: '2026-09-19',
      duration_seconds: 2538, preparation_state: 'ready', reading_state: 'inbox',
      manuscript_version: 1, failure_reason: null, manuscript_characters: 6200,
      excerpt: 'Good design begins with attention to the ordinary. A conversation about the spaces we inhabit, the objects we keep, and how thoughtful details shape our daily lives.',
      source_trace: {transcript_available: true, translation_available: true},
    }));
    const calls: string[] = [];
    await page.route('**/v1/youtube/capability', async route => {
      const {capability, arguments: args = {}} = route.request().postDataJSON();
      calls.push(capability);
      let result: unknown = {};
      if (capability === 'library.list') result = {assets};
      if (capability === 'collection.preferences') result = {sources: [], excluded_channels: []};
      if (capability === 'activity.snapshot') result = {queued: 0, acquiring: 0, generating: 0, ready: 8, failed: 0, unavailable: 0, drain_paused: true, model_ready: true, batch: {completed: 0, limit: 100}};
      if (capability === 'activity.list') result = {items: [], total: 0};
      if (capability === 'library.inspect') result = assets.find(a => a.video_id === args.video_id);
      if (capability === 'summary.ensure') {
        const summary = 'An independent overview of the whole document.';
        assets = assets.map(a => a.video_id === args.video_id ? {...a, summary} : a);
        result = {summary};
      }
      if (capability === 'library.set_reading_state') {
        assets = assets.map(a => a.video_id === args.video_id ? {...a, reading_state: args.reading_state} : a);
        result = assets.find(a => a.video_id === args.video_id);
      }
      if (capability === 'library.delete') assets = assets.filter(a => a.video_id !== args.video_id);
      await route.fulfill({json: {ok: true, result}});
    });
    await page.goto('/');
    await page.getByTestId('nav-youtube').click();
    await expect(page.locator('.yp-page-nav button').first()).toHaveText('Progress');
    await expect(page.locator('.yp-page-nav button').first()).toHaveAttribute('aria-current', 'page');
    await expect(page.locator('.yp-queue')).toHaveCSS('border-top-width', '0px');
    await page.getByRole('button', {name: 'Documents', exact: true}).click();
    const row = page.locator('.yp-row').first();
    await expect(row).toContainText('Good design begins');
    await row.click();
    const info = page.getByRole('complementary', {name: 'Document details'});
    await expect(info.getByRole('heading', {name: assets[0].title})).toBeVisible();
    await expect(info.locator('.yp-inspector-summary')).toContainText('An independent overview of the whole document.');
    await expect(info.locator('.yp-inspector-summary')).not.toContainText('Good design begins with attention');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(row).toHaveAttribute('aria-pressed', 'true');
    await info.getByRole('button', {name: 'Open with default app', exact: true}).click();
    expect(calls).toContain('documents.open');
    await info.getByRole('button', {name: 'Mark read', exact: true}).click();
    await expect(info.getByRole('button', {name: 'Mark unread', exact: true})).toBeVisible();
    await expect(info.locator('.yp-inspector-summary')).toContainText('An independent overview of the whole document.');
    await page.screenshot({path: testInfo.outputPath(`documents-light-${width}.png`)});
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
    await page.screenshot({path: testInfo.outputPath(`documents-dark-${width}.png`)});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await info.getByRole('button', {name: 'Delete document', exact: true}).click();
    await info.getByRole('button', {name: 'Confirm deletion', exact: true}).click();
    await expect(page.locator('.yp-row')).toHaveCount(7);
    await expect(page.locator('.yp-row').first()).toBeVisible();
  });
}
