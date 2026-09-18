import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { YouTubeView } from './YouTubeView';
import { youtubeCapability } from '../api';

vi.mock('../api', () => ({ youtubeCapability: vi.fn() }));
const call = vi.mocked(youtubeCapability);
const asset = { video_id:'one', channel_id:'channel', channel_title:'Example',title:'Prepared manuscript',url:'https://www.youtube.com/watch?v=one',published_at:'2026-09-18',preparation_state:'ready',reading_state:'inbox',manuscript_version:1 };
const activity = { queued:1, acquiring:0,generating:0,ready:1,failed:0,unavailable:0,drain_paused:false,batch:{completed:1,limit:100},model:'host/model',model_ready:false,volume:{transcript_characters:100,manuscript_characters:50},failures:[] };
beforeEach(() => {
 call.mockReset();
 call.mockImplementation(async (capability) => {
  if(capability==='library.list') return {assets:[asset]};
  if(capability==='activity.snapshot') return activity;
  if(capability==='collection.subscription_sources') return {sources:[]};
  if(capability==='library.inspect') return {...asset, source_trace:{video_url:asset.url,transcript_available:true},generation_records:[]};
  if(capability==='connection.status') return new Promise(() => {});
  return {};
 });
});
afterEach(cleanup);
describe('YouTube module inside Edison', () => {
 it('uses the host model settings and keeps the connection dialog immediate', async () => {
  const settings = vi.fn();
  render(<YouTubeView onModelSettings={settings}/>);
  await screen.findByText(/host\/model/);
  expect(screen.getByText(/新资料会保持排队/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'模型设置'}));
  expect(settings).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole('button',{name:'连接 YouTube'}));
  expect(screen.getByRole('dialog',{name:'连接 YouTube'})).toBeTruthy();
 });
 it('selects a result into provenance without opening an external application',async () => {
  render(<YouTubeView onModelSettings={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/Prepared manuscript/}));
  expect(await screen.findByRole('complementary',{name:'来源检查器'})).toBeTruthy();
  expect(call.mock.calls.some(([capability])=>capability==='documents.open')).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'用默认应用打开'}));
  await waitFor(()=>expect(call).toHaveBeenCalledWith('documents.open',{video_id:'one'}));
 });
 it('keeps All Manuscripts unfiltered and opts transcripts in explicitly',async () => {
  render(<YouTubeView onModelSettings={()=>{}}/>);
  await screen.findByText(/host\/model/);
  fireEvent.click(screen.getByRole('button',{name:'全部稿件'}));
  await waitFor(()=>expect(call).toHaveBeenCalledWith('library.list',{query:'',include_transcript:false}));
  fireEvent.click(screen.getByRole('checkbox',{name:'包含原始字幕'}));
  await waitFor(()=>expect(call).toHaveBeenCalledWith('library.list',{query:'',include_transcript:true}));
 });
});
