import { useState } from "react";
import { useTranslation } from "react-i18next";
import { yt } from "./text";
import { Icon } from "../Icon";
import {
  Asset,
  Layout,
  Source,
  excerpt,
  dateLabel,
  readingTime,
  publicationLabel,
  videoDurationLabel,
} from "./types";

export function ChannelAvatar({ name, thumbnailUrl }: { name: string; thumbnailUrl?: string | null }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const imageUrl = thumbnailUrl?.startsWith("https://") && thumbnailUrl !== failedUrl ? thumbnailUrl : null;
  return (
    <span className="yp-avatar" aria-hidden="true">
      {[...name][0]?.toUpperCase() || "·"}
      {imageUrl && <img src={imageUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailedUrl(imageUrl)} />}
    </span>
  );
}
function Row({
  asset,
  onSelect,
  selectedId,
}: {
  asset: Asset;
  selectedId?: string;
  onSelect: (a: Asset) => void;
}) {
  useTranslation();
  return (
    <button className="yp-row" aria-pressed={asset.video_id === selectedId} onClick={() => onSelect(asset)}>
      <span className="yp-document-cover" aria-hidden="true">{/^[\w-]{11}$/.test(asset.video_id) && <img src={`https://i.ytimg.com/vi/${asset.video_id}/mqdefault.jpg`} alt="" loading="lazy" onError={event => { event.currentTarget.hidden = true; }} />}<Icon name="file" size={26} /><span>{asset.channel_title}</span></span>
      <span className="yp-rowtext">
        <h3>{asset.title}</h3>
        <p className="yp-rowexcerpt">{excerpt(asset.excerpt)}</p>
        <p className="yp-rowbyline">
          <Icon name="file" size={12} />
          <span>{asset.channel_title}</span>
          <span>{videoDurationLabel(asset.duration_seconds)}</span>
          {readingTime(asset) && <span>{readingTime(asset)}</span>}
          {asset.reading_state === "read" && <span>{yt("已读")}</span>}
        </p>

      </span>
      <span className="yp-rowmeta" title={publicationLabel(asset.published_at)}>
        <span aria-hidden="true">{dateLabel(asset.published_at)}</span><span className="sr-only">{publicationLabel(asset.published_at)}</span>
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
  selectedId,
}: {
  layout: Layout;
  assets: Asset[];
  sources: Source[];
  channel: string;
  onChannel: (id: string) => void;
  onSelect: (a: Asset) => void;
  selectedId?: string;
}) {
  useTranslation();
  const thumbnails = new Map(sources.map((source) => [source.channel_id, source.thumbnail_url]));
  if (layout === "library")
    return (
      <div className="yp-grid">
        {assets.map((a) => (
          <button
            key={a.video_id}
            className="yp-document"
            aria-pressed={a.video_id === selectedId}
            onClick={() => onSelect(a)}
          >
            <div className="yp-document-top">
              <ChannelAvatar name={a.channel_title} thumbnailUrl={thumbnails.get(a.channel_id)} />
              <span>{a.channel_title}</span>
              <Icon name="chevronRight" />
            </div>
            <div className="yp-paper-mark">
              <Icon name="file" size={25} />
            </div>
            <h2>{a.title}</h2>
            <p>{excerpt(a.excerpt)}</p>
            <footer>
              <span>{publicationLabel(a.published_at)}</span>
              <span>{videoDurationLabel(a.duration_seconds)}</span>
              <span>{readingTime(a)}</span>
            </footer>
          </button>
        ))}
      </div>
    );
  if (layout === "channels")
    return (
      <div className="yp-source-layout">
        <nav className="yp-source-nav" aria-label={yt("按频道浏览")}>
          <button
            className={!channel ? "chosen" : ""}
            onClick={() => onChannel("")}
          >
            {yt("全部频道")}</button>
          {sources.map((s) => (
            <button
              key={s.channel_id}
              className={channel === s.channel_id ? "chosen" : ""}
              onClick={() => onChannel(s.channel_id)}
            >
              <ChannelAvatar name={s.title} thumbnailUrl={s.thumbnail_url} />
              <span>{s.title}</span>
            </button>
          ))}
        </nav>
        <section className="yp-source-results">
          <div className="yp-source-heading">
            <h2>
              {sources.find((s) => s.channel_id === channel)?.title ||
                yt("所有频道的文档")}
            </h2>
            <span>{assets.length} {yt("篇")}</span>
          </div>
          {assets.length ? (
            assets.map((a) => (
              <Row key={a.video_id} asset={a} onSelect={onSelect} selectedId={selectedId} />
            ))
          ) : (
            <p className="yp-inline-status">{yt("当前筛选下没有文档。")}</p>
          )}
        </section>
      </div>
    );
  return (
    <div className="yp-timeline">
      {assets.map((a) => <Row key={a.video_id} asset={a} onSelect={onSelect} selectedId={selectedId} />)}
    </div>
  );
}
