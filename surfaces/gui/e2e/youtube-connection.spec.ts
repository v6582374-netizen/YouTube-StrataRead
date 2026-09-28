import { test, expect } from './fixtures';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('migrates once into Keychain, then connects without depending on Vault', async ({ page, request }) => {
  const dir = await mkdtemp(join(tmpdir(), 'edison-connection-'));
  const backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-connection-server.py', dir], { cwd: resolve('../..'), stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    let logs = '';
    backend.stderr.on('data', data => logs += data);
    const port = await new Promise<number>((resolve, reject) => {
      let out = '';
      const timer = setTimeout(() => reject(new Error(logs || 'startup timeout')), 15000);
      backend.stdout.on('data', data => {
        out += data;
        const line = out.split('\n').find(line => line.startsWith('{"port":'));
        if (line) { clearTimeout(timer); resolve(JSON.parse(line).port); }
      });
      backend.once('exit', () => { clearTimeout(timer); reject(new Error(logs)); });
    });
    const url = `http://127.0.0.1:${port}`;
    await expect.poll(async () => { try { return (await request.get(url + '/v1/health')).status(); } catch { return 0; } }).toBe(200);
    await page.route('**/v1/youtube/capability', async route => {
      const response = await route.fetch({ url: url + '/v1/youtube/capability', headers: { ...route.request().headers(), 'X-OpenWorker-Token': 'youtube-connection-e2e' } });
      await route.fulfill({ response });
    });
    await page.addInitScript(() => localStorage.setItem('openworker.lang', 'en'));
    await page.goto('/');
    await page.getByTestId('nav-youtube').click();
    await page.getByRole('button', { name: 'Connect YouTube', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('button', { name: 'Migrate existing connection', exact: true })).toBeVisible();
    await expect(dialog.getByLabel('Client ID')).toBeHidden();
    expect(await access(join(dir, 'injected')).then(() => true, () => false)).toBe(false);
    await dialog.getByRole('button', { name: 'Migrate existing connection', exact: true }).click();
    await expect(dialog.getByRole('button', { name: /Authorize/ })).toBeVisible();
    await expect(dialog.getByRole('button', { name: /Disconnect/ })).toHaveCount(0);
    expect(await access(join(dir, 'injected')).then(() => true, () => false)).toBe(true);
    await rm(join(dir, 'injected'));
    await rm(join(dir, 'av')); // Removing Vault must not affect normal application use.
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Connect YouTube', exact: true }).click();
    await expect(dialog.getByRole('button', { name: /Authorize/ })).toBeVisible();
    await expect(dialog.getByLabel('Client ID')).toHaveCount(0);
    expect(await access(join(dir, 'injected')).then(() => true, () => false)).toBe(false);
  } finally {
    if (backend.exitCode === null) {
      const stopped = new Promise<void>(resolve => backend.once('exit', () => resolve()));
      backend.kill('SIGTERM'); await stopped;
    }
    await rm(dir, { recursive: true, force: true });
  }
});
