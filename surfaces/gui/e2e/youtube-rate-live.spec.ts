import { test, expect } from './fixtures';
import { spawn, execFileSync, type ChildProcess } from 'node:child_process';
import { mkdtemp, rm, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('429 pauses every video and remains in force after restart', async ({ page, request }) => {
  test.setTimeout(90000);
  const dir = await mkdtemp(join(tmpdir(), 'edison-rate-'));
  const headers = { 'X-OpenWorker-Token': 'youtube-progress-e2e' };
  let backend: ChildProcess | undefined;
  let url = '';
  const start = async () => {
    backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-progress-server.py', dir, 'rate'],
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
    await expect.poll(async () => {
      try { return (await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')[0]; }
      catch { return ''; }
    }).toBe('one');
    // Observe several real worker iterations: a cooldown must protect other videos too.
    await page.waitForTimeout(3500);
    expect((await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')).toEqual(['one']);
    const activity = await call('activity.snapshot');
    expect(activity.rate_limited).toBe(1);
    expect(activity.queued).toBe(2);
    expect(activity.youtube_requests.cooldown_until).toBeGreaterThan(Date.now() / 1000);
    await expect(progress.getByRole('heading', { name: 'YouTube 冷却中', exact: true })).toBeVisible();
    await progress.getByRole('button', { name: /^限流等待/ }).click();
    await expect(progress.getByRole('region', { name: '处理队列' }).getByText('建筑与时间', { exact: true })).toBeVisible();
    await stop();
    await start();
    await call('activity.resume');
    await call('activity.retry_all_failed');
    await page.waitForTimeout(2500);
    expect((await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')).toEqual(['one']);
    const after = await call('activity.snapshot');
    expect(after.youtube_requests.cooldown_until).toBe(activity.youtube_requests.cooldown_until);
    expect(after.rate_limited).toBe(1);
    // Simulate elapsed time only in this isolated test workspace, then let the real worker resume.
    await stop();
    await writeFile(join(dir, 'rate-release'), 'go');
    execFileSync(resolve('../../.venv/bin/python'), ['-c', `
import json, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    state=json.loads(db.execute("SELECT value FROM workspace_meta WHERE key='youtube_request_policy'").fetchone()[0])
    state['cooldown_until']=0
    db.execute("UPDATE workspace_meta SET value=? WHERE key='youtube_request_policy'", (json.dumps(state),))
`, join(dir, 'youtube', 'workspace.sqlite3')]);
    await start();
    await expect.poll(async () => (await call('activity.snapshot')).ready, {timeout: 15000}).toBe(3);
    expect((await readFile(join(dir, 'caption-calls'), 'utf8')).trim().split('\n')).toEqual(['one', 'one', 'two', 'three']);
    expect((await call('activity.snapshot')).rate_limited).toBe(0);
  } finally {
    await stop();
    await rm(dir, { recursive: true, force: true });
  }
});
