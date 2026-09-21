import { test, expect } from './fixtures';
import { spawn, type ChildProcess } from 'node:child_process';
import { mkdtemp, rm, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('Shorts admission, deferred classification and retained manuscripts through the real host', async ({ page, request }) => {
  test.setTimeout(90000);
  const dir = await mkdtemp(join(tmpdir(), 'edison-shorts-'));
  const headers = { 'X-OpenWorker-Token': 'youtube-progress-e2e' };
  let backend: ChildProcess | undefined;
  let url = '';
  const start = async () => {
    backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-progress-server.py', dir, 'shorts'],
      { cwd: resolve('../..'), stdio: ['ignore', 'pipe', 'pipe'] });
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
    const response = await request.post(url + '/v1/youtube/capability', { headers, data: { capability, arguments: args } });
    const payload = await response.json();
    expect(payload.ok, payload.error).toBe(true);
    return payload.result;
  };
  try {
    await writeFile(join(dir, 'captions-release'), 'go');
    await writeFile(join(dir, 'model-release'), 'go');
    await start();
    await page.route('**/v1/youtube/capability', async route => {
      try {
        const response = await route.fetch({ url: url + '/v1/youtube/capability', headers: { ...route.request().headers(), ...headers } });
        await route.fulfill({ response });
      } catch {
        // The real host is deliberately stopped and restarted below.
        await route.abort();
      }
    });
    await page.addInitScript(() => localStorage.setItem('openworker.lang', 'zh'));
    await page.goto('/');
    await page.getByTestId('nav-youtube').click();
    await page.getByRole('button', { name: '处理进度', exact: true }).click();
    const progress = page.getByRole('region', { name: '处理进度', exact: true });
    await progress.getByRole('button', { name: '恢复自动更新', exact: true }).click();
    await expect.poll(async () => (await call('activity.snapshot')).ready, { timeout: 15000 }).toBe(2);
    await expect.poll(async () => (await call('activity.snapshot')).awaiting_classification, { timeout: 15000 }).toBe(1);
    expect((await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')).toEqual(['normal00001']);
    const activity = await call('activity.snapshot');
    expect(activity.filtered).toBe(1);
    expect(activity.awaiting_classification).toBe(1);
    await progress.getByRole('button', { name: /^待确认类型/ }).click();
    await expect(progress.getByRole('region', { name: '处理队列' }).getByText('暂时无法确认的视频', { exact: true })).toBeVisible();
    await expect(progress.getByText('稍后自动重试；确认前不会获取字幕或生成文稿。')).toBeVisible();
    await page.getByRole('button', { name: '阅读文档', exact: true }).click();
    await expect(page.getByText('两分钟横屏讲解', { exact: true })).toBeVisible();
    await expect(page.getByText('已有的 Shorts 文稿', { exact: true })).toBeVisible();
    await expect(page.getByText('平台 Shorts', { exact: true })).toHaveCount(0);
    await stop();
    await start();
    await call('collection.refresh_updates');
    expect((await call('activity.snapshot')).filtered).toBe(1);
    expect((await call('activity.snapshot')).awaiting_classification).toBe(1);
    expect((await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')).toEqual(['normal00001']);
  } finally {
    await stop();
    await rm(dir, { recursive: true, force: true });
  }
});
