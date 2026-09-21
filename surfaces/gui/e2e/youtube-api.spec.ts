import {test, expect} from './fixtures';
import {spawn} from 'node:child_process';
import {mkdtemp, writeFile, readFile, rm, rename, access} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {tmpdir} from 'node:os';
import type {Page, APIRequestContext} from '@playwright/test';

type Scenario = {channels?: string[]; videos?: {id: string; published: number; added?: number; channel?: string; kind?: string; claimed_publication?: number}[];
  global_failure?: string; failure_endpoint?: string; auth_failure?: boolean; channel_failure?: string; caption_cooldown?: boolean; more_pages?: boolean};
async function harness(page: Page, request: APIRequestContext, scenario: Scenario, releaseModel = true) {
  const root = await mkdtemp(join(tmpdir(), 'edison-api-'));
  const now = Math.floor(Date.now()/1000);
  const write = async (name: string, value='go') => {await writeFile(join(root,name+'.tmp'),value);await rename(join(root,name+'.tmp'),join(root,name));};
  const exists = async (name: string) => {try{await access(join(root,name));return true;}catch{return false;}};
  await write('clock',String(now));
  await write('scenario.json',JSON.stringify(scenario));
  if(releaseModel) await write('model-release');
  const backend = spawn(resolve('../../.venv/bin/python'), ['surfaces/gui/e2e/youtube-api-server.py',root],{cwd:resolve('../..'),stdio:['ignore','pipe','pipe']});
  let logs=''; backend.stderr!.on('data',chunk=>logs+=chunk);
  const port=await new Promise<number>((done,reject)=>{
    let output='';const timer=setTimeout(()=>reject(new Error(logs)),30000);
    backend.stdout!.on('data',chunk=>{output+=chunk;const line=output.split('\n').find(line=>line.startsWith('{"port":'));if(line){clearTimeout(timer);done(JSON.parse(line).port);}});
    backend.once('exit',code=>{clearTimeout(timer);reject(new Error(`${code}: ${logs}`));});
  });
  const url=`http://127.0.0.1:${port}`;
  await expect.poll(async()=>{try{return (await request.get(url+'/v1/health')).status();}catch{return 0;}}).toBe(200);
  const call=async(capability: string,args={})=>{
    const response=await request.post(url+'/v1/youtube/capability',{headers:{'X-OpenWorker-Token':'youtube-api-e2e'},data:{capability,arguments:args}});
    const payload=await response.json();expect(payload.ok,payload.error).toBe(true);return payload.result;
  };
  await page.route('**/v1/youtube/capability',async route=>{
    try {const response=await route.fetch({url:url+'/v1/youtube/capability',headers:{...route.request().headers(),'X-OpenWorker-Token':'youtube-api-e2e'}});await route.fulfill({response});}
    catch {await route.abort();}
  });
  await page.addInitScript(()=>localStorage.setItem('openworker.lang','zh'));
  await page.goto('/');await page.getByTestId('nav-youtube').click();
  const authorize=async()=>{
    await page.getByRole('button',{name:'订阅频道',exact:true}).click();
    await page.getByRole('dialog',{name:'订阅频道',exact:true}).getByRole('button',{name:'连接 YouTube',exact:true}).click();
    await page.getByRole('button',{name:'在浏览器中授权并导入订阅',exact:true}).click();
    await expect(page.getByText(/YouTube 已连接，已导入 \d+ 个订阅。/)).toBeVisible();
    await page.getByRole('button',{name:'关闭',exact:true}).click();
  };
  await authorize();
  await page.getByRole('button',{name:'处理进度',exact:true}).click();
  const toggle=async(on: boolean)=>{
    await page.getByRole('button',{name:on?'恢复自动更新':'完成当前文档后暂停',exact:true}).click();
    await expect(page.getByRole('button',{name:on?'完成当前文档后暂停':'恢复自动更新',exact:true})).toBeEnabled();
  };
  return {root,now,write,exists,call,toggle,authorize,
    scenario:(value: Scenario)=>write('scenario.json',JSON.stringify(value)),
    clock:(value: number)=>write('clock',String(value)),
    requests:async()=>{try{return (await readFile(join(root,'api-requests.jsonl'),'utf8')).trim().split('\n').map(line=>JSON.parse(line));}catch{return []; }},
    close:async()=>{if(backend.exitCode===null){const exited=new Promise<void>(done=>backend.once('exit',()=>done()));backend.kill('SIGKILL');await exited;}await rm(root,{recursive:true,force:true});},
  };
}

test('official uploads discovery prepares a new video using its public time',async({page,request})=>{
  test.setTimeout(60000);
  const now=Math.floor(Date.now()/1000);
  const app=await harness(page,request,{videos:[{id:'fresh-video',published:now-60,added:now-100*3600}]});
  try{
    await app.toggle(true);
    await expect.poll(async()=>(await app.call('activity.snapshot')).ready,{timeout:15000}).toBe(1);
    expect((await app.requests()).map(r=>r.endpoint)).toEqual(expect.arrayContaining(['subscriptions','channels','playlistItems','videos']));
    await page.getByRole('button',{name:'阅读文档',exact:true}).click();
    await expect(page.getByRole('button',{name:/fresh-video/})).toBeVisible();
  }finally{await app.close();}
});

test('five-minute discovery continues during a long model request',async({page,request})=>{
  test.setTimeout(60000);
  const now=Math.floor(Date.now()/1000);
  const app=await harness(page,request,{videos:[{id:'slow-model',published:now-60}]},false);
  try{
    await app.toggle(true);
    await expect.poll(()=>app.exists('model-started'),{timeout:15000}).toBe(true);
    await app.scenario({videos:[{id:'slow-model',published:now-60},{id:'discovered-during-model',published:now+200}]});
    await app.clock(app.now+300);
    const queue=page.getByRole('region',{name:'处理队列',exact:true});
    await expect(queue).toContainText('discovered-during-model',{timeout:10000});
    expect((await app.call('activity.snapshot')).generating).toBe(1);
    expect((await app.requests()).filter(r=>r.endpoint==='subscriptions')).toHaveLength(1);
  }finally{await app.close();}
});

test('caption cooldown and one unavailable channel do not block discovery; pause blocks the next scan',async({page,request})=>{
  const now=Math.floor(Date.now()/1000);
  const initial: Scenario={channels:['alpha','beta'],channel_failure:'alpha',caption_cooldown:true,videos:[{id:'caption-wait',channel:'beta',published:now-30}]};
  const app=await harness(page,request,initial);
  try {
    await app.toggle(true);
    await expect.poll(()=>app.exists('caption-caption-wait')).toBe(true);
    await app.scenario({...initial,videos:[...initial.videos!,{id:'during-cooldown',channel:'beta',published:now+200}]});
    await app.clock(app.now+300);
    await expect(page.getByRole('region',{name:'处理队列',exact:true})).toContainText('during-cooldown');
    await expect(page.getByRole('region',{name:'订阅发现',exact:true}).getByText('部分频道不可用，其他频道继续检查。')).toBeVisible();
    await app.toggle(false);
    const count=(await app.requests()).length;
    await app.clock(app.now+600);
    await page.waitForTimeout(1600);
    expect((await app.requests()).length).toBe(count);
  } finally {await app.close();}
});

for (const mode of ['quota','service','authorization']) {
  test(`global ${mode} gate stops channels and recovers only with Auto Update enabled`,async({page,request})=>{
    test.setTimeout(60000);
    const app=await harness(page,request,{channels:['alpha','beta']});
    try {
      await app.scenario({channels:['alpha','beta'],global_failure:mode});
      await app.toggle(true);
      await expect.poll(async()=>(await app.call('activity.snapshot')).discovery.status).toBe(mode);
      const failed=await app.requests();
      expect(failed.filter(r=>r.endpoint!=='subscriptions')).toHaveLength(mode==='authorization'?2:1);
      await app.toggle(false);
      await app.scenario({channels:['alpha','beta'],videos:[{id:'after-recovery',published:app.now+86400}]});
      await app.clock(app.now+86400);
      await page.waitForTimeout(1600);
      expect((await app.requests()).length).toBe(failed.length);
      if(mode==='authorization') {
        await app.authorize();
        await page.getByRole('button',{name:'处理进度',exact:true}).click();
      }
      await app.toggle(true);
      await expect.poll(async()=>(await app.call('activity.snapshot')).ready,{timeout:15000}).toBe(1);
    } finally {await app.close();}
  });
}

test('bounded scans disclose incomplete coverage and keep uncertain publication pending',async({page,request})=>{
  const now=Math.floor(Date.now()/1000);
  const app=await harness(page,request,{more_pages:true,videos:[
    {id:'old-first',published:now-100*3600}, {id:'ordinary',published:now-60},
    {id:'premiere',published:now-60,kind:'upcoming'},
    {id:'conflicting-time',published:now-60,claimed_publication:now-100*3600},
  ]});
  try {
    await app.toggle(true);
    await expect.poll(async()=>(await app.call('activity.snapshot')).ready).toBe(1);
    const snapshot=await app.call('activity.snapshot');
    expect(snapshot.discovery.status).toBe('partial');
    expect(snapshot.discovery.budget.project_remaining_units).toBeNull();
    await page.getByText('来源状态与预算', {exact:true}).click();
    await expect(page.getByText(/本轮仅检查一页上传列表/)).toBeVisible();
    expect(await app.exists('caption-premiere')).toBe(false);
    expect(await app.exists('caption-conflicting-time')).toBe(false);
    await app.clock(app.now+300);
    await expect.poll(async()=>(await app.requests()).filter(r=>r.endpoint==='playlistItems').length).toBe(2);
    expect((await app.call('activity.snapshot')).ready).toBe(1);
  } finally {await app.close();}
});


test('first list observation survives a failed detail request',async({page,request})=>{
  const app=await harness(page,request,{});
  try {
    const videos=[{id:'observed-before-failure',published:app.now-60}];
    await app.scenario({videos,global_failure:'service',failure_endpoint:'videos'});
    await app.toggle(true);
    await expect.poll(async()=>(await app.call('activity.snapshot')).discovery.status).toBe('service');
    await app.scenario({videos});
    await app.clock(app.now+300);
    await expect.poll(async()=>(await app.call('activity.snapshot')).ready).toBe(1);
    const asset=await app.call('library.inspect',{video_id:'observed-before-failure'});
    expect(asset.source_observed_at).toBe(app.now);
    expect(asset.source_observed_from).toBe(app.now);
    expect(asset.discovered_at).toBe(app.now+300);
  } finally {await app.close();}
});

test('budget scale is visible and membership refresh remains separate',async({page,request})=>{
  const channels=Array.from({length:35},(_,i)=>`channel-${i}`);
  const app=await harness(page,request,{channels});
  try {
    await app.toggle(true);
    await expect.poll(async()=>(await app.call('activity.snapshot')).discovery.scanned_sources).toBe(35);
    await page.getByText('来源状态与预算',{exact:true}).click();
    await expect(page.getByText('订阅规模超过当前扫描或预算容量，无法覆盖所有频道的五分钟检查。')).toBeVisible();
    await app.clock(app.now+300);
    await expect.poll(async()=>(await app.requests()).filter(r=>r.endpoint==='playlistItems').length).toBe(70);
    expect((await app.requests()).filter(r=>r.endpoint==='subscriptions')).toHaveLength(1);
    await app.clock(app.now+21610);
    await expect.poll(async()=>(await app.requests()).filter(r=>r.endpoint==='subscriptions').length).toBe(2);
    await app.toggle(false);
    await page.getByRole('button',{name:'订阅频道',exact:true}).click();
    await page.getByRole('dialog',{name:'订阅频道',exact:true}).getByRole('button',{name:'同步订阅',exact:true}).click();
    await expect.poll(async()=>(await app.requests()).filter(r=>r.endpoint==='subscriptions').length).toBeGreaterThanOrEqual(3);
  } finally {await app.close();}
});
