import { test, expect } from './fixtures';
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

for (const width of [800, 1440]) {
  test(`real progress, cancellation and recovery at ${width}px`, async ({page, request}, testInfo) => {
    test.setTimeout(120000);
    const dir = await mkdtemp(join(tmpdir(), 'edison-progress-'));
    let backend: ChildProcess | undefined;
    let url = '';
    const headers = {'X-OpenWorker-Token': 'youtube-progress-e2e'};
    const start = async () => {
      backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-progress-server.py', dir], {cwd: resolve('../..'), stdio: ['ignore', 'pipe', 'pipe']});
      let logs = '';
      backend.stderr!.on('data', data => logs += data);
      const port = await new Promise<number>((resolve, reject) => {
        let out = '';
        const timer = setTimeout(() => reject(new Error(logs || 'startup timeout')), 30000);
        backend!.stdout!.on('data', data => {
          out += data;
          const line = out.split('\n').find(line => line.startsWith('{"port":'));
          if (line) { clearTimeout(timer); resolve(JSON.parse(line).port); }
        });
        backend!.once('exit', code => { clearTimeout(timer); reject(new Error(`backend ${code}: ${logs}`)); });
      });
      url = `http://127.0.0.1:${port}`;
      await expect.poll(async () => { try { return (await request.get(url + '/v1/health')).status(); } catch { return 0; } }).toBe(200);
    };
    const stop = async () => {
      if (!backend || backend.exitCode !== null) return;
      const stopped = new Promise<void>(resolve => backend!.once('exit', () => resolve()));
      backend.kill('SIGTERM');
      await stopped;
    };
    const call = async (capability: string, args = {}) => {
      const response = await request.post(url + '/v1/youtube/capability', {headers, data: {capability, arguments: args}});
      expect(response.ok()).toBeTruthy();
      const payload = await response.json();
      expect(payload.ok, payload.error).toBe(true);
      return payload.result;
    };
    let offline = false;
    try {
      await start();
      expect((await request.post(url + '/v1/youtube/capability', {data: {capability: 'activity.snapshot'}})).status()).toBe(401);
      await page.route('**/v1/youtube/capability', async route => {
        if (offline) return route.abort();
        try {
          const response = await route.fetch({url: url + '/v1/youtube/capability', headers: {...route.request().headers(), ...headers}});
          await route.fulfill({response});
        } catch { await route.abort(); }
      });
      await page.setViewportSize({width, height: 950});
      await page.addInitScript(dark => {
        localStorage.setItem('openworker.lang', 'zh');
        localStorage.setItem('openwork-theme', dark ? 'dark' : 'light');
      }, width === 1440);
      await page.goto('/');
      await page.getByTestId('nav-youtube').click();
      await page.getByRole('button', {name: '处理进度', exact: true}).click();
      const progress = page.getByRole('region', {name: '处理进度', exact: true});
      const queue = progress.getByRole('region', {name: '处理队列'});
      await expect(progress.getByText('后台在线', {exact: true})).toBeVisible();
      await expect(progress.getByRole('heading', {name: '更新已暂停'})).toBeVisible();
      const firstVideo = queue.locator('li').filter({hasText: '建筑与时间'});
      await expect(firstVideo).toContainText('发布于 2026-09-19');
      await expect(firstVideo).toContainText('时长未知');
      await queue.locator('li').filter({hasText: '建筑与时间'}).getByRole('button', {name: '取消处理', exact: true}).click();
      await expect(queue.locator('li')).toHaveCount(2);
      await queue.getByRole('checkbox', {name: '选择本页全部视频'}).check();
      await queue.getByRole('button', {name: '取消处理所选（2）'}).click();
      await expect(queue.getByText('没有等待处理的视频。')).toBeVisible();
      await progress.getByRole('button', {name: /^已取消/}).click();
      await expect(queue.locator('li')).toHaveCount(3);
      await progress.getByRole('button', {name: '立即检查更新'}).click();
      expect((await call('activity.snapshot')).cancelled).toBe(3);
      await stop();
      await start();
      expect((await call('activity.snapshot')).cancelled).toBe(3);
      await queue.locator('li').filter({hasText: '建筑与时间'}).getByRole('button', {name: '恢复处理', exact: true}).click();
      await expect(queue.locator('li')).toHaveCount(2);
      await progress.getByRole('button', {name: /^待处理/}).click();
      await expect(queue.locator('li')).toHaveCount(1);
      await progress.getByRole('button', {name: '恢复自动更新', exact: true}).click();
      await expect(progress.getByRole('heading', {name: '获取字幕', exact: true})).toBeVisible({timeout: 15000});
      const raced = await call('activity.cancel', {video_ids: ['one']});
      expect(raced.changed).toEqual([]);
      expect(raced.skipped[0].state).toBe('acquiring');
      await progress.getByRole('button', {name: '完成当前文档后暂停'}).click();
      await writeFile(join(dir, 'captions-release'), 'go');
      await expect(progress.getByRole('heading', {name: '初译', exact: true})).toBeVisible({timeout: 15000});
      const consoleOutput = progress.getByRole('region', {name: '原始控制台'});
      await expect(consoleOutput).toBeVisible();
      await expect(consoleOutput.locator('code')).toContainText('request started; model=fixture-model');
      await expect(consoleOutput.locator('code')).toContainText('waiting for response');
      await expect(consoleOutput.locator('code')).not.toContainText('response received');
      await expect(progress.locator('.discovery-runtime-event')).toHaveCount(0);
      await expect(progress.locator('.discovery-beacon-orb span')).toHaveCSS('animation-name', 'discovery-beacon-breathe');
      await page.getByRole("main", {name: "YouTube 资料库"}).evaluate(element => element.scrollTop = 0);
      await page.screenshot({path: testInfo.outputPath(`progress-${width}.png`), fullPage: true});
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.emulateMedia({reducedMotion: 'reduce'});
      await expect(progress.locator('.discovery-beacon-orb span')).toHaveCSS('animation-name', 'none');
      await page.emulateMedia({reducedMotion: 'no-preference'});
      offline = true;
      await expect(progress.getByRole('status').filter({hasText: '连接中断 · 正在重连'})).toBeVisible({timeout: 15000});
      await expect(progress.locator('.discovery-beacon-orb span')).toHaveCSS('animation-name', 'none');
      offline = false;
      await expect(progress.getByText('后台在线', {exact: true})).toBeVisible({timeout: 15000});
      await writeFile(join(dir, 'model-release'), 'go');
      await expect.poll(async () => (await call('activity.snapshot')).ready, {timeout: 15000}).toBe(1);
      await expect(progress.getByRole('heading', {name: '更新已暂停'})).toBeVisible({timeout: 10000});
      await expect(consoleOutput.locator('code')).toContainText('response received');
      await expect(consoleOutput.locator('code')).toContainText('validated and checkpoint saved');
      await consoleOutput.screenshot({path: testInfo.outputPath(`console-${width}.png`)});
      await consoleOutput.getByRole('button', {name: '跟随输出'}).click();
      await expect(consoleOutput.getByRole('button', {name: '跟随输出'})).toHaveAttribute('aria-pressed', 'false');
      await page.getByRole('button', {name: '事件时间线', exact: true}).click();
      await expect(page.getByRole('button', {name: '事件时间线', exact: true})).toHaveAttribute('aria-current', 'page');
      const timeline = page.getByRole('region', {name: '事件时间线', exact: true});
      await expect(timeline.locator('.discovery-runtime-event').first()).toContainText('已生成');
      await expect(page.getByRole('region', {name: '原始控制台'})).toHaveCount(0);
      await page.getByRole('button', {name: '阅读文档', exact: true}).click();
      await expect(page.getByText('建筑与时间', {exact: true})).toBeVisible({timeout: 15000});
      for (const layout of ['时间流', '文档库', '频道索引']) {
        await page.getByRole('button', {name: layout, exact: true}).click();
        const document = page.getByRole('button', {name: /建筑与时间/});
        await expect(document).toContainText('发布于 2026-09-19');
        await expect(document.getByText('视频 42 分 18 秒', {exact: true})).toBeVisible();
        await expect(document.getByText(/预计阅读 \d+ 分钟/)).toBeVisible();
      }
      await page.getByRole('button', {name: /建筑与时间/}).click();
      await expect(page.getByRole('dialog').getByText('视频 42 分 18 秒', {exact: true})).toBeVisible();
      expect((await call('activity.snapshot')).cancelled).toBe(2);
    } finally {
      await writeFile(join(dir, 'captions-release'), 'go');
      await writeFile(join(dir, 'model-release'), 'go');
      await stop();
      await rm(dir, {recursive: true, force: true});
    }
  });
}
