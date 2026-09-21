import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import i18n from "i18next";
import zh from "../../locales/zh.json";
import en from "../../locales/en.json";
import { DocumentViews } from "./DocumentViews";
import type { Asset, Layout } from "./types";

const video: Asset = {
  video_id: "one", channel_id: "channel", channel_title: "Example",
  title: "An interview", url: "https://www.youtube.com/watch?v=one",
  published_at: "2025-01-02", duration_seconds: 3661,
  preparation_state: "ready", reading_state: "inbox", manuscript_version: 1,
  failure_reason: null, manuscript_characters: 6000,
};

function show(asset: Asset, layout: Layout = "timeline") {
  render(<DocumentViews layout={layout} assets={[asset]} sources={[]} channel=""
    onChannel={() => {}} onSelect={() => {}} searching={false} />);
}

beforeEach(async () => {
  i18n.addResourceBundle("zh", "translation", zh);
  i18n.addResourceBundle("en", "translation", en);
  await i18n.changeLanguage("zh");
});
afterEach(cleanup);

describe("source metadata in reading views", () => {
  for (const language of ["zh", "en"]) {
    for (const layout of ["timeline", "library", "channels"] as const) {
      it(`distinguishes publication, video length and reading time in ${layout} (${language})`, async () => {
        await i18n.changeLanguage(language);
        show(video, layout);
        expect(screen.getByText(language === "zh" ? "发布于 2025-01-02" : "Published 2025-01-02")).toBeTruthy();
        expect(screen.getByText(language === "zh" ? "视频 1 小时 1 分 1 秒" : "Video 1 hr 1 min 1 sec")).toBeTruthy();
        expect(screen.getByText(language === "zh" ? "预计阅读 12 分钟" : "Estimated 12 min read")).toBeTruthy();
      });
    }
  }

  it.each([undefined, null, 0, -1, NaN, Infinity])("shows unknown duration for %s without inventing a source date", duration => {
    show({ ...video, published_at: "", duration_seconds: duration });
    expect(screen.getByText("发布日期未知")).toBeTruthy();
    expect(screen.getByText("时长未知")).toBeTruthy();
    expect(screen.queryByText(/获取中/)).toBeNull();
  });

  it("keeps sub-minute video length separate from reading time", () => {
    show({ ...video, duration_seconds: 18 });
    expect(screen.getByText("视频 18 秒")).toBeTruthy();
    expect(screen.getByText("预计阅读 12 分钟")).toBeTruthy();
  });
});
