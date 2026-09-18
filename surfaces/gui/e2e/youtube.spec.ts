import { expect } from '@playwright/test';
import { test } from './fixtures';

for (const width of [800, 1100, 1440]) {
 test(`Edison YouTube sidebar and library at ${width}px`, async ({page}) => {
  await page.setViewportSize({width,height:850});
  if (width === 1100) await page.addInitScript(() => localStorage.setItem('openwork-theme', 'dark'));
  let opened = 0;
  await page.route('**/v1/youtube/capability', async route => {
   const {capability} = route.request().postDataJSON();
   const asset = {video_id:'one',title:'一份用于验证整合的稿件',channel_title:'Example channel',channel_id:'channel',published_at:'2026-09-18',preparation_state:'ready',reading_state:'inbox',manuscript_version:1};
   let result: unknown = {};
   if(capability==='library.list') result={assets:[asset],total:1};
   if(capability==='collection.subscription_sources') result={sources:[]};
   if(capability==='activity.snapshot') result={queued:0,acquiring:0,generating:0,ready:1,failed:0,unavailable:0,drain_paused:false,batch:{completed:1,limit:100},model:'host/shared-model',model_ready:true,volume:{transcript_characters:100,manuscript_characters:50},failures:[]};
   if(capability==='library.inspect') result={...asset,source_trace:{video_url:'https://www.youtube.com/watch?v=one',transcript_available:true},generation_records:[]};
   if(capability==='documents.open') {opened++;result={opened:true};}
   await route.fulfill({json:{ok:true,result}});
  });
  await page.goto('/');
  await page.getByTestId('nav-youtube').click();
  await expect(page.getByRole('heading',{name:'YouTube',exact:true})).toBeVisible();
  await expect(page.getByText(/host\/shared-model/)).toBeVisible();
  await page.getByRole('button',{name:/一份用于验证整合的稿件/}).click();
  await expect(page.getByRole('complementary',{name:'来源检查器'})).toBeVisible();
  expect(opened).toBe(0);
  await page.getByRole('button',{name:'用默认应用打开'}).click();
  await expect.poll(()=>opened).toBe(1);
  await page.getByRole('button',{name:/活动 0/}).click();
  await expect(page.getByRole('region',{name:'批处理活动'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/edison-youtube-${width}.png`,fullPage:true});
 });
}
