import { test, expect } from './fixtures';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

test('reopening subscriptions syncs unfollows without Vault approval and retains documents offline', async ({ page, request }) => {
  const dir = await mkdtemp(join(tmpdir(), 'edison-native-'));
  const backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-connection-server.py', dir, 'native'], {cwd: resolve('../..'), stdio: ['ignore','pipe','pipe']});
  try {
    let logs = ''; backend.stderr.on('data', data => logs += data);
    const port = await new Promise<number>((resolve, reject) => {
      let text = ''; const timer = setTimeout(() => reject(new Error(logs || 'startup timeout')), 15000);
      backend.stdout.on('data', data => {
        text += data; const line = text.split('\n').find(line => line.startsWith('{"port":'));
        if (line) {clearTimeout(timer); resolve(JSON.parse(line).port);}
      });
      backend.once('exit', () => { clearTimeout(timer); reject(new Error(logs)); });
    });
    const url = `http://127.0.0.1:${port}`;
    await expect.poll(async () => {try {return (await request.get(url+'/v1/health')).status();} catch {return 0;}}).toBe(200);
    await page.route('**/v1/youtube/capability', async route => {
      const response = await route.fetch({url:url+'/v1/youtube/capability',headers:{...route.request().headers(),'X-OpenWorker-Token':'youtube-connection-e2e'}});
      await route.fulfill({response});
    });
    await page.addInitScript(() => localStorage.setItem('openworker.lang','en'));
    await page.goto('/'); await page.getByTestId('nav-youtube').click();
    await page.getByRole('button',{name:'Subscriptions',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByText('Beta',{exact:true})).toBeVisible();
    await expect(dialog.getByRole('button',{name:'YouTube connected',exact:true})).toBeVisible();
    expect(await access(join(dir,'injected')).then(()=>true,()=>false)).toBe(false);
    await page.keyboard.press('Escape'); await writeFile(join(dir,'unfollowed'),'');
    await page.getByRole('button',{name:'Subscriptions',exact:true}).click();
    await expect(dialog.getByText('Beta',{exact:true})).toHaveCount(0);
    await expect(dialog.getByText('Alpha',{exact:true})).toBeVisible();
    expect(await access(join(dir,'injected')).then(()=>true,()=>false)).toBe(false);
    await page.keyboard.press('Escape'); await writeFile(join(dir,'offline'),'');
    await page.getByRole('button',{name:'Subscriptions',exact:true}).click();
    await expect(dialog.getByText('Alpha',{exact:true})).toBeVisible();
    const response=await request.post(url+'/v1/youtube/capability',{headers:{'X-OpenWorker-Token':'youtube-connection-e2e'},data:{capability:'library.list'}});
    expect((await response.json()).result.assets.some((asset: {video_id:string})=>asset.video_id==='saved')).toBe(true);
  } finally {
    if (backend.exitCode===null) {const stopped=new Promise<void>(resolve=>backend.once('exit',()=>resolve()));backend.kill('SIGTERM');await stopped;}
    await rm(dir,{recursive:true,force:true});
  }
});
