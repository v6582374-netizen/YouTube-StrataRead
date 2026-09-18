import { Icon } from "../Icon";
import {
  Asset,
  Layout,
  Source,
  dateLabel,
  excerpt,
  readingTime,
} from "./types";

export function ChannelAvatar({ name }: { name: string }) {
  return (
    <span className="yp-avatar" aria-hidden="true">
      {[...name][0]?.toUpperCase() || "·"}
    </span>
  );
}
function Row({
  asset,
  onSelect,
}: {
  asset: Asset;
  onSelect: (a: Asset) => void;
}) {
  return (
    <button className="yp-row" onClick={() => onSelect(asset)}>
      <ChannelAvatar name={asset.channel_title} />
      <span className="yp-rowtext">
        <h3>{asset.title}</h3>
        <p>
          <span>{asset.channel_title}</span>
          <span>{dateLabel(asset.published_at)}</span>
          {asset.reading_state === "read" && <span>已读</span>}
        </p>
      </span>
      <span className="yp-rowmeta">
        <span>{readingTime(asset)}</span>
        <Icon name="file" />
      </span>
    </button>
  );
}
export function DocumentViews({
  layout,
  assets,
  sources,
  channel,
  onChannel,
  onSelect,
  searching,
}: {
  layout: Layout;
  assets: Asset[];
  sources: Source[];
  channel: string;
  onChannel: (id: string) => void;
  onSelect: (a: Asset) => void;
  searching: boolean;
}) {
  if (layout === "library")
    return (
      <div className="yp-grid">
        {assets.map((a) => (
          <button
            key={a.video_id}
            className="yp-document"
            onClick={() => onSelect(a)}
          >
            <div className="yp-document-top">
              <ChannelAvatar name={a.channel_title} />
              <span>{a.channel_title}</span>
              <Icon name="chevronRight" />
            </div>
            <div className="yp-paper-mark">
              <Icon name="file" size={25} />
            </div>
            <h2>{a.title}</h2>
            <p>{excerpt(a.excerpt)}</p>
            <footer>
              <span>{dateLabel(a.published_at)}</span>
              <span>{readingTime(a)}</span>
            </footer>
          </button>
        ))}
      </div>
    );
  if (layout === "channels")
    return (
      <div className="yp-source-layout">
        <nav className="yp-source-nav" aria-label="按频道浏览">
          <button
            className={!channel ? "chosen" : ""}
            onClick={() => onChannel("")}
          >
            全部频道
          </button>
          {sources.map((s) => (
            <button
              key={s.channel_id}
              className={channel === s.channel_id ? "chosen" : ""}
              onClick={() => onChannel(s.channel_id)}
            >
              <ChannelAvatar name={s.title} />
              <span>{s.title}</span>
            </button>
          ))}
        </nav>
        <section className="yp-source-results">
          <div className="yp-source-heading">
            <h2>
              {sources.find((s) => s.channel_id === channel)?.title ||
                "所有频道的文档"}
            </h2>
            <span>{assets.length} 篇</span>
          </div>
          {assets.length ? (
            assets.map((a) => (
              <Row key={a.video_id} asset={a} onSelect={onSelect} />
            ))
          ) : (
            <p className="yp-inline-status">当前筛选下没有文档。</p>
          )}
        </section>
      </div>
    );
  const groups = new Map<string, Asset[]>();
  for (const a of assets) {
    const key = searching ? "搜索结果" : dateLabel(a.published_at);
    groups.set(key, [...(groups.get(key) || []), a]);
  }
  return (
    <div className="yp-timeline">
      {[...groups].map(([day, items]) => (
        <section className="yp-day" key={day}>
          <h2>
            {day}
            <span>{items.length} 篇</span>
          </h2>
          {items.map((a) => (
            <Row key={a.video_id} asset={a} onSelect={onSelect} />
          ))}
        </section>
      ))}
    </div>
  );
}
