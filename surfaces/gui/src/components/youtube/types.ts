export type Layout = "timeline" | "library" | "channels";
export type Asset = {
  video_id: string;
  channel_id: string;
  channel_title: string;
  title: string;
  url: string;
  published_at: string;
  preparation_state: string;
  reading_state: string;
  manuscript_version: number | null;
  failure_reason: string | null;
  excerpt?: string;
  manuscript_characters?: number;
};
export type Inspection = Asset & {
  source_trace: { video_url: string; transcript_available: boolean };
  generation_records: { manuscript_version: number; created_at: number }[];
};
export type Source = {
  channel_id: string;
  title: string;
  description?: string;
};
export type Preferences = { sources: Source[]; excluded_channels: string[] };
export type Prompt = { prompt: string; default_prompt: string };
export type Connection = {
  configured: boolean;
  authorized: boolean;
  subscription_count: number;
};
export type Activity = {
  queued: number;
  acquiring: number;
  generating: number;
  ready: number;
  failed: number;
  unavailable: number;
  drain_paused: boolean;
  model_ready: boolean;
  discovery_error: string | null;
  batch: { completed: number; limit: number };
  failures: {
    video_id: string;
    title: string;
    reason: string;
    state: string;
  }[];
};
export const readingTime = (asset: Asset) =>
  asset.manuscript_characters
    ? `约 ${Math.max(1, Math.ceil(asset.manuscript_characters / 500))} 分钟阅读`
    : "";
export const dateLabel = (value: string) => {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return "日期未知";
  const now = new Date();
  const yesterday = new Date();
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return "今天";
  if (date.toDateString() === yesterday.toDateString()) return "昨天";
  return date.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    ...(date.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  });
};
export const excerpt = (value = "") =>
  value
    .replace(/^#+\s+.*$/gm, "")
    .replace(/[`*_>#\[\]]/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 110);
