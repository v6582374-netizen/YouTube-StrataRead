import {yt} from './text';
import type {DiscoveryState} from './types';

const timeLabel = (value?: number | null) => value ? new Date(value * 1000).toLocaleString() : yt('尚无记录');

export function DiscoveryStatus({discovery, paused}: {discovery?: DiscoveryState; paused: boolean}) {
  if (!discovery) return null;
  const labels: Record<string, string> = {
    healthy: yt('本轮检查完成'), partial: yt('补查未完成'), paused: yt('自动发现已暂停'),
    authorization: yt('YouTube 授权失效，请重新连接。'), quota: yt('YouTube API 项目额度受限'),
    budget: yt('本机 API 日预算已用尽'), service: yt('YouTube 官方 API 暂不可用'),
  };
  const budget = discovery.budget;
  return <section className="yp-discovery-status" aria-label={yt('订阅发现')}>
    <div className="yp-discovery-status-head">
      <strong>YouTube Data API</strong>
      <span role="status">{discovery.scanning ? yt('正在检查订阅') : labels[discovery.status || ''] || yt('尚未扫描')}</span>
    </div>
    <p>{paused ? yt('自动发现已暂停') : yt('来源健康时每 5 分钟检查；字幕与成稿不阻塞发现。')}</p>
    {discovery.error && <p className="yp-discovery-warning">{yt(discovery.error)}</p>}
    <details>
      <summary>{yt('来源状态与预算')}</summary>
      <p>{yt('扫描区间')}：{timeLabel(discovery.started_at)} — {timeLabel(discovery.finished_at)}</p>
      {!paused && <p>{yt('下次正常检查')}：{timeLabel(discovery.next_scan_at)}</p>}
      <p>{yt('首次观测受 API 采样限制，不代表网页首次出现时间；五分钟轮询不是十分钟发现保证。')}</p>
      {budget && <>
        <p>{yt('本机今日记录 {{used}} 次请求，预算上限 {{limit}} 单位；项目实际剩余额度未知。', {used:budget.used_units,limit:budget.local_daily_budget})}</p>
        <p>{yt('完整扫描的每日最低估算 {{units}} 单位；新内容详情、额外分页和重试另计。', {units:budget.minimum_daily_units})}</p>
        {budget.over_capacity && <p className="yp-discovery-warning">{yt('订阅规模超过当前扫描或预算容量，无法覆盖所有频道的五分钟检查。')}</p>}
        <p>{yt('每轮最多 100 个频道，每频道 1 页、每页 50 条；订阅名单每 6 小时同步，可在订阅频道中立即刷新。')}</p>
        <ul>{Object.entries(budget.requests_by_endpoint).map(([resource, count]) => <li key={resource}>{resource}：{count}</li>)}</ul>
        <p>{yt('预算日按美国太平洋时间重置；默认项目配额 10000 不是账户实际余额。')}</p>
      </>}
      <ul>{discovery.sources?.map(source => <li key={source.channel_id}>
        <strong>{source.title}</strong> · {source.error ? yt(source.error) : source.complete ? yt('本轮检查完成') : yt('补查未完成')}
        {source.coverage_reason && <p>{yt(source.coverage_reason)}</p>}
        {source.valid_from != null && source.valid_until != null && <p>{yt('已核查的 API 时间窗口')}：{timeLabel(source.valid_from)} — {timeLabel(source.valid_until)}</p>}
      </li>)}</ul>
    </details>
  </section>;
}
